import { AppShell } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PhaseBadge } from "@/components/PhaseBadge";
import { TaskRow } from "@/components/TaskRow";
import Link from "next/link";
import { mockProjects, mockRepositories, mockTasks } from "@/lib/mocks";
import { TERMINAL_PHASES } from "@/lib/types";

export default function DashboardPage() {
  const active = mockTasks.filter((t) => !TERMINAL_PHASES.has(t.phase));
  const awaiting = active.filter((t) => t.phase === "awaiting_approval");
  const recent = [...mockTasks].sort((a, b) =>
    b.updated_at.localeCompare(a.updated_at),
  );

  return (
    <AppShell>
      <div className="container max-w-7xl py-8 space-y-8">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            {mockProjects.length} projects · {mockRepositories.length} repositories ·{" "}
            {active.length} active tasks · {awaiting.length} awaiting approval
          </p>
        </header>

        <section className="grid gap-4 md:grid-cols-3">
          <StatCard label="Projects" value={mockProjects.length} href="/projects" />
          <StatCard
            label="Repositories"
            value={mockRepositories.length}
            href="/repositories"
          />
          <StatCard
            label="Tasks awaiting approval"
            value={awaiting.length}
            href="/tasks"
            highlight={awaiting.length > 0}
          />
        </section>

        {awaiting.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-lg font-semibold">Awaiting your approval</h2>
            <div className="space-y-2">
              {awaiting.map((t) => (
                <TaskRow key={t.id} task={t} />
              ))}
            </div>
          </section>
        )}

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Recent tasks</h2>
            <Link
              href="/tasks"
              className="text-sm text-muted-foreground hover:underline"
            >
              View all →
            </Link>
          </div>
          <div className="space-y-2">
            {recent.map((t) => (
              <TaskRow key={t.id} task={t} />
            ))}
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Frontend-first reminder</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground space-y-2">
              <p>
                Agents can write to{" "}
                <code className="text-foreground">src/**</code>,{" "}
                <code className="text-foreground">app/**</code>,{" "}
                <code className="text-foreground">components/**</code>, and{" "}
                <code className="text-foreground">public/**</code> before
                approval.
              </p>
              <p>
                Backend paths (
                <code>apps/api/**</code>, <code>migrations/**</code>,{" "}
                <code>.env*</code>) are blocked by the rules engine until you
                approve a task here.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Phase indicators</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p className="text-muted-foreground">
                The colour-coded chip tells you exactly where each task is in
                the multi-agent pipeline.
              </p>
              <div className="flex flex-wrap gap-2">
                <PhaseBadge phase="planning" />
                <PhaseBadge phase="frontend_coding" />
                <PhaseBadge phase="awaiting_approval" />
                <PhaseBadge phase="backend_coding" />
                <PhaseBadge phase="pr_opened" />
                <PhaseBadge phase="done" />
              </div>
            </CardContent>
          </Card>
        </section>
      </div>
    </AppShell>
  );
}

function StatCard({
  label,
  value,
  href,
  highlight,
}: {
  label: string;
  value: number;
  href: string;
  highlight?: boolean;
}) {
  return (
    <Link href={href}>
      <Card
        className={
          "hover:bg-accent transition-colors " +
          (highlight ? "border-amber-400" : "")
        }
      >
        <CardContent className="p-6 space-y-2">
          <p className="text-xs uppercase tracking-wider text-muted-foreground">
            {label}
          </p>
          <p className="text-3xl font-semibold">{value}</p>
        </CardContent>
      </Card>
    </Link>
  );
}
