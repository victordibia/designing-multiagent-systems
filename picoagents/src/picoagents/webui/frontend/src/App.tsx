/**
 * PicoAgents WebUI - app shell.
 *
 * Hash-routed sections in a collapsible sidebar (Build / Observe / Tools),
 * top bar with breadcrumb + debug-dock + theme controls, and a resizable
 * debug rail on entity pages.
 */

import { useCallback, useEffect, useState } from "react";
import { Bot, GitBranch, SearchX, Users } from "lucide-react";
import { AppSidebar } from "@/components/shell/app-sidebar";
import { TopBar, type Crumb } from "@/components/shell/top-bar";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentView } from "@/components/agent/agent-view";
import { OrchestratorView } from "@/components/orchestrator/orchestrator-view";
import { WorkflowView } from "@/components/workflow/workflow-view";
import { RunsView } from "@/components/runs/runs-view";
import { EvalView } from "@/components/eval/eval-view";
import { McpView } from "@/components/mcp/mcp-view";
import { OverviewView } from "@/components/overview/overview-view";
import { EntityListView } from "@/components/entities/entity-list-view";
import { ExamplesGallery } from "@/components/shared/examples-gallery";
import { DebugPanel } from "@/components/shared/debug-panel";
import { EmptyState } from "@/components/shared/empty-state";
import { RouterProvider, navigate, useSegments } from "@/lib/router";
import { apiClient } from "@/services/api";
import { mcpApiClient } from "@/services/mcp-api";
import type {
  AgentInfo,
  Entity,
  HealthResponse,
  OrchestratorInfo,
  SessionInfo,
  StreamEvent,
  WorkflowInfo,
} from "@/types";
import type { McpServerSummary } from "@/types/mcp";

const SECTION_TYPE: Record<string, Entity["type"]> = {
  agents: "agent",
  orchestrators: "orchestrator",
  workflows: "workflow",
};

const SECTION_BLURB: Record<string, string> = {
  agents: "A single agent: one model, its instructions, and the tools it can call.",
  orchestrators: "Several agents coordinated by a pattern - round-robin, AI-selected, or plan-based.",
  workflows: "A deterministic pipeline of steps with a typed input, no model in the loop deciding order.",
};

const SECTION_LABEL: Record<string, string> = {
  overview: "Overview",
  agents: "Agents",
  orchestrators: "Orchestrators",
  workflows: "Workflows",
  gallery: "Examples",
  history: "History",
  evaluation: "Evaluation",
  mcp: "MCP Playground",
};

export default function App() {
  return (
    <RouterProvider>
      <AppShell />
    </RouterProvider>
  );
}

