import { AppShell } from "@/components/AppShell";
import { ActivityPanel } from "@/components/ActivityPanel";
import { mockTaskLogs, mockTasks } from "@/lib/mocks";
import { notFound } from "next/navigation";

export default function TaskActivityPage({
  params,
}: {
  params: { id: string };
}) {
  const task = mockTasks.find((t) => t.id === params.id);
  if (!task) notFound();
  return (
    <AppShell>
      <div className="container max-w-2xl py-6">
        <ActivityPanel task={task} logs={mockTaskLogs[task.id] ?? []} />
      </div>
    </AppShell>
  );
}
