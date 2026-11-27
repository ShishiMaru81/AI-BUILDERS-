from tests.test_platform import client, session

from app.db import Record, Session, User
from app.market_admin import create_admin
from app.market_auth import hash_password


def test_admin_login_and_console_allow_only_active_admins(client, session):
    password = 'test-only-operator-password'
    with Session() as db:
        operator = create_admin(db, email='operator@example.test', name='Test operator', password=password)
        operator_id = operator.id
        db.add(User(email='customer@example.test', name='Customer', role='customer',
                    password_hash=hash_password(password)))
        db.add(Record(owner_id=operator_id, kind='farmer_chat', payload={'messages': ['private marker']}))
        db.commit()
    path = '/api/v1/auth/admin/login'
    calls = [
        {'email': 'customer@example.test', 'password': password},
        {'email': 'operator@example.test', 'password': 'wrong password'},
        {'email': 'unknown@example.test', 'password': password},
    ]
    responses = [client.post(path, json=credentials) for credentials in calls]
    assert all(response.status_code == 401 for response in responses)
    assert len({response.json()['message'] for response in responses}) == 1

    overview = '/api/v1/admin/overview'
    system = '/api/v1/admin/system'
    assert client.get(overview, headers={'Authorization': 'Bearer invalid'}).status_code == 401
    for forbidden in [overview, system, '/api/v1/admin/market/users']:
        assert client.get(forbidden).status_code == 403
    result = client.post(path, json={'email': ' OPERATOR@EXAMPLE.TEST ', 'password': password})
    assert result.status_code == 200
    assert result.json()['user']['role'] == 'admin'
    headers = {'Authorization': 'Bearer ' + result.json()['token']}
    response = client.get(overview, headers=headers)
    assert response.status_code == 200 and response.headers['Cache-Control'] == 'no-store'
    data = response.json()
    assert data['accounts']['admin'] == 1
    assert data['records']['farm'] == 1 and data['records']['farmer_chat'] == 1
    assert 'private marker' not in response.text and 'operator@example.test' not in response.text
    for collection in ('users', 'products', 'orders', 'auctions', 'reports', 'audit'):
        assert client.get('/api/v1/admin/market/' + collection, headers=headers).status_code == 200
    search = client.get('/api/v1/admin/market/users', params={'search': 'test operator'}, headers=headers).json()
    assert search['total'] == 1 and search['items'][0]['id'] == operator_id
    assert client.get('/api/v1/admin/market/users', params={'search': '%'}, headers=headers).json()['total'] == 0
    private_input = client.post(path, json={'email': 'operator@example.test', 'password': 'private marker', 'role': 'admin'})
    assert private_input.status_code == 422 and 'private marker' not in private_input.text
    assert client.get(system, headers=headers).status_code == 200
    assert client.post('/api/v1/auth/logout', headers=headers).status_code == 200
    assert client.get(overview, headers=headers).status_code == 401
    with Session() as db:
        db.get(User, operator_id).is_active = False
        db.commit()
    assert client.post(path, json={'email': 'operator@example.test', 'password': password}).status_code == 401


def test_hosted_admin_login_works_with_provisioned_account(client, monkeypatch):
    monkeypatch.setenv('HOSTING_TIER', 'vercel_demo')
    with Session() as db:
        create_admin(db, email='operator@example.test', name='Test operator', password='hosted-test-operator')
    response = client.post('/api/v1/auth/admin/login', json={
        'email': 'operator@example.test', 'password': 'hosted-test-operator',
    })
    assert response.status_code == 200
    denied = client.post('/api/v1/auth/register', json={
        'email': 'unprovisioned@example.test', 'password': 'hosted-test-operator', 'role': 'admin',
    })
    assert denied.status_code == 403
