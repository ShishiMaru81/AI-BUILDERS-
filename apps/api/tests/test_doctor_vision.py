"""Exercise the authenticated upload path with only the external vision service replaced."""
import base64
import io
import json

import httpx
import pytest
from PIL import Image

from tests.test_platform import client, session


def upload(client, **form):
    out = io.BytesIO()
    Image.effect_noise((320, 240), 70).convert('RGB').save(out, 'PNG')
    return client.post('/api/v1/doctor/cases', data=form, files={'image': ('test.png', out.getvalue(), 'image/png')})


def provider(monkeypatch, answer, status=200, *, expected_instruction=None):
    monkeypatch.setenv('GROQ_API_KEY', 'unit-test-only')
    def post(url, *, headers, json, timeout):
        assert url == 'https://api.groq.com/openai/v1/chat/completions'
        assert 0 < json['max_completion_tokens'] <= 1000
        if expected_instruction is not None:
            assert expected_instruction in json['messages'][0]['content']
        content = json['messages'][-1]['content']
        data_url = next(item['image_url']['url'] for item in content if item['type'] == 'image_url')
        image = Image.open(io.BytesIO(base64.b64decode(data_url.split(',')[1])))
        assert image.format == 'JPEG' and image.size == (320, 240) and not image.getexif()
        return httpx.Response(status, json={'choices': [{'message': {'content': answer}}]})
    monkeypatch.setattr(httpx, 'post', post)


def finding(**changes):
    return json.dumps(dict(dict(outcome='possible_condition', subject='Tomato fruit', part='produce', produce_finding='surface_mold',
        crop_match='match', pattern='Fruit surface decay', marker='surface_growth', distinguishing_sign='Fuzzy growth over a collapsed patch.',
        condition='Possible fruit rot', signs=['A sunken brown patch on the fruit.'],
        explanation='The localized collapse is consistent with decay.', uncertainty='A photo cannot identify the organism.',
        next_steps=['Inspect nearby fruit for similar patches.']), **changes))


def test_produce_vision_saves_evidence_and_exposes_active_model(client, session, monkeypatch):
    provider(monkeypatch, finding())
    caps = client.get('/api/v1/doctor/capabilities').json()
    assert caps.get('provider') == 'groq'
    result = upload(client, plot_id=session['plot_id'], plant_part='other').json()
    assert result['classification']['top_label'] == 'Possible mold-associated decay'
    assert result['classification']['score'] is None and result['meta']['mode'] == 'LIVE'
    assert result['assessment']['part'] == 'produce'
    stored = client.get('/api/v1/doctor/cases/'+result['id']).json()
    assert stored['assessment'] == result['assessment']
    assert 'sunken brown patch' in client.get('/api/v1/doctor/cases/'+result['id']+'/report').text


def test_other_crop_preview_and_plot_mismatch(client, session, monkeypatch):
    provider(monkeypatch, finding(subject='Carrot', crop_match='mismatch'))
    for form in [{'crop': 'auto'}, {'plot_id': session['plot_id']}]:
        response = upload(client, **form)
        assert response.status_code == 200, response.text
        assert response.json()['assessment']['subject'] == 'Carrot'
        assert 'id' not in response.json()
    assert client.get('/api/v1/doctor/cases').json()['total'] == 0


def test_research_leaf_preview_stays_local_and_unsaved(client, session, monkeypatch):
    from app.doctor_models import DoctorRegistry

    monkeypatch.setenv('GROQ_API_KEY', 'unit-test-only')

    def local(_registry, image, crop):
        assert crop == 'tomato' and image.size == (320, 240)
        return {'model': {'model_id': 'agrodoctor-research-leaf', 'version': 'test-export', 'available': True},
                'crop': crop, 'status': 'unable_to_classify'}

    monkeypatch.setattr(DoctorRegistry, 'infer_research', local)
    form = dict(crop='tomato', plant_part='leaf', screening_mode='research_leaf')
    result = upload(client, **form)
    assert result.status_code == 200, result.text
    assert result.json()['model']['version'] == 'test-export'
    assert 'id' not in result.json()
    assert upload(client, **{**form, 'plot_id': session['plot_id']}).status_code == 422
    assert upload(client, **{**form, 'plant_part': 'other'}).status_code == 422
    assert client.get('/api/v1/doctor/cases').json()['total'] == 0


