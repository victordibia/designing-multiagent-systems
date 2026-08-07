/**
 * InputBanner - MRTR mid-call input prompt.
 *
 * When a server answers a tool call with input_required, the parked request
 * surfaces here; submitting resumes the call. Mirrors the tool-approval
 * banner pattern used in agent chat.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MessageCircleQuestion } from "lucide-react";
import type { McpPendingInput } from "@/types/mcp";

interface InputBannerProps {
  pending: McpPendingInput;
  onReply: (inputId: string, action: string, content: Record<string, any> | null) => void;
}

export function InputBanner({ pending, onReply }: InputBannerProps) {
  const properties: Record<string, any> =
    pending.requested_schema?.properties ?? {};
  const fieldNames = Object.keys(properties);
  const [values, setValues] = useState<Record<string, any>>({});

  const isSimpleConfirm =
    fieldNames.length === 1 && properties[fieldNames[0]]?.type === "boolean";

  const submit = (content: Record<string, any>) =>
    onReply(pending.input_id, "accept", content);

  return (
    <div className="border border-amber-400/60 bg-amber-50 dark:bg-amber-950/30 rounded-md p-3 space-y-2">
      <div className="flex items-start gap-2">
        <MessageCircleQuestion className="h-4 w-4 mt-0.5 shrink-0 text-amber-600" />
        <div className="text-sm">
          <span className="font-medium">{pending.server_id}</span> is asking:{" "}
          {pending.message}
        </div>
      </div>

      {isSimpleConfirm ? (
        <div className="flex gap-2 justify-end">
          <Button
            size="sm"
            variant="outline"
            onClick={() => submit({ [fieldNames[0]]: false })}
          >
            No
          </Button>
          <Button size="sm" onClick={() => submit({ [fieldNames[0]]: true })}>
            Yes
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          {fieldNames.map((name) => (
            <div key={name} className="flex items-center gap-2">
              <label className="text-xs font-mono w-32 truncate">{name}</label>
              <Input
                className="h-7 text-xs"
                placeholder={properties[name]?.description || properties[name]?.type}
                value={values[name] ?? ""}
                onChange={(e) =>
                  setValues((prev) => ({ ...prev, [name]: e.target.value }))
                }
              />
            </div>
          ))}
          <div className="flex gap-2 justify-end">
            <Button
              size="sm"
              variant="outline"
              onClick={() => onReply(pending.input_id, "decline", null)}
            >
              Decline
            </Button>
            <Button size="sm" onClick={() => submit(values)}>
              Submit
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
