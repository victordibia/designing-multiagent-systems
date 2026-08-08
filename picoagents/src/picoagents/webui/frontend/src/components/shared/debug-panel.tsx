/**
 * DebugPanel - Real-time debug information for PicoAgents
 * Features: Stream events, session info, execution traces
 */

import { useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  Bug,
  MessageSquare,
  Activity,
  Clock,
  AlertCircle,
  CheckCircle,
  Info,
  ChevronDown,
  ChevronRight,
  Users,
  UserPlus,
  Play,
  Pause,
} from "lucide-react";
import type { StreamEvent } from "@/types";

interface DebugPanelProps {
  events: StreamEvent[];
  isStreaming?: boolean;
}

const getEventIcon = (eventType: string) => {
  switch (eventType) {
    case "message":
      return <MessageSquare className="h-4 w-4" />;
    case "token_chunk":
      return <MessageSquare className="h-4 w-4 text-info" />;
    case "tool_call":
      return <Activity className="h-4 w-4" />;
    case "tool_approval":
      return <AlertCircle className="h-4 w-4 text-warning" />;
    case "error":
      return <AlertCircle className="h-4 w-4 text-destructive" />;
    case "complete":
      return <CheckCircle className="h-4 w-4 text-success" />;
    case "workflow_started":
    case "workflow_completed":
      return <Activity className="h-4 w-4 text-info" />;
    // Orchestration events
    case "orchestration_start":
      return <Users className="h-4 w-4 text-info" />;
    case "orchestration_complete":
      return <CheckCircle className="h-4 w-4 text-info" />;
    case "agent_selection":
      return <UserPlus className="h-4 w-4 text-info" />;
    case "agent_execution_start":
      return <Play className="h-4 w-4 text-info" />;
    case "agent_execution_complete":
      return <Pause className="h-4 w-4 text-info" />;
    default:
      return <Info className="h-4 w-4" />;
  }
};

const getEventBadgeVariant = (eventType: string) => {
  switch (eventType) {
    case "error":
      return "destructive" as const;
    case "tool_approval":
      return "default" as const;
    case "complete":
    case "workflow_completed":
    case "orchestration_complete":
    case "agent_execution_complete":
      return "default" as const;
    case "message":
    case "token_chunk":
    case "tool_call":
      return "secondary" as const;
    case "orchestration_start":
    case "agent_selection":
    case "agent_execution_start":
      return "outline" as const;
    default:
      return "outline" as const;
  }
};

// Helper to format orchestration event details
const getOrchestrationEventDetail = (event: StreamEvent): string | null => {
  const data = event.data as any;

  switch (event.type) {
    case "orchestration_start":
      return data?.pattern ? `Pattern: ${data.pattern}` : null;
    case "agent_selection":
      return data?.selected_agent
        ? `Selected: ${data.selected_agent}${data.selection_reason ? ` (${data.selection_reason})` : ''}`
        : null;
    case "agent_execution_start":
      return data?.executing_agent
        ? `${data.executing_agent}${data.context_size ? ` - ${data.context_size} messages` : ''}`
        : null;
    case "agent_execution_complete":
      return data?.executing_agent
        ? `${data.executing_agent}${data.message_count ? ` - added ${data.message_count} messages` : ''}`
        : null;
    case "orchestration_complete":
      return data?.stop_reason ? `Reason: ${data.stop_reason}` : null;
    default:
      return null;
  }
};

function EventItem({ event }: { event: StreamEvent }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const orchestrationDetail = getOrchestrationEventDetail(event);

  return (
    <div className="bg-card border rounded-md p-2">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          {getEventIcon(event.type)}
          <span className="text-sm font-medium">{event.type}</span>
          <Badge variant={getEventBadgeVariant(event.type)} className="text-xs px-1.5 py-0.5 h-5">
            {event.type}
          </Badge>
        </div>
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          {new Date(event.timestamp).toLocaleTimeString()}
        </div>
      </div>

      {/* Show orchestration event detail prominently */}
      {orchestrationDetail && (
        <div className="text-xs text-foreground font-medium mt-1">
          {orchestrationDetail}
        </div>
      )}

      {event.data && (
        <div className="mt-1">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            {isExpanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
            {isExpanded ? "Hide" : "Show"} data
          </button>
          {isExpanded && (
            <div className="mt-1 space-y-2">
              {event.session_id && (
                <div className="text-xs text-muted-foreground">
                  Session: {event.session_id}
                </div>
              )}
              <ScrollArea className="h-20">
                <pre className="text-xs bg-muted p-2 rounded overflow-auto">
                  {JSON.stringify(event.data, null, 2)}
                </pre>
              </ScrollArea>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function EventsSummary({ events }: { events: StreamEvent[] }) {
  const eventCounts = events.reduce((acc, event) => {
    acc[event.type] = (acc[event.type] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className="grid grid-cols-2 gap-2 mb-4">
      {Object.entries(eventCounts).map(([type, count]) => (
        <div key={type} className="bg-card border rounded-md p-2">
          <div className="flex items-center gap-2">
            {getEventIcon(type)}
            <div>
              <div className="text-sm font-medium">{count}</div>
              <div className="text-xs text-muted-foreground">{type}</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function DebugPanel({ events, isStreaming }: DebugPanelProps) {
  const recentEvents = events.slice(-50); // Keep only last 50 events for performance

  return (
    <div className="h-full flex flex-col border-l bg-background">
      <div className="p-4 border-b">
        <div className="flex items-center gap-2">
          <Bug className="h-5 w-5" />
          <h3 className="text-sm font-semibold">Debug Panel</h3>
          {isStreaming && (
            <Badge variant="secondary" className="gap-1">
              <div className="h-2 w-2 bg-success rounded-full animate-pulse" />
              Live
            </Badge>
          )}
        </div>
        <div className="text-xs text-muted-foreground mt-1">
          {events.length} events total
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-hidden flex flex-col px-4">
        <Tabs defaultValue="events" className="flex-1 flex flex-col min-h-0">
          <TabsList className="grid w-full grid-cols-2 mt-4 mb-2 flex-shrink-0">
            <TabsTrigger value="events">Events</TabsTrigger>
            <TabsTrigger value="summary">Summary</TabsTrigger>
          </TabsList>

          <TabsContent value="events" className="flex-1 min-h-0 mb-4 overflow-hidden data-[state=active]:flex data-[state=inactive]:hidden">
            <ScrollArea className="h-full w-full">
              {recentEvents.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-32 text-center">
                  <Bug className="h-8 w-8 text-muted-foreground mb-2" />
                  <div className="text-sm text-muted-foreground">
                    No debug events yet
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Events will appear here during execution
                  </div>
                </div>
              ) : (
                <div className="space-y-1">
                  {recentEvents.map((event, index) => (
                    <EventItem key={index} event={event} />
                  ))}
                </div>
              )}
            </ScrollArea>
          </TabsContent>

          <TabsContent value="summary" className="flex-1 min-h-0 mb-4 overflow-hidden data-[state=active]:flex data-[state=inactive]:hidden">
            <ScrollArea className="h-full w-full">
              {events.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-32 text-center">
                  <Activity className="h-8 w-8 text-muted-foreground mb-2" />
                  <div className="text-sm text-muted-foreground">
                    No events to summarize
                  </div>
                </div>
              ) : (
                <EventsSummary events={events} />
              )}
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}