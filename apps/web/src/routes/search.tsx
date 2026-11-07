import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { AlertTriangle, FileAudio, FileText, FileVideo, Globe, Lock, MessageSquareText, NotebookPen, Search as SearchIcon } from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { confidentialityLabel, typeLabel } from "@/components/sources";
import { Alert, Badge, Button, EmptyState, Input, PageHeader, Select, Spinner, Textarea } from "@/components/ui";
import { api, unwrap, type Schemas, type SourceType } from "@/lib/api";
import { cn, formatDate } from "@/lib/utils";
import { formatTime } from "@/routes/source";

type Hit = Schemas["SearchHit"];
type Mode = "cerca" | "chiedi";

const typeIcon: Record<SourceType, ReactNode> = {
  audio: <FileAudio className="size-4" />,
  video: <FileVideo className="size-4" />,
  document: <FileText className="size-4" />,
  web: <Globe className="size-4" />,
  note: <NotebookPen className="size-4" />,
};

/** Estratto con le parole trovate evidenziate (marcatori ⟦ ⟧ dal server, niente HTML). */
function Snippet({ text }: { text: string }) {
  const parts = text.split(/(⟦[^⟧]*⟧)/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("⟦") ? (
          <mark key={i} className="rounded-sm bg-warning-soft px-0.5 text-text">
            {p.slice(1, -1)}
          </mark>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  );
}

function Where({ hit }: { hit: Hit }) {
  const bits: string[] = [];
  if (hit.start != null) bits.push(formatTime(hit.start));
  if (hit.page != null) bits.push(`pag. ${hit.page}`);
  if (hit.speaker) bits.push(hit.speaker);
  return <span className="font-mono text-[11px] text-muted">{bits.join(" · ")}</span>;
}

function HitLink({ workspaceId, hit, children, className }: { workspaceId: string; hit: Hit; children: ReactNode; className?: string }) {
  return (
    <Link
      to="/w/$workspaceId/fonti/$sourceId"
      params={{ workspaceId, sourceId: hit.source_id }}
      search={{ seg: hit.segment_id }}
      className={className}
    >
      {children}
    </Link>
  );
}

type Filters = { type: SourceType | ""; storyId: string; from: string; to: string };

function FilterBar({ workspaceId, filters, onChange }: { workspaceId: string; filters: Filters; onChange: (f: Filters) => void }) {
  const stories = useQuery({
    queryKey: ["stories", workspaceId],
    queryFn: () => unwrap(api.GET("/api/workspaces/{workspace_id}/stories", { params: { path: { workspace_id: workspaceId } } })),
  });
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Select className="h-8 w-auto text-xs" value={filters.type} onChange={(e) => set({ type: e.target.value as SourceType | "" })} aria-label="Tipo di fonte">
        <option value="">Tutti i tipi</option>
        {Object.entries(typeLabel).map(([k, v]) => (
          <option key={k} value={k}>
            {v}
          </option>
        ))}
      </Select>
      <Select className="h-8 w-auto max-w-56 text-xs" value={filters.storyId} onChange={(e) => set({ storyId: e.target.value })} aria-label="Storia">
        <option value="">Tutte le storie</option>
        {stories.data?.map((s) => (
          <option key={s.id} value={s.id}>
            {s.title}
          </option>
        ))}
      </Select>
      <label className="flex items-center gap-1 text-muted">
        dal
        <Input type="date" className="h-8 w-auto text-xs" value={filters.from} onChange={(e) => set({ from: e.target.value })} />
      </label>
      <label className="flex items-center gap-1 text-muted">
        al
        <Input type="date" className="h-8 w-auto text-xs" value={filters.to} onChange={(e) => set({ to: e.target.value })} />
      </label>
    </div>
  );
}

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export function SearchPage() {
  const { workspaceId } = useParams({ strict: false }) as { workspaceId: string };
  const params = useSearch({ strict: false }) as { q?: string; mode?: Mode };
  const navigate = useNavigate();
  const mode: Mode = params.mode === "chiedi" ? "chiedi" : "cerca";
  const [filters, setFilters] = useState<Filters>({ type: "", storyId: "", from: "", to: "" });

  const setMode = (m: Mode) => navigate({ to: ".", search: { q: params.q, mode: m }, replace: true });

  return (
    <>
      <PageHeader title="Ricerca" subtitle="In tutte le fonti del workspace: interviste, documenti, pagine web e note." />
      <div className="mb-4 inline-flex rounded-md bg-surface-2 p-0.5" role="tablist">
        {(
          [
            ["cerca", "Cerca", <SearchIcon key="i" className="size-3.5" />],
            ["chiedi", "Chiedi all'archivio", <MessageSquareText key="i" className="size-3.5" />],
          ] as const
        ).map(([m, label, icon]) => (
          <button
            key={m}
            role="tab"
            aria-selected={mode === m}
            onClick={() => setMode(m)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium",
              mode === m ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text",
            )}
          >
            {icon}
            {label}
          </button>
        ))}
      </div>
      {mode === "cerca" ? (
        <SearchMode workspaceId={workspaceId} initial={params.q ?? ""} filters={filters} setFilters={setFilters} />
      ) : (
        <AskMode workspaceId={workspaceId} filters={filters} setFilters={setFilters} />
      )}
    </>
  );
}

