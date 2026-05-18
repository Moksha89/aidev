import { AppShell } from "@/components/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { mockModelServers } from "@/lib/mocks";

export default function ModelSettingsPage() {
  return (
    <AppShell>
      <div className="container max-w-4xl py-8 space-y-6">
        <header className="flex items-end justify-between">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">
              Model servers
            </h1>
            <p className="text-sm text-muted-foreground">
              Configure any OpenAI-compatible endpoint (Ollama, vLLM,
              llama.cpp, LM Studio).
            </p>
          </div>
          <Button>Add model server</Button>
        </header>

        <div className="space-y-3">
          {mockModelServers.map((m) => (
            <Card key={m.id}>
              <CardHeader className="flex flex-row items-start gap-3">
                <div className="flex-1">
                  <CardTitle>{m.name}</CardTitle>
                  <p className="text-xs text-muted-foreground mt-1 font-mono">
                    {m.base_url} · {m.model_identifier}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <Badge variant={m.is_default ? "success" : "secondary"}>
                    {m.is_default ? "default" : m.server_type}
                  </Badge>
                  {!m.is_active && <Badge variant="danger">inactive</Badge>}
                </div>
              </CardHeader>
              <CardContent className="flex gap-2">
                <Button variant="outline" size="sm">
                  Test connection
                </Button>
                {!m.is_default && (
                  <Button variant="outline" size="sm">
                    Make default
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
        </div>

        <Card>
          <CardHeader>
            <CardTitle>How it talks to your server</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground space-y-2">
            <p>
              The agents call <code>POST {`{base_url}`}/chat/completions</code> with
              the OpenAI schema. Tool calls are emitted via the standard
              <code> tool_calls </code> field. No API keys leave your network.
            </p>
            <p>
              On the Ubuntu GPU VPS we recommend{" "}
              <code>Qwen/Qwen2.5-Coder-32B-Instruct</code> on vLLM or{" "}
              <code>llama3.1:8b-instruct</code> on Ollama if VRAM is tight. See{" "}
              <code>docs/MODEL_SERVER_SETUP.md</code>.
            </p>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
