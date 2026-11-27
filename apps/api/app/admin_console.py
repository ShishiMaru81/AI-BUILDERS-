"""Restricted operator sign-in and aggregate platform monitoring."""

import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import Record, User, get_db
from .doctor_models import DoctorRegistry
from .identity import require_user
from .market_auth import _DUMMY_HASH, issue_session, limit_auth, normalize_email, verify_password
from .market_models import Auction, Order, Product, Report
from .market_service import policy

router = APIRouter(prefix='/api/v1', tags=['administration'])
Database = Annotated[Session, Depends(get_db)]

RECORDS = (
    'farm', 'plot', 'case', 'weather', 'price', 'comparison', 'rescue_plan', 'action',
    'farmer_chat', 'farm_ledger', 'storage_batch', 'farm_reminder', 'community_report', 'device',
)


class AdminCredentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator('email')
    @classmethod
    def email_valid(cls, value: str) -> str:
        return normalize_email(value)


def require_admin(user: Annotated[User, Depends(require_user)]) -> User:
    if user.role != 'admin':
        raise HTTPException(403, 'Administrator access required')
    return user


Admin = Annotated[User, Depends(require_admin)]


@router.post('/auth/admin/login')
def admin_login(body: AdminCredentials, request: Request, db: Database):
    limit_auth(request, body.email)
    user = db.scalar(select(User).where(User.email == body.email))
    eligible = bool(user and user.role == 'admin' and user.is_active and user.password_hash)
    valid = verify_password(body.password.get_secret_value(), user.password_hash if eligible else _DUMMY_HASH)
    if not valid or not eligible:
        raise HTTPException(401, 'Invalid administrator email or password',
                            headers={'WWW-Authenticate': 'Bearer'})
    session = issue_session(db, user)
    db.commit()
    return session


@router.get('/admin/overview')
def overview(operator: Admin, db: Database):
    records = dict.fromkeys(RECORDS, 0)
    records.update(dict(db.execute(select(Record.kind, func.count()).where(
        Record.kind.in_(RECORDS)).group_by(Record.kind)).all()))
    accounts = dict.fromkeys(('farmer', 'customer', 'admin', 'other'), 0)
    total = active = demo = 0
    for role, is_active, is_demo, count in db.execute(select(
        User.role, User.is_active, User.is_demo, func.count()).group_by(
        User.role, User.is_active, User.is_demo)):
        accounts[role if role in accounts else 'other'] += count
        total += count
        active += count if is_active else 0
        demo += count if is_demo is True else 0
    marketplace = {
        'listings': db.scalar(select(func.count()).select_from(Product)),
        'orders': db.scalar(select(func.count()).select_from(Order)),
        'auctions': db.scalar(select(func.count()).select_from(Auction)),
        'open_reports': db.scalar(select(func.count()).select_from(Report).where(Report.status == 'open')),
        'enabled': policy(db)['marketplace_enabled'],
    }
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'accounts': {**accounts, 'total': total, 'active': active, 'demo': demo},
        'records': records,
        'marketplace': marketplace,
    }


@router.get('/admin/system')
def system_status(operator: Admin):
    capabilities = DoctorRegistry().capabilities()
    return {
        'data_mode': os.getenv('DATA_MODE', 'DEMO'),
        'chat_configured': bool(os.getenv('GROQ_API_KEY', '').strip()),
        'models': [{key: model[key] for key in ('model_id', 'version', 'available', 'artifact_status')}
                   for model in capabilities['models']],
    }
