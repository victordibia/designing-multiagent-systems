/**
 * WorkflowView - Workflow execution interface for PicoAgents
 * Features: Workflow step visualization, input forms, execution monitoring
 */

import { useState, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Workflow,
  Play,
  CheckCircle,
  Clock,
  AlertCircle,
  ArrowRight,
  FileCode,
  StopCircle
} from "lucide-react";
import { apiClient } from "@/services/api";
import type {
  WorkflowInfo,
  StreamEvent,
  RunEntityRequest,
  WorkflowExecutionState
} from "@/types";

interface WorkflowViewProps {
  selectedWorkflow: WorkflowInfo;
  onDebugEvent: (event: StreamEvent) => void;
}

export function WorkflowView({
  selectedWorkflow,
  onDebugEvent,
}: WorkflowViewProps) {
  const [inputData, setInputData] = useState<Record<string, any>>({});
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionState, setExecutionState] = useState<WorkflowExecutionState>({
    status: "pending",
    steps_completed: [],
  });
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const handleInputChange = (key: string, value: any) => {
    setInputData(prev => ({
      ...prev,
      [key]: value
    }));
  };

  const handleExecute = useCallback(async () => {
    setIsExecuting(true);
    setError(null);
    setResult(null);
    setExecutionState({
      status: "running",
      steps_completed: [],
    });

    // Create new AbortController for this request
    abortControllerRef.current = new AbortController();

    try {
      const request: RunEntityRequest = {
        input_data: inputData,
      };

      for await (const event of apiClient.streamEntityExecution(
        selectedWorkflow.id,
        request,
        abortControllerRef.current.signal
      )) {
        onDebugEvent(event);

        // Handle workflow events - using actual WorkflowRunner event types
        // The API client normalizes events: type = event_type, data = full WorkflowEvent
        const workflowEvent = event.data;
        const eventType = event.type; // API client already extracts event_type to type

        if (eventType === "workflow_started") {
          setExecutionState(prev => ({
            ...prev,
            status: "running",
          }));
        } else if (eventType === "step_started") {
          setExecutionState(prev => ({
            ...prev,
            current_step: workflowEvent?.step_id || "unknown",
          }));
        } else if (eventType === "step_completed") {
          setExecutionState(prev => ({
            ...prev,
            steps_completed: [...prev.steps_completed, workflowEvent?.step_id || "unknown"],
            current_step: undefined, // Clear current step when completed
          }));
        } else if (eventType === "step_failed") {
          setExecutionState(prev => ({
            ...prev,
            status: "failed",
            error: workflowEvent?.error || "Step execution failed",
          }));
          setError(workflowEvent?.error || "Step execution failed");
        } else if (eventType === "workflow_completed") {
          setExecutionState(prev => ({
            ...prev,
            status: "completed",
            current_step: undefined,
          }));
          // Extract the final output from the execution
          const execution = workflowEvent?.execution;
          const finalOutput = execution?.step_executions?.[execution?.step_executions?.length - 1]?.output;
          setResult(finalOutput || workflowEvent);
        } else if (eventType === "workflow_failed") {
          setExecutionState(prev => ({
            ...prev,
            status: "failed",
            error: workflowEvent?.error || "Workflow execution failed",
          }));
          setError(workflowEvent?.error || "Workflow execution failed");
        } else if (eventType === "workflow_cancelled") {
          setExecutionState(prev => ({
            ...prev,
            status: "failed",
            error: workflowEvent?.reason || "Workflow was cancelled",
          }));
          setError(workflowEvent?.reason || "Workflow was cancelled");
        }
      }
    } catch (err) {
      console.error("Workflow execution error:", err);

      // Check if this was an abort (user clicked stop)
      if (err instanceof Error && err.name === "AbortError") {
        setError("Cancelled by user");
        setExecutionState(prev => ({
          ...prev,
          status: "failed",
          error: "Cancelled by user",
        }));
      } else {
        setError(err instanceof Error ? err.message : "Execution failed");
        setExecutionState(prev => ({
          ...prev,
          status: "failed",
          error: err instanceof Error ? err.message : "Unknown error",
        }));
      }
    } finally {
      setIsExecuting(false);
      abortControllerRef.current = null;
    }
  }, [selectedWorkflow.id, inputData, onDebugEvent]);

  const handleStop = useCallback(() => {
    if (abortControllerRef.current) {
      console.log("🛑 Stopping workflow execution");
      abortControllerRef.current.abort();
    }
  }, []);

  const getStepStatus = (stepId: string) => {
    if (executionState.steps_completed.includes(stepId)) {
      return "completed";
    } else if (executionState.current_step === stepId) {
      return "running";
    } else {
      return "pending";
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <CheckCircle className="h-4 w-4 text-success" />;
      case "running":
        return <Clock className="h-4 w-4 text-info animate-spin" />;
      case "failed":
        return <AlertCircle className="h-4 w-4 text-destructive" />;
      default:
        return <div className="h-4 w-4 rounded-full border-2 border-border" />;
    }
  };

  const renderInputForm = () => {
    if (!selectedWorkflow.input_schema) {
      return (
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">
              No input schema defined for this workflow.
            </p>
          </CardContent>
        </Card>
      );
    }

    const schema = selectedWorkflow.input_schema;
    const properties = schema.properties || {};

    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Workflow Input</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {Object.entries(properties).map(([key, prop]) => {
            const property = prop as any;
            return (
              <div key={key} className="space-y-2">
                <Label htmlFor={key} className="text-sm font-medium">
                  {key}
                  {schema.required?.includes(key) && (
                    <span className="text-destructive ml-1">*</span>
                  )}
                </Label>
                <Input
                  id={key}
                  type={property.type === "number" ? "number" : "text"}
                  placeholder={property.description || `Enter ${key}`}
                  value={inputData[key] || ""}
                  onChange={(e) => handleInputChange(key, e.target.value)}
                  disabled={isExecuting}
                />
                {property.description && (
                  <p className="text-xs text-muted-foreground">
                    {property.description}
                  </p>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="flex flex-col h-full">
      {/* Workflow Info Header */}
      <div className="border-b p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Workflow className="h-6 w-6 text-success" />
            <div>
              <h2 className="text-lg font-semibold">
                {selectedWorkflow.name || selectedWorkflow.id}
              </h2>
              {selectedWorkflow.description && (
                <p className="text-sm text-muted-foreground">
                  {selectedWorkflow.description}
                </p>
              )}
            </div>
          </div>
          <Badge variant="outline" className="gap-1">
            <FileCode className="h-3 w-3" />
            {selectedWorkflow.steps.length} steps
          </Badge>
        </div>

        {/* Workflow Steps */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Workflow className="h-4 w-4" />
            <span>Workflow Steps</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {selectedWorkflow.steps.map((stepId, index) => (
              <div key={stepId} className="flex items-center gap-2">
                <Badge
                  variant={
                    getStepStatus(stepId) === "completed"
                      ? "default"
                      : getStepStatus(stepId) === "running"
                      ? "secondary"
                      : "outline"
                  }
                  className="gap-1"
                >
                  {getStatusIcon(getStepStatus(stepId))}
                  {stepId}
                </Badge>
                {index < selectedWorkflow.steps.length - 1 && (
                  <ArrowRight className="h-3 w-3 text-muted-foreground" />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Start Step */}
        {selectedWorkflow.start_step && (
          <div className="text-sm">
            <span className="text-muted-foreground">Entry point: </span>
            <Badge variant="outline">{selectedWorkflow.start_step}</Badge>
          </div>
        )}
      </div>

      <div className="flex-1 p-4 space-y-4 overflow-auto">
        {/* Input Form */}
        {renderInputForm()}

        {/* Execution Controls */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-medium">Execute Workflow</h3>
                <p className="text-sm text-muted-foreground">
                  Run the workflow with the provided input
                </p>
              </div>
              <div className="flex gap-2">
                {isExecuting && (
                  <Button
                    variant="destructive"
                    onClick={handleStop}
                    className="gap-2"
                  >
                    <StopCircle className="h-4 w-4" />
                    Stop
                  </Button>
                )}
                <Button
                  onClick={handleExecute}
                  disabled={isExecuting}
                  className="gap-2"
                >
                  {isExecuting ? (
                    <Clock className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                  {isExecuting ? "Executing..." : "Execute"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Execution Status */}
        {executionState.status !== "pending" && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                {getStatusIcon(executionState.status)}
                Execution Status
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">Status:</span>
                <Badge
                  variant={
                    executionState.status === "completed"
                      ? "default"
                      : executionState.status === "running"
                      ? "secondary"
                      : "destructive"
                  }
                >
                  {executionState.status}
                </Badge>
              </div>
              <div className="text-sm">
                <span className="font-medium">Steps completed:</span>{" "}
                {executionState.steps_completed.length} of {selectedWorkflow.steps.length}
              </div>
              {executionState.current_step && (
                <div className="text-sm">
                  <span className="font-medium">Current step:</span>{" "}
                  <Badge variant="outline">{executionState.current_step}</Badge>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Results */}
        {result && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-success" />
                Execution Result
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-32">
                <pre className="text-xs bg-muted p-2 rounded overflow-auto">
                  {JSON.stringify(result, null, 2)}
                </pre>
              </ScrollArea>
            </CardContent>
          </Card>
        )}

        {/* Error */}
        {error && (
          <Card className="border-destructive">
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2 text-destructive">
                <AlertCircle className="h-4 w-4" />
                Execution Error
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-destructive">{error}</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}