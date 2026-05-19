/**
 * Runtime banner that surfaces the v0.4 pipeline state in the topbar.
 *
 * Renders three pill-shaped badges:
 *
 *   - executor    : ``mock`` / ``docker``  (which sandbox the worker uses)
 *   - pipeline    : ``mock`` / ``real``    (which dispatcher path the API takes)
 *   - github      : ``configured`` / ``missing``
 *
 * Plus a single one-word verdict ("MOCK MODE" / "REAL PIPELINE" / etc.)
 * derived from the two flags so the operator can tell the run mode at a
 * glance.
 *
 * Data source: ``GET /settings/runtime`` (see
 * ``apps/api/app/routes/settings.py``). The endpoint requires auth, so
 * the badge degrades to a non-blocking "MODE: UNKNOWN" pill if the
 * request fails (e.g. logged out or backend unreachable) — the goal is
 * to never break the dashboard frame.
 */
"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import type { RuntimeStatus } from "@/lib/types";

type State =
  | { kind: "loading" }
  | { kind: "ok"; value: RuntimeStatus }
  | { kind: "error" };

export function RuntimeBadge() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    apiFetch<RuntimeStatus>("/settings/runtime")
      .then((value) => {
        if (!cancelled) setState({ kind: "ok", value });
      })
      .catch(() => {
        if (!cancelled) setState({ kind: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.kind === "loading") {
    return (
      <Badge variant="secondary" className="font-mono">
        MODE: …
      </Badge>
    );
  }
  if (state.kind === "error") {
    return (
      <Badge variant="secondary" className="font-mono">
        MODE: UNKNOWN
      </Badge>
    );
  }

  const { sandbox_executor, agent_pipeline, github_configured, real_pipeline_active } = state.value;

  const verdictVariant: BadgeVariant = real_pipeline_active
    ? "warn"
    : "secondary";
  const verdictLabel = real_pipeline_active ? "REAL PIPELINE" : "MOCK MODE";

  return (
    <div className="flex items-center gap-2 font-mono text-xs">
      <Badge variant={verdictVariant}>{verdictLabel}</Badge>
      <Badge variant="outline">executor: {sandbox_executor}</Badge>
      <Badge variant="outline">pipeline: {agent_pipeline}</Badge>
      <Badge variant={github_configured ? "success" : "outline"}>
        github: {github_configured ? "configured" : "missing"}
      </Badge>
    </div>
  );
}
