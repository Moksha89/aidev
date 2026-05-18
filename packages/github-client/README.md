# @aidev/github-client

A thin, opinionated wrapper around the GitHub REST API for the things
the platform actually does:

- list branches / get default branch
- create a branch from a ref
- get / put file contents
- create a commit on a branch
- create a pull request
- post a comment with screenshots

It intentionally does **not** implement every GitHub API call. If you
need something else, prefer a one-off `httpx.AsyncClient` call over
adding a new method here.

## Auth

Supports two modes:

- **PAT** — pass `token=…` to the constructor.
- **GitHub App** — pass `app_id=…`, `private_key=…`, `installation_id=…`.
  The client mints an installation token internally and refreshes it on
  expiry.

The client never logs tokens; the structured logger redacts the
`Authorization` header.
