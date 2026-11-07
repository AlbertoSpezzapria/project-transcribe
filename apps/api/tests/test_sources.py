import hashlib
import io

from conftest import login_full, make_user

from app import jobs, storage

# Un finto MP3: intestazione ID3 seguita da byte qualsiasi (basta per il riconoscimento)
FAKE_MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(range(256)) * 400


def _setup(client, email):
    _, ws = make_user(email, f"WS {email}")
    login_full(client, email)
    return ws


def test_story_crud(client):
    ws = _setup(client, "story@example.com")
    r = client.post(f"/api/workspaces/{ws}/stories", json={"title": "Cantiere di via Roma"})
    assert r.status_code == 201
    sid = r.json()["id"]
    r = client.patch(f"/api/workspaces/{ws}/stories/{sid}", json={"status": "archived"})
    assert r.json()["status"] == "archived"
    assert [s["id"] for s in client.get(f"/api/workspaces/{ws}/stories").json()] == [sid]


def test_upload_play_and_delete(client):
    ws = _setup(client, "upload@example.com")
    story = client.post(f"/api/workspaces/{ws}/stories", json={"title": "S"}).json()

    r = client.post(
        f"/api/workspaces/{ws}/sources/upload",
        files={"file": ("intervista sindaco.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")},
        data={"source_date": "2026-11-02", "confidentiality": "confidential", "story_id": story["id"]},
    )
    assert r.status_code == 201, r.text
    src = r.json()
    assert src["type"] == "audio"
    assert src["title"] == "intervista sindaco"
    assert src["confidentiality"] == "confidential"
    assert src["story_ids"] == [story["id"]]
    asset = src["assets"][0]
    assert asset["sha256"] == hashlib.sha256(FAKE_MP3).hexdigest()
    assert asset["size_bytes"] == len(FAKE_MP3)

    # La chiave nello storage non contiene il nome del file
    from app.db import SessionLocal, bind_workspace
    from app.models import Asset

    with SessionLocal() as db:
        bind_workspace(db, ws)
        key = db.get(Asset, asset["id"]).storage_key
    assert "sindaco" not in key

    # Job di ingestione (eseguito qui in modo sincrono)
    # Per l'audio, l'ingestione mette in coda la trascrizione
    jobs.ingest_source(workspace_id=str(ws), source_id=src["id"])
    after = client.get(f"/api/workspaces/{ws}/sources/{src['id']}").json()
    assert after["status"] == "processing"
    assert after["status_detail"] == "In coda per la trascrizione"

    # Riproduzione con Range, come fa il player audio
    url = f"/api/workspaces/{ws}/assets/{asset['id']}/content"
    r = client.get(url, headers={"Range": "bytes=10-19"})
    assert r.status_code == 206
    assert r.content == FAKE_MP3[10:20]
    assert r.headers["content-range"] == f"bytes 10-19/{len(FAKE_MP3)}"
    full = client.get(url + "?download=true")
    assert full.status_code == 200 and full.content == FAKE_MP3
    assert "attachment" in full.headers["content-disposition"]

    # Cancellazione definitiva: anche dallo storage
    assert client.delete(f"/api/workspaces/{ws}/sources/{src['id']}").status_code == 204
    assert client.get(f"/api/workspaces/{ws}/sources/{src['id']}").status_code == 404
    listed = storage.client().list_objects_v2(Bucket="redazione-test", Prefix=f"ws/{ws}/")
    assert listed.get("KeyCount", 0) == 0


def test_upload_rejects_disguised_files(client):
    ws = _setup(client, "fake@example.com")
    r = client.post(
        f"/api/workspaces/{ws}/sources/upload",
        files={"file": ("intervista.mp3", io.BytesIO(b"MZ\x90\x00 eseguibile"), "audio/mpeg")},
    )
    assert r.status_code == 415


def test_note_source(client):
    ws = _setup(client, "note@example.com")
    r = client.post(
        f"/api/workspaces/{ws}/sources/note",
        json={"title": "Appunti telefonata", "text": "Il cantiere riparte a gennaio."},
    )
    assert r.status_code == 201
    assert r.json()["type"] == "note" and r.json()["status"] == "ready"


def test_assets_of_other_workspace_are_unreachable(client):
    ws = _setup(client, "owner@example.com")
    r = client.post(
        f"/api/workspaces/{ws}/sources/upload",
        files={"file": ("a.mp3", io.BytesIO(FAKE_MP3), "audio/mpeg")},
    )
    asset_id = r.json()["assets"][0]["id"]
    client.post("/api/auth/logout")

    other_ws = _setup(client, "intruder@example.com")
    # Asset di un altro workspace richiesto attraverso il proprio workspace
    assert client.get(f"/api/workspaces/{other_ws}/assets/{asset_id}/content").status_code == 404
    # Attraverso il workspace altrui
    assert client.get(f"/api/workspaces/{ws}/assets/{asset_id}/content").status_code == 404
