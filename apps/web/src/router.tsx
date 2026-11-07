import type { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, createRoute, createRouter, Outlet, redirect } from "@tanstack/react-router";

import { Shell } from "@/components/Shell";
import { authQuery, routeForStep } from "@/lib/auth";
import { LoginPage, MfaSetupPage, MfaVerifyPage } from "@/routes/auth";
import { ArchivePage, ComingSoon, StoriesPage, StoryPage } from "@/routes/pages";

type Ctx = { queryClient: QueryClient };

const root = createRootRouteWithContext<Ctx>()({ component: Outlet });

/** Ogni pagina di accesso è raggiungibile solo nel passo giusto del flusso. */
const authStep = <P extends string>(path: P, step: string, component: () => React.JSX.Element) =>
  createRoute({
    getParentRoute: () => root,
    path,
    component,
    beforeLoad: async ({ context }) => {
      const auth = await context.queryClient.fetchQuery(authQuery);
      if (auth.step !== step) throw redirect({ to: routeForStep(auth.step) ?? "/" });
    },
  });

const login = authStep("/accesso", "none", LoginPage);
const mfaSetup = authStep("/accesso/configura-2fa", "mfa_setup", MfaSetupPage);
const mfaVerify = authStep("/accesso/verifica", "mfa_verify", MfaVerifyPage);

const authed = createRoute({
  getParentRoute: () => root,
  id: "authed",
  component: Outlet,
  beforeLoad: async ({ context }) => {
    const auth = await context.queryClient.fetchQuery(authQuery);
    const target = routeForStep(auth.step);
    if (target) throw redirect({ to: target });
    return { auth };
  },
});

const home = createRoute({
  getParentRoute: () => authed,
  path: "/",
  beforeLoad: ({ context }) => {
    const ws = context.auth.workspaces[0];
    if (ws) throw redirect({ to: "/w/$workspaceId/storie", params: { workspaceId: ws.id } });
  },
  component: () => (
    <main className="flex min-h-dvh items-center justify-center p-6 text-center text-sm text-muted">
      Il tuo account non fa ancora parte di nessun workspace. Chiedi all'amministratore di aggiungerti.
    </main>
  ),
});

const workspace = createRoute({
  getParentRoute: () => authed,
  path: "/w/$workspaceId",
  component: Shell,
  beforeLoad: ({ context, params }) => {
    if (!context.auth.workspaces.some((w) => w.id === params.workspaceId)) throw redirect({ to: "/" });
  },
});

const wsIndex = createRoute({
  getParentRoute: () => workspace,
  path: "/",
  beforeLoad: ({ params }) => {
    throw redirect({ to: "/w/$workspaceId/storie", params });
  },
});
const stories = createRoute({ getParentRoute: () => workspace, path: "/storie", component: StoriesPage });
const story = createRoute({ getParentRoute: () => workspace, path: "/storie/$storyId", component: StoryPage });
const archive = createRoute({ getParentRoute: () => workspace, path: "/archivio", component: ArchivePage });
const search = createRoute({
  getParentRoute: () => workspace,
  path: "/ricerca",
  component: () => (
    <ComingSoon title="Ricerca" phase="Fase 3">
      Ricerca su tutte le fonti, per parole esatte e per concetto, con salto al punto preciso dell'audio o del documento.
    </ComingSoon>
  ),
});
const people = createRoute({
  getParentRoute: () => workspace,
  path: "/persone",
  component: () => (
    <ComingSoon title="Persone ed enti" phase="Fase 4">
      Una scheda per ogni persona o ente: in quali fonti compare, cosa ha detto, con chi è collegata.
    </ComingSoon>
  ),
});
const graph = createRoute({
  getParentRoute: () => workspace,
  path: "/grafo",
  component: () => (
    <ComingSoon title="Connessioni" phase="Fase 4">
      La mappa dei collegamenti tra persone, enti e temi delle tue storie, con la linea del tempo.
    </ComingSoon>
  ),
});

const routeTree = root.addChildren([
  login,
  mfaSetup,
  mfaVerify,
  authed.addChildren([home, workspace.addChildren([wsIndex, stories, story, archive, search, people, graph])]),
]);

export function makeRouter(queryClient: QueryClient) {
  return createRouter({ routeTree, context: { queryClient }, defaultPreload: "intent" });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof makeRouter>;
  }
}
