import Link from "next/link";

export default function Home() {
  return (
    <div className="container max-w-3xl py-16 space-y-8">
      <div className="space-y-2">
        <p className="text-sm font-medium text-muted-foreground">AI Developer</p>
        <h1 className="text-4xl font-semibold tracking-tight">
          Self-hosted AI developer platform.
        </h1>
        <p className="text-muted-foreground leading-7">
          A private Devin-like system that drives the Planner, Frontend,
          Backend, QA, and Security agents through a strict frontend-first
          workflow. Backend changes are unlocked only after you approve the
          frontend in the dashboard.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Link
          href="/dashboard"
          className="inline-flex h-10 items-center rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Open the dashboard
        </Link>
        <Link
          href="/login"
          className="inline-flex h-10 items-center rounded-md border px-5 text-sm font-medium hover:bg-accent"
        >
          Sign in
        </Link>
        <a
          href="https://github.com/Moksha89/aidev"
          className="inline-flex h-10 items-center rounded-md border px-5 text-sm font-medium hover:bg-accent"
        >
          GitHub
        </a>
      </div>

      <div className="rounded-lg border bg-card p-6 space-y-3">
        <h2 className="text-lg font-semibold">What this MVP includes</h2>
        <ul className="grid gap-2 sm:grid-cols-2 text-sm text-muted-foreground">
          <li>Dashboard with Sidebar / Chat / Activity</li>
          <li>Tabs: Preview, Diff, Logs, Screenshots</li>
          <li>Strict frontend-first approval gate</li>
          <li>OpenAI-compatible model server config</li>
          <li>Mock multi-agent task lifecycle</li>
          <li>GitHub PR creation hook</li>
        </ul>
      </div>
    </div>
  );
}
