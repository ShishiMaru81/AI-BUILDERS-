import base64
from itertools import count

import pytest
from cryptography.fernet import Fernet
import httpx

from app import otp_auth
from tests.test_platform import client, picture


@pytest.fixture(autouse=True)
def configured_sms(monkeypatch):
    monkeypatch.delenv('TWILIO_ACCOUNT_SID', raising=False)
    monkeypatch.delenv('TWILIO_AUTH_TOKEN', raising=False)
    monkeypatch.setenv('TWILIO_VERIFY_SERVICE_SID', 'VA' + 'a' * 32)
    monkeypatch.setenv('TWILIO_API_KEY_SID', 'SK' + 'b' * 32)
    monkeypatch.setenv('TWILIO_API_KEY_SECRET', 'test-provider-secret')


def test_unconfigured_otp_never_claims_to_send_a_code(client, monkeypatch):
    monkeypatch.delenv('TWILIO_API_KEY_SECRET')
    assert client.get('/api/v1/auth/options').json()['otp'] is False
    response = client.post('/api/v1/auth/otp/start', json={
        'contact': '+8801712345678', 'purpose': 'login',
    })
    assert response.status_code == 503
    assert 'verification_id' not in response.json()


def test_hosted_accounts_allow_password_signup_and_login_with_encryption(client, monkeypatch):
    monkeypatch.setenv('HOSTING_TIER', 'vercel_demo')
    monkeypatch.setenv('ENABLE_HOSTED_ACCOUNTS', '1')
    monkeypatch.setenv('SIGNUP_DATA_KEY', 'invalid-test-key')
    assert client.get('/api/v1/auth/options').json()['signup'] is False
    assert client.post('/api/v1/auth/signup', json={}).status_code == 403

    monkeypatch.setenv('SIGNUP_DATA_KEY', Fernet.generate_key().decode())
    options = client.get('/api/v1/auth/options').json()
    assert options['demo'] and options['signup'] and not options['otp']
    contact = 'hosted-test@example.test'
    password = 'synthetic test password'
    profile = {
        'name': 'Hosted Test Farmer', 'age': 27, 'role': 'farmer', 'gender': 'female',
        'national_id': '1234567890', 'present_address': 'Sample test address',
        'permanent_address': 'Sample test address', 'ward_number': '12',
        'photo_base64': base64.b64encode(picture()).decode(),
        'password': password, 'confirm_password': password,
    }
    signup = client.post('/api/v1/auth/signup', json={'contact': contact, 'profile': profile})
    assert signup.status_code == 200, signup.text
    assert client.post('/api/v1/auth/otp/start', json={'contact': contact, 'purpose': 'signup'}).status_code == 403
    login = client.post('/api/v1/auth/password', json={'contact': contact, 'password': password})
    assert login.status_code == 200
    headers = {'Authorization': 'Bearer ' + login.json()['token']}
    own = client.get('/api/v1/me', headers=headers).json()
    assert own['id'] == signup.json()['user']['id'] and own['role'] == 'farmer'
    assert 'national_id' not in own and 'permanent_address' not in own
    assert client.get('/api/v1/me/signup-photo', headers=headers).status_code == 200


def test_account_sid_and_auth_token_can_send_verification(client, monkeypatch):
    monkeypatch.delenv('TWILIO_API_KEY_SID')
    monkeypatch.delenv('TWILIO_API_KEY_SECRET')
    monkeypatch.setenv('TWILIO_ACCOUNT_SID', 'AC' + 'c' * 32)
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', 'test-account-token')
    monkeypatch.setenv('SIGNUP_DATA_KEY', Fernet.generate_key().decode())
    monkeypatch.setattr(otp_auth, 'send_limit', otp_auth.AuthLimiter())
    outbound = []

    def provider_post(url, **kwargs):
        outbound.append((url, kwargs['auth'], kwargs['data']))
        return httpx.Response(201, request=httpx.Request('POST', url),
                              json={'sid': 'VE' + 'd' * 32, 'status': 'pending'})

    monkeypatch.setattr(otp_auth.httpx, 'post', provider_post)
    assert client.get('/api/v1/auth/options').json()['signup'] is True
    response = client.post('/api/v1/auth/otp/start', json={
        'contact': '+8801712345678', 'purpose': 'signup',
    })
    assert response.status_code == 200
    assert response.json()['verification_id'] == 'VE' + 'd' * 32
    assert outbound == [(
        'https://verify.twilio.com/v2/Services/VA' + 'a' * 32 + '/Verifications',
        ('AC' + 'c' * 32, 'test-account-token'),
        {'To': '+8801712345678', 'Channel': 'sms'},
    )]


