import { RuntimeBadge } from "@/components/RuntimeBadge";
import { Sidebar } from "@/components/Sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar />
        <main className="flex-1 min-w-0">{children}</main>
      </div>
    </div>
  );
}

function Topbar() {
  return (
    <header className="sticky top-0 z-10 h-14 border-b bg-background flex items-center justify-between gap-3 px-4">
      <p className="text-sm text-muted-foreground">
        Frontend-first mode. Backend changes require explicit approval.
      </p>
      <RuntimeBadge />
    </header>
  );
}
