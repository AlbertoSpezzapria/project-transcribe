import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { ApiError } from "@/lib/api";
import { makeRouter } from "@/router";

import "./styles.css";

// Tema scelto dall'utente (se presente) applicato prima del primo render
try {
  const theme = localStorage.getItem("theme");
  if (theme) document.documentElement.dataset.theme = theme;
} catch {
  /* storage non disponibile */
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
});

const router = makeRouter(queryClient);

// Sessione scaduta durante l'uso: torna alla pagina di accesso
queryClient.getQueryCache().subscribe((event) => {
  const error = event.query.state.error;
  if (error instanceof ApiError && error.status === 401 && event.query.queryKey[0] !== "auth") {
    queryClient.removeQueries({ queryKey: ["auth"] });
    router.navigate({ to: "/accesso" });
  }
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
