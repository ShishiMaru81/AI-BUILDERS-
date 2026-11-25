"""Private plot tools and consented district-level community aggregates."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_UP
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import farm_advisory, market_service
from .db import Record, User, get_db, now
from .district_prices_catalog import DISTRICT_OPTIONS, canonical_district
from .identity import require_user
from .services import parse_iso_utc

router = APIRouter(prefix='/api/v1/farm-tools', tags=['Farm tools'])
Db = Annotated[Session, Depends(get_db)]
Who = Annotated[User, Depends(require_user)]
DHAKA = timezone(timedelta(hours=6))
RECORD_KINDS = ('farm_ledger', 'storage_batch', 'farm_reminder', 'farm_alert_seen', 'community_report')
Quantity = Annotated[Decimal, Field(gt=0, le=1_000_000, decimal_places=3)]
Money = Annotated[Decimal, Field(gt=0, le=1_000_000_000, decimal_places=2)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


def require_farmer(user: Who):
    if user.role != 'farmer':
        raise HTTPException(403, 'Farm tools are available to farmer accounts')
    return user


Farmer = Annotated[User, Depends(require_farmer)]


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Entry(Input):
    kind: Literal['expense', 'receipt']
    category: Literal['seed', 'inputs', 'labour', 'transport', 'storage', 'other', 'sale']
    amount_bdt: Money
    date: date
    label: Label

    @model_validator(mode='after')
    def verify_category(self):
        if (self.kind == 'receipt') != (self.category == 'sale'):
            raise ValueError('Use the sale category for receipts only')
        return self


class Batch(Input):
    label: Label
    harvested_on: date
    stored_on: date
    quantity_kg: Quantity
    method: Literal['ambient', 'ventilated', 'cold', 'other']

    @model_validator(mode='after')
    def check_dates(self):
        if self.harvested_on > self.stored_on:
            raise ValueError('Storage date cannot precede harvest')
        return self


class Movement(Input):
    kind: Literal['inspection', 'loss', 'removed']
    date: date
    quantity_kg: Quantity | None = None
    label: Label

    @model_validator(mode='after')
    def check_quantity(self):
        if (self.kind == 'inspection') != (self.quantity_kg is None):
            raise ValueError('Provide a weight for losses and removals only')
        return self


class Reminder(Input):
    label: Label
    due_on: date


class Planting(Input):
    date: date | None
    stage: Literal['Seedling', 'Vegetative', 'Flowering', 'Fruiting', 'Harvest']


class Report(Input):
    case_id: str = Field(min_length=1, max_length=80)
    consent: Literal[True]


def _owned(db, user, record_id, kind):
    record = db.get(Record, record_id)
    if not record or record.owner_id != user.id or record.kind != kind:
        raise HTTPException(404, 'Record not found')
    return record


def _rows(db, user, plot_id, kind, limit=None):
    query = (select(Record).where(Record.owner_id == user.id, Record.plot_id == plot_id, Record.kind == kind)
             .order_by(Record.created_at.desc(), Record.id.desc()))
    if limit:
        query = query.limit(limit)
    return list(db.scalars(query))


def _plot_context(db, user, plot_id):
    plot = _owned(db, user, plot_id, 'plot')
    return plot, _owned(db, user, plot.payload['farm_id'], 'farm')


def _insert(db, user, plot, kind, payload, maximum=250, source=None):
    if len(_rows(db, user, plot.id, kind, maximum)) >= maximum:
        raise HTTPException(409, 'The record limit for this plot has been reached')
    record = Record(owner_id=user.id, plot_id=plot.id, farm_id=plot.payload['farm_id'],
                    kind=kind, payload=payload, source_record_id=source)
    db.add(record)
    db.flush()
    return record


def _display(record):
    return {'id': record.id, **record.payload}


def _valid_date(value, today):
    if value > today:
        raise HTTPException(422, 'Enter today’s date or an earlier date')


def _today():
    return datetime.now(DHAKA).date()


def _sum(rows, field):
    return sum((Decimal(row[field]) for row in rows if row.get(field) is not None), Decimal(0))


def _storage(batch):
    events = batch['events']
    loss = _sum([event for event in events if event['kind'] == 'loss'], 'quantity_kg')
    weight = Decimal(batch['quantity_kg'])
    return {**batch, 'loss_kg': loss, 'remaining_kg': weight - _sum(events, 'quantity_kg'),
            'loss_pct': (loss * 100 / weight).quantize(Decimal('0.1'))}


def _alerts(db, user, plot_id):
    current = datetime.now(DHAKA)
    outlook = _rows(db, user, plot_id, 'weather', 1)
    cases = _rows(db, user, plot_id, 'case', 20)
    smart = farm_advisory.evidence_alerts(outlook[0] if outlook else None, cases, current)
    seen = {row.payload['key'] for row in _rows(db, user, plot_id, 'farm_alert_seen')}
    return [alert for alert in smart if alert['id'] not in seen]


@router.get('/plots/{plot_id}')
def overview(plot_id: str, user: Farmer, db: Db, break_even_kg: Quantity | None = None):
    plot, farm = _plot_context(db, user, plot_id)
    district = canonical_district(farm.payload.get('district'))
    today = _today()
    ledger = [_display(row) for row in _rows(db, user, plot_id, 'farm_ledger')]
    expenses = _sum([row for row in ledger if row['kind'] == 'expense'], 'amount_bdt')
    receipts = _sum([row for row in ledger if row['kind'] == 'receipt'], 'amount_bdt')
    reports = _rows(db, user, plot_id, 'community_report')
    return {
        'today': today, 'plot_name': plot.payload['name'], 'planting_date': plot.payload.get('sowing_date'),
        'calendar': farm_advisory.calendar(plot.payload, district, today),
        'alerts': _alerts(db, user, plot_id),
        'reminders': [_display(row) for row in _rows(db, user, plot_id, 'farm_reminder')],
        'ledger': ledger,
        'summary': {
            'expenses_bdt': str(expenses), 'receipts_bdt': str(receipts), 'margin_bdt': str(receipts - expenses),
            'break_even_bdt_per_kg': str((expenses / break_even_kg).quantize(Decimal('0.01'), rounding=ROUND_UP))
            if break_even_kg and expenses else None,
        },
        'storage': [_storage(_display(row)) for row in _rows(db, user, plot_id, 'storage_batch')],
        'sharing_allowed': user.is_demo is False and district is not None,
        'shared_case_ids': [row.source_record_id for row in reports],
    }


@router.patch('/plots/{plot_id}/planting')
def set_planting(plot_id: str, body: Planting, user: Farmer):
    if body.date:
        _valid_date(body.date, _today())
    with market_service.transaction() as db:
        actor = market_service.actor(db, user, {'farmer'})
        plot = _owned(db, actor, plot_id, 'plot')
        plot.payload = {**plot.payload, 'sowing_date': body.date.isoformat() if body.date else None, 'stage': body.stage}
        plot.updated_at = now()
    return {'ok': True}


@router.post('/plots/{plot_id}/ledger', status_code=201)
def add_entry(plot_id: str, body: Entry, user: Farmer):
    _valid_date(body.date, _today())
    with market_service.transaction() as db:
        actor = market_service.actor(db, user, {'farmer'})
        plot = _owned(db, actor, plot_id, 'plot')
        return _display(_insert(db, actor, plot, 'farm_ledger', body.model_dump(mode='json')))


@router.post('/plots/{plot_id}/storage', status_code=201)
def add_batch(plot_id: str, body: Batch, user: Farmer):
    _valid_date(body.stored_on, _today())
    with market_service.transaction() as db:
        actor = market_service.actor(db, user, {'farmer'})
        plot = _owned(db, actor, plot_id, 'plot')
        row = _insert(db, actor, plot, 'storage_batch',
                      {**body.model_dump(mode='json'), 'crop': plot.payload['crop'], 'events': []}, maximum=100)
        return _storage(_display(row))


@router.post('/storage/{batch_id}/events', status_code=201)
def add_movement(batch_id: str, body: Movement, user: Farmer):
    _valid_date(body.date, _today())
    with market_service.transaction() as db:
        actor = market_service.actor(db, user, {'farmer'})
        batch = _owned(db, actor, batch_id, 'storage_batch')
        events = batch.payload['events']
        if body.date.isoformat() < batch.payload['stored_on']:
            raise HTTPException(422, 'Enter an event date on or after storage began')
        if len(events) >= 200:
            raise HTTPException(409, 'This batch has reached its event limit')
        if body.quantity_kg and body.quantity_kg > _storage(_display(batch))['remaining_kg']:
            raise HTTPException(409, 'Weight exceeds the remaining stock')
        event = {**body.model_dump(mode='json'), 'id': uuid4().hex}
        batch.payload = {**batch.payload, 'events': [*events, event]}
        batch.updated_at = now()
        return _storage(_display(batch))


@router.delete('/storage/{batch_id}/events/{event_id}')
def remove_movement(batch_id: str, event_id: str, user: Farmer):
    with market_service.transaction() as db:
        actor = market_service.actor(db, user, {'farmer'})
        batch = _owned(db, actor, batch_id, 'storage_batch')
        events = [event for event in batch.payload['events'] if event['id'] != event_id]
        batch.payload = {**batch.payload, 'events': events}
        batch.updated_at = now()
        return _storage(_display(batch))


@router.post('/plots/{plot_id}/reminders', status_code=201)
def add_reminder(plot_id: str, body: Reminder, user: Farmer):
    with market_service.transaction() as db:
        actor = market_service.actor(db, user, {'farmer'})
        plot = _owned(db, actor, plot_id, 'plot')
        payload = body.model_dump(mode='json')
        for existing in _rows(db, actor, plot_id, 'farm_reminder'):
            if existing.payload == payload:
                return _display(existing)
        return _display(_insert(db, actor, plot, 'farm_reminder', payload, maximum=100))


@router.post('/plots/{plot_id}/alerts/{key}/dismiss')
def dismiss_alert(plot_id: str, key: str, user: Farmer):
    with market_service.transaction() as db:
        actor = market_service.actor(db, user, {'farmer'})
        plot = _owned(db, actor, plot_id, 'plot')
        if any(alert['id'] == key for alert in _alerts(db, actor, plot_id)):
            seen = _rows(db, actor, plot_id, 'farm_alert_seen')
            for row in seen:
                if row.payload['date'] < (_today() - timedelta(days=14)).isoformat():
                    db.delete(row)
            _insert(db, actor, plot, 'farm_alert_seen', {'key': key, 'date': _today().isoformat()}, maximum=50)
    return {'ok': True}


@router.delete('/records/{kind}/{record_id}')
def remove_record(kind: Literal['farm_ledger', 'storage_batch', 'farm_reminder'], record_id: str, user: Farmer):
    with market_service.transaction() as db:
        actor = market_service.actor(db, user, {'farmer'})
        db.delete(_owned(db, actor, record_id, kind))
    return {'ok': True}


@router.post('/plots/{plot_id}/community')
def share_case(plot_id: str, body: Report, user: Farmer):
    with market_service.transaction() as db:
        actor = market_service.actor(db, user, {'farmer'})
        plot, farm = _plot_context(db, actor, plot_id)
        case = _owned(db, actor, body.case_id, 'case')
        if case.plot_id != plot.id or (case.farm_id and case.farm_id != farm.id):
            raise HTTPException(404, 'Record not found')
        district = canonical_district(farm.payload.get('district'))
        meta = case.payload.get('meta') or {}
        crop = case.payload.get('crop') or plot.payload.get('crop')
        created = parse_iso_utc(case.created_at)
        observed_on = created.astimezone(DHAKA).date() if created else None
        if (actor.is_demo is not False or not district or crop not in farm_advisory.CALENDARS
                or meta.get('is_simulated') is not False or not observed_on
                or not timedelta(0) <= _today() - observed_on < timedelta(days=28)):
            raise HTTPException(422, 'Sharing requires a recent live potato or tomato screening and a supported district')
        if not any(row.source_record_id == case.id for row in _rows(db, actor, plot.id, 'community_report')):
            _insert(db, actor, plot, 'community_report',
                    {'district': district, 'crop': crop, 'observed_on': observed_on.isoformat()},
                    source=case.id, maximum=100)
    return {'ok': True}


@router.delete('/community/{case_id}')
def withdraw_case(case_id: str, user: Farmer):
    with market_service.transaction() as db:
        actor = market_service.actor(db, user, {'farmer'})
        case = _owned(db, actor, case_id, 'case')
        for row in _rows(db, actor, case.plot_id, 'community_report'):
            if row.source_record_id == case.id:
                db.delete(row)
    return {'ok': True}


@router.get('/community')
def community(user: Farmer, db: Db, crop: Literal['tomato', 'potato'] = Query('tomato')):
    end = _today()
    start = end - timedelta(days=27)
    case = Record.__table__.alias('screening')
    query = (select(Record).join(User, User.id == Record.owner_id)
             .join(case, (case.c.id == Record.source_record_id) & (case.c.owner_id == Record.owner_id))
             .where(Record.kind == 'community_report', User.is_active.is_(True), User.is_demo.is_(False),
                    Record.payload['crop'].as_string() == crop,
                    Record.payload['observed_on'].as_string() >= start.isoformat(),
                    Record.payload['observed_on'].as_string() <= end.isoformat()))
    by_district = defaultdict(set)
    for row in db.scalars(query):
        by_district[row.payload['district']].add(row.owner_id)
    bands = {district: '3–5' if len(owners) < 6 else '6–10' if len(owners) <= 10 else '11+'
             for district, owners in by_district.items() if len(owners) >= 3}
    return {'start': start, 'end': end, 'crop': crop,
            'districts': [{**item, 'band': bands.get(item['id'])} for item in DISTRICT_OPTIONS]}
