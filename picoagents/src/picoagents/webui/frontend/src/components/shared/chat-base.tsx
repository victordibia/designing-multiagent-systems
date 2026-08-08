/**
 * ChatBase - Rich chat interface for PicoAgents with multimodal support
 * Provides chat UI with message display, file upload, and rich content rendering
 */

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageInput } from "@/components/ui/message-input";
import { MessageRenderer } from "@/components/message_renderer";
import { User, Bot, Trash2, StopCircle, ArrowUp, ArrowDown } from "lucide-react";
import type { Message, UserMessage } from "@/types";
import type { AttachmentItem } from "@/components/ui/attachment-gallery";
import { createMultiModalMessage } from "@/utils/message-utils";

interface ChatBaseProps {
  messages: Message[];
  onSendMessage: (messages: Message[]) => Promise<void>; // Updated to accept Message array
  onClearMessages: () => void;
  onStop?: () => void; // Optional callback to stop streaming
  isStreaming: boolean;
  placeholder?: string;
  emptyStateTitle?: string;
  emptyStateDescription?: string;
  emptyStateCustom?: React.ReactNode; // Optional custom empty state component
  beforeInput?: React.ReactNode; // Optional content to render above input (e.g., approval banner)
  messageUsage?: Map<number, { tokens_input: number; tokens_output: number }>; // Optional token usage per message
}

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
  usage?: { tokens_input: number; tokens_output: number }; // Optional usage for this message
}

function MessageBubble({ message, isStreaming, usage }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const Icon = isUser ? User : Bot;

  // Show agent name for multi-agent orchestrator messages
  const showAgentName = !isUser && message.source && message.source !== "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-md border ${
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        }`}
      >
        <Icon className="h-4 w-4" />
      </div>

      <div
        className={`flex flex-col space-y-1 ${
          isUser ? "items-end" : "items-start"
        } max-w-[80%]`}
      >
        {/* Agent name label - shown above message for multi-agent orchestrators */}
        {showAgentName && (
          <div className="text-xs font-medium text-muted-foreground px-1">
            {message.source}
          </div>
        )}

        <div
          className={`rounded px-3 py-2 text-sm ${
            isUser ? "bg-primary text-primary-foreground" : "bg-muted"
          }`}
        >
          <MessageRenderer
            message={message}
            isStreaming={isStreaming}
          />
        </div>
        {/* Token usage - show for assistant messages with usage data */}
        {!isUser && usage && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground px-1">
            <div className="flex items-center gap-1">
              <ArrowUp className="h-3 w-3" />
              <span>{usage.tokens_input.toLocaleString()}</span>
            </div>
            <div className="flex items-center gap-1">
              <ArrowDown className="h-3 w-3" />
              <span>{usage.tokens_output.toLocaleString()}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-md border bg-muted">
        <Bot className="h-4 w-4" />
      </div>
      <div className="flex items-center space-x-1 rounded bg-muted px-3 py-2">
        <div className="flex space-x-1">
          <div className="h-2 w-2 animate-bounce rounded-full bg-current [animation-delay:-0.3s]" />
          <div className="h-2 w-2 animate-bounce rounded-full bg-current [animation-delay:-0.15s]" />
          <div className="h-2 w-2 animate-bounce rounded-full bg-current" />
        </div>
      </div>
    </div>
  );
}

export function ChatBase({
  messages,
  onSendMessage,
  onClearMessages,
  onStop,
  isStreaming,
  placeholder = "Type a message...",
  emptyStateTitle = "Start a conversation",
  emptyStateDescription = "Type a message below to begin",
  emptyStateCustom,
  beforeInput,
  messageUsage,
}: ChatBaseProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  // Handle message sending with text and attachments
  const handleSendMessage = async (text: string, attachments: AttachmentItem[]) => {
    if ((!text.trim() && attachments.length === 0) || isSubmitting || isStreaming) {
      return;
    }

    setIsSubmitting(true);

    try {
      const messagesToSend: Message[] = [];

      if (attachments.length > 0) {
        // Send multimodal messages for attachments
        for (const attachment of attachments) {
          const multiModalMsg = await createMultiModalMessage(
            text || `Uploaded ${attachment.file.name}`,
            attachment.file,
            "user"
          );
          messagesToSend.push(multiModalMsg);
        }
      } else if (text.trim()) {
        // Send regular text message
        const userMsg: UserMessage = {
          role: "user",
          content: text.trim(),
          source: "user",
        };
        messagesToSend.push(userMsg);
      }

      await onSendMessage(messagesToSend);
    } catch (error) {
      console.error("Failed to send message:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Messages */}
      <ScrollArea className="flex-1 min-h-0 p-4 overflow-auto" ref={scrollAreaRef}>
        <div className="space-y-4">
          {messages.length === 0 ? (
            emptyStateCustom || (
              <div className="flex flex-col items-center justify-center h-32 text-center">
                <div className="text-muted-foreground text-sm">{emptyStateTitle}</div>
                <div className="text-xs text-muted-foreground mt-1">
                  {emptyStateDescription}
                </div>
              </div>
            )
          ) : (
            <>
              {messages.map((message, index) => {
                // Check if this is the last message and streaming
                const isLastMessage = index === messages.length - 1;
                const shouldShowStreaming = isStreaming && isLastMessage && message.role === "assistant";

                // Get usage for this message if available (check both message.usage and messageUsage Map for backwards compatibility)
                const usage = (message as any).usage || messageUsage?.get(index);

                return (
                  <MessageBubble
                    key={index}
                    message={message}
                    isStreaming={shouldShowStreaming}
                    usage={usage}
                  />
                );
              })}
              {isStreaming && <TypingIndicator />}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Action Buttons */}
      {(messages.length > 0 || isStreaming) && (
        <div className="px-4 py-2 border-t flex gap-2">
          {isStreaming && onStop && (
            <Button
              variant="destructive"
              size="sm"
              onClick={onStop}
              className="gap-1"
            >
              <StopCircle className="h-3 w-3" />
              Stop
            </Button>
          )}
          {messages.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={onClearMessages}
              disabled={isStreaming}
              className="gap-1"
            >
              <Trash2 className="h-3 w-3" />
              Clear Chat
            </Button>
          )}
        </div>
      )}

      {/* Optional content above input (e.g., approval banner) */}
      {beforeInput}

      {/* Enhanced Input with File Upload */}
      <MessageInput
        onSendMessage={handleSendMessage}
        disabled={isSubmitting || isStreaming}
        placeholder={placeholder}
      />
    </div>
  );
}