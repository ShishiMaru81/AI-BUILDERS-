"""Bilingual scouting prompts and evidence-based in-app alerts."""
from datetime import date, datetime, timedelta

from .services import compute_effective_weather, parse_iso_utc


CALENDARS = {
    'potato': 'https://www.bamis.gov.bd/calendar/1/52',
    'tomato': 'https://www.bamis.gov.bd/calendar/1/13',
}
DHAKA_REGION = {'Dhaka', 'Gazipur', 'Tangail', 'Narsingdi', 'Narayanganj', 'Munshiganj', 'Manikganj'}
PROMPTS = {
    'potato': {
        'seedling': ('Check emergence and mark gaps or standing water.', 'চারা উঠেছে কি না দেখুন। ফাঁকা স্থান ও জমে থাকা পানি চিহ্নিত করুন।'),
        'vegetative': ('Check lower leaves and stems for new dark patches. Photograph changes.', 'নিচের পাতা ও কাণ্ডে নতুন কালচে দাগ দেখুন। পরিবর্তনের ছবি তুলুন।'),
        'flowering': ('Inspect foliage after wet weather and record which rows show symptoms.', 'ভেজা আবহাওয়ার পর পাতা দেখুন। কোন সারিতে লক্ষণ আছে লিখে রাখুন।'),
        'fruiting': ('Check for standing water and record changes in foliage as tubers develop.', 'কন্দ বৃদ্ধির সময় পানি জমে কি না ও পাতার পরিবর্তন লিখে রাখুন।'),
        'harvest': ('Sort damaged tubers and record the harvested and stored weights separately.', 'ক্ষতিগ্রস্ত আলু আলাদা করুন। তোলা ও সংরক্ষিত আলুর ওজন আলাদা করে লিখুন।'),
    },
    'tomato': {
        'seedling': ('Check seedlings for gaps, wilt, or collapsed stems.', 'চারা না ওঠা, ঢলে পড়া বা কাণ্ড ভেঙে যাওয়ার লক্ষণ দেখুন।'),
        'vegetative': ('Check lower leaves for spots and note where symptoms begin.', 'নিচের পাতায় দাগ দেখুন। কোথায় প্রথম লক্ষণ দেখা যায় লিখুন।'),
        'flowering': ('Check flowers and supports, especially after windy or wet weather.', 'বিশেষ করে ঝড়ো বা ভেজা আবহাওয়ার পর ফুল ও খুঁটি দেখুন।'),
        'fruiting': ('Inspect fruit for splits or soft patches. Record how many are affected.', 'ফলে ফাটল বা নরম দাগ দেখুন। কতটি ফলে লক্ষণ আছে লিখুন।'),
        'harvest': ('Separate damaged fruit and record harvested weight before packing.', 'ক্ষতিগ্রস্ত ফল আলাদা করুন। প্যাক করার আগে তোলা ফলের ওজন লিখুন।'),
    },
}


def calendar(plot: dict, district: str | None, today: date) -> dict:
    crop = plot.get('crop')
    stage = str(plot.get('stage', '')).strip().casefold()
    try:
        planted = date.fromisoformat(plot.get('sowing_date') or '')
    except (ValueError, TypeError):
        planted = None
    week = ((today - planted).days // 7 + 1) if planted and planted <= today else None
    source = CALENDARS.get(crop)
    in_dhaka = district in DHAKA_REGION or (crop == 'tomato' and district == 'Kishoreganj')
    region = 'Dhaka' if source and in_dhaka else None
    if region:
        source += '/9/'
    prompt = PROMPTS.get(crop, {}).get(stage)
    monday = today - timedelta(days=today.weekday())
    tasks = []
    if prompt:
        tasks.append({'date': today, 'en': prompt[0], 'bn': prompt[1]})
        tasks.append({
            'date': today + timedelta(days=7),
            'en': 'Recheck the same plants or batch and update the recorded growth stage.',
            'bn': 'একই গাছ বা ব্যাচ আবার দেখুন এবং নথিভুক্ত বৃদ্ধির পর্যায় হালনাগাদ করুন।',
        })
    return {'crop': crop, 'stage': plot.get('stage'), 'district': district, 'region': region,
            'planting_week': week, 'week_start': monday, 'source_url': source, 'tasks': tasks}


def evidence_alerts(weather, cases, current: datetime) -> list[dict]:
    alerts = []
    if weather:
        outlook = compute_effective_weather(weather.payload, current)
        meta = outlook['meta']
        if (meta.get('mode') == 'LIVE' and meta.get('is_simulated') is False
                and meta.get('freshness') == 'fresh' and not outlook['is_expired']
                and not outlook.get('last_refresh_failed_at') and outlook['level'] == 'prepare'):
            anchor = parse_iso_utc(outlook.get('horizon_valid_until'))
            if anchor and anchor > current:
                alerts.append({
                    'id': 'rain-' + current.date().isoformat(), 'kind': 'rain',
                    'en': 'Inspect drainage before the forecast rain.',
                    'bn': 'পূর্বাভাসের বৃষ্টির আগে পানি নিষ্কাশনের পথ দেখুন।',
                    'detail': str(outlook['total_mm']), 'hours': outlook['horizon_hours'],
                    'source_url': 'https://open-meteo.com/en/docs',
                })
    for case in cases:
        stamp = parse_iso_utc(case.updated_at or case.created_at)
        evidence = case.payload.get('classification') or {}
        label = str(evidence.get('top_label') or '').casefold()
        if (stamp and current - timedelta(days=7) <= stamp <= current
                and (case.payload.get('meta') or {}).get('is_simulated') is False
                and evidence.get('abstained') is False and label
                and 'healthy' not in label and not label.startswith(('unknown', 'uncertain'))):
            alerts.append({
                'id': 'scout-' + case.id, 'kind': 'scout',
                'en': 'Revisit the plants in your recent screening and check for new symptoms.',
                'bn': 'সম্প্রতি পরীক্ষা করা গাছগুলো আবার দেখুন এবং নতুন লক্ষণ খুঁজুন।',
            })
            break
    return alerts
