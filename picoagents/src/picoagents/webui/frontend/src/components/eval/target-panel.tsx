/**
 * TargetPanel — list and create evaluation target configurations.
 */

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { evalApiClient } from "@/services/eval-api";
import { Plus, Trash2, RefreshCw, Target, Settings } from "lucide-react";
import type { TargetConfig } from "@/types/eval";

export function TargetPanel() {
  const [targets, setTargets] = useState<TargetConfig[]>([]);
  const [pendingDelete, setPendingDelete] = useState<TargetConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await evalApiClient.listTargets();
      setTargets(data);
    } catch (e) {
      console.error("Failed to load targets:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleDelete = async (id: string) => {
    try {
      await evalApiClient.deleteTarget(id);
      setTargets((prev) => prev.filter((t) => t.id !== id));
    } catch (e) {
      console.error("Delete failed:", e);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <h3 className="text-sm font-semibold">Targets</h3>
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={() => setShowCreate(!showCreate)}
          >
            <Plus className="h-3 w-3 mr-1" />
            Create
          </Button>
          <Button variant="ghost" size="sm" className="h-7" onClick={load}>
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {/* Create form */}
        {showCreate && (
          <CreateTargetForm
            onCreated={(t) => {
              setTargets((prev) => [...prev, t]);
              setShowCreate(false);
            }}
            onCancel={() => setShowCreate(false)}
          />
        )}

        {/* Target list */}
        {loading ? (
          <div className="p-4 text-sm text-muted-foreground text-center">
            Loading targets...
          </div>
        ) : targets.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            <Target className="h-8 w-8 mx-auto mb-2 opacity-40" />
            No target configs yet. Create one to define an agent for evaluation.
          </div>
        ) : (
          <div className="divide-y">
            {targets.map((target) => (
              <div
                key={target.id}
                className="flex items-start gap-3 px-4 py-2.5 hover:bg-muted/30 group"
              >
                <Settings className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                <div className="flex-1 min-w-0 space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{target.name}</span>
                    <Badge
                      variant="outline"
                      className="text-[10px] px-1.5 py-0"
                    >
                      {target.target_type}
                    </Badge>
                  </div>
                  {target.description && (
                    <p className="text-xs text-muted-foreground">
                      {target.description}
                    </p>
                  )}
                  {target.config && (
                    <p className="text-xs text-muted-foreground font-mono truncate">
                      {target.config.model || ""}
                      {target.config.tools
                        ? ` + ${(target.config.tools as string[]).length} tools`
                        : ""}
                    </p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100 shrink-0"
                  onClick={() => setPendingDelete(target)}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete target?"
        description={`This removes the evaluation target "${pendingDelete?.name}". Past evaluation runs keep their results.`}
        confirmLabel="Delete"
        onConfirm={() => pendingDelete && handleDelete(pendingDelete.id)}
      />
    </div>
  );
}

function CreateTargetForm({
  onCreated,
  onCancel,
}: {
  onCreated: (t: TargetConfig) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [configJson, setConfigJson] = useState(
    '{\n  "model": "gpt-4.1-mini",\n  "instructions": "You are a helpful assistant."\n}'
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      let config: Record<string, any> | undefined;
      if (configJson.trim()) {
        try {
          config = JSON.parse(configJson);
        } catch {
          throw new Error("Invalid JSON for config");
        }
      }
      const t = await evalApiClient.createTarget({
        name: name.trim(),
        target_type: "picoagent",
        config,
        description,
      });
      onCreated(t);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="border-b bg-muted/30 px-4 py-3 space-y-2">
      <p className="text-xs font-medium">Create target configuration</p>
      <div className="space-y-1.5">
        <div>
          <Label className="text-xs">Name</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="gpt-4o-baseline"
            className="h-7 text-xs"
          />
        </div>
        <div>
          <Label className="text-xs">Description</Label>
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Baseline agent with default settings"
            className="h-7 text-xs"
          />
        </div>
        <div>
          <Label className="text-xs">Agent Config (JSON)</Label>
          <Textarea
            value={configJson}
            onChange={(e) => setConfigJson(e.target.value)}
            rows={5}
            className="text-xs font-mono"
          />
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="flex gap-1">
          <Button
            size="sm"
            className="h-7 text-xs"
            onClick={handleSubmit}
            disabled={submitting || !name.trim()}
          >
            {submitting ? "Creating..." : "Create"}
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
    </div>
  );
}
