import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { ArrowLeft, FileText, Inbox, NotebookPen, Plus } from "lucide-react";
import { useState } from "react";

import { NoteDialog, SourceList, typeLabel, UploadZone } from "@/components/sources";
import { Alert, Badge, Button, Dialog, EmptyState, Field, Input, PageHeader, Select, Spinner, Textarea } from "@/components/ui";
import { api, unwrap, type Source, type SourceType, type Story } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

const statusLabel: Record<Story["status"], string> = {
  active: "In corso",
  published: "Pubblicata",
  archived: "Archiviata",
};

// Finché una fonte è in elaborazione, ricarica l'elenco ogni pochi secondi.
const pollWhileProcessing = (q: { state: { data?: Source[] } }) =>
  q.state.data?.some((s) => s.status === "uploaded" || s.status === "processing") ? 3000 : false;

function useWorkspaceId() {
  return (useParams({ strict: false }) as { workspaceId: string }).workspaceId;
}

export function StoriesPage() {
  const workspaceId = useWorkspaceId();
  const [creating, setCreating] = useState(false);
  const stories = useQuery({
    queryKey: ["stories", workspaceId],
    queryFn: () =>
      unwrap(api.GET("/api/workspaces/{workspace_id}/stories", { params: { path: { workspace_id: workspaceId } } })),
  });

  return (
    <>
      <PageHeader
        title="Storie"
        subtitle="Ogni storia raccoglie le sue fonti: interviste, documenti, note."
        actions={
          <Button onClick={() => setCreating(true)}>
            <Plus className="size-4" /> Nuova storia
          </Button>
        }
      />
      {stories.isLoading && <Spinner />}
      {stories.error && <Alert>{stories.error.message}</Alert>}
      {stories.data?.length === 0 && (
        <EmptyState
          icon={<FileText className="size-6" />}
          title="Nessuna storia ancora"
          action={<Button onClick={() => setCreating(true)}>Crea la prima storia</Button>}
        >
          Crea una storia per ogni vicenda che segui, poi caricaci registrazioni e documenti.
        </EmptyState>
      )}
      {!!stories.data?.length && (
        <ul className="grid gap-3 sm:grid-cols-2">
          {stories.data.map((s) => (
            <li key={s.id}>
              <Link
                to="/w/$workspaceId/storie/$storyId"
                params={{ workspaceId, storyId: s.id }}
                className="block h-full rounded-lg border border-border bg-surface p-4 transition hover:border-accent/50"
              >
                <div className="flex items-start justify-between gap-2">
                  <h2 className="font-medium leading-snug">{s.title}</h2>
                  {s.status !== "active" && <Badge>{statusLabel[s.status]}</Badge>}
                </div>
                {s.description && <p className="mt-1 line-clamp-2 text-sm text-muted">{s.description}</p>}
                <p className="mt-3 text-xs text-muted">
                  {s.source_count === 1 ? "1 fonte" : `${s.source_count} fonti`} · aggiornata {formatDateTime(s.updated_at)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <CreateStoryDialog workspaceId={workspaceId} open={creating} onClose={() => setCreating(false)} />
    </>
  );
}

function CreateStoryDialog({ workspaceId, open, onClose }: { workspaceId: string; open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/workspaces/{workspace_id}/stories", {
          params: { path: { workspace_id: workspaceId } },
          body: { title, description: description || null },
        }),
      ),
    onSuccess: (story) => {
      qc.invalidateQueries({ queryKey: ["stories", workspaceId] });
      onClose();
      setTitle("");
      setDescription("");
      navigate({ to: "/w/$workspaceId/storie/$storyId", params: { workspaceId, storyId: story.id } });
    },
  });
  return (
    <Dialog open={open} onClose={onClose} title="Nuova storia">
      <form onSubmit={(e) => (e.preventDefault(), create.mutate())} className="space-y-4">
        {create.error && <Alert>{create.error.message}</Alert>}
        <Field label="Titolo" htmlFor="story-title">
          <Input id="story-title" required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ritardi nel cantiere della tangenziale" autoFocus />
        </Field>
        <Field label="Descrizione" hint="Facoltativa: di cosa si tratta, cosa resta da verificare." htmlFor="story-desc">
          <Textarea id="story-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Annulla
          </Button>
          <Button type="submit" loading={create.isPending}>
            Crea storia
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function StoryPage() {
  const { workspaceId, storyId } = useParams({ strict: false }) as { workspaceId: string; storyId: string };
  const [noteOpen, setNoteOpen] = useState(false);
  const path = { workspace_id: workspaceId, story_id: storyId };
  const story = useQuery({
    queryKey: ["stories", workspaceId, storyId],
    queryFn: () => unwrap(api.GET("/api/workspaces/{workspace_id}/stories/{story_id}", { params: { path } })),
  });
  const sources = useQuery({
    queryKey: ["sources", workspaceId, { storyId }],
    queryFn: () => unwrap(api.GET("/api/workspaces/{workspace_id}/stories/{story_id}/sources", { params: { path } })),
    refetchInterval: pollWhileProcessing,
  });

  if (story.isLoading) return <Spinner />;
  if (story.error) return <Alert>{story.error.message}</Alert>;
  const s = story.data!;

  return (
    <>
      <Link to="/w/$workspaceId/storie" params={{ workspaceId }} className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-3.5" /> Storie
      </Link>
      <PageHeader
        title={s.title}
        subtitle={s.description}
        actions={
          <Button variant="secondary" onClick={() => setNoteOpen(true)}>
            <NotebookPen className="size-4" /> Nota
          </Button>
        }
      />
      <section className="space-y-6">
        <UploadZone workspaceId={workspaceId} storyId={storyId} />
        <div>
          <h2 className="mb-2 text-sm font-semibold text-muted">Fonti della storia</h2>
          {sources.isLoading && <Spinner />}
          {sources.data?.length === 0 && (
            <EmptyState icon={<Inbox className="size-6" />} title="Nessuna fonte">
              Carica la registrazione di un'intervista o un documento per iniziare.
            </EmptyState>
          )}
          {!!sources.data?.length && <SourceList workspaceId={workspaceId} sources={sources.data} />}
        </div>
      </section>
      <NoteDialog workspaceId={workspaceId} storyId={storyId} open={noteOpen} onClose={() => setNoteOpen(false)} />
    </>
  );
}

export function ArchivePage() {
  const workspaceId = useWorkspaceId();
  const [type, setType] = useState<SourceType | "">("");
  const sources = useQuery({
    queryKey: ["sources", workspaceId, { type }],
    queryFn: () =>
      unwrap(
        api.GET("/api/workspaces/{workspace_id}/sources", {
          params: { path: { workspace_id: workspaceId }, query: type ? { type } : {} },
        }),
      ),
    refetchInterval: pollWhileProcessing,
  });
  return (
    <>
      <PageHeader
        title="Archivio fonti"
        subtitle="Tutto il materiale del workspace, anche quello non ancora assegnato a una storia."
        actions={
          <Select className="w-44" value={type} onChange={(e) => setType(e.target.value as SourceType | "")} aria-label="Filtra per tipo">
            <option value="">Tutti i tipi</option>
            {Object.entries(typeLabel).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Select>
        }
      />
      <div className="space-y-6">
        <UploadZone workspaceId={workspaceId} />
        {sources.isLoading && <Spinner />}
        {sources.data?.length === 0 && (
          <EmptyState icon={<Inbox className="size-6" />} title="L'archivio è vuoto">
            Le fonti caricate qui o dentro una storia compaiono in questo elenco.
          </EmptyState>
        )}
        {!!sources.data?.length && <SourceList workspaceId={workspaceId} sources={sources.data} />}
      </div>
    </>
  );
}

export function ComingSoon({ title, phase, children }: { title: string; phase: string; children: string }) {
  return (
    <>
      <PageHeader title={title} />
      <EmptyState icon={<Badge tone="accent">{phase}</Badge>} title="In arrivo">
        {children}
      </EmptyState>
    </>
  );
}
