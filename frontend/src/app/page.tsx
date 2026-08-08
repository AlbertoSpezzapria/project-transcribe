"use client";

import { useState, useEffect, useCallback } from "react";
import AudioUploader from "@/components/AudioUploader";
import InterviewCard from "@/components/InterviewCard";
import { InterviewSummary } from "@/types";
import { API_BASE_URL } from "@/lib/api";
import { Search, Library, Sparkles, RefreshCw, AlertCircle, Layers, FileCheck, HardDrive } from "lucide-react";

export default function Dashboard() {
  const [interviews, setInterviews] = useState<InterviewSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const fetchInterviews = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/interviews`, { cache: "no-store" });
      if (!res.ok) {
        throw new Error(`Impossibile recuperare le interviste (${res.status})`);
      }
      const data: InterviewSummary[] = await res.json();
      setInterviews(data);
    } catch (err: any) {
      setError(err.message || "Errore nella connessione con FastAPI.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInterviews();
  }, [fetchInterviews]);

  const handleDelete = async (id: number) => {
    if (!confirm(`Sei sicuro di voler eliminare l'intervista #${id}?`)) return;
    try {
      const res = await fetch(`${API_BASE_URL}/interviews/${id}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Errore durante l'eliminazione");
      setInterviews((prev) => prev.filter((item) => item.id !== id));
    } catch (err: any) {
      alert(`Impossibile eliminare: ${err.message}`);
    }
  };

  const filteredInterviews = interviews.filter((item) => {
    const matchesSearch =
      item.filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (item.summary && item.summary.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (item.key_topics && item.key_topics.some((t) => t.toLowerCase().includes(searchQuery.toLowerCase())));

    const matchesStatus = statusFilter === "all" ? true : item.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  const totalTopics = Array.from(
    new Set(interviews.flatMap((i) => i.key_topics || []))
  ).length;

  const completedCount = interviews.filter((i) => i.status === "completed").length;

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-slate-950 pb-16">
      {/* Background Subtle Gradient Glow */}
      <div className="absolute top-16 left-1/2 -translate-x-1/2 w-full max-w-7xl h-96 bg-indigo-600/10 blur-[120px] pointer-events-none rounded-full" />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 space-y-12 relative z-10">
        {/* Header Hero Section */}
        <div className="text-center space-y-4 max-w-3xl mx-auto">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Piattaforma Next-Gen di Trascrizione RAG</span>
          </div>
          <h1 className="text-3xl sm:text-5xl font-extrabold text-slate-100 tracking-tight leading-tight">
            Trasforma la tua voce in <br />
            <span className="gradient-text">Conoscenza Interrogabile</span>
          </h1>
          <p className="text-slate-400 text-sm sm:text-base leading-relaxed">
            Carica file audio, ottieni trascrizioni editoriali raffinate con Whisper AI ed effettua domande semantiche in linguaggio naturale sul tuo intero archivio.
          </p>
        </div>

        {/* Audio Uploader Component */}
        <section>
          <AudioUploader onUploadSuccess={() => fetchInterviews()} />
        </section>

        {/* Stats Section */}
        <section className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-4xl mx-auto">
          <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 flex items-center gap-4">
            <div className="p-3 rounded-xl bg-indigo-500/10 text-indigo-400">
              <Library className="w-6 h-6" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-100">{interviews.length}</p>
              <p className="text-xs text-slate-400">Interviste Totali</p>
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 flex items-center gap-4">
            <div className="p-3 rounded-xl bg-emerald-500/10 text-emerald-400">
              <FileCheck className="w-6 h-6" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-100">{completedCount}</p>
              <p className="text-xs text-slate-400">Completate & Indicizzate</p>
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 flex items-center gap-4">
            <div className="p-3 rounded-xl bg-purple-500/10 text-purple-400">
              <Layers className="w-6 h-6" />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-100">{totalTopics}</p>
              <p className="text-xs text-slate-400">Temi Chiave Estratti</p>
            </div>
          </div>
        </section>

        {/* Archive Section */}
        <section className="space-y-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
            <div>
              <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2">
                <HardDrive className="w-5 h-5 text-indigo-400" />
                <span>Archivio Interviste</span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">Gestisci ed esplora tutti i file audio elaborati</p>
            </div>

            {/* Search & Refresh */}
            <div className="flex items-center gap-3 w-full sm:w-auto">
              <div className="relative flex-1 sm:w-64">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Cerca per titolo o tema..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-4 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 placeholder-slate-400 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-3 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
              >
                <option value="all">Tutti gli stati</option>
                <option value="completed">Completate</option>
                <option value="processing">In corso</option>
                <option value="failed">Fallite</option>
              </select>

              <button
                type="button"
                onClick={fetchInterviews}
                className="p-2 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
                title="Ricarica lista"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              </button>
            </div>
          </div>

          {error && (
            <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 flex items-center gap-3 text-rose-300 text-sm">
              <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {loading && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {[1, 2, 3].map((n) => (
                <div key={n} className="h-48 rounded-2xl bg-slate-900/40 border border-slate-800/60 animate-pulse" />
              ))}
            </div>
          )}

          {!loading && filteredInterviews.length === 0 && (
            <div className="text-center py-16 px-4 rounded-2xl border border-dashed border-slate-800 bg-slate-900/20">
              <Library className="w-12 h-12 text-slate-600 mx-auto mb-3" />
              <p className="text-slate-300 font-semibold text-base">Nessuna intervista trovata</p>
              <p className="text-xs text-slate-400 mt-1">
                {searchQuery ? "Prova a cambiare i criteri di ricerca." : "Carica il tuo primo file audio per iniziare!"}
              </p>
            </div>
          )}

          {!loading && filteredInterviews.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredInterviews.map((interview) => (
                <InterviewCard key={interview.id} interview={interview} onDelete={handleDelete} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}