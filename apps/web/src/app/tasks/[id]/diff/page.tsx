import { AppShell } from "@/components/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { mockTaskFiles, mockTasks } from "@/lib/mocks";
import { notFound } from "next/navigation";

export default function TaskDiffPage({ params }: { params: { id: string } }) {
  const task = mockTasks.find((t) => t.id === params.id);
  if (!task) notFound();
  const files = mockTaskFiles[task.id] ?? [];
  const diff = files
    .map(
      (f) =>
        `diff --git a/${f.path} b/${f.path}\n--- a/${f.path}\n+++ b/${f.path}\n${f.diff_snippet}`,
    )
    .join("\n");
  return (
    <AppShell>
      <div className="container max-w-5xl py-6 space-y-4">
        <h1 className="text-xl font-semibold">{task.title} — diff</h1>
        <Card>
          <CardContent className="p-4">
            <pre className="overflow-x-auto rounded-md bg-muted p-4 text-xs font-mono leading-6">
              {diff || "(no changes yet)"}
            </pre>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
