import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import {
  ArrowLeft,
  Check,
  Download,
  Gauge,
  Lock,
  Pause,
  Pencil,
  Play,
  RefreshCw,
  RotateCcw,
  RotateCw,
  Sparkles,
  Undo2,
  UserPlus,
  X,
} from "lucide-react";
import { memo, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { confidentialityLabel, typeLabel } from "@/components/sources";
import { Alert, Badge, Button, Dialog, Field, Input, Select, Spinner, Textarea } from "@/components/ui";
import { api, ApiError, assetUrl, unwrap, type Schemas } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";

type Transcript = Schemas["TranscriptOut"];
type Segment = Schemas["SegmentOut"];
type Speaker = Schemas["SpeakerOut"];

const BUSY = ["queued", "processing"];

export function formatTime(t: number) {
  const s = Math.max(0, Math.floor(t));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

const speakerColor = (i: number) => `var(--spk-${(i % 6) + 1})`;
const speakerName = (s?: Speaker) => (s ? s.name || s.label : "Senza voce");

/** Indice dell'ultimo elemento con start <= t (ricerca binaria). */
function findAt<T>(items: T[], t: number, start: (x: T) => number) {
  let lo = 0;
  let hi = items.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (start(items[mid]) <= t) {
      ans = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return ans;
}

function isTyping(el: EventTarget | null) {
  const node = el as HTMLElement | null;
  return !!node && (node.tagName === "INPUT" || node.tagName === "TEXTAREA" || node.tagName === "SELECT" || node.isContentEditable);
}

// --- Pagina ----------------------------------------------------------------------

export function SourcePage() {
  const { workspaceId, sourceId } = useParams({ strict: false }) as { workspaceId: string; sourceId: string };
  const path = { workspace_id: workspaceId, source_id: sourceId };

  const source = useQuery({
    queryKey: ["sources", workspaceId, sourceId],
    queryFn: () => unwrap(api.GET("/api/workspaces/{workspace_id}/sources/{source_id}", { params: { path } })),
    refetchInterval: (q) => (q.state.data && ["uploaded", "processing"].includes(q.state.data.status) ? 3000 : false),
  });
  const isMedia = source.data?.type === "audio" || source.data?.type === "video";
  const transcript = useQuery({
    queryKey: ["transcript", workspaceId, sourceId],
    enabled: isMedia,
    retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2,
    // openapi-fetch allarga le tuple delle parole: il tipo dichiarato è quello dello schema
    queryFn: async () =>
      (await unwrap(
        api.GET("/api/workspaces/{workspace_id}/sources/{source_id}/transcript", { params: { path } }),
      )) as unknown as Transcript,
    refetchInterval: (q) => {
      const t = q.state.data;
      if (!t) return source.data?.status === "processing" ? 3000 : false;
      const busy = BUSY.includes(t.status) || BUSY.includes(t.clean_status) || (t.pending && BUSY.includes(t.pending.status));
      return busy ? 3000 : false;
    },
  });

  if (source.isLoading) return <Spinner />;
  if (source.error) return <Alert>{source.error.message}</Alert>;
  const s = source.data!;
  const original = s.assets.find((a) => a.kind === "original");

  return (
    <>
      <Link to="/w/$workspaceId/archivio" params={{ workspaceId }} className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-3.5" /> Archivio
      </Link>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="font-serif text-2xl font-semibold tracking-tight">{s.title}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
            {typeLabel[s.type]} · {s.source_date ? formatDate(s.source_date) : `caricata il ${formatDate(s.created_at)}`}
            {s.confidentiality !== "normal" && (
              <Badge tone="warning">
                <Lock className="size-3" /> {confidentialityLabel[s.confidentiality]}
              </Badge>
            )}
          </p>
        </div>
        {isMedia && transcript.data && <TranscriptActions workspaceId={workspaceId} sourceId={sourceId} transcript={transcript.data} />}
      </div>

      {!isMedia && (
        <div className="space-y-3">
          {s.note_text && <p className="whitespace-pre-wrap rounded-lg border border-border bg-surface p-4 text-sm">{s.note_text}</p>}
          {original && (
            <a href={assetUrl(workspaceId, original.id, true)}>
              <Button variant="secondary">
                <Download className="size-4" /> Scarica l'originale
              </Button>
            </a>
          )}
          <p className="text-sm text-muted">L'anteprima e la ricerca nei documenti arrivano con la Fase 3.</p>
        </div>
      )}

      {isMedia && original && (
        <>
          {transcript.isLoading && <Spinner />}
          {transcript.error && !(transcript.error instanceof ApiError && transcript.error.status === 404) && (
            <Alert>{transcript.error.message}</Alert>
          )}
          {!transcript.data && !transcript.isLoading && (
            <JobProgress label={s.status_detail ?? "In attesa"} progress={null} failed={s.status === "failed"} />
          )}
          {transcript.data && (
            <TranscriptWorkspace
              workspaceId={workspaceId}
              sourceId={sourceId}
              mediaUrl={assetUrl(workspaceId, original.id)}
              isVideo={s.type === "video"}
              transcript={transcript.data}
              statusDetail={s.status_detail}
            />
          )}
        </>
      )}
    </>
  );
}

function JobProgress({ label, progress, failed }: { label: string; progress: number | null; failed?: boolean }) {
  if (failed) return <Alert>{label}</Alert>;
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="text-sm">{label}</p>
      <div className="mt-2 h-1.5 overflow-hidden rounded bg-surface-2">
        {progress === null ? (
          <div className="h-full w-1/3 animate-pulse rounded bg-accent/60" />
        ) : (
          <div className="h-full bg-accent transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
        )}
      </div>
      <p className="mt-2 text-xs text-muted">
        La trascrizione avviene sul server, senza inviare l'audio all'esterno. Puoi chiudere la pagina: il lavoro continua.
      </p>
    </div>
  );
}

// --- Azioni sulla trascrizione ------------------------------------------------------

function TranscriptActions({ workspaceId, sourceId, transcript }: { workspaceId: string; sourceId: string; transcript: Transcript }) {
  const qc = useQueryClient();
  const [retranscribe, setRetranscribe] = useState(false);
  const versions = useQuery({
    queryKey: ["transcript-versions", workspaceId, sourceId, transcript.id, transcript.pending?.status],
    queryFn: () =>
      unwrap(
        api.GET("/api/workspaces/{workspace_id}/sources/{source_id}/transcripts", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
        }),
      ),
  });
  const activate = useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.POST("/api/workspaces/{workspace_id}/transcripts/{transcript_id}/activate", {
          params: { path: { workspace_id: workspaceId, transcript_id: id } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["transcript", workspaceId, sourceId] }),
  });
  const ready = (versions.data ?? []).filter((v) => v.status === "ready");
  const exportUrl = (format: "txt" | "srt", text: "edited" | "clean" = "edited") =>
    `/api/workspaces/${workspaceId}/transcripts/${transcript.id}/export?format=${format}&text=${text}`;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {ready.length > 1 && (
        <Select
          className="h-8 w-auto text-xs"
          aria-label="Versione della trascrizione"
          value={transcript.id}
          onChange={(e) => activate.mutate(e.target.value)}
        >
          {ready.map((v, i) => (
            <option key={v.id} value={v.id}>
              Versione {ready.length - i} · {v.model} · {formatDate(v.created_at)}
            </option>
          ))}
        </Select>
      )}
      {transcript.status === "ready" && (
        <>
          <a href={exportUrl("txt")} download>
            <Button variant="secondary" size="sm">
              <Download className="size-3.5" /> Testo
            </Button>
          </a>
          <a href={exportUrl("srt")} download>
            <Button variant="secondary" size="sm">
              <Download className="size-3.5" /> Sottotitoli
            </Button>
          </a>
        </>
      )}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setRetranscribe(true)}
        disabled={BUSY.includes(transcript.status) || (!!transcript.pending && BUSY.includes(transcript.pending.status))}
      >
        <RefreshCw className="size-3.5" /> Ritrascrivi
      </Button>
      <RetranscribeDialog
        workspaceId={workspaceId}
        sourceId={sourceId}
        open={retranscribe}
        onClose={() => setRetranscribe(false)}
        hasEdits={transcript.segments.some((s) => s.edited_at)}
      />
    </div>
  );
}

