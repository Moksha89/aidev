export default function LoginPage() {
  return (
    <div className="container max-w-md py-16 space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">Sign in</h1>
        <p className="text-sm text-muted-foreground">
          Local-first authentication. POST /auth/login with email + password.
        </p>
      </div>
      <form className="space-y-4 rounded-lg border bg-card p-6">
        <label className="block space-y-1">
          <span className="text-sm font-medium">Email</span>
          <input
            type="email"
            name="email"
            autoComplete="email"
            className="h-10 w-full rounded-md border bg-background px-3 text-sm"
            placeholder="you@example.com"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Password</span>
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            className="h-10 w-full rounded-md border bg-background px-3 text-sm"
            placeholder="••••••••"
          />
        </label>
        <button
          type="submit"
          className="inline-flex h-10 w-full items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Sign in
        </button>
      </form>
      <p className="text-xs text-muted-foreground">
        First-time setup: the API creates an admin from the
        <code className="mx-1 rounded bg-muted px-1 py-0.5">AIDEV_ADMIN_EMAIL</code>
        environment variable on first start.
      </p>
    </div>
  );
}
