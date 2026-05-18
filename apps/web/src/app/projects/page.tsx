import { AppShell } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { mockProjects, mockTasks } from "@/lib/mocks";
import Link from "next/link";

export default function ProjectsPage() {
  return (
    <AppShell>
      <div className="container max-w-7xl py-8 space-y-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="text-sm text-muted-foreground">
            A project is a workspace that binds repositories, rules, and tasks.
          </p>
        </header>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {mockProjects.map((p) => {
            const latest =
              mockTasks
                .filter((t) => t.project_id === p.id)
                .sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0] ??
              null;
            return (
              <Link key={p.id} href={`/projects/${p.id}`}>
                <Card className="hover:bg-accent transition-colors h-full">
                  <CardHeader>
                    <CardTitle>{p.name}</CardTitle>
                    <p className="text-xs font-mono text-muted-foreground">
                      {p.slug}
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {p.description}
                    </p>
                    {latest && (
                      <p className="text-xs text-muted-foreground">
                        Last task: <span className="font-medium text-foreground">{latest.title}</span>
                      </p>
                    )}
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
}
