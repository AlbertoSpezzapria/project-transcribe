# Redazione

Archivio di lavoro per giornalisti: interviste, documenti e note organizzati per storia, ricercabili e citabili, con uno studio di produzione per carta, web e social. Il design completo è in [docs/DESIGN.md](docs/DESIGN.md).

Stato: **Fase 0 e Fase 1 completate** (fondamenta). La trascrizione arriva con la Fase 2.

## Struttura

```
apps/api      API FastAPI, modelli, migrazioni Alembic, worker della coda (Procrastinate)
apps/web      Frontend React + TypeScript (Vite, TanStack Router/Query, Tailwind)
infra/        Script di inizializzazione di Postgres e SeaweedFS
docs/         Documenti di design
legacy/       Bozza precedente del backend, tenuta come riferimento per la Fase 2
```

## Avvio in sviluppo

Serve Docker. Tutte le porte sono legate a `127.0.0.1`.

1. Crea il file `.env` da `.env.example` e imposta almeno `SECRET_KEY`, le password e `DEV_USER_PASSWORD`:

```bash
cp .env.example .env
```

```bash
docker run --rm python:3.12-slim sh -c "pip -q install cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
```

2. Avvia tutto (le migrazioni partono da sole):

```bash
docker compose up -d --build
```

3. Crea il workspace e l'utente di prova (credenziali prese da `DEV_USER_EMAIL` / `DEV_USER_PASSWORD` in `.env`):

```bash
docker compose exec api python -m app.cli seed-dev
```

4. Apri http://localhost:5173. Al primo accesso è obbligatorio configurare la verifica in due passaggi con un'app di autenticazione.

| Servizio | Indirizzo |
|---|---|
| Frontend | http://localhost:5173 |
| API (docs interattive) | http://localhost:8010/api/docs |
| Postgres | localhost:5442 |

## Comandi utili

```bash
docker compose run --rm api pytest
```

```bash
docker compose run --rm api ruff check app tests
```

```bash
cd apps/web && npm run typecheck
```

Rigenerare i tipi del client dopo una modifica all'API (con l'API avviata):

```bash
cd apps/web && npm run gen:api
```

Nuova migrazione dopo una modifica ai modelli:

```bash
docker compose run --rm api alembic revision --autogenerate -m "descrizione"
```

Amministrazione degli account (durante il pilota non c'è registrazione libera):

```bash
docker compose exec api python -m app.cli --help
```

## Scelte di sicurezza già attive

- **Accesso**: password argon2id e 2FA TOTP obbligatoria, codici di recupero monouso, sessioni in cookie `httpOnly` + `SameSite=Strict` con token ruotato dopo la 2FA, limite ai tentativi, controllo dell'header `Origin` sulle richieste che modificano dati.
- **Isolamento**: ogni dato di lavoro ha `workspace_id` ed è protetto da **Row-Level Security** in Postgres. L'API si connette con un ruolo senza privilegi; le FK composte impediscono collegamenti tra workspace diversi. I test lo verificano anche aggirando l'API.
- **File**: tipo riconosciuto dal contenuto e non dall'estensione, hash SHA-256 dell'originale, chiavi di storage senza nomi di file. Lo storage non è esposto: i file passano dall'API con controllo dei permessi e supporto Range per il player.
- **Tracciabilità**: registro di audit in sola aggiunta (l'applicazione non può modificarlo né cancellarlo), senza contenuti delle fonti.
- **Cancellazione**: eliminare una fonte rimuove anche i file dallo storage.