def test_research_produce_preview_needs_no_cloud_and_does_not_save(client, session, monkeypatch):
    from app.doctor_models import DoctorRegistry

    monkeypatch.delenv('GROQ_API_KEY', raising=False)

    def local(_registry, image, crop, *, part='leaf'):
        assert part == 'produce' and crop == 'potato' and image.size == (320, 240)
        return {'model': {'model_id': 'agrodoctor-research-produce', 'version': 'test-produce', 'available': True},
                'crop': crop, 'status': 'unable_to_classify'}

    monkeypatch.setattr(DoctorRegistry, 'infer_research', local)
    form = {'crop': 'potato', 'plant_part': 'other', 'screening_mode': 'research_produce'}
    result = upload(client, **form)
    assert result.status_code == 200, result.text
    assert result.json()['model']['version'] == 'test-produce'
    assert 'id' not in result.json()
    assert upload(client, **{**form, 'plant_part': 'leaf'}).status_code == 422
    assert client.get('/api/v1/doctor/cases').json()['total'] == 0


@pytest.mark.parametrize('outcome', ['uncertain', 'unrelated'])
def test_abstention_never_displays_spurious_label(client, session, monkeypatch, outcome):
    provider(monkeypatch, finding(outcome=outcome, part='unknown', crop_match='unknown', condition='bogus'))
    result = upload(client, crop='tomato').json()
    assert result['classification']['abstained']
    assert result['classification']['top_label'] == 'unknown'
    assert result['assessment']['condition'] is None


@pytest.mark.parametrize('body,status,expected', [('{}', 200, 502), ('busy', 429, 429), ('unavailable', 503, 503)])
def test_provider_failure_never_saves_a_guess(client, session, monkeypatch, body, status, expected):
    provider(monkeypatch, body, status)
    assert upload(client, plot_id=session['plot_id']).status_code == expected
    assert client.get('/api/v1/doctor/cases').json()['total'] == 0



def test_generic_signs_only_support_a_symptom_pattern(client, session, monkeypatch):
    provider(monkeypatch, finding(part='leaf', condition='Specific infection', pattern='Leaf spotting',
                                  distinguishing_sign='A yellow halo.', marker='nonspecific'))
    result = upload(client, plot_id=session['plot_id']).json()
    assert result['classification']['top_label'] == 'Leaf spotting'
    assert result['assessment']['condition'] is None


def test_potato_leaf_screen_considers_leafroll_and_rejects_generic_curling(client, session, monkeypatch):
    provider(monkeypatch, finding(subject='Potato leaf', part='leaf', produce_finding=None,
                                  condition='Potato leafroll virus', pattern='Upward curling',
                                  distinguishing_sign='One leaflet rolls upward.', marker='nonspecific'),
             expected_instruction='A lone discolored or curled')
    result = upload(client, crop='potato', plant_part='leaf').json()
    assert result['classification']['top_label'] == 'Upward curling'
    assert result['assessment']['condition'] is None


def test_conflicting_leaf_screens_do_not_report_no_visible_damage(client, session, monkeypatch):
    from app.doctor_models import DoctorRegistry
    provider(monkeypatch, finding(outcome='no_visible_damage', part='leaf', condition=None))
    monkeypatch.setattr(DoctorRegistry, 'infer', lambda *args: {
        'model': {'version': 'test-leaf-model'}, 'classification': {'abstained': False, 'top_label': 'Tomato___Late_blight'}})
    result = upload(client, plot_id=session['plot_id']).json()
    assert result['assessment']['outcome'] == 'uncertain'
    assert result['classification']['abstained']
    assert result['classification']['rejection_reason'] == 'model_disagreement'
    assert result['cross_check_model'] == 'test-leaf-model'


def test_internal_produce_damage_never_inherits_a_speculative_pathogen(client, session, monkeypatch):
    provider(monkeypatch, finding(produce_finding='internal_breakdown', condition='Unverified pathogen',
                                  explanation='Unverified pathogen', uncertainty='Unverified pathogen',
                                  next_steps=['Smell the tuber.']))
    result = upload(client, crop='auto').json()
    assert result['classification']['top_label'] == 'Possible internal decay'
    assert 'Unverified pathogen' not in json.dumps(result)
    assert 'Smell the tuber' not in json.dumps(result)
