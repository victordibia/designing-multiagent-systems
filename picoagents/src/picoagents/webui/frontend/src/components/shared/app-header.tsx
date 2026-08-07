/**
 * AppHeader - Global application header for PicoAgents WebUI
 * Features: Entity selection, mode toggle, global settings, theme toggle
 */

import { Button } from "@/components/ui/button";
import { EntitySelector } from "@/components/shared/entity-selector";
import { ModeToggle } from "@/components/mode-toggle";
import { Settings, Bot, History, FlaskConical, Cable } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Entity } from "@/types";

type AppMode = "entities" | "runs" | "evaluate" | "mcp";

interface AppHeaderProps {
  entities: Entity[];
  selectedEntity?: Entity;
  onSelect: (entity: Entity) => void;
  isLoading?: boolean;
  onViewGallery?: () => void;
  onDeleteEntity?: (entity: Entity) => void;
  appMode?: AppMode;
  onAppModeChange?: (mode: AppMode) => void;
}

const modeItems: { mode: AppMode; label: string; icon: React.ReactNode }[] = [
  { mode: "entities", label: "Entities", icon: <Bot className="h-3.5 w-3.5" /> },
  { mode: "runs", label: "Runs", icon: <History className="h-3.5 w-3.5" /> },
  { mode: "evaluate", label: "Evaluate", icon: <FlaskConical className="h-3.5 w-3.5" /> },
  { mode: "mcp", label: "MCP", icon: <Cable className="h-3.5 w-3.5" /> },
];

export function AppHeader({
  entities,
  selectedEntity,
  onSelect,
  isLoading = false,
  onViewGallery,
  onDeleteEntity,
  appMode = "entities",
  onAppModeChange,
}: AppHeaderProps) {
  return (
    <header className="flex h-14 items-center gap-4 border-b px-4">
      <div className="font-semibold shrink-0">PicoAgents</div>

      {/* App mode toggle */}
      {onAppModeChange && (
        <div className="flex items-center gap-0.5 bg-muted rounded-lg p-0.5">
          {modeItems.map(({ mode, label, icon }) => (
            <button
              key={mode}
              onClick={() => onAppModeChange(mode)}
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors",
                appMode === mode
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {icon}
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Entity selector — only shown in entities mode */}
      {appMode === "entities" && (
        <EntitySelector
          entities={entities}
          selectedEntity={selectedEntity}
          onSelect={onSelect}
          isLoading={isLoading}
          onViewGallery={onViewGallery}
          onDeleteEntity={onDeleteEntity}
        />
      )}

      <div className="flex items-center gap-2 ml-auto">
        <ModeToggle />
        <Button variant="ghost" size="sm">
          <Settings className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
