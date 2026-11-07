import hashlib
import io
import math
import re
import uuid

import pytest
from conftest import login_full, make_user

from app import embeddings, jobs, llm
from app.db import SessionLocal, bind_workspace
from app.models import EMBEDDING_DIM, Segment, Source, Transcript
from app.pipeline import documents, web

# --- Embedding finto: sacchetto di parole su 1024 dimensioni --------------------------

# Sinonimi minimi per simulare la ricerca "per significato"
_SYN = {"fermo": "sospeso", "fermi": "sospeso", "sospesi": "sospeso", "cantiere": "lavori"}


def fake_embed(texts, timeout=None):
    out = []
    for t in texts:
        v = [0.0] * EMBEDDING_DIM
        for w in re.findall(r"\w+", t.lower()):
            w = _SYN.get(w, w)
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % EMBEDDING_DIM] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append([x / n for x in v])
    return out


# --- Estrazione del testo --------------------------------------------------------------


def test_paragraphs_from_layout_lines():
    lines = [
        "Il consiglio comunale ha approvato la varia-",
        "zione di bilancio con 18 voti favorevoli e",
        "sei contrari.",
        "La seduta è stata sospesa alle 21 per una",
        "protesta del pubblico.",
        "",
        "12",
    ]
    paras = documents._paragraphs(documents.lines_to_paragraphs(lines))
    assert [p.text for p in paras] == [
        "Il consiglio comunale ha approvato la variazione di bilancio con 18 voti favorevoli e sei contrari.",
        "La seduta è stata sospesa alle 21 per una protesta del pubblico.",
    ]


def test_web_tables_become_readable_paragraphs():
    text = "Introduzione.\n| Carica | Sindaco | |\n|---|---|---|\n| Mandato | 1945 – 1980 |\nTesto finale."
    assert [p.text for p in documents.web_text_to_paragraphs(text)] == [
        "Introduzione.",
        "Carica — Sindaco · Mandato — 1945 – 1980",
        "Testo finale.",
    ]


def test_long_paragraph_is_split_on_sentences():
    text = " ".join(f"Frase numero {i} del documento." for i in range(200))
    parts = documents._split_long(text)
    assert len(parts) > 1 and all(len(p) <= documents.MAX_PARAGRAPH for p in parts)
    assert all(p.endswith(".") for p in parts)


def _minimal_pdf(pages: list[str]) -> bytes:
    """PDF valido con una riga di testo per pagina (font standard Helvetica)."""
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        None,
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    kids = []
    for text in pages:
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
        objs.append(f"<< /Length {len(content)} >>\nstream\n{content.decode('latin-1')}\nendstream")
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {len(objs)} 0 R "
            "/Resources << /Font << /F1 3 0 R >> >> >>"
        )
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def test_pdf_extraction_keeps_pages(tmp_path):
    path = tmp_path / "delibera.pdf"
    path.write_bytes(
        _minimal_pdf(
            [
                "La giunta approva il progetto del depuratore di Valle Verde.",
                "Spesa prevista: 4,5 milioni di euro a carico del bilancio 2027.",
            ]
        )
    )
    result = documents.extract_pdf(path)
    assert result.engine == "pdf" and result.pages == 2
    assert [(p.page, p.text[:20]) for p in result.paragraphs] == [
        (1, "La giunta approva il"),
        (2, "Spesa prevista: 4,5 "),
    ]


def test_docx_extraction(tmp_path):
    import docx

    d = docx.Document()
    d.add_heading("Verbale", level=1)
    d.add_paragraph("Presenti: il sindaco e l'assessore ai lavori pubblici.")
    table = d.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Voce"
    table.rows[0].cells[1].text = "1.200.000 euro"
    path = tmp_path / "verbale.docx"
    d.save(path)
    texts = [p.text for p in documents.extract_docx(path).paragraphs]
    assert texts == [
        "Verbale",
        "Presenti: il sindaco e l'assessore ai lavori pubblici.",
        "Voce | 1.200.000 euro",
    ]


# --- Pagine web: sicurezza ed estrazione ---------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "http://user:pw@example.com/",
        "http://example.com:8080/",
        "javascript:alert(1)",
    ],
)
def test_url_validation(url):
    with pytest.raises(web.FetchError):
        web.check_url(url)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "10.0.0.5", "169.254.169.254", "db", "storage"])
def test_internal_hosts_are_blocked(host):
    with pytest.raises(web.FetchError):
        web.fetch(f"http://{host}/")


ARTICLE = b"""<html><head><title>Depuratore, lavori fermi</title>
<meta name="author" content="Redazione Cronaca"><meta property="article:published_time" content="2026-10-30">
</head><body><nav>Menu Home Sport</nav><article><h1>Depuratore, lavori fermi da marzo</h1>
<p>I lavori del depuratore di Valle Verde sono fermi da marzo. La ditta ha chiesto una revisione dei prezzi.</p>
<p>Il Comune valuta la richiesta di 1,2 milioni di euro con l'ufficio tecnico, ha spiegato l'assessore.</p>
</article><footer>Cookie policy</footer><script>alert('x')</script></body></html>"""


