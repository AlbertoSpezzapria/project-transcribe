import io
import uuid

import pytest
from conftest import login_full, make_user
from test_sources import FAKE_MP3

from app import jobs, llm
from app.db import SessionLocal, bind_workspace
from app.models import Source, Transcript
from app.pipeline import clean
from app.pipeline.segmentation import Turn, assign_speakers, build_segments

# --- Funzioni pure ---------------------------------------------------------------


def _w(text, s, e):
    return [text, s, e, 0.9]


def test_words_keep_model_spacing():
    from app.pipeline.segmentation import join_words

    assert join_words([_w(" con", 0, 1), _w(" l'", 1, 2), _w("ufficio", 2, 3)]) == "con l'ufficio"


def test_segments_follow_speaker_turns():
    words = [
        _w(" Buongiorno.", 0.0, 0.5),
        _w(" Salve,", 0.9, 1.2),
        _w(" mi", 1.3, 1.4),
        _w(" dica.", 1.5, 1.8),
    ]
    turns = [Turn(0.0, 0.7, "A"), Turn(0.8, 2.0, "B")]
    assert assign_speakers(words, turns) == ["A", "B", "B", "B"]
    segs = build_segments(words, turns)
    assert [(s.speaker, s.text) for s in segs] == [("A", "Buongiorno."), ("B", "Salve, mi dica.")]


def test_word_in_gap_takes_nearest_turn():
    words = [_w("uno", 0.0, 0.4), _w("due", 1.05, 1.3)]
    turns = [Turn(0.0, 0.5, "A"), Turn(1.4, 3.0, "B")]
    assert assign_speakers(words, turns) == ["A", "B"]


def test_long_pause_and_sentence_split():
    words = [_w("Prima.", 0.0, 0.5), _w("Dopo", 5.0, 5.5)]
    assert len(build_segments(words)) == 2
    many = [_w(f"p{i}.", i * 1.0, i * 1.0 + 0.8) for i in range(70)]
    segs = build_segments(many, target_seconds=30, max_seconds=60)
    assert all(s.end - s.start <= 60 for s in segs)
    assert len(segs) >= 2


def test_clean_check_protects_names_and_numbers():
    orig = "Allora, ehm, l'assessore Mario Rossi ha detto che servono 4,5 milioni."
    assert clean.check(orig, "L'assessore Mario Rossi ha detto che servono 4,5 milioni.") is None
    assert (
        clean.check(orig, "L'assessore Rossi ha detto che servono 4,5 milioni.") == "nomi propri modificati"
    )
    assert clean.check(orig, "L'assessore Mario Rossi ha detto che servono 5 milioni.") == "cifre modificate"
    assert clean.check(orig, "Servono soldi.") == "lunghezza troppo diversa"


def test_llm_routing_by_confidentiality(monkeypatch):
    from app.config import get_settings
    from app.models import Confidentiality

    s = get_settings()
    monkeypatch.setattr(s, "llm_cloud_api_key", "k")
    monkeypatch.setattr(s, "llm_cloud_model", "m")
    assert llm.profile_for(Confidentiality.normal).name == "cloud"
    assert llm.profile_for(Confidentiality.confidential) is None
    assert llm.profile_for(Confidentiality.secret) is None
    monkeypatch.setattr(s, "llm_local_base_url", "http://llm:8000/v1")
    monkeypatch.setattr(s, "llm_local_model", "locale")
    assert llm.profile_for(Confidentiality.secret).name == "local"


# --- Flusso completo con il motore finto ------------------------------------------


def _transcribed_source(client, email, confidentiality="normal"):
    _, ws = make_user(email, f"WS {email}")
    login_full(client, email)
    r = client.post(
        f"/api/workspaces/{ws}/sources/upload",
        files={"file": ("intervista.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")},
        data={"confidentiality": confidentiality},
    )
    src = r.json()
    jobs.ingest_source(workspace_id=str(ws), source_id=src["id"])
    with SessionLocal() as db:
        bind_workspace(db, ws)
        t = db.query(Transcript).filter_by(source_id=uuid.UUID(src["id"])).one()
        jobs.run_transcription(db, db.get(Source, uuid.UUID(src["id"])), t)
    return ws, src["id"]


