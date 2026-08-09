/**
 * EmptyState - the single empty/none-yet pattern for every view.
 *
 * Owns no horizontal padding: it is a content block, so it inherits the
 * page's content padding and lines up with every sibling heading.
 */

import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  /** Add padding when the container does not provide it (e.g. full-bleed lists). */
  className?: string;
}

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-start gap-2 py-10", className)}>
      <Icon className="size-7 text-muted-foreground/50" />
      <div>
        <div className="text-sm font-medium">{title}</div>
        {description && <div className="mt-0.5 max-w-md text-sm text-muted-foreground">{description}</div>}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
