/**
 * McpView - the MCP playground.
 *
 * Server selection lives in the app sidebar (routed /mcp/:serverId); this
 * view renders the selected server's tabs (Overview, Tools, Wire, Tasks,
 * SDK Matrix) and live MRTR input prompts fed by the playground SSE stream.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Cable, CircleSlash, Loader2, Plus, PlugZap, Trash2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { EmptyState } from "@/components/shared/empty-state";
import { JsonBlock } from "@/components/shared/json-block";
import { PageHeader } from "@/components/shared/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { navigate } from "@/lib/router";
import { mcpApiClient } from "@/services/mcp-api";
import { AddServerDialog } from "./add-server-dialog";
import { InputBanner } from "./input-banner";
import { SupportMatrixView } from "./support-matrix";
import { ToolTester } from "./tool-tester";
import { WireLog } from "./wire-log";
import type {
  McpPendingInput,
  McpServerInfo,
  McpServerSummary,
  McpToolInfo,
  McpWireFrame,
} from "@/types/mcp";

type McpTab = "overview" | "tools" | "wire" | "tasks" | "matrix";

/** The picoagents code that attaches this exact server to an agent. */
function agentSnippet(server: McpServerSummary): string {
  const config =
    server.transport === "stdio"
      ? `StdioServerConfig(\n    server_id="${server.server_id}",\n    command="${server.command ?? ""}",\n    args=${JSON.stringify(server.args ?? [])},\n)`
      : `HTTPServerConfig(\n    server_id="${server.server_id}",\n    url="${server.url ?? ""}",\n)`;
  return `from picoagents.tools import create_mcp_tools, ${
    server.transport === "stdio" ? "StdioServerConfig" : "HTTPServerConfig"
  }

manager, tools = await create_mcp_tools([
  ${config}
])
agent = Agent(name="my_agent", tools=tools, model_client=client)`;
}

interface McpViewProps {
  servers: McpServerSummary[];
  selectedServerId?: string;
  onServersChanged: () => void;
}

