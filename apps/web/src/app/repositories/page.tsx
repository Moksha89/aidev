import { AppShell } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { mockProjects, mockRepositories } from "@/lib/mocks";
import { GitBranch } from "lucide-react";

export default function RepositoriesPage() {
  return (
    <AppShell>
      <div className="container max-w-7xl py-8 space-y-6">
        <header className="flex items-end justify-between">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">Repositories</h1>
            <p className="text-sm text-muted-foreground">
              GitHub repositories connected to projects on this platform.
            </p>
          </div>
          <Button>Connect repository</Button>
        </header>

        <div className="grid gap-3">
          {mockRepositories.map((r) => {
            const project = mockProjects.find((p) => p.id === r.project_id);
            return (
              <Card key={r.id}>
                <CardHeader className="flex flex-row items-start gap-3">
                  <GitBranch className="h-5 w-5 mt-1 text-muted-foreground" />
                  <div className="flex-1">
                    <CardTitle>
                      {r.github_owner}/{r.github_name}
                    </CardTitle>
                    <p className="text-xs text-muted-foreground mt-1">
                      Project: {project?.name ?? "—"} · default branch:{" "}
                      <span className="font-mono">{r.default_branch}</span>
                    </p>
                  </div>
                </CardHeader>
                <CardContent>
                  <a
                    href={r.html_url}
                    className="text-sm text-primary underline-offset-4 hover:underline"
                  >
                    {r.html_url}
                  </a>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
}
