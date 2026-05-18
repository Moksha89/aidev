"use client";

import { cn } from "@/lib/utils";
import {
  FolderGit2,
  GitBranch,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  Terminal,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/projects", label: "Projects", icon: FolderGit2 },
  { href: "/repositories", label: "Repositories", icon: GitBranch },
  { href: "/tasks", label: "Tasks", icon: Terminal },
] as const;

const SETTINGS = [
  { href: "/settings/github", label: "GitHub", icon: GitBranch },
  { href: "/settings/models", label: "Model servers", icon: Terminal },
  { href: "/settings/rules", label: "Rules", icon: ShieldCheck },
  { href: "/settings/servers", label: "Servers", icon: Settings },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const appName = process.env.NEXT_PUBLIC_APP_NAME ?? "AI Developer";

  return (
    <aside className="hidden lg:flex h-screen w-64 flex-col border-r bg-card sticky top-0">
      <div className="h-14 flex items-center px-5 border-b">
        <Link href="/dashboard" className="font-semibold tracking-tight">
          {appName}
        </Link>
      </div>
      <nav className="flex-1 overflow-y-auto p-3 space-y-6">
        <div className="space-y-1">
          {NAV.map((item) => (
            <SidebarLink
              key={item.href}
              href={item.href}
              label={item.label}
              icon={<item.icon className="h-4 w-4" />}
              active={pathname.startsWith(item.href)}
            />
          ))}
        </div>
        <div className="space-y-1">
          <p className="px-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Settings
          </p>
          {SETTINGS.map((item) => (
            <SidebarLink
              key={item.href}
              href={item.href}
              label={item.label}
              icon={<item.icon className="h-4 w-4" />}
              active={pathname === item.href}
            />
          ))}
        </div>
      </nav>
      <div className="border-t p-3 text-xs text-muted-foreground">
        v0.1.0 · frontend-first mode
      </div>
    </aside>
  );
}

function SidebarLink({
  href,
  label,
  icon,
  active,
}: {
  href: string;
  label: string;
  icon: React.ReactNode;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-2 rounded-md px-3 h-9 text-sm font-medium",
        active
          ? "bg-accent text-foreground"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      {icon}
      {label}
    </Link>
  );
}
