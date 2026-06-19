"""LLM client with full tool_call cycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from openai import OpenAI

from app.config import Settings
from app.llm.providers import FallbackBackend, resolve_llm_credentials
from app.llm.text_tool_calls import parse_text_tool_calls
from app.prompts.loader import build_system_prompt
from app.tools import ToolHandlers, get_openai_tools


@dataclass
class ChatResult:
    text: str
    tool_calls_made: int
    model: str


@dataclass(frozen=True)
class _ParsedFunction:
    name: str
    arguments: str


@dataclass(frozen=True)
class _ParsedToolCall:
    id: str
    function: _ParsedFunction


class ToolCallClient:
    """Ассистент: system prompt из шаблона + цикл tool_call → handler → ответ."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        provider: Literal["primary", "fallback"] = "primary",
        fallback_backend: FallbackBackend | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.provider = provider

        credentials = resolve_llm_credentials(
            self.settings,
            provider,
            fallback_backend=fallback_backend,
        )
        self._backend = credentials.backend
        self._model = credentials.model
        self._client = OpenAI(api_key=credentials.api_key, base_url=credentials.base_url)
        self._system_prompt = build_system_prompt(self.settings.service_name)
        if provider == "fallback":
            self._system_prompt += (
                "\n\nНапоминание: ты обязан отвечать на русском языке, "
                "даже если контекст tool на английском."
            )
        self._tools = get_openai_tools(self.settings.service_name)
        self._handlers = ToolHandlers(
            knowledge_base_path=self.settings.knowledge_base_path,
            docs_dir=self.settings.docs_dir,
            methodology_dir=self.settings.methodology_dir,
            shablon_path=self.settings.shablon_path,
        )

    def chat(self, user_message: str) -> ChatResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_message},
        ]
        tool_calls_made = 0

        for round_num in range(1, self.settings.max_tool_rounds + 1):
            print(f"  → LLM раунд {round_num}/{self.settings.max_tool_rounds}...", flush=True)
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=self._tools,
                tool_choice="auto",
                temperature=0.2,
                timeout=self.settings.request_timeout_seconds,
            )
            assistant_message = response.choices[0].message
            tool_calls = list(assistant_message.tool_calls or [])
            parsed_from_text = False

            if not tool_calls:
                text_calls = parse_text_tool_calls(assistant_message.content)
                if text_calls:
                    parsed_from_text = True
                    tool_calls = [
                        _ParsedToolCall(
                            id=f"parsed_{round_num}_{index}",
                            function=_ParsedFunction(name=name, arguments=arguments),
                        )
                        for index, (name, arguments) in enumerate(text_calls)
                    ]

            if parsed_from_text:
                messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_message.content or "",
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": tool_call.function.arguments,
                                },
                            }
                            for tool_call in tool_calls
                        ],
                    }
                )
            else:
                messages.append(assistant_message.model_dump(exclude_none=True))

            if not tool_calls:
                text = (assistant_message.content or "").strip()
                return ChatResult(text=text, tool_calls_made=tool_calls_made, model=self._model)

            for tool_call in tool_calls:
                tool_calls_made += 1
                suffix = " (из текста)" if parsed_from_text else ""
                print(f"    tool: {tool_call.function.name}{suffix}", flush=True)
                result = self._handlers.dispatch(
                    tool_call.function.name,
                    tool_call.function.arguments,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

        return ChatResult(
            text="Не удалось завершить диалог: превышено число раундов tool_call.",
            tool_calls_made=tool_calls_made,
            model=self._model,
        )

    def chat_json(self, user_message: str) -> dict[str, Any]:
        result = self.chat(user_message)
        return {
            "answer": result.text,
            "tool_calls_made": result.tool_calls_made,
            "model": result.model,
        }

    def chat_sectioned(
        self,
        user_message: str,
        *,
        feature_name: str | None = None,
        protocol: str | None = None,
    ) -> ChatResult:
        """Пошаговая генерация: kit-tool → секция → склейка (без одного огромного контекста)."""
        from app.llm.section_orchestrator import SectionOrchestrator

        return SectionOrchestrator(self).generate(
            user_message,
            feature_name=feature_name,
            protocol=protocol,
        )

    def chat_sectioned_json(
        self,
        user_message: str,
        *,
        feature_name: str | None = None,
        protocol: str | None = None,
    ) -> dict[str, Any]:
        result = self.chat_sectioned(
            user_message,
            feature_name=feature_name,
            protocol=protocol,
        )
        return {
            "answer": result.text,
            "tool_calls_made": result.tool_calls_made,
            "model": result.model,
        }
