"use client";

import { useState, useRef, useEffect } from "react";
import { Mic, Square, Pause, Play, RotateCcw, Sparkles, CheckCircle2, AlertCircle, Volume2 } from "lucide-react";
import { UploadResponse } from "@/types";
import { API_BASE_URL } from "@/lib/api";

interface AudioRecorderProps {
  onUploadSuccess?: (response: UploadResponse) => void;
}

export default function AudioRecorder({ onUploadSuccess }: AudioRecorderProps) {
  const [recordingState, setRecordingState] = useState<"idle" | "recording" | "paused" | "stopped">("idle");
  const [recordingTime, setRecordingTime] = useState(0);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successResponse, setSuccessResponse] = useState<UploadResponse | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const audioPreviewRef = useRef<HTMLAudioElement | null>(null);
  const [isPreviewPlaying, setIsPreviewPlaying] = useState(false);

  // Timer per la durata della registrazione
  useEffect(() => {
    if (recordingState === "recording") {
      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [recordingState]);

  const startRecording = async () => {
    setError(null);
    setSuccessResponse(null);
    audioChunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Scegli il miglior tipo MIME supportato dal browser
      let mimeType = "audio/webm";
      if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
        mimeType = "audio/webm;codecs=opus";
      } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
        mimeType = "audio/mp4";
      } else if (MediaRecorder.isTypeSupported("audio/ogg")) {
        mimeType = "audio/ogg";
      }

      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: mimeType });
        setAudioBlob(blob);
        const url = URL.createObjectURL(blob);
        setAudioUrl(url);

        // Ferma le traccia del microfono
        stream.getTracks().forEach((track) => track.stop());
      };

      recorder.start(200);
      setRecordingState("recording");
      setRecordingTime(0);
    } catch (err: any) {
      console.error("Errore di accesso al microfono:", err);
      setError("Impossibile accedere al microfono. Assicurati di aver concesso i permessi nel browser.");
    }
  };

  const pauseRecording = () => {
    if (mediaRecorderRef.current && recordingState === "recording") {
      mediaRecorderRef.current.pause();
      setRecordingState("paused");
    }
  };

  const resumeRecording = () => {
    if (mediaRecorderRef.current && recordingState === "paused") {
      mediaRecorderRef.current.resume();
      setRecordingState("recording");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && (recordingState === "recording" || recordingState === "paused")) {
      mediaRecorderRef.current.stop();
      setRecordingState("stopped");
    }
  };

  const resetRecording = () => {
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
    }
    setRecordingState("idle");
    setRecordingTime(0);
    setAudioBlob(null);
    setAudioUrl(null);
    setError(null);
    setSuccessResponse(null);
    setIsPreviewPlaying(false);
  };

  const togglePreviewPlay = () => {
    if (!audioPreviewRef.current) return;
    if (isPreviewPlaying) {
      audioPreviewRef.current.pause();
      setIsPreviewPlaying(false);
    } else {
      audioPreviewRef.current.play();
      setIsPreviewPlaying(true);
    }
  };

  const handleUploadRecordedAudio = async () => {
    if (!audioBlob) return;

    setUploading(true);
    setError(null);

    const now = new Date();
    const dateStr = now.toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const filename = `registrazione_${dateStr}.webm`;
    const audioFile = new File([audioBlob], filename, { type: audioBlob.type });

    const formData = new FormData();
    formData.append("file", audioFile);

    try {
      const res = await fetch(`${API_BASE_URL}/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || `Errore durante il caricamento (${res.status})`);
      }

      const data: UploadResponse = await res.json();
      setSuccessResponse(data);

      if (onUploadSuccess) {
        onUploadSuccess(data);
      }

      setTimeout(() => {
        resetRecording();
      }, 2500);
    } catch (err: any) {
      setError(err.message || "Errore durante l'invio della registrazione.");
    } finally {
      setUploading(false);
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div className="w-full max-w-3xl mx-auto">
      <div className="relative border-2 border-slate-800 rounded-2xl p-8 bg-slate-900/60 backdrop-blur-md text-center transition-all duration-300">
        {/* Stato IDLE: Avvia Registrazione */}
        {recordingState === "idle" && !successResponse && (
          <div className="flex flex-col items-center justify-center gap-4 py-4">
            <button
              type="button"
              onClick={startRecording}
              className="group relative flex items-center justify-center w-20 h-20 rounded-full bg-rose-600 hover:bg-rose-500 text-white shadow-xl shadow-rose-600/30 hover:scale-105 active:scale-95 transition-all duration-200"
              title="Avvia Registrazione Vocale"
            >
              <Mic className="w-9 h-9" />
              <span className="absolute -inset-1 rounded-full border-2 border-rose-500/40 animate-ping pointer-events-none" />
            </button>
            <div>
              <p className="text-base font-semibold text-slate-200">Clicca per avviare la registrazione vocale</p>
              <p className="text-xs text-slate-400 mt-1">L'applicazione ti chiederà l'accesso al microfono del browser</p>
            </div>
          </div>
        )}

        {/* Stato RECORDING o PAUSED */}
        {(recordingState === "recording" || recordingState === "paused") && (
          <div className="flex flex-col items-center justify-center gap-6 py-2">
            {/* Timer & Pulsing Wave Indicator */}
            <div className="flex flex-col items-center gap-2">
              <div className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-semibold">
                <span className={`w-2.5 h-2.5 rounded-full bg-rose-500 ${recordingState === "recording" ? "animate-ping" : ""}`} />
                <span>{recordingState === "recording" ? "Registrazione In Corso..." : "In Pausa"}</span>
              </div>
              <span className="text-4xl font-extrabold font-mono tracking-wider text-slate-100">
                {formatTime(recordingTime)}
              </span>
            </div>

            {/* Wave animation simulator */}
            {recordingState === "recording" && (
              <div className="flex items-center gap-1.5 h-8">
                {[40, 70, 30, 90, 50, 80, 40, 100, 60, 30].map((height, i) => (
                  <span
                    key={i}
                    style={{ height: `${height}%` }}
                    className="w-1.5 rounded-full bg-indigo-500 animate-pulse"
                  />
                ))}
              </div>
            )}

            {/* Controlli durante la registrazione */}
            <div className="flex items-center gap-4">
              {recordingState === "recording" ? (
                <button
                  type="button"
                  onClick={pauseRecording}
                  className="p-3.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
                  title="Metti in pausa"
                >
                  <Pause className="w-5 h-5 fill-current" />
                </button>
              ) : (
                <button
                  type="button"
                  onClick={resumeRecording}
                  className="p-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
                  title="Riprendi registrazione"
                >
                  <Play className="w-5 h-5 fill-current ml-0.5" />
                </button>
              )}

              <button
                type="button"
                onClick={stopRecording}
                className="flex items-center gap-2 px-5 py-3 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-semibold shadow-lg shadow-rose-600/25 transition-all"
                title="Ferma registrazione"
              >
                <Square className="w-4 h-4 fill-current" />
                <span>Ferma Registrazione</span>
              </button>
            </div>
          </div>
        )}

        {/* Stato STOPPED: Anteprima Audio & Invio */}
        {recordingState === "stopped" && audioUrl && !successResponse && (
          <div className="flex flex-col items-center justify-center gap-5 py-2">
            <audio
              ref={audioPreviewRef}
              src={audioUrl}
              onEnded={() => setIsPreviewPlaying(false)}
            />

            <div className="w-full max-w-md p-4 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={togglePreviewPlay}
                  className="p-3 rounded-xl bg-indigo-600 text-white hover:bg-indigo-500 transition-colors"
                >
                  {isPreviewPlaying ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current ml-0.5" />}
                </button>
                <div className="text-left">
                  <p className="text-xs font-semibold text-slate-200">Anteprima Registrazione</p>
                  <p className="text-[11px] text-slate-400 font-mono">Durata: {formatTime(recordingTime)}</p>
                </div>
              </div>

              <button
                type="button"
                onClick={resetRecording}
                disabled={uploading}
                className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
                title="Rincomincia registrazione"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={resetRecording}
                disabled={uploading}
                className="px-4 py-2.5 rounded-xl border border-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-800 text-xs font-semibold transition-colors"
              >
                Annulla
              </button>

              <button
                type="button"
                onClick={handleUploadRecordedAudio}
                disabled={uploading}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white font-semibold text-xs shadow-lg shadow-indigo-500/25 hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 transition-all"
              >
                {uploading ? (
                  <>
                    <div className="w-4 h-4 rounded-full border-2 border-white/20 border-t-white animate-spin" />
                    <span>Invio in corso...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    <span>Avvia Trascrizione & Polishing AI</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Notifica di successo */}
        {successResponse && (
          <div className="flex flex-col items-center justify-center py-2 gap-3">
            <div className="p-3 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <CheckCircle2 className="w-8 h-8" />
            </div>
            <div>
              <p className="text-base font-bold text-slate-100">{successResponse.message}</p>
              <p className="text-xs text-emerald-400/90 font-medium mt-1">
                ID Intervista: #{successResponse.interview_id} &bull; Stato: {successResponse.status}
              </p>
            </div>
          </div>
        )}
      </div>

      {error && (
        <div className="mt-4 p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 flex items-center gap-3 text-rose-300 text-sm">
          <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
