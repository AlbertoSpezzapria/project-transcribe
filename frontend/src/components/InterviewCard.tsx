"use client";

import Link from "next/link";
import { FileAudio, Calendar, ArrowRight, Tag, Trash2, CheckCircle2, Clock, AlertTriangle, FileText } from "lucide-react";
import { InterviewSummary } from "@/types";

interface InterviewCardProps {
  interview: InterviewSummary;
  onDelete?: (id: number) => void;
}

export default function InterviewCard({ interview, onDelete }: InterviewCardProps) {
  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return "Data non disponibile";
    try {
      const date = new Date(dateStr);
      return new Intl.DateTimeFormat("it-IT", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
    } catch {
      return dateStr;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "completed":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Completato
          </span>
        );
      case "completed_raw_only":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/20">
            <FileText className="w-3.5 h-3.5" />
            Grezzo
          </span>
        );
      case "processing":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <Clock className="w-3.5 h-3.5 animate-spin" />
            In corso
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <AlertTriangle className="w-3.5 h-3.5" />
            Fallito
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-400 border border-slate-700">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="group relative flex flex-col justify-between rounded-2xl bg-slate-900/60 border border-slate-800/80 p-5 transition-all duration-300 hover:border-indigo-500/40 hover:bg-slate-900/90 hover:shadow-xl hover:shadow-indigo-500/5">
      <div>
        {/* Header card: Icona, Titolo & Status */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 group-hover:scale-105 transition-transform shrink-0">
              <FileAudio className="w-5 h-5" />
            </div>
            <div className="overflow-hidden">
              <h3 className="text-base font-bold text-slate-100 truncate group-hover:text-indigo-300 transition-colors" title={interview.filename}>
                {interview.filename}
              </h3>
              <div className="flex items-center gap-1.5 text-xs text-slate-400 mt-0.5">
                <Calendar className="w-3.5 h-3.5 text-slate-400" />
                <span>{formatDate(interview.created_at)}</span>
              </div>
            </div>
          </div>
          <div className="shrink-0">{getStatusBadge(interview.status)}</div>
        </div>

        {/* Sommario AI */}
        <div className="mt-3 mb-4">
          {interview.summary ? (
            <p className="text-xs text-slate-300 line-clamp-3 leading-relaxed bg-slate-950/40 p-3 rounded-xl border border-slate-800/50">
              {interview.summary}
            </p>
          ) : (
            <p className="text-xs text-slate-400 italic p-3 rounded-xl bg-slate-950/20 border border-slate-800/30">
              {interview.status === "processing"
                ? "Generazione del sommario AI e dei temi chiave in corso..."
                : "Nessun sommario disponibile."}
            </p>
          )}
        </div>

        {/* Argomenti Chiave (Key Topics) */}
        {interview.key_topics && interview.key_topics.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {interview.key_topics.slice(0, 4).map((topic, idx) => (
              <span
                key={idx}
                className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-[11px] font-medium bg-slate-800/80 text-indigo-300 border border-slate-700/60"
              >
                <Tag className="w-2.5 h-2.5 text-indigo-400" />
                {topic}
              </span>
            ))}
            {interview.key_topics.length > 4 && (
              <span className="text-[11px] text-slate-400 font-medium self-center px-1">
                +{interview.key_topics.length - 4} altri
              </span>
            )}
          </div>
        )}
      </div>

      {/* Footer Card: Azioni */}
      <div className="pt-3 border-t border-slate-800/60 flex items-center justify-between gap-2">
        <Link
          href={`/interviews/${interview.id}`}
          className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-indigo-600/10 hover:bg-indigo-600 text-indigo-300 hover:text-white border border-indigo-500/20 hover:border-indigo-500 text-xs font-semibold transition-all duration-200"
        >
          <span>Apri Dettaglio & Chat</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>

        {onDelete && (
          <button
            type="button"
            onClick={() => onDelete(interview.id)}
            className="p-2 rounded-xl text-slate-400 hover:text-rose-400 hover:bg-rose-950/40 hover:border-rose-800/50 border border-transparent transition-colors"
            title="Elimina intervista"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}
