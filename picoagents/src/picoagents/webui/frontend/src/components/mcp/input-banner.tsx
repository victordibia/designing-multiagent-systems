/**
 * InputBanner - MRTR mid-call input prompt.
 *
 * When a server answers a tool call with input_required, the parked request
 * surfaces here; submitting resumes the call.
 */

import { useState } from "react";
import { MessageCircleQuestion } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { McpPendingInput } from "@/types/mcp";

interface InputBannerProps {
  pending: McpPendingInput;
  onReply: (inputId: string, action: string, content: Record<string, any> | null) => void;
}

export function InputBanner({ pending, onReply }: InputBannerProps) {
  const properties: Record<string, any> = pending.requested_schema?.properties ?? {};
  const fieldNames = Object.keys(properties);
  const [values, setValues] = useState<Record<string, any>>({});

  const isSimpleConfirm =
    fieldNames.length === 1 && properties[fieldNames[0]]?.type === "boolean";

  const submit = (content: Record<string, any>) =>
    onReply(pending.input_id, "accept", content);

  return (
    <Alert variant="warning">
      <MessageCircleQuestion />
      <AlertTitle>
        <span className="font-mono">{pending.server_id}</span> is asking for input
      </AlertTitle>
      <AlertDescription>
        <p>{pending.message}</p>
        {isSimpleConfirm ? (
          <div className="mt-2 flex justify-end gap-2">
            <Button size="sm" variant="outline" onClick={() => submit({ [fieldNames[0]]: false })}>
              No
            </Button>
            <Button size="sm" onClick={() => submit({ [fieldNames[0]]: true })}>
              Yes
            </Button>
          </div>
        ) : (
          <div className="mt-2 space-y-2">
            {fieldNames.map((name) => (
              <div key={name} className="flex items-center gap-2">
                <label className="w-32 truncate font-mono text-xs">{name}</label>
                <Input
                  className="h-7 text-xs"
                  placeholder={properties[name]?.description || properties[name]?.type}
                  value={values[name] ?? ""}
                  onChange={(e) => setValues((prev) => ({ ...prev, [name]: e.target.value }))}
                />
              </div>
            ))}
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => onReply(pending.input_id, "decline", null)}>
                Decline
              </Button>
              <Button size="sm" onClick={() => submit(values)}>
                Submit
              </Button>
            </div>
          </div>
        )}
      </AlertDescription>
    </Alert>
  );
}