function filterQuery(f: Filters) {
  return {
    ...(f.type ? { type: f.type } : {}),
    ...(f.storyId ? { story_id: f.storyId } : {}),
    ...(f.from ? { date_from: f.from } : {}),
    ...(f.to ? { date_to: f.to } : {}),
  };
}

function SearchMode({
  workspaceId,
  initial,
  filters,
  setFilters,
}: {
  workspaceId: string;
  initial: string;
  filters: Filters;
  setFilters: (f: Filters) => void;
}) {
  const navigate = useNavigate();
  const [q, setQ] = useState(initial);
  const query = useDebounced(q.trim(), 300);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => input.current?.focus(), []);
  // La query resta nell'indirizzo: tornando indietro da una fonte si ritrovano i risultati
  useEffect(() => {
    navigate({ to: ".", search: { q: query || undefined, mode: "cerca" }, replace: true });
  }, [query, navigate]);

  const results = useQuery({
    queryKey: ["search", workspaceId, query, filters],
    enabled: query.length > 0,
    placeholderData: (prev) => prev,
    queryFn: () =>
      unwrap(
        api.GET("/api/workspaces/{workspace_id}/search", {
          params: { path: { workspace_id: workspaceId }, query: { q: query, ...filterQuery(filters) } },
        }),
      ),
  });

  const groups = useMemo(() => {
    const m = new Map<string, Hit[]>();
    for (const h of results.data?.results ?? []) m.set(h.source_id, [...(m.get(h.source_id) ?? []), h]);
    return [...m.values()];
  }, [results.data]);

  return (
    <div className="space-y-4">
      <div className="relative">
        <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
        <Input
          ref={input}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder='Nomi, cifre, temi… usa le virgolette per una frase esatta, "-parola" per escludere'
          className="h-11 pl-9 text-base"
          aria-label="Cerca nell'archivio"
        />
      </div>
      <FilterBar workspaceId={workspaceId} filters={filters} onChange={setFilters} />
      {results.data && !results.data.semantic && (
        <Alert tone="warning">La ricerca per significato non è disponibile in questo momento: risultati solo per parole esatte.</Alert>
      )}
      {results.error && <Alert>{results.error.message}</Alert>}
      {results.isFetching && !results.data && <Spinner label="Cerco…" />}
      {query && results.data?.results.length === 0 && (
        <EmptyState icon={<SearchIcon className="size-6" />} title="Nessun risultato">
          Prova con altre parole o togli qualche filtro. Le fonti appena caricate diventano cercabili quando l'elaborazione è finita.
        </EmptyState>
      )}
      <ul className={cn("space-y-3", results.isFetching && "opacity-70")}>
        {groups.map((hits) => {
          const first = hits[0];
          return (
            <li key={first.source_id} className="overflow-hidden rounded-lg border border-border bg-surface">
              <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
                <span className="text-muted">{typeIcon[first.source_type]}</span>
                <HitLink workspaceId={workspaceId} hit={first} className="min-w-0 flex-1 truncate text-sm font-medium hover:text-accent">
                  {first.source_title}
                </HitLink>
                <span className="text-xs text-muted">{first.source_date ? formatDate(first.source_date) : typeLabel[first.source_type]}</span>
                {first.confidentiality !== "normal" && (
                  <Badge tone="warning">
                    <Lock className="size-3" /> {confidentialityLabel[first.confidentiality]}
                  </Badge>
                )}
              </div>
              <ul className="divide-y divide-border">
                {hits.map((h) => (
                  <li key={h.segment_id}>
                    <HitLink workspaceId={workspaceId} hit={h} className="block px-4 py-2.5 hover:bg-surface-2">
                      <div className="mb-0.5 flex items-center gap-2">
                        <Where hit={h} />
                        {h.matched.length === 1 && h.matched[0] === "significato" && (
                          <span className="text-[10px] uppercase tracking-wide text-muted/80">per significato</span>
                        )}
                      </div>
                      <p className="text-sm leading-relaxed">
                        <Snippet text={h.snippet} />
                      </p>
                    </HitLink>
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Risposta con i rimandi [n] resi cliccabili verso i passaggi elencati sotto. */
function AnswerText({ text, onCite }: { text: string; onCite: (n: number) => void }) {
  const parts = text.split(/(\[\d+\])/g);
  return (
    <p className="whitespace-pre-wrap text-[15px] leading-relaxed">
      {parts.map((p, i) => {
        const m = p.match(/^\[(\d+)\]$/);
        return m ? (
          <button
            key={i}
            onClick={() => onCite(Number(m[1]))}
            className="mx-0.5 rounded bg-accent-soft px-1 align-super text-[10px] font-semibold text-accent hover:bg-accent hover:text-accent-contrast"
            aria-label={`Vai al passaggio ${m[1]}`}
          >
            {m[1]}
          </button>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        );
      })}
    </p>
  );
}

function AskMode({ workspaceId, filters, setFilters }: { workspaceId: string; filters: Filters; setFilters: (f: Filters) => void }) {
  const [question, setQuestion] = useState("");
  const [focused, setFocused] = useState<number | null>(null);
  const ask = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/workspaces/{workspace_id}/ask", {
          params: { path: { workspace_id: workspaceId } },
          body: {
            question,
            type: filters.type || null,
            story_id: filters.storyId || null,
            date_from: filters.from || null,
            date_to: filters.to || null,
          },
        }),
      ),
    onSuccess: () => setFocused(null),
  });
  const cite = (n: number) => {
    setFocused(n);
    document.getElementById(`passaggio-${n}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  };
  const r = ask.data;

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => (e.preventDefault(), ask.mutate())} className="space-y-2">
        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.metaKey || e.ctrlKey) && ask.mutate()}
          placeholder="Es.: Cosa ha detto l'assessore sui costi del depuratore? Chi ha parlato di cassa integrazione?"
          className="min-h-20 text-base"
          autoFocus
          required
          minLength={3}
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <FilterBar workspaceId={workspaceId} filters={filters} onChange={setFilters} />
          <Button type="submit" loading={ask.isPending} disabled={question.trim().length < 3}>
            <MessageSquareText className="size-4" /> Chiedi
          </Button>
        </div>
      </form>
      <p className="text-xs text-muted">
        La risposta usa solo i passaggi dell'archivio e li cita uno per uno. Le fonti riservate vengono elaborate solo da un modello sul server.
      </p>
      {ask.error && <Alert>{ask.error.message}</Alert>}
      {ask.isPending && <Spinner label="Cerco i passaggi e preparo la risposta…" />}
      {r && (
        <div className="space-y-4">
          {r.unavailable_reason && (
            <Alert tone="warning">
              {r.unavailable_reason}.{r.passages.length > 0 && " Ecco i passaggi più pertinenti trovati."}
            </Alert>
          )}
          {r.answer && (
            <div className="rounded-lg border border-border bg-surface p-4">
              <AnswerText text={r.answer} onCite={cite} />
              {r.insufficient && <p className="mt-3 text-xs text-warning">Il materiale in archivio non basta per una risposta completa.</p>}
              {r.unverified_quotes.length > 0 && (
                <div className="mt-3 flex gap-2 rounded-md bg-danger-soft p-2 text-xs text-danger">
                  <AlertTriangle className="size-4 shrink-0" />
                  <span>
                    Queste citazioni non compaiono alla lettera nei passaggi: non usarle senza verificare.{" "}
                    {r.unverified_quotes.map((q) => `«${q}»`).join(" · ")}
                  </span>
                </div>
              )}
              <p className="mt-3 border-t border-border pt-2 text-[11px] text-muted">
                Risposta generata automaticamente ({r.model}): verifica sempre sulle fonti prima di pubblicare.
              </p>
            </div>
          )}
          {r.passages.length > 0 && (
            <div>
              <h2 className="mb-2 text-sm font-semibold text-muted">Passaggi usati</h2>
              <ol className="space-y-2">
                {r.passages.map((h, i) => (
                  <li
                    key={h.segment_id}
                    id={`passaggio-${i + 1}`}
                    className={cn("rounded-lg border bg-surface transition", focused === i + 1 ? "border-accent ring-2 ring-accent/30" : "border-border")}
                  >
                    <HitLink workspaceId={workspaceId} hit={h} className="flex gap-3 px-4 py-2.5 hover:bg-surface-2">
                      <span className="mt-0.5 shrink-0 font-mono text-xs font-semibold text-accent">[{i + 1}]</span>
                      <span className="min-w-0">
                        <span className="flex flex-wrap items-center gap-2 text-xs">
                          <span className="text-muted">{typeIcon[h.source_type]}</span>
                          <span className="font-medium">{h.source_title}</span>
                          <Where hit={h} />
                        </span>
                        <span className="mt-1 block text-sm leading-relaxed">
                          <Snippet text={h.snippet} />
                        </span>
                      </span>
                    </HitLink>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
