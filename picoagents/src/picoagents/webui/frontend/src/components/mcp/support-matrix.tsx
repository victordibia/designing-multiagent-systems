/**
 * SupportMatrix - per-SDK feature support for the MCP 2026-07-28 spec.
 *
 * The Python row is introspected live from the installed mcp package;
 * other rows are curated data dated by as_of. Unsupported features are
 * shown, not hidden - the gaps are the point.
 */

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Check, CircleDashed, Minus, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { mcpApiClient } from "@/services/mcp-api";
import type { McpFeatureStatus, McpSupportMatrix } from "@/types/mcp";

function StatusCell({ status, note }: { status: McpFeatureStatus; note?: string }) {
  const icon =
    status === "shipped" ? (
      <Check className="h-3.5 w-3.5 text-success" />
    ) : status === "partial" ? (
      <CircleDashed className="h-3.5 w-3.5 text-warning" />
    ) : (
      <Minus className="h-3.5 w-3.5 text-muted-foreground/50" />
    );
  return (
    <td className="px-2 py-1.5 text-center" title={note || status}>
      <span className="inline-flex">{icon}</span>
    </td>
  );
}

export function SupportMatrixView() {
  const [matrix, setMatrix] = useState<McpSupportMatrix | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    mcpApiClient
      .getSupportMatrix()
      .then(setMatrix)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  if (error) return <div className="p-4 text-sm text-destructive">{error}</div>;
  if (!matrix)
    return (
      <div className="p-4 text-sm text-muted-foreground flex items-center gap-2">
        <RefreshCw className="h-3.5 w-3.5 animate-spin" /> Loading matrix...
      </div>
    );

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant="secondary">spec {matrix.protocol_version}</Badge>
        <Badge variant="outline">as of {matrix.as_of}</Badge>
      </div>
      <div className="overflow-x-auto border border-border rounded-md">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-muted/40 border-b border-border">
              <th className="px-2 py-2 text-left font-medium">Feature</th>
              {matrix.sdks.map((sdk) => (
                <th key={sdk.sdk} className="px-2 py-2 text-center font-medium">
                  <div>{sdk.label}</div>
                  <div
                    className={cn(
                      "text-[10px] font-normal",
                      sdk.source === "introspected"
                        ? "text-success"
                        : "text-muted-foreground"
                    )}
                  >
                    {sdk.source === "introspected" ? `live · ${sdk.version}` : sdk.version}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.features.map((feature) => (
              <tr key={feature.key} className="border-b border-border/50 last:border-b-0">
                <td className="px-2 py-1.5">
                  <div className="font-medium">{feature.label}</div>
                  <div className="text-[10px] text-muted-foreground">{feature.description}</div>
                </td>
                {matrix.sdks.map((sdk) => {
                  const cell = sdk.features[feature.key] ?? { status: "unknown" as const };
                  return <StatusCell key={sdk.sdk} status={cell.status} note={cell.note} />;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-muted-foreground">{matrix.notes}</p>
    </div>
  );
}
