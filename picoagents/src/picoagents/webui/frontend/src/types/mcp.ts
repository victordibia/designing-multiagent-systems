/**
 * Types for the MCP playground, mirroring _mcp_router.py responses.
 */

export interface McpServerSummary {
  server_id: string;
  transport: string;
  status: "connected" | "disconnected";
  tool_count: number;
  command?: string;
  args?: string[];
  url?: string;
}

export interface McpServerInfo {
  server_id: string;
  protocol_version: string | null;
  server_info: { name?: string; version?: string; [key: string]: unknown } | null;
  capabilities: Record<string, unknown> | null;
  instructions: string | null;
  tools?: McpToolInfo[];
}

export interface McpToolInfo {
  name: string;
  title: string | null;
  description: string | null;
  input_schema: Record<string, any>;
  output_schema: Record<string, any> | null;
  /** MCP Apps: the ui:// resource this tool renders with, if any. */
  app_resource_uri: string | null;
}

export interface McpCallResult {
  is_error: boolean;
  error?: string;
  content: Array<Record<string, any>>;
  structured_content: Record<string, any> | null;
}

export interface McpWireFrame {
  direction: "in" | "out";
  timestamp: number;
  message: Record<string, any>;
}

export interface McpPendingInput {
  input_id: string;
  server_id: string;
  message: string;
  requested_schema: Record<string, any> | null;
}

export type McpEvent =
  | { type: "wire_frame"; server_id: string; frame: McpWireFrame }
  | ({ type: "input_required" } & McpPendingInput)
  | { type: "input_resolved"; server_id: string; input_id: string };

export interface McpPreset {
  server_id: string;
  description: string;
  transport: "stdio";
  command: string;
  args: string[];
}

export type McpFeatureStatus = "shipped" | "missing";

export interface McpSpecSupport {
  sdk: string;
  version: string;
  protocol_version: string;
  features: Array<{
    key: string;
    label: string;
    description: string;
    status: McpFeatureStatus;
  }>;
}

export interface AddServerPayload {
  server_id: string;
  transport: string;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
}
