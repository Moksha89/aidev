"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import type {
  Task,
  TaskFile,
  TaskLog,
  TaskPreview,
} from "@/lib/types";
import Image from "next/image";

export function TaskTabs({
  task,
  logs,
  files,
  previews,
}: {
  task: Task;
  logs: TaskLog[];
  files: TaskFile[];
  previews: TaskPreview[];
}) {
  return (
    <Tabs defaultValue="preview" className="w-full">
      <TabsList>
        <TabsTrigger value="preview">Preview</TabsTrigger>
        <TabsTrigger value="diff">Diff</TabsTrigger>
        <TabsTrigger value="logs">Logs</TabsTrigger>
        <TabsTrigger value="screenshots">
          Screenshots ({previews.length})
        </TabsTrigger>
        <TabsTrigger value="files">Files ({files.length})</TabsTrigger>
      </TabsList>

      <TabsContent value="preview">
        <PreviewTab task={task} />
      </TabsContent>
      <TabsContent value="diff">
        <DiffTab files={files} />
      </TabsContent>
      <TabsContent value="logs">
        <LogsTab logs={logs} />
      </TabsContent>
      <TabsContent value="screenshots">
        <ScreenshotsTab previews={previews} />
      </TabsContent>
      <TabsContent value="files">
        <FilesTab files={files} />
      </TabsContent>
    </Tabs>
  );
}

function PreviewTab({ task }: { task: Task }) {
  if (!task.preview_url) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          The preview URL is generated when QA completes the frontend build.
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardContent className="p-0 overflow-hidden">
        <iframe
          src={task.preview_url}
          title={`Preview for ${task.title}`}
          className="w-full h-[640px]"
        />
      </CardContent>
    </Card>
  );
}

function DiffTab({ files }: { files: TaskFile[] }) {
  if (files.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          No changes yet.
        </CardContent>
      </Card>
    );
  }
  const diff = files
    .map(
      (f) =>
        `diff --git a/${f.path} b/${f.path}\n--- a/${f.path}\n+++ b/${f.path}\n${f.diff_snippet}`,
    )
    .join("\n");
  return (
    <Card>
      <CardContent className="p-4">
        <pre className="overflow-x-auto rounded-md bg-muted p-4 text-xs font-mono leading-6">
          {diff}
        </pre>
      </CardContent>
    </Card>
  );
}

function LogsTab({ logs }: { logs: TaskLog[] }) {
  return (
    <Card>
      <CardContent className="p-4">
        <pre className="overflow-x-auto rounded-md bg-muted p-4 text-xs font-mono leading-6">
          {logs.length === 0
            ? "(no logs yet)"
            : logs
                .map(
                  (l) =>
                    `#${l.sequence} [${l.level}] ${l.phase ?? "-"} ${l.agent_role ?? "-"}: ${l.message}`,
                )
                .join("\n")}
        </pre>
      </CardContent>
    </Card>
  );
}

function FilesTab({ files }: { files: TaskFile[] }) {
  if (files.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          No file changes yet.
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardContent className="p-0">
        <table className="w-full text-sm">
          <thead className="bg-muted text-xs uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Path</th>
              <th className="text-right px-4 py-2">+</th>
              <th className="text-right px-4 py-2">−</th>
            </tr>
          </thead>
          <tbody>
            {files.map((f) => (
              <tr key={f.id} className="border-t">
                <td className="px-4 py-2 font-mono uppercase text-xs">
                  {f.status}
                </td>
                <td className="px-4 py-2 font-mono break-all">{f.path}</td>
                <td className="px-4 py-2 text-right text-emerald-600">
                  {f.lines_added}
                </td>
                <td className="px-4 py-2 text-right text-red-600">
                  {f.lines_removed}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function ScreenshotsTab({ previews }: { previews: TaskPreview[] }) {
  if (previews.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          Screenshots appear after the QA agent runs Playwright.
        </CardContent>
      </Card>
    );
  }
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {previews.map((p) => (
        <Card key={p.id}>
          <CardContent className="p-3 space-y-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span className="font-mono">{p.viewport}</span>
              <span>{p.width}×{p.height}</span>
            </div>
            <div className="aspect-video relative rounded-md border bg-muted overflow-hidden">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={p.image_url}
                alt={`Screenshot at ${p.viewport}`}
                className="object-cover w-full h-full"
              />
              {/* `Image` would require remote loader config; this is mock data. */}
              {false && <Image src={p.image_url} alt="" fill />}
            </div>
            {p.notes && (
              <p className="text-xs text-muted-foreground">{p.notes}</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
