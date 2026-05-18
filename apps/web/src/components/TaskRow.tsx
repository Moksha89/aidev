import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { PhaseBadge } from "@/components/PhaseBadge";
import { formatRelative } from "@/lib/utils";
import type { Task } from "@/lib/types";

export function TaskRow({ task }: { task: Task }) {
  return (
    <Link href={`/tasks/${task.id}`}>
      <Card className="hover:bg-accent transition-colors">
        <CardContent className="flex items-center gap-4 p-4">
          <div className="flex-1 min-w-0">
            <p className="font-medium truncate">{task.title}</p>
            <p className="text-sm text-muted-foreground truncate">
              {task.instruction}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <PhaseBadge phase={task.phase} />
            <span className="text-xs text-muted-foreground">
              {formatRelative(task.updated_at)}
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
