import { AppShell } from "@/components/AppShell";
import { ActivityPanel } from "@/components/ActivityPanel";
import { ApprovalGate } from "@/components/ApprovalGate";
import { ChatPanel } from "@/components/ChatPanel";
import { PhaseBadge } from "@/components/PhaseBadge";
import { TaskTabs } from "@/components/TaskTabs";
import { TaskTimeline } from "@/components/TaskTimeline";
import {
  mockTaskFiles,
  mockTaskLogs,
  mockTaskMessages,
  mockTaskPreviews,
  mockTasks,
} from "@/lib/mocks";
import { notFound } from "next/navigation";

export default function TaskDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const task = mockTasks.find((t) => t.id === params.id);
  if (!task) notFound();

  const logs = mockTaskLogs[task.id] ?? [];
  const messages = mockTaskMessages[task.id] ?? [];
  const files = mockTaskFiles[task.id] ?? [];
  const previews = mockTaskPreviews[task.id] ?? [];

  return (
    <AppShell>
      <div className="container max-w-7xl py-6 space-y-6">
        <header className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <PhaseBadge phase={task.phase} />
            <h1 className="text-2xl font-semibold tracking-tight">
              {task.title}
            </h1>
          </div>
          <p className="text-sm text-muted-foreground max-w-prose">
            {task.instruction}
          </p>
          <TaskTimeline phase={task.phase} />
        </header>

        <ApprovalGate task={task} />

        <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
          <div className="space-y-6 min-w-0">
            <TaskTabs
              task={task}
              logs={logs}
              files={files}
              previews={previews}
            />
            <ChatPanel taskId={task.id} initialMessages={messages} />
          </div>
          <div>
            <ActivityPanel task={task} logs={logs} />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
