import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  Download,
  FileAudio,
  FileText,
  FileVideo,
  Globe,
  Lock,
  NotebookPen,
  ScrollText,
  Trash2,
  Upload,
} from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { Alert, Badge, Button, Dialog, Field, Input, Select, Textarea } from "@/components/ui";
import { api, assetUrl, unwrap, uploadSource, type Confidentiality, type Source } from "@/lib/api";
import { cn, formatBytes, formatDate } from "@/lib/utils";

export const typeLabel: Record<Source["type"], string> = {
  audio: "Audio",
  video: "Video",
  document: "Documento",
  web: "Pagina web",
  note: "Nota",
};

const typeIcon = (t: Source["type"]) =>
  ({
    audio: <FileAudio className="size-4" />,
    video: <FileVideo className="size-4" />,
    document: <FileText className="size-4" />,
    web: <Globe className="size-4" />,
    note: <NotebookPen className="size-4" />,
  })[t];

export const confidentialityLabel: Record<Confidentiality, string> = {
  normal: "Normale",
  confidential: "Riservata",
  secret: "Segreta",
};

function StatusBadge({ source }: { source: Source }) {
  switch (source.status) {
    case "uploaded":
    case "processing":
      return <Badge tone="accent">{source.status_detail?.startsWith("Trascrizione") ? source.status_detail : "In elaborazione"}</Badge>;
    case "failed":
      return <Badge tone="danger">Errore</Badge>;
    default:
      return null;
  }
}

function useInvalidateSources(workspaceId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["sources", workspaceId] });
    qc.invalidateQueries({ queryKey: ["stories", workspaceId] });
  };
}

export function SourceList({ workspaceId, sources }: { workspaceId: string; sources: Source[] }) {
  const [openId, setOpenId] = useState<string | null>(null);
  return (
    <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-surface">
      {sources.map((s) => (
        <SourceRow
          key={s.id}
          workspaceId={workspaceId}
          source={s}
          open={openId === s.id}
          onToggle={() => setOpenId(openId === s.id ? null : s.id)}
        />
      ))}
    </ul>
  );
}

