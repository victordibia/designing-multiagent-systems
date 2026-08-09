/**
 * EvalRunsPanel — list eval runs, launch new ones, view progress.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/status-badge";
import { EvalRunDetail } from "@/components/eval/eval-run-detail";
import { navigate } from "@/lib/router";
import { evalApiClient } from "@/services/eval-api";
import {
  Play,
  ArrowLeft,
  RefreshCw,
  XCircle,
  Download,
  Activity,
} from "lucide-react";
import type { EvalRun, Dataset, TargetConfig } from "@/types/eval";

export function EvalRunsPanel() {
  const [evalRuns, setEvalRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRun, setSelectedRun] = useState<EvalRun | null>(null);
  const [showLaunch, setShowLaunch] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await evalApiClient.listEvalRuns();
      setEvalRuns(data);
    } catch (e) {
      console.error("Failed to load eval runs:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Poll running eval runs
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  useEffect(() => {
    const hasRunning = evalRuns.some(
      (r) => r.status === "running" || r.status === "pending"
    );
    if (hasRunning) {
      pollRef.current = setInterval(async () => {
        try {
          const data = await evalApiClient.listEvalRuns();
          setEvalRuns(data);
          // Also refresh selected run if it's running
          if (
            selectedRun &&
            (selectedRun.status === "running" || selectedRun.status === "pending")
          ) {
            const updated = data.find((r) => r.id === selectedRun.id);
            if (updated) setSelectedRun(updated);
          }
        } catch {
          // ignore polling errors
        }
      }, 2000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [evalRuns, selectedRun]);

  const handleCancel = async (runId: string) => {
    try {
      await evalApiClient.cancelEvalRun(runId);
      load();
    } catch (e) {
      console.error("Cancel failed:", e);
    }
  };

  const handleExport = async (runId: string) => {
    try {
      const blob = await evalApiClient.exportEvalRun(runId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `eval_${runId}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("Export failed:", e);
    }
  };

  // Detail view
  if (selectedRun) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-2 p-3 border-b">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setSelectedRun(null);
              load();
            }}
          >
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back
          </Button>
          <span className="text-sm font-medium">
            {selectedRun.dataset_name}
          </span>
          <StatusBadge status={selectedRun.status} />
          {selectedRun.status === "running" && (
            <span className="text-xs text-muted-foreground">
              {selectedRun.completed_tasks}/{selectedRun.total_tasks}
            </span>
          )}
        </div>
        <div className="flex-1 overflow-auto">
          <EvalRunDetail evalRun={selectedRun} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 p-3 border-b">
        <h3 className="text-sm font-semibold">Eval Runs</h3>
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={() => setShowLaunch(!showLaunch)}
          >
            <Play className="h-3 w-3 mr-1" />
            Launch
          </Button>
          <Button variant="ghost" size="sm" className="h-7" onClick={load}>
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {/* Launch form */}
        {showLaunch && (
          <LaunchEvalForm
            onLaunched={(run) => {
              setEvalRuns((prev) => [run, ...prev]);
              setShowLaunch(false);
            }}
            onCancel={() => setShowLaunch(false)}
          />
        )}

        {/* Eval runs list */}
        {loading ? (
          <div className="p-4 text-sm text-muted-foreground text-center">
            Loading eval runs...
          </div>
        ) : evalRuns.length === 0 ? (
          <EmptyState
            icon={Activity}
            title="No evaluation runs yet"
            description="An evaluation scores one or more targets against a dataset of tasks. You need a dataset and at least one target first."
            action={
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => navigate("/evaluation/datasets")}>
                  Go to Datasets
                </Button>
                <Button size="sm" variant="outline" onClick={() => navigate("/evaluation/targets")}>
                  Go to Targets
                </Button>
              </div>
            }
          />
        ) : (
          <div className="divide-y">
            {evalRuns.map((run) => (
              <div
                key={run.id}
                className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/50 cursor-pointer group"
                onClick={() => setSelectedRun(run)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">
                      {run.dataset_name}
                    </span>
                    <StatusBadge status={run.status} />
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                    <span>
                      {run.target_names?.join(", ") || "No targets"}
                    </span>
                    {run.status === "running" && (
                      <>
                        <span>|</span>
                        <span>
                          {run.completed_tasks}/{run.total_tasks} tasks
                        </span>
                        {run.current_target && (
                          <span>| Target: {run.current_target}</span>
                        )}
                      </>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  {run.status === "running" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCancel(run.id);
                      }}
                    >
                      <XCircle className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  {run.status === "completed" && run.file_path && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleExport(run.id);
                      }}
                    >
                      <Download className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  <span className="text-xs text-muted-foreground/60">
                    {new Date(run.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function LaunchEvalForm({
  onLaunched,
  onCancel,
}: {
  onLaunched: (run: EvalRun) => void;
  onCancel: () => void;
}) {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [targets, setTargets] = useState<TargetConfig[]>([]);
  const [selectedDataset, setSelectedDataset] = useState("");
  const [selectedTargets, setSelectedTargets] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      evalApiClient.listDatasets(),
      evalApiClient.listTargets(),
    ])
      .then(([ds, ts]) => {
        setDatasets(ds);
        setTargets(ts);
        if (ds.length > 0) setSelectedDataset(ds[0].id);
        if (ts.length > 0) setSelectedTargets([ts[0].id]);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const toggleTarget = (id: string) => {
    setSelectedTargets((prev) =>
      prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]
    );
  };

  const handleLaunch = async () => {
    if (!selectedDataset || selectedTargets.length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const run = await evalApiClient.startEvalRun({
        dataset_id: selectedDataset,
        target_ids: selectedTargets,
      });
      onLaunched(run);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Launch failed");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="p-3 border-b bg-muted/30 text-xs text-muted-foreground">
        Loading datasets and targets...
      </div>
    );
  }

  return (
    <div className="p-3 border-b bg-muted/30 space-y-2">
      <p className="text-xs font-medium">Launch Evaluation</p>

      {/* Dataset selector */}
      <div>
        <Label className="text-xs">Dataset</Label>
        {datasets.length === 0 ? (
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={() => navigate("/evaluation/datasets")}
          >
            No datasets yet - create one
          </Button>
        ) : (
          <select
            value={selectedDataset}
            onChange={(e) => setSelectedDataset(e.target.value)}
            className="w-full h-7 text-xs border rounded-md px-2 bg-background"
          >
            {datasets.map((ds) => (
              <option key={ds.id} value={ds.id}>
                {ds.name} ({ds.task_count} tasks)
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Target selector */}
      <div>
        <Label className="text-xs">Targets (select one or more)</Label>
        {targets.length === 0 ? (
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={() => navigate("/evaluation/targets")}
          >
            No targets yet - create one
          </Button>
        ) : (
          <div className="space-y-1 mt-1">
            {targets.map((t) => (
              <label
                key={t.id}
                className="flex items-center gap-2 text-xs cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selectedTargets.includes(t.id)}
                  onChange={() => toggleTarget(t.id)}
                  className="rounded"
                />
                <span>{t.name}</span>
                <Badge
                  variant="outline"
                  className="text-[10px] px-1 py-0"
                >
                  {t.target_type}
                </Badge>
              </label>
            ))}
          </div>
        )}
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      <div className="flex gap-1">
        <Button
          size="sm"
          className="h-7 text-xs"
          onClick={handleLaunch}
          disabled={
            submitting ||
            !selectedDataset ||
            selectedTargets.length === 0
          }
        >
          <Play className="h-3 w-3 mr-1" />
          {submitting ? "Launching..." : "Launch Eval"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          onClick={onCancel}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}
