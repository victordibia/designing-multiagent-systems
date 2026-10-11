"""Gemini chat completions through Google's OpenAI-compatible API.

See https://ai.google.dev/gemini-api/docs/openai. Reusing the OpenAI
adapter keeps messages, tools, structured output, and errors consistent.
"""

import os
from typing import Any, AsyncGenerator, Dict, List, Optional, Type

from openai.types.completion_usage import CompletionUsage
from pydantic import BaseModel, Field

from ..messages import AssistantMessage, Message, ToolMessage
from ..types import ChatCompletionChunk
from ._openai import OpenAIChatCompletionClient

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class GeminiChatCompletionClientConfig(BaseModel):
    """Serializable Gemini connection configuration."""

    model: str = "gemini-3.1-flash-lite"
    api_key: Optional[str] = None
    base_url: str = GEMINI_BASE_URL
    config: Dict[str, Any] = Field(default_factory=dict)


class GeminiChatCompletionClient(OpenAIChatCompletionClient):
    """Gemini implementation of the PicoAgents chat completion interface.

    Uses the existing OpenAI SDK; no additional package is required. Supply
    an AI Studio API key explicitly or set GEMINI_API_KEY (GOOGLE_API_KEY
    is also accepted). Model availability and free-tier quotas vary.
    """

    component_config_schema = GeminiChatCompletionClientConfig
    component_provider_override = "picoagents.llm.GeminiChatCompletionClient"

    def __init__(
        self,
        model: str = "gemini-3.1-flash-lite",
        api_key: Optional[str] = None,
        base_url: str = GEMINI_BASE_URL,
        **kwargs: Any,
    ):
        resolved_key = (
            api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        )
        if not resolved_key:
            raise ValueError(
                "Gemini API key is required: pass api_key or set GEMINI_API_KEY "
                "(or GOOGLE_API_KEY). Get a key at https://aistudio.google.com/apikey"
            )
        super().__init__(model=model, api_key=resolved_key, base_url=base_url, **kwargs)
        # Preserve environment-based credentials as environment references on export.
        self.api_key = api_key

    def _estimate_cost(self, usage: CompletionUsage) -> Optional[float]:
        """Do not apply OpenAI prices or assume the account uses the free tier."""
        return None

    def _convert_messages_to_api_format(
        self, messages: List[Message]
    ) -> List[Dict[str, Any]]:
        """Return thought signatures on the exact function call that supplied them."""
        converted = super()._convert_messages_to_api_format(messages)
        for message, api_message in zip(messages, converted):
            if isinstance(message, AssistantMessage) and message.tool_calls:
                for call, api_call in zip(
                    message.tool_calls, api_message["tool_calls"]
                ):
                    if call.extra_content is not None:
                        api_call["extra_content"] = call.extra_content
            if isinstance(message, ToolMessage):
                api_message["name"] = message.tool_name
        return converted

    async def create_stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        output_format: Optional[Type[BaseModel]] = None,
        stream_options: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Stream using the shared adapter, ensuring a terminal chunk is emitted.

        Some compatible endpoints omit the trailing usage chunk, and callers
        can disable it. The agent still needs a completion signal in that case.
        Structured output has the same streaming limitation as the OpenAI client.
        """
        complete = False
        async for chunk in super().create_stream(
            messages, tools, output_format, stream_options=stream_options, **kwargs
        ):
            complete = complete or chunk.is_complete
            yield chunk
        if not complete:
            yield ChatCompletionChunk(content="", is_complete=True)

    def _to_config(self) -> GeminiChatCompletionClientConfig:
        return GeminiChatCompletionClientConfig(
            model=self.model,
            api_key=self.api_key,
            base_url=str(self.client.base_url),
            config=self.config,
        )

    @classmethod
    def _from_config(
        cls, config: GeminiChatCompletionClientConfig
    ) -> "GeminiChatCompletionClient":
        return cls(
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            **config.config,
        )
