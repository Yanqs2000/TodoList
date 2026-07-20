import json
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

_TRANSCRIBE_PROMPT = (
    "请识别音频中的内容，以文字形式返回识别结果。只输出识别出的文字，不要输出其他内容。"
)
_DISABLED_THINKING = {"thinking": {"type": "disabled"}}


class ArkUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArkToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ArkChatResult:
    content: str
    tool_calls: list[ArkToolCall] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    raw_message: dict[str, Any] = field(default_factory=dict)  # type: ignore[reportUnknownVariableType]


class ArkClient:
    def __init__(
        self,
        api_key: str,
        chat_model: str,
        audio_model: str,
        *,
        timeout: float = 60.0,
        client: OpenAI | None = None,
    ) -> None:
        self._client = client or OpenAI(
            base_url=ARK_BASE_URL,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
        )
        self._chat_model = chat_model
        self._audio_model = audio_model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ArkChatResult:
        kwargs: dict[str, Any] = {
            "model": self._chat_model,
            "messages": messages,
            "extra_body": _DISABLED_THINKING,
        }
        if tools:
            kwargs["tools"] = tools
        try:
            completion = self._client.chat.completions.create(**kwargs)  # type: ignore[reportUnknownVariableType]
        except Exception as error:  # openai raises a broad exception tree
            raise ArkUnavailableError("chat completion failed") from error
        message = completion.choices[0].message  # type: ignore[reportUnknownMemberType, reportUnknownVariableType]
        tool_calls = [
            ArkToolCall(
                id=call.id,  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                name=call.function.name,  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                arguments=json.loads(call.function.arguments or "{}"),  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            )
            for call in message.tool_calls or []  # type: ignore[reportUnknownVariableType, reportUnknownMemberType]
        ]
        return ArkChatResult(
            content=message.content or "",  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            tool_calls=tool_calls,
            raw_message=message.model_dump(exclude_none=True),  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        )

    def transcribe(self, audio_base64: str, audio_format: str) -> str:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_base64, "format": audio_format},
                    },
                    {"type": "text", "text": _TRANSCRIBE_PROMPT},
                ],
            }
        ]
        try:
            completion = self._client.chat.completions.create(
                model=self._audio_model,
                messages=messages,  # type: ignore[arg-type]
            )
        except Exception as error:
            raise ArkUnavailableError("audio transcription failed") from error
        return completion.choices[0].message.content or ""
