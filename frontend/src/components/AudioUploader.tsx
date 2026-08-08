"use client";

import { useState, useRef, ChangeEvent, DragEvent } from "react";
import { UploadCloud, FileAudio, CheckCircle2, AlertCircle, Loader2, X, Sparkles, Mic, FileUp } from "lucide-react";
import { UploadResponse } from "@/types";
import { API_BASE_URL } from "@/lib/api";
import AudioRecorder from "@/components/AudioRecorder";

interface AudioUploaderProps {
  onUploadSuccess?: (response: UploadResponse) => void;
}

export default function AudioUploader({ onUploadSuccess }: AudioUploaderProps) {
  const [activeTab, setActiveTab] = useState<"upload" | "record">("upload");

  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [statusText, setStatusText] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [successResponse, setSuccessResponse] = useState<UploadResponse | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const acceptedExtensions = [".mp3", ".wav", ".m4a", ".mp4", ".mpeg"];

  const validateFile = (selectedFile: File): boolean => {
    const ext = "." + selectedFile.name.split(".").pop()?.toLowerCase();
    if (!acceptedExtensions.includes(ext)) {
      setError(`Formato non supportato (${ext}). Usa file .mp3, .wav, .m4a o .mp4.`);
      return false;
    }
    if (selectedFile.size > 100 * 1024 * 1024) {
      setError("Il file supera il limite massimo di 100 MB.");
      return false;
    }
    setError(null);
    return true;
  };

  const handleFileSelect = (selectedFile: File) => {
    if (validateFile(selectedFile)) {
      setFile(selectedFile);
      setSuccessResponse(null);
    }
  };

  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const onDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const onInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileSelect(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setError(null);
    setStatusText("Invio file in corso...");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE_URL}/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => null);
        throw new Error(errorData?.detail || `Errore server (${res.status})`);
      }

      const data: UploadResponse = await res.json();
      setSuccessResponse(data);
      setFile(null);

      if (onUploadSuccess) {
        onUploadSuccess(data);
      }

      setTimeout(() => {
        setSuccessResponse(null);
      }, 2500);
    } catch (err: any) {
      setError(err.message || "Impossibile caricare l'intervista. Verificare che il backend sia attivo.");
    } finally {
      setUploading(false);
      setStatusText("");
    }
  };

  const resetSelection = () => {
    setFile(null);
    setError(null);
    setSuccessResponse(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <div className="w-full max-w-3xl mx-auto space-y-4">
      {/* Tab Switcher / Toggle Header */}
      <div className="flex items-center justify-center gap-2 p-1.5 rounded-2xl bg-slate-900/90 border border-slate-800/90 max-w-md mx-auto shadow-md">
        <button
          type="button"
          onClick={() => setActiveTab("upload")}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-bold transition-all duration-200 ${
            activeTab === "upload"
              ? "bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-md shadow-indigo-600/20"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
          }`}
        >
          <FileUp className="w-4 h-4" />
          <span>Carica File Audio</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("record")}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-bold transition-all duration-200 ${
            activeTab === "record"
              ? "bg-gradient-to-r from-rose-600 to-rose-700 text-white shadow-md shadow-rose-600/20"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
          }`}
        >
          <Mic className="w-4 h-4" />
          <span>Registra in App</span>
        </button>
      </div>

      {/* Tab Content 1: Upload File */}
      {activeTab === "upload" && (
        <div>
          <div
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => !uploading && fileInputRef.current?.click()}
            className={`relative border-2 border-dashed rounded-2xl p-8 transition-all duration-300 cursor-pointer text-center ${
              isDragging
                ? "border-indigo-400 bg-indigo-950/40 shadow-2xl shadow-indigo-500/20 scale-[1.01]"
                : file
                ? "border-indigo-500/60 bg-slate-900/80"
                : "border-slate-800 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-900/60"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".mp3,.wav,.m4a,.mp4,.mpeg"
              className="hidden"
              onChange={onInputChange}
              disabled={uploading}
            />

            {!file && !uploading && !successResponse && (
              <div className="flex flex-col items-center justify-center gap-3">
                <div className="p-4 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 group-hover:scale-110 transition-transform">
                  <UploadCloud className="w-10 h-10" />
                </div>
                <div>
                  <p className="text-base font-semibold text-slate-200">
                    Trascina qui il file audio dell'intervista o <span className="text-indigo-400 underline decoration-indigo-400/40">sfoglia i file</span>
                  </p>
                  <p className="text-xs text-slate-400 mt-1">
                    Formati supportati: MP3, WAV, M4A, MP4 (max 100MB)
                  </p>
                </div>
              </div>
            )}

            {file && !uploading && (
              <div className="flex flex-col items-center justify-center gap-4" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-800/80 border border-slate-700/80 max-w-md w-full justify-between">
                  <div className="flex items-center gap-3 overflow-hidden">
                    <FileAudio className="w-8 h-8 text-indigo-400 shrink-0" />
                    <div className="text-left truncate">
                      <p className="text-sm font-medium text-slate-100 truncate">{file.name}</p>
                      <p className="text-xs text-slate-400">{(file.size / (1024 * 1024)).toFixed(2)} MB</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={resetSelection}
                    className="p-1 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-700 transition-colors"
                    title="Rimuovi file"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <button
                  type="button"
                  onClick={handleUpload}
                  className="flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:scale-[1.02] active:scale-[0.98] transition-all duration-200"
                >
                  <Sparkles className="w-4 h-4" />
                  <span>Avvia Trascrizione & Polishing AI</span>
                </button>
              </div>
            )}

            {uploading && (
              <div className="flex flex-col items-center justify-center py-4 gap-4">
                <div className="relative">
                  <div className="w-16 h-16 rounded-full border-4 border-indigo-500/20 border-t-indigo-500 animate-spin" />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Sparkles className="w-6 h-6 text-indigo-400 animate-pulse" />
                  </div>
                </div>
                <div>
                  <p className="text-base font-semibold text-slate-100">{statusText}</p>
                  <p className="text-xs text-slate-400 mt-1">L'operazione potrebbe richiedere alcuni secondi per i file più lunghi.</p>
                </div>
              </div>
            )}

            {successResponse && !uploading && (
              <div className="flex flex-col items-center justify-center py-2 gap-3" onClick={(e) => e.stopPropagation()}>
                <div className="p-3 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                  <CheckCircle2 className="w-8 h-8" />
                </div>
                <div>
                  <p className="text-base font-bold text-slate-100">{successResponse.message}</p>
                  <p className="text-xs text-emerald-400/90 font-medium mt-1">
                    ID Intervista: #{successResponse.interview_id} &bull; Stato: {successResponse.status}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={resetSelection}
                  className="mt-2 text-xs text-slate-400 underline hover:text-slate-200"
                >
                  Carica un'altra intervista
                </button>
              </div>
            )}
          </div>

          {error && (
            <div className="mt-4 p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 flex items-center gap-3 text-rose-300 text-sm animate-shake">
              <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>
      )}

      {/* Tab Content 2: Registra in App */}
      {activeTab === "record" && (
        <AudioRecorder onUploadSuccess={onUploadSuccess} />
      )}
    </div>
  );
}
