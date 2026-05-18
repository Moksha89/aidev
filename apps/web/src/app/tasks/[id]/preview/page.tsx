import { AppShell } from "@/components/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { mockTasks } from "@/lib/mocks";
import { notFound } from "next/navigation";

export default function TaskPreviewPage({
  params,
}: {
  params: { id: string };
}) {
  const task = mockTasks.find((t) => t.id === params.id);
  if (!task) notFound();
  return (
    <AppShell>
      <div className="container max-w-7xl py-6 space-y-4">
        <h1 className="text-xl font-semibold">{task.title} — preview</h1>
        {task.preview_url ? (
          <Card>
            <CardContent className="p-0 overflow-hidden">
              <iframe
                src={task.preview_url}
                title={`Preview for ${task.title}`}
                className="w-full h-[800px]"
              />
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="py-16 text-center text-sm text-muted-foreground">
              The preview URL is generated when the QA agent completes the
              frontend build inside the sandbox.
            </CardContent>
          </Card>
        )}
      </div>
    </AppShell>
  );
}
