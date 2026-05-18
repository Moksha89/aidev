import { AppShell } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const SERVERS = [
  {
    name: "Ubuntu 24 LTS · GPU",
    host: "gpu-vps.internal",
    role: "model server + API + workers + sandboxes",
    status: "planned",
  },
  {
    name: "Windows 11 Pro",
    host: "qa-vps.internal",
    role: "manual QA / RDP preview only",
    status: "planned",
  },
] as const;

export default function ServersPage() {
  return (
    <AppShell>
      <div className="container max-w-4xl py-8 space-y-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Servers</h1>
          <p className="text-sm text-muted-foreground">
            Hosts that run the model server, API, workers, and sandboxes.
            Credentials are loaded from secrets, never displayed here.
          </p>
        </header>

        <div className="grid gap-3">
          {SERVERS.map((s) => (
            <Card key={s.host}>
              <CardHeader className="flex flex-row items-start gap-3">
                <div className="flex-1">
                  <CardTitle>{s.name}</CardTitle>
                  <p className="text-xs font-mono text-muted-foreground mt-1">
                    {s.host}
                  </p>
                  <p className="text-sm text-muted-foreground mt-1">{s.role}</p>
                </div>
                <Badge variant={s.status === "planned" ? "secondary" : "success"}>
                  {s.status}
                </Badge>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">
                Deployment commands live in{" "}
                <code className="font-mono">docs/DEPLOYMENT.md</code>.
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
