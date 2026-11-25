import json
from pathlib import Path

from scraper.cli import main
from scraper.swiggy.parser import parse_swiggy_catalogue
from scraper.swiggy.scraper import collect_local_source

FIXTURE_JSON = Path(__file__).parent / "fixtures" / "swiggy_menu_payload.json"
LOCAL_URL = "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001"


def test_local_json_fixture_runs_full_pipeline():
    raw = collect_local_source(LOCAL_URL, json_path=FIXTURE_JSON)
    catalogue = parse_swiggy_catalogue(raw)
    assert raw.blocked is False
    assert "local_json" in raw.data_locations[0]
    assert catalogue.restaurant.name == "Harbor Spice House"
    assert len(catalogue.categories) == 2
    assert sum(len(category.items) for category in catalogue.categories) == 2
    assert catalogue.extraction_status == "ok"
    assert catalogue.source_type == "xhr_json"
    assert catalogue.item_count == 2
    assert catalogue.image_count >= 2
    assert catalogue.error is None


def test_local_html_fixture_uses_embedded_next_data(tmp_path):
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    html = (
        "<html><head><title>Harbor Spice House</title></head><body>"
        "<h1>Harbor Spice House</h1><p>Sample menu page</p>"
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'
        "</body></html>"
    )
    html_path = tmp_path / "menu.html"
    html_path.write_text(html, encoding="utf-8")
    raw = collect_local_source(LOCAL_URL, html_path=html_path)
    catalogue = parse_swiggy_catalogue(raw)
    assert raw.next_data is not None
    assert catalogue.restaurant.name == "Harbor Spice House"
    assert catalogue.categories[0].items[0].image_url.endswith("test/item-thali")


def test_cli_from_json(tmp_path):
    out_dir = tmp_path / "out"
    code = main(
        [
            LOCAL_URL,
            "--from-json",
            str(FIXTURE_JSON),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert code == 0
    saved = json.loads((out_dir / "harbor-spice-house-rest999001.json").read_text(encoding="utf-8"))
    assert saved["restaurant"]["name"] == "Harbor Spice House"
    assert saved["extraction"]["blocked"] is False
    assert saved["extraction_status"] == "ok"
    assert saved["item_count"] == 2
    assert saved["categories"]


def test_json_ld_and_dom_fallback(tmp_path):
    html = """
    <html><head>
    <script type="application/ld+json">
    {
      "@type": "Restaurant",
      "name": "Harbor Spice House",
      "hasMenu": {
        "@type": "Menu",
        "hasMenuSection": [{
          "@type": "MenuSection",
          "name": "Breads",
          "hasMenuItem": [{"@type": "MenuItem", "name": "Butter Naan", "offers": {"price": "70"}}]
        }]
      }
    }
    </script>
    </head><body>
    <section data-menu-category="Sides">
      <h3 data-menu-item="Papad"></h3>
    </section>
    </body></html>
    """
    html_path = tmp_path / "ld.html"
    html_path.write_text(html, encoding="utf-8")
    raw = collect_local_source(LOCAL_URL, html_path=html_path)
    catalogue = parse_swiggy_catalogue(raw)
    assert catalogue.extraction_status == "ok"
    assert catalogue.source_type == "json_ld"
    assert catalogue.restaurant.name == "Harbor Spice House"
    assert catalogue.categories[0].name == "Breads"
    assert catalogue.categories[0].items[0].name == "Butter Naan"


def test_blocked_result_is_not_success():
    from scraper.swiggy.models import RawSource
    from scraper.swiggy.parser import parse_swiggy_catalogue

    catalogue = parse_swiggy_catalogue(
        RawSource(
            source_url=LOCAL_URL,
            blocked=True,
            access_status="blocked",
            http_status=403,
            reason="Swiggy/CloudFront denied the restaurant page (HTTP 403).",
        )
    )
    payload = catalogue.to_dict()
    assert payload["extraction_status"] == "blocked"
    assert payload["restaurant"]["name"] is None
    assert payload["categories"] == []
    assert payload["item_count"] == 0
    assert payload["error"]
