/**
 * EntityListView - the section landing page for Agents / Orchestrators /
 * Workflows. Shows what each entity is and what it needs, so the developer
 * can pick one deliberately instead of being dropped into an arbitrary chat.
 */

import type { LucideIcon } from "lucide-react";
import { AlertTriangle, BookOpen, Brain, ChevronRight, Wrench } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";
import { navigate } from "@/lib/router";
import type { AgentInfo, Entity, OrchestratorInfo, WorkflowInfo } from "@/types";

interface EntityListViewProps {
  section: string;
  label: string;
  icon: LucideIcon;
  description: string;
  entities: Entity[];
  entitiesDir?: string | null;
}

export function EntityListView({
  section,
  label,
  icon: Icon,
  description,
  entities,
  entitiesDir,
}: EntityListViewProps) {
  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title={
          <>
            {label}
            {entities.length > 0 && (
              <Badge variant="outline" className="text-xs">
                {entities.length}
              </Badge>
            )}
          </>
        }
        description={description}
        actions={
          <Button variant="outline" size="sm" className="h-8" onClick={() => navigate("/gallery")}>
            <BookOpen className="size-3.5" /> Examples
          </Button>
        }
      />

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {entities.length === 0 ? (
          <div className="max-w-3xl">
            <EmptyState
              icon={Icon}
              title={`No ${label.toLowerCase()} loaded`}
              description={
                entitiesDir
                  ? `Nothing in ${entitiesDir} defines a ${section.slice(0, -1)}. Load a working example to see one running, or check the Overview page for what discovery looks for.`
                  : "No entities directory is being scanned. Load a working example to try one now, or see the Overview page for how to point the server at your project."
              }
              action={
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => navigate("/gallery")}>
                    <BookOpen className="size-3.5" /> Load an example
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => navigate("/overview")}>
                    Overview
                  </Button>
                </div>
              }
            />
          </div>
        ) : (
          <div className="grid max-w-5xl grid-cols-1 gap-3 lg:grid-cols-2">
            {entities.map((entity) => (
              <EntityCard key={entity.id} entity={entity} section={section} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function EntityCard({ entity, section }: { entity: Entity; section: string }) {
  const href = `#/${section}/${encodeURIComponent(entity.id)}`;
  const agent = entity as AgentInfo;
  const orchestrator = entity as OrchestratorInfo;
  const workflow = entity as WorkflowInfo;

  return (
    <a href={href} className="group block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring">
    <Card className="py-0 transition-colors group-hover:bg-muted/40">
      <CardContent className="space-y-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="truncate font-medium">{entity.name || entity.id}</div>
            {entity.description && (
              <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">
                {entity.description}
              </p>
            )}
          </div>
          <ChevronRight className="mt-1 size-4 shrink-0 text-muted-foreground/40 transition-transform group-hover:translate-x-0.5" />
        </div>

        {entity.instructions && (
          <p className="line-clamp-2 rounded bg-muted/50 px-2 py-1 font-mono text-xs text-muted-foreground">
            {entity.instructions}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-1.5">
          {agent.model && (
            <Badge variant="secondary" className="text-xs">
              <Brain className="size-3" /> {agent.model}
            </Badge>
          )}
          {entity.type === "orchestrator" && orchestrator.agents?.length > 0 && (
            <Badge variant="secondary" className="text-xs">
              {orchestrator.agents.length} agents
            </Badge>
          )}
          {entity.type === "workflow" && workflow.steps?.length > 0 && (
            <Badge variant="secondary" className="text-xs">
              {workflow.steps.length} steps
            </Badge>
          )}
          {entity.tools?.length > 0 && (
            <Badge variant="secondary" className="text-xs">
              <Wrench className="size-3" /> {entity.tools.length} tools
            </Badge>
          )}
          <Badge variant="outline" className="text-xs">
            {entity.source}
          </Badge>
        </div>

        {entity.has_env === false && entity.source === "directory" && (
          <Alert variant="warning" className="py-2">
            <AlertTriangle />
            <AlertTitle className="text-xs">No .env found next to this module</AlertTitle>
            <AlertDescription className="text-xs">
              If it needs API keys, calls will fail until they are set.
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
    </a>
  );
}
