/**
 * RunDetail — full view of a persisted run: metadata + message trajectory.
 */

import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/shared/status-badge";
import { MessageRenderer } from "@/components/message_renderer";
import { evalApiClient } from "@/services/eval-api";
import {
  Clock,
  Cpu,
  Zap,
  Wrench,
  DollarSign,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { navigate } from "@/lib/router";
import type { Entity } from "@/types";
import type { Run, RunData } from "@/types/eval";
import type { Message } from "@/types/picoagents";

interface RunDetailProps {
  run: Run;
  /** Loaded entities, to offer 'open the agent that produced this'. */
  entities?: Entity[];
}

export function RunDetail({ run, entities = [] }: RunDetailProps) {
  const [runData, setRunData] = useState<RunData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    evalApiClient
      .getRunData(run.id)
      .then((data) => {
        if (!cancelled) setRunData(data);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [run.id]);

  const dur =
    run.duration_ms >= 1000
      ? `${(run.duration_ms / 1000).toFixed(1)}s`
      : `${run.duration_ms}ms`;

  const messages: Message[] = runData?.response?.messages ?? [];

  const producer = entities.find(
    (e) => e.name === run.agent_name || e.id === run.agent_name
  );

  return (
    <div className="p-4 space-y-4">
      {/* Metadata header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <h3 className="text-base font-semibold">{run.agent_name}</h3>
          {producer && (
            <Button
              variant="outline"
              size="sm"
              className="h-6 text-xs"
              onClick={() =>
                navigate(`/${producer.type}s/${encodeURIComponent(producer.id)}`)
              }
            >
              Open {producer.type}
            </Button>
          )}
          <Badge variant="outline" className="text-xs">
            {run.run_type}
          </Badge>
          <StatusBadge status={run.status} />
          {run.model && (
            <Badge variant="secondary" className="text-xs">
              {run.model}
            </Badge>
          )}
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-4 text-xs text-muted-foreground flex-wrap">
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {dur}
          </span>
          <span className="flex items-center gap-1">
            <Zap className="h-3 w-3" />
            {run.tokens_input.toLocaleString()} in / {run.tokens_output.toLocaleString()} out
          </span>
          <span className="flex items-center gap-1">
            <Cpu className="h-3 w-3" />
            {run.llm_calls} LLM calls
          </span>
          <span className="flex items-center gap-1">
            <Wrench className="h-3 w-3" />
            {run.tool_calls} tool calls
          </span>
          {run.cost_estimate != null && (
            <span className="flex items-center gap-1">
              <DollarSign className="h-3 w-3" />${run.cost_estimate.toFixed(4)}
            </span>
          )}
          {run.trace_id && (
            <span className="flex items-center gap-1">
              <ExternalLink className="h-3 w-3" />
              Trace: {run.trace_id.slice(0, 8)}...
            </span>
          )}
          <span>{new Date(run.created_at).toLocaleString()}</span>
        </div>

        {run.tags && run.tags.length > 0 && (
          <div className="flex gap-1 flex-wrap">
            {run.tags.map((tag) => (
              <Badge key={tag} variant="outline" className="text-[10px]">
                {tag}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Messages / Trajectory */}
      <div className="border rounded-lg">
        <div className="px-3 py-2 border-b bg-muted/30">
          <h4 className="text-xs font-medium text-muted-foreground">
            Messages ({messages.length})
          </h4>
        </div>
        <div className="divide-y max-h-[600px] overflow-auto">
          {loading ? (
            <div className="p-4 text-sm text-muted-foreground text-center">
              Loading trajectory...
            </div>
          ) : error ? (
            <div className="p-4 text-sm text-destructive text-center">
              {error}
            </div>
          ) : messages.length === 0 ? (
            <div className="p-4 text-sm text-muted-foreground text-center">
              No messages in this run.
            </div>
          ) : (
            messages.map((msg, i) => (
              <div key={i} className="px-3 py-2">
                <div className="flex items-center gap-2 mb-1">
                  <Badge
                    variant={
                      msg.role === "user"
                        ? "default"
                        : msg.role === "assistant"
                          ? "secondary"
                          : "outline"
                    }
                    className="text-[10px] px-1.5"
                  >
                    {msg.source || msg.role}
                  </Badge>
                </div>
                <MessageRenderer message={msg} isStreaming={false} />
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
