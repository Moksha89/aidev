# GitHub Integration

The platform uses the GitHub REST API to:

- list repos a user can grant access to,
- clone a repo into the per-task sandbox workspace,
- create the per-task branch (`aidev/task-<id>-<slug>`),
- commit and push agent-produced changes,
- open a pull request when the task reaches `DONE`,
- post screenshots and Playwright reports as PR comments.

## Auth modes

### Personal Access Token (PAT)

For a single-user install. Create a fine-grained PAT with these scopes:

- `repo` → `read` + `write` (for the specific repos you want to connect)
- `pull_requests` → `read` + `write`
- `contents` → `read` + `write`

Set in `apps/api/.env`:

```
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

…or paste it into the dashboard at `/settings/github`. The token is stored
encrypted-at-rest (see `SECURITY.md`).

### GitHub App (recommended for teams)

1. Visit `https://github.com/settings/apps/new` (or your org's apps page).
2. Permissions:
   - **Repository**: `contents: read/write`, `pull_requests: read/write`,
     `metadata: read`, `workflows: read` (optional).
   - **Account**: none.
3. Subscribe to events: `pull_request`, `push` (optional, for status
   updates).
4. Generate a private key, download the `.pem` file.
5. Install the app on the orgs/repos you want the platform to manage.
6. Configure:

```
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=/etc/aidev/github-app.pem
GITHUB_APP_INSTALLATION_ID=78901234   # per installation
```

The installation ID can be looked up via the `/repositories` page in the
dashboard — the API will fetch it once you've installed the app.

## What the platform does on your repo

Every task that completes successfully produces:

1. A branch `aidev/task-<task_id>-<slug>` pushed to the connected repo.
2. One squash commit per agent phase (`planner`, `frontend`, `qa`,
   `backend`, `security`).
3. A pull request titled with the task title, body containing:
   - the original instruction,
   - the agent plan,
   - the list of files changed,
   - links to preview URL and screenshots,
   - the rules-engine audit summary.

The branch is never force-pushed; if a task is re-run it creates a new
branch with a `-rerun-N` suffix.

## What the platform will NOT do

- Push directly to `main` / `master` / `develop`.
- Merge a PR (you do that yourself).
- Delete branches.
- Modify GitHub Actions workflow files unless `.ai-rules/forbidden-files.md`
  explicitly allows it (it does not by default).
- Touch secrets, releases, or environments.

## Connecting a repo

1. In the dashboard, go to `/settings/github` and verify your auth mode
   is configured.
2. Go to `/repositories` and click **Connect repository**.
3. Pick the repo from the dropdown (populated from the GitHub API).
4. Pick the default base branch (usually `main`).
5. Optionally pin a per-repo rule set override (e.g. extra allowed paths).

## Webhooks

Outgoing webhooks (from GitHub → platform) are optional. They are used
only to update PR status badges in the dashboard. If you don't configure
them, the dashboard polls the GitHub API every 60 s.

If you do want them, set the webhook URL to
`https://api.<your-domain>/webhooks/github` with a shared secret matching
`GITHUB_WEBHOOK_SECRET`.