def test_web_source_saves_snapshot_and_text(client, monkeypatch):
    _, ws = make_user("web@example.com", "WS web")
    login_full(client, "web@example.com")
    r = client.post(f"/api/workspaces/{ws}/sources/web", json={"url": "https://giornale.example/depuratore"})
    assert r.status_code == 201, r.text
    src = r.json()
    assert src["type"] == "web" and src["status"] == "uploaded"

    from datetime import UTC, datetime

    monkeypatch.setattr(
        web,
        "fetch",
        lambda url: web.Fetched(url, "text/html", ARTICLE, 200, datetime.now(UTC), []),
    )
    with SessionLocal() as db:
        bind_workspace(db, ws)
        jobs.run_fetch_web(db, db.get(Source, uuid.UUID(src["id"])))

    got = client.get(f"/api/workspaces/{ws}/sources/{src['id']}").json()
    assert got["status"] == "ready"
    assert got["title"] == "Depuratore, lavori fermi da marzo"  # titolo preso dalla pagina
    assert got["source_date"] == "2026-10-30"
    assert got["metadata"]["final_url"] == "https://giornale.example/depuratore"
    snapshot = got["assets"][0]
    assert snapshot["kind"] == "derived" and snapshot["mime_type"] == "text/html"
    # La copia salvata si apre solo in sandbox: nessuno script della pagina gira nell'app
    r = client.get(f"/api/workspaces/{ws}/assets/{snapshot['id']}/content")
    assert r.headers["content-security-policy"] == "sandbox"

    text = client.get(f"/api/workspaces/{ws}/sources/{src['id']}/transcript").json()
    joined = " ".join(s["text_raw"] for s in text["segments"])
    assert "fermi da marzo" in joined and "Cookie policy" not in joined and "alert" not in joined


# --- Documenti caricati, note, ricerca ---------------------------------------------------


def _ws(client, email):
    _, ws = make_user(email, f"WS {email}")
    login_full(client, email)
    return ws


def _upload_txt(client, ws, name, text, **data):
    r = client.post(
        f"/api/workspaces/{ws}/sources/upload",
        files={"file": (name, io.BytesIO(text.encode()), "text/plain")},
        data=data,
    )
    assert r.status_code == 201, r.text
    src = r.json()
    jobs.ingest_source(workspace_id=str(ws), source_id=src["id"])
    jobs.extract_document(workspace_id=str(ws), source_id=src["id"])
    return src["id"]


def _index_all(ws):
    with SessionLocal() as db:
        bind_workspace(db, ws)
        for source in db.query(Source).all():
            jobs.run_index(db, source, embed=fake_embed)


DELIBERA = """Delibera di giunta n. 45 del 2026

La giunta comunale approva la perizia di variante per il depuratore di Valle Verde.

La spesa aggiuntiva di 1.200.000 euro è finanziata con l'avanzo di amministrazione."""


def test_uploaded_document_becomes_searchable(client):
    ws = _ws(client, "doc@example.com")
    sid = _upload_txt(client, ws, "delibera.txt", DELIBERA, source_date="2026-10-01")
    src = client.get(f"/api/workspaces/{ws}/sources/{sid}").json()
    assert src["status"] == "ready"
    t = client.get(f"/api/workspaces/{ws}/sources/{sid}/transcript").json()
    assert len(t["segments"]) == 3 and t["engine"] == "text"

    # Per parole, con le radici italiane: "approvata" trova "approva"
    r = client.get(f"/api/workspaces/{ws}/search", params={"q": "approvata perizia"}).json()
    assert r["semantic"] is False  # embedder assente: solo ricerca per parole
    assert r["results"][0]["source_id"] == sid
    assert "⟦" in r["results"][0]["snippet"]
    # Frase esatta e filtri
    assert client.get(f"/api/workspaces/{ws}/search", params={"q": '"avanzo di amministrazione"'}).json()[
        "results"
    ]
    none = client.get(f"/api/workspaces/{ws}/search", params={"q": "depuratore", "type": "audio"}).json()
    assert none["results"] == []
    later = {"q": "depuratore", "date_from": "2026-11-01"}
    assert client.get(f"/api/workspaces/{ws}/search", params=later).json()["results"] == []


