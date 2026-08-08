/**
 * API client for PicoAgents persistence: runs, datasets, targets, eval runs.
 * Mirrors the REST endpoints in _runs_router.py and _eval_router.py.
 */

import type {
  Run,
  RunData,
  Dataset,
  EvalTask,
  BuiltinDataset,
  TargetConfig,
  EvalRun,
  EvalResult,
} from "@/types/eval";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL !== undefined
    ? import.meta.env.VITE_API_BASE_URL
    : "http://localhost:8080";

class EvalApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      throw new Error(
        `API ${response.status}: ${detail || response.statusText}`
      );
    }

    return response.json();
  }

  // -----------------------------------------------------------------------
  // Runs
  // -----------------------------------------------------------------------

  async listRuns(params?: {
    run_type?: string;
    agent_name?: string;
    limit?: number;
    offset?: number;
  }): Promise<Run[]> {
    const qs = new URLSearchParams();
    if (params?.run_type) qs.set("run_type", params.run_type);
    if (params?.agent_name) qs.set("agent_name", params.agent_name);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const suffix = qs.toString() ? `?${qs}` : "";
    return this.request<Run[]>(`/api/runs${suffix}`);
  }


  async getRunData(runId: string): Promise<RunData> {
    return this.request<RunData>(`/api/runs/${runId}/data`);
  }

  async getRun(runId: string): Promise<Run> {
    return this.request(`/api/runs/${runId}`);
  }

  async deleteRun(runId: string): Promise<{ status: string }> {
    return this.request(`/api/runs/${runId}`, { method: "DELETE" });
  }

  // -----------------------------------------------------------------------
  // Datasets
  // -----------------------------------------------------------------------

  async listDatasets(): Promise<Dataset[]> {
    return this.request<Dataset[]>("/api/eval/datasets");
  }

  async getDataset(datasetId: string): Promise<Dataset> {
    return this.request<Dataset>(`/api/eval/datasets/${datasetId}`);
  }

  async createDataset(data: {
    name: string;
    tasks: Record<string, any>[];
    version?: string;
    description?: string;
    source?: string;
    categories?: string[];
    default_eval_criteria?: string[];
  }): Promise<Dataset> {
    return this.request<Dataset>("/api/eval/datasets", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async deleteDataset(datasetId: string): Promise<{ status: string }> {
    return this.request(`/api/eval/datasets/${datasetId}`, {
      method: "DELETE",
    });
  }

  async importBuiltinDataset(name: string): Promise<Dataset> {
    return this.request<Dataset>("/api/eval/datasets/import", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  }

  async listBuiltinDatasets(): Promise<BuiltinDataset[]> {
    return this.request<BuiltinDataset[]>("/api/eval/builtin-datasets");
  }

  // --- Tasks within datasets ---

  async addTask(
    datasetId: string,
    task: {
      name: string;
      input: string;
      expected_output?: string;
      category?: string;
      eval_criteria?: string[];
    }
  ): Promise<EvalTask> {
    return this.request<EvalTask>(
      `/api/eval/datasets/${datasetId}/tasks`,
      { method: "POST", body: JSON.stringify(task) }
    );
  }

  async updateTask(
    datasetId: string,
    taskId: string,
    updates: Partial<EvalTask>
  ): Promise<EvalTask> {
    return this.request<EvalTask>(
      `/api/eval/datasets/${datasetId}/tasks/${taskId}`,
      { method: "PUT", body: JSON.stringify(updates) }
    );
  }

  async deleteTask(
    datasetId: string,
    taskId: string
  ): Promise<{ status: string }> {
    return this.request(
      `/api/eval/datasets/${datasetId}/tasks/${taskId}`,
      { method: "DELETE" }
    );
  }

  // -----------------------------------------------------------------------
  // Target Configs
  // -----------------------------------------------------------------------

  async listTargets(): Promise<TargetConfig[]> {
    return this.request<TargetConfig[]>("/api/eval/targets");
  }


  async createTarget(data: {
    name: string;
    target_type?: string;
    config?: Record<string, any>;
    entity_id?: string;
    description?: string;
  }): Promise<TargetConfig> {
    return this.request<TargetConfig>("/api/eval/targets", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async deleteTarget(targetId: string): Promise<{ status: string }> {
    return this.request(`/api/eval/targets/${targetId}`, {
      method: "DELETE",
    });
  }

  // -----------------------------------------------------------------------
  // Eval Runs
  // -----------------------------------------------------------------------

  async listEvalRuns(): Promise<EvalRun[]> {
    return this.request<EvalRun[]>("/api/eval/runs");
  }


  async startEvalRun(data: {
    dataset_id: string;
    target_ids: string[];
    judge_config?: Record<string, any>;
  }): Promise<EvalRun> {
    return this.request<EvalRun>("/api/eval/runs", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async cancelEvalRun(evalRunId: string): Promise<{ status: string }> {
    return this.request(`/api/eval/runs/${evalRunId}/cancel`, {
      method: "POST",
    });
  }

  async getEvalResults(evalRunId: string): Promise<EvalResult[]> {
    return this.request<EvalResult[]>(
      `/api/eval/runs/${evalRunId}/results`
    );
  }


  async exportEvalRun(evalRunId: string): Promise<Blob> {
    const url = `${this.baseUrl}/api/eval/runs/${evalRunId}/export`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Export failed: ${response.status}`);
    return response.blob();
  }
}

export const evalApiClient = new EvalApiClient();
export { EvalApiClient };
