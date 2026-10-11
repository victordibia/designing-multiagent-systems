"""
OpenAI BaseChatCompletionClient implementation.

This module provides integration with OpenAI's API using the official
openai>=1.100.2 client library.
"""

import json
import time
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional, Type

from pydantic import BaseModel

try:
    from openai import (
        APIError,
        AsyncOpenAI,
    )
    from openai import AuthenticationError as OpenAIAuthError
    from openai import RateLimitError as OpenAIRateLimitError
    from openai.types.chat import (
        ChatCompletion,
    )
    from openai.types.chat import ChatCompletionChunk as OpenAIChatCompletionChunk
    from openai.types.chat.chat_completion import Choice
    from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
    from openai.types.completion_usage import CompletionUsage
except ImportError:
    raise ImportError(
        "OpenAI library not installed. Please install with: pip install openai>=1.100.2"
    )

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


class OpenAIChatCompletionClientConfig(BaseModel):
    """Configuration for OpenAIChatCompletionClient serialization."""

    model: str = "gpt-4.1-mini"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    organization: Optional[str] = None
    config: Dict[str, Any] = {}


class OpenAIChatCompletionClient(
    Component[OpenAIChatCompletionClientConfig], BaseChatCompletionClient
):
    """
    OpenAI implementation of BaseChatCompletionClient.

    Supports GPT-4, GPT-3.5-turbo, and other OpenAI models with
    function calling capabilities.
    """

    component_config_schema = OpenAIChatCompletionClientConfig
    component_type = "model_client"
    component_provider_override = "picoagents.llm.OpenAIChatCompletionClient"

    def __init__(
        self,
        model: str = "gpt-4.1-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        **kwargs: Any,
    ):
        """
        Initialize OpenAI client.

        Args:
            model: OpenAI model name. For structured output, use "gpt-4o-mini" or "gpt-4o-2024-08-06"+
                   For vision (MultiModalMessage with images), use "gpt-4o", "gpt-4o-mini", or "gpt-4-vision-preview"
            api_key: OpenAI API key (will use OPENAI_API_KEY env var if not provided)
            base_url: Custom base URL for API calls
            organization: OpenAI organization ID
            **kwargs: Additional OpenAI client configuration
        """
        super().__init__(model, api_key, **kwargs)

        self.client = AsyncOpenAI(
            api_key=api_key, base_url=base_url, organization=organization, **kwargs
        )

    async def create(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        output_format: Optional[Type[BaseModel]] = None,
        **kwargs: Any,
    ) -> ChatCompletionResult:
        """
        Make a single OpenAI API call.

        Args:
            messages: List of messages to send
            tools: Optional function definitions for tool calling
            output_format: Optional Pydantic model for structured output
            **kwargs: Additional OpenAI parameters (temperature, max_tokens, etc.)

        Returns:
            Standardized chat completion result
        """
        try:
            start_time = time.time()

            # Convert messages to OpenAI format
            api_messages = self._convert_messages_to_api_format(messages)

            # Prepare request parameters
            request_params = {"model": self.model, "messages": api_messages, **kwargs}

            # Add tools if provided
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = "auto"

            # Add structured output if requested
            if output_format:
                try:
                    # Convert Pydantic model to JSON schema for OpenAI
                    schema = output_format.model_json_schema()

                    # Ensure OpenAI Structured Outputs compatibility
                    schema = self._make_schema_compatible(schema)

                    # Format according to OpenAI documentation
                    request_params["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema.get("title", output_format.__name__),
                            "description": schema.get(
                                "description",
                                f"Structured output for {output_format.__name__}",
                            ),
                            "strict": True,
                            "schema": schema,
                        },
                    }
                except Exception as e:
                    # If schema conversion fails, continue without structured output
                    print(
                        f"Warning: Failed to convert {output_format.__name__} to JSON schema: {e}"
                    )
                    pass

            # Make API call
            response: ChatCompletion = await self.client.chat.completions.create(
                **request_params
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # Extract the assistant message
            choice: Choice = response.choices[0]
            assistant_content = choice.message.content or ""

            # Handle tool calls if present
            tool_calls = []
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    # Only handle function tool calls, skip custom tool calls
                    if tc.type == "function":
                        # Type narrowing: tc is now ChatCompletionMessageFunctionToolCall
                        function_call = tc.function
                        tool_calls.append(
                            ToolCallRequest(
                                tool_name=function_call.name,
                                parameters=json.loads(function_call.arguments)
                                if function_call.arguments
                                else {},
                                call_id=tc.id,
                                extra_content=getattr(tc, "extra_content", None),
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
                    pass

            # Create usage statistics
            usage_data = response.usage
            usage = Usage(
                duration_ms=duration_ms,
                llm_calls=1,
                tokens_input=usage_data.prompt_tokens if usage_data else 0,
                tokens_output=usage_data.completion_tokens if usage_data else 0,
                tool_calls=len(tool_calls),
                cost_estimate=self._estimate_cost(usage_data) if usage_data else None,
            )

            return ChatCompletionResult(
                message=assistant_message,
                usage=usage,
                model=response.model,
                finish_reason=choice.finish_reason or "stop",
                structured_output=structured_output,
            )

        except OpenAIAuthError as e:
            raise AuthenticationError(f"OpenAI authentication failed: {str(e)}")
        except OpenAIRateLimitError as e:
            raise RateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
        except APIError as e:
            raise BaseChatCompletionError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            raise BaseChatCompletionError(f"Unexpected error: {str(e)}")

    async def create_stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        output_format: Optional[Type[BaseModel]] = None,
        stream_options: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Make a streaming OpenAI API call.

        Args:
            messages: List of messages to send
            tools: Optional function definitions for tool calling
            output_format: Optional Pydantic model for structured output (Note: streaming structured output not fully supported yet)
            stream_options: Stream options (defaults to {"include_usage": True} to enable token tracking)
            **kwargs: Additional OpenAI parameters

        Yields:
            ChatCompletionChunk objects with incremental response data (final chunk includes usage if stream_options.include_usage=true)
        """
        try:
            # Note: Streaming structured output is not fully implemented yet
            if output_format:
                print(
                    "Warning: Structured output is not yet supported in streaming mode"
                )

            # Convert messages to OpenAI format
            api_messages = self._convert_messages_to_api_format(messages)

            # Prepare request parameters
            request_params = {
                "model": self.model,
                "messages": api_messages,
                "stream": True,
                **kwargs,
            }

            # Add stream options - default to including usage for token tracking
            if stream_options is None:
                stream_options = {"include_usage": True}
            if stream_options:
                request_params["stream_options"] = stream_options

            # Add tools if provided
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = "auto"

            # Make streaming API call
            stream = await self.client.chat.completions.create(**request_params)

            accumulated_content = ""
            tool_call_chunks = {}
            pending_usage = None

            async for chunk in stream:
                if chunk.usage:
                    pending_usage = chunk.usage
                # Handle usage-only chunk (comes AFTER finish_reason, has empty choices array)
                if hasattr(chunk, "usage") and chunk.usage and (not chunk.choices or len(chunk.choices) == 0):
                    # This is the final usage-only chunk
                    usage_data = Usage(
                        duration_ms=0,  # Duration tracked at agent level
                        llm_calls=1,
                        tokens_input=chunk.usage.prompt_tokens,
                        tokens_output=chunk.usage.completion_tokens,
                        tool_calls=0,  # Tool calls tracked at agent level
                    )
                    yield ChatCompletionChunk(
                        content="",
                        is_complete=True,
                        tool_call_chunk=None,
                        usage=usage_data,
                    )
                    return

                if not chunk.choices:
                    continue

                chunk_choice: ChunkChoice = chunk.choices[0]
                delta = chunk_choice.delta

                # Handle content chunks
                if delta.content:
                    accumulated_content += delta.content
                    yield ChatCompletionChunk(
                        content=delta.content, is_complete=False, tool_call_chunk=None
                    )

                # Handle tool call chunks
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        # Use index as the primary key, fallback to id
                        index = getattr(tc_delta, "index", None)
                        call_id = tc_delta.id

                        # Use index as the tracking key when available
                        tracking_key = index if index is not None else call_id

                        # Initialize tool call entry if not exists
                        if tracking_key not in tool_call_chunks:
                            tool_call_chunks[tracking_key] = {
                                "id": call_id,  # Will be None initially, filled in later
                                "function": {"name": "", "arguments": ""},
                            }

                        # Update the call_id if we have one (first chunk for this index)
                        if call_id:
                            tool_call_chunks[tracking_key]["id"] = call_id

                        extra_content = getattr(tc_delta, "extra_content", None)
                        if extra_content:
                            tool_call_chunks[tracking_key]["extra_content"] = extra_content

                        # Update function data
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_call_chunks[tracking_key]["function"][
                                    "name"
                                ] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_call_chunks[tracking_key]["function"][
                                    "arguments"
                                ] += tc_delta.function.arguments

                        # Yield chunk with the updated state
                        yield ChatCompletionChunk(
                            content="",
                            is_complete=False,
                            tool_call_chunk=tool_call_chunks[tracking_key],
                        )

                # Check if stream is complete (has finish_reason)
                # NOTE: Usage will come in a SEPARATE chunk after this one
                if chunk_choice.finish_reason:
                    # Don't yield completion yet - wait for usage chunk
                    continue

            # Compatible endpoints may attach usage to the final choice rather
            # than send OpenAI's separate usage-only chunk.
            if pending_usage is not None:
                yield ChatCompletionChunk(
                    content="",
                    is_complete=True,
                    usage=Usage(
                        duration_ms=0,
                        llm_calls=1,
                        tokens_input=pending_usage.prompt_tokens,
                        tokens_output=pending_usage.completion_tokens,
                        tool_calls=0,
                    ),
                )

        except OpenAIAuthError as e:
            raise AuthenticationError(f"OpenAI authentication failed: {str(e)}")
        except OpenAIRateLimitError as e:
            raise RateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
        except APIError as e:
            raise BaseChatCompletionError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            raise BaseChatCompletionError(f"Unexpected error: {str(e)}")

    def _estimate_cost(self, usage: CompletionUsage) -> Optional[float]:
        """
        Estimate the cost of the API call based on token usage.

        Note: These are approximate rates and may not reflect current pricing.

        Args:
            usage: OpenAI usage object

        Returns:
            Estimated cost in USD
        """
        # Approximate pricing (as of 2024, rates may vary)
        pricing = {
            "gpt-4": {"input": 0.03 / 1000, "output": 0.06 / 1000},
            "gpt-4-turbo": {"input": 0.01 / 1000, "output": 0.03 / 1000},
            "gpt-3.5-turbo": {"input": 0.0005 / 1000, "output": 0.0015 / 1000},
        }

        model_pricing = pricing.get(
            self.model, pricing["gpt-4"]
        )  # Default to GPT-4 pricing

        input_cost = usage.prompt_tokens * model_pricing["input"]
        output_cost = usage.completion_tokens * model_pricing["output"]

        return input_cost + output_cost

    def _make_schema_compatible(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Modify schema to be compatible with OpenAI Structured Outputs.

        Handles: $defs/$ref, nested objects, array items, and Optional fields.
        OpenAI strict mode requires all properties in 'required' and
        additionalProperties=false on every object.
        """
        compatible_schema = schema.copy()

        # Process $defs (Pydantic nested models generate these)
        if "$defs" in compatible_schema:
            compatible_schema["$defs"] = {
                name: self._make_schema_compatible(defn)
                for name, defn in compatible_schema["$defs"].items()
            }

        if compatible_schema.get("type") == "object":
            compatible_schema["additionalProperties"] = False
            properties = compatible_schema.get("properties", {})

            # OpenAI requires ALL properties in 'required'
            compatible_schema["required"] = list(properties.keys())

            for prop_name, prop_schema in properties.items():
                if isinstance(prop_schema, dict):
                    compatible_schema["properties"][
                        prop_name
                    ] = self._make_schema_compatible(prop_schema)

        if compatible_schema.get("type") == "array":
            items = compatible_schema.get("items")
            if isinstance(items, dict):
                compatible_schema["items"] = self._make_schema_compatible(items)

        return compatible_schema

    def _to_config(self) -> OpenAIChatCompletionClientConfig:
        """Convert client to configuration for serialization."""
        # Extract OpenAI-specific parameters from the client
        base_url = getattr(self.client, "base_url", None)
        organization = getattr(self.client, "organization", None)

        return OpenAIChatCompletionClientConfig(
            model=self.model,
            api_key=self.api_key,
            base_url=str(base_url) if base_url else None,
            organization=organization,
            config=self.config,
        )

    @classmethod
    def _from_config(
        cls, config: OpenAIChatCompletionClientConfig
    ) -> "OpenAIChatCompletionClient":
        """Create client from configuration.

        Args:
            config: Client configuration
        """
        return cls(
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            organization=config.organization,
            **config.config,
        )
