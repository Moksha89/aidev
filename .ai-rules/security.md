---
id: security
title: Security baseline
applies_to: all_phases
priority: 95
enforced_by: [rules_engine, security_reviewer]
---

# Security baseline

These rules apply in every phase and are checked at both the rules-engine
stage (path / content) and the Security Reviewer stage (semantic).

## Secrets

- Never write a literal secret to any file. Use the platform's secret
  placeholder syntax (e.g. `{{GITHUB_TOKEN}}`) and let the runtime
  substitute it at HTTP send time.
- Never read from `process.env` or `os.environ` in a route handler or
  React component. Use the project's configuration module.
- Never log a token, password, cookie, or authorisation header. The
  platform's structured logger redacts known patterns, but do not rely
  on that — don't pass them in the first place.
- Never check in a `.env`, `.pem`, `.p12`, `.key`, or `id_rsa*` file.

## Crypto

- Use the platform's crypto helpers; do not roll your own AES/HMAC.
- Use `crypto.randomUUID()` or the language equivalent, not `Math.random()`,
  for any ID that must be unguessable.
- Use `bcrypt`, `argon2`, or `scrypt` for password hashing — never raw
  `sha256` or `md5`.

## Input validation

- Validate every external input at the trust boundary (route handler,
  message handler, file upload). The platform exposes
  `apps/api/app/schemas/` patterns for this.
- Never interpolate user input into SQL, shell commands, or template
  strings. Use parameterised queries and quoted shell argv.

## Auth

- Every authenticated route must check both *authentication* (the user
  is who they claim) and *authorisation* (the user is allowed to do
  what they're asking).
- Use the platform's `require_user(role)` dependency, not ad-hoc
  middleware.
- Never compare tokens with `==`; use `secrets.compare_digest`.

## Web

- All cookies must be `HttpOnly`, `Secure`, and `SameSite=Lax` (or
  `Strict` where applicable).
- The dashboard's Content-Security-Policy is set centrally — do not
  introduce inline scripts or `unsafe-eval`.
- All API responses include `Cache-Control: no-store` by default.

## Dependencies

- Do not add a dependency from an unknown publisher. Stick to packages
  with > 1k weekly downloads or that the project already uses.
- Pin versions in production lockfiles. Renovate handles upgrades.