def test_semantic_search_and_reindex_after_edit(client, monkeypatch):
    ws = _ws(client, "semantica@example.com")
    r = client.post(
        f"/api/workspaces/{ws}/sources/note",
        json={"title": "Telefonata con il capocantiere", "text": "Il cantiere è fermo da settimane."},
    )
    note = r.json()["id"]
    _index_all(ws)
    monkeypatch.setattr(embeddings, "embed", fake_embed)
    from app.config import get_settings

    # L'embedding finto è grezzo: soglia più bassa di quella tarata su BGE-M3
    monkeypatch.setattr(get_settings(), "semantic_min_similarity", 0.2)

    # Nessuna parola in comune con la nota, ma stesso significato (per l'embedding finto)
    res = client.get(f"/api/workspaces/{ws}/search", params={"q": "lavori sospesi"}).json()
    assert res["semantic"] is True
    assert res["results"][0]["source_id"] == note
    assert res["results"][0]["matched"] == ["significato"]

    # Correggere il testo azzera l'embedding (verrà ricalcolato) e aggiorna l'indice per parole
    seg = client.get(f"/api/workspaces/{ws}/sources/{note}/transcript").json()["segments"][0]
    client.patch(
        f"/api/workspaces/{ws}/segments/{seg['id']}", json={"text": "Il cantiere è chiuso per maltempo."}
    )
    with SessionLocal() as db:
        bind_workspace(db, ws)
        assert db.get(Segment, uuid.UUID(seg["id"])).embedding is None
    hit = client.get(f"/api/workspaces/{ws}/search", params={"q": "maltempo"}).json()["results"]
    assert hit and hit[0]["segment_id"] == seg["id"]


def test_search_only_current_version_and_own_workspace(client):
    ws = _ws(client, "versione-ricerca@example.com")
    sid = _upload_txt(client, ws, "a.txt", "Prima stesura con la parola zafferano.")
    with SessionLocal() as db:
        bind_workspace(db, ws)
        source = db.get(Source, uuid.UUID(sid))
        jobs.save_text_version(
            db, source, engine="text", paragraphs=[documents.Paragraph("Seconda stesura.")]
        )
        db.commit()
    assert client.get(f"/api/workspaces/{ws}/search", params={"q": "zafferano"}).json()["results"] == []

    client.post("/api/auth/logout")
    other = _ws(client, "altro-ricerca@example.com")
    assert client.get(f"/api/workspaces/{other}/search", params={"q": "stesura"}).json()["results"] == []


# --- Domande con citazioni -------------------------------------------------------------


def _cloud(monkeypatch):
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "llm_cloud_api_key", "k")
    monkeypatch.setattr(s, "llm_cloud_strong_model", "forte")


def test_ask_answers_with_checked_citations(client, monkeypatch):
    ws = _ws(client, "domande@example.com")
    _upload_txt(client, ws, "delibera.txt", DELIBERA)
    _cloud(monkeypatch)
    seen = {}

    def fake_chat(profile, system, user):
        seen["model"] = profile.model
        seen["user"] = user
        return {
            "answer": "La spesa aggiuntiva è di 1.200.000 euro [3][9]. La delibera dice «finanziata con "
            "l'avanzo di amministrazione» [3] e anche «pagata dallo Stato» [3].",
            "insufficient": False,
        }

    monkeypatch.setattr(llm, "chat_json", fake_chat)
    r = client.post(
        f"/api/workspaces/{ws}/ask", json={"question": "Come è finanziata la variante del depuratore?"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert seen["model"] == "forte"  # domande = compito difficile
    assert "PASSAGGI" in seen["user"] and "delibera" in seen["user"]
    assert "[9]" not in body["answer"]  # rimando a un passaggio inesistente: rimosso
    assert body["unverified_quotes"] == ["pagata dallo Stato"]
    assert body["passages"] and body["model"] == "cloud_strong:forte"


def test_ask_with_confidential_sources_needs_local_model(client, monkeypatch):
    ws = _ws(client, "domande-riservate@example.com")
    _upload_txt(client, ws, "fonte.txt", DELIBERA, confidentiality="confidential")
    _cloud(monkeypatch)
    monkeypatch.setattr(llm, "chat_json", lambda *a: pytest.fail("fonte riservata inviata al cloud"))
    body = client.post(f"/api/workspaces/{ws}/ask", json={"question": "Quanto costa il depuratore?"}).json()
    assert body["answer"] is None
    assert "modello locale" in body["unavailable_reason"]
    assert body["passages"]  # i passaggi pertinenti si vedono comunque


def test_note_has_searchable_text_version(client):
    ws = _ws(client, "nota-ricerca@example.com")
    r = client.post(
        f"/api/workspaces/{ws}/sources/note",
        json={"title": "Appunti", "text": "Primo paragrafo.\n\nSecondo paragrafo sul bilancio."},
    )
    sid = r.json()["id"]
    with SessionLocal() as db:
        bind_workspace(db, ws)
        t = db.query(Transcript).filter_by(source_id=uuid.UUID(sid), is_current=True).one()
        assert t.engine == "note"
    hits = client.get(f"/api/workspaces/{ws}/search", params={"q": "bilancio"}).json()["results"]
    assert hits[0]["source_id"] == sid
