# @aidev/shared

Shared enums and types used by both the Python services (`apps/api`,
`workers/*`, `packages/rules-engine`) and the TypeScript dashboard
(`apps/web`). Treat this as the single source of truth for the wire
format.

## Layout

```
packages/shared/
├── python/aidev_shared/
│   ├── __init__.py
│   ├── enums.py          # TaskPhase, AgentRole, LogLevel, ApprovalDecision
│   └── pyproject.toml
└── typescript/
    ├── src/index.ts      # mirror of enums.py
    ├── package.json
    └── tsconfig.json
```

When you change one side, change the other. CI lints both.