function RetranscribeDialog({
  workspaceId,
  sourceId,
  open,
  onClose,
  hasEdits,
}: {
  workspaceId: string;
  sourceId: string;
  open: boolean;
  onClose: () => void;
  hasEdits: boolean;
}) {
  const qc = useQueryClient();
  const [language, setLanguage] = useState("it");
  const run = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/workspaces/{workspace_id}/sources/{source_id}/transcribe", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
          body: { language: language === "auto" ? null : language },
        }),
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transcript", workspaceId, sourceId] });
      qc.invalidateQueries({ queryKey: ["sources", workspaceId] });
      onClose();
    },
  });
  return (
    <Dialog open={open} onClose={onClose} title="Nuova trascrizione">
      <form onSubmit={(e) => (e.preventDefault(), run.mutate())} className="space-y-4">
        {run.error && <Alert>{run.error.message}</Alert>}
        <Field label="Lingua dell'audio" htmlFor="stt-lang">
          <Select id="stt-lang" value={language} onChange={(e) => setLanguage(e.target.value)}>
            <option value="it">Italiano</option>
            <option value="en">Inglese</option>
            <option value="auto">Riconoscimento automatico</option>
          </Select>
        </Field>
        <p className="text-sm text-muted">
          Viene creata una nuova versione. Finché non è pronta continui a vedere quella attuale.
          {hasEdits && " Le correzioni che hai fatto restano nella versione attuale, che potrai riattivare in qualsiasi momento."}
        </p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Annulla
          </Button>
          <Button type="submit" loading={run.isPending}>
            Avvia
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

// --- Area di lavoro: player + trascrizione + interlocutori ---------------------------

function TranscriptWorkspace({
  workspaceId,
  sourceId,
  mediaUrl,
  isVideo,
  transcript: t,
  statusDetail,
}: {
  workspaceId: string;
  sourceId: string;
  mediaUrl: string;
  isVideo: boolean;
  transcript: Transcript;
  statusDetail: string | null;
}) {
  const mediaRef = useRef<HTMLMediaElement | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<"verbatim" | "clean">("verbatim");
  const [follow, setFollow] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const editingRef = useRef<string | null>(null);
  editingRef.current = editingId;
  const followRef = useRef(follow);
  followRef.current = follow;

  const speakerIndex = useMemo(() => new Map(t.speakers.map((s, i) => [s.id, i])), [t.speakers]);
  const segments = t.segments;

  const seek = useCallback((time: number, play = true) => {
    const m = mediaRef.current;
    if (!m) return;
    m.currentTime = Math.max(0, time);
    if (play) void m.play();
  }, []);

  // Evidenziazione della parola corrente: direttamente sul DOM, senza ri-renderizzare
  // migliaia di parole a ogni frame.
  const active = useRef<{ seg: number; word: Element | null }>({ seg: -1, word: null });
  const sync = useCallback(
    (time: number) => {
      const list = listRef.current;
      if (!list) return;
      const si = findAt(segments, time, (s) => s.start);
      const cur = active.current;
      if (si !== cur.seg) {
        list.querySelector(".seg-row.is-current")?.classList.remove("is-current");
        const row = si >= 0 ? list.querySelector(`[data-seg="${si}"]`) : null;
        row?.classList.add("is-current");
        if (row && followRef.current && !editingRef.current && !mediaRef.current?.paused) {
          row.scrollIntoView({ block: "center", behavior: "smooth" });
        }
        cur.seg = si;
      }
      let word: Element | null = null;
      if (si >= 0 && time <= segments[si].end + 0.3) {
        const words = segments[si].words;
        const wi = findAt(words, time, (w) => w[1]);
        if (wi >= 0 && time <= words[wi][2] + 0.25) {
          word = list.querySelector(`[data-seg="${si}"] [data-w="${wi}"]`);
        }
      }
      if (word !== cur.word) {
        cur.word?.classList.remove("is-active");
        word?.classList.add("is-active");
        cur.word = word;
      }
    },
    [segments],
  );

  const busy = BUSY.includes(t.status);
  if (busy || t.status === "failed") {
    return (
      <div className="space-y-4">
        <JobProgress
          label={t.status === "failed" ? (t.error ?? "Trascrizione non riuscita") : (statusDetail ?? "In coda per la trascrizione")}
          progress={t.status === "processing" ? t.progress : null}
          failed={t.status === "failed"}
        />
        {t.status === "failed" && <RetryButton workspaceId={workspaceId} sourceId={sourceId} />}
        <MediaPlayer ref={mediaRef} src={mediaUrl} isVideo={isVideo} peaks={t.peaks} segments={[]} speakerIndex={speakerIndex} onTime={() => {}} duration={t.duration} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {t.pending && (
        <Alert tone={t.pending.status === "failed" ? "danger" : "info"}>
          {t.pending.status === "failed"
            ? `La nuova trascrizione non è riuscita: ${t.pending.error ?? "errore"}. Resta attiva questa versione.`
            : `Nuova trascrizione in corso (${Math.round(t.pending.progress * 100)}%). Quando è pronta sostituisce questa versione.`}
        </Alert>
      )}
      <div className="sticky top-0 z-10 -mx-1 bg-bg/95 px-1 pb-2 pt-1 backdrop-blur">
        <MediaPlayer
          ref={mediaRef}
          src={mediaUrl}
          isVideo={isVideo}
          peaks={t.peaks}
          segments={segments}
          speakerIndex={speakerIndex}
          onTime={sync}
          duration={t.duration}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_16rem]">
        <section>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <ModeSwitch workspaceId={workspaceId} sourceId={sourceId} transcript={t} mode={mode} setMode={setMode} />
            <label className="flex items-center gap-2 text-xs text-muted">
              <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
              Segui l'audio
            </label>
          </div>
          {mode === "clean" && (
            <Alert tone="warning">
              Versione pulita, generata automaticamente per la lettura: non usarla per le citazioni tra virgolette.
            </Alert>
          )}
          {segments.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted">
              Nessun parlato riconosciuto in questo file.
            </p>
          ) : (
            <div ref={listRef} className="mt-2 overflow-hidden rounded-lg border border-border bg-surface">
              <SegmentList
                workspaceId={workspaceId}
                sourceId={sourceId}
                segments={segments}
                speakers={t.speakers}
                speakerIndex={speakerIndex}
                transcriptId={t.id}
                mode={mode}
                editingId={editingId}
                setEditingId={setEditingId}
                seek={seek}
              />
            </div>
          )}
          <p className="mt-3 text-xs text-muted">
            Clic su una parola per ascoltarla · <Kbd>Spazio</Kbd> play/pausa · <Kbd>←</Kbd> <Kbd>→</Kbd> 5 secondi ·{" "}
            <Kbd>Alt</Kbd>+<Kbd>K</Kbd> play/pausa anche mentre scrivi · le parole sottolineate a puntini sono incerte
          </p>
        </section>
        <SpeakersPanel workspaceId={workspaceId} sourceId={sourceId} transcript={t} speakerIndex={speakerIndex} />
      </div>
    </div>
  );
}