function AppShell() {
  const segs = useSegments();
  const [section, subId] = segs;

  // ---- server capabilities (scanned dir, persistence, mcp) ----
  const [health, setHealth] = useState<HealthResponse | null>(null);
  useEffect(() => {
    apiClient.getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  // ---- entities ----
  const [entities, setEntities] = useState<Entity[]>([]);
  const [entitiesLoading, setEntitiesLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const refreshEntities = useCallback(async () => {
    try {
      const list = await apiClient.getEntities();
      setEntities(list);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load entities");
    } finally {
      setEntitiesLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshEntities();
  }, [refreshEntities]);

  // ---- mcp servers (sidebar + playground share this list) ----
  const [mcpServers, setMcpServers] = useState<McpServerSummary[]>([]);
  const refreshMcpServers = useCallback(async () => {
    try {
      setMcpServers(await mcpApiClient.listServers());
    } catch {
      setMcpServers([]);
    }
  }, []);
  useEffect(() => {
    refreshMcpServers();
  }, [refreshMcpServers]);

  // ---- sessions (per entity) ----
  const [sessionCache, setSessionCache] = useState<Record<string, SessionInfo>>({});

  // ---- debug panel ----
  const [debugEvents, setDebugEvents] = useState<StreamEvent[]>([]);
  const [debugOpen, setDebugOpen] = useState(
    () => localStorage.getItem("debugPanelOpen") !== "false"
  );
  const [debugWidth, setDebugWidth] = useState(() => {
    const saved = localStorage.getItem("debugPanelWidth");
    return saved ? parseInt(saved, 10) : 320;
  });
  useEffect(() => {
    localStorage.setItem("debugPanelOpen", String(debugOpen));
  }, [debugOpen]);
  useEffect(() => {
    localStorage.setItem("debugPanelWidth", String(debugWidth));
  }, [debugWidth]);

  const handleDebugEvent = useCallback((event: StreamEvent) => {
    setDebugEvents((prev) => [...prev.slice(-499), event]);
  }, []);

  const startResize = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startWidth = debugWidth;
      const onMove = (move: MouseEvent) => {
        const next = Math.max(
          240,
          Math.min(window.innerWidth * 0.5, startWidth + (startX - move.clientX))
        );
        setDebugWidth(next);
      };
      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    },
    [debugWidth]
  );

  // ---- routing ----
  const entityType = SECTION_TYPE[section];
  const selectedEntity =
    entityType && subId ? entities.find((e) => e.type === entityType && e.id === subId) : undefined;
  const isEntityPage = Boolean(selectedEntity);

  // "/" is the Overview landing page. Section routes list their entities
  // rather than silently redirecting into an arbitrary one.
  useEffect(() => {
    if (!section) navigate("/overview", { replace: true });
  }, [section]);

  // Ensure a session exists for the routed entity; clear debug on change
  useEffect(() => {
    setDebugEvents([]);
    if (!selectedEntity || selectedEntity.type === "workflow") return;
    if (sessionCache[selectedEntity.id]) return;
    let cancelled = false;
    apiClient
      .getOrCreateSession(selectedEntity.id, selectedEntity.type)
      .then((session) => {
        if (!cancelled) {
          setSessionCache((prev) => ({ ...prev, [selectedEntity.id]: session }));
        }
      })
      .catch((e) => console.error("Failed to load session:", e));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEntity?.id]);

  const handleSessionChange = useCallback(
    (session: SessionInfo) => {
      if (selectedEntity) {
        setSessionCache((prev) => ({ ...prev, [selectedEntity.id]: session }));
      }
    },
    [selectedEntity]
  );

  const handleExampleLoaded = useCallback(
    async (entity: Entity) => {
      await refreshEntities();
      const sectionKey = `${entity.type}s`;
      navigate(`/${sectionKey}/${encodeURIComponent(entity.id)}`);
    },
    [refreshEntities]
  );

  const [pendingDeleteEntity, setPendingDeleteEntity] = useState<Entity | null>(null);
  const handleDeleteEntity = useCallback(async () => {
    if (!pendingDeleteEntity) return;
    try {
      await apiClient.deleteEntity(pendingDeleteEntity.id);
      if (selectedEntity?.id === pendingDeleteEntity.id) {
        navigate(`/${pendingDeleteEntity.type}s`);
      }
      await refreshEntities();
    } catch (e) {
      console.error("Failed to delete entity:", e);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingDeleteEntity, refreshEntities]);

  // ---- breadcrumbs ----
  const crumbs: Crumb[] = [];
  if (section && SECTION_LABEL[section]) {
    crumbs.push({
      label: SECTION_LABEL[section],
      href: section === "evaluation" ? "/evaluation/runs" : `/${section}`,
    });
    if (selectedEntity) {
      crumbs.push({ label: selectedEntity.name || selectedEntity.id });
    } else if (section === "evaluation" && subId) {
      crumbs.push({ label: subId.charAt(0).toUpperCase() + subId.slice(1) });
    } else if (section === "mcp" && subId) {
      crumbs.push({ label: subId });
    } else if (section === "history" && subId) {
      crumbs.push({ label: subId.slice(0, 12) });
    }
  }

  // ---- content ----
  const renderContent = () => {
    if (entitiesLoading && entityType) {
      return (
        <div className="space-y-3 p-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-4 w-96" />
          <Skeleton className="h-40 w-full max-w-3xl" />
        </div>
      );
    }

    if (loadError && entityType) {
      return (
        <EmptyState
          icon={SearchX}
          title="Failed to load entities"
            className="px-4"
          description={loadError}
          action={
            <Button variant="outline" size="sm" onClick={refreshEntities}>
              Retry
            </Button>
          }
        />
      );
    }

    if (entityType && subId && !selectedEntity) {
      return (
        <EmptyState
          icon={SearchX}
          title="Not found"
            className="px-4"
          description={`No ${entityType} named "${subId}" is loaded. It may have been removed.`}
          action={
            <Button variant="outline" size="sm" onClick={() => navigate(`/${section}`)}>
              Back to {SECTION_LABEL[section]}
            </Button>
          }
        />
      );
    }

    if (entityType && !subId) {
      const icon = section === "agents" ? Bot : section === "orchestrators" ? Users : GitBranch;
      return (
        <EntityListView
          section={section}
          label={SECTION_LABEL[section]}
          icon={icon}
          description={SECTION_BLURB[section]}
          entities={entities.filter((e) => e.type === entityType)}
          entitiesDir={health?.entities_dir}
        />
      );
    }

    if (selectedEntity?.type === "agent") {
      return (
        <AgentView
          selectedAgent={selectedEntity as AgentInfo}
          currentSession={sessionCache[selectedEntity.id]}
          onSessionChange={handleSessionChange}
          onDebugEvent={handleDebugEvent}
        />
      );
    }
    if (selectedEntity?.type === "orchestrator") {
      return (
        <OrchestratorView
          selectedOrchestrator={selectedEntity as OrchestratorInfo}
          currentSession={sessionCache[selectedEntity.id]}
          onSessionChange={handleSessionChange}
          onDebugEvent={handleDebugEvent}
        />
      );
    }
    if (selectedEntity?.type === "workflow") {
      return (
        <WorkflowView
          selectedWorkflow={selectedEntity as WorkflowInfo}
          onDebugEvent={handleDebugEvent}
        />
      );
    }

    switch (section) {
      case "overview":
        return (
          <OverviewView
            entities={entities}
            mcpServers={mcpServers}
            loading={entitiesLoading}
          />
        );
      case "gallery":
        return <ExamplesGallery onExampleLoaded={handleExampleLoaded} />;
      case "history":
        return <RunsView selectedRunId={subId} entities={entities} />;
      case "evaluation":
        return <EvalView tab={subId || "runs"} />;
      case "mcp":
        return (
          <McpView
            servers={mcpServers}
            selectedServerId={subId}
            onServersChanged={refreshMcpServers}
          />
        );
      default:
        return null;
    }
  };

  return (
    <SidebarProvider>
      <AppSidebar
        segments={segs}
        entities={entities}
        mcpServers={mcpServers}
        onDeleteEntity={setPendingDeleteEntity}
      />
      <SidebarInset>
        <TopBar
          crumbs={crumbs}
          showDebugToggle={isEntityPage}
          debugOpen={debugOpen}
          onToggleDebug={() => setDebugOpen((o) => !o)}
        />
        <div className="flex min-h-0 flex-1">
          <div className="min-w-0 flex-1 overflow-hidden">{renderContent()}</div>
          {isEntityPage && debugOpen && (
            <>
              <div
                className="group relative w-1 shrink-0 cursor-col-resize bg-border hover:bg-accent"
                onMouseDown={startResize}
                onDoubleClick={() => setDebugOpen(false)}
                title="Drag to resize · double-click to close"
              />
              <div className="shrink-0" style={{ width: debugWidth }}>
                <DebugPanel events={debugEvents} onClear={() => setDebugEvents([])} />
              </div>
            </>
          )}
        </div>
        <ConfirmDialog
          open={pendingDeleteEntity !== null}
          onOpenChange={(open) => !open && setPendingDeleteEntity(null)}
          title="Remove entity?"
          description={`This removes "${pendingDeleteEntity?.name || pendingDeleteEntity?.id}" from the registry.`}
          confirmLabel="Remove"
          onConfirm={handleDeleteEntity}
        />
      </SidebarInset>
    </SidebarProvider>
  );
}
