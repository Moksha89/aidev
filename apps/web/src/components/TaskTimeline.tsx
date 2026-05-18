import { cn } from "@/lib/utils";
import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import { taskPhaseLabel, type TaskPhase } from "@/lib/types";

const PHASES: TaskPhase[] = [
  "planning",
  "frontend_coding",
  "frontend_qa",
  "awaiting_approval",
  "backend_coding",
  "security_review",
  "pr_opened",
  "done",
];

export function TaskTimeline({ phase }: { phase: TaskPhase }) {
  const reachedIndex = PHASES.indexOf(phase);
  const isFailed = phase === "rejected" || phase === "cancelled" || phase === "failed";

  return (
    <ol className="grid gap-1 sm:grid-cols-2 lg:grid-cols-4">
      {PHASES.map((p, i) => {
        const status =
          isFailed && i >= reachedIndex
            ? "skipped"
            : i < reachedIndex
              ? "done"
              : i === reachedIndex
                ? "current"
                : "todo";
        return (
          <li
            key={p}
            className={cn(
              "flex items-center gap-2 rounded-md border px-3 py-2",
              status === "current" && "border-primary bg-accent",
              status === "skipped" && "opacity-50",
            )}
          >
            {status === "done" && (
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            )}
            {status === "current" && (
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
            )}
            {status === "todo" && <Circle className="h-4 w-4 text-muted-foreground" />}
            {status === "skipped" && (
              <XCircle className="h-4 w-4 text-destructive" />
            )}
            <span className="text-sm">{taskPhaseLabel(p)}</span>
          </li>
        );
      })}
    </ol>
  );
}
