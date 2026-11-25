"""Verified account signup/login with SMTP email or optional Twilio delivery."""
import base64
import binascii
import io
import json
import os
import warnings
import re
import secrets
from typing import Literal

import httpx
from cryptography.fernet import Fernet, InvalidToken
from PIL import Image, ImageOps
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import public_demo_enabled
from .db import SignupIdentity, User, fixture_contact, get_db
from .email_otp import smtp_ready, start_email, consume_email
from .market_auth import AuthLimiter, _DUMMY_HASH, hash_password, issue_session, limit_auth, normalize_email, verify_password

router = APIRouter(prefix='/api/v1/auth', tags=['authentication'])
send_limit = AuthLimiter(window=600, ip_limit=12, identity_limit=3, by_destination=True)
check_limit = AuthLimiter(window=600, ip_limit=40, identity_limit=10, by_destination=True)
BANGLA_DIGITS = str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')


def demo_login_enabled() -> bool:
    default = '1' if public_demo_enabled() or not os.getenv('HOSTING_TIER') else '0'
    return os.getenv('ENABLE_DEMO_LOGIN', default) == '1'


class Contact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    contact: str = Field(min_length=3, max_length=254)

    @field_validator('contact')
    @classmethod
    def normalize(cls, value: str) -> str:
        if '@' in value:
            return normalize_email(value)
        phone = value.translate(BANGLA_DIGITS)
        if not re.fullmatch(r'\+8801[0-9]{9}', phone):
            raise ValueError('Enter a Bangladesh mobile number with exactly 14 characters, including +, such as +8801712345678')
        return phone


class Start(Contact):
    purpose: Literal['login', 'signup']


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=1, le=120)
    role: Literal['farmer', 'customer']

    national_id: SecretStr
    permanent_address: str = Field(min_length=5, max_length=500)
    present_address: str = Field(min_length=5, max_length=500)
    ward_number: str = Field(pattern=r'^[0-9]{1,4}$')
    gender: Literal['male', 'female']
    photo_base64: SecretStr = Field(min_length=4, max_length=1398104)
    password: SecretStr = Field(min_length=10, max_length=128)
    confirm_password: SecretStr = Field(min_length=10, max_length=128)

    @field_validator('name', 'permanent_address', 'present_address', mode='before')
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('national_id')
    @classmethod
    def format_nid(cls, value: SecretStr) -> SecretStr:
        digits = value.get_secret_value().translate(BANGLA_DIGITS)
        if not re.fullmatch(r'(?:[0-9]{10}|[0-9]{13}|[0-9]{17})', digits):
            raise ValueError('Enter exactly 10, 13, or 17 digits for the national ID')
        return SecretStr(digits)

    @model_validator(mode='after')
    def matching_passwords(self):
        if self.password != self.confirm_password:
            raise ValueError('Passwords must match')
        return self


class PasswordSignup(Contact):
    profile: ProfileInput


class ContactPassword(Contact):
    password: SecretStr = Field(min_length=1, max_length=1024)


def identity_cipher() -> Fernet:
    try:
        return Fernet(os.environ['SIGNUP_DATA_KEY'].encode('ascii'))
    except (KeyError, ValueError):
        raise HTTPException(503, 'Private signup storage is not configured on this server') from None


def open_identity(encrypted: bytes) -> bytes:
    try:
        return identity_cipher().decrypt(encrypted)
    except InvalidToken:
        raise HTTPException(503, 'Private account data is temporarily unavailable') from None


def passport_photo(value: SecretStr) -> bytes:
    try:
        data = base64.b64decode(value.get_secret_value(), validate=True)
        if len(data) > 1024 * 1024:
            raise ValueError('Photo too large')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {'JPEG', 'PNG', 'WEBP'} or getattr(image, 'n_frames', 1) != 1 or image.width * image.height > 8_000_000:
                    raise ValueError('Unsupported photo')
                image.load()
                clean = ImageOps.exif_transpose(image).convert('RGB')
                clean.thumbnail((512, 512))
                # Create a fresh image to discard source EXIF, ICC, and other metadata.
                output = io.BytesIO()
                plain = Image.new('RGB', clean.size)
                plain.paste(clean)
                plain.save(output, 'JPEG', quality=85)
                return output.getvalue()
    except (ValueError, binascii.Error, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, 'Use a valid JPG, PNG, or WebP portrait photo up to 1 MB') from None


