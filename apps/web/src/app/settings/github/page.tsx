import { AppShell } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function GithubSettingsPage() {
  return (
    <AppShell>
      <div className="container max-w-3xl py-8 space-y-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">
            GitHub integration
          </h1>
          <p className="text-sm text-muted-foreground">
            How agents push branches and open PRs on your behalf.
          </p>
        </header>

        <Card>
          <CardHeader>
            <CardTitle>Personal access token</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              The platform uses a fine-grained PAT with{" "}
              <code>contents:rw</code> and <code>pull_requests:rw</code> on the
              repositories you connect. Tokens are AES-encrypted in the
              database — never written to logs.
            </p>
            <div className="space-y-2">
              <label className="block space-y-1">
                <span className="text-sm font-medium">Token</span>
                <input
                  type="password"
                  name="github_token"
                  placeholder="github_pat_…"
                  className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                />
              </label>
              <Button>Save token</Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Webhook</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground space-y-2">
            <p>
              Add this webhook URL to the repositories you want the platform to
              watch:
            </p>
            <pre className="rounded-md bg-muted p-3 text-xs font-mono overflow-x-auto">
              {`POST {API_BASE_URL}/webhooks/github
content-type: application/json
x-aidev-secret: <AIDEV_GITHUB_WEBHOOK_SECRET>`}
            </pre>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
