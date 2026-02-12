"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Cpu,
  BarChart3,
  History,
  Video,
  Settings,
  KeyRound,
  Network,
  TrendingUp,
  BookOpen,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { useApiKey } from "@/lib/use-api-key";

const nav = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Models", href: "/models", icon: Cpu, glossary: "model" },
  { label: "Evolution", href: "/evolution", icon: TrendingUp },
  { label: "Metrics", href: "/metrics", icon: BarChart3, glossary: "latency" },
  { label: "Metric Catalog", href: "/metrics-catalog", icon: BookOpen },
  { label: "Architecture", href: "/architecture", icon: Network },
  { label: "History", href: "/history", icon: History },
  { label: "WebRTC", href: "/webrtc", icon: Video, glossary: "webrtc" },
  { label: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { apiKey, setApiKey } = useApiKey();

  return (
    <aside className="flex flex-col w-64 min-h-screen border-r bg-sidebar text-sidebar-foreground">
      {/* Brand */}
      <div className="flex items-center gap-2 px-6 py-5 text-lg font-bold tracking-tight">
        <div className="h-7 w-7 rounded-md bg-primary flex items-center justify-center text-primary-foreground text-xs font-black">
          OD
        </div>
        OpenDeploy
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 space-y-1">
        {nav.map(({ label, href, icon: Icon, glossary }) => {
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              data-glossary={glossary}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* API Key input */}
      <div className="px-4 pb-5 space-y-1.5" data-glossary="api key">
        <label className="flex items-center gap-1.5 text-xs text-sidebar-foreground/60 font-medium cursor-help decoration-dotted underline underline-offset-4 decoration-muted-foreground/40">
          <KeyRound className="h-3 w-3" /> API Key
        </label>
        <Input
          type="password"
          placeholder="Enter API key"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          className="h-8 text-xs bg-sidebar-accent/40 border-sidebar-border"
        />
      </div>
    </aside>
  );
}