function Kbd({ children }: { children: string }) {
  return <kbd className="rounded border border-border bg-surface px-1 font-mono text-[10px]">{children}</kbd>;
}

function RetryButton({ workspaceId, sourceId }: { workspaceId: string; sourceId: string }) {
  const qc = useQueryClient();
  const run = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/workspaces/{workspace_id}/sources/{source_id}/transcribe", {
          params: { path: { workspace_id: workspaceId, source_id: sourceId } },
          body: { language: "it" },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["transcript", workspaceId, sourceId] }),
  });
  return (
    <Button variant="secondary" onClick={() => run.mutate()} loading={run.isPending}>
      <RefreshCw className="size-4" /> Riprova
    </Button>
  );
}

// --- Player --------------------------------------------------------------------------

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];

type PlayerProps = {
  src: string;
  isVideo: boolean;
  peaks: number[] | null;
  segments: Segment[];
  speakerIndex: Map<string, number>;
  onTime: (t: number) => void;
  duration: number | null;
};

const MediaPlayer = memo(function MediaPlayer({
  ref,
  src,
  isVideo,
  peaks,
  segments,
  speakerIndex,
  onTime,
  duration: knownDuration,
}: PlayerProps & { ref: React.RefObject<HTMLMediaElement | null> }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(knownDuration ?? 0);
  const [speed, setSpeed] = useState(1);

  // Ciclo di aggiornamento mentre l'audio va: ora, forma d'onda, parola evidenziata
  useEffect(() => {
    const m = ref.current;
    if (!m) return;
    let raf = 0;
    const tick = () => {
      setTime(m.currentTime);
      onTime(m.currentTime);
      if (!m.paused) raf = requestAnimationFrame(tick);
    };
    const onPlay = () => {
      setPlaying(true);
      raf = requestAnimationFrame(tick);
    };
    const onPause = () => {
      setPlaying(false);
      cancelAnimationFrame(raf);
      tick();
    };
    const onMeta = () => Number.isFinite(m.duration) && setDuration(m.duration);
    m.addEventListener("play", onPlay);
    m.addEventListener("pause", onPause);
    m.addEventListener("seeked", tick);
    m.addEventListener("loadedmetadata", onMeta);
    return () => {
      cancelAnimationFrame(raf);
      m.removeEventListener("play", onPlay);
      m.removeEventListener("pause", onPause);
      m.removeEventListener("seeked", tick);
      m.removeEventListener("loadedmetadata", onMeta);
    };
  }, [ref, onTime]);

  // Scorciatoie da tastiera
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const m = ref.current;
      if (!m) return;
      const toggle = () => (m.paused ? void m.play() : m.pause());
      if (e.altKey && e.code === "KeyK") {
        e.preventDefault();
        toggle();
        return;
      }
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.code === "Space") {
        e.preventDefault();
        toggle();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        m.currentTime = Math.max(0, m.currentTime - 5);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        m.currentTime = m.currentTime + 5;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ref]);

  // Forma d'onda con le regioni degli interlocutori
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth;
    const h = c.clientHeight;
    if (c.width !== w * dpr) {
      c.width = w * dpr;
      c.height = h * dpr;
    }
    const ctx = c.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const styles = getComputedStyle(c);
    const muted = styles.getPropertyValue("--border").trim() || "#ccc";
    const accent = styles.getPropertyValue("--accent").trim() || "#1f4ed8";
    const total = duration || 1;
    const stripH = 4;
    const waveH = h - stripH - 2;
    const playedX = (time / total) * w;
    if (peaks?.length) {
      const bar = w / peaks.length;
      for (let i = 0; i < peaks.length; i++) {
        const x = i * bar;
        const ph = Math.max(1, peaks[i] * waveH);
        ctx.fillStyle = x < playedX ? accent : muted;
        ctx.fillRect(x, (waveH - ph) / 2, Math.max(1, bar - 0.5), ph);
      }
    } else {
      ctx.fillStyle = muted;
      ctx.fillRect(0, waveH / 2 - 1, w, 2);
      ctx.fillStyle = accent;
      ctx.fillRect(0, waveH / 2 - 1, playedX, 2);
    }
    for (const s of segments) {
      const idx = s.speaker_id ? (speakerIndex.get(s.speaker_id) ?? 0) : 0;
      ctx.fillStyle = styles.getPropertyValue(`--spk-${(idx % 6) + 1}`).trim();
      ctx.fillRect((s.start / total) * w, h - stripH, Math.max(1, ((s.end - s.start) / total) * w), stripH);
    }
    ctx.fillStyle = accent;
    ctx.fillRect(playedX - 0.5, 0, 1, waveH);
  }, [peaks, time, duration, segments, speakerIndex]);

  const onCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const m = ref.current;
    const rect = e.currentTarget.getBoundingClientRect();
    if (m && duration) m.currentTime = ((e.clientX - rect.left) / rect.width) * duration;
  };
  const toggle = () => {
    const m = ref.current;
    if (m) (m.paused ? void m.play() : m.pause());
  };
  const skip = (d: number) => {
    const m = ref.current;
    if (m) m.currentTime = Math.max(0, m.currentTime + d);
  };

  const MediaTag = isVideo ? "video" : "audio";
  return (
    <div className="rounded-lg border border-border bg-surface p-3">
      <MediaTag
        ref={ref as React.RefObject<HTMLVideoElement>}
        src={src}
        preload="metadata"
        className={isVideo ? "mb-3 max-h-72 w-full rounded bg-black" : "hidden"}
      />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Button size="md" className="size-9 shrink-0 rounded-full p-0" aria-label={playing ? "Pausa" : "Riproduci"} onClick={toggle}>
          {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
        </Button>
        <button className="rounded p-1 text-muted hover:bg-surface-2" aria-label="Indietro di 5 secondi" onClick={() => skip(-5)}>
          <RotateCcw className="size-4" />
        </button>
        <button className="rounded p-1 text-muted hover:bg-surface-2" aria-label="Avanti di 5 secondi" onClick={() => skip(5)}>
          <RotateCw className="size-4" />
        </button>
        <canvas
          ref={canvas}
          onClick={onCanvasClick}
          className="order-last h-12 min-w-0 basis-full cursor-pointer sm:order-none sm:basis-0 sm:flex-1"
          role="slider"
          aria-label="Posizione nella registrazione"
          aria-valuemin={0}
          aria-valuemax={Math.round(duration)}
          aria-valuenow={Math.round(time)}
        />
        <span className="w-24 shrink-0 font-mono text-xs tabular-nums text-muted max-sm:ml-auto sm:text-right">
          {formatTime(time)} / {formatTime(duration)}
        </span>
        <label className="flex shrink-0 items-center gap-1 text-xs text-muted" title="Velocità">
          <Gauge className="size-3.5" />
          <select
            className="rounded bg-transparent text-xs"
            value={speed}
            onChange={(e) => {
              const v = Number(e.target.value);
              setSpeed(v);
              if (ref.current) ref.current.playbackRate = v;
            }}
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
});

