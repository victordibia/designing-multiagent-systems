/**
 * ContentRenderer - Renders different content types based on message type
 */

import { useState } from "react";
import {
  Download,
  FileText,
  AlertCircle,
  Code,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type {
  AssistantMessage,
  ToolMessage,
} from "@/types";
import {
  isMultiModalMessage,
  isAssistantMessage,
  isToolMessage
} from "@/types";
import type { RenderProps, MultiModalRenderProps } from "./types";

function TextContentRenderer({ message, isStreaming, className }: RenderProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const content = message.content;
  const TRUNCATE_LENGTH = 1600;
  const shouldTruncate = content.length > TRUNCATE_LENGTH && !isStreaming;
  const displayText = shouldTruncate && !isExpanded
    ? content.slice(0, TRUNCATE_LENGTH) + "..."
    : content;

  return (
    <div className={`whitespace-pre-wrap break-words ${className || ""}`}>
      <div className={isExpanded && shouldTruncate ? "max-h-96 overflow-y-auto" : ""}>
        {displayText}
      </div>
      {isStreaming && (
        <span className="ml-1 inline-block h-2 w-2 animate-pulse rounded-full bg-current" />
      )}
      {shouldTruncate && (
        <div className="flex justify-end mt-1">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="inline-flex items-center gap-1 text-xs
                       bg-background/80 hover:bg-background border border-border/50 hover:border-border
                       text-muted-foreground hover:text-foreground
                       transition-colors cursor-pointer px-2 py-1 rounded"
          >
            {isExpanded ? (
              <>
                less <ChevronUp className="h-3 w-3" />
              </>
            ) : (
              <>
                {(content.length - TRUNCATE_LENGTH).toLocaleString()} more{" "}
                <ChevronDown className="h-3 w-3" />
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

function MultiModalContentRenderer({ message, className }: MultiModalRenderProps) {
  const [imageError, setImageError] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  const isImage = message.mime_type.startsWith("image/");
  const isPdf = message.mime_type === "application/pdf";
  const isAudio = message.mime_type.startsWith("audio/");
  const isVideo = message.mime_type.startsWith("video/");

  // Create data URI if we have base64 data
  const dataUri = message.data
    ? `data:${message.mime_type};base64,${message.data}`
    : message.media_url;

  const filename = message.metadata?.filename || "attachment";

  if (isImage && dataUri && !imageError) {
    return (
      <div className={`my-2 ${className || ""}`}>
        <img
          src={dataUri}
          alt={filename}
          className={`rounded-lg border max-w-full transition-all cursor-pointer ${
            isExpanded ? "max-h-none" : "max-h-64"
          }`}
          onClick={() => setIsExpanded(!isExpanded)}
          onError={() => setImageError(true)}
        />
        <div className="text-xs text-muted-foreground mt-1">
          {message.mime_type} • {filename} • Click to {isExpanded ? "collapse" : "expand"}
        </div>
        {message.content && (
          <div className="mt-2 text-sm">{message.content}</div>
        )}
      </div>
    );
  }

  // Fallback for non-images or failed images
  return (
    <div className={`my-2 p-3 border rounded-lg bg-muted ${className || ""}`}>
      <div className="flex items-center gap-2">
        {isPdf ? (
          <FileText className="h-4 w-4 text-destructive" />
        ) : isAudio ? (
          <div className="h-4 w-4 rounded-full bg-success" />
        ) : isVideo ? (
          <div className="h-4 w-4 rounded-sm bg-info" />
        ) : (
          <Download className="h-4 w-4" />
        )}
        <span className="text-sm font-medium">
          {isPdf ? "PDF Document" :
           isAudio ? "Audio File" :
           isVideo ? "Video File" :
           "File Attachment"}
        </span>
        <span className="text-xs text-muted-foreground">({message.mime_type})</span>
      </div>

      {message.content && (
        <div className="mt-2 text-sm">{message.content}</div>
      )}

      {dataUri && (
        <Button
          variant="outline"
          size="sm"
          className="mt-2"
          onClick={() => {
            const link = document.createElement("a");
            link.href = dataUri;
            link.download = filename;
            link.click();
          }}
        >
          <Download className="h-3 w-3 mr-1" />
          Download {filename}
        </Button>
      )}
    </div>
  );
}

function ToolCallRenderer({ message }: { message: AssistantMessage; className?: string }) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!message.tool_calls || message.tool_calls.length === 0) return null;

  return (
    <div className="my-2 space-y-2">
      {message.tool_calls.map((toolCall, index) => {
        let parsedParams;
        try {
          parsedParams = typeof toolCall.parameters === "string"
            ? JSON.parse(toolCall.parameters)
            : toolCall.parameters;
        } catch {
          parsedParams = toolCall.parameters;
        }

        return (
          <div key={index} className="p-3 border border-info/40 rounded-lg bg-info/10">
            <div
              className="flex items-center gap-2 cursor-pointer"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              <Code className="h-4 w-4 text-info" />
              <span className="text-sm font-medium">
                Tool Call: {toolCall.tool_name}
              </span>
              <span className="text-xs text-muted-foreground">{isExpanded ? "▼" : "▶"}</span>
            </div>
            {isExpanded && (
              <div className="mt-2 text-xs font-mono bg-background p-2 rounded border">
                <div className="text-muted-foreground mb-1">Parameters:</div>
                <pre className="whitespace-pre-wrap">
                  {JSON.stringify(parsedParams, null, 2)}
                </pre>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ToolResultRenderer({ message, className }: { message: ToolMessage; className?: string }) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className={`my-2 p-3 border rounded-lg ${message.success ? 'border-success/40 bg-success/10' : 'border-destructive/40 bg-destructive/10'} ${className || ""}`}>
      <div
        className="flex items-center gap-2 cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {message.success ? (
          <Code className="h-4 w-4 text-success" />
        ) : (
          <AlertCircle className="h-4 w-4 text-destructive" />
        )}
        <span className={`text-sm font-medium `}>
          Tool Result: {message.tool_name} {message.success ? '✓' : '✗'}
        </span>
        <span className={`text-xs text-muted-foreground`}>
          {isExpanded ? "▼" : "▶"}
        </span>
      </div>
      {isExpanded && (
        <div className="mt-2 text-xs font-mono bg-background p-2 rounded border">
          {message.error ? (
            <div className="text-destructive">Error: {message.error}</div>
          ) : (
            <pre className="whitespace-pre-wrap">{message.content}</pre>
          )}
        </div>
      )}
    </div>
  );
}

export function ContentRenderer({ message, isStreaming, className }: RenderProps) {
  // Handle MultiModalMessage
  if (isMultiModalMessage(message)) {
    return (
      <div>
        <MultiModalContentRenderer
          message={message}
          isStreaming={isStreaming}
          className={className}
        />
      </div>
    );
  }

  // Handle AssistantMessage with tool calls
  if (isAssistantMessage(message) && message.tool_calls) {
    return (
      <div>
        {message.content && (
          <TextContentRenderer
            message={message}
            isStreaming={isStreaming}
            className={className}
          />
        )}
        <ToolCallRenderer message={message} className={className} />
      </div>
    );
  }

  // Handle ToolMessage
  if (isToolMessage(message)) {
    return <ToolResultRenderer message={message} className={className} />;
  }

  // Default: render as text
  return (
    <TextContentRenderer
      message={message}
      isStreaming={isStreaming}
      className={className}
    />
  );
}