"""
Anthropic BaseChatCompletionClient implementation.

This module provides integration with Anthropic's Claude API using the official
anthropic>=0.73.0 client library.
"""

import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Type

from pydantic import BaseModel

try:
    from anthropic import (
        APIError,
        AsyncAnthropic,
        AsyncMessageStream,
    )
    from anthropic import AuthenticationError as AnthropicAuthError
    from anthropic import RateLimitError as AnthropicRateLimitError
    from anthropic.types import Message as AnthropicMessage
    from anthropic.types import ContentBlock, ToolUseBlock
    _ANTHROPIC_AVAILABLE = True
except ImportError:  # optional extra - fail when the client is used, not on import
    _ANTHROPIC_AVAILABLE = False
    APIError = AsyncAnthropic = AsyncMessageStream = None  # type: ignore[assignment,misc]
    AnthropicAuthError = AnthropicRateLimitError = None  # type: ignore[assignment,misc]
    AnthropicMessage = ContentBlock = ToolUseBlock = None  # type: ignore[assignment,misc]

from .._component_config import Component
from ..messages import AssistantMessage, Message, ToolCallRequest
from ..types import ChatCompletionChunk, ChatCompletionResult, Usage
from ._base import (
    AuthenticationError,
    BaseChatCompletionClient,
    BaseChatCompletionError,
    InvalidRequestError,
    RateLimitError,
)


class AnthropicChatCompletionClientConfig(BaseModel):
    """Configuration for AnthropicChatCompletionClient serialization."""

    model: str = "claude-sonnet-4-5"  # Sonnet supports structured outputs
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    config: Dict[str, Any] = {}


