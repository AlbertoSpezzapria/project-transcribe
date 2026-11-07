import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, ExternalLink, FileSearch, Pencil, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Alert, Badge, Button, Spinner } from "@/components/ui";
import { api, assetUrl, unwrap, type Schemas, type Source } from "@/lib/api";
import { cn, formatDate, formatDateTime } from "@/lib/utils";
import { JobProgress, SegmentEditor, useSegmentPatch } from "@/routes/source";

type Transcript = Schemas["TranscriptOut"];
type Segment = Schemas["SegmentOut"];

/** Lettore per documenti, pagine web e note: paragrafi citabili, pagine, correzioni. */
export function DocumentView({
  workspaceId,
  source: s,
  transcript: t,
  loading,
  seg,
}: {
  workspaceId: string;
  source: Source;
  transcript?: Transcript;
  loading: boolean;
  seg?: string;
}) {
  const original = s.assets.find((a) => a.kind === "original");
  const snapshot = s.assets.find((a) => a.kind === "derived" && a.mime_type === "text/html");
  const isPdf = original?.mime_type === "application/pdf";
  const meta = (s.metadata ?? {}) as Record<string, unknown>;
  const busy = s.status === "uploaded" || s.status === "processing";

  return (
    <div className="space-y-4">
      <SourceInfo workspaceId={workspaceId} source={s} meta={meta} />

      <div className="flex flex-wrap gap-2">
        {isPdf && original && (
          <a href={assetUrl(workspaceId, original.id)} target="_blank" rel="noopener noreferrer">
            <Button variant="secondary" size="sm">
              <FileSearch className="size-3.5" /> Apri il PDF
            </Button>
          </a>
        )}
        {snapshot && (
          <a href={assetUrl(workspaceId, snapshot.id)} target="_blank" rel="noopener noreferrer" title="La pagina com'era al momento dell'acquisizione">
            <Button variant="secondary" size="sm">
              <FileSearch className="size-3.5" /> Copia salvata della pagina
            </Button>
          </a>
        )}
        {s.url && (
          <a href={String(meta.final_url ?? s.url)} target="_blank" rel="noopener noreferrer nofollow">
            <Button variant="ghost" size="sm">
              <ExternalLink className="size-3.5" /> Pagina originale
            </Button>
          </a>
        )}
        {original && (
          <a href={assetUrl(workspaceId, original.id, true)}>
            <Button variant="ghost" size="sm">
              <Download className="size-3.5" /> Scarica l'originale
            </Button>
          </a>
        )}
        {t && t.segments.length > 0 && (
          <a href={`/api/workspaces/${workspaceId}/transcripts/${t.id}/export?format=txt`} download>
            <Button variant="ghost" size="sm">
              <Download className="size-3.5" /> Testo
            </Button>
          </a>
        )}
      </div>

      {busy && <JobProgress label={s.status_detail ?? "In elaborazione"} progress={null} />}
      {s.status === "failed" && <FailedBox workspaceId={workspaceId} source={s} />}
      {s.status === "ready" && s.status_detail && <Alert tone="warning">{s.status_detail}</Alert>}
      {typeof meta.ocr_pages === "number" && meta.ocr_pages > 0 && (
        <Alert tone="info">
          {meta.ocr_pages === 1 ? "Una pagina è stata letta" : `${meta.ocr_pages} pagine sono state lette`} con il riconoscimento ottico (OCR): il testo può contenere errori, controlla sull'originale prima di citare.
        </Alert>
      )}
      {loading && <Spinner />}
      {t && t.segments.length > 0 && (
        <Paragraphs
          workspaceId={workspaceId}
          sourceId={s.id}
          segments={t.segments}
          pdfAssetId={isPdf ? original?.id : undefined}
          seg={seg}
        />
      )}
    </div>
  );
}

