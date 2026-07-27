import json
from dataclasses import dataclass, field
from typing import Any, Literal

from openai import OpenAI

from .ark_asr import AgentPlanAsrNoTextError, transcribe_agent_plan_audio

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
ARK_AGENT_PLAN_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"

_TRANSCRIBE_PROMPT = (
    "请识别音频中的内容，以文字形式返回识别结果。只输出识别出的文字，不要输出其他内容。"
)
_DISABLED_THINKING = {"thinking": {"type": "disabled"}}

ThinkingMode = Literal["enabled", "disabled"]


class ArkUnavailableError(RuntimeError):
    pass


class ArkAudioNotRecognizedError(ArkUnavailableError):
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
        base_url: str = ARK_BASE_URL,
        *,
        timeout: float = 60.0,
        client: OpenAI | None = None,
    ) -> None:
        self._client = client or OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
        )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._chat_model = chat_model
        self._audio_model = audio_model

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: dict[str, Any] | None = None,
        thinking: ThinkingMode = "disabled",
    ) -> ArkChatResult:
        return self._chat_once(
            messages,
            tools,
            tool_choice=tool_choice,
            thinking=thinking,
        )

    def plan(
        self,
        messages: list[dict[str, Any]],
        submit_plan_tool: dict[str, Any],
    ) -> dict[str, Any]:
        choice = {"type": "function", "function": {"name": "submit_plan"}}
        result = self._chat_once(
            messages,
            [submit_plan_tool],
            tool_choice=choice,
            thinking="disabled",
        )
        if len(result.tool_calls) != 1 or result.tool_calls[0].name != "submit_plan":
            raise ArkUnavailableError("planner did not submit exactly one plan")
        arguments = result.tool_calls[0].arguments
        if not isinstance(arguments, dict):
            raise ArkUnavailableError("plan arguments must be an object")
        return arguments

    def _chat_once(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        tool_choice: dict[str, Any] | None,
        thinking: ThinkingMode,
    ) -> ArkChatResult:
        kwargs: dict[str, Any] = {
            "model": self._chat_model,
            "messages": messages,
            "extra_body": {"thinking": {"type": thinking}},
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        try:
            completion = self._client.chat.completions.create(**kwargs)  # type: ignore[reportUnknownVariableType]
        except Exception as error:  # openai raises a broad exception tree
            raise ArkUnavailableError("chat completion failed") from error
        message = completion.choices[0].message  # type: ignore[reportUnknownMemberType, reportUnknownVariableType]
        tool_calls: list[ArkToolCall] = []
        for call in message.tool_calls or []:  # type: ignore[reportUnknownVariableType, reportUnknownMemberType]
            try:
                arguments = json.loads(call.function.arguments or "{}")  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            except json.JSONDecodeError as error:
                raise ArkUnavailableError("malformed tool call arguments") from error
            if not isinstance(arguments, dict):
                raise ArkUnavailableError("tool call arguments must be an object")
            tool_calls.append(
                ArkToolCall(
                    id=call.id,  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                    name=call.function.name,  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                    arguments=arguments,
                )
            )
        return ArkChatResult(
            content=message.content or "",  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            tool_calls=tool_calls,
            raw_message=message.model_dump(exclude_none=True),  # type: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        )

    def transcribe(self, audio_base64: str, audio_format: str) -> str:
        if self._base_url == ARK_AGENT_PLAN_BASE_URL:
            try:
                return transcribe_agent_plan_audio(
                    self._api_key,
                    audio_base64,
                    audio_format,
                    self._timeout,
                )
            except AgentPlanAsrNoTextError as error:
                raise ArkAudioNotRecognizedError(
                    "audio contained no recognized text"
                ) from error
            except Exception as error:
                raise ArkUnavailableError("audio transcription failed") from error

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
                extra_body=_DISABLED_THINKING,
            )
        except Exception as error:
            raise ArkUnavailableError("audio transcription failed") from error
        return completion.choices[0].message.content or ""
