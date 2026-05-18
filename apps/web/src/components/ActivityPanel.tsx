import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PhaseBadge } from "@/components/PhaseBadge";
import { formatRelative } from "@/lib/utils";
import type { Task, TaskLog } from "@/lib/types";

export function ActivityPanel({
  task,
  logs,
}: {
  task: Task;
  logs: TaskLog[];
}) {
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>Activity</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-wider text-muted-foreground">
            Current phase
          </p>
          <div className="flex items-center gap-2">
            <PhaseBadge phase={task.phase} />
            {task.active_agent && (
              <span className="text-xs text-muted-foreground">
                {task.active_agent.replace("_", " ")}
              </span>
            )}
          </div>
        </div>

        <div className="space-y-1">
          <p className="text-xs uppercase tracking-wider text-muted-foreground">
            Branch
          </p>
          <p className="text-sm font-mono">
            {task.branch_name ?? "— not assigned —"}
          </p>
        </div>

        <div className="space-y-1">
          <p className="text-xs uppercase tracking-wider text-muted-foreground">
            Preview URL
          </p>
          {task.preview_url ? (
            <a
              href={task.preview_url}
              className="text-sm text-primary underline-offset-4 hover:underline break-all"
            >
              {task.preview_url}
            </a>
          ) : (
            <p className="text-sm text-muted-foreground">
              Generated when QA completes.
            </p>
          )}
        </div>

        <div className="space-y-1">
          <p className="text-xs uppercase tracking-wider text-muted-foreground">
            Pull request
          </p>
          {task.pr_url ? (
            <a
              href={task.pr_url}
              className="text-sm text-primary underline-offset-4 hover:underline break-all"
            >
              #{task.pr_number} · {task.pr_url}
            </a>
          ) : (
            <p className="text-sm text-muted-foreground">
              Opens after approval + security review.
            </p>
          )}
        </div>

        <div className="space-y-2">
          <p className="text-xs uppercase tracking-wider text-muted-foreground">
            Recent activity
          </p>
          <ol className="space-y-2 max-h-64 overflow-y-auto">
            {logs.length === 0 && (
              <li className="text-sm text-muted-foreground">No activity yet.</li>
            )}
            {logs.map((log) => (
              <li key={log.id} className="rounded-md border p-2 text-sm">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="font-mono">#{log.sequence}</span>
                  {log.phase && <PhaseBadge phase={log.phase} />}
                  <span className="ml-auto">{formatRelative(log.created_at)}</span>
                </div>
                <p className="mt-1 leading-6">{log.message}</p>
              </li>
            ))}
          </ol>
        </div>
      </CardContent>
    </Card>
  );
}
