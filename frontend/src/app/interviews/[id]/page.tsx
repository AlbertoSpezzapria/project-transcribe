"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import AudioPlayer from "@/components/AudioPlayer";
import ChatWindow from "@/components/ChatWindow";
import { InterviewDetail, Segment, SourceSegment } from "@/types";
import { API_BASE_URL } from "@/lib/api";
import {
  ArrowLeft,
  Calendar,
  Sparkles,
  FileText,
  Tag,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Volume2,
  SlidersHorizontal,
  Play,
} from "lucide-react";

export default function InterviewDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  const id = params?.id ? parseInt(params.id as string, 10) : null;
  const initialTime = searchParams?.get("time") ? parseFloat(searchParams.get("time")!) : null;

  const [interview, setInterview] = useState<InterviewDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [transcriptTab, setTranscriptTab] = useState<"polished" | "raw">("polished");
  const [seekTime, setSeekTime] = useState<number | null>(initialTime);
  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number | null>(null);

  const fetchInterviewDetail = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/interviews/${id}`, { cache: "no-store" });
      if (!res.ok) {
        throw new Error(`Intervista #${id} non trovata o errore server (${res.status})`);
      }
      const data: InterviewDetail = await res.json();
      setInterview(data);

      // Default to raw if polished is empty
      if (!data.polished_transcript && data.raw_transcript) {
        setTranscriptTab("raw");
      }
    } catch (err: any) {
      setError(err.message || "Errore nel caricamento dei dettagli.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchInterviewDetail();
  }, [fetchInterviewDetail]);

  const handleTimeUpdate = (currentTime: number) => {
    // Sincronizza il segmento attivo in base all'avanzamento dell'audio
    const segments = transcriptTab === "polished" ? interview?.polished_segments : interview?.raw_segments;
    if (segments && segments.length > 0) {
      const idx = segments.findIndex(
        (seg) => currentTime >= seg.start && currentTime <= seg.end
      );
      if (idx !== -1 && idx !== activeSegmentIndex) {
        setActiveSegmentIndex(idx);
      }
    }
  };

  const handleSegmentClick = (start: number) => {
    setSeekTime(start);
  };

  const handleSourceClick = (source: SourceSegment) => {
    setSeekTime(source.start);
  };

  const formatTimestamp = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return "Data non specificata";
    try {
      return new Intl.DateTimeFormat("it-IT", {
        day: "2-digit",
        month: "long",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(dateStr));
    } catch {
      return dateStr;
    }
  };

  if (loading) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-slate-950 flex items-center justify-center p-6">
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="w-12 h-12 rounded-full border-4 border-indigo-500/20 border-t-indigo-500 animate-spin" />
          <p className="text-slate-300 font-medium text-sm">Caricamento dettagli intervista #{id}...</p>
        </div>
      </div>
    );
  }

  if (error || !interview) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-slate-950 p-8 flex items-center justify-center">
        <div className="max-w-md text-center p-8 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
          <AlertTriangle className="w-12 h-12 text-rose-400 mx-auto" />
          <h2 className="text-lg font-bold text-slate-100">Impossibile Caricare l'Intervista</h2>
          <p className="text-xs text-slate-400">{error || "L'intervista richiesta non esiste."}</p>
          <Link
            href="/"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-500 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" /> Torna alla Dashboard
          </Link>
        </div>
      </div>
    );
  }

  // Costruisci l'URL audio per il componente AudioPlayer
  // Se file_path esiste (es. uploads/nomefile.mp3), estraiamo solo il nome del file per servire via /uploads
  const audioFilename = interview.file_path ? interview.file_path.split("/").pop() : interview.filename;
  const audioSrc = `${API_BASE_URL}/uploads/${encodeURIComponent(audioFilename || "")}`;

  const currentSegments = transcriptTab === "polished" ? interview.polished_segments : interview.raw_segments;

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-slate-950 p-4 sm:p-6 space-y-6">
      {/* Top Header / Breadcrumb */}
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div className="flex items-center gap-3">
          <Link
            href="/"
            className="p-2 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
            title="Torna alla Dashboard"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-slate-100 truncate max-w-md sm:max-w-xl">
                {interview.filename}
              </h1>
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                #{interview.id}
              </span>
            </div>
            <p className="text-xs text-slate-400 flex items-center gap-1.5 mt-0.5">
              <Calendar className="w-3.5 h-3.5 text-slate-400" />
              <span>Caricato il {formatDate(interview.created_at)}</span>
            </p>
          </div>
        </div>
      </div>

      {/* Main 2-Column Grid */}
      <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* LEFT COLUMN: Player + Summary + Transcript (7 Cols) */}
        <div className="lg:col-span-7 space-y-6">
          {/* Audio Player Component */}
          <AudioPlayer
            src={audioSrc}
            title={interview.filename}
            seekTime={seekTime}
            onTimeUpdate={handleTimeUpdate}
          />

          {/* AI Summary Card */}
          {interview.summary && (
            <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800/80 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-indigo-400" />
                  <span>Sommario Sintetico AI</span>
                </h3>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed bg-slate-950/60 p-4 rounded-xl border border-slate-800/60">
                {interview.summary}
              </p>

              {interview.key_topics && interview.key_topics.length > 0 && (
                <div className="pt-2 flex flex-wrap gap-1.5">
                  {interview.key_topics.map((topic, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-indigo-500/10 text-indigo-300 border border-indigo-500/20"
                    >
                      <Tag className="w-3 h-3 text-indigo-400" />
                      {topic}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Interactive Transcript Box */}
          <div className="rounded-2xl bg-slate-900/80 border border-slate-800/80 p-5 space-y-4">
            {/* Tabs Bar */}
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <FileText className="w-4 h-4 text-indigo-400" />
                <span>Trascrizione dell'Intervista</span>
              </h3>

              <div className="flex items-center gap-1 bg-slate-950/80 p-1 rounded-xl border border-slate-800">
                <button
                  type="button"
                  onClick={() => setTranscriptTab("polished")}
                  className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                    transcriptTab === "polished"
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Raffinata (Polished)
                </button>
                <button
                  type="button"
                  onClick={() => setTranscriptTab("raw")}
                  className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                    transcriptTab === "raw"
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Integrale (Raw)
                </button>
              </div>
            </div>

            {/* Segment List */}
            <div className="max-h-[450px] overflow-y-auto pr-2 space-y-2">
              {currentSegments && currentSegments.length > 0 ? (
                currentSegments.map((seg, idx) => {
                  const isCurrent = activeSegmentIndex === idx;
                  const text = seg.polished_text || seg.text || "";

                  return (
                    <div
                      key={idx}
                      onClick={() => handleSegmentClick(seg.start)}
                      className={`group p-3.5 rounded-xl border transition-all cursor-pointer flex gap-3 ${
                        isCurrent
                          ? "bg-indigo-950/50 border-indigo-500/60 shadow-md shadow-indigo-500/10"
                          : "bg-slate-950/40 border-slate-800/60 hover:bg-slate-900 hover:border-slate-700"
                      }`}
                    >
                      {/* Timestamp Pill */}
                      <button
                        type="button"
                        className={`px-2 py-1 rounded-lg text-xs font-mono font-semibold shrink-0 h-fit flex items-center gap-1 transition-colors ${
                          isCurrent
                            ? "bg-indigo-600 text-white"
                            : "bg-slate-800 text-indigo-400 group-hover:bg-indigo-600 group-hover:text-white"
                        }`}
                      >
                        <Play className="w-3 h-3 fill-current" />
                        <span>{formatTimestamp(seg.start)}</span>
                      </button>

                      {/* Text */}
                      <p
                        className={`text-xs leading-relaxed ${
                          isCurrent ? "text-slate-100 font-medium" : "text-slate-300 group-hover:text-slate-100"
                        }`}
                      >
                        {text}
                      </p>
                    </div>
                  );
                })
              ) : (
                <div className="p-4 rounded-xl bg-slate-950/40 text-slate-300 text-xs leading-relaxed whitespace-pre-wrap">
                  {transcriptTab === "polished"
                    ? interview.polished_transcript || "Trascrizione raffinata non ancora disponibile."
                    : interview.raw_transcript || "Trascrizione grezza non disponibile."}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Contextual RAG Chat Window (5 Cols) */}
        <div className="lg:col-span-5 h-[650px] lg:h-auto">
          <ChatWindow
            interviewId={interview.id}
            title={`Chat con #${interview.id}`}
            subtitle={`Poni domande mirate sul contenuto di ${interview.filename}`}
            onSourceClick={handleSourceClick}
          />
        </div>
      </div>
    </div>
  );
}
