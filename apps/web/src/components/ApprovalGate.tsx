"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, ShieldAlert } from "lucide-react";
import type { Task } from "@/lib/types";
import { useState } from "react";

export function ApprovalGate({ task }: { task: Task }) {
  const [reason, setReason] = useState("");

  if (task.phase !== "awaiting_approval") {
    return null;
  }

  return (
    <Card className="border-amber-400">
      <CardHeader className="flex flex-row items-start gap-3">
        <ShieldAlert className="h-5 w-5 text-amber-500 mt-1" />
        <div className="flex-1">
          <CardTitle>Frontend complete — approve to unlock backend</CardTitle>
          <p className="text-sm text-muted-foreground mt-1">
            Review the preview, diff, and screenshots. Backend changes are
            blocked at the filesystem level until you click Approve.
          </p>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={2}
          placeholder="Optional note for the audit log…"
          className="w-full rounded-md border bg-background p-3 text-sm"
        />
        <div className="flex gap-2">
          <Button
            type="button"
            onClick={() => {
              // POST /tasks/{task.id}/approve-frontend
              // Wired in v0.2; kept inert here to avoid pretending.
            }}
          >
            <CheckCircle2 className="h-4 w-4 mr-2" />
            Approve frontend
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={() => {
              // POST /tasks/{task.id}/reject
            }}
          >
            Reject
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Decision is recorded in <code>task_approvals</code> with your user ID,
          IP, and user agent.
        </p>
      </CardContent>
    </Card>
  );
}
