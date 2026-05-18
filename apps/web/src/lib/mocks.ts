/**
 * Typed mock data used by the dashboard before the backend is up.
 *
 * Once the FastAPI backend is running, components should fetch real
 * data via `lib/api.ts`. These mocks keep the dashboard demonstrable
 * for screenshots and pre-PR previews.
 */

import type {
  ModelServer,
  Project,
  Repository,
  Task,
  TaskFile,
  TaskLog,
  TaskMessage,
  TaskPreview,
} from "./types";

export const mockProjects: Project[] = [
  {
    id: "p_001",
    name: "AI Developer Platform",
    slug: "aidev-platform",
    description: "The platform that's looking at itself in the mirror.",
    owner_id: "u_001",
    default_model_server_id: "m_default",
    created_at: "2026-05-17T10:00:00Z",
    updated_at: "2026-05-18T01:00:00Z",
  },
  {
    id: "p_002",
    name: "Cricket Casino Lobby",
    slug: "cricsino",
    description: "Frontend redesign of the lobby + dashboard.",
    owner_id: "u_001",
    default_model_server_id: "m_default",
    created_at: "2026-05-12T15:30:00Z",
    updated_at: "2026-05-17T11:20:00Z",
  },
];

export const mockRepositories: Repository[] = [
  {
    id: "r_001",
    project_id: "p_001",
    github_owner: "Moksha89",
    github_name: "aidev",
    default_branch: "main",
    html_url: "https://github.com/Moksha89/aidev",
    created_at: "2026-05-17T10:00:00Z",
    updated_at: "2026-05-17T10:00:00Z",
  },
  {
    id: "r_002",
    project_id: "p_002",
    github_owner: "Moksha89",
    github_name: "cricsino",
    default_branch: "main",
    html_url: "https://github.com/Moksha89/cricsino",
    created_at: "2026-05-12T15:30:00Z",
    updated_at: "2026-05-12T15:30:00Z",
  },
];

export const mockTasks: Task[] = [
  {
    id: "t_demo_001",
    project_id: "p_001",
    repository_id: "r_001",
    creator_id: "u_001",
    title: "Build the projects dashboard cards",
    instruction:
      "Create a card grid on /projects showing each project's name, slug, " +
      "and last-touched task. Match the design system in .ai-rules/ui-theme.md.",
    phase: "awaiting_approval",
    active_agent: null,
    branch_name: "aidev/task-demo_001",
    preview_url: "https://task-demo_001.preview.aidev.local",
    pr_url: null,
    pr_number: null,
    error_message: null,
    created_at: "2026-05-17T18:00:00Z",
    updated_at: "2026-05-18T01:10:00Z",
  },
  {
    id: "t_demo_002",
    project_id: "p_001",
    repository_id: "r_001",
    creator_id: "u_001",
    title: "Wire the /tasks/:id/diff tab",
    instruction:
      "Fetch GET /tasks/:id/diff and render it with syntax highlighting.",
    phase: "frontend_coding",
    active_agent: "frontend_developer",
    branch_name: "aidev/task-demo_002",
    preview_url: null,
    pr_url: null,
    pr_number: null,
    error_message: null,
    created_at: "2026-05-18T00:00:00Z",
    updated_at: "2026-05-18T01:30:00Z",
  },
  {
    id: "t_demo_003",
    project_id: "p_002",
    repository_id: "r_002",
    creator_id: "u_001",
    title: "Polish lobby tile hover states",
    instruction: "Add the new gradient and shadow tokens from the design ticket.",
    phase: "done",
    active_agent: null,
    branch_name: "aidev/task-demo_003",
    preview_url: null,
    pr_url: "https://github.com/Moksha89/cricsino/pull/42",
    pr_number: 42,
    error_message: null,
    created_at: "2026-05-15T12:00:00Z",
    updated_at: "2026-05-15T16:00:00Z",
  },
];

export const mockTaskLogs: Record<string, TaskLog[]> = {
  t_demo_001: [
    {
      id: "l_1",
      task_id: "t_demo_001",
      level: "info",
      agent_role: "planner",
      phase: "planning",
      message: "Decomposed instruction into a 3-step plan.",
      sequence: 0,
      created_at: "2026-05-17T18:00:05Z",
    },
    {
      id: "l_2",
      task_id: "t_demo_001",
      level: "info",
      agent_role: "frontend_developer",
      phase: "frontend_coding",
      message: "Created ProjectCard.tsx, ProjectGrid.tsx, and updated /projects.",
      sequence: 1,
      created_at: "2026-05-17T18:02:00Z",
    },
    {
      id: "l_3",
      task_id: "t_demo_001",
      level: "info",
      agent_role: "qa",
      phase: "frontend_qa",
      message: "Build OK. Playwright: 5 viewports captured.",
      sequence: 2,
      created_at: "2026-05-17T18:05:30Z",
    },
    {
      id: "l_4",
      task_id: "t_demo_001",
      level: "warn",
      agent_role: null,
      phase: "awaiting_approval",
      message: "Awaiting human approval before any backend work.",
      sequence: 3,
      created_at: "2026-05-17T18:05:31Z",
    },
  ],
};

