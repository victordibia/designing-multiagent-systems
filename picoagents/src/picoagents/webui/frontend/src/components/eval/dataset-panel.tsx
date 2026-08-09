/**
 * DatasetPanel — list, create, and import evaluation datasets.
 */

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { DatasetDetail } from "@/components/eval/dataset-detail";
import { evalApiClient } from "@/services/eval-api";
import {
  Plus,
  Download,
  Trash2,
  ArrowLeft,
  RefreshCw,
  Database,
  FileText,
} from "lucide-react";
import type { Dataset, BuiltinDataset } from "@/types/eval";

export function DatasetPanel() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [builtins, setBuiltins] = useState<BuiltinDataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDataset, setSelectedDataset] = useState<Dataset | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [showImport, setShowImport] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ds, bi] = await Promise.all([
        evalApiClient.listDatasets(),
        evalApiClient.listBuiltinDatasets().catch(() => [] as BuiltinDataset[]),
      ]);
      setDatasets(ds);
      setBuiltins(bi);
    } catch (e) {
      console.error("Failed to load datasets:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleDelete = async (id: string) => {
    try {
      await evalApiClient.deleteDataset(id);
      setDatasets((prev) => prev.filter((d) => d.id !== id));
      if (selectedDataset?.id === id) setSelectedDataset(null);
    } catch (e) {
      console.error("Delete failed:", e);
    }
  };

  const handleImportBuiltin = async (name: string) => {
    try {
      const ds = await evalApiClient.importBuiltinDataset(name);
      setDatasets((prev) => [...prev, ds]);
      setShowImport(false);
    } catch (e) {
      console.error("Import failed:", e);
    }
  };

  // Dataset detail view
  if (selectedDataset) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-2 border-b px-4 py-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setSelectedDataset(null);
              load();
            }}
          >
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back
          </Button>
          <span className="text-sm font-medium">{selectedDataset.name}</span>
          <Badge variant="outline" className="text-xs">
            {selectedDataset.task_count} tasks
          </Badge>
        </div>
        <div className="flex-1 overflow-auto">
          <DatasetDetail
            datasetId={selectedDataset.id}
            onUpdate={() => load()}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <h3 className="text-sm font-semibold">Datasets</h3>
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={() => setShowImport(!showImport)}
          >
            <Download className="h-3 w-3 mr-1" />
            Import
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={() => setShowCreate(!showCreate)}
          >
            <Plus className="h-3 w-3 mr-1" />
            Create
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7"
            onClick={load}
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {/* Import panel */}
        {showImport && (
          <div className="border-b bg-muted/30 px-4 py-3 space-y-2">
            <p className="text-xs font-medium">Import built-in dataset</p>
            {builtins.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No built-in datasets available.
              </p>
            ) : (
              <div className="space-y-1">
                {builtins.map((b) => (
                  <div
                    key={b.name}
                    className="flex items-center gap-2 p-2 rounded border bg-background"
                  >
                    <Database className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium">{b.name}</p>
                      <p className="text-xs text-muted-foreground truncate">
                        {b.description} ({b.task_count} tasks)
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-6 text-xs"
                      onClick={() => handleImportBuiltin(b.name)}
                    >
                      Import
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Create panel */}
        {showCreate && (
          <CreateDatasetForm
            onCreated={(ds) => {
              setDatasets((prev) => [...prev, ds]);
              setShowCreate(false);
            }}
            onCancel={() => setShowCreate(false)}
          />
        )}

        {/* Dataset list */}
        {loading ? (
          <div className="p-4 text-sm text-muted-foreground text-center">
            Loading datasets...
          </div>
        ) : datasets.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            <FileText className="h-8 w-8 mx-auto mb-2 opacity-40" />
            No datasets yet. Create one or import a built-in dataset.
          </div>
        ) : (
          <div className="divide-y">
            {datasets.map((ds) => (
              <div
                key={ds.id}
                className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/50 cursor-pointer group"
                onClick={() => setSelectedDataset(ds)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{ds.name}</span>
                    <Badge
                      variant="outline"
                      className="text-[10px] px-1.5 py-0"
                    >
                      {ds.source}
                    </Badge>
                    <Badge
                      variant="secondary"
                      className="text-[10px] px-1.5 py-0"
                    >
                      {ds.task_count} tasks
                    </Badge>
                  </div>
                  {ds.description && (
                    <p className="text-xs text-muted-foreground truncate mt-0.5">
                      {ds.description}
                    </p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(ds.id);
                  }}
                >
                  <Trash2 className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function CreateDatasetForm({
  onCreated,
  onCancel,
}: {
  onCreated: (ds: Dataset) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tasksJson, setTasksJson] = useState("[]");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      let tasks: Record<string, any>[];
      try {
        tasks = JSON.parse(tasksJson);
      } catch {
        throw new Error("Invalid JSON for tasks");
      }
      const ds = await evalApiClient.createDataset({
        name: name.trim(),
        tasks,
        description,
      });
      onCreated(ds);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="border-b bg-muted/30 px-4 py-3 space-y-2">
      <p className="text-xs font-medium">Create dataset</p>
      <div className="space-y-1.5">
        <div>
          <Label className="text-xs">Name</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my-eval-dataset"
            className="h-7 text-xs"
          />
        </div>
        <div>
          <Label className="text-xs">Description</Label>
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional description"
            className="h-7 text-xs"
          />
        </div>
        <div>
          <Label className="text-xs">
            Tasks (JSON array of {`{name, input, expected_output, category}`})
          </Label>
          <Textarea
            value={tasksJson}
            onChange={(e) => setTasksJson(e.target.value)}
            rows={4}
            className="text-xs font-mono"
            placeholder='[{"name": "test", "input": "What is 2+2?", "expected_output": "4"}]'
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
