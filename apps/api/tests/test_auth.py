from conftest import PASSWORD, login_full, make_user


def test_login_wrong_password_is_generic(client):
    make_user("wrong@example.com")
    r = client.post("/api/auth/login", json={"email": "wrong@example.com", "password": "nope"})
    assert r.status_code == 401
    r2 = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope"})
    assert r2.status_code == 401
    assert r.json()["detail"] == r2.json()["detail"]  # non rivela se l'utente esiste


def test_rate_limit_on_login(client):
    make_user("brute@example.com")
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "brute@example.com", "password": "x"})
    r = client.post("/api/auth/login", json={"email": "brute@example.com", "password": PASSWORD})
    assert r.status_code == 429


def test_2fa_is_mandatory(client):
    _, ws = make_user("mfa@example.com", "WS mfa")
    r = client.post("/api/auth/login", json={"email": "mfa@example.com", "password": PASSWORD})
    assert r.json()["step"] == "mfa_setup"
    # Con la sola password non si accede ai dati
    assert client.get(f"/api/workspaces/{ws}/stories").status_code == 401
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_full_flow_and_recovery_code(client):
    _, ws = make_user("full@example.com", "WS full")
    codes = login_full(client, "full@example.com")
    assert len(codes) == 10
    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is True and me["step"] == "done"
    assert me["workspaces"][0]["id"] == str(ws)
    assert client.get(f"/api/workspaces/{ws}/stories").status_code == 200

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json()["step"] == "none"

    # Secondo accesso: 2FA già attiva → verifica con codice di recupero (monouso)
    r = client.post("/api/auth/login", json={"email": "full@example.com", "password": PASSWORD})
    assert r.json()["step"] == "mfa_verify"
    r = client.post("/api/auth/2fa/verify", json={"code": codes[0].lower()})
    assert r.status_code == 200 and r.json()["authenticated"] is True

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "full@example.com", "password": PASSWORD})
    r = client.post("/api/auth/2fa/verify", json={"code": codes[0]})
    assert r.status_code == 400


def test_session_token_rotates_after_mfa(client):
    make_user("rotate@example.com")
    client.post("/api/auth/login", json={"email": "rotate@example.com", "password": PASSWORD})
    before = client.cookies.get("redazione_session")
    secret = client.post("/api/auth/2fa/setup").json()["secret"]
    import pyotp

    client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()})
    assert client.cookies.get("redazione_session") != before


def test_foreign_origin_is_rejected(client):
    r = client.post(
        "/api/auth/login",
        json={"email": "x@example.com", "password": "x"},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403


def test_mfa_setup_is_idempotent(client):
    make_user("idem@example.com")
    client.post("/api/auth/login", json={"email": "idem@example.com", "password": PASSWORD})
    first = client.post("/api/auth/2fa/setup").json()["secret"]
    assert client.post("/api/auth/2fa/setup").json()["secret"] == first


def test_login_accepts_reserved_domains(client):
    make_user("redattore@redazione.test")
    r = client.post("/api/auth/login", json={"email": "Redattore@Redazione.test", "password": PASSWORD})
    assert r.status_code == 200


def test_concurrent_mfa_setup_returns_the_stored_secret(client):
    """Due richieste di setup in parallelo devono restituire la stessa chiave, quella salvata."""
    from concurrent.futures import ThreadPoolExecutor

    import pyotp

    make_user("race@example.com")
    client.post("/api/auth/login", json={"email": "race@example.com", "password": PASSWORD})
    with ThreadPoolExecutor(4) as pool:
        secrets = list(pool.map(lambda _: client.post("/api/auth/2fa/setup").json()["secret"], range(4)))
    assert len(set(secrets)) == 1
    r = client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secrets[0]).now()})
    assert r.status_code == 200
