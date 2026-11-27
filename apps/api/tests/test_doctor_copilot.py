from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app import main
from tests.test_platform import client, picture, session


def saved_case(client, session):
    response = client.post('/api/v1/doctor/cases', data={'plot_id': session['plot_id']},
                           files={'image': ('leaf.jpg', picture(), 'image/jpeg')})
    assert response.status_code == 200
    return response.json()['id']


def test_case_check_ins_separate_farmer_reports_from_screening_and_retry_safely(client, session, monkeypatch):
    case_id = saved_case(client, session)
    path = f'/api/v1/doctor/cases/{case_id}'
    before = client.get(path).json()
    payload = {'request_id': uuid4().hex, 'change': 'worsening', 'note': '  Three more plants have spots.  '}
    created = client.post(path + '/check-ins', json=payload)
    assert created.status_code == 201
    item = created.json()
    assert item['change'] == 'worsening' and item['note'] == 'Three more plants have spots.'
    assert item['source_record_id'] == case_id and item['plot_id'] == session['plot_id']
    assert client.post(path + '/check-ins', json=payload).json() == item
    assert client.post(path + '/check-ins', json={**payload, 'change': 'unchanged'}).status_code == 409
    assert client.post(path + '/check-ins', json={**payload, 'change': 'confirmed_disease'}).status_code == 422
    assert client.post(path + '/feedback', json={'note': 'Checked the lower leaves.'}).is_success
    current = client.get(path).json()
    assert current['check_ins'] == [item]
    assert [value['note'] for value in current['feedback']] == ['Checked the lower leaves.']
    assert current['classification'] == before['classification']

    inputs = []
    def groq(system, data, tokens):
        inputs.append(data)
        return {'scope': 'farm', 'topic': 'health', 'language': 'en'} if 'evidence' not in data else {}
    monkeypatch.setattr(main.farmer_chat, 'groq_json', groq)
    monkeypatch.setattr(main.farmer_chat, 'collect_sources', lambda *_: [])
    response = client.post('/api/v1/farmer-chat/messages', json={
        'request_id': uuid4().hex, 'case_id': case_id, 'locale': 'en',
        'message': 'What should I check next in this saved crop screening?',
    })
    assert response.is_success and inputs[-1]['evidence']['case']['farmer_check_ins'][0]['change'] == 'worsening'
    assert 'You reported worsening' in response.json()['messages'][-1]['text']


def test_case_reminder_uses_original_plot_and_is_removed_with_the_case(client, session):
    case_id = saved_case(client, session)
    path = f'/api/v1/doctor/cases/{case_id}'
    farm_tools = f"/api/v1/farm-tools/plots/{session['plot_id']}"
    other = client.post('/api/v1/auth/demo', json={}).json()
    stranger = {'Authorization': 'Bearer ' + other['token']}
    today = datetime.now(timezone(timedelta(hours=6))).date()
    first = {'due_on': (today + timedelta(days=1)).isoformat(), 'locale': 'en'}
    assert client.post(path + '/reminder', json=first, headers=stranger).status_code == 404
    assert client.post(path + '/check-ins', json={'change': 'unsure', 'request_id': uuid4().hex},
                       headers=stranger).status_code == 404
    assert client.post(path + '/reminder', json={**first, 'due_on': str(today - timedelta(days=1))}).status_code == 422
    assert client.post(path + '/reminder', json={**first, 'plot_id': other['plot_id']}).status_code == 422
    reminder = client.post(path + '/reminder', json=first).json()
    assert reminder['case_id'] == case_id and reminder['due_on'] == first['due_on']
    assert client.post(path + '/reminder', json=first).json() == reminder
    moved = client.post(path + '/reminder', json={'due_on': str(today + timedelta(days=4)), 'locale': 'bn'}).json()
    assert moved['id'] == reminder['id'] and moved['due_on'] != first['due_on']
    assert client.get(path).json()['follow_up_reminder'] == moved
    assert [row for row in client.get(farm_tools).json()['reminders'] if row['id'] == moved['id']] == [moved]
    assert client.delete(path).is_success
    assert not client.get(farm_tools).json()['reminders']
    assert client.post(path + '/reminder', json=first).status_code == 404
