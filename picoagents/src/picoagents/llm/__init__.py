"""
LLM client implementations for picoagents framework.

Provides unified interface for different language model providers
with standardized response formats and error handling.
"""

from ._anthropic import AnthropicChatCompletionClient
from ._azure_openai import AzureOpenAIChatCompletionClient
from ._base import (
    AuthenticationError,
    BaseChatCompletionClient,
    BaseChatCompletionError,
    InvalidRequestError,
    RateLimitError,
)
from ._openai import OpenAIChatCompletionClient
from ._gemini import GeminiChatCompletionClient

__all__ = [
    "BaseChatCompletionClient",
    "BaseChatCompletionError",
    "RateLimitError",
    "AuthenticationError",
    "InvalidRequestError",
    "OpenAIChatCompletionClient",
    "GeminiChatCompletionClient",
    "AzureOpenAIChatCompletionClient",
    "AnthropicChatCompletionClient",
]
