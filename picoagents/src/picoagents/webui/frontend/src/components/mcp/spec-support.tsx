/**
 * SpecSupportView - which 2026-07-28 spec features the installed Python SDK
 * actually supports, probed live from the package on every request.
 */

import { useEffect, useState } from "react";
import { Check, Minus, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { mcpApiClient } from "@/services/mcp-api";
import type { McpSpecSupport } from "@/types/mcp";

export function SpecSupportView() {
  const [support, setSupport] = useState<McpSpecSupport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    mcpApiClient
      .getSpecSupport()
      .then(setSupport)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  if (error) return <div className="text-sm text-destructive">{error}</div>;
  if (!support)
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <RefreshCw className="size-3.5 animate-spin" /> Probing installed SDK...
      </div>
    );

  const missing = support.features.filter((f) => f.status !== "shipped");

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">mcp {support.version}</Badge>
        <Badge variant="outline">spec {support.protocol_version}</Badge>
        <span className="text-xs text-muted-foreground">probed live from the installed package</span>
      </div>

      <div className="divide-y rounded-md border">
        {support.features.map((feature) => (
          <div key={feature.key} className="flex items-start gap-3 px-3 py-2">
            {feature.status === "shipped" ? (
              <Check className="mt-0.5 size-4 shrink-0 text-success" />
            ) : (
              <Minus className="mt-0.5 size-4 shrink-0 text-muted-foreground/50" />
            )}
            <div className="min-w-0">
              <div
                className={
                  feature.status === "shipped"
                    ? "text-sm font-medium"
                    : "text-sm font-medium text-muted-foreground"
                }
              >
                {feature.label}
              </div>
              <div className="text-xs text-muted-foreground">{feature.description}</div>
            </div>
          </div>
        ))}
      </div>

      {missing.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {missing.map((f) => f.label).join(", ")}{" "}
          {missing.length === 1 ? "is" : "are"} defined in the spec but not available in
          this environment, so the playground cannot exercise{" "}
          {missing.length === 1 ? "it" : "them"}.
        </p>
      )}
    </div>
  );
}
