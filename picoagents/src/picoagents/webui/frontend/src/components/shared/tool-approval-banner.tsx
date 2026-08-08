/**
 * ToolApprovalBanner - Inline banner for approving/rejecting tool calls
 * Appears above the message input for a non-intrusive approval flow
 */

import { useState } from "react";
import { AlertCircle, CheckCircle, XCircle, Wrench, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { ToolApprovalRequest, ToolApprovalResponse } from "@/types";

interface ToolApprovalBannerProps {
  request: ToolApprovalRequest | null;
  onApprove: (response: ToolApprovalResponse) => void;
  onReject: (response: ToolApprovalResponse) => void;
}

export function ToolApprovalBanner({
  request,
  onApprove,
  onReject,
}: ToolApprovalBannerProps) {
  const [reason, setReason] = useState("");
  const [showDetails, setShowDetails] = useState(false);

  if (!request) return null;

  const handleApprove = (e: React.MouseEvent) => {
    e.preventDefault();
    const approvalResponse = {
      request_id: request.request_id,
      tool_call_id: request.tool_call_id,
      approved: true,
      reason: reason || undefined,
    };
    console.log("✅ Approval response created:", approvalResponse);
    onApprove(approvalResponse);
    setReason("");
    setShowDetails(false);
  };

  const handleReject = (e: React.MouseEvent) => {
    e.preventDefault();
    onReject({
      request_id: request.request_id,
      tool_call_id: request.tool_call_id,
      approved: false,
      reason: reason || "User rejected",
    });
    setReason("");
    setShowDetails(false);
  };

  return (
    <div className="border-t border-warning/40 bg-warning/10 animate-in slide-in-from-bottom-4 duration-300">
      <div className="p-3 space-y-3">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2 flex-1 min-w-0">
            <AlertCircle className="h-5 w-5 text-warning shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-sm">Approval Required:</span>
                <Badge variant="secondary" className="text-xs">
                  <Wrench className="h-3 w-3 mr-1" />
                  {request.tool_name}
                </Badge>
              </div>
              {request.reason && (
                <p className="text-sm text-muted-foreground mt-1">
                  {request.reason}
                </p>
              )}
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex gap-2 shrink-0">
            <Button
              size="sm"
              variant="default"
              onClick={handleApprove}
              className="gap-1.5"
            >
              <CheckCircle className="h-3.5 w-3.5" />
              Approve
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={handleReject}
              className="gap-1.5"
            >
              <XCircle className="h-3.5 w-3.5" />
              Reject
            </Button>
          </div>
        </div>

        {/* Expandable details */}
        <div className="space-y-2">
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {showDetails ? (
              <ChevronUp className="h-3.5 w-3.5" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
            {showDetails ? "Hide" : "Show"} parameters
          </button>

          {showDetails && (
            <div className="space-y-2">
              {/* Parameters */}
              <div className="bg-background rounded-md p-2 border">
                <div className="text-xs font-medium mb-1.5">Parameters:</div>
                <pre className="text-xs font-mono overflow-x-auto">
                  {JSON.stringify(request.parameters, null, 2)}
                </pre>
              </div>

              {/* Optional reason input */}
              <div className="space-y-1.5">
                <label className="text-xs font-medium">
                  Note (optional):
                </label>
                <textarea
                  className="w-full min-h-[50px] px-2 py-1.5 text-xs border rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="Add a note about your decision..."
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
