/**
 * Shared enums and types for the AI Developer platform.
 *
 * Mirror of `packages/shared/python/aidev_shared/enums.py`.
 * When you change one side, change the other.
 */

export const TaskPhase = {
  PENDING: "pending",
  PLANNING: "planning",
  FRONTEND_CODING: "frontend_coding",
  FRONTEND_QA: "frontend_qa",
  AWAITING_APPROVAL: "awaiting_approval",
  BACKEND_UNLOCKED: "backend_unlocked",
  BACKEND_CODING: "backend_coding",
  SECURITY_REVIEW: "security_review",
  PR_OPENED: "pr_opened",
  DONE: "done",
  REJECTED: "rejected",
  CANCELLED: "cancelled",
  BLOCKED: "blocked",
  FAILED: "failed",
} as const;

export type TaskPhase = (typeof TaskPhase)[keyof typeof TaskPhase];

export const AgentRole = {
  PLANNER: "planner",
  FRONTEND_DEVELOPER: "frontend_developer",
  BACKEND_DEVELOPER: "backend_developer",
  QA: "qa",
  SECURITY_REVIEWER: "security_reviewer",
} as const;

export type AgentRole = (typeof AgentRole)[keyof typeof AgentRole];

export const LogLevel = {
  DEBUG: "debug",
  INFO: "info",
  WARN: "warn",
  ERROR: "error",
} as const;

export type LogLevel = (typeof LogLevel)[keyof typeof LogLevel];

export const ApprovalDecision = {
  APPROVED: "approved",
  REJECTED: "rejected",
} as const;

export type ApprovalDecision =
  (typeof ApprovalDecision)[keyof typeof ApprovalDecision];

export const FRONTEND_PHASES: ReadonlySet<TaskPhase> = new Set([
  TaskPhase.PLANNING,
  TaskPhase.FRONTEND_CODING,
  TaskPhase.FRONTEND_QA,
  TaskPhase.AWAITING_APPROVAL,
]);

export const BACKEND_PHASES: ReadonlySet<TaskPhase> = new Set([
  TaskPhase.BACKEND_UNLOCKED,
  TaskPhase.BACKEND_CODING,
  TaskPhase.SECURITY_REVIEW,
  TaskPhase.PR_OPENED,
]);

export const TERMINAL_PHASES: ReadonlySet<TaskPhase> = new Set([
  TaskPhase.DONE,
  TaskPhase.REJECTED,
  TaskPhase.CANCELLED,
  TaskPhase.FAILED,
]);

export function isFrontendPhase(phase: TaskPhase): boolean {
  return FRONTEND_PHASES.has(phase);
}

export function isBackendPhase(phase: TaskPhase): boolean {
  return BACKEND_PHASES.has(phase);
}

export function isTerminal(phase: TaskPhase): boolean {
  return TERMINAL_PHASES.has(phase);
}

/** Human-friendly label for a phase. Keep short — used in chips/badges. */
export function taskPhaseLabel(phase: TaskPhase): string {
  switch (phase) {
    case TaskPhase.PENDING:
      return "Pending";
    case TaskPhase.PLANNING:
      return "Planning";
    case TaskPhase.FRONTEND_CODING:
      return "Frontend Coding";
    case TaskPhase.FRONTEND_QA:
      return "Frontend QA";
    case TaskPhase.AWAITING_APPROVAL:
      return "Awaiting Approval";
    case TaskPhase.BACKEND_UNLOCKED:
      return "Backend Unlocked";
    case TaskPhase.BACKEND_CODING:
      return "Backend Coding";
    case TaskPhase.SECURITY_REVIEW:
      return "Security Review";
    case TaskPhase.PR_OPENED:
      return "PR Opened";
    case TaskPhase.DONE:
      return "Done";
    case TaskPhase.REJECTED:
      return "Rejected";
    case TaskPhase.CANCELLED:
      return "Cancelled";
    case TaskPhase.BLOCKED:
      return "Blocked";
    case TaskPhase.FAILED:
      return "Failed";
  }
}
