import os
from pathlib import Path

import pytest

DEFAULT_TEST_ORGANIZATION_IDS = {
    "org_harbor",
    "org_1",
    "org_a",
    "org_b",
    "org_idem",
    "org_other",
    "org",
}


@pytest.fixture(autouse=True)
def _isolated_catalogue_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CATALOGFORGE_CATALOGUE_DB", str(tmp_path / "catalogues.sqlite"))
    monkeypatch.setenv("CATALOGFORGE_ASSETS_DIR", str(tmp_path / "catalogue-assets"))
    monkeypatch.setenv("CATALOGFORGE_RAW_DIR", str(tmp_path / "catalogue-raw"))
    monkeypatch.setenv("CATALOGFORGE_GENERATED_MEDIA_DIR", str(tmp_path / "generated-media"))
    monkeypatch.setenv("CATALOGFORGE_REVIEW_EVIDENCE_DIR", str(tmp_path / "review-evidence"))
    monkeypatch.setenv("CATALOGFORGE_DOWNLOAD_IMAGES", "0")
    monkeypatch.delenv("CATALOGFORGE_MEDIA_IMAGE_URL", raising=False)
    monkeypatch.delenv("CATALOGFORGE_MEDIA_VIDEO_URL", raising=False)
    monkeypatch.delenv("CATALOGFORGE_MEDIA_API_TOKEN", raising=False)
    monkeypatch.delenv("CATALOGFORGE_MEDIA_PROTOCOL", raising=False)
    os.environ["CATALOGFORGE_CATALOGUE_DB"] = str(tmp_path / "catalogues.sqlite")
    from backend.improvement.service import set_generator_factory
    from backend.media.service import set_media_provider_factory
    from backend.migrate_catalogues import migrate_catalogue_db

    set_media_provider_factory(None)
    set_generator_factory(None)
    migrate_catalogue_db(tmp_path / "catalogues.sqlite")
    yield
    set_media_provider_factory(None)
    set_generator_factory(None)


@pytest.fixture(autouse=True)
def _stub_organization_membership(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_load(_request, _user):
        return set(DEFAULT_TEST_ORGANIZATION_IDS)

    monkeypatch.setattr("backend.authz._load_organization_ids", fake_load)