// --- Modalità di lettura --------------------------------------------------------------

function ModeSwitch({
  workspaceId,
  sourceId,
  transcript: t,
  mode,
  setMode,
}: {
  workspaceId: string;
  sourceId: string;
  transcript: Transcript;
  mode: "verbatim" | "clean";
  setMode: (m: "verbatim" | "clean") => void;
}) {
  const qc = useQueryClient();
  const clean = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/workspaces/{workspace_id}/transcripts/{transcript_id}/clean", {
          params: { path: { workspace_id: workspaceId, transcript_id: t.id } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["transcript", workspaceId, sourceId] }),
  });
  const cleanBusy = BUSY.includes(t.clean_status);
  const tab = (m: "verbatim" | "clean", label: string, disabled = false) => (
    <button
      disabled={disabled}
      onClick={() => setMode(m)}
      className={cn(
        "rounded px-2.5 py-1 text-xs font-medium disabled:opacity-40",
        mode === m ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text",
      )}
    >
      {label}
    </button>
  );
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="inline-flex rounded-md bg-surface-2 p-0.5" role="tablist" aria-label="Versione del testo">
        {tab("verbatim", "Verbatim")}
        {tab("clean", "Pulita", t.clean_status !== "ready")}
      </div>
      {t.clean_status !== "ready" && !cleanBusy && (
        <Button
          variant="ghost"
          size="sm"
          disabled={!t.clean_available}
          title={t.clean_unavailable_reason ?? "Toglie intercalari e ripetizioni, senza cambiare nomi e cifre"}
          onClick={() => clean.mutate()}
          loading={clean.isPending}
        >
          <Sparkles className="size-3.5" /> Genera versione pulita
        </Button>
      )}
      {t.clean_status === "ready" && (
        <Button variant="ghost" size="sm" onClick={() => clean.mutate()} loading={clean.isPending} title="Rigenera dopo le correzioni">
          <RefreshCw className="size-3.5" /> Rigenera
        </Button>
      )}
      {cleanBusy && <span className="text-xs text-muted">Versione pulita in preparazione…</span>}
      {!t.clean_available && t.clean_status !== "ready" && (
        <span className="text-xs text-muted">{t.clean_unavailable_reason}</span>
      )}
      {t.clean_status === "failed" && <span className="text-xs text-danger">{t.clean_error}</span>}
      {t.clean_status === "ready" && t.clean_error && <span className="text-xs text-muted">{t.clean_error}</span>}
      {clean.error && <span className="text-xs text-danger">{clean.error.message}</span>}
    </div>
  );
}

