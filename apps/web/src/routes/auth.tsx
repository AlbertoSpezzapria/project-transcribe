import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ShieldCheck } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useState, type FormEvent, type ReactNode } from "react";

import { Alert, Button, Field, Input } from "@/components/ui";
import { api, unwrap, type AuthState } from "@/lib/api";
import { routeForStep } from "@/lib/auth";

function AuthFrame({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <main className="flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <p className="mb-8 text-center font-serif text-xl font-semibold tracking-tight">Redazione</p>
        <div className="rounded-lg border border-border bg-surface p-6 shadow-sm">
          <h1 className="text-lg font-semibold">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
          <div className="mt-5">{children}</div>
        </div>
      </div>
    </main>
  );
}

function useAfterAuth() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  return (state: AuthState) => {
    qc.setQueryData(["auth"], state);
    navigate({ to: routeForStep(state.step) ?? "/" });
  };
}

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const after = useAfterAuth();
  const login = useMutation({
    mutationFn: () => unwrap(api.POST("/api/auth/login", { body: { email, password } })),
    onSuccess: after,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate();
  };
  return (
    <AuthFrame title="Accedi" subtitle="L'archivio di lavoro della tua redazione.">
      <form onSubmit={submit} className="space-y-4">
        {login.error && <Alert>{login.error.message}</Alert>}
        <Field label="Email" htmlFor="email">
          <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        </Field>
        <Field label="Password" htmlFor="password">
          <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Button type="submit" className="w-full" loading={login.isPending}>
          Continua
        </Button>
      </form>
    </AuthFrame>
  );
}

function CodeInput({ value, onChange, allowRecovery }: { value: string; onChange: (v: string) => void; allowRecovery?: boolean }) {
  return (
    <Input
      inputMode={allowRecovery ? "text" : "numeric"}
      autoComplete="one-time-code"
      placeholder={allowRecovery ? "123456 o codice di recupero" : "123456"}
      className="h-11 text-center font-mono text-lg tracking-[0.3em]"
      maxLength={allowRecovery ? 20 : 6}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      autoFocus
      required
    />
  );
}

export function MfaVerifyPage() {
  const [code, setCode] = useState("");
  const after = useAfterAuth();
  const verify = useMutation({
    mutationFn: () => unwrap(api.POST("/api/auth/2fa/verify", { body: { code } })),
    onSuccess: after,
  });
  return (
    <AuthFrame title="Verifica in due passaggi" subtitle="Inserisci il codice a 6 cifre dell'app di autenticazione.">
      <form onSubmit={(e) => (e.preventDefault(), verify.mutate())} className="space-y-4">
        {verify.error && <Alert>{verify.error.message}</Alert>}
        <CodeInput value={code} onChange={setCode} allowRecovery />
        <Button type="submit" className="w-full" loading={verify.isPending}>
          Verifica
        </Button>
        <p className="text-xs text-muted">Hai perso il telefono? Usa uno dei codici di recupero che hai salvato.</p>
      </form>
    </AuthFrame>
  );
}

export function MfaSetupPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState<string[] | null>(null);

  // Query e non mutation: React Query deduplica le richieste (anche il doppio
  // render di StrictMode), quindi il QR mostrato è sempre quello salvato.
  const setup = useQuery({
    queryKey: ["mfa-setup"],
    queryFn: () => unwrap(api.POST("/api/auth/2fa/setup")),
    staleTime: Infinity,
    gcTime: 0,
  });
  const enable = useMutation({
    mutationFn: () => unwrap(api.POST("/api/auth/2fa/enable", { body: { code } })),
    onSuccess: (res) => setRecovery(res.recovery_codes),
  });

  if (recovery) {
    const finish = async () => {
      await qc.invalidateQueries({ queryKey: ["auth"] });
      navigate({ to: "/" });
    };
    return (
      <AuthFrame title="Salva i codici di recupero" subtitle="Ti servono se perdi il telefono. Ognuno vale una sola volta e non verrà mostrato di nuovo.">
        <ul className="grid grid-cols-2 gap-2 rounded-md bg-surface-2 p-3 font-mono text-sm">
          {recovery.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <div className="mt-4 flex gap-2">
          <Button variant="secondary" className="flex-1" onClick={() => navigator.clipboard.writeText(recovery.join("\n"))}>
            Copia
          </Button>
          <Button className="flex-1" onClick={finish}>
            Li ho salvati
          </Button>
        </div>
      </AuthFrame>
    );
  }

  return (
    <AuthFrame title="Attiva la verifica in due passaggi" subtitle="È obbligatoria: protegge le tue fonti anche se qualcuno scopre la password.">
      <div className="space-y-4">
        {setup.error && <Alert>{setup.error.message}</Alert>}
        <ol className="list-decimal space-y-1 pl-5 text-sm text-muted">
          <li>Apri un'app di autenticazione (Google Authenticator, Microsoft Authenticator, 1Password…).</li>
          <li>Inquadra il codice QR, oppure inserisci la chiave a mano.</li>
          <li>Scrivi qui il codice a 6 cifre che compare.</li>
        </ol>
        {setup.data ? (
          <div className="flex flex-col items-center gap-2 rounded-md bg-white p-4">
            <QRCodeSVG value={setup.data.otpauth_uri} size={168} />
            <code className="break-all text-center text-xs text-neutral-600">{setup.data.secret}</code>
          </div>
        ) : (
          <div className="h-52 animate-pulse rounded-md bg-surface-2" />
        )}
        <form onSubmit={(e) => (e.preventDefault(), enable.mutate())} className="space-y-3">
          {enable.error && <Alert>{enable.error.message}</Alert>}
          <CodeInput value={code} onChange={setCode} />
          <Button type="submit" className="w-full" loading={enable.isPending} disabled={!setup.data}>
            <ShieldCheck className="size-4" /> Attiva
          </Button>
        </form>
      </div>
    </AuthFrame>
  );
}
