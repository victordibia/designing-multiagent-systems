"""
Tests for model client implementations.

This module tests various LLM client implementations including:
- OpenAI
- Azure OpenAI
- Anthropic
"""

import os
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from picoagents.llm import (
    AnthropicChatCompletionClient,
    AzureOpenAIChatCompletionClient,
    BaseChatCompletionClient,
    OpenAIChatCompletionClient,
)
from picoagents.messages import (
    AssistantMessage,
    SystemMessage,
    ToolCallRequest,
    ToolMessage,
    UserMessage,
)


class TestOutput(BaseModel):
    """Test structured output model."""
    name: str
    value: int


class TestModelClients:
    """Test suite for model client implementations."""

    @pytest.fixture
    def messages(self):
        """Sample messages for testing."""
        return [
            SystemMessage(content="You are a helpful assistant", source="system"),
            UserMessage(content="Hello, how are you?", source="user"),
        ]

    @pytest.fixture
    def tools(self):
        """Sample tools for testing."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"}
                        },
                        "required": ["location"]
                    }
                }
            }
        ]

    def test_client_inheritance(self):
        """Test that all clients inherit from BaseChatCompletionClient."""
        assert issubclass(OpenAIChatCompletionClient, BaseChatCompletionClient)
        assert issubclass(AzureOpenAIChatCompletionClient, BaseChatCompletionClient)
        assert issubclass(AnthropicChatCompletionClient, BaseChatCompletionClient)

    def test_client_initialization(self):
        """Test client initialization with various parameters."""
        # OpenAI client
        openai_client = OpenAIChatCompletionClient(
            model="gpt-4",
            api_key="test-key"
        )
        assert openai_client.model == "gpt-4"
        assert openai_client.api_key == "test-key"

        # Azure OpenAI client
        azure_client = AzureOpenAIChatCompletionClient(
            azure_endpoint="https://test.openai.azure.com",
            azure_deployment="test-deployment",
            api_key="test-key",
            api_version="2024-02-15-preview"
        )
        assert azure_client.azure_deployment == "test-deployment"

        # Anthropic client
        anthropic_client = AnthropicChatCompletionClient(
            model="claude-3-5-sonnet-20241022",
            api_key="test-key"
        )
        assert anthropic_client.model == "claude-3-5-sonnet-20241022"
        assert anthropic_client.api_key == "test-key"

    def test_component_types(self):
        """Test that all clients have correct component type."""
        openai_client = OpenAIChatCompletionClient(api_key="test")
        azure_client = AzureOpenAIChatCompletionClient(
            azure_endpoint="https://test.openai.azure.com",
            azure_deployment="test",
            api_key="test"
        )
        anthropic_client = AnthropicChatCompletionClient(api_key="test")

        assert openai_client.component_type == "model_client"
        assert azure_client.component_type == "model_client"
        assert anthropic_client.component_type == "model_client"

    @pytest.mark.asyncio
    async def test_openai_message_conversion(self, messages):
        """Test OpenAI message format conversion."""
        client = OpenAIChatCompletionClient(api_key="test")

        # Test basic message conversion
        converted = client._convert_messages_to_api_format(messages)
        assert len(converted) == 2
        assert converted[0]["role"] == "system"
        assert converted[0]["content"] == "You are a helpful assistant"
        assert converted[1]["role"] == "user"
        assert converted[1]["content"] == "Hello, how are you?"

        # Test with tool calls
        messages_with_tools = messages + [
            AssistantMessage(
                content="I'll check the weather",
                source="assistant",
                tool_calls=[
                    ToolCallRequest(
                        tool_name="get_weather",
                        parameters={"location": "Paris"},
                        call_id="call_123"
                    )
                ]
            ),
            ToolMessage(
                content="It's sunny in Paris",
                tool_call_id="call_123",
                tool_name="get_weather",
                success=True,
                source="tool"
            )
        ]

        converted = client._convert_messages_to_api_format(messages_with_tools)
        assert len(converted) == 4
        assert "tool_calls" in converted[2]
        assert converted[3]["role"] == "tool"
        assert converted[3]["tool_call_id"] == "call_123"

    @pytest.mark.asyncio
    async def test_anthropic_message_conversion(self, messages):
        """Test Anthropic message format conversion."""
        client = AnthropicChatCompletionClient(api_key="test")

        # Test basic message conversion
        converted = client._convert_messages_to_anthropic_format(messages)
        assert len(converted) == 2
        assert converted[0]["role"] == "system"
        assert converted[1]["role"] == "user"

        # Test with tool calls
        messages_with_tools = messages + [
            AssistantMessage(
                content="I'll check the weather",
                source="assistant",
                tool_calls=[
                    ToolCallRequest(
                        tool_name="get_weather",
                        parameters={"location": "Paris"},
                        call_id="call_123"
                    )
                ]
            )
        ]

        converted = client._convert_messages_to_anthropic_format(messages_with_tools)
        assert len(converted) == 3
        # Anthropic uses content blocks for tool calls
        assert isinstance(converted[2]["content"], list)
        assert any(block.get("type") == "tool_use" for block in converted[2]["content"])

    def test_anthropic_tool_conversion(self, tools):
        """Test conversion of OpenAI tools to Anthropic format."""
        client = AnthropicChatCompletionClient(api_key="test")

        converted = client._convert_tools_to_anthropic_format(tools)
        assert len(converted) == 1
        assert converted[0]["name"] == "get_weather"
        assert converted[0]["description"] == "Get weather for a location"
        assert "input_schema" in converted[0]
        assert converted[0]["input_schema"]["properties"]["location"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_openai_create_with_mock(self, messages):
        """Test OpenAI client create method with mocked API."""
        with patch('picoagents.llm._openai.AsyncOpenAI') as MockOpenAI:
            # Setup mock
            mock_client = AsyncMock()
            MockOpenAI.return_value = mock_client

            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Hello! I'm doing well."
            mock_response.choices[0].message.tool_calls = None
            mock_response.choices[0].finish_reason = "stop"
            mock_response.model = "gpt-4"
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 5

            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            # Test
            client = OpenAIChatCompletionClient(model="gpt-4", api_key="test")
            result = await client.create(messages)

            assert result.message.content == "Hello! I'm doing well."
            assert result.model == "gpt-4"
            assert result.usage.tokens_input == 10
            assert result.usage.tokens_output == 5

    @pytest.mark.asyncio
    async def test_anthropic_create_with_mock(self, messages):
        """Test Anthropic client create method with mocked API."""
        with patch('picoagents.llm._anthropic.AsyncAnthropic') as MockAnthropic:
            # Setup mock
            mock_client = AsyncMock()
            MockAnthropic.return_value = mock_client

            # Mock text content block
            mock_text_block = MagicMock()
            mock_text_block.text = "Hello! I'm Claude."

            mock_response = MagicMock()
            mock_response.content = [mock_text_block]
            mock_response.model = "claude-3-5-sonnet-20241022"
            mock_response.stop_reason = "end_turn"
            mock_response.usage.input_tokens = 10
            mock_response.usage.output_tokens = 5

            mock_client.messages.create = AsyncMock(return_value=mock_response)

            # Test
            client = AnthropicChatCompletionClient(
                model="claude-3-5-sonnet-20241022",
                api_key="test"
            )
            result = await client.create(messages)

            assert result.message.content == "Hello! I'm Claude."
            assert result.model == "claude-3-5-sonnet-20241022"
            assert result.usage.tokens_input == 10
            assert result.usage.tokens_output == 5

    def test_serialization_configs(self):
        """Test that all clients can be serialized to config."""
        # OpenAI
        openai_client = OpenAIChatCompletionClient(
            model="gpt-4",
            api_key="test-key"
        )
        openai_config = openai_client._to_config()
        assert openai_config.model == "gpt-4"
        assert openai_config.api_key == "test-key"

        # Azure OpenAI
        azure_client = AzureOpenAIChatCompletionClient(
            azure_endpoint="https://test.openai.azure.com",
            azure_deployment="test-deployment",
            api_key="test-key"
        )
        azure_config = azure_client._to_config()
        assert azure_config.azure_deployment == "test-deployment"

        # Anthropic
        anthropic_client = AnthropicChatCompletionClient(
            model="claude-3-5-sonnet-20241022",
            api_key="test-key"
        )
        anthropic_config = anthropic_client._to_config()
        assert anthropic_config.model == "claude-3-5-sonnet-20241022"
        assert anthropic_config.api_key == "test-key"

    def test_deserialization_from_config(self):
        """Test that clients can be deserialized from config."""
        # OpenAI
        openai_client = OpenAIChatCompletionClient(
            model="gpt-4",
            api_key="test-key"
        )
        config = openai_client._to_config()
        restored = OpenAIChatCompletionClient._from_config(config)
        assert restored.model == "gpt-4"
        assert restored.api_key == "test-key"

        # Anthropic
        anthropic_client = AnthropicChatCompletionClient(
            model="claude-3-5-sonnet-20241022",
            api_key="test-key"
        )
        config = anthropic_client._to_config()
        restored = AnthropicChatCompletionClient._from_config(config)
        assert restored.model == "claude-3-5-sonnet-20241022"
        assert restored.api_key == "test-key"

    @pytest.mark.asyncio
    async def test_streaming_interface(self):
        """Test that all clients implement the streaming interface."""
        clients = [
            OpenAIChatCompletionClient(api_key="test"),
            AnthropicChatCompletionClient(api_key="test"),
            AzureOpenAIChatCompletionClient(
                azure_endpoint="https://test.openai.azure.com",
                azure_deployment="test",
                api_key="test"
            )
        ]

        for client in clients:
            assert hasattr(client, 'create_stream')
            assert callable(client.create_stream)

    def test_cost_estimation(self):
        """Test cost estimation methods."""
        # OpenAI cost estimation
        openai_client = OpenAIChatCompletionClient(
            model="gpt-4",
            api_key="test"
        )

        # Mock usage object
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50

        cost = openai_client._estimate_cost(mock_usage)
        assert isinstance(cost, float)
        assert cost > 0

        # Anthropic cost estimation
        anthropic_client = AnthropicChatCompletionClient(
            model="claude-3-5-sonnet-20241022",
            api_key="test"
        )

        cost = anthropic_client._estimate_cost(100, 50)
        assert isinstance(cost, float)
        assert cost > 0


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("AZURE_OPENAI_API_KEY"),
    reason="AZURE_OPENAI_API_KEY not set"
)
class TestOpenAIIntegration:
    """Integration tests for Azure OpenAI client (requires API key)."""

    @pytest.mark.asyncio
    async def test_openai_basic_completion(self):
        """Test actual Azure OpenAI API call."""
        client = AzureOpenAIChatCompletionClient(
            model="gpt-4.1-mini",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        )

        messages = [
            UserMessage(
                content="Say 'Hello' in one word",
                source="user",
            )
        ]

        result = await client.create(messages, max_tokens=10)
        assert result.message.content.strip() != ""
        assert "hello" in result.message.content.lower()


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set"
)
class TestAnthropicIntegration:
    """Integration tests for Anthropic client (requires API key)."""

    @pytest.mark.asyncio
    async def test_anthropic_basic_completion(self):
        """Test actual Anthropic API call."""
        client = AnthropicChatCompletionClient(
            model="claude-haiku-4-5",
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

        messages = [
            UserMessage(content="Say 'Hello' in one word", source="user")
        ]

        result = await client.create(messages, max_tokens=10)
        assert result.message.content.strip() != ""
        assert "hello" in result.message.content.lower()