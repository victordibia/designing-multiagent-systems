/**
 * Sidebar - shadcn-style collapsible sidebar, dependency-free.
 *
 * Follows the shadcn/ui sidebar API surface (Provider/Sidebar/Header/
 * Content/Footer/Group/Menu/MenuButton/Trigger/Inset) and consumes the
 * --sidebar design tokens defined in index.css. Collapses to an icon rail;
 * state persists to localStorage. Swap for the official registry component
 * when convenient - call sites should not need changes.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { PanelLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const STORAGE_KEY = "sidebar:state";

interface SidebarContextValue {
  open: boolean;
  toggle: () => void;
}

const SidebarContext = createContext<SidebarContextValue | null>(null);

export function useSidebar(): SidebarContextValue {
  const context = useContext(SidebarContext);
  if (!context) throw new Error("useSidebar must be used within SidebarProvider");
  return context;
}

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState<boolean>(() => {
    return localStorage.getItem(STORAGE_KEY) !== "collapsed";
  });
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, open ? "expanded" : "collapsed");
  }, [open]);
  const toggle = useCallback(() => setOpen((o) => !o), []);

  return (
    <SidebarContext.Provider value={{ open, toggle }}>
      <div className="flex h-screen w-full overflow-hidden bg-background">
        {children}
      </div>
    </SidebarContext.Provider>
  );
}

export function Sidebar({ children }: { children: React.ReactNode }) {
  const { open } = useSidebar();
  return (
    <aside
      data-state={open ? "expanded" : "collapsed"}
      className={cn(
        "group/sidebar flex h-full shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200",
        open ? "w-60" : "w-12"
      )}
    >
      {children}
    </aside>
  );
}

export function SidebarHeader({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("flex h-14 shrink-0 items-center border-b border-sidebar-border px-3", className)}>{children}</div>;
}

export function SidebarContent({ children }: { children: React.ReactNode }) {
  return <div className="flex-1 overflow-y-auto overflow-x-hidden py-2">{children}</div>;
}

export function SidebarFooter({ children }: { children: React.ReactNode }) {
  return <div className="shrink-0 border-t border-sidebar-border p-2">{children}</div>;
}

export function SidebarGroup({ children }: { children: React.ReactNode }) {
  return <div className="px-2 py-1.5">{children}</div>;
}

export function SidebarGroupLabel({ children }: { children: React.ReactNode }) {
  const { open } = useSidebar();
  if (!open) return null;
  return (
    <div className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wider text-sidebar-foreground/50">
      {children}
    </div>
  );
}

export function SidebarMenu({ children }: { children: React.ReactNode }) {
  return <ul className="flex flex-col gap-0.5">{children}</ul>;
}

export function SidebarMenuItem({ children }: { children: React.ReactNode }) {
  return <li className="relative">{children}</li>;
}

interface SidebarMenuButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  isActive?: boolean;
  tooltip?: string;
}

export function SidebarMenuButton({
  isActive = false,
  tooltip,
  className,
  children,
  ...props
}: SidebarMenuButtonProps) {
  const { open } = useSidebar();
  return (
    <button
      data-active={isActive}
      title={!open ? tooltip : undefined}
      className={cn(
        "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm text-sidebar-foreground/80 outline-none transition-colors",
        "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        "focus-visible:ring-2 focus-visible:ring-sidebar-ring",
        "data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium data-[active=true]:text-sidebar-accent-foreground",
        !open && "justify-center px-0",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

/** Label span inside a menu button - hidden when the rail is collapsed. */
export function SidebarMenuLabel({ children, className }: { children: React.ReactNode; className?: string }) {
  const { open } = useSidebar();
  if (!open) return null;
  return <span className={cn("truncate", className)}>{children}</span>;
}

export function SidebarMenuSub({ children }: { children: React.ReactNode }) {
  const { open } = useSidebar();
  if (!open) return null;
  return (
    <ul className="ml-4 mt-0.5 flex flex-col gap-0.5 border-l border-sidebar-border pl-2">
      {children}
    </ul>
  );
}

interface SidebarMenuSubButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  isActive?: boolean;
}

export function SidebarMenuSubButton({ isActive = false, className, children, ...props }: SidebarMenuSubButtonProps) {
  return (
    <button
      data-active={isActive}
      className={cn(
        "flex w-full items-center gap-2 truncate rounded-md px-2 py-1 text-left text-xs text-sidebar-foreground/70 outline-none transition-colors",
        "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        "data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium data-[active=true]:text-sidebar-accent-foreground",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function SidebarTrigger({ className }: { className?: string }) {
  const { toggle } = useSidebar();
  return (
    <Button
      variant="ghost"
      size="icon"
      className={cn("size-7", className)}
      onClick={toggle}
      title="Toggle sidebar"
    >
      <PanelLeft className="size-4" />
    </Button>
  );
}

/** Main content area next to the sidebar. */
export function SidebarInset({ children }: { children: React.ReactNode }) {
  return <main className="flex h-full min-w-0 flex-1 flex-col">{children}</main>;
}
