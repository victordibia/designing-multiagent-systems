/**
 * SessionSwitcher - Manage and switch between conversation sessions
 * Features: List sessions, create new, delete, switch active session
 */

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/badge";
import { MessageSquare, Plus, Trash2, Clock, ChevronDown } from "lucide-react";
import { apiClient } from "@/services/api";
import type { SessionInfo } from "@/types";

interface SessionSwitcherProps {
  entityId: string;
  entityType: "agent" | "orchestrator";
  currentSessionId?: string;
  onSessionChange: (sessionId: string | undefined) => void;
}

export function SessionSwitcher({
  entityId,
  entityType,
  currentSessionId,
  onSessionChange,
}: SessionSwitcherProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  const loadSessions = async () => {
    setIsLoading(true);
    try {
      const allSessions = await apiClient.getSessions(entityId);
      setSessions(allSessions);
    } catch (error) {
      console.error("Failed to load sessions:", error);
    } finally {
      setIsLoading(false);
    }
  };

  // Load sessions when dropdown opens OR when we have a currentSessionId
  useEffect(() => {
    if (isOpen || currentSessionId) {
      loadSessions();
    }
  }, [isOpen, entityId, currentSessionId]);

  const handleNewSession = async () => {
    try {
      // Create a new empty session on the backend
      const newSession = await apiClient.createSession(entityId, entityType);
      // Refresh session list
      await loadSessions();
      // Switch to the new session (use .id not .session_id)
      onSessionChange(newSession.id);
      setIsOpen(false);
    } catch (error) {
      console.error("Failed to create new session:", error);
      // Fallback: let frontend create session on next message
      onSessionChange(undefined);
      setIsOpen(false);
    }
  };

  const handleSelectSession = (sessionId: string) => {
    onSessionChange(sessionId);
    setIsOpen(false);
  };

  const handleDeleteSession = async (
    sessionId: string,
    e: React.MouseEvent
  ) => {
    e.stopPropagation();
    try {
      await apiClient.deleteSession(sessionId);
      setSessions(sessions.filter((s) => s.id !== sessionId));
      if (currentSessionId === sessionId) {
        onSessionChange(undefined);
      }
    } catch (error) {
      console.error("Failed to delete session:", error);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
    return date.toLocaleDateString();
  };

  const currentSession = sessions.find((s) => s.id === currentSessionId);

  return (
    <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className="gap-2">
          <MessageSquare className="h-4 w-4" />
          {currentSession ? (
            <span className="max-w-[150px] truncate">
              Conversation ({currentSession.message_count} msgs)
            </span>
          ) : (
            <span>New conversation</span>
          )}
          <ChevronDown className="h-4 w-4 opacity-50" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel className="flex items-center justify-between">
          <span>Conversations</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleNewSession}
            className="h-7 gap-1"
          >
            <Plus className="h-3 w-3" />
            New
          </Button>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        {isLoading ? (
          <div className="px-2 py-8 text-center text-sm text-muted-foreground">
            Loading sessions...
          </div>
        ) : sessions.length === 0 ? (
          <div className="px-2 py-8 text-center">
            <MessageSquare className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
            <div className="text-sm text-muted-foreground">
              No conversations yet
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              Start a conversation to create one
            </div>
          </div>
        ) : (
          <ScrollArea className="max-h-[300px]">
            {sessions.map((session) => (
              <DropdownMenuItem
                key={session.id}
                onClick={() => handleSelectSession(session.id)}
                className={`px-3 py-2 cursor-pointer ${
                  currentSessionId === session.id ? "bg-accent" : ""
                }`}
              >
                <div className="flex items-start justify-between w-full gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs px-1.5 py-0">
                        {session.message_count} msgs
                      </Badge>
                      {currentSessionId === session.id && (
                        <Badge variant="default" className="text-xs px-1.5 py-0">
                          Active
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-1 mt-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {formatDate(session.last_activity)}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5 truncate">
                      {session.id.slice(0, 8)}...
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => handleDeleteSession(session.id, e)}
                    className="h-7 w-7 p-0 hover:bg-destructive hover:text-destructive-foreground"
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </DropdownMenuItem>
            ))}
          </ScrollArea>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
