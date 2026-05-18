import { AppShell } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TaskRow } from "@/components/TaskRow";
import { mockProjects, mockRepositories, mockTasks } from "@/lib/mocks";
import { notFound } from "next/navigation";

export default function ProjectDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const project = mockProjects.find((p) => p.id === params.id);
  if (!project) notFound();

  const repos = mockRepositories.filter((r) => r.project_id === project.id);
  const tasks = mockTasks
    .filter((t) => t.project_id === project.id)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));

  return (
    <AppShell>
      <div className="container max-w-7xl py-8 space-y-6">
        <header className="space-y-1">
          <p className="text-xs font-mono text-muted-foreground">{project.slug}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{project.name}</h1>
          <p className="text-sm text-muted-foreground">{project.description}</p>
        </header>

        <section className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Repositories</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {repos.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No repositories connected yet.
                </p>
              )}
              {repos.map((r) => (
                <a
                  key={r.id}
                  href={r.html_url}
                  className="block text-sm font-mono hover:underline"
                >
                  {r.github_owner}/{r.github_name}
                </a>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Tasks</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {tasks.length === 0 && (
                <p className="text-sm text-muted-foreground">No tasks yet.</p>
              )}
              {tasks.map((t) => (
                <TaskRow key={t.id} task={t} />
              ))}
            </CardContent>
          </Card>
        </section>
      </div>
    </AppShell>
  );
}
