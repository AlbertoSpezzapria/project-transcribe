import createClient from "openapi-fetch";

import type { components, paths } from "./api-schema";

export type Schemas = components["schemas"];
export type AuthState = Schemas["AuthState"];
export type Story = Schemas["StoryOut"];
export type Source = Schemas["SourceOut"];
export type SourceType = Source["type"];
export type Confidentiality = Source["confidentiality"];

/** Client tipizzato generato dall'OpenAPI del backend (`npm run gen:api`). */
export const api = createClient<paths>({ baseUrl: "", credentials: "same-origin" });

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function detailOf(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const d = (error as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
  }
  return "Si è verificato un errore. Riprova.";
}

/** Restituisce i dati o lancia un ApiError con il messaggio del server. */
export async function unwrap<T>(
  p: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await p;
  if (!response.ok) throw new ApiError(response.status, detailOf(error));
  return data as T;
}

export function assetUrl(workspaceId: string, assetId: string, download = false) {
  return `/api/workspaces/${workspaceId}/assets/${assetId}/content${download ? "?download=true" : ""}`;
}

/** Upload con avanzamento (fetch non espone il progresso dell'invio). */
export function uploadSource(
  workspaceId: string,
  form: FormData,
  onProgress: (fraction: number) => void,
): Promise<Source> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/workspaces/${workspaceId}/sources/upload`);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      const body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Source);
      else reject(new ApiError(xhr.status, detailOf(body)));
    };
    xhr.onerror = () => reject(new ApiError(0, "Connessione interrotta durante il caricamento"));
    xhr.send(form);
  });
}
