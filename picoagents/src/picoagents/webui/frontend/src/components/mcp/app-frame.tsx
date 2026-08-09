/**
 * AppFrame - host side of the MCP Apps bridge.
 *
 * Renders a `ui://` app in a sandboxed iframe and speaks JSON-RPC 2.0 over
 * postMessage with it, per the ext-apps spec:
 *
 *   view -> ui/initialize            host -> result (hostCapabilities)
 *   view -> ui/notifications/initialized
 *   host -> ui/notifications/tool-input / tool-result
 *   view -> tools/call | resources/read | ui/* | ping
 *
 * Tool calls from the app are proxied to the real MCP server, so anything
 * the app does shows up as ordinary traffic in the Wire tab.
 *
 * Security: the frame is sandboxed WITHOUT allow-same-origin, so it has an
 * opaque origin and cannot touch this page, its storage, or its session.
 * Because the origin is opaque, messages are authenticated by comparing
 * event.source against the frame's contentWindow rather than by origin.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { mcpApiClient } from "@/services/mcp-api";

const PROTOCOL_VERSION = "2026-01-26";

interface JsonRpcMessage {
  jsonrpc: "2.0";
  id?: number | string;
  method?: string;
  params?: any;
  result?: any;
  error?: { code: number; message: string };
}

export interface AppFrameHandle {
  /** Push a tool result into the app (host -> view notification). */
  notifyToolResult: (result: unknown) => void;
}

interface AppFrameProps {
  serverId: string;
  html: string;
  toolName: string;
  /** Latest arguments for the bound tool, sent after the handshake. */
  toolInput?: Record<string, unknown>;
  onLog?: (level: string, text: string) => void;
}

export function AppFrame({ serverId, html, toolName, toolInput, onLog }: AppFrameProps) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(260);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const post = useCallback((message: JsonRpcMessage) => {
    // Opaque-origin frame: "*" is required, and safe because the payload
    // carries nothing the app did not already have.
    frameRef.current?.contentWindow?.postMessage(message, "*");
  }, []);

  const respond = useCallback(
    (id: number | string, result: unknown) => post({ jsonrpc: "2.0", id, result }),
    [post]
  );

  const fail = useCallback(
    (id: number | string, code: number, message: string) =>
      post({ jsonrpc: "2.0", id, error: { code, message } }),
    [post]
  );

  useEffect(() => {
    const onMessage = async (event: MessageEvent) => {
      // Authenticate by frame identity - a sandboxed frame has no usable origin.
      if (!frameRef.current || event.source !== frameRef.current.contentWindow) return;
      const msg = event.data as JsonRpcMessage;
      if (!msg || msg.jsonrpc !== "2.0" || !msg.method) return;

      const { id, method, params } = msg;

      switch (method) {
        case "ui/initialize":
          if (id !== undefined) {
            respond(id, {
              protocolVersion: PROTOCOL_VERSION,
              hostInfo: { name: "picoagents-playground", version: "1.0.0" },
              hostCapabilities: { tools: {}, resources: {}, logging: {} },
              hostContext: { displayMode: "inline", theme: "dark" },
            });
          }
          return;

        case "ui/notifications/initialized":
          setReady(true);
          if (toolInput) {
            post({
              jsonrpc: "2.0",
              method: "ui/notifications/tool-input",
              params: { arguments: toolInput },
            });
          }
          return;

        case "ping":
          if (id !== undefined) respond(id, {});
          return;

        case "ui/notifications/size-changed":
          if (typeof params?.height === "number") {
            setHeight(Math.max(140, Math.min(640, Math.round(params.height))));
          }
          return;

        case "notifications/message":
          onLog?.(params?.level ?? "info", params?.text ?? "");
          return;

        case "ui/open-link":
          if (typeof params?.url === "string" && /^https?:\/\//.test(params.url)) {
            window.open(params.url, "_blank", "noopener,noreferrer");
          }
          if (id !== undefined) respond(id, {});
          return;

        case "tools/call": {
          if (id === undefined) return;
          try {
            const result = await mcpApiClient.callTool(
              serverId,
              params?.name,
              params?.arguments ?? {}
            );
            respond(id, {
              content: result.content,
              structuredContent: result.structured_content,
              isError: result.is_error,
            });
          } catch (e) {
            fail(id, -32000, e instanceof Error ? e.message : String(e));
          }
          return;
        }

        case "resources/read": {
          if (id === undefined) return;
          try {
            const app = await mcpApiClient.readApp(serverId, params?.uri);
            respond(id, {
              contents: [{ uri: app.uri, mimeType: "text/html", text: app.html }],
            });
          } catch (e) {
            fail(id, -32000, e instanceof Error ? e.message : String(e));
          }
          return;
        }

        default:
          // Unimplemented host methods must not hang a waiting app.
          if (id !== undefined) fail(id, -32601, `Host does not implement ${method}`);
      }
    };

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [serverId, toolInput, post, respond, fail, onLog]);

  // The app never completing the handshake is a real failure mode worth showing.
  useEffect(() => {
    const timer = setTimeout(() => {
      if (!ready) setError("App did not complete the ui/initialize handshake.");
    }, 5000);
    return () => clearTimeout(timer);
  }, [ready]);

  return (
    <div>
      <iframe
        ref={frameRef}
        title={`${toolName} app`}
        srcDoc={html}
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
        className="w-full rounded-md border bg-background"
        style={{ height }}
      />
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}
