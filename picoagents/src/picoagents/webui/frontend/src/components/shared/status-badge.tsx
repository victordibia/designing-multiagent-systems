/**
 * StatusBadge / ScoreBadge - the single status color system.
 * Built on the Badge primitive + semantic tokens (success/warning/info).
 * Replaces eval/score-badge.tsx and per-view color maps.
 */

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type StatusKind = "success" | "warning" | "error" | "info" | "neutral";

const statusClass: Record<StatusKind, string> = {
  success: "border-success/40 bg-success/10 text-success",
  warning: "border-warning/40 bg-warning/10 text-warning",
  error: "border-destructive/40 bg-destructive/10 text-destructive",
  info: "border-info/40 bg-info/10 text-info",
  neutral: "border-border bg-muted text-muted-foreground",
};

const STATUS_MAP: Record<string, StatusKind> = {
  completed: "success",
  success: "success",
  connected: "success",
  passed: "success",
  running: "info",
  in_progress: "info",
  pending: "neutral",
  disconnected: "neutral",
  cancelled: "warning",
  partial: "warning",
  failed: "error",
  error: "error",
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const kind = STATUS_MAP[status.toLowerCase()] ?? "neutral";
  return (
    <Badge variant="outline" className={cn("text-xs font-medium", statusClass[kind], className)}>
      {status}
    </Badge>
  );
}

export function ScoreBadge({ score, max = 10, className }: { score: number; max?: number; className?: string }) {
  const ratio = max > 0 ? score / max : 0;
  const kind: StatusKind = ratio >= 0.7 ? "success" : ratio >= 0.4 ? "warning" : "error";
  return (
    <Badge variant="outline" className={cn("font-mono text-xs", statusClass[kind], className)}>
      {Number.isInteger(score) ? score : score.toFixed(1)}/{max}
    </Badge>
  );
}
