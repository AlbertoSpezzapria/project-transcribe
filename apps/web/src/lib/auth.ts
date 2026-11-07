import { queryOptions, useQuery } from "@tanstack/react-query";

import { api, unwrap, type AuthState } from "./api";

export const authQuery = queryOptions({
  queryKey: ["auth"],
  queryFn: () => unwrap<AuthState>(api.GET("/api/auth/me")),
  staleTime: 60_000,
});

export function useAuth() {
  return useQuery(authQuery);
}

/** Pagina a cui mandare l'utente in base allo stato della sessione. */
export function routeForStep(step: string): string | null {
  switch (step) {
    case "none":
      return "/accesso";
    case "mfa_setup":
      return "/accesso/configura-2fa";
    case "mfa_verify":
      return "/accesso/verifica";
    default:
      return null;
  }
}
