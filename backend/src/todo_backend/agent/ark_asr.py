import base64
import binascii
import gzip
import io
import json
import struct
import uuid
import wave
from audioop import lin2lin, ratecv, tomono
from dataclasses import dataclass
from typing import Any, cast

import websockets.sync.client

AGENT_PLAN_ASR_URL = "wss://openspeech.bytedance.com/api/v3/plan/sauc/bigmodel_nostream"
AGENT_PLAN_ASR_RESOURCE_ID = "volc.seedasr.sauc.duration"

_CLIENT_FULL_REQUEST = 0b0001
_CLIENT_AUDIO_REQUEST = 0b0010
_SERVER_FULL_RESPONSE = 0b1001
_SERVER_ERROR_RESPONSE = 0b1111
_POSITIVE_SEQUENCE = 0b0001
_LAST_SEQUENCE = 0b0011
_GZIP_JSON = 0x11
_AUDIO_CHUNK_BYTES = 64 * 1024
_MP3_CHUNK_BYTES = 3200


class AgentPlanAsrError(RuntimeError):
    pass


class AgentPlanAsrNoTextError(AgentPlanAsrError):
    pass


@dataclass(frozen=True)
class _AsrResponse:
    code: int
    is_last: bool
    payload: dict[str, Any]


def transcribe_agent_plan_audio(
    api_key: str,
    audio_base64: str,
    audio_format: str,
    timeout: float,
) -> str:
    if audio_format not in {"wav", "mp3"}:
        raise AgentPlanAsrError(f"unsupported Agent Plan ASR format: {audio_format}")
    try:
        audio = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise AgentPlanAsrError("invalid base64 audio") from error
    if not audio:
        raise AgentPlanAsrError("audio is empty")
    if audio_format == "wav":
        audio = _normalize_wav(audio)

    request_id = str(uuid.uuid4())
    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": AGENT_PLAN_ASR_RESOURCE_ID,
        "X-Api-Request-Id": request_id,
        "X-Api-Connect-Id": request_id,
        "X-Api-Sequence": "-1",
    }
    try:
        with websockets.sync.client.connect(
            AGENT_PLAN_ASR_URL,
            additional_headers=headers,
            open_timeout=timeout,
            close_timeout=5,
        ) as websocket:
            websocket.send(_full_request(1, audio_format))
            initial = _parse_response(_receive_bytes(websocket, timeout))
            _raise_for_error(initial)

            chunk_bytes = (
                _MP3_CHUNK_BYTES if audio_format == "mp3" else _AUDIO_CHUNK_BYTES
            )
            chunks = [
                audio[offset : offset + chunk_bytes]
                for offset in range(0, len(audio), chunk_bytes)
            ]
            for index, chunk in enumerate(chunks, start=2):
                websocket.send(
                    _audio_request(index, chunk, is_last=index == len(chunks) + 1)
                )

            transcript = ""
            while True:
                response = _parse_response(_receive_bytes(websocket, timeout))
                _raise_for_error(response)
                result_value: object = response.payload.get("result")
                if isinstance(result_value, dict):
                    result = cast(dict[str, object], result_value)
                    text = result.get("text")
                    if isinstance(text, str) and text.strip():
                        transcript = text.strip()
                if response.is_last:
                    break
    except AgentPlanAsrError:
        raise
    except Exception as error:
        raise AgentPlanAsrError("Agent Plan ASR request failed") from error

    if not transcript:
        raise AgentPlanAsrNoTextError("Agent Plan ASR returned no text")
    return transcript


def _normalize_wav(audio: bytes) -> bytes:
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            channels = source.getnchannels()
            sample_width = source.getsampwidth()
            sample_rate = source.getframerate()
            compression = source.getcomptype()
            frames = source.readframes(source.getnframes())
    except (EOFError, wave.Error):
        return audio
    if compression != "NONE" or channels not in {1, 2}:
        raise AgentPlanAsrError("Agent Plan ASR requires mono or stereo PCM WAV audio")
    if channels == 2:
        frames = tomono(frames, sample_width, 0.5, 0.5)
    if sample_width != 2:
        frames = lin2lin(frames, sample_width, 2)
    if sample_rate != 16000:
        frames, _state = ratecv(frames, 2, 1, sample_rate, 16000, None)
    if channels == 1 and sample_width == 2 and sample_rate == 16000:
        return audio
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes(frames)
    return output.getvalue()


