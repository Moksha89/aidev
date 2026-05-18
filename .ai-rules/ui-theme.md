---
id: ui-theme
title: UI theme & component conventions
applies_to: phases.FRONTEND_CODING
priority: 60
---

# UI theme & component conventions

These are the visual / structural conventions the Frontend agent must
follow when producing the dashboard or any product UI.

## Stack

- **React** with **TypeScript** (strict mode).
- **Next.js 14 App Router** for any page route.
- **Tailwind CSS** for styling — no CSS-in-JS, no inline `style={{}}`
  unless dynamic.
- **shadcn/ui** for primitives (`Button`, `Card`, `Dialog`, `Tabs`, …).
  Import from `@/components/ui/*`.
- **lucide-react** for icons.
- **recharts** for charts.

## Tokens

- Colours: use Tailwind theme tokens (`bg-primary`, `text-muted-foreground`,
  …). Do not use arbitrary values (`bg-[#ff0000]`).
- Spacing: standard Tailwind scale only.
- Radius: `rounded-lg` by default; `rounded-2xl` for hero cards.
- Shadows: `shadow-sm` default, `shadow-md` on hover for interactive
  cards.

## Layout

- Dashboard uses a three-column layout:
  - Left: sidebar (`Projects`, `Tasks`, `Repositories`, `Settings`).
  - Centre: page content, scrollable.
  - Right: live activity panel (logs + current step), collapsible.
- Page max width: `max-w-7xl mx-auto px-6`.
- Sticky header height: `h-14`.

## Responsiveness

- Pages must render correctly at the five preview viewports:
  `mobile-375`, `mobile-430`, `tablet-768`, `desktop-1280`, `desktop-1920`.
- Use Tailwind responsive prefixes; do not write media-query CSS.
- The sidebar collapses to icons at `<lg`.

## Accessibility

- Every interactive element has a discernible name (`aria-label` or
  visible text).
- Colour contrast ≥ 4.5 : 1 for body text.
- Keyboard: every action reachable via Tab; Escape closes dialogs.
- Honor `prefers-reduced-motion`.

## File organisation

- `apps/web/src/app/**` — route files only (`page.tsx`, `layout.tsx`,
  `loading.tsx`, `error.tsx`).
- `apps/web/src/components/**` — reusable components.
- `apps/web/src/components/ui/**` — shadcn primitives (don't modify).
- `apps/web/src/lib/**` — utilities.
- `apps/web/src/mocks/**` — typed mock data.
- `apps/web/src/hooks/**` — custom React hooks.
