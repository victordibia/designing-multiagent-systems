/**
 * JsonBlock - the single pretty-printed JSON pattern.
 */

import { cn } from "@/lib/utils";

export function JsonBlock({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre
      className={cn(
        "overflow-x-auto rounded-md bg-muted/60 p-2 font-mono text-xs leading-snug",
        className
      )}
    >
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}
