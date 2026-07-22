import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from openai import BadRequestError, OpenAI

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

_TRANSCRIBE_PROMPT = (
    "请识别音频中的内容，以文字形式返回识别结果。只输出识别出的文字，不要输出其他内容。"
)
_DISABLED_THINKING = {"thinking": {"type": "disabled"}}
_LOGGER = logging.getLogger(__name__)

ThinkingMode = Literal["enabled", "disabled"]


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
        self._chat_model = chat_model
        self._audio_model = audio_model
        self.planning_thinking_supported: bool | None = None

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
            propagate_bad_request=False,
        )

    def plan(
        self,
        messages: list[dict[str, Any]],
        submit_plan_tool: dict[str, Any],
    ) -> dict[str, Any]:
        choice = {"type": "function", "function": {"name": "submit_plan"}}
        if self.planning_thinking_supported is False:
            result = self._chat_once(
                messages,
                [submit_plan_tool],
                tool_choice=choice,
                thinking="disabled",
                propagate_bad_request=False,
            )
        else:
            try:
                result = self._chat_once(
                    messages,
                    [submit_plan_tool],
                    tool_choice=choice,
                    thinking="enabled",
                    propagate_bad_request=True,
                )
                self.planning_thinking_supported = True
            except BadRequestError:
                self.planning_thinking_supported = False
                self._capability_event("assistant_planner_thinking_fallback")
                result = self._chat_once(
                    messages,
                    [submit_plan_tool],
                    tool_choice=choice,
                    thinking="disabled",
                    propagate_bad_request=False,
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
        propagate_bad_request: bool,
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
        except BadRequestError as error:
            if propagate_bad_request:
                raise
            raise ArkUnavailableError("chat completion failed") from error
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

    def _capability_event(self, event_name: str) -> None:
        _LOGGER.info(event_name)

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
                extra_body=_DISABLED_THINKING,
            )
        except Exception as error:
            raise ArkUnavailableError("audio transcription failed") from error
        return completion.choices[0].message.content or ""
