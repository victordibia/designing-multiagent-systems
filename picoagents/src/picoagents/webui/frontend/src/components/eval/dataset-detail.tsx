/**
 * DatasetDetail — view/edit tasks within a dataset.
 */

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { evalApiClient } from "@/services/eval-api";
import { Plus, Trash2, Edit2, Check, X } from "lucide-react";
import type { Dataset, EvalTask } from "@/types/eval";

interface DatasetDetailProps {
  datasetId: string;
  onUpdate?: () => void;
}

export function DatasetDetail({ datasetId, onUpdate }: DatasetDetailProps) {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAddTask, setShowAddTask] = useState(false);
  const [editingTask, setEditingTask] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const ds = await evalApiClient.getDataset(datasetId);
      setDataset(ds);
    } catch (e) {
      console.error("Failed to load dataset:", e);
    } finally {
      setLoading(false);
    }
  }, [datasetId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleDeleteTask = async (taskId: string) => {
    try {
      await evalApiClient.deleteTask(datasetId, taskId);
      load();
      onUpdate?.();
    } catch (e) {
      console.error("Delete task failed:", e);
    }
  };

  if (loading) {
    return (
      <div className="p-4 text-sm text-muted-foreground text-center">
        Loading dataset...
      </div>
    );
  }

  if (!dataset) {
    return (
      <div className="p-4 text-sm text-destructive text-center">
        Dataset not found.
      </div>
    );
  }

  const tasks = dataset.tasks || [];

  return (
    <div className="p-4 space-y-4">
      {/* Dataset info */}
      <div className="space-y-1">
        <h3 className="text-base font-semibold">{dataset.name}</h3>
        {dataset.description && (
          <p className="text-sm text-muted-foreground">
            {dataset.description}
          </p>
        )}
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>v{dataset.version}</span>
          <span>Source: {dataset.source}</span>
          <span>{dataset.task_count} tasks</span>
        </div>
      </div>

      {/* Tasks */}
      <div className="border rounded-lg">
        <div className="flex items-center px-3 py-2 border-b bg-muted/30">
          <h4 className="text-xs font-medium text-muted-foreground flex-1">
            Tasks ({tasks.length})
          </h4>
          <Button
            variant="outline"
            size="sm"
            className="h-6 text-xs"
            onClick={() => setShowAddTask(!showAddTask)}
          >
            <Plus className="h-3 w-3 mr-1" />
            Add Task
          </Button>
        </div>

        {showAddTask && (
          <AddTaskForm
            datasetId={datasetId}
            onAdded={() => {
              setShowAddTask(false);
              load();
              onUpdate?.();
            }}
            onCancel={() => setShowAddTask(false)}
          />
        )}

        {tasks.length === 0 ? (
          <div className="p-4 text-sm text-muted-foreground text-center">
            No tasks. Add tasks above.
          </div>
        ) : (
          <div className="divide-y">
            {tasks.map((task) => (
              <TaskRow
                key={task.id}
                task={task}
                datasetId={datasetId}
                isEditing={editingTask === task.id}
                onEdit={() => setEditingTask(task.id)}
                onCancelEdit={() => setEditingTask(null)}
                onSaved={() => {
                  setEditingTask(null);
                  load();
                }}
                onDelete={() => handleDeleteTask(task.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TaskRow({
  task,
  datasetId,
  isEditing,
  onEdit,
  onCancelEdit,
  onSaved,
  onDelete,
}: {
  task: EvalTask;
  datasetId: string;
  isEditing: boolean;
  onEdit: () => void;
  onCancelEdit: () => void;
  onSaved: () => void;
  onDelete: () => void;
}) {
  const [name, setName] = useState(task.name);
  const [input, setInput] = useState(task.input);
  const [expectedOutput, setExpectedOutput] = useState(
    task.expected_output || ""
  );
  const [category, setCategory] = useState(task.category);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await evalApiClient.updateTask(datasetId, task.id, {
        name,
        input,
        expected_output: expectedOutput || undefined,
        category,
      });
      onSaved();
    } catch (e) {
      console.error("Update task failed:", e);
    } finally {
      setSaving(false);
    }
  };

  if (isEditing) {
    return (
      <div className="space-y-2 bg-muted/20 px-4 py-3">
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label className="text-xs">Name</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-7 text-xs"
            />
          </div>
          <div>
            <Label className="text-xs">Category</Label>
            <Input
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="h-7 text-xs"
            />
          </div>
        </div>
        <div>
          <Label className="text-xs">Input</Label>
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            rows={2}
            className="text-xs"
          />
        </div>
        <div>
          <Label className="text-xs">Expected Output</Label>
          <Textarea
            value={expectedOutput}
            onChange={(e) => setExpectedOutput(e.target.value)}
            rows={2}
            className="text-xs"
          />
        </div>
        <div className="flex gap-1">
          <Button
            size="sm"
            className="h-6 text-xs"
            onClick={handleSave}
            disabled={saving}
          >
            <Check className="h-3 w-3 mr-1" />
            {saving ? "Saving..." : "Save"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-xs"
            onClick={onCancelEdit}
          >
            <X className="h-3 w-3 mr-1" />
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3 px-3 py-2 hover:bg-muted/30 group">
      <div className="flex-1 min-w-0 space-y-0.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{task.name || "Untitled"}</span>
          <Badge variant="outline" className="text-[10px] px-1.5 py-0">
            {task.category}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground line-clamp-2">
          {task.input}
        </p>
        {task.expected_output && (
          <p className="text-xs text-green-600 dark:text-green-400 line-clamp-1">
            Expected: {task.expected_output}
          </p>
        )}
      </div>
      <div className="flex gap-1 opacity-0 group-hover:opacity-100 shrink-0">
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          onClick={onEdit}
        >
          <Edit2 className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          onClick={onDelete}
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}

function AddTaskForm({
  datasetId,
  onAdded,
  onCancel,
}: {
  datasetId: string;
  onAdded: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [input, setInput] = useState("");
  const [expectedOutput, setExpectedOutput] = useState("");
  const [category, setCategory] = useState("general");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!input.trim()) return;
    setSubmitting(true);
    try {
      await evalApiClient.addTask(datasetId, {
        name: name || "Untitled",
        input,
        expected_output: expectedOutput || undefined,
        category,
      });
      onAdded();
    } catch (e) {
      console.error("Add task failed:", e);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="border-b bg-muted/20 px-4 py-3 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label className="text-xs">Name</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Task name"
            className="h-7 text-xs"
          />
        </div>
        <div>
          <Label className="text-xs">Category</Label>
          <Input
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="h-7 text-xs"
          />
        </div>
      </div>
      <div>
        <Label className="text-xs">Input (prompt)</Label>
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={2}
          className="text-xs"
          placeholder="What should the agent do?"
        />
      </div>
      <div>
        <Label className="text-xs">Expected Output (optional)</Label>
        <Textarea
          value={expectedOutput}
          onChange={(e) => setExpectedOutput(e.target.value)}
          rows={2}
          className="text-xs"
          placeholder="Expected response or output"
        />
      </div>
      <div className="flex gap-1">
        <Button
          size="sm"
          className="h-7 text-xs"
          onClick={handleSubmit}
          disabled={submitting || !input.trim()}
        >
          {submitting ? "Adding..." : "Add Task"}
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