def test_transcript_edit_speakers_and_export(client):
    ws, sid = _transcribed_source(client, "trascr@example.com")
    base = f"/api/workspaces/{ws}"
    assert client.get(f"{base}/sources/{sid}").json()["status"] == "ready"

    t = client.get(f"{base}/sources/{sid}/transcript").json()
    assert t["status"] == "ready" and t["is_current"]
    assert len(t["speakers"]) == 1
    seg = t["segments"][0]
    assert "Mario Rossi" in seg["text_raw"]
    assert seg["words"][0][0] == " Buongiorno,"
    assert seg["text_raw"].startswith("Buongiorno, sono")

    # Correzione: il verbatim resta intatto
    r = client.patch(
        f"{base}/segments/{seg['id']}", json={"text": seg["text_raw"].replace("Rossi", "Rossini")}
    )
    assert r.status_code == 200
    assert "Rossini" in r.json()["text_edited"] and "Rossi" in r.json()["text_raw"]
    # Riportare il testo al verbatim annulla la correzione
    r = client.patch(f"{base}/segments/{seg['id']}", json={"text": seg["text_raw"]})
    assert r.json()["text_edited"] is None

    # Interlocutori: rinomina, nuovo, assegnazione, unione
    v1 = t["speakers"][0]["id"]
    assert client.patch(f"{base}/speakers/{v1}", json={"name": "Mario Rossi"}).json()["name"] == "Mario Rossi"
    v2 = client.post(f"{base}/transcripts/{t['id']}/speakers", json={"name": "Giornalista"}).json()
    assert client.patch(f"{base}/segments/{seg['id']}", json={"speaker_id": v2["id"]}).status_code == 200
    assert client.post(f"{base}/speakers/{v2['id']}/merge", json={"into_id": v1}).status_code == 204
    t2 = client.get(f"{base}/sources/{sid}/transcript").json()
    assert [s["id"] for s in t2["speakers"]] == [v1]
    assert t2["segments"][0]["speaker_id"] == v1

    # Export testuale, tracciato
    r = client.get(f"{base}/transcripts/{t['id']}/export?format=txt")
    assert r.status_code == 200 and "[00:00:00] Mario Rossi: Buongiorno" in r.text
    srt = client.get(f"{base}/transcripts/{t['id']}/export?format=srt").text
    assert srt.startswith("1\n00:00:00,000 --> ")


def test_retranscribe_keeps_previous_until_ready(client):
    ws, sid = _transcribed_source(client, "versioni@example.com")
    base = f"/api/workspaces/{ws}"
    first = client.get(f"{base}/sources/{sid}/transcript").json()

    r = client.post(f"{base}/sources/{sid}/transcribe", json={"language": "en"})
    assert r.status_code == 202 and r.json()["is_current"] is False
    assert client.post(f"{base}/sources/{sid}/transcribe", json={}).status_code == 409
    # Nel frattempo si vede ancora la versione precedente, con la nuova "in arrivo"
    cur = client.get(f"{base}/sources/{sid}/transcript").json()
    assert cur["id"] == first["id"] and cur["pending"]["id"] == r.json()["id"]

    with SessionLocal() as db:
        bind_workspace(db, ws)
        jobs.run_transcription(
            db, db.get(Source, uuid.UUID(sid)), db.get(Transcript, uuid.UUID(r.json()["id"]))
        )
    cur = client.get(f"{base}/sources/{sid}/transcript").json()
    assert cur["id"] == r.json()["id"] and cur["pending"] is None
    # Si può tornare alla versione precedente
    assert len(client.get(f"{base}/sources/{sid}/transcripts").json()) == 2
    assert client.post(f"{base}/transcripts/{first['id']}/activate").status_code == 200
    assert client.get(f"{base}/sources/{sid}/transcript").json()["id"] == first["id"]


