/**
 * OverviewView - the landing page.
 *
 * Answers the three questions a developer has right after launching:
 * what was discovered, where did it look, and what do I do next. When
 * nothing was discovered it carries the same guidance the CLI prints.
 */

import { useEffect, useState } from "react";
import {
  Bot,
  BookOpen,
  Cable,
  Clock,
  Database,
  FolderSearch,
  GitBranch,
  History,
  Users,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shared/page-header";
import { StatusBadge } from "@/components/shared/status-badge";
import { navigate } from "@/lib/router";
import { apiClient } from "@/services/api";
import { evalApiClient } from "@/services/eval-api";
import type { Entity, HealthResponse } from "@/types";
import type { McpServerSummary } from "@/types/mcp";
import type { Run } from "@/types/eval";

const QUICKSTART = `# my_agent.py - the webui discovers this variable by name
from picoagents.agents import Agent
from picoagents.llm import OpenAIChatCompletionClient

agent = Agent(
    name="my_agent",
    description="What this agent does",
    instructions="You are a helpful assistant.",
    model_client=OpenAIChatCompletionClient(model="gpt-4o-mini"),
)`;

interface OverviewViewProps {
  entities: Entity[];
  mcpServers: McpServerSummary[];
  loading: boolean;
}

export function OverviewView({ entities, mcpServers, loading }: OverviewViewProps) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [recentRuns, setRecentRuns] = useState<Run[]>([]);

  useEffect(() => {
    apiClient.getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (health?.persistence_enabled === false) return;
    evalApiClient
      .listRuns({ limit: 5 })
      .then(setRecentRuns)
      .catch(() => setRecentRuns([]));
  }, [health?.persistence_enabled]);

  const counts = {
    agent: entities.filter((e) => e.type === "agent").length,
    orchestrator: entities.filter((e) => e.type === "orchestrator").length,
    workflow: entities.filter((e) => e.type === "workflow").length,
  };
  const total = entities.length;

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title={
          <>
            Overview
            {health?.version && (
              <span className="text-sm font-normal text-muted-foreground">
                picoagents {health.version}
              </span>
            )}
          </>
        }
        description={
          health?.entities_dir
            ? `Scanning ${health.entities_dir}`
            : "No entities directory configured - serving programmatically registered entities only."
        }
        actions={
          <Button size="sm" className="h-8" onClick={() => navigate("/gallery")}>
            <BookOpen className="size-3.5" /> Browse examples
          </Button>
        }
      />

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="max-w-4xl space-y-6">
          {loading ? (
            <div className="space-y-3">
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-32 w-full" />
            </div>
          ) : total === 0 ? (
            <GettingStarted entitiesDir={health?.entities_dir ?? null} />
          ) : (
            <section>
              <h2 className="mb-2 text-sm font-medium">Discovered</h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <CountCard
                  icon={Bot}
                  label="Agents"
                  count={counts.agent}
                  href="#/agents"
                />
                <CountCard
                  icon={Users}
                  label="Orchestrators"
                  count={counts.orchestrator}
                  href="#/orchestrators"
                />
                <CountCard
                  icon={GitBranch}
                  label="Workflows"
                  count={counts.workflow}
                  href="#/workflows"
                />
              </div>
            </section>
          )}

          <section>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-medium">Recent activity</h2>
              {recentRuns.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => navigate("/history")}
                >
                  View all history
                </Button>
              )}
            </div>
            {health && !health.persistence_enabled ? (
              <Alert>
                <Database />
                <AlertTitle>Run recording is off</AlertTitle>
                <AlertDescription>
                  Executions are not being recorded, so History stays empty. Install
                  the persistence extra to turn it on:{" "}
                  <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                    pip install "picoagents[persist]"
                  </code>
                </AlertDescription>
              </Alert>
            ) : recentRuns.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nothing has run yet. Open an agent and send it a task - the
                execution will show up here and in History.
              </p>
            ) : (
              <div className="divide-y rounded-md border">
                {recentRuns.map((run) => (
                  <button
                    key={run.id}
                    className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-muted/50"
                    onClick={() => navigate(`/history/${encodeURIComponent(run.id)}`)}
                  >
                    <Clock className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate text-sm font-medium">{run.agent_name}</span>
                    <StatusBadge status={run.status} />
                    <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                      {run.duration_ms >= 1000
                        ? `${(run.duration_ms / 1000).toFixed(1)}s`
                        : `${run.duration_ms}ms`}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-medium">MCP servers</h2>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 text-xs"
                onClick={() => navigate("/mcp")}
              >
                Open playground
              </Button>
            </div>
            {mcpServers.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No servers configured. The playground ships lab servers you can add
                in one click to explore the 2026-07-28 spec.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {mcpServers.map((server) => (
                  <button
                    key={server.server_id}
                    className="flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs hover:bg-muted/50"
                    onClick={() => navigate(`/mcp/${encodeURIComponent(server.server_id)}`)}
                  >
                    <Cable className="size-3.5 text-muted-foreground" />
                    <span className="font-mono">{server.server_id}</span>
                    <StatusBadge status={server.status} />
                  </button>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function CountCard({
  icon: Icon,
  label,
  count,
  href,
}: {
  icon: typeof Bot;
  label: string;
  count: number;
  href: string;
}) {
  return (
    <a href={href} className="block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring">
    <Card className="py-0 transition-colors hover:bg-muted/50">
      <CardContent className="flex items-center gap-3 p-3">
        <Icon className="size-4 text-muted-foreground" />
        <div>
          <div className="text-lg font-semibold leading-none">{count}</div>
          <div className="mt-1 text-xs text-muted-foreground">{label}</div>
        </div>
      </CardContent>
    </Card>
    </a>
  );
}

function GettingStarted({ entitiesDir }: { entitiesDir: string | null }) {
  return (
    <section className="space-y-3">
      <Alert>
        <FolderSearch />
        <AlertTitle>
          {entitiesDir
            ? `No agents, orchestrators, or workflows found in ${entitiesDir}`
            : "No entities directory is being scanned"}
        </AlertTitle>
        <AlertDescription>
          {entitiesDir ? (
            <>
              Discovery looks for top-level Python modules that assign an{" "}
              <code className="rounded bg-muted px-1 font-mono text-xs">agent</code>,{" "}
              <code className="rounded bg-muted px-1 font-mono text-xs">orchestrator</code>,
              or{" "}
              <code className="rounded bg-muted px-1 font-mono text-xs">workflow</code>{" "}
              variable.
            </>
          ) : (
            <>
              Restart pointed at your project to discover entities:{" "}
              <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                picoagents ui --entities-dir .
              </code>
            </>
          )}
        </AlertDescription>
      </Alert>

      <div>
        <h2 className="mb-2 text-sm font-medium">Define an agent</h2>
        <pre className="overflow-x-auto rounded-md border bg-muted/50 p-3 font-mono text-xs leading-relaxed">
          {QUICKSTART}
        </pre>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => navigate("/gallery")}>
          <BookOpen className="size-3.5" /> Load a working example
        </Button>
        <Button variant="outline" size="sm" onClick={() => navigate("/mcp")}>
          <Cable className="size-3.5" /> Explore the MCP playground
        </Button>
        <Button variant="ghost" size="sm" onClick={() => navigate("/history")}>
          <History className="size-3.5" /> History
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Loading an example downloads it from GitHub and registers it in this
        session - nothing is written to your project.
      </p>
    </section>
  );
}
