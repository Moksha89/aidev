import { AppShell } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const RULE_FILES = [
  { name: "global.md", description: "Universal rules every agent must obey." },
  {
    name: "frontend-first.md",
    description: "Allowlist for the pre-approval frontend phase.",
  },
  {
    name: "backend-policy.md",
    description: "Allowlist that activates after explicit human approval.",
  },
  {
    name: "security.md",
    description: "Hard prohibitions — secrets, eval, exec, etc.",
  },
  { name: "ui-theme.md", description: "Design tokens and component library." },
  { name: "testing.md", description: "Test commands and viewport list." },
  { name: "deployment.md", description: "Deploy paths and gating." },
  {
    name: "forbidden-files.md",
    description: "Files that never get written, regardless of phase.",
  },
] as const;

export default function RulesSettingsPage() {
  return (
    <AppShell>
      <div className="container max-w-4xl py-8 space-y-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">
            Rules engine
          </h1>
          <p className="text-sm text-muted-foreground">
            The rule files in <code>.ai-rules/</code> drive the
            phase-aware allowlist and denylist. Edits here override the
            repo-level defaults.
          </p>
        </header>

        <div className="grid gap-3">
          {RULE_FILES.map((f) => (
            <Card key={f.name}>
              <CardHeader>
                <CardTitle>
                  <code className="font-mono">.ai-rules/{f.name}</code>
                </CardTitle>
                <p className="text-sm text-muted-foreground mt-1">
                  {f.description}
                </p>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">
                  Project-level override editor lands in v0.2. For now, edit
                  the source files in the repo.
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
