/**
 * ToolTester - invoke an MCP tool with JSON arguments and inspect results.
 *
 * Arguments are pre-filled with a skeleton generated from the input schema.
 * Calls that trigger MRTR park until the input banner is answered; the
 * result then completes here.
 */

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, Play } from "lucide-react";
import { mcpApiClient } from "@/services/mcp-api";
import type { McpCallResult, McpToolInfo } from "@/types/mcp";

function schemaSkeleton(schema: Record<string, any>): Record<string, any> {
  const skeleton: Record<string, any> = {};
  const properties = schema?.properties ?? {};
  for (const [name, spec] of Object.entries<any>(properties)) {
    if (spec.default !== undefined) skeleton[name] = spec.default;
    else if (spec.type === "number" || spec.type === "integer") skeleton[name] = 0;
    else if (spec.type === "boolean") skeleton[name] = false;
    else if (spec.type === "array") skeleton[name] = [];
    else if (spec.type === "object") skeleton[name] = {};
    else skeleton[name] = "";
  }
  return skeleton;
}

interface HistoryEntry {
  args: Record<string, any>;
  result: McpCallResult;
  at: number;
}

interface ToolTesterProps {
  serverId: string;
  tool: McpToolInfo;
}

export function ToolTester({ serverId, tool }: ToolTesterProps) {
  const [argsText, setArgsText] = useState("{}");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<McpCallResult | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    setArgsText(JSON.stringify(schemaSkeleton(tool.input_schema), null, 2));
    setResult(null);
    setParseError(null);
  }, [serverId, tool.name]);

  const run = async () => {
    let args: Record<string, any>;
    try {
      args = JSON.parse(argsText);
      setParseError(null);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    setRunning(true);
    setResult(null);
    try {
      const callResult = await mcpApiClient.callTool(serverId, tool.name, args);
      setResult(callResult);
      setHistory((prev) => [{ args, result: callResult, at: Date.now() }, ...prev].slice(0, 20));
    } catch (e) {
      setResult({
        is_error: true,
        error: e instanceof Error ? e.message : String(e),
        content: [],
        structured_content: null,
      });
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-medium">{tool.name}</span>
          {tool.title && <span className="text-xs text-muted-foreground">{tool.title}</span>}
        </div>
        {tool.description && (
          <p className="text-xs text-muted-foreground mt-1">{tool.description}</p>
        )}
      </div>

      <div>
        <div className="text-xs font-medium mb-1">Arguments (JSON)</div>
        <Textarea
          className="font-mono text-xs min-h-[120px]"
          value={argsText}
          onChange={(e) => setArgsText(e.target.value)}
          spellCheck={false}
        />
        {parseError && <p className="text-xs text-destructive mt-1">{parseError}</p>}
      </div>

      <div className="flex items-center gap-2">
        <Button size="sm" onClick={run} disabled={running}>
          {running ? (
            <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
          ) : (
            <Play className="h-3.5 w-3.5 mr-1" />
          )}
          {running ? "Running (may await input)..." : "Run"}
        </Button>
      </div>

      {result && (
        <div className="border border-border rounded-md p-2 space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium">Result</span>
            <Badge variant={result.is_error ? "destructive" : "secondary"}>
              {result.is_error ? "error" : "ok"}
            </Badge>
          </div>
          {result.error && <p className="text-xs text-destructive">{result.error}</p>}
          {result.structured_content && (
            <pre className="p-2 rounded bg-muted/60 text-[11px] overflow-x-auto">
              {JSON.stringify(result.structured_content, null, 2)}
            </pre>
          )}
          {result.content.length > 0 && !result.structured_content && (
            <pre className="p-2 rounded bg-muted/60 text-[11px] overflow-x-auto">
              {JSON.stringify(result.content, null, 2)}
            </pre>
          )}
        </div>
      )}

      {history.length > 1 && (
        <div>
          <div className="text-xs font-medium mb-1">History</div>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {history.map((entry, index) => (
              <button
                key={entry.at}
                className="w-full text-left px-2 py-1 rounded border border-border/60 hover:bg-muted/50 text-[11px] font-mono truncate"
                onClick={() => setArgsText(JSON.stringify(entry.args, null, 2))}
                title="Click to restore these arguments"
              >
                {index === 0 ? "· " : ""}
                {JSON.stringify(entry.args)} → {entry.result.is_error ? "error" : "ok"}
              </button>
            ))}
          </div>
        </div>
      )}

      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground">Input schema</summary>
        <pre className="mt-1 p-2 rounded bg-muted/60 text-[11px] overflow-x-auto">
          {JSON.stringify(tool.input_schema, null, 2)}
        </pre>
      </details>
    </div>
  );
}