class Verify(Start):
    verification_id: str = Field(pattern=r'^(?:VE|EM)[a-fA-F0-9]{32}$')
    code: str = Field(pattern=r'^[0-9]{4,10}$')
    profile: ProfileInput | None = None


def provider_settings():
    service = os.getenv('TWILIO_VERIFY_SERVICE_SID', '').strip()
    key = os.getenv('TWILIO_API_KEY_SID', '').strip()
    secret = os.getenv('TWILIO_API_KEY_SECRET', '').strip()
    if key and secret:
        return service, key, secret
    return (service, os.getenv('TWILIO_ACCOUNT_SID', '').strip(),
            os.getenv('TWILIO_AUTH_TOKEN', '').strip())


def verify_request(endpoint: str, data: dict[str, str]) -> dict:
    service, username, secret = provider_settings()
    if not service or not username or not secret:
        raise HTTPException(503, 'Email and SMS verification is not configured on this server')
    try:
        response = httpx.post(
            f'https://verify.twilio.com/v2/Services/{service}/{endpoint}',
            auth=(username, secret),
            data=data,
            timeout=10,
        )
        if response.status_code == 429:
            raise HTTPException(429, 'Too many code attempts. Please wait and try again.')
        if endpoint == 'VerificationCheck' and response.status_code in (400, 404):
            raise HTTPException(401, 'The code is invalid or expired')
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, 'Could not reach the verification provider. Try again later.') from None


def lookup(db: Session, contact: str) -> User | None:
    column = User.email if '@' in contact else User.phone
    return db.scalar(select(User).where(column == contact))


def otp_account(db: Session, account: User | None) -> bool:
    if not account or not account.is_active or account.role == 'admin':
        return False
    if not account.password_hash:
        return True
    identity = db.get(SignupIdentity, account.id)
    return bool(identity and identity.contact_verified)


def email_provider() -> str:
    return os.getenv('AUTH_EMAIL_PROVIDER', 'twilio').strip().lower()


def available_channels() -> dict[str, bool]:
    twilio = all(provider_settings())
    return {
        'email': smtp_ready() if email_provider() == 'smtp' else twilio,
        'sms': twilio and os.getenv('ENABLE_SMS_VERIFICATION', '1') == '1',
    }


def register_profile(db: Session, contact: str, profile: ProfileInput, cipher: Fernet, photo: bytes,
                     *, contact_verified: bool) -> dict:
    try:
        account = User(name=profile.name, age=profile.age, role=profile.role, is_demo=fixture_contact(contact),
                       email=contact if '@' in contact else None,
                       phone=contact if '@' not in contact else None,
                       password_hash=hash_password(profile.password.get_secret_value()))
        db.add(account)
        db.flush()
        details = {
            'national_id': profile.national_id.get_secret_value(),
            'permanent_address': profile.permanent_address,
            'present_address': profile.present_address,
            'ward_number': profile.ward_number,
        }
        db.add(SignupIdentity(user_id=account.id, gender=profile.gender, contact_verified=contact_verified,
                              encrypted_details=cipher.encrypt(json.dumps(details).encode('utf-8')),
                              encrypted_photo=cipher.encrypt(photo)))
        session = issue_session(db, account)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'An account already uses this contact') from None
    return session


