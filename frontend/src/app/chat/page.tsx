"use client";

import ChatWindow from "@/components/ChatWindow";
import { SourceSegment } from "@/types";
import { useRouter } from "next/navigation";
import { MessageSquare, Sparkles, HelpCircle, Layers } from "lucide-react";

export default function GlobalChatPage() {
  const router = useRouter();

  const handleSourceClick = (source: SourceSegment) => {
    // Naviga al dettaglio dell'intervista salvando eventualmente il timestamp nei query params o rotta
    router.push(`/interviews/${source.interview_id}?time=${source.start}`);
  };

  return (
    <div className="h-[calc(100vh-4rem)] bg-slate-950 flex flex-col overflow-hidden">
      <div className="max-w-7xl mx-auto w-full h-full p-4 sm:p-6 flex flex-col gap-4">
        {/* Banner informativo superiore */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-md">
              <MessageSquare className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <span>Chat RAG Globale dell'Archivio</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1">
                  <Sparkles className="w-3 h-3" /> Qdrant Vector DB Active
                </span>
              </h1>
              <p className="text-xs text-slate-400">
                Fai domande trasversali su qualsiasi trascrizione audio caricata nel sistema
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-400 bg-slate-950/60 px-3 py-1.5 rounded-xl border border-slate-800/60">
            <Layers className="w-3.5 h-3.5 text-indigo-400" />
            <span>Clicca sulle fonti citate per aprire l'audio player al minuto esatto</span>
          </div>
        </div>

        {/* Chat Window Component Full Height */}
        <div className="flex-1 min-h-0">
          <ChatWindow
            title="Assistente RAG Globale"
            subtitle="Interroga l'intera base di conoscenza vettoriale"
            onSourceClick={handleSourceClick}
          />
        </div>
      </div>
    </div>
  );
}
