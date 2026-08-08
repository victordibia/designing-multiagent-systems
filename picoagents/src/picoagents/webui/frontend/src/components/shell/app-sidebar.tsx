/**
 * AppSidebar - global navigation.
 *
 * Build: Agents / Orchestrators / Workflows with their entities as sub-items
 * (replaces the old header entity dropdown). Observe: History, Evaluation.
 * Tools: MCP Playground with configured servers as sub-items.
 */

import {
  Bot,
  BookOpen,
  Cable,
  FlaskConical,
  GitBranch,
  History,
  Trash2,
  Users,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuLabel,
  SidebarMenuSub,
  SidebarMenuSubButton,
  useSidebar,
} from "@/components/ui/sidebar";
import { navigate } from "@/lib/router";
import { cn } from "@/lib/utils";
import type { Entity } from "@/types";
import type { McpServerSummary } from "@/types/mcp";

interface AppSidebarProps {
  segments: string[];
  entities: Entity[];
  mcpServers: McpServerSummary[];
  /** Called for entities that can be removed (gallery/memory sourced). */
  onDeleteEntity?: (entity: Entity) => void;
}

interface EntitySectionSpec {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  type: "agent" | "orchestrator" | "workflow";
}

const ENTITY_SECTIONS: EntitySectionSpec[] = [
  { key: "agents", label: "Agents", icon: Bot, type: "agent" },
  { key: "orchestrators", label: "Orchestrators", icon: Users, type: "orchestrator" },
  { key: "workflows", label: "Workflows", icon: GitBranch, type: "workflow" },
];

export function AppSidebar({ segments, entities, mcpServers, onDeleteEntity }: AppSidebarProps) {
  const { open } = useSidebar();
  const [section, selectedId] = segments;

  return (
    <Sidebar>
      <SidebarHeader className={cn(!open && "justify-center px-0")}>
        <button
          className="flex items-center gap-2 text-sm font-semibold outline-none"
          onClick={() => navigate("/agents")}
        >
          <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Bot className="size-4" />
          </span>
          {open && <span>PicoAgents</span>}
        </button>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Build</SidebarGroupLabel>
          <SidebarMenu>
            {ENTITY_SECTIONS.map((spec) => {
              const sectionEntities = entities.filter((e) => e.type === spec.type);
              const isActive = section === spec.key && !selectedId;
              return (
                <SidebarMenuItem key={spec.key}>
                  <SidebarMenuButton
                    isActive={isActive}
                    tooltip={spec.label}
                    onClick={() => navigate(`/${spec.key}`)}
                  >
                    <spec.icon className="size-4 shrink-0" />
                    <SidebarMenuLabel>{spec.label}</SidebarMenuLabel>
                    {open && sectionEntities.length > 0 && (
                      <span className="ml-auto text-xs text-sidebar-foreground/50">
                        {sectionEntities.length}
                      </span>
                    )}
                  </SidebarMenuButton>
                  {sectionEntities.length > 0 && (
                    <SidebarMenuSub>
                      {sectionEntities.map((entity) => {
                        const canDelete =
                          onDeleteEntity &&
                          ["memory", "github"].includes((entity as any).source);
                        return (
                          <li key={entity.id} className="group/entity relative">
                            <SidebarMenuSubButton
                              isActive={section === spec.key && selectedId === entity.id}
                              className={cn(canDelete && "pr-6")}
                              onClick={() =>
                                navigate(`/${spec.key}/${encodeURIComponent(entity.id)}`)
                              }
                            >
                              <span className="truncate font-mono">
                                {entity.name || entity.id}
                              </span>
                            </SidebarMenuSubButton>
                            {canDelete && (
                              <button
                                className="absolute right-1 top-1/2 -translate-y-1/2 rounded p-0.5 text-sidebar-foreground/40 opacity-0 transition-opacity hover:text-destructive group-hover/entity:opacity-100"
                                title="Remove entity"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onDeleteEntity(entity);
                                }}
                              >
                                <Trash2 className="size-3" />
                              </button>
                            )}
                          </li>
                        );
                      })}
                    </SidebarMenuSub>
                  )}
                </SidebarMenuItem>
              );
            })}
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={section === "gallery"}
                tooltip="Examples"
                onClick={() => navigate("/gallery")}
              >
                <BookOpen className="size-4 shrink-0" />
                <SidebarMenuLabel>Examples</SidebarMenuLabel>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Observe</SidebarGroupLabel>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={section === "history"}
                tooltip="History"
                onClick={() => navigate("/history")}
              >
                <History className="size-4 shrink-0" />
                <SidebarMenuLabel>History</SidebarMenuLabel>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={section === "evaluation"}
                tooltip="Evaluation"
                onClick={() => navigate("/evaluation/runs")}
              >
                <FlaskConical className="size-4 shrink-0" />
                <SidebarMenuLabel>Evaluation</SidebarMenuLabel>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Tools</SidebarGroupLabel>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                isActive={section === "mcp" && !selectedId}
                tooltip="MCP Playground"
                onClick={() => navigate("/mcp")}
              >
                <Cable className="size-4 shrink-0" />
                <SidebarMenuLabel>MCP Playground</SidebarMenuLabel>
              </SidebarMenuButton>
              {mcpServers.length > 0 && (
                <SidebarMenuSub>
                  {mcpServers.map((server) => (
                    <li key={server.server_id}>
                      <SidebarMenuSubButton
                        isActive={section === "mcp" && selectedId === server.server_id}
                        onClick={() =>
                          navigate(`/mcp/${encodeURIComponent(server.server_id)}`)
                        }
                      >
                        <span
                          className={cn(
                            "size-1.5 shrink-0 rounded-full",
                            server.status === "connected"
                              ? "bg-success"
                              : "bg-sidebar-foreground/30"
                          )}
                        />
                        <span className="truncate font-mono">{server.server_id}</span>
                      </SidebarMenuSubButton>
                    </li>
                  ))}
                </SidebarMenuSub>
              )}
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
