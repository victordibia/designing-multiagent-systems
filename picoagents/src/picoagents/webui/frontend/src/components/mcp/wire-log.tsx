/**
 * WireLog - raw JSON-RPC frame inspector for an MCP server connection.
 *
 * Every request, response, and notification with direction and timestamp.
 * This is where the 2026 stateless model is visible: each request carries
 * its own _meta, negotiation is server/discover, and there is no initialize.
 */

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { ArrowDownLeft, ArrowUpRight, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { McpWireFrame } from "@/types/mcp";

function frameLabel(frame: McpWireFrame): string {
  const message = frame.message;
  if (message.method) return message.method;
  if ("result" in message) return `response (id ${message.id ?? "?"})`;
  if ("error" in message) return `error (id ${message.id ?? "?"})`;
  return "frame";
}

function FrameRow({ frame }: { frame: McpWireFrame }) {
  const [expanded, setExpanded] = useState(false);
  const isOut = frame.direction === "out";
  const time = new Date(frame.timestamp * 1000).toLocaleTimeString(undefined, {
    hour12: false,
  });
  const millis = String(Math.floor((frame.timestamp % 1) * 1000)).padStart(3, "0");

  return (
    <div className="border-b border-border/50 last:border-b-0">
      <button
        className="w-full flex items-center gap-2 px-2 py-1.5 text-left hover:bg-muted/50 text-xs"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
        )}
        {isOut ? (
          <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-info" />
        ) : (
          <ArrowDownLeft className="h-3.5 w-3.5 shrink-0 text-success" />
        )}
        <span className="font-mono text-muted-foreground shrink-0">
          {time}.{millis}
        </span>
        <span className={cn("font-mono truncate", isOut ? "text-info" : "")}>
          {frameLabel(frame)}
        </span>
        {"error" in frame.message && (
          <Badge variant="destructive" className="ml-auto shrink-0">
            error
          </Badge>
        )}
      </button>
      {expanded && (
        <pre className="mx-2 mb-2 p-2 rounded bg-muted/60 text-[11px] leading-snug overflow-x-auto">
          {JSON.stringify(frame.message, null, 2)}
        </pre>
      )}
    </div>
  );
}

export function WireLog({ frames }: { frames: McpWireFrame[] }) {
  if (frames.length === 0) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        No frames recorded yet. Connect and invoke a tool to see the raw
        JSON-RPC traffic.
      </div>
    );
  }
  return (
    <div className="border border-border rounded-md overflow-hidden">
      <div className="flex items-center gap-3 px-2 py-1.5 bg-muted/40 border-b border-border text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1">
          <ArrowUpRight className="h-3 w-3 text-info" /> client → server
        </span>
        <span className="flex items-center gap-1">
          <ArrowDownLeft className="h-3 w-3 text-success" /> server → client
        </span>
        <span className="ml-auto">{frames.length} frames</span>
      </div>
      <div className="max-h-[60vh] overflow-y-auto">
        {frames.map((frame, index) => (
          <FrameRow key={index} frame={frame} />
        ))}
      </div>
    </div>
  );
}