// --- Segmenti ------------------------------------------------------------------------

type ListProps = {
  workspaceId: string;
  sourceId: string;
  segments: Segment[];
  speakers: Speaker[];
  speakerIndex: Map<string, number>;
  transcriptId: string;
  mode: "verbatim" | "clean";
  editingId: string | null;
  setEditingId: (id: string | null) => void;
  seek: (t: number, play?: boolean) => void;
};

const SegmentList = memo(function SegmentList(props: ListProps) {
  return (
    <>
      {props.segments.map((s, i) => (
        <SegmentRow
          key={s.id}
          {...props}
          segment={s}
          position={i}
          editing={props.editingId === s.id}
          continued={i > 0 && props.segments[i - 1].speaker_id === s.speaker_id}
        />
      ))}
    </>
  );
});

function useSegmentPatch(workspaceId: string, sourceId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, body }: { id: string; body: Schemas["SegmentUpdate"] }) =>
      (await unwrap(
        api.PATCH("/api/workspaces/{workspace_id}/segments/{segment_id}", {
          params: { path: { workspace_id: workspaceId, segment_id: id } },
          body,
        }),
      )) as unknown as Segment,
    // Aggiorna solo il segmento nella cache, senza ricaricare l'intera trascrizione
    onSuccess: (seg) =>
      qc.setQueryData<Transcript>(["transcript", workspaceId, sourceId], (t) =>
        t ? { ...t, segments: t.segments.map((s) => (s.id === seg.id ? seg : s)) } : t,
      ),
  });
}

