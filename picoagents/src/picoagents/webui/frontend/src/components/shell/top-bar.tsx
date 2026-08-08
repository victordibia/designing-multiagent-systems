/**
 * TopBar - breadcrumb on the left; debug-dock and theme controls top-right.
 */

import { Fragment } from "react";
import { PanelRight } from "lucide-react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { ModeToggle } from "@/components/mode-toggle";
import { cn } from "@/lib/utils";

export interface Crumb {
  label: string;
  href?: string;
}

interface TopBarProps {
  crumbs: Crumb[];
  showDebugToggle?: boolean;
  debugOpen?: boolean;
  onToggleDebug?: () => void;
}

export function TopBar({ crumbs, showDebugToggle, debugOpen, onToggleDebug }: TopBarProps) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3">
      <SidebarTrigger />
      <Separator orientation="vertical" className="h-4" />
      <Breadcrumb>
        {crumbs.map((crumb, index) => (
          <Fragment key={index}>
            {index > 0 && <BreadcrumbSeparator />}
            <BreadcrumbItem>
              {crumb.href && index < crumbs.length - 1 ? (
                <BreadcrumbLink href={`#${crumb.href}`}>{crumb.label}</BreadcrumbLink>
              ) : (
                <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
              )}
            </BreadcrumbItem>
          </Fragment>
        ))}
      </Breadcrumb>
      <div className="ml-auto flex items-center gap-1">
        {showDebugToggle && (
          <Button
            variant="ghost"
            size="icon"
            className={cn("size-7", debugOpen && "bg-accent text-accent-foreground")}
            onClick={onToggleDebug}
            title={debugOpen ? "Hide debug panel" : "Show debug panel"}
          >
            <PanelRight className="size-4" />
          </Button>
        )}
        <ModeToggle />
      </div>
    </header>
  );
}
