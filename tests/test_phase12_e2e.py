import pytest
from backend.improvement.contract import ImprovementLineRequest
from backend.improvement.service import apply_improvement, create_improvement, set_generator_factory
from backend.media.service import create_media_job, apply_media_job
from backend.media.contract import MediaJobRequest
from backend.media.persist import store_artifact_bytes, new_id
from backend.history.service import list_history, rollback_history
from backend.store import get_catalogue, save_catalogue
from backend.services.grading_service import grade_catalogue
from backend.schemas import CatalogCreateResponse
from PIL import Image
from io import BytesIO

from tests.test_phase6_improvement import ScriptedGenerator, _safe_desc

def test_phase12_end_to_end_workflow():
    set_generator_factory(lambda: ScriptedGenerator([_safe_desc("Fresh Lemonade")]))
    # Prepare sample catalogue
    cat_data = {
        'id': 'cat_e2e_p12',
        'user_id': 'user_1',
        'organization_id': 'org_1',
        'extraction_status': 'ok',
        'restaurant_name': 'Brew 59',
        'fssai_number': '12345678901234',
        'source_url': 'https://magicpin.in/Belgaum/Sadashiv-Nagar/Restaurant/Brew-59/store/606749/delivery',
        'platform': 'magicpin',
        'restaurant': {'name': 'Brew 59'},
        'categories': [
            {
                'name': 'Drinks',
                'items': [
                    {
                        'name': 'Fresh Lemonade',
                        'price': 120,
                        'description': '',
                        'food_type': 'veg',
                        'labels': []
                    }
                ]
            }
        ]
    }

    stored = save_catalogue(user_id='user_1', organization_id='org_1', result=CatalogCreateResponse.model_validate(cat_data))
    grade_catalogue(user_id='user_1', organization_id='org_1', catalogue_id=stored.id)

    # 1. Initial AI proposal
    p1 = create_improvement(
        user_id='user_1',
        organization_id='org_1',
        catalogue_id=stored.id,
        request=ImprovementLineRequest(check_id='missing_description', paths=['menus[0].categories[0].items[0].description'])
    )
    assert p1.status == "READY"
    assert p1.lines[0].proposed_value is not None
    assert p1.lines[0].provenance.get("mode") == "LLM_GENERATED"

    # 2. Natural language refinement
    p2 = create_improvement(
        user_id='user_1',
        organization_id='org_1',
        catalogue_id=stored.id,
        request=ImprovementLineRequest(
            check_id='missing_description',
            paths=['menus[0].categories[0].items[0].description'],
            instruction='Make it shorter',
            refining_proposal_id=p1.id
        )
    )
    assert p2.status == "READY"
    assert p2.lines[0].proposed_value is not None
    assert p2.lines[0].provenance.get("mode") == "OWNER_REFINED"
    assert p2.lines[0].provenance.get("owner_instruction") == "Make it shorter"

    # 3. Apply description and verify persistence + re-grading
    app_res = apply_improvement(user_id='user_1', organization_id='org_1', catalogue_id=stored.id, proposal_id=p2.id)
    assert app_res.grade_letter is not None

    reloaded = get_catalogue('user_1', stored.id, 'org_1').result
    item = reloaded.categories[0]['items'][0] if isinstance(reloaded.categories[0], dict) else reloaded.categories[0].items[0]
    desc = item['description'] if isinstance(item, dict) else item.description
    price = item['price'] if isinstance(item, dict) else item.price
    assert desc == p2.lines[0].proposed_value
    assert price == 120
    history = list_history(user_id='user_1', organization_id='org_1', catalogue_id=stored.id)
    assert history.records
    applied_row = history.records[0]
    assert applied_row.source == 'improvement'
    assert applied_row.previous_value in {'', None}
    assert applied_row.new_value == p2.lines[0].proposed_value
    assert applied_row.after_grade_score is not None

    # 4. Main Catalogue Hero Image Edit & Apply
    img = Image.new('RGB', (100, 100), color='green')
    buf = BytesIO()
    img.save(buf, format='PNG')

    art_id = new_id()
    local_url = store_artifact_bytes(artefact_id=art_id, user_id='user_1', organization_id='org_1', catalogue_id=stored.id, data=buf.getvalue(), suffix='.png')
    reloaded_dict = reloaded.model_dump(mode="json")
    reloaded_dict["restaurant"]["image_url"] = local_url
    save_catalogue(user_id='user_1', organization_id='org_1', result=CatalogCreateResponse.model_validate(reloaded_dict))

    hero_job = create_media_job(
        user_id='user_1',
        organization_id='org_1',
        catalogue_id=stored.id,
        request=MediaJobRequest(path='restaurant.image_url', operation='edit', prompt='Make the background cleaner')
    )
    assert hero_job.status == "READY"
    assert len(hero_job.candidates) >= 1

    hero_apply = apply_media_job(user_id='user_1', organization_id='org_1', catalogue_id=stored.id, job_id=hero_job.id)
    assert hero_apply.job.status == "APPLIED"

    final_cat = get_catalogue('user_1', stored.id, 'org_1').result
    assert final_cat.restaurant['image_url'] == hero_apply.catalogue_url
    later = list_history(user_id='user_1', organization_id='org_1', catalogue_id=stored.id)
    assert any(row.source == 'media' and row.media_job_id == hero_job.id for row in later.records)
    rolled = rollback_history(user_id='user_1', organization_id='org_1', catalogue_id=stored.id, history_id=applied_row.id, confirm=True)
    assert rolled.source == 'rollback'
    restored = get_catalogue('user_1', stored.id, 'org_1').result
    restored_item = restored.categories[0]['items'][0] if isinstance(restored.categories[0], dict) else restored.categories[0].items[0]
    restored_desc = restored_item['description'] if isinstance(restored_item, dict) else restored_item.description
    assert not (restored_desc or '').strip()
    trail = list_history(user_id='user_1', organization_id='org_1', catalogue_id=stored.id)
    assert any(row.id == applied_row.id for row in trail.records)
    assert trail.records[0].rolled_back_history_id == applied_row.id