def test_otp_signup_login_and_role_permissions(client, monkeypatch):
    monkeypatch.setenv('SIGNUP_DATA_KEY', Fernet.generate_key().decode())
    pending = {}
    ids = count(1)

    def fake_provider(endpoint, data):
        if endpoint == 'Verifications':
            sid = 'VE' + f'{next(ids):032x}'
            pending[sid] = data['To']
            return {'sid': sid, 'status': 'pending'}
        contact = pending.pop(data['VerificationSid'], None) if data['Code'] == '123456' else None
        return {'to': contact, 'status': 'approved' if contact else 'pending'}

    monkeypatch.setattr(otp_auth, 'verify_request', fake_provider)
    monkeypatch.setattr(otp_auth, 'send_limit', otp_auth.AuthLimiter())
    monkeypatch.setattr(otp_auth, 'check_limit', otp_auth.AuthLimiter())
    base = '/api/v1'
    for contact, role in [('+8801712345678', 'farmer'), ('Customer@Gmail.com', 'customer')]:
        body = {'contact': contact, 'purpose': 'signup'}
        sid = client.post(base+'/auth/otp/start', json=body).json()['verification_id']
        profile = {
            'name': 'Test account', 'age': 27, 'role': role, 'gender': 'female',
            'national_id': '1234567890', 'present_address': 'Present address, Dhaka',
            'permanent_address': 'Permanent address, Dhaka', 'ward_number': '12',
            'photo_base64': base64.b64encode(picture()).decode(),
            'password': 'correct horse battery', 'confirm_password': 'correct horse battery',
        }
        verify = body | {'verification_id': sid, 'code': '000000', 'profile': profile}
        for candidate in ('0123456789', '0123456789012', '০১২৩৪৫৬৭৮৯০১২৩৪৫৬'):
            validated = otp_auth.ProfileInput.model_validate(profile | {'national_id': candidate})
            assert validated.national_id.get_secret_value() == candidate.translate(otp_auth.BANGLA_DIGITS)
        for candidate in ('123456789', '12345678901', '123456789012345678', '123456789A', ' 1234567890', '12345 67890'):
            invalid = client.post(base+'/auth/otp/verify', json=verify | {
                'profile': profile | {'national_id': candidate},
            })
            assert invalid.status_code == 422
            assert 'national_id' in invalid.json()['message'] and candidate not in invalid.text
        bad_password = profile | {'confirm_password': 'mismatched password'}
        rejected = client.post(base+'/auth/otp/verify', json=verify | {'profile': bad_password})
        assert rejected.status_code == 422
        assert profile['password'] not in rejected.text and profile['national_id'] not in rejected.text
        assert client.post(base+'/auth/otp/verify', json=verify).status_code == 401
        assert client.post(base+'/auth/otp/verify', json=verify | {'profile': verify['profile'] | {'role':'admin'}}).status_code == 422
        signup = client.post(base+'/auth/otp/verify', json=verify | {'code':'123456'})
        assert signup.status_code == 200, signup.text
        assert signup.json()['user']['role'] == role
        assert client.post(base+'/auth/otp/verify', json=verify | {'code':'123456'}).status_code == 401

        login = {'contact': contact, 'purpose': 'login'}
        sid = client.post(base+'/auth/otp/start', json=login).json()['verification_id']
        verified = client.post(base+'/auth/otp/verify', json=login | {'verification_id':sid,'code':'123456'})
        assert verified.status_code == 200, verified.text
        headers = {'Authorization': 'Bearer ' + verified.json()['token']}
        own = client.get(base+'/me', headers=headers).json()
        assert own['age'] == 27 and own['gender'] == 'female'
        assert 'national_id' not in own and 'permanent_address' not in own
        photo = client.get(base+'/me/signup-photo', headers=headers)
        assert photo.status_code == 200 and photo.headers['content-type'] == 'image/jpeg'
        password = client.post(base+'/auth/password', json={'contact':contact,'password':profile['password']})
        assert password.status_code == 200
        assert client.get(base+'/me/signup-photo').status_code == 401
        from app.db import Session, SignupIdentity, User
        with Session() as db:
            private = db.get(SignupIdentity, own['id'])
            assert profile['national_id'].encode() not in private.encrypted_details
            assert private.encrypted_photo != photo.content
            assert db.get(User, own['id']).password_hash.startswith('scrypt$')
        assert (own['phone'], own['email']) == (
            ('+8801712345678', None) if role == 'farmer' else (None, 'customer@gmail.com')
        )

        for session in (signup, verified, password):
            session_headers = {'Authorization': 'Bearer ' + session.json()['token']}
            seller_status = 200 if role == 'farmer' else 403
            buyer_status = 200 if role == 'customer' else 403
            assert client.get(base+'/doctor/cases', headers=session_headers).status_code == seller_status
            assert client.get(base+'/market/farmer/dashboard', headers=session_headers).status_code == seller_status
            assert client.get(base+'/market/cart', headers=session_headers).status_code == buyer_status

def test_bangladesh_phone_length_and_email(client, monkeypatch):
    monkeypatch.setenv('SIGNUP_DATA_KEY', Fernet.generate_key().decode())
    sent = []

    def fake_provider(endpoint, data):
        sent.append(data)
        return {'sid': 'VE'+'a'*32, 'status': 'pending'}

    monkeypatch.setattr(otp_auth, 'verify_request', fake_provider)
    monkeypatch.setattr(otp_auth, 'send_limit', otp_auth.AuthLimiter())
    url = '/api/v1/auth/otp/start'
    for invalid in ('+880171234567', '+88017123456789', '01712345678', '8801712345678',
                    '+88017123 45678', '+88017123-45678', '+12025550123', '+880171234567x'):
        assert client.post(url, json={'contact': invalid, 'purpose': 'signup'}).status_code == 422
    assert sent == []
    for valid, destination in [
        ('+8801712345678', '+8801712345678'),
        ('+৮৮০১৭১২৩৪৫৬৭৮', '+8801712345678'),
        ('Customer@Gmail.com', 'customer@gmail.com'),
    ]:
        assert client.post(url, json={'contact': valid, 'purpose': 'signup'}).status_code == 200
        assert sent[-1]['To'] == destination