const SegmentRow = memo(function SegmentRow({
  workspaceId,
  sourceId,
  segment: s,
  position,
  speakers,
  speakerIndex,
  transcriptId,
  mode,
  editing,
  continued,
  setEditingId,
  seek,
}: ListProps & { segment: Segment; position: number; editing: boolean; continued: boolean }) {
  const qc = useQueryClient();
  const patch = useSegmentPatch(workspaceId, sourceId);
  const speaker = speakers.find((sp) => sp.id === s.speaker_id);
  const color = s.speaker_id ? speakerColor(speakerIndex.get(s.speaker_id) ?? 0) : "var(--text-muted)";
  const verbatim = s.text_edited ?? s.text_raw;
  const spaced = s.words.some((w) => w[0].startsWith(" "));

  const [newSpeaker, setNewSpeaker] = useState(false);
  const onSpeakerChange = (value: string) => {
    if (value === "__new") setNewSpeaker(true);
    else patch.mutate({ id: s.id, body: { speaker_id: value || null } });
  };

  let body: React.ReactNode;
  if (editing) {
    body = (
      <SegmentEditor
        initial={verbatim}
        raw={s.text_raw}
        saving={patch.isPending}
        onCancel={() => setEditingId(null)}
        onSave={(text) => patch.mutate({ id: s.id, body: { text } }, { onSuccess: () => setEditingId(null) })}
      />
    );
  } else if (mode === "clean") {
    body = (
      <p className="cursor-pointer text-[15px] leading-relaxed" onClick={() => seek(s.start)}>
        {s.text_clean ?? (
          <>
            {verbatim} <span className="text-xs text-muted">(non semplificato)</span>
          </>
        )}
      </p>
    );
  } else if (s.text_edited) {
    body = (
      <p className="cursor-pointer text-[15px] leading-relaxed" onClick={() => seek(s.start)} title="Testo corretto: clic per ascoltare il passaggio">
        {s.text_edited}
      </p>
    );
  } else {
    body = (
      <p className="text-[15px] leading-relaxed">
        {s.words.map((w, i) => (
          // Lo spazio iniziale del modello indica una parola nuova ("l'" + "ufficio" restano uniti).
          // Le trascrizioni senza questa informazione separano sempre le parole.
          <span key={i}>
            {i > 0 && (!spaced || w[0].startsWith(" ")) ? " " : ""}
            <span
              data-w={i}
              className={cn("w", w[3] < 0.5 && "low")}
              title={w[3] < 0.5 ? "Parola incerta: verifica ascoltando" : undefined}
              onClick={() => seek(w[1])}
            >
              {w[0].trim()}
            </span>
          </span>
        ))}
      </p>
    );
  }

  return (
    <div
      data-seg={position}
      className={cn(
        "seg-row group grid grid-cols-[7rem_minmax(0,1fr)] gap-3 px-4 max-sm:grid-cols-1",
        continued ? "pb-2 pt-0.5" : "pb-2 pt-3",
        !continued && position > 0 && "border-t border-border",
      )}
    >
      <div className="flex flex-col items-start gap-1 text-xs max-sm:flex-row max-sm:items-center max-sm:gap-3">
        <select
          aria-label="Interlocutore"
          value={s.speaker_id ?? ""}
          onChange={(e) => onSpeakerChange(e.target.value)}
          className={cn(
            "max-w-full truncate rounded bg-transparent font-semibold hover:bg-surface-2",
            // Stessa voce del passaggio precedente: etichetta nascosta finché non ci si passa sopra
            continued && "opacity-0 focus:opacity-100 group-hover:opacity-100",
          )}
          style={{ color }}
        >
          {!speaker && <option value="">Senza voce</option>}
          {speakers.map((sp) => (
            <option key={sp.id} value={sp.id}>
              {speakerName(sp)}
            </option>
          ))}
          <option value="__new">+ Nuovo…</option>
        </select>
        <button className="font-mono text-muted tabular-nums hover:text-accent" onClick={() => seek(s.start)} title="Ascolta da qui">
          {formatTime(s.start)}
        </button>
        {s.text_edited && !editing && <Badge tone="success">corretto</Badge>}
      </div>
      <div className="relative min-w-0">
        {body}
        {!editing && (
          <button
            onClick={() => setEditingId(s.id)}
            className="absolute -right-1 -top-1 rounded p-1 text-muted opacity-0 transition hover:bg-surface-2 hover:text-text focus:opacity-100 group-hover:opacity-100"
            aria-label="Correggi il passaggio"
            title="Correggi"
          >
            <Pencil className="size-3.5" />
          </button>
        )}
        {patch.error && <p className="mt-1 text-xs text-danger">{patch.error.message}</p>}
      </div>
      {newSpeaker && (
        <NewSpeakerDialog
          workspaceId={workspaceId}
          sourceId={sourceId}
          transcriptId={transcriptId}
          onClose={() => setNewSpeaker(false)}
          onCreated={async (sp) => {
            await patch.mutateAsync({ id: s.id, body: { speaker_id: sp.id } });
            qc.invalidateQueries({ queryKey: ["transcript", workspaceId, sourceId] });
          }}
        />
      )}
    </div>
  );
});

