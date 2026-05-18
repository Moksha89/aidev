import { AppShell } from "@/components/AppShell";
import { ChatPanel } from "@/components/ChatPanel";
import { mockTaskMessages, mockTasks } from "@/lib/mocks";
import { notFound } from "next/navigation";

export default function TaskChatPage({ params }: { params: { id: string } }) {
  const task = mockTasks.find((t) => t.id === params.id);
  if (!task) notFound();
  return (
    <AppShell>
      <div className="container max-w-3xl py-6">
        <h1 className="text-xl font-semibold mb-4">{task.title} — chat</h1>
        <ChatPanel
          taskId={task.id}
          initialMessages={mockTaskMessages[task.id] ?? []}
        />
      </div>
    </AppShell>
  );
}
