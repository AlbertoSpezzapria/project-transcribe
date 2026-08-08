"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { Sparkles, LayoutDashboard, MessageSquareText, Activity, Radio } from "lucide-react";
import { API_BASE_URL } from "@/lib/api";

export default function Navbar() {
  const pathname = usePathname();
  const [apiStatus, setApiStatus] = useState<"online" | "offline" | "checking">("checking");

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/`, { cache: "no-store" });
        if (res.ok) {
          setApiStatus("online");
        } else {
          setApiStatus("offline");
        }
      } catch (err) {
        setApiStatus("offline");
      }
    };

    checkStatus();
    const interval = setInterval(checkStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const navLinks = [
    {
      href: "/",
      label: "Dashboard",
      icon: LayoutDashboard,
      active: pathname === "/",
    },
    {
      href: "/chat",
      label: "Chat RAG Globale",
      icon: MessageSquareText,
      active: pathname.startsWith("/chat"),
    },
  ];

  return (
    <header className="sticky top-0 z-50 w-full backdrop-blur-md bg-slate-950/80 border-b border-slate-800/80 shadow-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand / Logo */}
        <Link href="/" className="flex items-center gap-3 group transition-transform duration-200 hover:scale-[1.01]">
          <div className="p-2 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-500 to-indigo-700 shadow-lg shadow-indigo-500/20 group-hover:shadow-indigo-500/40 transition-all duration-300">
            <Sparkles className="w-5 h-5 text-white animate-pulse" />
          </div>
          <div className="flex flex-col">
            <span className="font-extrabold text-lg tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-100 to-indigo-200">
              Interview<span className="text-indigo-400 font-black">AI</span>
            </span>
            <span className="text-[10px] text-slate-400 font-medium tracking-wide">
              Trascrizione & RAG Analysis
            </span>
          </div>
        </Link>

        {/* Navigation Links */}
        <nav className="flex items-center gap-1 sm:gap-2">
          {navLinks.map((link) => {
            const Icon = link.icon;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  link.active
                    ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <Icon className={`w-4 h-4 ${link.active ? "text-indigo-400" : "text-slate-400"}`} />
                <span>{link.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* API Backend Status Indicator */}
        <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/90 border border-slate-800 text-xs">
          <Radio className="w-3.5 h-3.5 text-slate-400" />
          <span className="text-slate-400 font-medium">Backend:</span>
          {apiStatus === "online" && (
            <span className="inline-flex items-center gap-1.5 text-emerald-400 font-semibold">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
              Online
            </span>
          )}
          {apiStatus === "offline" && (
            <span className="inline-flex items-center gap-1.5 text-rose-400 font-semibold">
              <span className="w-2 h-2 rounded-full bg-rose-500" />
              Disconnesso
            </span>
          )}
          {apiStatus === "checking" && (
            <span className="inline-flex items-center gap-1.5 text-amber-400 font-semibold">
              <Activity className="w-3 h-3 animate-spin text-amber-400" />
              Verifica...
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