class AnthropicChatCompletionClient(
    Component[AnthropicChatCompletionClientConfig], BaseChatCompletionClient
):
    """
    Anthropic implementation of BaseChatCompletionClient.

    Supports Claude 3 models (Opus, Sonnet, Haiku) with
    function calling and structured output capabilities.
    """

    component_config_schema = AnthropicChatCompletionClientConfig
    component_type = "model_client"
    component_provider_override = "picoagents.llm.AnthropicChatCompletionClient"

    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ):
        """
        Initialize Anthropic client.

        Args:
            model: Anthropic model name (e.g., "claude-sonnet-4-5", "claude-opus-4-1")
                   Note: Only Sonnet 4.5 and Opus 4.1 support structured outputs
            api_key: Anthropic API key (will use ANTHROPIC_API_KEY env var if not provided)
            base_url: Custom base URL for API calls
            **kwargs: Additional Anthropic client configuration

        Raises:
            ImportError: If the optional `anthropic` extra is not installed.
        """
        if not _ANTHROPIC_AVAILABLE:
            raise ImportError(
                "AnthropicChatCompletionClient requires the anthropic extra. "
                'Install it with: pip install "picoagents[anthropic]"'
            )
        super().__init__(model, api_key, **kwargs)

        self.client = AsyncAnthropic(
            api_key=api_key, base_url=base_url, **kwargs
        )

    async def create(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        output_format: Optional[Type[BaseModel]] = None,
        **kwargs: Any,
    ) -> ChatCompletionResult:
        """
        Make a single Anthropic API call.

        Args:
            messages: List of messages to send
            tools: Optional function definitions for tool calling
            output_format: Optional Pydantic model for structured output
            **kwargs: Additional Anthropic parameters (temperature, max_tokens, etc.)

        Returns:
            Standardized chat completion result
        """
        try:
            start_time = time.time()

            # Convert messages to Anthropic format
            api_messages = self._convert_messages_to_anthropic_format(messages)

            # Extract system message if present (Anthropic uses separate system parameter)
            system_message = None
            if api_messages and api_messages[0]["role"] == "system":
                system_message = api_messages[0]["content"]
                api_messages = api_messages[1:]

            # Prepare request parameters
            request_params = {
                "model": self.model,
                "messages": api_messages,
                "max_tokens": kwargs.get("max_tokens", 4096),  # Anthropic requires max_tokens
            }

            # Add system message if present
            if system_message:
                request_params["system"] = system_message

            # Add temperature if provided
            if "temperature" in kwargs:
                request_params["temperature"] = kwargs["temperature"]

            # Add tools if provided
            if tools:
                request_params["tools"] = self._convert_tools_to_anthropic_format(tools)

            # Add structured output if requested
            if output_format:
                # For structured outputs, we need to use beta features
                request_params["betas"] = ["structured-outputs-2025-11-13"]

                # Convert Pydantic model to JSON schema
                schema = output_format.model_json_schema()

                # Add Anthropic-specific formatting - note: 'schema' not 'json_schema'
                request_params["output_format"] = {
                    "type": "json_schema",
                    "schema": self._make_schema_compatible(schema)
                }

            # Make API call
            if output_format:
                # Use beta.messages for structured outputs
                response: AnthropicMessage = await self.client.beta.messages.create(
                    **request_params
                )
            else:
                response: AnthropicMessage = await self.client.messages.create(
                    **request_params
                )

            duration_ms = int((time.time() - start_time) * 1000)

            # Extract content and tool calls
            assistant_content = ""
            tool_calls = []

            for block in response.content:
                if hasattr(block, "text"):  # TextBlock
                    assistant_content += block.text
                elif isinstance(block, ToolUseBlock):
                    tool_calls.append(
                        ToolCallRequest(
                            tool_name=block.name,
                            parameters=block.input if isinstance(block.input, dict) else {},
                            call_id=block.id,
                        )
                    )

            assistant_message = AssistantMessage(
                content=assistant_content,
                source="llm",  # Temporary source, will be overwritten by agent
                tool_calls=tool_calls if tool_calls else None,
            )

            # Parse structured output if requested
            structured_output = None
            if output_format and assistant_content:
                try:
                    # Try to parse the JSON content using the provided Pydantic model
                    structured_output = output_format.model_validate_json(
                        assistant_content
                    )
                except Exception as e:
                    # If parsing fails, log warning but continue with text response
                    print(f"Warning: Failed to parse structured output: {e}")

            # Create usage statistics
            usage = Usage(
                duration_ms=duration_ms,
                llm_calls=1,
                tokens_input=response.usage.input_tokens,
                tokens_output=response.usage.output_tokens,
                tool_calls=len(tool_calls),
                cost_estimate=self._estimate_cost(
                    response.usage.input_tokens,
                    response.usage.output_tokens
                ),
            )

            return ChatCompletionResult(
                message=assistant_message,
                usage=usage,
                model=response.model,
                finish_reason=response.stop_reason or "stop",
                structured_output=structured_output,
            )

        except AnthropicAuthError as e:
            raise AuthenticationError(f"Anthropic authentication failed: {str(e)}")
        except AnthropicRateLimitError as e:
            raise RateLimitError(f"Anthropic rate limit exceeded: {str(e)}")
        except APIError as e:
            raise BaseChatCompletionError(f"Anthropic API error: {str(e)}")
        except Exception as e:
            raise BaseChatCompletionError(f"Unexpected error: {str(e)}")

    async def create_stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        output_format: Optional[Type[BaseModel]] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Make a streaming Anthropic API call.

        Args:
            messages: List of messages to send
            tools: Optional function definitions for tool calling
            output_format: Optional Pydantic model for structured output
            **kwargs: Additional Anthropic parameters

        Yields:
            ChatCompletionChunk objects with incremental response data
        """
        try:
            if output_format:
                print(
                    "Warning: Structured output is not yet supported in streaming mode"
                )

            # Convert messages to Anthropic format
            api_messages = self._convert_messages_to_anthropic_format(messages)

            # Extract system message if present
            system_message = None
            if api_messages and api_messages[0]["role"] == "system":
                system_message = api_messages[0]["content"]
                api_messages = api_messages[1:]

            # Prepare request parameters
            request_params = {
                "model": self.model,
                "messages": api_messages,
                "max_tokens": kwargs.get("max_tokens", 4096),
            }

            if system_message:
                request_params["system"] = system_message

            if "temperature" in kwargs:
                request_params["temperature"] = kwargs["temperature"]

            if tools:
                request_params["tools"] = self._convert_tools_to_anthropic_format(tools)

            # Create stream using context manager
            async with self.client.messages.stream(**request_params) as stream:
                accumulated_content = ""
                tool_call_chunks = {}

                async for event in stream:
                    # Handle different event types
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            # Text content chunk
                            accumulated_content += event.delta.text
                            yield ChatCompletionChunk(
                                content=event.delta.text,
                                is_complete=False,
                                tool_call_chunk=None,
                            )
                        elif hasattr(event.delta, "partial_json"):
                            # Tool use chunk (streaming tool input)
                            block_index = event.index
                            if block_index not in tool_call_chunks:
                                tool_call_chunks[block_index] = {
                                    "id": f"call_{block_index}",
                                    "function": {
                                        "name": "",
                                        "arguments": ""
                                    }
                                }

                            # Append partial JSON to arguments
                            tool_call_chunks[block_index]["function"]["arguments"] += event.delta.partial_json

                            yield ChatCompletionChunk(
                                content="",
                                is_complete=False,
                                tool_call_chunk=tool_call_chunks[block_index],
                            )

                    elif event.type == "content_block_start":
                        # Initialize tool call if it's a tool use block
                        if hasattr(event.content_block, "name"):
                            block_index = event.index
                            tool_call_chunks[block_index] = {
                                "id": event.content_block.id,
                                "function": {
                                    "name": event.content_block.name,
                                    "arguments": ""
                                }
                            }

                # Get final message for usage stats
                final_message = await stream.get_final_message()

                # Send final chunk with usage
                usage_data = Usage(
                    duration_ms=0,  # Duration tracked at agent level
                    llm_calls=1,
                    tokens_input=final_message.usage.input_tokens,
                    tokens_output=final_message.usage.output_tokens,
                    tool_calls=len(tool_call_chunks),
                )

                yield ChatCompletionChunk(
                    content="",
                    is_complete=True,
                    tool_call_chunk=None,
                    usage=usage_data,
                )

        except AnthropicAuthError as e:
            raise AuthenticationError(f"Anthropic authentication failed: {str(e)}")
        except AnthropicRateLimitError as e:
            raise RateLimitError(f"Anthropic rate limit exceeded: {str(e)}")
        except APIError as e:
            raise BaseChatCompletionError(f"Anthropic API error: {str(e)}")
        except Exception as e:
            raise BaseChatCompletionError(f"Unexpected error: {str(e)}")

    def _convert_messages_to_anthropic_format(
        self, messages: List[Message]
    ) -> List[Dict[str, Any]]:
        """
        Convert internal Message objects to Anthropic API format.

        Args:
            messages: List of internal Message objects

        Returns:
            List of messages in Anthropic API format
        """
        from ..messages import AssistantMessage, MultiModalMessage, ToolMessage

        api_messages = []

        for msg in messages:
            if msg.role == "system":
                # System messages are handled separately in Anthropic
                api_messages.append({"role": "system", "content": msg.content})
            elif isinstance(msg, MultiModalMessage):
                # Handle multimodal messages
                content_parts = []

                if msg.content and msg.content.strip():
                    content_parts.append({
                        "type": "text",
                        "text": msg.content
                    })

                if msg.is_image() and (msg.data or msg.media_url):
                    if msg.data:
                        # Use base64 data
                        base64_data = msg.to_base64()
                        content_parts.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": msg.mime_type,
                                "data": base64_data
                            }
                        })
                    elif msg.media_url:
                        # Anthropic doesn't support URLs directly, would need to download
                        print("Warning: Anthropic API doesn't support image URLs directly")

                api_messages.append({
                    "role": msg.role,
                    "content": content_parts if content_parts else msg.content
                })
            elif isinstance(msg, AssistantMessage) and msg.tool_calls:
                # Handle assistant messages with tool calls
                content_blocks = []

                # Add text content if present
                if msg.content:
                    content_blocks.append({
                        "type": "text",
                        "text": msg.content
                    })

                # Add tool use blocks
                for tc in msg.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.call_id,
                        "name": tc.tool_name,
                        "input": tc.parameters
                    })

                api_messages.append({
                    "role": "assistant",
                    "content": content_blocks
                })
            elif isinstance(msg, ToolMessage):
                # Handle tool response messages
                api_messages.append({
                    "role": "user",  # Anthropic uses "user" role for tool results
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content
                        }
                    ]
                })
            else:
                # Regular text messages
                api_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })

        return api_messages

    def _convert_tools_to_anthropic_format(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert OpenAI-style tool definitions to Anthropic format.

        Args:
            tools: List of OpenAI-format tool definitions

        Returns:
            List of Anthropic-format tool definitions
        """
        anthropic_tools = []

        for tool in tools:
            if tool.get("type") == "function":
                function = tool.get("function", {})
                anthropic_tools.append({
                    "name": function.get("name"),
                    "description": function.get("description", ""),
                    "input_schema": function.get("parameters", {})
                })

        return anthropic_tools

    def _make_schema_compatible(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Modify schema to be compatible with Anthropic Structured Outputs requirements.

        Args:
            schema: The JSON schema to make compatible

        Returns:
            Modified schema with Anthropic compatibility fixes
        """
        # Make a copy to avoid modifying the original
        compatible_schema = schema.copy()

        # Ensure additionalProperties is False for objects
        if compatible_schema.get("type") == "object":
            compatible_schema["additionalProperties"] = False

            # Recursively apply to nested objects
            properties = compatible_schema.get("properties", {})
            for prop_name, prop_schema in properties.items():
                if isinstance(prop_schema, dict):
                    compatible_schema["properties"][prop_name] = self._make_schema_compatible(
                        prop_schema
                    )

        # Handle arrays with object items
        if compatible_schema.get("type") == "array":
            items = compatible_schema.get("items")
            if isinstance(items, dict):
                compatible_schema["items"] = self._make_schema_compatible(items)

        return compatible_schema

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Estimate the cost of the API call based on token usage.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Estimated cost in USD
        """
        # Approximate pricing for Claude models (as of 2024)
        pricing = {
            "claude-3-5-sonnet": {"input": 0.003 / 1000, "output": 0.015 / 1000},
            "claude-3-opus": {"input": 0.015 / 1000, "output": 0.075 / 1000},
            "claude-3-sonnet": {"input": 0.003 / 1000, "output": 0.015 / 1000},
            "claude-3-haiku": {"input": 0.00025 / 1000, "output": 0.00125 / 1000},
        }

        # Match model prefix
        model_pricing = None
        for model_prefix, prices in pricing.items():
            if self.model.startswith(model_prefix):
                model_pricing = prices
                break

        if not model_pricing:
            # Default to Sonnet pricing if model not recognized
            model_pricing = pricing["claude-3-sonnet"]

        input_cost = input_tokens * model_pricing["input"]
        output_cost = output_tokens * model_pricing["output"]

        return input_cost + output_cost

    def _to_config(self) -> AnthropicChatCompletionClientConfig:
        """Convert client to configuration for serialization."""
        base_url = getattr(self.client, "base_url", None)

        return AnthropicChatCompletionClientConfig(
            model=self.model,
            api_key=self.api_key,
            base_url=str(base_url) if base_url else None,
            config=self.config,
        )

    @classmethod
    def _from_config(
        cls, config: AnthropicChatCompletionClientConfig
    ) -> "AnthropicChatCompletionClient":
        """Create client from configuration.

        Args:
            config: Client configuration
        """
        return cls(
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            **config.config,
        )