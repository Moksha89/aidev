import { AppShell } from "@/components/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { mockTaskLogs, mockTasks } from "@/lib/mocks";
import { notFound } from "next/navigation";

export default function TaskLogsPage({ params }: { params: { id: string } }) {
  const task = mockTasks.find((t) => t.id === params.id);
  if (!task) notFound();
  const logs = mockTaskLogs[task.id] ?? [];
  return (
    <AppShell>
      <div className="container max-w-5xl py-6 space-y-4">
        <h1 className="text-xl font-semibold">{task.title} — logs</h1>
        <Card>
          <CardContent className="p-4">
            <pre className="overflow-x-auto rounded-md bg-muted p-4 text-xs font-mono leading-6">
              {logs.length === 0
                ? "(no logs yet)"
                : logs
                    .map(
                      (l) =>
                        `#${l.sequence} [${l.level}] ${l.phase ?? "-"} ${l.agent_role ?? "-"}: ${l.message}`,
                    )
                    .join("\n")}
            </pre>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