function SourceInfo({ source: s, meta }: { workspaceId: string; source: Source; meta: Record<string, unknown> }) {
  const rows: [string, string][] = [];
  if (s.type === "web") {
    if (meta.site) rows.push(["Sito", String(meta.site)]);
    if (meta.author) rows.push(["Autore", String(meta.author)]);
    if (meta.published) rows.push(["Pubblicata", formatDate(String(meta.published).slice(0, 10))]);
    if (meta.fetched_at) rows.push(["Acquisita", formatDateTime(String(meta.fetched_at))]);
    if (s.url) rows.push(["Indirizzo", String(meta.final_url ?? s.url)]);
  }
  if (typeof meta.pages === "number") rows.push(["Pagine", String(meta.pages)]);
  if (!rows.length) return null;
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 rounded-lg border border-border bg-surface px-4 py-3 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="truncate" title={v}>
            {v}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function FailedBox({ workspaceId, source: s }: { workspaceId: string; source: Source }) {
  const qc = useQueryClient();
  const retry = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/workspaces/{workspace_id}/sources/{source_id}/reprocess", {
          params: { path: { workspace_id: workspaceId, source_id: s.id } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources", workspaceId] }),
  });
  return (
    <div className="space-y-2">
      <Alert>{s.status_detail ?? "Elaborazione non riuscita"}</Alert>
      {(s.type === "document" || s.type === "web") && (
        <Button variant="secondary" size="sm" onClick={() => retry.mutate()} loading={retry.isPending}>
          <RefreshCw className="size-3.5" /> Riprova
        </Button>
      )}
      {retry.error && <p className="text-xs text-danger">{retry.error.message}</p>}
    </div>
  );
}

function Paragraphs({
  workspaceId,
  sourceId,
  segments,
  pdfAssetId,
  seg,
}: {
  workspaceId: string;
  sourceId: string;
  segments: Segment[];
  pdfAssetId?: string;
  seg?: string;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!seg) return;
    const el = list.current?.querySelector(`[data-id="${seg}"]`);
    el?.scrollIntoView({ block: "center" });
    el?.classList.add("flash");
  }, [seg]);

  return (
    <div ref={list} className="rounded-lg border border-border bg-surface px-5 py-4 font-serif">
      {segments.map((p, i) => (
        <div key={p.id}>
          {p.page != null && p.page !== segments[i - 1]?.page && (
            <div className="mb-2 mt-4 flex items-center gap-3 font-sans text-[11px] uppercase tracking-wide text-muted first:mt-0">
              <span>Pagina {p.page}</span>
              <span className="h-px flex-1 bg-border" />
              {pdfAssetId && (
                <a
                  href={`${assetUrl(workspaceId, pdfAssetId)}#page=${p.page}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="normal-case tracking-normal hover:text-accent"
                >
                  apri nel PDF
                </a>
              )}
            </div>
          )}
          <ParagraphRow
            workspaceId={workspaceId}
            sourceId={sourceId}
            segment={p}
            editing={editing === p.id}
            setEditing={setEditing}
          />
        </div>
      ))}
    </div>
  );
}

function ParagraphRow({
  workspaceId,
  sourceId,
  segment: p,
  editing,
  setEditing,
}: {
  workspaceId: string;
  sourceId: string;
  segment: Segment;
  editing: boolean;
  setEditing: (id: string | null) => void;
}) {
  const patch = useSegmentPatch(workspaceId, sourceId);
  const text = p.text_edited ?? p.text_raw;
  if (editing) {
    return (
      <div className="my-2 font-sans">
        <SegmentEditor
          initial={text}
          raw={p.text_raw}
          saving={patch.isPending}
          onCancel={() => setEditing(null)}
          onSave={(value) => patch.mutate({ id: p.id, body: { text: value } }, { onSuccess: () => setEditing(null) })}
        />
      </div>
    );
  }
  return (
    <div data-id={p.id} className={cn("group relative -mx-2 rounded px-2 py-1.5")}>
      <p className="text-[16px] leading-relaxed">
        {text}
        {p.text_edited && (
          <Badge tone="success" className="ml-2 align-middle font-sans">
            corretto
          </Badge>
        )}
      </p>
      <button
        onClick={() => setEditing(p.id)}
        className="absolute -right-1 top-1 rounded p-1 text-muted opacity-0 transition hover:bg-surface-2 hover:text-text focus:opacity-100 group-hover:opacity-100"
        aria-label="Correggi il paragrafo"
        title="Correggi (es. errori dell'OCR)"
      >
        <Pencil className="size-3.5" />
      </button>
      {patch.error && <p className="font-sans text-xs text-danger">{patch.error.message}</p>}
    </div>
  );
}
