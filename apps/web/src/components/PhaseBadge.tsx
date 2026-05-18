import { Badge, type BadgeVariant } from "@/components/ui/badge";
import {
  taskPhaseLabel,
  TERMINAL_PHASES,
  type TaskPhase,
} from "@/lib/types";

const VARIANTS: Partial<Record<TaskPhase, BadgeVariant>> = {
  pending: "secondary",
  planning: "secondary",
  frontend_coding: "default",
  frontend_qa: "default",
  awaiting_approval: "warn",
  backend_unlocked: "secondary",
  backend_coding: "default",
  security_review: "default",
  pr_opened: "success",
  done: "success",
  rejected: "danger",
  cancelled: "secondary",
  blocked: "danger",
  failed: "danger",
};

export function PhaseBadge({ phase }: { phase: TaskPhase }) {
  const variant = VARIANTS[phase] ?? "secondary";
  const label = taskPhaseLabel(phase);
  const dim = TERMINAL_PHASES.has(phase) ? "" : "animate-pulse";
  return (
    <Badge variant={variant} className={dim}>
      {label}
    </Badge>
  );
}