export function McpView({ servers, selectedServerId, onServersChanged }: McpViewProps) {
  const [tab, setTab] = useState<McpTab>("overview");
  const [serverInfo, setServerInfo] = useState<McpServerInfo | null>(null);
  const [tools, setTools] = useState<McpToolInfo[]>([]);
  const [selectedTool, setSelectedTool] = useState<McpToolInfo | null>(null);
  const [wireFrames, setWireFrames] = useState<McpWireFrame[]>([]);
  const [pendingInputs, setPendingInputs] = useState<McpPendingInput[]>([]);
  const [busy, setBusy] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedIdRef = useRef<string | undefined>(selectedServerId);
  selectedIdRef.current = selectedServerId;

  const selected = servers.find((s) => s.server_id === selectedServerId);
  const isConnected = selected?.status === "connected";

  // Recover inputs parked before this page loaded (e.g. after a refresh)
  useEffect(() => {
    mcpApiClient.getPendingInputs().then(setPendingInputs).catch(() => {});
  }, []);

  // SSE: live wire frames + MRTR prompts
  useEffect(() => {
    const unsubscribe = mcpApiClient.subscribeEvents((event) => {
      if (event.type === "wire_frame") {
        if (event.server_id === selectedIdRef.current) {
          setWireFrames((prev) => [...prev.slice(-999), event.frame]);
        }
      } else if (event.type === "input_required") {
        setPendingInputs((prev) => [...prev, event]);
      } else if (event.type === "input_resolved") {
        setPendingInputs((prev) => prev.filter((p) => p.input_id !== event.input_id));
      }
    });
    return unsubscribe;
  }, []);

  // Load details when selection/connection changes
  useEffect(() => {
    setServerInfo(null);
    setTools([]);
    setSelectedTool(null);
    setWireFrames([]);
    setTab("overview");
    setError(null);
    if (!selectedServerId || !isConnected) return;
    mcpApiClient.getCapabilities(selectedServerId).then(setServerInfo).catch(() => {});
    mcpApiClient
      .listTools(selectedServerId)
      .then((list) => {
        setTools(list);
        setSelectedTool(list[0] ?? null);
      })
      .catch(() => {});
    mcpApiClient.getWireFrames(selectedServerId).then(setWireFrames).catch(() => {});
  }, [selectedServerId, isConnected]);

  const toggleConnection = useCallback(async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      if (selected.status === "connected") {
        await mcpApiClient.disconnect(selected.server_id);
      } else {
        await mcpApiClient.connect(selected.server_id);
      }
      onServersChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [selected, onServersChanged]);

  const removeServer = useCallback(async () => {
    if (!selected) return;
    try {
      await mcpApiClient.removeServer(selected.server_id);
      onServersChanged();
      navigate("/mcp");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [selected, onServersChanged]);

  const replyInput = useCallback(
    async (inputId: string, action: string, content: Record<string, any> | null) => {
      try {
        await mcpApiClient.replyInput(inputId, action, content);
      } catch {
        // input may have timed out; the resolved event cleans it up
      }
      setPendingInputs((prev) => prev.filter((p) => p.input_id !== inputId));
    },
    []
  );

  // ---- index page (no server selected) ----
  if (!selected) {
    return (
      <div className="flex h-full flex-col">
        <PageHeader
          title="MCP Playground"
          description="Test MCP servers against the 2026-07-28 spec: stateless discovery, tools, mid-call input (MRTR), and raw wire traffic."
          actions={
            <Button size="sm" className="h-8" onClick={() => setAddOpen(true)}>
              <Plus className="size-3.5" /> Add server
            </Button>
          }
        />
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {servers.length === 0 ? (
            <EmptyState
              icon={Cable}
              title="No servers configured"
              description="Add a server or pick a lab preset, then connect and explore its tools with full wire visibility."
              action={
                <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
                  <Plus className="size-3.5" /> Add server
                </Button>
              }
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              Pick a server from the sidebar to inspect it.
            </p>
          )}
          <div className="mt-6 max-w-4xl">
            <h2 className="mb-2 text-sm font-medium">SDK support matrix</h2>
            <SupportMatrixView />
          </div>
        </div>
        <AddServerDialog
          open={addOpen}
          onOpenChange={setAddOpen}
          onAdded={onServersChanged}
        />
      </div>
    );
  }

  // ---- server page ----
  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title={
          <>
            <span className="font-mono">{selected.server_id}</span>
            <StatusBadge status={selected.status} />
            <Badge variant="outline" className="text-xs">
              {selected.transport}
            </Badge>
          </>
        }
        description={
          serverInfo?.protocol_version
            ? `Protocol ${serverInfo.protocol_version}`
            : undefined
        }
        actions={
          <>
            <Button
              size="sm"
              variant="outline"
              className="h-8"
              disabled={busy}
              onClick={toggleConnection}
            >
              {busy ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : isConnected ? (
                <>
                  <CircleSlash className="size-3.5" /> Disconnect
                </>
              ) : (
                <>
                  <PlugZap className="size-3.5" /> Connect
                </>
              )}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-8"
              onClick={() => setConfirmRemove(true)}
              aria-label="Remove server"
            >
              <Trash2 className="size-3.5" />
            </Button>
          </>
        }
      />

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="space-y-3">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {pendingInputs.map((pending) => (
            <InputBanner key={pending.input_id} pending={pending} onReply={replyInput} />
          ))}

          {!isConnected ? (
            <EmptyState
              icon={PlugZap}
              title="Not connected"
              description="Connect to discover capabilities and tools."
              action={
                <Button size="sm" disabled={busy} onClick={toggleConnection}>
                  <PlugZap className="size-3.5" /> Connect
                </Button>
              }
            />
          ) : (
            <>
              <SegmentedControl
                value={tab}
                onValueChange={setTab}
                options={[
                  { value: "overview", label: "Overview" },
                  { value: "tools", label: `Tools (${tools.length})` },
                  { value: "wire", label: `Wire (${wireFrames.length})` },
                  { value: "tasks", label: "Tasks" },
                  { value: "matrix", label: "SDK Matrix" },
                ]}
              />

              {tab === "overview" && (
                <div className="max-w-4xl space-y-4">
                  {serverInfo ? (
                    <>
                      {serverInfo.instructions && (
                        <p className="text-sm text-muted-foreground">{serverInfo.instructions}</p>
                      )}
                      <div>
                        <div className="mb-1 text-xs font-medium">Connection</div>
                        <div className="rounded-md border p-2 text-xs">
                          <div className="flex gap-2">
                            <span className="w-24 shrink-0 text-muted-foreground">Transport</span>
                            <span className="font-mono">{selected.transport}</span>
                          </div>
                          <div className="mt-1 flex gap-2">
                            <span className="w-24 shrink-0 text-muted-foreground">Target</span>
                            <span className="break-all font-mono">
                              {selected.url ??
                                [selected.command, ...(selected.args ?? [])].join(" ")}
                            </span>
                          </div>
                          {serverInfo.server_info?.name && (
                            <div className="mt-1 flex gap-2">
                              <span className="w-24 shrink-0 text-muted-foreground">Reports as</span>
                              <span className="font-mono">
                                {String(serverInfo.server_info.name)}
                                {serverInfo.server_info.version
                                  ? ` ${serverInfo.server_info.version}`
                                  : ""}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                      <div>
                        <div className="mb-1 text-xs font-medium">Use these tools in an agent</div>
                        <JsonBlock value={agentSnippet(selected)} />
                      </div>
                      <div>
                        <div className="mb-1 text-xs font-medium">Capabilities</div>
                        <JsonBlock value={serverInfo.capabilities} />
                      </div>
                    </>
                  ) : (
                    <Loader2 className="size-4 animate-spin text-muted-foreground" />
                  )}
                </div>
              )}

              {tab === "tools" && tools.length === 0 && (
                <EmptyState
                  icon={Cable}
                  title="This server exposes no tools"
                  description="It connected and negotiated fine, but tools/list came back empty. Check the Wire tab to see the exchange."
                  action={
                    <Button variant="outline" size="sm" onClick={() => setTab("wire")}>
                      Open wire log
                    </Button>
                  }
                />
              )}
              {tab === "tools" && tools.length > 0 && (
                <div className="flex max-w-5xl gap-4">
                  <div className="w-48 shrink-0 space-y-0.5">
                    {tools.map((tool) => (
                      <button
                        key={tool.name}
                        className={
                          selectedTool?.name === tool.name
                            ? "w-full truncate rounded-md bg-muted px-2 py-1.5 text-left font-mono text-xs font-medium"
                            : "w-full truncate rounded-md px-2 py-1.5 text-left font-mono text-xs hover:bg-muted/50"
                        }
                        onClick={() => setSelectedTool(tool)}
                      >
                        {tool.name}
                      </button>
                    ))}
                  </div>
                  <div className="min-w-0 flex-1">
                    {selectedTool && <ToolTester serverId={selected.server_id} tool={selectedTool} />}
                  </div>
                </div>
              )}

              {tab === "wire" && <WireLog frames={wireFrames} />}

              {tab === "tasks" && (
                <Alert variant="warning" className="max-w-4xl">
                  <AlertTitle>Tasks: not supported by the installed Python SDK</AlertTitle>
                  <AlertDescription>
                    The 2026-07-28 spec defines Tasks (durable handles for long-running
                    work: tasks/get polling, tasks/update). The Python SDK ships the wire
                    types (GetTaskRequest, CancelTaskRequest, CreateTaskResult, ...) but
                    the client runtime is still an open upstream PR. This tab activates
                    when it lands - see the SDK Matrix for current status.
                  </AlertDescription>
                </Alert>
              )}

              {tab === "matrix" && (
                <div className="max-w-4xl">
                  <SupportMatrixView />
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <AddServerDialog open={addOpen} onOpenChange={setAddOpen} onAdded={onServersChanged} />
      <ConfirmDialog
        open={confirmRemove}
        onOpenChange={setConfirmRemove}
        title="Remove server?"
        description={`This removes "${selected.server_id}" from the playground configuration.`}
        confirmLabel="Remove"
        onConfirm={removeServer}
      />
    </div>
  );
}