def test_clean_version_with_checks(client, monkeypatch):
    ws, sid = _transcribed_source(client, "pulita@example.com")
    base = f"/api/workspaces/{ws}"
    t = client.get(f"{base}/sources/{sid}/transcript").json()
    assert t["clean_available"] is False
    assert client.post(f"{base}/transcripts/{t['id']}/clean").status_code == 400

    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "llm_cloud_api_key", "k")
    monkeypatch.setattr(s, "llm_cloud_model", "m")

    def blocks(user):
        for block in user.split("\n\n"):
            head, text = block.split("\n", 1)
            yield int(head.strip("[]")), text

    def fake_chat(profile, system, user):
        # Il modello "sbaglia" la cifra: il controllo deve scartare solo quel passaggio
        return {"segments": [{"i": i, "text": text.replace("4,5", "5")} for i, text in blocks(user)]}

    monkeypatch.setattr(llm, "chat_json", fake_chat)
    assert client.post(f"{base}/transcripts/{t['id']}/clean").status_code == 202
    jobs.clean_transcript(workspace_id=str(ws), source_id=sid, transcript_id=t["id"])
    t2 = client.get(f"{base}/sources/{sid}/transcript").json()
    assert t2["clean_status"] == "ready"
    rejected = [s for s in t2["segments"] if "4,5" in s["text_raw"]]
    assert rejected and all(s["text_clean"] is None for s in rejected)
    assert "1 passaggi" in t2["clean_error"]

    def faithful(profile, system, user):
        return {"segments": [{"i": i, "text": text} for i, text in blocks(user)]}

    monkeypatch.setattr(llm, "chat_json", faithful)
    client.post(f"{base}/transcripts/{t['id']}/clean")
    jobs.clean_transcript(workspace_id=str(ws), source_id=sid, transcript_id=t["id"])
    t3 = client.get(f"{base}/sources/{sid}/transcript").json()
    assert all(s["text_clean"] for s in t3["segments"]) and t3["clean_error"] is None


def test_confidential_source_never_goes_to_cloud(client, monkeypatch):
    ws, sid = _transcribed_source(client, "riservata@example.com", confidentiality="confidential")
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "llm_cloud_api_key", "k")
    monkeypatch.setattr(s, "llm_cloud_model", "m")
    monkeypatch.setattr(llm, "chat_json", lambda *a: pytest.fail("chiamata al cloud"))
    t = client.get(f"/api/workspaces/{ws}/sources/{sid}/transcript").json()
    assert t["clean_available"] is False
    assert "modello locale" in t["clean_unavailable_reason"]
    assert client.post(f"/api/workspaces/{ws}/transcripts/{t['id']}/clean").status_code == 400


def test_transcripts_isolated_between_workspaces(client):
    ws, sid = _transcribed_source(client, "isola-a@example.com")
    t = client.get(f"/api/workspaces/{ws}/sources/{sid}/transcript").json()
    client.post("/api/auth/logout")
    _, ws_b = make_user("isola-b@example.com", "WS B")
    login_full(client, "isola-b@example.com")
    seg = t["segments"][0]["id"]
    assert client.patch(f"/api/workspaces/{ws_b}/segments/{seg}", json={"text": "x"}).status_code == 404
    assert client.get(f"/api/workspaces/{ws_b}/transcripts/{t['id']}/export").status_code == 404
    assert (
        client.patch(
            f"/api/workspaces/{ws_b}/speakers/{t['speakers'][0]['id']}", json={"name": "x"}
        ).status_code
        == 404
    )


def test_retry_after_failure_replaces_failed_version(client):
    ws, sid = _transcribed_source(client, "riprova@example.com")
    base = f"/api/workspaces/{ws}"
    with SessionLocal() as db:
        bind_workspace(db, ws)
        t = db.query(Transcript).filter_by(source_id=uuid.UUID(sid), is_current=True).one()
        from app.models import JobStatus

        t.status = JobStatus.failed
        db.commit()
    r = client.post(f"{base}/sources/{sid}/transcribe", json={"language": "it"})
    assert r.status_code == 202 and r.json()["is_current"] is True
    assert client.get(f"{base}/sources/{sid}/transcript").json()["id"] == r.json()["id"]
