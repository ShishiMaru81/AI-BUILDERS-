"""ZYNTRIX AgroSphere AI HTTP API — audit remediation contracts (Phases 1–5)."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import secrets
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Annotated, Any, Literal
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response
from PIL import Image
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from . import image_storage_root, public_demo_enabled
from .identity import require_user, user_view
from .market_privacy import owner_export as market_owner_export, erase_account as erase_market_account
from .market_auth import router as auth_router, AuthLimiter
from .otp_auth import router as otp_router, demo_login_enabled, open_identity
from .rescue import router as rescue_router
from .farm_tools import RECORD_KINDS as FARM_TOOL_RECORDS, router as farm_tools_router
from . import market_models, market_service
from .db import Base, Reading, Record, SignupIdentity, Token, User, engine, ensure_compat_schema, get_db, now
from . import doctor_vision, farmer_chat
from . import district_prices
from .district_prices_catalog import COMMODITY_OPTIONS
from .doctor_context import FarmerContext
from .doctor_photos import case_photo_paths, decode_photo, read_upload
from .doctor_models import CROPS, DoctorRegistry, VisionUnavailable, normalize_crop
from .schemas import (
    ActionUpdate,
    ComparisonInput,
    ComparisonScenarioInput,
    DemoLogin,
    DeviceInput,
    FarmCreate,
    FarmLocationInput,
    FarmPatch,
    FeedbackInput,
    PlotCreate,
    PlotPatch,
    PreferencesModel,
    PreferencesPatch,
    SensorInput,
    ValidatedFarm,
    VulnerabilityInput,
    WatchInput,
    WatchPatch,
)
from .services import (
    DemoWeatherProvider,
    Esp32HttpAdapter,
    HistoricalSensorAdapter,
    LocationSearchProvider,
    ModelBrokenError,
    ModelBusyError,
    ModelRegistry,
    OpenMeteoProvider,
    FFWC_URL,
    SimulatorAdapter,
    acquire_upload_slot,
    calculate,
    compute_effective_price_meta,
    compute_effective_weather,
    iso_now,
    parse_and_validate_market_csv,
    parse_iso_utc,
    preparedness,
    provenance,
)

storage = image_storage_root()
storage.mkdir(parents=True, exist_ok=True)
Image.MAX_IMAGE_PIXELS = 20_000_000
APP_VERSION = '1.0.0'


@asynccontextmanager
async def lifespan(app: FastAPI):
    if public_demo_enabled():
        # Concurrent cold starts share the schema but use separate application processes.
        with engine.begin() as connection:
            connection.execute(text('SELECT pg_advisory_xact_lock(659853250)'))
            ensure_compat_schema(engine)
    else:
        ensure_compat_schema(engine)
    app.state.instance_id = uuid4().hex
    app.state.market_auth_limiter = AuthLimiter()
    app.state.farmer_chat_limiter = AuthLimiter(ip_limit=60, identity_limit=14, by_destination=True)
    app.state.demo_login_limiter = AuthLimiter(window=3600, ip_limit=30, identity_limit=30)
    yield


app = FastAPI(title='ZYNTRIX AgroSphere AI', version=APP_VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(','),
    allow_methods=['GET', 'POST', 'PATCH', 'DELETE'],
    allow_headers=['Authorization', 'Content-Type', 'X-Device-Key', 'Idempotency-Key'],
    expose_headers=['Retry-After'],
)


@app.middleware('http')
async def request_headers(request: Request, call_next):
    request.state.request_id = uuid4().hex
    path = request.url.path.rstrip('/')
    if (public_demo_enabled() and request.method == 'POST' and path.startswith('/api/v1/auth/')
            and path not in {'/api/v1/auth/demo', '/api/v1/auth/logout'}):
        response = JSONResponse({'message': 'Only demo sign-in is available on this deployment.'}, status_code=403)
    else:
        response = await call_next(request)
    response.headers.update({
        'X-Request-ID': request.state.request_id,
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'no-store',
    })
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            'code': 'VISION_UNAVAILABLE' if isinstance(exc, VisionUnavailable) else f'HTTP_{exc.status_code}',
            'message': str(exc.detail),
            'request_id': getattr(request.state, 'request_id', None),
        },
        headers=exc.headers,
    )


@app.exception_handler(ModelBrokenError)
async def model_broken(request: Request, exc: ModelBrokenError):
    return JSONResponse(
        status_code=503,
        content={
            'code': 'MODEL_UNAVAILABLE',
            'message': str(exc),
            'request_id': getattr(request.state, 'request_id', None),
        },
    )


@app.exception_handler(ModelBusyError)
async def model_busy(request: Request, exc: ModelBusyError):
    return JSONResponse(
        status_code=429,
        headers={'Retry-After': '5'},
        content={
            'code': 'MODEL_BUSY',
            'message': str(exc),
            'request_id': getattr(request.state, 'request_id', None),
        },
    )


Db = Annotated[DBSession, Depends(get_db)]


def current_user(db: Db, authorization: Annotated[str | None, Header()] = None) -> User:
    return require_user(db, authorization)


Who = Annotated[User, Depends(current_user)]


def farmer_user(user: Who) -> User:
    if user.role != 'farmer':
        raise HTTPException(403, 'AgroDoctor screening is available to farmer accounts')
    return user


Farmer = Annotated[User, Depends(farmer_user)]


def records(db: DBSession, user: User, kind: str, plot: str | None = None) -> list[Record]:
    q = select(Record).where(Record.owner_id == user.id, Record.kind == kind)
    if plot:
        q = q.where(Record.plot_id == plot)
    return list(db.scalars(q.order_by(Record.created_at.desc())))


def owned(db: DBSession, user: User, id: str, kind: str | None = None) -> Record:
    r = db.get(Record, id)
    if not r or r.owner_id != user.id or (kind and r.kind != kind):
        raise HTTPException(404, 'Record not found')
    return r


def view(r: Record, *, include_kind: bool = False, strip_secrets: bool = False) -> dict[str, Any]:
    reserved = {
        'id', 'created_at', 'updated_at', 'plot_id', 'farm_id', 'source_record_id', 'kind', 'owner_id',
        'follow_up_image_file', 'follow_up_checksum',
    }
    payload = {k: v for k, v in (r.payload or {}).items() if k not in reserved}
    data = dict(
        id=r.id,
        created_at=r.created_at,
        updated_at=r.updated_at,
        plot_id=r.plot_id,
        farm_id=r.farm_id or payload.get('farm_id'),
        source_record_id=r.source_record_id,
        **payload,
    )
    # Prefer relational farm_id column; fall back to payload farm_id for legacy plot records
    if r.farm_id:
        data['farm_id'] = r.farm_id
    elif 'farm_id' in (r.payload or {}):
        data['farm_id'] = r.payload['farm_id']
    if include_kind:
        data['kind'] = r.kind
    if strip_secrets:
        data.pop('key_hash', None)
        data.pop('image_file', None)
    return data


def add(
    db: DBSession,
    user: User,
    kind: str,
    payload: dict[str, Any],
    plot: str | None = None,
    farm_id: str | None = None,
    source_record_id: str | None = None,
) -> Record:
    stamp = now()
    r = Record(
        owner_id=user.id,
        kind=kind,
        payload=payload,
        plot_id=plot,
        farm_id=farm_id,
        source_record_id=source_record_id,
        created_at=stamp,
        updated_at=stamp,
    )
    db.add(r)
    db.flush()
    return r


def touch(r: Record) -> None:
    r.updated_at = now()


def audit(db: DBSession, user: User, event: str, record_id: str, plot: str | None = None) -> None:
    add(db, user, 'audit', dict(event=event, record_id=record_id), plot=plot)


def evidence_fingerprint(topic: str, payload: dict[str, Any] | None) -> str:
    base = {'topic': topic, 'payload': payload or {}}
    return hashlib.sha256(json.dumps(base, sort_keys=True, default=str).encode()).hexdigest()


def _snooze_expired(payload: dict[str, Any]) -> bool:
    until = payload.get('snoozed_until')
    if not until:
        return True
    parsed = parse_iso_utc(until)
    if not parsed:
        return True
    return parsed <= datetime.now(timezone.utc)


def upsert_action(
    db: DBSession,
    user: User,
    plot: str,
    topic: str,
    title: str,
    reason: str,
    meta: dict[str, Any],
    *,
    source_record_id: str | None = None,
    fingerprint: str | None = None,
) -> Record:
    """Idempotent action upsert that preserves done/snoozed for identical evidence (B09)."""
    fp = fingerprint or evidence_fingerprint(topic, meta)
    matches = [
        r for r in records(db, user, 'action', plot)
        if r.payload.get('topic') == topic and r.payload.get('evidence_fingerprint') == fp
    ]
    if matches:
        a = matches[0]
        status = a.payload.get('status', 'open')
        if status == 'done':
            a.payload = {**a.payload, 'title': title, 'reason': reason, 'meta': meta}
            touch(a)
            return a
        if status == 'snoozed' and not _snooze_expired(a.payload):
            a.payload = {**a.payload, 'title': title, 'reason': reason, 'meta': meta}
            touch(a)
            return a
        # Identical evidence but open, or snooze expired → refresh without duplicate notification
        a.payload = {
            **a.payload,
            'title': title,
            'reason': reason,
            'status': 'open',
            'meta': meta,
            'evidence_fingerprint': fp,
            'snoozed_until': None,
        }
        a.source_record_id = source_record_id or a.source_record_id
        touch(a)
        return a

    # Different fingerprint: retire prior open action of same topic, then create
    for existing in records(db, user, 'action', plot):
        if existing.payload.get('topic') == topic and existing.payload.get('status') == 'open':
            if existing.payload.get('evidence_fingerprint') != fp:
                existing.payload = {**existing.payload, 'status': 'done', 'reason': existing.payload.get('reason', '') + ' (superseded)'}
                touch(existing)

    a = add(
        db,
        user,
        'action',
        dict(
            topic=topic,
            title=title,
            reason=reason,
            status='open',
            comment='',
            snoozed_until=None,
            evidence_fingerprint=fp,
            meta=meta,
        ),
        plot=plot,
        source_record_id=source_record_id,
    )
    add(
        db,
        user,
        'notification',
        dict(
            title=title,
            read=False,
            action_id=a.id,
            topic=topic,
            source_record_id=source_record_id,
            target_route={'doctor': 'doctor', 'flood': 'flood', 'market': 'market'}.get(topic),
        ),
        plot=plot,
        source_record_id=source_record_id,
    )
    return a


def _location_signature(payload: dict[str, Any]) -> tuple:
    return (
        payload.get('latitude'),
        payload.get('longitude'),
        bool(payload.get('location_consent')),
        payload.get('location_name'),
    )


def _invalidate_plot_outlook(db, user, plot, reason, source):
    for old in records(db, user, 'weather', plot.id):
        db.delete(old)
    upsert_action(
        db, user, plot.id, 'flood', 'Refresh weather for your selected area', reason,
        provenance('MIXED', source),
        fingerprint=evidence_fingerprint('flood', {'event': source, 'at': iso_now()}),
    )


def apply_farm_location_change(
    db: DBSession,
    user: User,
    farm: Record,
    new_fields: dict[str, Any],
    *,
    reason: str = 'Farm location changed. Retrieve a new outlook before making rain preparations.',
) -> bool:
    """Central location mutation + weather invalidation (B01). Returns True if location changed."""
    before = _location_signature(farm.payload)
    merged = {**farm.payload, **new_fields}
    after = _location_signature(merged)
    farm.payload = merged
    touch(farm)
    if before == after:
        return False
    for p in records(db, user, 'plot'):
        if p.payload.get('farm_id') != farm.id:
            continue
        _invalidate_plot_outlook(db, user, p, reason, 'farmer_selected_location')
    return True


def merge_preferences(current: dict[str, Any] | None, patch: PreferencesPatch) -> dict[str, Any]:
    base = PreferencesModel.model_validate(current or {}).model_dump()
    updates = patch.model_dump(exclude_unset=True)
    base.update(updates)
    return PreferencesModel.model_validate(base).model_dump()


def merge_farm(current: dict[str, Any], patch: FarmPatch) -> dict[str, Any]:
    data = {
        'name': current.get('name'),
        'district': current.get('district'),
        'latitude': current.get('latitude'),
        'longitude': current.get('longitude'),
        'location_consent': bool(current.get('location_consent')),
        'location_name': current.get('location_name'),
        'country': current.get('country'),
    }
    data.update(patch.model_dump(exclude_unset=True))
    return ValidatedFarm.model_validate(data).model_dump()


def _prefs(user: User) -> dict[str, Any]:
    return PreferencesModel.model_validate(user.preferences or {}).model_dump()


def _plots_for_farm(db: DBSession, user: User, farm_id: str) -> list[Record]:
    return [p for p in records(db, user, 'plot') if p.payload.get('farm_id') == farm_id]


def _delete_case_artifacts(db: DBSession, user: User, case: Record) -> list[Path]:
    db.execute(delete(Record).where(Record.owner_id == user.id, Record.kind == 'community_report',
                                   Record.source_record_id == case.id))
    files = case_photo_paths(storage, case.payload)
    db.execute(delete(Record).where(Record.owner_id == user.id, Record.kind == 'farmer_chat',
                                    Record.source_record_id == case.id))
    for fb in list(records(db, user, 'feedback', case.plot_id)):
        if fb.source_record_id == case.id or fb.payload.get('case_id') == case.id:
            db.delete(fb)
    for action_rec in list(records(db, user, 'action', case.plot_id)):
        if action_rec.source_record_id == case.id or (
            action_rec.payload.get('topic') == 'doctor'
            and action_rec.payload.get('evidence_fingerprint') == evidence_fingerprint('doctor', {'case_id': case.id})
        ):
            action_rec.payload = {
                **action_rec.payload,
                'status': 'done',
                'reason': 'Observation deleted; screening evidence retired.',
            }
            touch(action_rec)
    for note in list(records(db, user, 'notification', case.plot_id)):
        if note.source_record_id == case.id or note.payload.get('source_record_id') == case.id:
            db.delete(note)
    db.delete(case)
    return files


def _cascade_plot(db: DBSession, user: User, plot: Record) -> list[Path]:
    plot_id = plot.id
    files = []
    for case in list(records(db, user, 'case', plot_id)):
        files.extend(_delete_case_artifacts(db, user, case))
    for kind in ('weather', 'action', 'notification', 'feedback', 'comparison_scenario', 'comparison',
                 'rescue_plan', 'farmer_chat', *FARM_TOOL_RECORDS):
        for r in list(records(db, user, kind, plot_id)):
            db.delete(r)
    for device in list(records(db, user, 'device', plot_id)):
        db.execute(delete(Reading).where(Reading.device_id == device.id))
        db.delete(device)
    db.delete(plot)
    return files


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        description='ZYNTRIX AgroSphere AI private farmer workspace API',
    )
    components = schema.setdefault('components', {})
    schemes = components.setdefault('securitySchemes', {})
    schemes['BearerAuth'] = {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'opaque'}
    schemes['DeviceKeyAuth'] = {
        'type': 'apiKey',
        'in': 'header',
        'name': 'X-Device-Key',
        'description': 'Device provisioning key returned once at register/rotate',
    }
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


# ── Auth & health ────────────────────────────────────────────────────────────

@app.post('/api/v1/auth/demo')
def login(body: DemoLogin, db: Db, request: Request):
    if not demo_login_enabled():
        raise HTTPException(404, 'Demo sign-in is disabled')
    if public_demo_enabled():
        request.app.state.demo_login_limiter.check(request.client.host if request.client else 'unknown', 'demo')
    user = User(
        name=body.name,
        is_demo=True,
        preferences={'language': 'en', 'theme': 'light', 'retraining_consent': False, 'selected_plot_id': None},
    )
    db.add(user)
    db.flush()
    raw = secrets.token_urlsafe(40)
    db.add(Token(
        id=hashlib.sha256(raw.encode()).hexdigest(),
        user_id=user.id,
        expires=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    ))
    farm = add(db, user, 'farm', dict(
        name='Gazipur Demo Farm',
        district='Gazipur',
        latitude=None,
        longitude=None,
        location_consent=False,
        meta=provenance(),
    ))
    plot = add(
        db,
        user,
        'plot',
        dict(farm_id=farm.id, name='Tomato plot · A', crop='tomato', area_acres='1.2', stage='Vegetative', low_lying=False, meta=provenance()),
        farm_id=farm.id,
    )
    for market, price in [('Gazipur demo wholesale', '42.00'), ('Dhaka demo wholesale', '46.00')]:
        add(db, user, 'price', dict(
            market=market,
            commodity='tomato',
            price=price,
            unit='BDT/kg',
            price_type='wholesale',
            grade='unspecified',
            observed_at='2026-11-15',
            meta=provenance(observed_at='2026-11-15'),
        ))
    upsert_action(db, user, plot.id, 'doctor', 'Start your first crop screening', 'Upload a clear tomato leaf photo. Review model evidence and uncertainty.', provenance())
    upsert_action(db, user, plot.id, 'flood', 'Review rain preparedness', 'Explore the clearly labeled simulated rain outlook.', provenance())
    upsert_action(db, user, plot.id, 'market', 'Compare selling options', 'Enter all costs before comparing synthetic market quotes.', provenance())
    user.preferences = {**_prefs(user), 'selected_plot_id': plot.id}
    audit(db, user, 'demo.created', farm.id)
    db.commit()
    return dict(token=raw, user_id=user.id, plot_id=plot.id)


@app.post('/api/v1/auth/logout')
def logout(user: Who, db: Db, authorization: Annotated[str, Header()]):
    db.execute(delete(Token).where(Token.id == hashlib.sha256(authorization[7:].encode()).hexdigest()))
    db.commit()
    return {'ok': True}


def _health_payload(request: Request | None = None) -> dict[str, Any]:
    instance = getattr(getattr(request, 'app', None), 'state', None)
    instance_id = getattr(instance, 'instance_id', None) if instance else None
    if instance_id is None and hasattr(app.state, 'instance_id'):
        instance_id = app.state.instance_id
    return {
        'status': 'ok',
        'version': APP_VERSION,
        'mode': os.getenv('DATA_MODE', 'DEMO'),
        'instance_id': instance_id or 'starting',
    }


@app.get('/api/v1/health')
@app.get('/api/v1/health/live')
def health(request: Request):
    return _health_payload(request)


@app.get('/api/v1/health/ready')
def ready(request: Request, db: Db):
    payload = _health_payload(request)
    db_state = 'ok'
    storage_state = 'ok'
    detail = None
    try:
        db.execute(text('SELECT 1'))
    except Exception as exc:  # noqa: BLE001 — readiness must never 500
        db_state = 'error'
        detail = 'Database connection failed.' if public_demo_enabled() else f'database: {exc}'
    try:
        probe = storage / f'.ready-{uuid4().hex}'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink(missing_ok=True)
    except OSError as exc:
        storage_state = 'error'
        detail = (detail + '; ' if detail else '') + f'storage: {exc}'
    doctor_models = DoctorRegistry().capabilities()['models']
    unavailable = [m for m in doctor_models if not m['available']]
    model_state = ('broken_artifact' if any(m['artifact_status']=='broken_artifact' for m in unavailable)
        else 'absent' if unavailable else 'ready')
    status = 'ready'
    if db_state != 'ok' or storage_state != 'ok' or unavailable:
        status = 'not_ready'
        if unavailable and not detail:
            detail = '; '.join(m['model_id']+': '+(m.get('artifact_error') or m['artifact_status']) for m in unavailable)
    result = {
        **payload,
        'status': status,
        'database': db_state,
        'storage': storage_state,
        'model_state': model_state,
        'model_version': ', '.join(m['version'] for m in doctor_models),
        'doctor_models': doctor_models,
        'detail': detail,
    }
    return JSONResponse(result, status_code=200 if status=='ready' else 503)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    if request.url.path in {'/api/v1/auth/otp/start', '/api/v1/auth/otp/verify', '/api/v1/auth/password', '/api/v1/auth/signup'}:
        first = error.errors()[0]
        field = first['loc'][-1]
        return JSONResponse(status_code=422, content={'message': f"{field}: {first['msg']}"},
                            headers={'Cache-Control': 'no-store'})
    return await request_validation_exception_handler(request, error)


@app.get('/api/v1/me')
def me(user: Who, db: Db):
    identity = db.get(SignupIdentity, user.id)
    return {**user_view(user), 'phone':user.phone, 'age':user.age,
            'gender':identity.gender if identity else None, 'preferences':_prefs(user)}


@app.get('/api/v1/me/signup-photo')
def signup_photo(user: Who, db: Db):
    identity = db.get(SignupIdentity, user.id)
    if not identity:
        raise HTTPException(404, 'No signup photo is available')
    return Response(open_identity(identity.encrypted_photo), media_type='image/jpeg',
                    headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})



@app.patch('/api/v1/me')
def preferences(body: PreferencesPatch, user: Who, db: Db):
    merged = merge_preferences(user.preferences, body)
    if merged.get('selected_plot_id'):
        owned(db, user, merged['selected_plot_id'], 'plot')
    user.preferences = merged
    db.commit()
    return merged


# ── Farms & plots ────────────────────────────────────────────────────────────

@app.get('/api/v1/farms')
def farms(user: Who, db: Db):
    return [view(r) for r in records(db, user, 'farm')]


@app.post('/api/v1/farms')
def create_farm(body: FarmCreate, user: Who, db: Db):
    r = add(db, user, 'farm', dict(**body.model_dump(), meta=provenance('MIXED', 'farmer_entered')))
    audit(db, user, 'farm.created', r.id)
    db.commit()
    return view(r)


@app.patch('/api/v1/farms/{id}')
def edit_farm(id: str, body: FarmPatch, user: Who, db: Db):
    farm = owned(db, user, id, 'farm')
    try:
        merged_fields = merge_farm(farm.payload, body)
    except Exception as exc:  # pydantic ValidationError
        raise HTTPException(422, str(exc)) from exc
    location_keys = {'latitude', 'longitude', 'location_consent', 'location_name', 'district', 'country'}
    supplied = body.model_dump(exclude_unset=True)
    location_touched = bool(location_keys & set(supplied.keys()))
    if location_touched:
        apply_farm_location_change(
            db,
            user,
            farm,
            {**merged_fields, 'meta': provenance('MIXED', 'farmer_entered')},
        )
    else:
        farm.payload = {**farm.payload, **merged_fields, 'meta': provenance('MIXED', 'farmer_entered')}
        touch(farm)
    audit(db, user, 'farm.updated', id)
    db.commit()
    return view(farm)


@app.get('/api/v1/farms/{id}')
def farm(id: str, user: Who, db: Db):
    return view(owned(db, user, id, 'farm'))


@app.delete('/api/v1/farms/{id}')
def delete_farm(id: str, user: Who, db: Db):
    with market_service.transaction() as tx:
        actor = market_service.actor(tx, user)
        farm = owned(tx, actor, id, 'farm')
        if tx.scalar(select(market_models.Product.id).where(market_models.Product.farm_id==id,market_models.Product.status!='archived').limit(1)):
            raise HTTPException(409,"Archive this farm's marketplace listings before deleting it.")
        if tx.scalar(select(market_models.SellerOrder.id).where(market_models.SellerOrder.farm_id==id,market_models.SellerOrder.status.not_in(['delivered','cancelled'])).limit(1)):
            raise HTTPException(409,"Resolve this farm's open marketplace orders before deleting it.")
        for product in tx.scalars(select(market_models.Product).where(market_models.Product.farm_id==id)): product.farm_id=None
        for order in tx.scalars(select(market_models.SellerOrder).where(market_models.SellerOrder.farm_id==id)): order.farm_id=None
        plots = _plots_for_farm(tx, actor, id)
        files = []
        for plot in plots:
            files.extend(_cascade_plot(tx, actor, plot))
        tx.delete(farm)
        if _prefs(actor).get('selected_plot_id') in {plot.id for plot in plots}: actor.preferences={**_prefs(actor),'selected_plot_id':None}
        audit(tx, actor, 'farm.deleted', id)
    for path in files:
        path.unlink(missing_ok=True)
    return {'ok':True,'deleted_id':id,'deleted_plots':len(plots)}


@app.get('/api/v1/locations/search')
def location_search(
    user: Who,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    language: Literal['en', 'bn'] = 'en',
):
    if len(q.strip()) < 2:
        raise HTTPException(422, 'Enter at least two characters for area search')
    try:
        return LocationSearchProvider().search(q.strip(), language)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'Area search is unavailable. Select a map point or enter coordinates instead.')


@app.patch('/api/v1/farms/{id}/location')
def update_location(id: str, body: FarmLocationInput, user: Who, db: Db):
    farm = owned(db, user, id, 'farm')
    apply_farm_location_change(
        db,
        user,
        farm,
        {**body.model_dump(), 'meta': provenance('MIXED', 'farmer_selected_location')},
    )
    audit(db, user, 'farm.location_updated', id)
    db.commit()
    return view(farm)


@app.get('/api/v1/plots')
def plots(user: Who, db: Db):
    return [view(r) for r in records(db, user, 'plot')]


@app.post('/api/v1/plots')
def create_plot(body: PlotCreate, user: Who, db: Db):
    owned(db, user, body.farm_id, 'farm')
    r = add(
        db,
        user,
        'plot',
        dict(**body.model_dump(mode='json'), meta=provenance('MIXED', 'farmer_entered')),
        farm_id=body.farm_id,
    )
    audit(db, user, 'plot.created', r.id)
    db.commit()
    return view(r)


@app.get('/api/v1/plots/{id}')
def plot(id: str, user: Who, db: Db):
    return view(owned(db, user, id, 'plot'))


def _apply_plot_edits(db, user, plot, updates):
    previous = plot.payload
    updated = {**previous, **updates}
    plot.payload = updated
    touch(plot)
    if (updated['farm_id'] != previous['farm_id']
            or updated.get('low_lying', False) != previous.get('low_lying', False)):
        _invalidate_plot_outlook(
            db, user, plot, 'Plot settings changed. Refresh the outlook to update rain preparations.',
            'farmer_updated_plot',
        )


@app.patch('/api/v1/plots/{id}')
def edit_plot(id: str, body: PlotPatch, user: Who, db: Db):
    p = owned(db, user, id, 'plot')
    updates = body.model_dump(exclude_unset=True, mode='json')
    if 'farm_id' in updates:
        owned(db, user, updates['farm_id'], 'farm')
        p.farm_id = updates['farm_id']
    _apply_plot_edits(db, user, p, updates)
    audit(db, user, 'plot.updated', id)
    db.commit()
    return view(p)


@app.delete('/api/v1/plots/{id}')
def delete_plot(id: str, user: Who):
    with market_service.transaction() as tx:
        actor = market_service.actor(tx, user)
        p = owned(tx, actor, id, 'plot')
        files = _cascade_plot(tx, actor, p)
        prefs = _prefs(actor)
        if prefs.get('selected_plot_id') == id:
            remaining = records(tx, actor, 'plot')
            actor.preferences = {**prefs, 'selected_plot_id': remaining[0].id if remaining else None}
        audit(tx, actor, 'plot.deleted', id)
    for path in files:
        path.unlink(missing_ok=True)
    return {'ok': True, 'deleted_id': id}


# ── AgroDoctor ───────────────────────────────────────────────────────────────

@app.get('/api/v1/doctor/models/current')
def model(crop: str = 'tomato'):
    try:
        return DoctorRegistry().card(crop)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/v1/doctor/capabilities')
def doctor_capabilities():
    return DoctorRegistry().capabilities()


@app.get('/api/v1/doctor/conditions')
def conditions(crop: str = 'tomato'):
    try:
        crop = normalize_crop(crop)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if doctor_vision.configured():
        return {'crop': crop, 'supported_model_labels': [],
                'guidance': ['Photograph the affected part in focus and in natural light.'],
                'source': doctor_vision.SOURCE, 'disclaimer': doctor_vision.LIMIT,
                'ood_scope': 'Open-ended visual assessment of leaves and produce.', 'limitations': [doctor_vision.LIMIT]}
    capability = next(c for c in DoctorRegistry().capabilities()['crops'] if c['id'] == crop)
    return {
        'crop': crop,
        'supported_model_labels': capability['labels'],
        'guidance': [
            'Photograph both sides of leaves.',
            'Record when symptoms began.',
            'Seek local agronomic review.',
            'Confirm the selected crop yourself; arbitrary images and unknown diseases can receive high scores.',
        ],
        'source': DoctorRegistry().card(crop)['source_url'],
        'disclaimer': 'Educational guidance. No disease-specific treatment or pesticide prescription.',
        'ood_scope': 'Closed-set research screening; not a validated crop or out-of-distribution detector.',
        'limitations': capability['limitations'],
    }


_preview_uploads: OrderedDict[str, deque[float]] = OrderedDict()
_preview_upload_lock = Lock()


def limit_screening_preview(user_id: str, image_count: int = 1) -> None:
    with _preview_upload_lock:
        current = monotonic()
        uploads = _preview_uploads.setdefault(user_id, deque())
        _preview_uploads.move_to_end(user_id)
        while uploads and uploads[0] <= current - 60:
            uploads.popleft()
        if len(uploads) + image_count > 6:
            raise HTTPException(429, 'Screening limit: six images per minute')
        uploads.extend([current] * image_count)
        if len(_preview_uploads) > 4096:
            _preview_uploads.popitem(last=False)


def _screen_meta(result: dict) -> dict:
    if result['model']['model_id'] == 'groq-vision':
        return provenance('LIVE', 'Groq vision · ' + result['model']['version'], source_url=doctor_vision.SOURCE)
    return provenance('MIXED' if result['model'].get('available') else 'DEMO', 'user_upload; ' + result['model']['version'])


def _confirmed_plot_crop(result: dict) -> bool:
    return result['assessment']['crop_match'] == 'match' and result['assessment']['outcome'] != 'unrelated'


def _screening_action(db: DBSession, user: User, case: Record):
    result = case.payload
    upsert_action(db, user, case.plot_id, 'doctor', 'Review your crop photo screening',
                  result['status'] + ': ' + result['advice'][0], result['meta'], source_record_id=case.id,
                  fingerprint=evidence_fingerprint('doctor', {'case_id': case.id}))


@app.post('/api/v1/doctor/cases')
def upload(
    user: Farmer,
    db: Db,
    image: Annotated[UploadFile, File()],
    plot_id: Annotated[str | None, Form()] = None,
    symptoms: Annotated[str, Form(max_length=2000)] = '',
    crop: Annotated[str | None, Form()] = None,
    plant_part: Annotated[Literal['auto', 'leaf', 'other'], Form()] = 'auto',
    screening_mode: Annotated[Literal['auto', 'local_leaf'], Form()] = 'auto',
    locale: Annotated[Literal['en', 'bn'], Form()] = 'en',
    follow_up_image: Annotated[UploadFile | None, File()] = None,
    farmer_context: Annotated[str | None, Form(max_length=512)] = None,
):
    use_vision = doctor_vision.configured()
    p = owned(db, user, plot_id, 'plot') if plot_id is not None else None
    context = FarmerContext.from_form(farmer_context).model_dump() if farmer_context is not None else None
    if follow_up_image is not None:
        if p is not None:
            raise HTTPException(422, 'Use the saved case follow-up endpoint to attach a second photo.')
        if not use_vision:
            raise HTTPException(503, 'Two-photo screening requires Groq vision.')
    try:
        plot_crop = normalize_crop(p.payload.get('crop', 'tomato')) if p is not None else None
        if use_vision and crop == 'auto' and p is None:
            selected_crop = 'auto'
        else:
            selected_crop = normalize_crop(crop) if crop is not None else plot_crop
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if selected_crop is None:
        raise HTTPException(422, 'Select a crop to screen a photo.')
    local_retry = screening_mode == 'local_leaf'
    if local_retry and (plant_part != 'leaf' or selected_crop not in ('potato', 'tomato') or follow_up_image is not None):
        raise HTTPException(422, 'Local retry requires one potato or tomato leaf photo.')
    if plot_crop is not None and selected_crop != plot_crop:
        raise HTTPException(422, 'Selected crop must match the plot crop. Choose or create a matching plot.')
    recent = [r for r in records(db, user, 'case') if r.created_at > (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()]
    if len(recent) >= 6:
        raise HTTPException(429, 'Upload limit: six images per minute')
    data = read_upload(image)
    second_data = read_upload(follow_up_image) if follow_up_image is not None else None
    if plant_part == 'other' and not use_vision:
        raise HTTPException(503, 'Produce screening requires Groq vision. Configure the server API key.')
    if p is None or use_vision:
        limit_screening_preview(user.id, 2 if second_data is not None else 1)
    # Release the read connection during inference. Saving rechecks ownership in a new transaction.
    db.commit()
    slot = acquire_upload_slot()
    try:
        im = decode_photo(data)
        if local_retry:
            result = {**DoctorRegistry().infer(im, selected_crop), 'fallback_reason': 'vision_unavailable'}
        elif use_vision:
            second = decode_photo(second_data) if second_data is not None else None
            result = DoctorRegistry().screen_with_vision(im, selected_crop, plant_part, locale, second)
        else:
            result = DoctorRegistry().infer(im, selected_crop)
    finally:
        slot.release()
    result.update(meta=_screen_meta(result), screening_locale=locale, photo_count=2 if second_data is not None else 1)
    if context is not None:
        result['farmer_context'] = context
    if 'assessment' in result and p is not None and not _confirmed_plot_crop(result):
        return {**result, 'save_notice': 'plot_crop_unconfirmed'}
    if p is None:
        return result
    filename = uuid4().hex + '.jpg'
    try:
        with market_service.transaction() as tx:
            actor = market_service.actor(tx, user, roles={'farmer'})
            plot = owned(tx, actor, plot_id, 'plot')
            if normalize_crop(plot.payload.get('crop', 'tomato')) != selected_crop:
                raise HTTPException(409, 'The plot crop changed during screening. Choose the matching plot and try again.')
            im.save(storage / filename, 'JPEG', quality=90)
            r = add(tx, actor, 'case', {**result, 'plot_name': plot.payload['name'], 'symptoms': symptoms,
                    'image_file': filename, 'checksum': hashlib.sha256(data).hexdigest()}, plot_id)
            _screening_action(tx, actor, r)
            audit(tx, actor, 'diagnosis.created', r.id, plot_id)
    except Exception:
        (storage / filename).unlink(missing_ok=True)
        raise
    return _case_view(r)


def _case_view(c: Record) -> dict:
    data = view(c)
    data.setdefault('crop', 'tomato')  # Pre-multicrop records retain their original tomato snapshot.
    filename = c.payload.get('image_file')
    data['image_available'] = bool(filename and (storage / Path(filename).name).is_file())
    second = c.payload.get('follow_up_image_file')
    data['second_photo_available'] = bool(second and (storage / Path(second).name).is_file())
    data.setdefault('photo_count', 2 if second else 1)
    return data


def _case_feedback(db: DBSession, user: User, case_id: str, plot_id: str | None) -> list[dict[str, Any]]:
    items = []
    for fb in records(db, user, 'feedback', plot_id):
        if fb.source_record_id == case_id or fb.payload.get('case_id') == case_id:
            items.append(view(fb))
    return items


@app.get('/api/v1/doctor/cases')
def cases(
    user: Farmer,
    db: Db,
    offset: int = 0,
    limit: int = 20,
    plot_id: str | None = None,
    paginated: bool = True,
):
    if plot_id:
        owned(db, user, plot_id, 'plot')
    all_cases = records(db, user, 'case', plot_id)
    total = len(all_cases)
    start = max(0, offset)
    size = max(1, min(limit, 100))
    page = [_case_view(r) for r in all_cases[start:start + size]]
    if not paginated:
        return page
    return {
        'items': page,
        'total': total,
        'offset': start,
        'limit': size,
        'has_more': start + size < total,
    }


@app.get('/api/v1/doctor/cases/{id}')
def case(id: str, user: Farmer, db: Db):
    c = owned(db, user, id, 'case')
    data = _case_view(c)
    data['feedback'] = _case_feedback(db, user, id, c.plot_id)
    return data


@app.get('/api/v1/doctor/cases/{id}/feedback')
def list_feedback(id: str, user: Farmer, db: Db):
    c = owned(db, user, id, 'case')
    return _case_feedback(db, user, id, c.plot_id)


def _case_image_bytes(payload: dict, view: str) -> bytes:
    filename = payload.get('follow_up_image_file' if view == 'follow_up' else 'image_file')
    if filename:
        try:
            return (storage / Path(filename).name).read_bytes()
        except FileNotFoundError:
            pass
    raise HTTPException(410, 'This image is unavailable. The saved assessment can still be viewed and exported.')


@app.get('/api/v1/doctor/cases/{id}/image')
def case_image(id: str, user: Farmer, db: Db, view: Literal['original', 'follow_up'] = 'original'):
    payload = owned(db, user, id, 'case').payload
    return Response(_case_image_bytes(payload, view), media_type='image/jpeg')


def _follow_up_exists(case: Record, checksum: str, locale: str) -> bool:
    if not case.payload.get('follow_up_image_file'):
        return False
    if case.payload.get('follow_up_checksum') == checksum and case.payload.get('screening_locale') == locale:
        return True
    raise HTTPException(409, 'This case already has a second photo and a combined assessment.')


@app.post('/api/v1/doctor/cases/{id}/follow-up')
def follow_up(id: str, user: Farmer, db: Db, image: Annotated[UploadFile, File()],
              locale: Annotated[Literal['en', 'bn'] | None, Form()] = None):
    case = owned(db, user, id, 'case')
    if case.payload.get('model', {}).get('model_id') != 'groq-vision' or not case.payload.get('assessment'):
        raise HTTPException(409, 'A second photo can be attached to a vision screening case.')
    locale = locale or case.payload.get('screening_locale', 'en')
    data = read_upload(image)
    checksum = hashlib.sha256(data).hexdigest()
    if _follow_up_exists(case, checksum, locale):
        return _case_view(case)
    if not doctor_vision.configured():
        raise HTTPException(503, 'Two-photo screening requires Groq vision.')
    limit_screening_preview(user.id)
    db.commit()
    slot = acquire_upload_slot()
    try:
        second = decode_photo(data)
        original = decode_photo(_case_image_bytes(case.payload, 'original'))
        result = DoctorRegistry().screen_with_vision(original, case.payload.get('crop', 'tomato'), 'auto', locale, second)
    finally:
        slot.release()
    if not _confirmed_plot_crop(result):
        raise HTTPException(422, 'The two photos could not confirm the crop in this case. Use another view of the same crop.')
    result.update(photo_count=2, screening_locale=locale, meta=_screen_meta(result))
    filename = uuid4().hex + '.jpg'
    try:
        # Re-read after slow inference. Deletions and other attachments use the same short write transaction.
        with market_service.transaction() as tx:
            actor = market_service.actor(tx, user, roles={'farmer'})
            current = owned(tx, actor, id, 'case')
            if _follow_up_exists(current, checksum, locale):
                return _case_view(current)
            second.save(storage / filename, 'JPEG', quality=90)
            payload = dict(current.payload)
            payload.pop('cross_check_model', None)
            if 'screening_locale' in payload:
                payload['initial_screening_locale'] = payload['screening_locale']
            payload.update(initial_assessment=payload['assessment'],
                           follow_up_recorded_at=iso_now(),
                           follow_up_image_file=filename, follow_up_checksum=checksum, **result)
            current.payload = payload
            touch(current)
            _screening_action(tx, actor, current)
            audit(tx, actor, 'doctor.follow_up_added', id, current.plot_id)
    except Exception:
        (storage / filename).unlink(missing_ok=True)
        raise
    return _case_view(current)


@app.post('/api/v1/doctor/cases/{id}/feedback')
def feedback(id: str, body: FeedbackInput, user: Farmer, db: Db):
    c = owned(db, user, id, 'case')
    r = add(
        db,
        user,
        'feedback',
        dict(case_id=id, **body.model_dump(), advisor_contacted=False, notice='Local note only; no advisor was contacted.'),
        c.plot_id,
        source_record_id=id,
    )
    audit(db, user, 'doctor.review_requested' if body.request_review else 'doctor.feedback', id, c.plot_id)
    db.commit()
    return view(r)


@app.get('/api/v1/doctor/cases/{id}/report')
def report(id: str, user: Farmer, db: Db):
    c = owned(db, user, id, 'case')
    out = io.StringIO()
    writer = csv.writer(out)
    assessment = c.payload.get('assessment', {})
    writer.writerow(['case_id', 'created_at', 'crop', 'plot_id', 'plot_name', 'status', 'possible_condition', 'model', 'source_revision', 'mode', 'limitations', 'visible_signs', 'explanation', 'uncertainty', 'next_steps'])
    writer.writerow([
        c.id,
        c.created_at,
        c.payload.get('crop','tomato'),
        c.plot_id,
        c.payload.get('plot_name',''),
        c.payload['status'],
        c.payload['classification']['top_label'],
        c.payload['model']['version'],
        c.payload['model'].get('revision','legacy'),
        c.payload['meta']['mode'],
        c.payload['disclaimer'],
        ' | '.join(assessment.get('signs', [])), assessment.get('explanation', ''), assessment.get('uncertainty', ''),
        ' | '.join(c.payload.get('advice', [])),
    ])
    audit(db, user, 'case.exported', id, c.plot_id)
    db.commit()
    return Response(out.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="agrodoctor-case.csv"'})


@app.delete('/api/v1/doctor/cases/{id}')
def delete_case(id: str, user: Farmer):
    with market_service.transaction() as tx:
        actor = market_service.actor(tx, user)
        c = owned(tx, actor, id, 'case')
        files = _delete_case_artifacts(tx, actor, c)
        audit(tx, actor, 'case.deleted', id, c.plot_id)
    for path in files:
        path.unlink(missing_ok=True)
    return {'ok': True, 'deleted_id': id}


# ── Weather / FloodCrop ──────────────────────────────────────────────────────

@app.get('/api/v1/flood/plots/{plot_id}/outlook')
@app.get('/api/v1/weather/plots/{plot_id}/forecast')
def outlook(
    plot_id: str,
    user: Who,
    db: Db,
    horizon_hours: int = 48,
    mode: Literal['DEMO', 'LIVE'] = 'DEMO',
):
    p = owned(db, user, plot_id, 'plot')
    f = owned(db, user, p.payload['farm_id'], 'farm')
    if horizon_hours not in (24, 48, 72):
        raise HTTPException(422, 'Horizon must be 24, 48 or 72 hours')
    lat, lon = f.payload.get('latitude'), f.payload.get('longitude')
    if mode == 'LIVE' and (f.payload.get('location_consent') is not True or lat is None or lon is None):
        raise HTTPException(422, 'Add consented farm coordinates for live weather')
    farm_id = f.id
    location = _location_signature(f.payload)
    low_lying = p.payload.get('low_lying', False)
    started_at = iso_now()
    db.commit()  # Release the read connection before the network call.
    provider = OpenMeteoProvider() if mode == 'LIVE' else DemoWeatherProvider()
    try:
        forecast = provider.forecast(lat if lat is not None else 24.0023, lon if lon is not None else 90.4264)
        data = preparedness(forecast, horizon_hours, low_lying)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        data = None

    with market_service.transaction() as tx:
        actor = market_service.actor(tx, user)
        farm = tx.get(Record, farm_id, with_for_update=True)
        plot = tx.get(Record, plot_id, with_for_update=True)
        if not farm or not plot or farm.owner_id != actor.id or plot.owner_id != actor.id:
            raise HTTPException(404, 'Record not found')
        if (plot.payload.get('farm_id') != farm_id or _location_signature(farm.payload) != location
                or plot.payload.get('low_lying', False) != low_lying):
            raise HTTPException(409, 'Plot settings changed during the forecast. Refresh the outlook.')
        existing = records(tx, actor, 'weather', plot_id)
        previous = existing[0] if existing else None
        saved = previous.payload if previous else {}
        # A slow request must not replace a more recent refresh. A simulated
        # preview must not replace a live forecast used for planning.
        saved_mode = (saved.get('meta') or {}).get('mode')
        newer_in_same_mode = saved_mode == mode and (saved.get('refresh_started_at') or '') > started_at
        preserve = newer_in_same_mode or (mode == 'DEMO' and saved_mode == 'LIVE')
        if data is not None:
            data['location'] = {'lat': lat if lat is not None else 24.0023, 'lon': lon if lon is not None else 90.4264}
            if not preserve:
                _save_plot_outlook(tx, actor, plot_id, farm_id, previous, data, started_at)
            return data
        if previous and not preserve:
            flag = 'live_refresh_failed' if mode == 'LIVE' else 'weather_refresh_failed'
            meta = dict(saved.get('meta') or {})
            meta['quality_flags'] = list(dict.fromkeys([*(meta.get('quality_flags') or []), flag]))
            previous.payload = {**saved, 'meta': meta, 'last_refresh_failed_at': iso_now(),
                                'last_refresh_failed_mode': mode, 'refresh_started_at': started_at}
            touch(previous)
    raise HTTPException(503, 'Weather unavailable. Please retry the forecast.')


def _save_plot_outlook(db, user, plot_id, farm_id, previous, data, started_at):
    payload = {**data, 'refresh_started_at': started_at}
    if previous:
        previous.payload = payload
        touch(previous)
        weather_id = previous.id
    else:
        weather_id = add(db, user, 'weather', payload, plot_id, farm_id=farm_id).id
    horizon_hours = data['horizon_hours']
    fp = evidence_fingerprint('flood', {
        'location': data.get('location'),
        'source_mode': data['meta']['mode'],
        'threshold_mm': data['threshold_mm'],
        'valid_until': data.get('horizon_valid_until'),
        'total_mm': data['total_mm'],
        'level': data['level'],
        'horizon_hours': horizon_hours,
    })
    upsert_action(
        db,
        user,
        plot_id,
        'flood',
        'Review rain preparedness',
        f"{data['total_mm']} mm / {horizon_hours} hours. {data['disclaimer']}",
        data['meta'],
        source_record_id=weather_id,
        fingerprint=fp,
    )
    audit(db, user, 'rainwatch.updated', plot_id, plot_id)


@app.get('/api/v1/flood/plots/{plot_id}/official-alerts')
def official(plot_id: str, user: Who, db: Db):
    owned(db, user, plot_id, 'plot')
    return {
        'alerts': [],
        'status': 'unavailable',
        'source_url': FFWC_URL,
        'reason': 'No authorized official bulletin feed configured',
    }


@app.post('/api/v1/flood/plots/{plot_id}/vulnerability')
def vulnerability(plot_id: str, body: VulnerabilityInput, user: Who, db: Db):
    p = owned(db, user, plot_id, 'plot')
    _apply_plot_edits(db, user, p, body.model_dump())
    audit(db, user, 'plot.vulnerability_updated', plot_id, plot_id)
    db.commit()
    return view(p)


# ── Market ───────────────────────────────────────────────────────────────────

def _price_view(r: Record) -> dict[str, Any]:
    data = view(r)
    meta = compute_effective_price_meta(data.get('meta') or {}, data.get('observed_at'))
    data['meta'] = meta
    return data


@app.get('/api/v1/market/prices')
def prices(
    user: Who,
    db: Db,
    commodity: str = 'tomato',
    price_type: str = 'wholesale',
    market: str | None = None,
):
    return [
        _price_view(r)
        for r in records(db, user, 'price')
        if r.payload['commodity'] == commodity
        and r.payload['price_type'] == price_type
        and (not market or r.payload['market'] == market)
    ]


def _compare_one(
    db: DBSession,
    user: User,
    body: ComparisonInput,
    *,
    write_action: bool,
) -> dict[str, Any]:
    price = owned(db, user, body.price_id, 'price')
    p = price.payload
    try:
        result = calculate(p['price'], body.harvested_kg, body.loss_fraction, body.transport_bdt, body.handling_bdt, body.fees_bdt)
    except (InvalidOperation, ValueError, ArithmeticError) as exc:
        raise HTTPException(422, f'Price or cost values cannot be calculated: {exc}') from exc
    assumptions = body.model_dump(mode='json')
    meta = compute_effective_price_meta(p.get('meta') or {}, p.get('observed_at'))
    result.update(
        market=p['market'],
        commodity=p.get('commodity'),
        price_type=p.get('price_type'),
        grade=p.get('grade'),
        unit_price_bdt=p.get('price'),
        observed_at=p.get('observed_at'),
        price_id=price.id,
        plot_id=body.plot_id,
        meta=meta,
        assumptions=assumptions,
        disclaimer='Illustrative expected proceeds, not a guaranteed sale price or profit.',
    )
    comparison = add(db, user, 'comparison', result, plot=body.plot_id, source_record_id=price.id)
    result['id'] = comparison.id
    if write_action and body.plot_id:
        plot_record = owned(db, user, body.plot_id, 'plot')
        if plot_record.payload.get('crop') != p.get('commodity'):
            raise HTTPException(422, 'Comparison plot crop must match the selected price commodity')
        upsert_action(
            db,
            user,
            body.plot_id,
            'market',
            'Review your net selling comparison',
            f"{plot_record.payload['name']}: {result['market']} · illustrative net BDT {result['net_bdt']} after declared costs.",
            meta,
            source_record_id=comparison.id,
            fingerprint=evidence_fingerprint('market', {
                'comparison_id': comparison.id,
                'price_id': price.id,
                'assumptions': assumptions,
            }),
        )
    return result


@app.post('/api/v1/market/compare')
def compare(body: ComparisonInput, user: Who, db: Db):
    # FE-C2: never fan out actions to every same-crop plot. Action only when plot_id provided.
    result = _compare_one(db, user, body, write_action=bool(body.plot_id))
    audit(db, user, 'market.compared', body.price_id, body.plot_id)
    db.commit()
    return result


@app.post('/api/v1/market/comparisons')
def compare_scenario(body: ComparisonScenarioInput, user: Who, db: Db):
    plot = owned(db, user, body.plot_id, 'plot')
    crop = plot.payload.get('crop', 'tomato')
    items = []
    shared = body.route_costs is None
    for price_id in body.price_ids:
        price = owned(db, user, price_id, 'price')
        if price.payload.get('commodity') != crop:
            raise HTTPException(422, f'Price {price_id} commodity does not match plot crop')
        if price.payload.get('price_type') != body.price_type:
            raise HTTPException(422, f'Price {price_id} type does not match scenario price_type')
        override = (body.route_costs or {}).get(price_id)
        transport = override.transport_bdt if override else body.transport_bdt
        handling = override.handling_bdt if override else body.handling_bdt
        fees = override.fees_bdt if override else body.fees_bdt
        item = _compare_one(
            db,
            user,
            ComparisonInput(
                price_id=price_id,
                plot_id=body.plot_id,
                harvested_kg=body.harvested_kg,
                loss_fraction=body.loss_fraction,
                transport_bdt=transport,
                handling_bdt=handling,
                fees_bdt=fees,
            ),
            write_action=False,
        )
        items.append(item)
    best = max(items, key=lambda x: Decimal(x['net_bdt']))
    assumptions = body.model_dump(mode='json')
    scenario_payload = dict(
        plot_id=body.plot_id,
        plot_name=plot.payload.get('name'),
        commodity=crop,
        price_type=body.price_type,
        cost_mode='shared_equal_costs' if shared else 'route_specific_costs',
        cost_limitation=(
            'All markets share the same declared transport/handling/fees vector.'
            if shared
            else 'Route-specific costs were supplied per selected quote.'
        ),
        assumptions=assumptions,
        items=items,
        best_net_bdt=best['net_bdt'],
        best_market=best['market'],
        disclaimer='Illustrative scenario comparison, not a guaranteed sale price or profit.',
        meta=provenance('MIXED', 'farmer_comparison_scenario'),
    )
    scenario = add(db, user, 'comparison_scenario', scenario_payload, plot=body.plot_id)
    upsert_action(
        db,
        user,
        body.plot_id,
        'market',
        'Review your net selling comparison',
        f"{plot.payload['name']}: scenario best {best['market']} · illustrative net BDT {best['net_bdt']}.",
        scenario_payload['meta'],
        source_record_id=scenario.id,
        fingerprint=evidence_fingerprint('market', {
            'scenario_id': scenario.id,
            'price_ids': body.price_ids,
            'assumptions': assumptions,
        }),
    )
    audit(db, user, 'market.scenario_compared', scenario.id, body.plot_id)
    db.commit()
    return view(scenario)


@app.post('/api/v1/market/imports')
def import_prices(
    user: Who,
    db: Db,
    file: Annotated[UploadFile, File()],
    source_name: Annotated[str, Form()],
    source_url: Annotated[str, Form()],
    permission_confirmed: Annotated[bool, Form()],
):
    if not permission_confirmed:
        raise HTTPException(422, 'Confirm permission to use this private import')
    raw = file.file.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise HTTPException(413, 'CSV limit is 1 MB')
    existing = {r.payload.get('import_key') for r in records(db, user, 'price') if r.payload.get('import_key')}
    try:
        valid, errors, duplicates = parse_and_validate_market_csv(
            raw,
            source_name=source_name,
            source_url=source_url,
            existing_keys=existing,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    status = 'rejected' if errors else 'accepted'
    if not errors:
        for item in valid:
            add(db, user, 'price', item)
    payload = dict(
        status=status,
        imported=0 if errors else len(valid),
        errors=errors,
        duplicates=duplicates,
        source_name=source_name,
        source_url=source_url,
        checksum=hashlib.sha256(raw).hexdigest(),
    )
    r = add(db, user, 'import', payload)
    audit(db, user, 'market_price.imported', r.id)
    db.commit()
    return view(r)


@app.get('/api/v1/market/imports/{id}')
def imported(id: str, user: Who, db: Db):
    return view(owned(db, user, id, 'import'))


def _watch_enrich(db: DBSession, user: User, watch: Record) -> dict[str, Any]:
    data = view(watch)
    market = data.get('market')
    commodity = data.get('commodity', 'tomato')
    price_type = data.get('price_type', 'wholesale')
    target = Decimal(str(data.get('target_bdt')))
    latest = None
    for price in records(db, user, 'price'):
        p = price.payload
        if p.get('market') == market and p.get('commodity') == commodity and p.get('price_type') == price_type:
            latest = price
            break
    data.update(
        monitoring_active=False,
        delivery_mode='saved_target_only',
        notice='Saved price target only. Automatic market monitoring and external alerts are not active.',
    )
    if latest:
        observed = Decimal(str(latest.payload['price']))
        data['latest_observed_bdt'] = latest.payload['price']
        data['latest_observed_at'] = latest.payload.get('observed_at')
        data['target_met_in_saved_quotes'] = observed >= target
    else:
        data['latest_observed_bdt'] = None
        data['latest_observed_at'] = None
        data['target_met_in_saved_quotes'] = None
    return data


@app.get('/api/v1/market/watchlists')
def watches(user: Who, db: Db):
    return [_watch_enrich(db, user, r) for r in records(db, user, 'watch')]


@app.post('/api/v1/market/watchlists')
def watch(body: WatchInput, user: Who, db: Db):
    payload = body.model_dump(mode='json')
    for existing in records(db, user, 'watch'):
        same = (
            existing.payload.get('market') == payload['market']
            and existing.payload.get('commodity') == payload.get('commodity', 'tomato')
            and existing.payload.get('price_type') == payload.get('price_type', 'wholesale')
        )
        if same:
            existing.payload = {**existing.payload, **payload}
            touch(existing)
            db.commit()
            return _watch_enrich(db, user, existing)
    r = add(db, user, 'watch', payload)
    db.commit()
    return _watch_enrich(db, user, r)


@app.patch('/api/v1/market/watchlists/{id}')
def patch_watch(id: str, body: WatchPatch, user: Who, db: Db):
    w = owned(db, user, id, 'watch')
    updates = body.model_dump(exclude_unset=True, mode='json')
    w.payload = {**w.payload, **updates}
    touch(w)
    db.commit()
    return _watch_enrich(db, user, w)


@app.delete('/api/v1/market/watchlists/{id}')
def delete_watch(id: str, user: Who, db: Db):
    w = owned(db, user, id, 'watch')
    db.delete(w)
    db.commit()
    return {'ok': True, 'deleted_id': id}


@app.get('/api/v1/market/forecast')
def forecast_disabled():
    return {'enabled': False, 'reason': 'No licensed, backtested price time series available'}


# ── Actions / notifications / center ─────────────────────────────────────────

@app.get('/api/v1/actions')
def actions_list(user: Who, db: Db, plot_id: str | None = None):
    if plot_id:
        owned(db, user, plot_id, 'plot')
    return [view(r) for r in records(db, user, 'action', plot_id)]


@app.patch('/api/v1/actions/{id}')
def update_action(id: str, body: ActionUpdate, user: Who):
    updates = body.model_dump(exclude_unset=True, mode='json')
    if updates.get('status') == 'snoozed':
        if body.snoozed_until is not None:
            updates['snoozed_until'] = body.snoozed_until.astimezone(timezone.utc).isoformat()
        elif body.snooze_hours:
            updates['snoozed_until'] = (datetime.now(timezone.utc) + timedelta(hours=body.snooze_hours)).isoformat()
        else:
            updates['snoozed_until'] = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    if updates.get('status') == 'open':
        updates['snoozed_until'] = None
    with market_service.transaction() as tx:
        actor = market_service.actor(tx, user)
        r = owned(tx, actor, id, 'action')
        r.payload = {**r.payload, **updates}
        touch(r)
        audit(tx, actor, 'action.acknowledged', id, r.plot_id)
    return view(r)


@app.get('/api/v1/plots/{id}/action-center')
def center(id: str, user: Who, db: Db):
    plot = owned(db, user, id, 'plot')
    crop = plot.payload.get('crop', 'tomato')
    case_items = [view(r) for r in records(db, user, 'case', id)[:1]]
    weather_items = []
    for w in records(db, user, 'weather', id)[:1]:
        weather_items.append(compute_effective_weather(view(w)))
    comparison_items = [view(r) for r in records(db, user, 'comparison_scenario', id)[:1]]
    market_evidence = [
        _price_view(r)
        for r in records(db, user, 'price')
        if r.payload.get('commodity') == crop
    ][:5]
    return dict(
        plot_id=id,
        plot_name=plot.payload.get('name'),
        crop=crop,
        case_count=len(records(db, user, 'case', id)),
        actions=[view(r) for r in records(db, user, 'action', id)],
        evidence={'case': case_items, 'weather': weather_items, 'comparison': comparison_items},
        market_evidence=market_evidence,
        meta=provenance('MIXED', 'independent module evidence'),
    )


@app.get('/api/v1/notifications')
def notifications(user: Who, db: Db):
    out = []
    for r in records(db, user, 'notification'):
        item = view(r)
        if r.plot_id:
            try:
                p = owned(db, user, r.plot_id, 'plot')
                item['plot_name'] = p.payload.get('name')
            except HTTPException:
                item['plot_name'] = None
        out.append(item)
    return out


@app.patch('/api/v1/notifications/{id}')
def read_notification(id: str, user: Who, db: Db):
    r = owned(db, user, id, 'notification')
    r.payload = {**r.payload, 'read': True}
    touch(r)
    db.commit()
    return view(r)


@app.get('/api/v1/history')
def history(user: Who, db: Db):
    return [view(r) for r in records(db, user, 'audit')[:100]]


# ── Devices ──────────────────────────────────────────────────────────────────

@app.post('/api/v1/devices')
def register_device(body: DeviceInput, user: Who, db: Db):
    owned(db, user, body.plot_id, 'plot')
    key = secrets.token_urlsafe(32)
    r = add(
        db,
        user,
        'device',
        dict(
            name=body.name,
            key_hash=hashlib.sha256(key.encode()).hexdigest(),
            status='NO_LIVE_DEVICE_DATA',
            revoked=False,
            key_version=1,
            last_heartbeat_at=None,
            last_reading=None,
            last_historical_reading=None,
        ),
        body.plot_id,
    )
    audit(db, user, 'device.registered', r.id, body.plot_id)
    db.commit()
    return {'id': r.id, 'key': key, 'plot_id': r.plot_id, 'key_version': 1, 'rotated_at': None}


@app.get('/api/v1/devices')
def devices(user: Who, db: Db):
    return [view(r, strip_secrets=True) for r in records(db, user, 'device')]


@app.delete('/api/v1/devices/{id}')
def revoke_device(id: str, user: Who, db: Db):
    d = owned(db, user, id, 'device')
    d.payload = {**d.payload, 'revoked': True, 'status': 'REVOKED', 'key_hash': hashlib.sha256(uuid4().hex.encode()).hexdigest()}
    touch(d)
    audit(db, user, 'device.revoked', id, d.plot_id)
    db.commit()
    return {'ok': True, 'deleted_id': id}


@app.post('/api/v1/devices/{id}/rotate')
def rotate_device(id: str, user: Who, db: Db):
    d = owned(db, user, id, 'device')
    if d.payload.get('revoked'):
        raise HTTPException(409, 'Device is revoked; register a new device instead')
    key = secrets.token_urlsafe(32)
    version = int(d.payload.get('key_version') or 1) + 1
    rotated_at = iso_now()
    d.payload = {
        **d.payload,
        'key_hash': hashlib.sha256(key.encode()).hexdigest(),
        'key_version': version,
        'rotated_at': rotated_at,
        'revoked': False,
    }
    touch(d)
    audit(db, user, 'device.rotated', id, d.plot_id)
    db.commit()
    return {'id': d.id, 'key': key, 'plot_id': d.plot_id, 'key_version': version, 'rotated_at': rotated_at}


@app.get('/api/v1/devices/{id}/readings')
def device_readings(id: str, user: Who, db: Db):
    d = owned(db, user, id, 'device')
    rows = list(db.scalars(
        select(Reading).where(Reading.device_id == d.id).order_by(Reading.created_at.desc())
    ))
    out = []
    for row in rows:
        payload = row.payload or {}
        out.append(dict(
            id=row.id,
            device_id=d.id,
            plot_id=d.plot_id,
            event_id=row.event_id,
            event_timestamp=row.event_timestamp,
            source_type=row.source_type,
            created_at=row.created_at,
            measurements=payload.get('measurements') or {},
            units=payload.get('units') or {},
            calibration_id=payload.get('calibration_id'),
            calibration_verified=bool(payload.get('calibration_verified')),
            quality_flags=payload.get('quality_flags') or [],
        ))
    return out


@app.post('/api/v1/device/readings')
def ingest(body: SensorInput, db: Db, x_device_key: Annotated[str, Header()]):
    d = db.get(Record, body.device_id)
    if (
        not d
        or d.kind != 'device'
        or d.payload.get('revoked')
        or not secrets.compare_digest(d.payload.get('key_hash', ''), hashlib.sha256(x_device_key.encode()).hexdigest())
    ):
        raise HTTPException(401, 'Invalid device credentials')
    if d.plot_id != body.plot_id:
        raise HTTPException(403, 'Device is not assigned to this plot')
    if body.timestamp > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HTTPException(422, 'Future sensor timestamp')

    is_heartbeat = body.source_type == 'heartbeat'
    if is_heartbeat:
        if body.measurements.has_any_value():
            raise HTTPException(422, 'Heartbeat events must not include measurement values')
        d.payload = {**d.payload, 'last_heartbeat_at': body.timestamp.astimezone(timezone.utc).isoformat()}
        touch(d)
        # Persist heartbeat as reading for audit without advancing measurement state
        previous = db.scalar(select(Reading).where(Reading.device_id == body.device_id, Reading.event_id == body.event_id))
        if previous:
            return {'id': previous.id, 'duplicate': True, 'quality_flags': [], 'stored_as_historical': False, 'status': d.payload.get('status')}
        payload = body.model_dump(mode='json')
        payload.update(quality_flags=['heartbeat'], calibration_verified=False, units={})
        row = Reading(
            device_id=d.id,
            event_id=body.event_id,
            event_timestamp=body.timestamp.astimezone(timezone.utc).isoformat(),
            source_type='heartbeat',
            created_at=now(),
            payload=payload,
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return {'duplicate': True, 'quality_flags': [], 'stored_as_historical': False, 'status': d.payload.get('status')}
        return {'id': row.id, 'duplicate': False, 'quality_flags': ['heartbeat'], 'stored_as_historical': False, 'status': d.payload.get('status')}

    if not body.measurements.has_any_value():
        raise HTTPException(422, 'Reading events require at least one supported measurement value')

    previous = db.scalar(select(Reading).where(Reading.device_id == body.device_id, Reading.event_id == body.event_id))
    if previous:
        return {'id': previous.id, 'duplicate': True, 'quality_flags': previous.payload.get('quality_flags', []), 'stored_as_historical': previous.source_type == 'historical', 'status': d.payload.get('status')}

    payload = body.model_dump(mode='json')
    # Invented calibration IDs never verify; scaffold keeps calibration_unverified (B12)
    calibration_verified = False
    if body.source_type == 'simulator':
        adapter = SimulatorAdapter()
        status = 'SIMULATED_DATA'
    elif body.source_type == 'historical':
        adapter = HistoricalSensorAdapter()
        status = d.payload.get('status') or 'DEVICE_DATA_UNVALIDATED'
    else:
        adapter = Esp32HttpAdapter()
        status = 'DEVICE_DATA_UNVALIDATED'
    payload = adapter.normalize(payload, calibration_verified=calibration_verified)
    event_ts = body.timestamp.astimezone(timezone.utc).isoformat()
    row = Reading(
        device_id=d.id,
        event_id=body.event_id,
        event_timestamp=event_ts,
        source_type=body.source_type,
        created_at=now(),
        payload=payload,
    )
    db.add(row)

    stored_as_historical = False
    current_last = (d.payload.get('last_reading') or {}).get('timestamp')
    current_dt = parse_iso_utc(current_last) if current_last else None
    event_dt = body.timestamp.astimezone(timezone.utc)
    if body.source_type == 'historical' or (current_dt and event_dt < current_dt):
        stored_as_historical = True
        d.payload = {
            **d.payload,
            'last_historical_reading': payload,
            'last_heartbeat_at': d.payload.get('last_heartbeat_at'),
        }
    else:
        d.payload = {
            **d.payload,
            'status': status,
            'last_reading': payload,
            'last_heartbeat_at': event_ts,
        }
    touch(d)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {'duplicate': True, 'quality_flags': [], 'stored_as_historical': False, 'status': d.payload.get('status')}
    return {
        'id': row.id,
        'duplicate': False,
        'quality_flags': payload.get('quality_flags', []),
        'stored_as_historical': stored_as_historical,
        'status': d.payload.get('status'),
    }


# ── Providers / export / account ─────────────────────────────────────────────

@app.get('/api/v1/providers/status')
def providers():
    return {
        'weather': {'provider': 'Open-Meteo', 'live_requires': 'consented coordinates; network', 'demo': 'scenario_simulated'},
        'flood': {'status': 'official_feed_unavailable', 'url': FFWC_URL},
        'market': {'status': 'private_csv_or_demo', 'url': 'https://market.dam.gov.bd/'},
        'model': DoctorRegistry().card(),
        'doctor_models': DoctorRegistry().capabilities()['models'],
    }


@app.get('/api/v1/models/evaluations')
def evaluations(crop: str = 'tomato'):
    card = model(crop)
    return {'model': card, 'metrics': None, 'field_validation': 'not_performed',
        'legacy_model': ModelRegistry().card(),
        'notice': 'Original tomato evaluations belong only to the original model. New upstream models have no independent AgroSphere accuracy evaluation.'}


@app.get('/api/v1/me/export')
def export(user: Who, db: Db, response: Response):
    response.headers['Cache-Control'] = 'private, no-store'
    identity = db.get(SignupIdentity, user.id)
    signup_details = (json.loads(open_identity(identity.encrypted_details)) | {'gender':identity.gender}) if identity else None
    all_records = list(db.scalars(select(Record).where(Record.owner_id == user.id)))
    exported = []
    counts: dict[str, int] = {}
    for r in all_records:
        payload = dict(r.payload or {})
        payload.pop('key_hash', None)
        # Keep image_file name out of export; binaries are separate authorized downloads
        payload.pop('image_file', None)
        payload.pop('follow_up_image_file', None)
        exported.append(dict(
            id=r.id,
            kind=r.kind,
            plot_id=r.plot_id,
            farm_id=r.farm_id,
            source_record_id=r.source_record_id,
            created_at=r.created_at,
            updated_at=r.updated_at,
            payload=payload,
        ))
        counts[r.kind] = counts.get(r.kind, 0) + 1
    device_ids = [r.id for r in all_records if r.kind == 'device']
    sensor_rows = []
    if device_ids:
        for row in db.scalars(select(Reading).where(Reading.device_id.in_(device_ids))):
            payload = row.payload or {}
            sensor_rows.append(dict(
                id=row.id,
                device_id=row.device_id,
                plot_id=next((r.plot_id for r in all_records if r.id == row.device_id), None),
                event_id=row.event_id,
                event_timestamp=row.event_timestamp,
                source_type=row.source_type,
                created_at=row.created_at,
                measurements=payload.get('measurements') or {},
                units=payload.get('units') or {},
                calibration_id=payload.get('calibration_id'),
                calibration_verified=bool(payload.get('calibration_verified')),
                quality_flags=payload.get('quality_flags') or [],
            ))
    audit(db, user, 'account.exported', user.id)
    db.commit()
    return {
        'schema_version': '2.0',
        'exported_at': iso_now(),
        'timezone': 'UTC',
        'contains_image_binaries': False,
        'image_export_note': 'Private case images are available through authorized per-case download endpoints, not this JSON export.',
        'user': {'id': user.id, 'name': user.name, 'role': user.role, 'email': user.email, 'phone': user.phone, 'age': user.age, 'preferences': _prefs(user)},
        'private_signup_details': signup_details,
        'marketplace': market_owner_export(user),
        'records_by_kind': counts,
        'records': exported,
        'sensor_readings': sensor_rows,
        'relationships': {
            'feedback.source_record_id': 'case.id',
            'action.source_record_id': 'originating case/weather/comparison id',
            'reading.device_id': 'device.id',
        },
    }


@app.delete('/api/v1/me')
def delete_account(user: Who, db: Db):
    return erase_market_account(user, storage)


def _chat_scope(db, user, plot_id, case_id):
    case = owned(db, user, case_id, 'case') if case_id else None
    if case and plot_id and plot_id != case.plot_id:
        raise HTTPException(422, 'This screening belongs to a different plot')
    plot_id = case.plot_id if case else plot_id
    return (owned(db, user, plot_id, 'plot') if plot_id else None), case


def _chat_snapshot(db, user, plot, case):
    result = {}
    if plot:
        result['plot'] = farmer_chat.pick(plot.payload, ('crop','stage','sowing_date','area_acres','low_lying'))
        result['plot']['source'] = (plot.payload.get('meta') or {}).get('source_name','farmer record')
        farm = owned(db, user, plot.farm_id or plot.payload['farm_id'], 'farm')
        result['district'] = farm.payload.get('district') or ''
        coords = [farm.payload.get(k) for k in ('latitude','longitude')]
        if farm.payload.get('location_consent') is True and all(n is not None for n in coords):
            result['coordinates'] = tuple(coords)
        result['tasks'] = [farmer_chat.pick(r.payload, ('title','topic','status'))
                           for r in records(db,user,'action',plot.id) if r.payload.get('status')=='open'][:8]
        saved = records(db,user,'weather',plot.id)
        if saved and result.get('coordinates'):
            weather = compute_effective_weather(saved[0].payload)
            meta = weather.get('meta') or {}
            if meta.get('mode')=='LIVE' and meta.get('source_name')=='Open-Meteo' and not meta.get('is_simulated'):
                result['saved_weather'] = {**farmer_chat.pick(weather, ('total_mm','horizon_hours','valid_from','horizon_valid_until')),
                                           'status':'saved forecast · '+str(meta.get('freshness','unknown'))}
    if case:
        result['case_id'] = case.id
        result['case'] = dict(farmer_chat.case_evidence(case.payload), created_at=case.created_at)
        result['case']['farmer_notes'] = [r['note'][:400] for r in _case_feedback(db,user,case.id,case.plot_id)[:4] if r.get('note')]
    return result


def _chat_quotes(owner_id, crop, trade_type, market, observed_on):
    p = Record.payload
    query = select(Record).where(
        Record.owner_id==owner_id, Record.kind=='price',func.lower(p['commodity'].as_string())==crop.casefold(),
        p['meta']['is_simulated'].as_boolean().is_(False), p['meta']['mode'].as_string()!='DEMO')
    if trade_type:
        query = query.where(p['price_type'].as_string()==trade_type)
    if market:
        query = query.where(func.lower(p['market'].as_string()).contains(market, autoescape=True))
    if observed_on:
        query = query.where(p['observed_at'].as_string().startswith(observed_on))
    with DBSession(engine) as tx:
        quotes = [_price_view(row) for row in tx.scalars(query.order_by(p['observed_at'].as_string().desc(),Record.created_at.desc()).limit(4))]
    return [{**farmer_chat.pick(q,('market','commodity','price','unit','price_type','observed_at')),
             'source':q['meta'].get('source_name'),'freshness':q['meta'].get('freshness')} for q in quotes]


@app.get('/api/v1/market/district-prices/crops')
def district_price_crops():
    return {'items': COMMODITY_OPTIONS}


@app.get('/api/v1/market/district-prices')
def district_price_board(db: Db, crop: Annotated[str, Query(min_length=1,max_length=100)],
                         district: Annotated[str, Query(min_length=1,max_length=80)],
                         unit: Literal['kg','g','piece','bundle','crate']='kg'):
    try:
        return district_prices.board(db,crop,district,unit)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


def _chat_district_board(crop, district, unit):
    with DBSession(engine) as tx:
        return district_prices.board(tx,crop,district,unit)


def _chat_response(thread):
    return {'conversation_id':thread.id, 'messages':thread.payload['messages']}


@app.get('/api/v1/farmer-chat/conversations/{id}')
def farmer_conversation(id: str, user: Farmer, db: Db):
    return _chat_response(owned(db,user,id,'farmer_chat'))


@app.get('/api/v1/farmer-chat/conversations')
def farmer_conversations(user: Farmer, db: Db, plot_id: str | None=None, case_id: str | None=None):
    plot, _ = _chat_scope(db,user,plot_id,case_id)
    query = select(Record.id, Record.updated_at).where(
        Record.owner_id==user.id, Record.kind=='farmer_chat', Record.source_record_id==case_id,
        Record.plot_id==(plot.id if plot else None)).order_by(Record.updated_at.desc()).limit(30)
    return {'items':[{'id':key, 'updated_at':stamp} for key,stamp in db.execute(query)]}


def _chat_repeat(thread, body):
    if thread is None:
        return False
    for entry in thread.payload['messages']:
        if entry['role']=='user' and entry['id']==body.request_id:
            if entry['text'] != body.message:
                raise HTTPException(409, 'This request already has a different message')
            return True
    return False


@app.post('/api/v1/farmer-chat/messages')
def farmer_message(body: farmer_chat.ChatInput, user: Farmer, db: Db, request: Request):
    # The first message can safely be retried before the browser receives its conversation ID.
    thread_id = body.conversation_id or hashlib.sha256(f'farmer-chat:{user.id}:{body.request_id}'.encode()).hexdigest()
    thread = owned(db,user,thread_id,'farmer_chat') if body.conversation_id else db.get(Record,thread_id)
    plot, case = _chat_scope(db,user,body.plot_id,body.case_id)
    plot_id = plot.id if plot else None
    if thread and (thread.owner_id!=user.id or thread.kind!='farmer_chat' or thread.plot_id!=plot_id
                   or thread.source_record_id!=body.case_id):
        raise HTTPException(409,'This conversation belongs to a different farm context')
    if _chat_repeat(thread,body):
        return _chat_response(thread)
    try:
        request.app.state.farmer_chat_limiter.check(request.client.host if request.client else 'unknown', user.id)
    except HTTPException as exc:
        raise HTTPException(429,'Farmer chat is busy. Try again shortly.',headers=exc.headers) from exc
    history = thread.payload['messages'] if thread else []
    if len(history)>=80:
        raise HTTPException(409,'This conversation is full. Start a new chat.')
    snapshot = _chat_snapshot(db,user,plot,case)
    state = thread.payload.get('state',{}) if thread else {}
    farm_id = plot.farm_id if plot else None
    db.commit()
    message, new_state = farmer_chat.make_turn(body.message,body.locale,history,state,snapshot,
        quote_lookup=lambda *filters: _chat_quotes(user.id,*filters), board_lookup=_chat_district_board)
    with market_service.transaction() as tx:
        actor = market_service.actor(tx,user,roles={'farmer'})
        _chat_scope(tx,actor,plot_id,body.case_id)
        current = tx.get(Record,thread_id)
        if _chat_repeat(current,body):
            return _chat_response(current)
        if (current is None and thread is not None) or (current and len(current.payload['messages'])!=len(history)):
            raise HTTPException(409,'The conversation changed. Reopen it before sending again.')
        messages = [*(current.payload['messages'] if current else []),
                    dict(id=body.request_id, role='user', text=body.message),
                    dict(id=uuid4().hex, role='assistant', **message)]
        payload = dict(messages=messages,state=new_state)
        if current is None:
            current = Record(id=thread_id, owner_id=actor.id, kind='farmer_chat', plot_id=plot_id,
                             farm_id=farm_id,source_record_id=body.case_id,payload=payload)
            tx.add(current)
        else:
            current.payload = payload
            touch(current)
        return _chat_response(current)


@app.post('/api/v1/farmer-chat/conversations/{id}/notes')
def confirm_chat_note(id: str, body: farmer_chat.SaveNote, user: Farmer):
    with market_service.transaction() as tx:
        actor = market_service.actor(tx,user,roles={'farmer'})
        thread = owned(tx,actor,id,'farmer_chat')
        item = next((m for m in thread.payload['messages'] if m['id']==body.message_id and m['role']=='assistant'),None)
        pending = next((a for a in (item or {}).get('actions',[]) if a['kind']=='note'),None)
        if not pending or not thread.source_record_id:
            raise HTTPException(404,'Case note not found')
        if pending.get('done'):
            return _chat_response(thread)
        case = owned(tx,actor,thread.source_record_id,'case')
        add(tx,actor,'feedback',dict(case_id=case.id,note=pending['target'],request_review=False,
            advisor_contacted=False,notice='Local note only; no advisor was contacted.'),case.plot_id,source_record_id=case.id)
        audit(tx,actor,'doctor.feedback',case.id,case.plot_id)
        updated = {**item,'actions':[{**a,'done':True} if a is pending else a for a in item['actions']]}
        thread.payload = {**thread.payload,'messages':[updated if m is item else m for m in thread.payload['messages']]}
        touch(thread)
        return _chat_response(thread)

app.include_router(auth_router)
app.include_router(otp_router)

from .market import router as market_router
app.include_router(market_router)
app.include_router(rescue_router)
app.include_router(farm_tools_router)
