"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { 
  UploadCloud, 
  FileAudio, 
  CheckCircle2, 
  Clock, 
  AlertCircle, 
  Search, 
  MessageSquare,
  Sparkles,
  ArrowRight,
  Loader2
} from "lucide-react";
import { uploadAudio, getInterviews, InterviewSummary } from "@/lib/api";

export default function DashboardPage() {
  const [interviews, setInterviews] = useState<InterviewSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState<boolean>(false);

  // Caricamento dell'elenco interviste
  const fetchInterviewsList = useCallback(async () => {
    try {
      const data = await getInterviews();
      setInterviews(data);
    } catch (err) {
      console.error("Errore durante il recupero delle interviste:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInterviewsList();
  }, [fetchInterviewsList]);

  // Gestione Upload File
  const handleFileUpload = async (file: File) => {
    if (!file) return;

    // Validazione estensione
    const validExtensions = [".mp3", ".m4a", ".wav", ".mp4", ".mpeg"];
    const fileExtension = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    
    if (!validExtensions.includes(fileExtension)) {
      setUploadError("Formato non supportato. Usa MP3, M4A, WAV o MP4.");
      return;
    }

    setUploadError(null);
    setIsUploading(true);

    try {
      await uploadAudio(file);
      await fetchInterviewsList(); // Aggiorna la lista dopo il caricamento
    } catch (err: any) {
      setUploadError(err.message || "Errore durante il caricamento dell'audio.");
    } finally {
      setIsUploading(false);
    }
  };

  // Gestione Eventi Drag & Drop
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileUpload(e.target.files[0]);
    }
  };

  // Helper per il badge di stato
  const renderStatusBadge = (status: string) => {
    switch (status) {
      case "completed":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3 h-3" /> Raffinata AI
          </span>
        );
      case "completed_raw_only":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <CheckCircle2 className="w-3 h-3" /> Solo Grezza
          </span>
        );
      case "processing":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20 animate-pulse">
            <Clock className="w-3 h-3" /> Elaborazione...
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <AlertCircle className="w-3 h-3" /> Errore
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto px-4 py-8">
      {/* Header & Titolo */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2">
            Dashboard Interviste <Sparkles className="w-6 h-6 text-indigo-400" />
          </h1>
          <p className="text-slate-400 mt-1">
            Gestisci le trascrizioni, genera analisi editoriali ed interroga l'archivio con la RAG.
          </p>
        </div>
        <Link
          href="/chat"
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-colors shadow-lg shadow-indigo-600/20"
        >
          <MessageSquare className="w-4 h-4" /> Chat RAG Globale
        </Link>
      </div>

      {/* Sezione Drag & Drop Upload */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`relative border-2 border-dashed rounded-2xl p-8 text-center transition-all duration-200 ${
          isDragging
            ? "border-indigo-500 bg-indigo-500/10 scale-[1.01]"
            : "border-slate-800 bg-slate-900/50 hover:border-slate-700"
        }`}
      >
        <input
          type="file"
          id="audio-upload"
          accept=".mp3,.m4a,.wav,.mp4,.mpeg"
          onChange={handleFileSelect}
          disabled={isUploading}
          className="hidden"
        />

        <div className="flex flex-col items-center justify-center space-y-3">
          <div className="p-4 rounded-full bg-slate-800/80 text-indigo-400 border border-slate-700">
            {isUploading ? (
              <Loader2 className="w-8 h-8 animate-spin" />
            ) : (
              <UploadCloud className="w-8 h-8" />
            )}
          </div>

          <div className="space-y-1">
            <p className="text-lg font-medium text-white">
              {isUploading
                ? "Caricamento e trascrizione in corso..."
                : "Trascina qui il tuo file audio/video"}
            </p>
            <p className="text-sm text-slate-400">
              Supporta MP3, M4A, WAV, MP4 (fino a 500MB)
            </p>
          </div>

          {!isUploading && (
            <label
              htmlFor="audio-upload"
              className="mt-2 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium cursor-pointer border border-slate-700 transition-colors"
            >
              <FileAudio className="w-4 h-4 text-indigo-400" /> Seleziona un file
            </label>
          )}

          {uploadError && (
            <div className="mt-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {uploadError}
            </div>
          )}
        </div>
      </div>

      {/* Griglia delle ultime Interviste */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold text-white">Ultime Interviste</h2>
          <span className="text-sm text-slate-400">
            {interviews.length} trascrizioni in archivio
          </span>
        </div>

        {loading ? (
          <div className="flex justify-center items-center py-12">
            <Loader2 className="w-8 h-8 text-indigo-400 animate-spin" />
          </div>
        ) : interviews.length === 0 ? (
          <div className="text-center py-12 bg-slate-900/30 rounded-xl border border-slate-800">
            <FileAudio className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400 font-medium">Nessuna intervista presente.</p>
            <p className="text-slate-500 text-sm">Carica un file audio per iniziare.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {interviews.map((item) => (
              <Link
                key={item.id}
                href={`/interviews/${item.id}`}
                className="group block p-5 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-slate-700 transition-all duration-200 hover:shadow-lg hover:shadow-slate-950/50"
              >
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="flex items-center gap-2 overflow-hidden">
                    <FileAudio className="w-5 h-5 text-indigo-400 flex-shrink-0" />
                    <h3 className="font-semibold text-white truncate group-hover:text-indigo-300 transition-colors">
                      {item.filename}
                    </h3>
                  </div>
                  {renderStatusBadge(item.status)}
                </div>

                {item.summary ? (
                  <p className="text-sm text-slate-400 line-clamp-2 mb-4">
                    {item.summary}
                  </p>
                ) : (
                  <p className="text-sm text-slate-500 italic mb-4">
                    Sommario in elaborazione o non disponibile...
                  </p>
                )}

                {/* Key Topics Tag */}
                {item.key_topics && item.key_topics.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-4">
                    {item.key_topics.slice(0, 3).map((topic, i) => (
                      <span
                        key={i}
                        className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-xs"
                      >
                        #{topic}
                      </span>
                    ))}
                    {item.key_topics.length > 3 && (
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 text-xs">
                        +{item.key_topics.length - 3}
                      </span>
                    )}
                  </div>
                )}

                <div className="flex items-center justify-between pt-3 border-t border-slate-800/60 text-xs text-slate-500">
                  <span>ID #{item.id}</span>
                  <span className="flex items-center gap-1 text-indigo-400 font-medium group-hover:translate-x-1 transition-transform">
                    Dettagli <ArrowRight className="w-3 h-3" />
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}