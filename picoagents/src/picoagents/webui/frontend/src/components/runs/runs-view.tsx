/**
 * RunsView (History) - persisted execution records with filters.
 * A run is one recorded execution of an agent, orchestrator, or eval task.
 * Detail is routed: /history/:runId.
 */

import { useCallback, useEffect, useState } from "react";
import { Clock, Cpu, History, RefreshCw, Search, Trash2, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { RunDetail } from "@/components/runs/run-detail";
import { navigate } from "@/lib/router";
import { evalApiClient } from "@/services/eval-api";
import type { Run } from "@/types/eval";

type RunTypeFilter = "all" | "agent" | "orchestrator" | "eval_task";

interface RunsViewProps {
  /** Routed run id for the detail page (undefined = list). */
  selectedRunId?: string;
}

export function RunsView({ selectedRunId }: RunsViewProps) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<RunTypeFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [pendingDelete, setPendingDelete] = useState<Run | null>(null);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, any> = { limit: 100 };
      if (filter !== "all") params.run_type = filter;
      setRuns(await evalApiClient.listRuns(params));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load history");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  const handleDelete = async (run: Run) => {
    try {
      await evalApiClient.deleteRun(run.id);
      setRuns((prev) => prev.filter((r) => r.id !== run.id));
      if (selectedRunId === run.id) navigate("/history");
    } catch (e) {
      console.error("Delete failed:", e);
    }
  };

  const filteredRuns = runs.filter((r) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      r.agent_name.toLowerCase().includes(q) ||
      r.task_input?.toLowerCase().includes(q) ||
      r.model?.toLowerCase().includes(q)
    );
  });

  // Detail page (routed). The run may not be in the loaded page (limit 100),
  // or the user deep-linked - fall back to fetching it directly.
  const [fetchedRun, setFetchedRun] = useState<Run | null>(null);
  const listedRun = selectedRunId ? runs.find((r) => r.id === selectedRunId) : undefined;
  useEffect(() => {
    setFetchedRun(null);
    if (selectedRunId && !listedRun) {
      evalApiClient
        .getRun(selectedRunId)
        .then(setFetchedRun)
        .catch(() => setFetchedRun(null));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRunId, listedRun?.id]);
  const selectedRun = listedRun ?? fetchedRun ?? undefined;
  if (selectedRunId) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader
          title={
            selectedRun ? (
              <>
                {selectedRun.agent_name}
                <StatusBadge status={selectedRun.status} />
              </>
            ) : (
              "Run"
            )
          }
          description="One recorded execution."
        />
        <div className="min-h-0 flex-1 overflow-y-auto">
          {selectedRun ? (
            <RunDetail run={selectedRun} />
          ) : loading ? (
            <div className="space-y-3 p-4">
              <Skeleton className="h-6 w-64" />
              <Skeleton className="h-32 w-full max-w-3xl" />
            </div>
          ) : (
            <EmptyState
              icon={History}
              title="Run not found"
              description="It may have been deleted."
              action={
                <Button variant="outline" size="sm" onClick={() => navigate("/history")}>
                  Back to history
                </Button>
              }
            />
          )}
        </div>
      </div>
    );
  }

  // List page
  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="History"
        description="Recorded executions of agents, orchestrators, and evaluation tasks."
        actions={
          <Button variant="ghost" size="sm" className="h-8" onClick={loadRuns} aria-label="Refresh">
            <RefreshCw className="size-3.5" />
          </Button>
        }
      />

      <div className="flex shrink-0 items-center gap-3 border-b px-4 py-2">
        <SegmentedControl
          value={filter}
          onValueChange={setFilter}
          options={[
            { value: "all", label: "All" },
            { value: "agent", label: "Agents" },
            { value: "orchestrator", label: "Orchestrators" },
            { value: "eval_task", label: "Evaluation tasks" },
          ]}
        />
        <div className="relative ml-auto w-64">
          <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search history..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-8 pl-7 text-xs"
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <div className="space-y-2 p-4">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : error ? (
          <EmptyState
            icon={History}
            title="Failed to load history"
            description={error}
            action={
              <Button variant="outline" size="sm" onClick={loadRuns}>
                Retry
              </Button>
            }
          />
        ) : filteredRuns.length === 0 ? (
          <EmptyState
            icon={History}
            title={runs.length === 0 ? "No recorded executions yet" : "No matches"}
            description={
              runs.length === 0
                ? "Runs are recorded when persistence is enabled on agent or orchestrator execution."
                : "No runs match your search."
            }
          />
        ) : (
          <div className="divide-y">
            {filteredRuns.map((run) => (
              <RunRow
                key={run.id}
                run={run}
                onSelect={() => navigate(`/history/${encodeURIComponent(run.id)}`)}
                onDelete={() => setPendingDelete(run)}
              />
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete run?"
        description={`This permanently deletes the recorded execution of "${pendingDelete?.agent_name}".`}
        confirmLabel="Delete"
        onConfirm={() => pendingDelete && handleDelete(pendingDelete)}
      />
    </div>
  );
}

function RunRow({
  run,
  onSelect,
  onDelete,
}: {
  run: Run;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const dur =
    run.duration_ms >= 1000
      ? `${(run.duration_ms / 1000).toFixed(1)}s`
      : `${run.duration_ms}ms`;

  const totalTokens = run.tokens_input + run.tokens_output;
  const timeAgo = formatTimeAgo(run.created_at);

  return (
    <div
      className="group flex cursor-pointer items-center gap-3 px-4 py-2.5 hover:bg-muted/50"
      onClick={onSelect}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="shrink-0 text-xs">
            {run.run_type === "eval_task" ? "evaluation" : run.run_type}
          </Badge>
          <span className="truncate text-sm font-medium">{run.agent_name}</span>
          <StatusBadge status={run.status} />
        </div>
        {run.task_input && (
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{run.task_input}</p>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground">
        {run.model && <span className="hidden max-w-[120px] truncate sm:inline">{run.model}</span>}
        <span className="flex items-center gap-1">
          <Clock className="size-3" />
          {dur}
        </span>
        <span className="flex items-center gap-1">
          <Zap className="size-3" />
          {totalTokens.toLocaleString()}
        </span>
        <span className="flex items-center gap-1">
          <Cpu className="size-3" />
          {run.llm_calls}
        </span>
        <span className="text-muted-foreground/60">{timeAgo}</span>
        <Button
          variant="ghost"
          size="icon"
          className="size-6 opacity-0 group-hover:opacity-100"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          aria-label="Delete run"
        >
          <Trash2 className="size-3" />
        </Button>
      </div>
    </div>
  );
}

function formatTimeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