function NewSpeakerDialog({
  workspaceId,
  sourceId,
  transcriptId,
  onClose,
  onCreated,
}: {
  workspaceId: string;
  sourceId: string;
  transcriptId: string;
  onClose: () => void;
  onCreated?: (sp: Speaker) => Promise<void>;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: async () => {
      const sp = await unwrap(
        api.POST("/api/workspaces/{workspace_id}/transcripts/{transcript_id}/speakers", {
          params: { path: { workspace_id: workspaceId, transcript_id: transcriptId } },
          body: { name: name.trim() },
        }),
      );
      await onCreated?.(sp);
      return sp;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transcript", workspaceId, sourceId] });
      onClose();
    },
  });
  return (
    <Dialog open onClose={onClose} title="Nuovo interlocutore">
      <form onSubmit={(e) => (e.preventDefault(), create.mutate())} className="space-y-4">
        {create.error && <Alert>{create.error.message}</Alert>}
        <Field label="Nome" hint="Come vuoi che compaia nella trascrizione e nelle citazioni." htmlFor="speaker-name">
          <Input id="speaker-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Assessore Mario Rossi" />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Annulla
          </Button>
          <Button type="submit" loading={create.isPending}>
            Aggiungi
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function SegmentEditor({
  initial,
  raw,
  saving,
  onSave,
  onCancel,
}: {
  initial: string;
  raw: string;
  saving: boolean;
  onSave: (text: string | null) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState(initial);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);
  useEffect(() => {
    const el = ref.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
    }
  }, [text]);
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Escape") onCancel();
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onSave(text);
  };
  return (
    <div className="space-y-2">
      <Textarea ref={ref} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey} className="min-h-0 resize-none text-[15px] leading-relaxed" />
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => onSave(text)} loading={saving}>
          <Check className="size-3.5" /> Salva
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>
          <X className="size-3.5" /> Annulla
        </Button>
        {initial !== raw && (
          <Button size="sm" variant="ghost" onClick={() => onSave(null)} title="Torna al testo riconosciuto automaticamente">
            <Undo2 className="size-3.5" /> Ripristina originale
          </Button>
        )}
        <span className="text-xs text-muted">⌘/Ctrl+Invio per salvare · Esc per annullare</span>
      </div>
    </div>
  );
}

