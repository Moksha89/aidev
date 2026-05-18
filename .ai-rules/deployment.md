---
id: deployment
title: Deployment policy
applies_to: all_phases
priority: 80
---

# Deployment policy

Agents do not deploy. Deployment is exclusively a human action initiated
from outside the platform (CI/CD or operator). This rule is here to make
that explicit.

## Forbidden in all phases

- Modifying `.github/workflows/deploy*.yml` or `release*.yml`.
- Modifying `infra/production/**` or any `*.tf` (Terraform) file.
- Modifying `helm/**`, `k8s/**`, or any chart values files.
- Calling cloud provider CLIs (`gcloud`, `aws`, `az`, `fly`, `vercel`,
  `flyctl`, `kubectl`) from agent tool calls.
- Writing or modifying `Dockerfile` files under `docker/` *unless* the
  task explicitly authorises it via a rule override.

## What agents may do

- Add a non-deploy CI workflow under `.github/workflows/ci-*.yml` (test,
  lint, type-check) — must be approved by the Security Reviewer.
- Add a `docker-compose.dev.yml` for local development that references
  only services declared by the platform.
- Document deployment in `docs/DEPLOYMENT.md` (markdown only).

## Preview deploys

Preview deploys (per-task subdomains) are handled by the platform's
`sandbox-runner` and Traefik — agents do not configure them. If an
agent needs a preview to be reachable on a different port, it must
update `next.config.*` / `vite.config.*` only; the platform handles the
proxy.
