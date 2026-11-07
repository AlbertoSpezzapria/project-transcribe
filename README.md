# Redazione

Archivio di lavoro per giornalisti: interviste, documenti e note organizzati per storia, ricercabili e citabili, con uno studio di produzione per carta, web e social. Il design completo è in [docs/DESIGN.md](docs/DESIGN.md).

Stato: **Fasi 0, 1 e 2 completate**: fondamenta, trascrizione con editor sincronizzato. Prossima: documenti, web e ricerca (Fase 3).

## Struttura

```
apps/api      API FastAPI, modelli, migrazioni Alembic, worker della coda (Procrastinate),
              pipeline di trascrizione (app/pipeline)
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

### Trascrizione

Il servizio `worker-stt` trascrive audio e video sul posto, senza inviare nulla all'esterno. In sviluppo gira su CPU con il modello `small` (`STT_MODEL` in `.env`); al primo uso scarica il modello nel volume `stt_models`. Sul server con GPU si usa `large-v3-turbo`.

Riconoscimento degli interlocutori (facoltativo, pesante):

1. crea un token su Hugging Face e accetta la licenza di `pyannote/speaker-diarization-community-1`;
2. in `.env` imposta `WITH_DIARIZATION=1`, `DIARIZATION_ENABLED=true` e `HF_TOKEN`;
3. ricostruisci il worker:

```bash
docker compose up -d --build worker-stt
```

Versione pulita della trascrizione: imposta `LLM_CLOUD_API_KEY` e `LLM_CLOUD_MODEL` (qualsiasi API compatibile OpenAI). Il profilo cloud vale solo per le fonti normali; per quelle riservate serve un modello locale (`LLM_LOCAL_*`).

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
- **Trascrizioni**: l'audio viene trascritto sul server; il verbatim del modello non viene mai sovrascritto (le correzioni sono separate) e la versione pulita non è usabile per le citazioni. Le fonti riservate non vengono mai inviate a un modello linguistico esterno.