// --- Interlocutori ---------------------------------------------------------------------

function SpeakersPanel({
  workspaceId,
  sourceId,
  transcript: t,
  speakerIndex,
}: {
  workspaceId: string;
  sourceId: string;
  transcript: Transcript;
  speakerIndex: Map<string, number>;
}) {
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: ["transcript", workspaceId, sourceId] });
  const stats = useMemo(() => {
    const m = new Map<string, { n: number; secs: number }>();
    for (const s of t.segments) {
      if (!s.speaker_id) continue;
      const v = m.get(s.speaker_id) ?? { n: 0, secs: 0 };
      v.n += 1;
      v.secs += s.end - s.start;
      m.set(s.speaker_id, v);
    }
    return m;
  }, [t.segments]);

  const rename = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      unwrap(
        api.PATCH("/api/workspaces/{workspace_id}/speakers/{speaker_id}", {
          params: { path: { workspace_id: workspaceId, speaker_id: id } },
          body: { name },
        }),
      ),
    onSuccess: refresh,
  });
  const merge = useMutation({
    mutationFn: ({ id, into }: { id: string; into: string }) =>
      unwrap(
        api.POST("/api/workspaces/{workspace_id}/speakers/{speaker_id}/merge", {
          params: { path: { workspace_id: workspaceId, speaker_id: id } },
          body: { into_id: into },
        }),
      ),
    onSuccess: refresh,
  });
  const [adding, setAdding] = useState(false);

  return (
    <aside className="space-y-3 lg:sticky lg:top-28 lg:self-start">
      <div className="rounded-lg border border-border bg-surface p-3">
        <h2 className="text-sm font-semibold">Interlocutori</h2>
        <p className="mt-0.5 text-xs text-muted">
          {t.diarized
            ? "Voci riconosciute automaticamente: dai un nome a ciascuna, unisci quelle doppie."
            : "Riconoscimento delle voci non attivo: assegna i passaggi dal menu accanto a ciascuno."}
        </p>
        <ul className="mt-3 space-y-3">
          {t.speakers.map((sp) => {
            const st = stats.get(sp.id);
            return (
              <li key={sp.id} className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="size-2.5 shrink-0 rounded-full" style={{ background: speakerColor(speakerIndex.get(sp.id) ?? 0) }} />
                  <Input
                    key={sp.name ?? ""}
                    defaultValue={sp.name ?? ""}
                    placeholder={sp.label}
                    aria-label={`Nome di ${sp.label}`}
                    className="h-7 text-xs"
                    onBlur={(e) => {
                      if (e.target.value.trim() !== (sp.name ?? "")) rename.mutate({ id: sp.id, name: e.target.value.trim() });
                    }}
                    onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                  />
                </div>
                <div className="flex items-center justify-between gap-2 pl-4 text-[11px] text-muted">
                  <span>{st ? `${st.n} passaggi · ${formatTime(st.secs)}` : "nessun passaggio"}</span>
                  {t.speakers.length > 1 && (
                    <select
                      className="rounded bg-transparent hover:bg-surface-2"
                      value=""
                      aria-label={`Unisci ${speakerName(sp)} a un altro interlocutore`}
                      onChange={(e) => {
                        const into = e.target.value;
                        const target = t.speakers.find((x) => x.id === into);
                        if (into && confirm(`Unire "${speakerName(sp)}" a "${speakerName(target)}"? I suoi passaggi passano all'altro.`))
                          merge.mutate({ id: sp.id, into });
                      }}
                    >
                      <option value="">Unisci a…</option>
                      {t.speakers
                        .filter((x) => x.id !== sp.id)
                        .map((x) => (
                          <option key={x.id} value={x.id}>
                            {speakerName(x)}
                          </option>
                        ))}
                    </select>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
        <Button
          variant="ghost"
          size="sm"
          className="mt-3"
          onClick={() => setAdding(true)}
        >
          <UserPlus className="size-3.5" /> Aggiungi
        </Button>
        {adding && (
          <NewSpeakerDialog workspaceId={workspaceId} sourceId={sourceId} transcriptId={t.id} onClose={() => setAdding(false)} />
        )}
        {(rename.error || merge.error) && <p className="mt-2 text-xs text-danger">{(rename.error || merge.error)!.message}</p>}
      </div>
      <p className="px-1 text-[11px] leading-relaxed text-muted">
        Modello: {t.model} · lingua {t.detected_language ?? t.language ?? "auto"}
        {t.duration ? ` · ${formatTime(t.duration)}` : ""}. Il testo riconosciuto resta conservato anche dopo le correzioni.
      </p>
    </aside>
  );
}