@router.post('/signup')
def password_signup(body: PasswordSignup, request: Request, response: Response, db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    limit_auth(request, body.contact)
    if lookup(db, body.contact):
        raise HTTPException(409, 'An account already uses this contact')
    return register_profile(db, body.contact, body.profile, identity_cipher(),
                            passport_photo(body.profile.photo_base64), contact_verified=False)


@router.post('/password')
def password_login(body: ContactPassword, request: Request, response: Response, db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    limit_auth(request, body.contact)
    account = lookup(db, body.contact)
    valid = verify_password(body.password.get_secret_value(), account.password_hash if account and account.password_hash else _DUMMY_HASH)
    if not valid or not account or not account.password_hash or not account.is_active:
        raise HTTPException(401, 'Invalid contact or password')
    result = issue_session(db, account)
    db.commit()
    return result


@router.get('/options')
def auth_options():
    if public_demo_enabled():
        return {'demo': demo_login_enabled(), 'otp': False, 'signup': False,
                'channels': {'email': False, 'sms': False}, 'default_channel': 'phone'}
    channels = available_channels()
    otp = any(channels.values())
    try:
        identity_cipher()
        signup = True
    except HTTPException:
        signup = False
    return {'demo': demo_login_enabled(), 'otp': otp, 'signup': signup, 'channels': channels,
            'default_channel': 'email' if email_provider() == 'smtp' else 'phone'}


@router.post('/otp/start')
def start(body: Start, request: Request, response: Response, db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    # An unavailable service must never return a pretend successful send,
    # including the account-enumeration protection path below.
    channel = 'email' if '@' in body.contact else 'sms'
    if not available_channels()[channel]:
        raise HTTPException(503, 'This verification method is not available on this server')
    if body.purpose == 'signup':
        identity_cipher()
    send_limit.check(request.client.host if request.client else 'unknown', body.contact)
    account = lookup(db, body.contact)
    # Use the same response shape for missing or unavailable accounts without sending a paid code.
    if (body.purpose == 'login' and (not otp_account(db, account))
            or body.purpose == 'signup' and account):
        prefix = 'EM' if channel == 'email' and email_provider() == 'smtp' else 'VE'
        return {'verification_id': prefix + secrets.token_hex(16)}
    if channel == 'email' and email_provider() == 'smtp':
        return {'verification_id': start_email(db, body.contact, body.purpose)}
    started = verify_request('Verifications', {'To': body.contact, 'Channel': channel})
    if started.get('status') != 'pending' or not re.fullmatch(r'VE[a-fA-F0-9]{32}', started.get('sid', '')):
        raise HTTPException(503, 'The verification provider could not send a code')
    return {'verification_id': started['sid']}


@router.post('/otp/verify')
def verify(body: Verify, request: Request, response: Response, db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    if (body.purpose == 'signup') != (body.profile is not None):
        raise HTTPException(422, 'Provide registration details only when creating an account')
    check_limit.check(request.client.host if request.client else 'unknown', body.contact)
    account = lookup(db, body.contact)
    invalid = HTTPException(401, 'The code or account could not be verified')
    if body.purpose == 'login' and (not otp_account(db, account)):
        raise invalid
    if body.purpose == 'signup' and account:
        raise invalid
    profile = body.profile
    if profile is not None:
        cipher = identity_cipher()
        photo = passport_photo(profile.photo_base64)
    channel = 'email' if '@' in body.contact else 'sms'
    if not available_channels()[channel]:
        raise HTTPException(503, 'This verification method is not available on this server')
    if channel == 'email' and email_provider() == 'smtp':
        if not body.verification_id.startswith('EM'):
            raise invalid
        consume_email(db, body.verification_id, body.contact, body.purpose, body.code)
    else:
        if not body.verification_id.startswith('VE'):
            raise invalid
        result = verify_request('VerificationCheck', {'VerificationSid': body.verification_id, 'Code': body.code})
        if result.get('status') != 'approved' or result.get('to') != body.contact:
            raise invalid
    if profile is not None:
        return register_profile(db, body.contact, profile, cipher, photo, contact_verified=True)
    assert account is not None
    session = issue_session(db, account)
    db.commit()
    return session
