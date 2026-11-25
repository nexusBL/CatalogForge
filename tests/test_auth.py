from pathlib import Path

from backend.main import app, get_swiggy_access, require_session
from backend.schemas import AuthUser
from backend.services.catalog_service import FixtureAccess
from fastapi.testclient import TestClient

FIXTURE_JSON = Path(__file__).parent / "fixtures" / "swiggy_menu_payload.json"
AUTH_TS = Path(__file__).resolve().parents[1] / "auth" / "auth.ts"
SAMPLE = {
    "restaurant_name": "Harbor Spice House",
    "fssai_number": "12345678901234",
    "swiggy_url": "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
    "organization_id": "org_1",
}


def test_better_auth_email_otp_configuration():
    source = AUTH_TS.read_text(encoding="utf-8")
    assert "betterAuth" in source
    assert "emailOTP" in source
    assert "emailAndPassword" in source
    assert "username(" in source
    assert "sendVerificationOTP" in source
    assert "BETTER_AUTH_SECRET" in source
    assert "better-sqlite3" in source or "Database" in source
    package = (AUTH_TS.parent / "package.json").read_text(encoding="utf-8")
    assert '"better-auth"' in package
    client = Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "auth-client.ts"
    client_source = client.read_text(encoding="utf-8")
    assert "usernameClient" in client_source
    assert "emailOTPClient" in client_source
    assert "organizationClient" in client_source


def test_unauthenticated_catalogue_request_is_rejected():
    client = TestClient(app)
    response = client.post("/catalog/create", json=SAMPLE)
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_auth_session_url_matches_better_auth_service(monkeypatch):
    monkeypatch.delenv("BETTER_AUTH_URL", raising=False)
    monkeypatch.delenv("AUTH_URL", raising=False)
    from backend.session import DEFAULT_AUTH_URL, auth_base_url

    assert DEFAULT_AUTH_URL == "http://localhost:3001"
    assert auth_base_url() == "http://localhost:3001"


def test_authenticated_catalogue_request(tmp_path):
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="owner@example.com")
    app.dependency_overrides[get_swiggy_access] = lambda: FixtureAccess(json_path=FIXTURE_JSON)
    try:
        client = TestClient(app)
        response = client.post("/catalog/create", json=SAMPLE)
        assert response.status_code == 200
        body = response.json()
        assert body["extraction_status"] == "ok"
        assert body["item_count"] == 2
    finally:
        app.dependency_overrides.clear()
