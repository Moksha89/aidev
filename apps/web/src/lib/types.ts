/**
 * TypeScript mirror of the API's response shapes.
 *
 * The Python source-of-truth is `apps/api/app/schemas/*.py`. If you
 * change one of those, update the matching shape here.
 */

export type TaskPhase =
  | "pending"
  | "planning"
  | "frontend_coding"
  | "frontend_qa"
  | "awaiting_approval"
  | "backend_unlocked"
  | "backend_coding"
  | "security_review"
  | "pr_opened"
  | "done"
  | "rejected"
  | "cancelled"
  | "blocked"
  | "failed";

export type AgentRole =
  | "planner"
  | "frontend_developer"
  | "backend_developer"
  | "qa"
  | "security_reviewer";

export interface Project {
  id: string;
  name: string;
  slug: string;
  description: string;
  owner_id: string;
  default_model_server_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Repository {
  id: string;
  project_id: string;
  github_owner: string;
  github_name: string;
  default_branch: string;
  html_url: string;
  created_at: string;
  updated_at: string;
}

export type ExecutionMode = "mock" | "real";

export interface Task {
  id: string;
  project_id: string;
  repository_id: string | null;
  creator_id: string | null;
  title: string;
  instruction: string;
  phase: TaskPhase;
  active_agent: AgentRole | null;
  /**
   * v0.4: ``mock`` (in-process orchestrator with demo data) or ``real``
   * (Celery agent-runner + Docker sandbox + real GitHub PR). Set when
   * the task starts and used by the dashboard to label rows; the API
   * uses it to decide which branch of the approval / reject paths to
   * drive.
   */
  execution_mode: ExecutionMode;
  branch_name: string | null;
  preview_url: string | null;
  pr_url: string | null;
  pr_number: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Mirror of ``GET /settings/runtime``. Used by the runtime banner on
 * the dashboard topbar so the operator can see at a glance which
 * executor + pipeline are wired and whether GitHub credentials are
 * installed.
 *
 * Source of truth: ``apps/api/app/routes/settings.py::get_runtime_status``.
 */
export interface RuntimeStatus {
  sandbox_executor: "mock" | "docker";
  agent_pipeline: "mock" | "real";
  github_configured: boolean;
  github_mode: "token" | "app" | null;
  real_pipeline_active: boolean;
  model_base_url: string;
  model_name: string;
  env: "development" | "staging" | "production";
}

export interface TaskLog {
  id: string;
  task_id: string;
  level: "debug" | "info" | "warn" | "error";
  agent_role: AgentRole | null;
  phase: TaskPhase | null;
  message: string;
  sequence: number;
  created_at: string;
}

export interface TaskFile {
  id: string;
  task_id: string;
  path: string;
  status: "added" | "modified" | "deleted" | "renamed";
  lines_added: number;
  lines_removed: number;
  diff_snippet: string;
}

export interface TaskMessage {
  id: string;
  task_id: string;
  role: "user" | "assistant" | "system";
  agent_role: AgentRole | null;
  content: string;
  created_at: string;
}

export interface TaskPreview {
  id: string;
  task_id: string;
  viewport: string;
  width: number;
  height: number;
  image_url: string;
  route: string;
  notes: string;
  created_at: string;
}

export interface ModelServer {
  id: string;
  name: string;
  base_url: string;
  model_identifier: string;
  server_type: "ollama" | "vllm" | "openai" | "llamacpp" | "lmstudio";
  is_default: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface RuleSet {
  id: string;
  project_id: string;
  name: string;
  extra_forbidden_globs: string;
  extra_allowed_globs: string;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export const FRONTEND_PHASES: ReadonlySet<TaskPhase> = new Set<TaskPhase>([
  "frontend_coding",
  "frontend_qa",
]);

export const BACKEND_PHASES: ReadonlySet<TaskPhase> = new Set<TaskPhase>([
  "backend_unlocked",
  "backend_coding",
  "security_review",
]);

export const TERMINAL_PHASES: ReadonlySet<TaskPhase> = new Set<TaskPhase>([
  "done",
  "rejected",
  "cancelled",
  "failed",
]);

export function taskPhaseLabel(p: TaskPhase): string {
  switch (p) {
    case "pending":
      return "Pending";
    case "planning":
      return "Planning";
    case "frontend_coding":
      return "Frontend Coding";
    case "frontend_qa":
      return "Frontend QA";
    case "awaiting_approval":
      return "Awaiting Approval";
    case "backend_unlocked":
      return "Backend Unlocked";
    case "backend_coding":
      return "Backend Coding";
    case "security_review":
      return "Security Review";
    case "pr_opened":
      return "PR Opened";
    case "done":
      return "Done";
    case "rejected":
      return "Rejected";
    case "cancelled":
      return "Cancelled";
    case "blocked":
      return "Blocked";
    case "failed":
      return "Failed";
  }
}
