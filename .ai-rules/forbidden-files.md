---
id: forbidden-files
title: Always-forbidden files
applies_to: all_phases
priority: 100
enforced_by: [rules_engine, overlayfs]
---

# Always-forbidden files

These paths are forbidden in **every** phase, regardless of approval
state or project override. They are checked by the rules engine first;
no other rule can grant access to them.

```glob
**/.env
**/.env.local
**/.env.production
**/.env.staging
**/.env.development
**/secrets/**
**/credentials.*
**/credential.json
**/service-account*.json
**/google-services.json
**/GoogleService-Info.plist
**/*.pem
**/*.key
**/*.p12
**/*.pfx
**/id_rsa*
**/id_ed25519*
**/known_hosts
**/.npmrc
**/.pypirc
**/.dockercfg
**/auth.json
.ai-rules/**
.git/**
.github/workflows/deploy*.yml
.github/workflows/release*.yml
docker/Dockerfile.sandbox
infra/production/**
**/*.sqlite
**/*.sqlite3
**/*.db-journal
**/wallet.dat
**/keystore/**
```

## Why `.ai-rules/**` is forbidden

The rules engine is operator-owned. If the agent could modify it, the
rest of the policy collapses. Project-level rule overrides happen
through the dashboard (`/settings/rules`) and are stored in the
database; the on-disk `.ai-rules/` is the global default and is not
agent-writable.

## Why `.git/**` is forbidden

Commits and pushes are produced by the platform, not by the agent
writing to `.git/` directly. The agent uses the workspace; the platform
commits with structured metadata.

## How to add to this list per-project

Operators can extend (never relax) the forbidden list via
`/settings/rules` → "Custom forbidden patterns". Patterns there are
unioned with the global list.
