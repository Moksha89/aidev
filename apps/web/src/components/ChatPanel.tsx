"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatRelative } from "@/lib/utils";
import type { AgentRole, TaskMessage } from "@/lib/types";
import { Send } from "lucide-react";
import { useState } from "react";

const AGENT_LABEL: Record<AgentRole, string> = {
  planner: "Planner",
  frontend_developer: "Frontend",
  backend_developer: "Backend",
  qa: "QA",
  security_reviewer: "Security",
};

export function ChatPanel({
  taskId,
  initialMessages,
}: {
  taskId: string;
  initialMessages: TaskMessage[];
}) {
  const [messages] = useState<TaskMessage[]>(initialMessages);
  const [draft, setDraft] = useState("");

  return (
    <Card className="flex flex-col h-full min-h-[480px]">
      <CardHeader>
        <CardTitle>Conversation</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col gap-3 overflow-y-auto">
        {messages.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No messages yet. Send an instruction below.
          </p>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
      </CardContent>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          // Wire to POST /tasks/{taskId}/message once the API is reachable.
          setDraft("");
        }}
        className="flex gap-2 border-t p-3"
        aria-label={`Send message in task ${taskId}`}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask the agents to refine or fix something…"
          className="h-10 flex-1 rounded-md border bg-background px-3 text-sm"
        />
        <Button type="submit" size="icon" aria-label="Send">
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </Card>
  );
}

function MessageBubble({ message }: { message: TaskMessage }) {
  const fromUser = message.role === "user";
  return (
    <div
      className={
        "flex flex-col gap-1 rounded-md border p-3 " +
        (fromUser ? "bg-accent" : "bg-card")
      }
    >
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {fromUser ? (
          <Badge variant="secondary">You</Badge>
        ) : message.agent_role ? (
          <Badge variant="default">{AGENT_LABEL[message.agent_role]}</Badge>
        ) : (
          <Badge variant="outline">System</Badge>
        )}
        <span>{formatRelative(message.created_at)}</span>
      </div>
      <p className="text-sm whitespace-pre-wrap leading-6">{message.content}</p>
    </div>
  );
}
