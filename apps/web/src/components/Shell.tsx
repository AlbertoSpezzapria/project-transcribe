import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, Outlet, useNavigate, useParams } from "@tanstack/react-router";
import { Archive, FileText, LogOut, Menu, Moon, Network, Search, Sun, Users } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

type NavItem = { to: string; label: string; icon: ReactNode; phase?: string };

function useTheme() {
  const read = () => {
    try {
      return localStorage.getItem("theme");
    } catch {
      return null;
    }
  };
  const [theme, setTheme] = useState<string | null>(read);
  const toggle = () => {
    const isDark =
      theme === "dark" || (theme === null && window.matchMedia("(prefers-color-scheme: dark)").matches);
    const next = isDark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      /* preferenza non salvata: nessun problema */
    }
    setTheme(next);
  };
  return { theme, toggle };
}

export function Shell() {
  const { workspaceId } = useParams({ strict: false }) as { workspaceId?: string };
  const { data: auth } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { toggle } = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);

  const logout = useMutation({
    mutationFn: () => api.POST("/api/auth/logout"),
    onSuccess: () => {
      qc.clear();
      navigate({ to: "/accesso" });
    },
  });

  // ⌘K / Ctrl+K: ricerca da qualsiasi pagina
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k" && workspaceId) {
        e.preventDefault();
        navigate({ to: "/w/$workspaceId/ricerca", params: { workspaceId } });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, workspaceId]);

  const workspace = auth?.workspaces.find((w) => w.id === workspaceId);
  const base = `/w/${workspaceId}`;
  const nav: NavItem[] = [
    { to: `${base}/storie`, label: "Storie", icon: <FileText className="size-4" /> },
    { to: `${base}/archivio`, label: "Archivio fonti", icon: <Archive className="size-4" /> },
    { to: `${base}/ricerca`, label: "Ricerca", icon: <Search className="size-4" />, phase: "⌘K" },
    { to: `${base}/persone`, label: "Persone ed enti", icon: <Users className="size-4" />, phase: "Fase 4" },
    { to: `${base}/grafo`, label: "Connessioni", icon: <Network className="size-4" />, phase: "Fase 4" },
  ];

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="px-4 pb-4 pt-5">
        <p className="font-serif text-lg font-semibold tracking-tight">Redazione</p>
        {auth && auth.workspaces.length > 1 ? (
          <select
            className="mt-2 w-full rounded border border-border bg-surface px-2 py-1 text-sm"
            value={workspaceId}
            onChange={(e) => navigate({ to: "/w/$workspaceId/storie", params: { workspaceId: e.target.value } })}
            aria-label="Workspace"
          >
            {auth.workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        ) : (
          <p className="mt-0.5 truncate text-sm text-muted">{workspace?.name}</p>
        )}
      </div>
      <nav className="flex-1 space-y-0.5 px-2" aria-label="Sezioni">
        {nav.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            onClick={() => setMobileOpen(false)}
            className="flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm text-muted hover:bg-surface-2 hover:text-text"
            activeProps={{ className: "!bg-surface-2 !text-text font-medium" }}
          >
            {item.icon}
            <span className="flex-1">{item.label}</span>
            {item.phase && <span className="text-[10px] uppercase tracking-wide text-muted/70">{item.phase}</span>}
          </Link>
        ))}
      </nav>
      <div className="border-t border-border p-3">
        <p className="truncate px-1 text-sm font-medium">{auth?.user?.full_name}</p>
        <p className="truncate px-1 text-xs text-muted">{auth?.user?.email}</p>
        <div className="mt-2 flex gap-1">
          <button onClick={toggle} className="rounded p-1.5 text-muted hover:bg-surface-2" aria-label="Cambia tema">
            <Sun className="size-4 dark:hidden" />
            <Moon className="hidden size-4 dark:block" />
          </button>
          <button
            onClick={() => logout.mutate()}
            className="flex items-center gap-1.5 rounded px-2 py-1.5 text-xs text-muted hover:bg-surface-2"
          >
            <LogOut className="size-3.5" /> Esci
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 border-r border-border bg-surface md:block">{sidebar}</aside>

      {/* Mobile */}
      <div className="fixed inset-x-0 top-0 z-20 flex h-12 items-center gap-2 border-b border-border bg-surface px-4 md:hidden">
        <button onClick={() => setMobileOpen(true)} aria-label="Apri menu" className="-ml-1 rounded p-1">
          <Menu className="size-5" />
        </button>
        <span className="font-serif font-semibold">Redazione</span>
      </div>
      {mobileOpen && (
        <div className="fixed inset-0 z-30 md:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 bg-surface shadow-xl">{sidebar}</aside>
        </div>
      )}

      <main className={cn("min-w-0 flex-1 px-4 pb-16 pt-16 md:px-8 md:pt-8")}>
        <div className="mx-auto max-w-5xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
