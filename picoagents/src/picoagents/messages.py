"""
Core message types for agent communication using Pydantic models.

This module defines the structured message types that agents use to communicate
with each other and with LLMs, following the OpenAI API format.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union, TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from .types import Usage


class BaseMessage(BaseModel):
    """Base class for all message types."""

    content: str = Field(..., description="The message content")
    source: str = Field(
        ..., description="Source of the message (agent name, system, user, etc.)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now, description="When the message was created"
    )

    class Config:
        frozen = True

    def __str__(self) -> str:
        """Returns a user-friendly string representation."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{self.source}] {time_str} | {self.content}"

    def __repr__(self) -> str:
        """Returns an unambiguous, developer-friendly representation."""
        class_name = self.__class__.__name__
        return f"{class_name}(source='{self.source}', content='{self.content[:50]}...', timestamp='{self.timestamp}')"


class SystemMessage(BaseMessage):
    """System message containing instructions/role definition for the agent."""

    role: Literal["system"] = Field(default="system", description="Message role")


class UserMessage(BaseMessage):
    """User message containing input from human or external system."""

    role: Literal["user"] = Field(default="user", description="Message role")
    name: Optional[str] = Field(default=None, description="Optional name of the user")


class ToolCallRequest(BaseModel):
    """Structured representation of an LLM's tool call request."""

    tool_name: str = Field(..., description="Name of the tool to call")
    parameters: Dict[str, Any] = Field(..., description="Arguments for the tool")
    call_id: str = Field(..., description="Unique identifier for this call")
    extra_content: Optional[Dict[str, Any]] = Field(
        default=None, description="Provider metadata, including Gemini thought signatures"
    )

    class Config:
        frozen = True


class AssistantMessage(BaseMessage):
    """Assistant message containing response from the agent/LLM."""

    role: Literal["assistant"] = Field(default="assistant", description="Message role")
    tool_calls: Optional[List[ToolCallRequest]] = Field(
        default=None, description="Tool calls made by the assistant"
    )
    structured_content: Optional[BaseModel] = Field(
        default=None, description="Structured data when output_format is used"
    )
    usage: Optional["Usage"] = Field(
        default=None, description="Token usage for this LLM call"
    )

    def __str__(self) -> str:
        """Returns a user-friendly string representation."""
        time_str = self.timestamp.strftime("%H:%M:%S")

        if self.tool_calls:
            # Show tool calls information
            tool_info = ", ".join(
                [
                    f"{tc.tool_name}({', '.join(f'{k}={v}' for k, v in tc.parameters.items())})"
                    for tc in self.tool_calls
                ]
            )
            if self.content and self.content.strip():
                return (
                    f"[{self.source}] {time_str} | {self.content} [tools: {tool_info}]"
                )
            else:
                return f"[{self.source}] {time_str} | [calling tools: {tool_info}]"
        else:
            return f"[{self.source}] {time_str} | {self.content}"


class ToolMessage(BaseMessage):
    """Tool message containing result from tool execution."""

    role: Literal["tool"] = Field(default="tool", description="Message role")
    tool_call_id: str = Field(
        ..., description="ID of the tool call this is responding to"
    )
    tool_name: str = Field(..., description="Name of the tool that was executed")
    success: bool = Field(..., description="Whether tool execution succeeded")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Tool-specific metadata (e.g. sub-agent usage)"
    )


class MultiModalMessage(BaseMessage):
    """Message supporting multiple content types (text, images, audio, etc.)."""

    role: Literal["user", "assistant"] = Field(..., description="Message role")
    mime_type: str = Field(
        ...,
        description="MIME type of the content (e.g., 'text/plain', 'image/jpeg', 'audio/wav', 'video/mp4')",
    )
    data: Optional[Union[bytes, str]] = Field(
        default=None, description="Binary data (bytes) or base64 string for the content"
    )
    media_url: Optional[str] = Field(
        default=None, description="URL to media content if data is not provided"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional content metadata"
    )

    @model_validator(mode="after")
    def validate_media_data(self):
        """Ensure either data or media_url is provided."""
        if self.data is None and self.media_url is None:
            raise ValueError("Either 'data' or 'media_url' must be provided")

        if self.data is not None and self.media_url is not None:
            raise ValueError("Only one of 'data' or 'media_url' should be provided")

        return self

    def is_text(self) -> bool:
        """Check if this is a text message."""
        return self.mime_type.startswith("text/")

    def is_image(self) -> bool:
        """Check if this is an image message."""
        return self.mime_type.startswith("image/")

    def is_audio(self) -> bool:
        """Check if this is an audio message."""
        return self.mime_type.startswith("audio/")

    def is_video(self) -> bool:
        """Check if this is a video message."""
        return self.mime_type.startswith("video/")

    def to_base64(self) -> Optional[str]:
        """Convert data to base64 string for API usage."""
        if self.data is None:
            return None

        # If data is already a string, assume it's base64
        if isinstance(self.data, str):
            return self.data

        # If data is bytes, encode to base64
        import base64

        return base64.b64encode(self.data).decode("utf-8")


# Union type for all message types
Message = Union[
    SystemMessage, UserMessage, AssistantMessage, ToolMessage, MultiModalMessage
]
