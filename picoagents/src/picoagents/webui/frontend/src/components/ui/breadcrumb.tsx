import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export function Breadcrumb({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <nav aria-label="breadcrumb" className={className}>
      <ol className="flex items-center gap-1.5 text-sm text-muted-foreground">{children}</ol>
    </nav>
  );
}

export function BreadcrumbItem({ children, className }: { children: React.ReactNode; className?: string }) {
  return <li className={cn("flex items-center gap-1.5", className)}>{children}</li>;
}

export function BreadcrumbLink({
  href,
  children,
  className,
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <a href={href} className={cn("transition-colors hover:text-foreground", className)}>
      {children}
    </a>
  );
}

export function BreadcrumbPage({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span aria-current="page" className={cn("font-medium text-foreground", className)}>
      {children}
    </span>
  );
}

export function BreadcrumbSeparator() {
  return (
    <li role="presentation" aria-hidden="true">
      <ChevronRight className="size-3.5" />
    </li>
  );
}
