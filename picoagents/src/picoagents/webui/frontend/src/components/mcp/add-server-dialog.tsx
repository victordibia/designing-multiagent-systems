/**
 * AddServerDialog - register an MCP server (stdio or streamable HTTP),
 * with one-click presets for the lab servers.
 */

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FlaskConical } from "lucide-react";
import { mcpApiClient } from "@/services/mcp-api";
import type { AddServerPayload, McpPreset } from "@/types/mcp";

interface AddServerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded: () => void;
}

export function AddServerDialog({ open, onOpenChange, onAdded }: AddServerDialogProps) {
  const [transport, setTransport] = useState<"stdio" | "streamable-http">("stdio");
  const [serverId, setServerId] = useState("");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [url, setUrl] = useState("");
  const [headersText, setHeadersText] = useState("");
  const [presets, setPresets] = useState<McpPreset[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      mcpApiClient.getPresets().then(setPresets).catch(() => setPresets([]));
      setError(null);
    }
  }, [open]);

  const submit = async (payload: AddServerPayload) => {
    setSubmitting(true);
    setError(null);
    try {
      await mcpApiClient.addServer(payload);
      onAdded();
      onOpenChange(false);
      setServerId("");
      setCommand("");
      setArgsText("");
      setUrl("");
      setHeadersText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const submitForm = () => {
    if (!serverId.trim()) {
      setError("Server id is required");
      return;
    }
    if (transport === "stdio") {
      submit({
        server_id: serverId.trim(),
        transport: "stdio",
        command: command.trim(),
        args: argsText.trim() ? argsText.trim().split(/\s+/) : [],
      });
    } else {
      let headers: Record<string, string> | undefined;
      if (headersText.trim()) {
        try {
          headers = JSON.parse(headersText);
        } catch {
          setError("Headers must be valid JSON");
          return;
        }
      }
      submit({ server_id: serverId.trim(), transport, url: url.trim(), headers });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader onClose={() => onOpenChange(false)}>
        <DialogTitle>Add MCP server</DialogTitle>
      </DialogHeader>
      <DialogContent className="p-4 w-[480px] max-w-[90vw] space-y-4 overflow-auto max-h-[80vh]">
        {presets.length > 0 && (
          <div className="space-y-1.5">
            <Label className="text-xs">Lab presets</Label>
            <div className="grid gap-1.5">
              {presets.map((preset) => (
                <button
                  key={preset.server_id}
                  className="flex items-center gap-2 px-2 py-1.5 rounded border border-border hover:bg-muted/50 text-left text-xs"
                  disabled={submitting}
                  onClick={() =>
                    submit({
                      server_id: preset.server_id,
                      transport: "stdio",
                      command: preset.command,
                      args: preset.args,
                    })
                  }
                >
                  <FlaskConical className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="font-mono font-medium">{preset.server_id}</span>
                  <span className="text-muted-foreground truncate">{preset.description}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-3">
          <div className="flex gap-2">
            {(["stdio", "streamable-http"] as const).map((t) => (
              <Button
                key={t}
                size="sm"
                variant={transport === t ? "default" : "outline"}
                onClick={() => setTransport(t)}
              >
                {t}
              </Button>
            ))}
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Server id</Label>
            <Input
              className="h-8 text-xs"
              placeholder="my-server"
              value={serverId}
              onChange={(e) => setServerId(e.target.value)}
            />
          </div>

          {transport === "stdio" ? (
            <>
              <div className="space-y-1">
                <Label className="text-xs">Command</Label>
                <Input
                  className="h-8 text-xs font-mono"
                  placeholder="python"
                  value={command}
                  onChange={(e) => setCommand(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Arguments (space-separated)</Label>
                <Input
                  className="h-8 text-xs font-mono"
                  placeholder="path/to/server.py"
                  value={argsText}
                  onChange={(e) => setArgsText(e.target.value)}
                />
              </div>
            </>
          ) : (
            <>
              <div className="space-y-1">
                <Label className="text-xs">URL</Label>
                <Input
                  className="h-8 text-xs font-mono"
                  placeholder="http://localhost:8000/mcp"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Headers (JSON, optional)</Label>
                <Input
                  className="h-8 text-xs font-mono"
                  placeholder='{"Authorization": "Bearer ..."}'
                  value={headersText}
                  onChange={(e) => setHeadersText(e.target.value)}
                />
              </div>
            </>
          )}

          {error && <p className="text-xs text-destructive">{error}</p>}

          <div className="flex justify-end gap-2">
            <Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={submitForm} disabled={submitting}>
              Add server
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
