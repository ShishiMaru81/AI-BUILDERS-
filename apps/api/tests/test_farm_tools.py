from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from tests.test_platform import client, session
from app.db import Record, Session, User
from app.farm_tools import _today
from app.services import DemoWeatherProvider, preparedness


def test_calendar_reminders_and_private_ledger(client, session):
    plot = session['plot_id']
    base = '/api/v1/farm-tools/plots/' + plot
    today = _today()
    start = today - timedelta(days=16)
    assert client.patch(base + '/planting', json={'date': str(start), 'stage': 'Fruiting'}).is_success
    result = client.get(base).json()
    assert result['calendar']['planting_week'] == 3
    assert result['calendar']['region'] == 'Dhaka'
    assert 'fruit' in result['calendar']['tasks'][0]['en'].lower()
    reminder = client.post(base + '/reminders', json={'label': 'Check waterlogged rows', 'due_on': str(today)})
    assert reminder.status_code == 201
    payload = {'kind': 'expense', 'category': 'seed', 'date': str(today), 'label': 'Seeds', 'amount_bdt': '20.15'}
    assert client.post(base + '/ledger', json=payload).status_code == 201
    assert client.post(base + '/ledger', json={**payload, 'amount_bdt': '0.009'}).status_code == 422
    assert client.post(base + '/ledger', json={**payload, 'kind': 'receipt', 'category': 'sale',
                                               'amount_bdt': '30.1'}).status_code == 201
    assert client.get(base + '?break_even_kg=3').json()['summary'] == {
        'expenses_bdt': '20.15', 'receipts_bdt': '30.1', 'margin_bdt': '9.95', 'break_even_bdt_per_kg': '6.72',
    }
    second = client.post('/api/v1/auth/demo', json={}).json()
    other = {'Authorization': 'Bearer ' + second['token']}
    assert client.get(base, headers=other).status_code == 404
    target = '/api/v1/farm-tools/records/farm_reminder/' + reminder.json()['id']
    assert client.delete(target, headers=other).status_code == 404
    assert client.delete(target).is_success


def test_storage_preserves_balances_and_cascades(client, session):
    plot = session['plot_id']
    today = str(_today())
    base = '/api/v1/farm-tools/plots/' + plot
    batch = client.post(base + '/storage', json={'label': 'First harvest', 'method': 'ventilated',
                                                'harvested_on': today, 'stored_on': today, 'quantity_kg': '12.5'}).json()
    events = '/api/v1/farm-tools/storage/' + batch['id'] + '/events'
    payload = {'label': 'Damage', 'date': today, 'kind': 'loss', 'quantity_kg': '2.5'}
    lost = client.post(events, json=payload).json()
    assert (lost['remaining_kg'], lost['loss_pct']) == (10, 20)
    assert client.post(events, json={**payload, 'quantity_kg': '10.001'}).status_code == 409
    assert client.post(events, json={**payload, 'kind': 'inspection', 'quantity_kg': None}).is_success
    removal = client.delete(events + '/' + lost['events'][0]['id']).json()
    assert removal['remaining_kg'] == 12.5
    assert client.delete('/api/v1/plots/' + plot).is_success
    with Session() as db:
        assert db.get(Record, batch['id']) is None


def test_community_suppresses_small_counts_and_withdrawal(client, session):
    accounts = [session, *(client.post('/api/v1/auth/demo', json={}).json() for _ in range(2))]
    reports = []
    for account in accounts:
        with Session() as db:
            plot = db.get(Record, account['plot_id'])
            user = db.get(User, plot.owner_id)
            user.is_demo = False
            case = Record(owner_id=user.id, kind='case', plot_id=plot.id,
                          payload={'crop': 'tomato', 'meta': {'is_simulated': False},
                                   'classification': {'top_label': 'Possible leaf damage', 'abstained': False}})
            db.add(case)
            db.commit()
            reports.append(case.id)
    aggregate = '/api/v1/farm-tools/community'
    for index, (account, case_id) in enumerate(zip(accounts,reports)):
        headers = {'Authorization': 'Bearer ' + account['token']}
        endpoint = '/api/v1/farm-tools/plots/' + account['plot_id'] + '/community'
        assert client.post(endpoint, headers=headers, json={'case_id': case_id, 'consent': False}).status_code == 422
        assert client.post(endpoint, headers=headers, json={'case_id': case_id, 'consent': True}).is_success
        assert client.post(endpoint, headers=headers, json={'case_id': case_id, 'consent': True}).is_success
        districts = client.get(aggregate).json()['districts']
        assert len(districts) == 64
        assert [row['band'] for row in districts if row['band']] == (['3–5'] if index == 2 else [])
        assert all(set(row) == {'id', 'en', 'bn', 'band'} for row in districts)
    assert client.delete(aggregate + '/' + reports[1]).status_code == 404
    assert client.delete(aggregate + '/' + reports[0]).is_success
    assert all(row['band'] is None for row in client.get(aggregate).json()['districts'])


def test_smart_alert_does_not_use_demo_and_can_be_dismissed(client, session):
    plot_id = session['plot_id']
    base = '/api/v1/farm-tools/plots/' + plot_id
    assert client.get('/api/v1/flood/plots/' + plot_id + '/outlook').is_success
    assert client.get(base).json()['alerts'] == []
    with Session() as db:
        plot = db.get(Record, plot_id)
        case = Record(owner_id=plot.owner_id, kind='case', plot_id=plot_id, payload={
            'meta': {'is_simulated': False}, 'classification': {'abstained': False, 'top_label': 'Possible spotting'},
        })
        db.add(case)
        db.commit()
    alerts = client.get(base).json()['alerts']
    assert len(alerts) == 1 and alerts[0]['kind'] == 'scout'
    assert client.post(base + '/alerts/' + alerts[0]['id'] + '/dismiss').is_success
    assert client.get(base).json()['alerts'] == []
    with Session() as db:
        weather = db.scalar(select(Record).where(Record.plot_id == plot_id, Record.kind == 'weather'))
        forecast = DemoWeatherProvider().forecast(24, 90)
        forecast['meta'].update(mode='LIVE', is_simulated=False)
        forecast['hourly'] = [{**hour, 'rain_mm': 10} for hour in forecast['hourly']]
        weather.payload = preparedness(forecast, 24)
        db.commit()
        rain = client.get(base).json()['alerts']
        assert len(rain) == 1 and rain[0]['kind'] == 'rain'
        weather.payload = {**weather.payload, 'meta': {
            **weather.payload['meta'], 'retrieved_at': (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat(),
        }}
        db.commit()
    assert client.get(base).json()['alerts'] == []
