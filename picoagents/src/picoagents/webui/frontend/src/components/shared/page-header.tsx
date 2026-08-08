/**
 * PageHeader - the single page-title contract for every view.
 * Title (text-lg) + optional description + actions slot on the right.
 */

import { cn } from "@/lib/utils";

interface PageHeaderProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <div className={cn("flex shrink-0 items-start justify-between gap-4 border-b px-4 py-3", className)}>
      <div className="min-w-0">
        <h1 className="flex items-center gap-2 text-lg font-semibold leading-tight">{title}</h1>
        {description && (
          <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