function SourceRow({
  workspaceId,
  source,
  open,
  onToggle,
}: {
  workspaceId: string;
  source: Source;
  open: boolean;
  onToggle: () => void;
}) {
  const invalidate = useInvalidateSources(workspaceId);
  const original = source.assets.find((a) => a.kind === "original");
  const remove = useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/api/workspaces/{workspace_id}/sources/{source_id}", {
          params: { path: { workspace_id: workspaceId, source_id: source.id } },
        }),
      ),
    onSuccess: invalidate,
  });

  return (
    <li>
      <button onClick={onToggle} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-surface-2" aria-expanded={open}>
        <span className="text-muted">{typeIcon(source.type)}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{source.title}</span>
          <span className="block text-xs text-muted">
            {typeLabel[source.type]} · {source.source_date ? formatDate(source.source_date) : `caricata il ${formatDate(source.created_at)}`}
            {original && ` · ${formatBytes(original.size_bytes)}`}
          </span>
        </span>
        {source.confidentiality !== "normal" && (
          <Badge tone="warning">
            <Lock className="size-3" /> {confidentialityLabel[source.confidentiality]}
          </Badge>
        )}
        <StatusBadge source={source} />
      </button>

      {open && (
        <div className="space-y-3 border-t border-border bg-bg/50 px-4 py-4">
          {source.status_detail && <p className="text-xs text-muted">{source.status_detail}</p>}
          {original && source.type === "audio" && (
            <audio controls preload="metadata" className="w-full" src={assetUrl(workspaceId, original.id)} />
          )}
          {source.note_text && <p className="whitespace-pre-wrap text-sm">{source.note_text}</p>}
          {original && (
            <p className="font-mono text-[11px] text-muted" title="Impronta SHA-256 dell'originale">
              {original.filename} · sha256 {original.sha256.slice(0, 16)}…
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {(source.type === "audio" || source.type === "video") && (
              <Link to="/w/$workspaceId/fonti/$sourceId" params={{ workspaceId, sourceId: source.id }}>
                <Button size="sm">
                  <ScrollText className="size-3.5" /> {source.status === "ready" ? "Apri la trascrizione" : "Apri"}
                </Button>
              </Link>
            )}
            {original && (
              <a href={assetUrl(workspaceId, original.id, true)}>
                <Button variant="secondary" size="sm">
                  <Download className="size-3.5" /> Scarica originale
                </Button>
              </a>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="text-danger"
              loading={remove.isPending}
              onClick={() => {
                if (confirm(`Eliminare definitivamente "${source.title}"? Il file verrà cancellato e non sarà recuperabile.`))
                  remove.mutate();
              }}
            >
              <Trash2 className="size-3.5" /> Elimina
            </Button>
          </div>
          {remove.error && <Alert>{remove.error.message}</Alert>}
        </div>
      )}
    </li>
  );
}

type Pending = { name: string; progress: number; error?: string };

export function UploadZone({ workspaceId, storyId }: { workspaceId: string; storyId?: string }) {
  const invalidate = useInvalidateSources(workspaceId);
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [confidentiality, setConfidentiality] = useState<Confidentiality>("normal");
  const [sourceDate, setSourceDate] = useState("");
  const [pending, setPending] = useState<Pending[]>([]);

  const send = async (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      setPending((p) => [...p, { name: file.name, progress: 0 }]);
      const update = (patch: Partial<Pending>) =>
        setPending((p) => p.map((x) => (x.name === file.name ? { ...x, ...patch } : x)));
      const form = new FormData();
      form.append("file", file);
      form.append("confidentiality", confidentiality);
      if (sourceDate) form.append("source_date", sourceDate);
      if (storyId) form.append("story_id", storyId);
      try {
        await uploadSource(workspaceId, form, (progress) => update({ progress }));
        setPending((p) => p.filter((x) => x.name !== file.name));
        invalidate();
      } catch (e) {
        update({ error: (e as Error).message });
      }
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) send(e.dataTransfer.files);
  };

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => (e.preventDefault(), setDragging(true))}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition",
          dragging ? "border-accent bg-accent-soft" : "border-border bg-surface",
        )}
      >
        <Upload className="size-5 text-muted" />
        <p className="text-sm">
          Trascina qui registrazioni, video o documenti, oppure{" "}
          <button className="font-medium text-accent underline-offset-2 hover:underline" onClick={() => input.current?.click()}>
            sfoglia
          </button>
        </p>
        <p className="text-xs text-muted">MP3, M4A, WAV, OGG, MP4, PDF, DOCX, TXT</p>
        <input
          ref={input}
          type="file"
          multiple
          hidden
          accept="audio/*,video/*,.pdf,.docx,.odt,.txt,.md"
          onChange={(e) => e.target.files && send(e.target.files)}
        />
      </div>
      <div className="flex flex-wrap gap-3">
        <label className="flex items-center gap-2 text-xs text-muted">
          Riservatezza
          <Select className="h-8 w-auto text-xs" value={confidentiality} onChange={(e) => setConfidentiality(e.target.value as Confidentiality)}>
            <option value="normal">Normale</option>
            <option value="confidential">Riservata — solo elaborazione interna</option>
            <option value="secret">Segreta — esclusa da anteprime e log</option>
          </Select>
        </label>
        <label className="flex items-center gap-2 text-xs text-muted">
          Data dell'intervista
          <Input type="date" className="h-8 w-auto text-xs" value={sourceDate} onChange={(e) => setSourceDate(e.target.value)} />
        </label>
      </div>
      {pending.map((p) => (
        <div key={p.name} className="rounded-md border border-border bg-surface px-3 py-2 text-sm">
          <div className="flex justify-between gap-3">
            <span className="truncate">{p.name}</span>
            <span className="text-xs text-muted">{p.error ? "" : `${Math.round(p.progress * 100)}%`}</span>
          </div>
          {p.error ? (
            <p className="mt-1 text-xs text-danger">{p.error}</p>
          ) : (
            <div className="mt-1.5 h-1 overflow-hidden rounded bg-surface-2">
              <div className="h-full bg-accent transition-all" style={{ width: `${p.progress * 100}%` }} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export function NoteDialog({
  workspaceId,
  storyId,
  open,
  onClose,
}: {
  workspaceId: string;
  storyId?: string;
  open: boolean;
  onClose: () => void;
}) {
  const invalidate = useInvalidateSources(workspaceId);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/workspaces/{workspace_id}/sources/note", {
          params: { path: { workspace_id: workspaceId } },
          body: { title, text, story_id: storyId ?? null, confidentiality: "normal" },
        }),
      ),
    onSuccess: () => {
      invalidate();
      setTitle("");
      setText("");
      onClose();
    },
  });
  return (
    <Dialog open={open} onClose={onClose} title="Nuova nota">
      <form onSubmit={(e) => (e.preventDefault(), create.mutate())} className="space-y-4">
        {create.error && <Alert>{create.error.message}</Alert>}
        <Field label="Titolo" htmlFor="note-title">
          <Input id="note-title" required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Telefonata con l'ufficio stampa" />
        </Field>
        <Field label="Testo" htmlFor="note-text">
          <Textarea id="note-text" required rows={8} value={text} onChange={(e) => setText(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Annulla
          </Button>
          <Button type="submit" loading={create.isPending}>
            Salva nota
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
