/**
 * EmptyState - the single empty/none-yet pattern for every view.
 */

import type { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-start gap-2 px-4 py-10">
      <Icon className="size-7 text-muted-foreground/50" />
      <div>
        <div className="text-sm font-medium">{title}</div>
        {description && <div className="mt-0.5 max-w-md text-sm text-muted-foreground">{description}</div>}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
