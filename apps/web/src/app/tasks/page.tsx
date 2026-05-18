import { AppShell } from "@/components/AppShell";
import { TaskRow } from "@/components/TaskRow";
import { Button } from "@/components/ui/button";
import { mockTasks } from "@/lib/mocks";
import { TERMINAL_PHASES } from "@/lib/types";

export default function TasksPage() {
  const active = mockTasks.filter((t) => !TERMINAL_PHASES.has(t.phase));
  const finished = mockTasks.filter((t) => TERMINAL_PHASES.has(t.phase));

  return (
    <AppShell>
      <div className="container max-w-7xl py-8 space-y-8">
        <header className="flex items-end justify-between">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">Tasks</h1>
            <p className="text-sm text-muted-foreground">
              Each task runs the Planner → Frontend → QA → (approval) →
              Backend → Security pipeline.
            </p>
          </div>
          <Button>New task</Button>
        </header>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Active ({active.length})
          </h2>
          {active.length === 0 ? (
            <p className="text-sm text-muted-foreground">No active tasks.</p>
          ) : (
            <div className="space-y-2">
              {active.map((t) => (
                <TaskRow key={t.id} task={t} />
              ))}
            </div>
          )}
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Finished ({finished.length})
          </h2>
          {finished.length === 0 ? (
            <p className="text-sm text-muted-foreground">No finished tasks.</p>
          ) : (
            <div className="space-y-2">
              {finished.map((t) => (
                <TaskRow key={t.id} task={t} />
              ))}
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
