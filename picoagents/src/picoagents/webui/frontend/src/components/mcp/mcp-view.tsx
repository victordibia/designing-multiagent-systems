/**
 * McpView - the MCP playground.
 *
 * Server sidebar (add/connect/status), per-server tabs (Overview, Tools,
 * Wire, Tasks), the SDK support matrix, and live MRTR input prompts fed
 * by the playground SSE stream.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Cable,
  CircleSlash,
  Loader2,
  Plug,
  PlugZap,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
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

export function McpView() {
  const [servers, setServers] = useState<McpServerSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [serverInfo, setServerInfo] = useState<McpServerInfo | null>(null);
  const [tools, setTools] = useState<McpToolInfo[]>([]);
  const [selectedTool, setSelectedTool] = useState<McpToolInfo | null>(null);
  const [wireFrames, setWireFrames] = useState<McpWireFrame[]>([]);
  const [pendingInputs, setPendingInputs] = useState<McpPendingInput[]>([]);
  const [busyServer, setBusyServer] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedIdRef = useRef<string | null>(null);
  selectedIdRef.current = selectedId;

  const refreshServers = useCallback(async () => {
    try {
      const list = await mcpApiClient.listServers();
      setServers(list);
      if (!selectedIdRef.current && list.length > 0) {
        setSelectedId(list[0].server_id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    refreshServers();
  }, [refreshServers]);

  // SSE: wire frames stream in live; MRTR prompts appear/disappear
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

  // Load details when selection or connection state changes
  const selected = servers.find((s) => s.server_id === selectedId) ?? null;
  const isConnected = selected?.status === "connected";

  useEffect(() => {
    setServerInfo(null);
    setTools([]);
    setSelectedTool(null);
    setWireFrames([]);
    if (!selectedId || !isConnected) return;
    mcpApiClient.getCapabilities(selectedId).then(setServerInfo).catch(() => {});
    mcpApiClient
      .listTools(selectedId)
      .then((list) => {
        setTools(list);
        setSelectedTool(list[0] ?? null);
      })
      .catch(() => {});
    mcpApiClient.getWireFrames(selectedId).then(setWireFrames).catch(() => {});
  }, [selectedId, isConnected]);

  const toggleConnection = async (server: McpServerSummary) => {
    setBusyServer(server.server_id);
    setError(null);
    try {
      if (server.status === "connected") {
        await mcpApiClient.disconnect(server.server_id);
      } else {
        await mcpApiClient.connect(server.server_id);
      }
      await refreshServers();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyServer(null);
    }
  };

  const removeServer = async (server: McpServerSummary) => {
    try {
      await mcpApiClient.removeServer(server.server_id);
      if (selectedId === server.server_id) setSelectedId(null);
      await refreshServers();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const replyInput = async (
    inputId: string,
    action: string,
    content: Record<string, any> | null
  ) => {
    try {
      await mcpApiClient.replyInput(inputId, action, content);
    } catch {
      // input may have timed out; the resolved event cleans it up
    }
    setPendingInputs((prev) => prev.filter((p) => p.input_id !== inputId));
  };

  return (
    <div className="h-full flex">
      {/* Sidebar */}
      <div className="w-64 shrink-0 border-r border-border flex flex-col">
        <div className="p-3 flex items-center justify-between border-b border-border">
          <span className="text-sm font-medium flex items-center gap-1.5">
            <Cable className="h-4 w-4" /> Servers
          </span>
          <Button size="sm" variant="outline" className="h-7" onClick={() => setAddOpen(true)}>
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {servers.length === 0 && (
            <div className="p-3 text-xs text-muted-foreground">
              No servers yet. Add one, or pick a lab preset.
            </div>
          )}
          {servers.map((server) => (
            <div
              key={server.server_id}
              className={cn(
                "group px-3 py-2 border-b border-border/50 cursor-pointer",
                selectedId === server.server_id ? "bg-muted/60" : "hover:bg-muted/30"
              )}
              onClick={() => setSelectedId(server.server_id)}
            >
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "h-2 w-2 rounded-full shrink-0",
                    server.status === "connected" ? "bg-green-500" : "bg-muted-foreground/40"
                  )}
                />
                <span className="text-xs font-mono font-medium truncate">
                  {server.server_id}
                </span>
                <Badge variant="outline" className="ml-auto text-[10px] px-1">
                  {server.transport}
                </Badge>
              </div>
              <div className="flex items-center gap-1 mt-1.5">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-6 text-[11px] px-2"
                  disabled={busyServer === server.server_id}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleConnection(server);
                  }}
                >
                  {busyServer === server.server_id ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : server.status === "connected" ? (
                    <>
                      <CircleSlash className="h-3 w-3 mr-1" /> Disconnect
                    </>
                  ) : (
                    <>
                      <PlugZap className="h-3 w-3 mr-1" /> Connect
                    </>
                  )}
                </Button>
                {server.status === "connected" && (
                  <span className="text-[10px] text-muted-foreground">
                    {server.tool_count} tools
                  </span>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 px-1.5 ml-auto opacity-0 group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeServer(server);
                  }}
                >
                  <Trash2 className="h-3 w-3 text-muted-foreground" />
                </Button>
              </div>
            </div>
          ))}
        </div>
        <div className="p-2 border-t border-border">
          <Button size="sm" variant="ghost" className="h-7 w-full text-xs" onClick={refreshServers}>
            <RefreshCw className="h-3 w-3 mr-1" /> Refresh
          </Button>
        </div>
      </div>

      {/* Main area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {error && (
          <div className="text-xs text-destructive border border-destructive/40 rounded p-2">
            {error}
          </div>
        )}

        {pendingInputs.map((pending) => (
          <InputBanner key={pending.input_id} pending={pending} onReply={replyInput} />
        ))}

        {!selected ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-md space-y-2">
              <Plug className="h-8 w-8 mx-auto text-muted-foreground/60" />
              <h2 className="text-sm font-medium">MCP Playground</h2>
              <p className="text-xs text-muted-foreground">
                Add a server to test tools, watch raw JSON-RPC traffic, and
                exercise 2026-07-28 spec features (stateless discovery, MRTR
                mid-call input). The SDK matrix below shows what the official
                SDKs support today.
              </p>
              <div className="pt-2 text-left">
                <SupportMatrixView />
              </div>
            </div>
          </div>
        ) : !isConnected ? (
          <div className="text-sm text-muted-foreground">
            <span className="font-mono">{selected.server_id}</span> is not connected.
          </div>
        ) : (
          <Tabs defaultValue="overview">
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="tools">Tools ({tools.length})</TabsTrigger>
              <TabsTrigger value="wire">Wire ({wireFrames.length})</TabsTrigger>
              <TabsTrigger value="tasks">Tasks</TabsTrigger>
              <TabsTrigger value="matrix">SDK Matrix</TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="space-y-3">
              {serverInfo ? (
                <>
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge>{serverInfo.server_info?.name ?? selected.server_id}</Badge>
                    <Badge variant="secondary">
                      protocol {serverInfo.protocol_version ?? "unknown"}
                    </Badge>
                    <Badge variant="outline">{selected.transport}</Badge>
                  </div>
                  {serverInfo.instructions && (
                    <p className="text-xs text-muted-foreground">{serverInfo.instructions}</p>
                  )}
                  <div>
                    <div className="text-xs font-medium mb-1">Capabilities</div>
                    <pre className="p-2 rounded bg-muted/60 text-[11px] overflow-x-auto">
                      {JSON.stringify(serverInfo.capabilities, null, 2)}
                    </pre>
                  </div>
                </>
              ) : (
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              )}
            </TabsContent>

            <TabsContent value="tools">
              <div className="flex gap-4">
                <div className="w-48 shrink-0 space-y-1">
                  {tools.map((tool) => (
                    <button
                      key={tool.name}
                      className={cn(
                        "w-full text-left px-2 py-1.5 rounded text-xs font-mono truncate",
                        selectedTool?.name === tool.name
                          ? "bg-muted font-medium"
                          : "hover:bg-muted/50"
                      )}
                      onClick={() => setSelectedTool(tool)}
                    >
                      {tool.name}
                    </button>
                  ))}
                </div>
                <div className="flex-1 min-w-0">
                  {selectedTool && (
                    <ToolTester serverId={selected.server_id} tool={selectedTool} />
                  )}
                </div>
              </div>
            </TabsContent>

            <TabsContent value="wire">
              <WireLog frames={wireFrames} />
            </TabsContent>

            <TabsContent value="tasks">
              <div className="border border-amber-400/50 bg-amber-50 dark:bg-amber-950/30 rounded-md p-3 text-xs space-y-1">
                <div className="font-medium">
                  Tasks: not supported by the installed Python SDK
                </div>
                <p className="text-muted-foreground">
                  The 2026-07-28 spec defines Tasks (durable handles for
                  long-running work: tasks/get polling, tasks/update). The
                  Python SDK ships the wire types (GetTaskRequest,
                  CancelTaskRequest, CreateTaskResult, ...) but the client
                  runtime is still an open upstream PR. This tab activates
                  when it lands - see the SDK Matrix for current status.
                </p>
              </div>
            </TabsContent>

            <TabsContent value="matrix">
              <SupportMatrixView />
            </TabsContent>
          </Tabs>
        )}
      </div>

      <AddServerDialog open={addOpen} onOpenChange={setAddOpen} onAdded={refreshServers} />
    </div>
  );
}
