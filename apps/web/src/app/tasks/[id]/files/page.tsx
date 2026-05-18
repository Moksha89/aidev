import { AppShell } from "@/components/AppShell";
import { Card, CardContent } from "@/components/ui/card";
import { mockTaskFiles, mockTasks } from "@/lib/mocks";
import { notFound } from "next/navigation";

export default function TaskFilesPage({ params }: { params: { id: string } }) {
  const task = mockTasks.find((t) => t.id === params.id);
  if (!task) notFound();
  const files = mockTaskFiles[task.id] ?? [];
  return (
    <AppShell>
      <div className="container max-w-5xl py-6 space-y-4">
        <h1 className="text-xl font-semibold">{task.title} — files</h1>
        <Card>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="bg-muted text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-left px-4 py-2">Path</th>
                  <th className="text-right px-4 py-2">+</th>
                  <th className="text-right px-4 py-2">−</th>
                </tr>
              </thead>
              <tbody>
                {files.map((f) => (
                  <tr key={f.id} className="border-t">
                    <td className="px-4 py-2 font-mono uppercase text-xs">
                      {f.status}
                    </td>
                    <td className="px-4 py-2 font-mono break-all">{f.path}</td>
                    <td className="px-4 py-2 text-right text-emerald-600">
                      {f.lines_added}
                    </td>
                    <td className="px-4 py-2 text-right text-red-600">
                      {f.lines_removed}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