def _full_request(sequence: int, audio_format: str) -> bytes:
    payload = gzip.compress(
        json.dumps(
            {
                "user": {"uid": "todo-list"},
                "audio": {
                    "format": audio_format,
                    "codec": "raw",
                    "rate": 16000,
                    "bits": 16,
                    "channel": 1,
                },
                "request": {
                    "model_name": "bigmodel",
                    "enable_itn": True,
                    "enable_punc": True,
                    "enable_ddc": True,
                    "show_utterances": True,
                    "enable_nonstream": False,
                },
            },
            separators=(",", ":"),
        ).encode()
    )
    return (
        _header(_CLIENT_FULL_REQUEST, _POSITIVE_SEQUENCE)
        + struct.pack(">iI", sequence, len(payload))
        + payload
    )


def _audio_request(sequence: int, audio: bytes, *, is_last: bool) -> bytes:
    payload = gzip.compress(audio)
    flags = _LAST_SEQUENCE if is_last else _POSITIVE_SEQUENCE
    wire_sequence = -sequence if is_last else sequence
    return (
        _header(_CLIENT_AUDIO_REQUEST, flags)
        + struct.pack(">iI", wire_sequence, len(payload))
        + payload
    )


def _header(message_type: int, flags: int) -> bytes:
    return bytes([0x11, (message_type << 4) | flags, _GZIP_JSON, 0x00])


def _receive_bytes(websocket: Any, timeout: float) -> bytes:
    message = websocket.recv(timeout=timeout)
    if not isinstance(message, bytes):
        raise AgentPlanAsrError("Agent Plan ASR returned a non-binary message")
    return message


def _parse_response(message: bytes) -> _AsrResponse:
    if len(message) < 4:
        raise AgentPlanAsrError("Agent Plan ASR returned a truncated response")
    header_size = (message[0] & 0x0F) * 4
    message_type = message[1] >> 4
    flags = message[1] & 0x0F
    compression = message[2] & 0x0F
    payload = message[header_size:]

    if flags & 0b0001:
        if len(payload) < 4:
            raise AgentPlanAsrError("Agent Plan ASR response omitted its sequence")
        payload = payload[4:]
    is_last = bool(flags & 0b0010)
    if flags & 0b0100:
        if len(payload) < 4:
            raise AgentPlanAsrError("Agent Plan ASR response omitted its event")
        payload = payload[4:]

    code = 0
    if message_type == _SERVER_FULL_RESPONSE:
        if len(payload) < 4:
            raise AgentPlanAsrError("Agent Plan ASR response omitted its size")
        size = struct.unpack(">I", payload[:4])[0]
        payload = payload[4 : 4 + size]
    elif message_type == _SERVER_ERROR_RESPONSE:
        if len(payload) < 8:
            raise AgentPlanAsrError("Agent Plan ASR error response was truncated")
        code, size = struct.unpack(">iI", payload[:8])
        payload = payload[8 : 8 + size]
    else:
        raise AgentPlanAsrError(
            f"Agent Plan ASR returned unknown message type: {message_type}"
        )

    if compression == 0b0001 and payload:
        try:
            payload = gzip.decompress(payload)
        except gzip.BadGzipFile as error:
            raise AgentPlanAsrError(
                "Agent Plan ASR response was not valid gzip"
            ) from error
    try:
        decoded_value: object = json.loads(payload.decode()) if payload else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AgentPlanAsrError("Agent Plan ASR response was not valid JSON") from error
    if not isinstance(decoded_value, dict):
        raise AgentPlanAsrError("Agent Plan ASR response must be an object")
    decoded = cast(dict[str, Any], decoded_value)
    return _AsrResponse(code=code, is_last=is_last, payload=decoded)


def _raise_for_error(response: _AsrResponse) -> None:
    if response.code != 0:
        raise AgentPlanAsrError(f"Agent Plan ASR failed with code {response.code}")