export const mockTaskMessages: Record<string, TaskMessage[]> = {
  t_demo_001: [
    {
      id: "m_1",
      task_id: "t_demo_001",
      role: "user",
      agent_role: null,
      content:
        "Create a card grid on /projects showing each project's name, slug, " +
        "and last-touched task.",
      created_at: "2026-05-17T18:00:00Z",
    },
    {
      id: "m_2",
      task_id: "t_demo_001",
      role: "assistant",
      agent_role: "planner",
      content:
        "I'll break this into three steps: (1) scaffold the page route, " +
        "(2) build ProjectCard + ProjectGrid, (3) run Playwright at five viewports.",
      created_at: "2026-05-17T18:00:10Z",
    },
    {
      id: "m_3",
      task_id: "t_demo_001",
      role: "assistant",
      agent_role: "frontend_developer",
      content:
        "Added ProjectCard.tsx, ProjectGrid.tsx, and updated /projects. " +
        "Lint and type-check are clean. Handing off to QA.",
      created_at: "2026-05-17T18:02:00Z",
    },
    {
      id: "m_4",
      task_id: "t_demo_001",
      role: "assistant",
      agent_role: "qa",
      content:
        "Build succeeded. Screenshots saved at mobile-375, mobile-430, " +
        "tablet-768, desktop-1280, desktop-1920. Preview URL is live.",
      created_at: "2026-05-17T18:05:30Z",
    },
  ],
};

export const mockTaskFiles: Record<string, TaskFile[]> = {
  t_demo_001: [
    {
      id: "f_1",
      task_id: "t_demo_001",
      path: "apps/web/src/app/projects/page.tsx",
      status: "modified",
      lines_added: 24,
      lines_removed: 4,
      diff_snippet:
        "@@ apps/web/src/app/projects/page.tsx @@\n+ import { ProjectGrid } from \"@/components/projects/ProjectGrid\";\n",
    },
    {
      id: "f_2",
      task_id: "t_demo_001",
      path: "apps/web/src/components/projects/ProjectCard.tsx",
      status: "added",
      lines_added: 86,
      lines_removed: 0,
      diff_snippet:
        "@@ apps/web/src/components/projects/ProjectCard.tsx @@\n+ export function ProjectCard(...) { ... }\n",
    },
    {
      id: "f_3",
      task_id: "t_demo_001",
      path: "apps/web/src/components/projects/ProjectGrid.tsx",
      status: "added",
      lines_added: 42,
      lines_removed: 0,
      diff_snippet:
        "@@ apps/web/src/components/projects/ProjectGrid.tsx @@\n+ export function ProjectGrid(...) { ... }\n",
    },
  ],
};

export const mockTaskPreviews: Record<string, TaskPreview[]> = {
  t_demo_001: [
    {
      id: "pv_1",
      task_id: "t_demo_001",
      viewport: "mobile-375",
      width: 375,
      height: 812,
      image_url: "/screenshots/t_demo_001/mobile-375.svg",
      route: "/projects",
      notes: "iPhone SE / Pixel 4a",
      created_at: "2026-05-17T18:05:00Z",
    },
    {
      id: "pv_2",
      task_id: "t_demo_001",
      viewport: "mobile-430",
      width: 430,
      height: 932,
      image_url: "/screenshots/t_demo_001/mobile-430.svg",
      route: "/projects",
      notes: "iPhone 15 Pro Max",
      created_at: "2026-05-17T18:05:00Z",
    },
    {
      id: "pv_3",
      task_id: "t_demo_001",
      viewport: "tablet-768",
      width: 768,
      height: 1024,
      image_url: "/screenshots/t_demo_001/tablet-768.svg",
      route: "/projects",
      notes: "iPad Mini",
      created_at: "2026-05-17T18:05:00Z",
    },
    {
      id: "pv_4",
      task_id: "t_demo_001",
      viewport: "desktop-1280",
      width: 1280,
      height: 800,
      image_url: "/screenshots/t_demo_001/desktop-1280.svg",
      route: "/projects",
      notes: "Macbook 13\"",
      created_at: "2026-05-17T18:05:00Z",
    },
    {
      id: "pv_5",
      task_id: "t_demo_001",
      viewport: "desktop-1920",
      width: 1920,
      height: 1080,
      image_url: "/screenshots/t_demo_001/desktop-1920.svg",
      route: "/projects",
      notes: "1080p monitor",
      created_at: "2026-05-17T18:05:00Z",
    },
  ],
};

export const mockModelServers: ModelServer[] = [
  {
    id: "m_default",
    name: "Local Ollama",
    base_url: "http://host.docker.internal:11434/v1",
    model_identifier: "llama3.1:8b-instruct",
    server_type: "ollama",
    is_default: true,
    is_active: true,
    created_at: "2026-05-17T09:50:00Z",
    updated_at: "2026-05-17T09:50:00Z",
  },
  {
    id: "m_vllm",
    name: "GPU vLLM (Ubuntu VPS)",
    base_url: "http://gpu-vps.internal:8000/v1",
    model_identifier: "Qwen/Qwen2.5-Coder-32B-Instruct",
    server_type: "vllm",
    is_default: false,
    is_active: true,
    created_at: "2026-05-17T09:50:00Z",
    updated_at: "2026-05-17T09:50:00Z",
  },
];
