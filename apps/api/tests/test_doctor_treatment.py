import pytest

from app import farmer_chat as chat
from tests.test_doctor_vision import finding, provider, upload
from tests.test_platform import client, session


def late_blight():
    return finding(part='leaf', produce_finding=None, subject='Tomato leaf', condition='Late blight',
                   marker='surface_growth', distinguishing_sign='Pale growth on the underside along fresh lesions.',
                   signs=['Irregular dark lesions with pale growth at the underside edge.'])


def test_ai_screening_and_reopened_case_share_verified_product_reference(client, session, monkeypatch):
    provider(monkeypatch, late_blight())
    response = upload(client, plot_id=session['plot_id'], plant_part='leaf')
    assert response.status_code == 200
    screened = response.json()
    guidance = screened['treatment_guidance']
    assert guidance['en']['products'][0]['registration'] == 'AP-1075'
    assert guidance['bn']['products'][0] == guidance['en']['products'][0]
    assert 'extension officer' in guidance['en']['summary']
    assert 'current Bangladesh label' in ' '.join(guidance['en']['steps'])
    assert 'g/L' not in str(guidance)
    path = '/api/v1/doctor/cases/' + screened['id']
    assert client.get(path).json()['treatment_guidance'] == guidance


@pytest.mark.parametrize(('image_result', 'expected'), [
    (finding(), 'storage'),
    (finding(part='leaf', condition='Late blight', marker='nonspecific'), 'uncertain'),
    (finding(part='leaf', condition='Late blight', crop_match='mismatch'), 'uncertain'),
    (finding(part='leaf', condition='Tomato yellow leaf curl virus', marker='distinct_damage_distribution'), 'nonchemical'),
])
def test_a_lookalike_a_mismatched_crop_or_produce_gets_no_product(client, session, monkeypatch, image_result, expected):
    provider(monkeypatch, image_result)
    response = upload(client, crop='tomato')
    assert response.status_code == 200
    guidance = response.json()['treatment_guidance']['en']
    assert guidance['status'] == expected
    assert not guidance['products']


def test_farmer_chat_uses_cited_treatment_references_instead_of_a_model_guess(monkeypatch):
    monkeypatch.setattr(chat, 'groq_json', lambda *args: pytest.fail('Treatment must be grounded by the reviewed catalog.'))
    reply, state = chat.make_turn('What fungicide is listed for potato late blight?', 'en', [], {}, {})
    assert 'Revus 250 SC' in reply['text'] and 'AP-2534' in reply['text']
    assert any('dae.gov.bd' in item['url'] for item in reply['sources'])
    dosage, _ = chat.make_turn('How much should I use per litre?', 'en', [], state, {})
    assert 'current label' in dosage['text']
    assert 'mL' not in dosage['text'] and 'Revus' not in dosage['text']


def test_a_saved_uncertain_screening_cannot_be_turned_into_a_product_recommendation(monkeypatch):
    monkeypatch.setattr(chat, 'groq_json', lambda *args: pytest.fail('Treatment routing must not ask the model to guess.'))
    context = {'case_id': 'case', 'treatment_guidance': {'en': {
        'status': 'uncertain', 'crop': 'potato', 'condition': None, 'products': [], 'sources': [], 'steps': [],
        'summary': 'There is not enough evidence to identify a treatment option.',
    }}}
    reply, _ = chat.make_turn('What fungicide should I spray for potato late blight?', 'en', [], {}, context)
    assert 'not enough evidence' in reply['text'] and 'Revus' not in reply['text']


def test_bengali_treatment_handles_inflection_and_keeps_differential_open(monkeypatch):
    monkeypatch.setattr(chat, 'groq_json', lambda *args: pytest.fail('Treatment routing must stay on verified entries.'))
    reply, _ = chat.make_turn('টমেটোর নাবি ধসায় কী ওষুধ আছে?', 'bn', [], {}, {})
    assert 'AP-1075' in reply['text']
    unclear, _ = chat.make_turn('টমেটোর আগাম বা নাবি ধসায় কী ওষুধ আছে?', 'bn', [], {}, {})
    assert 'AP-1075' not in unclear['text']
