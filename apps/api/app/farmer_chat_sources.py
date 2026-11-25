"""Read district bulletins and seasonal calendars from Bangladesh's extension service."""

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import unescape
from io import BytesIO
import re
from threading import Lock
from time import monotonic
import unicodedata

import httpx
from pypdf import PdfReader
from pypdf.errors import PyPdfError


BAMIS = "https://www.bamis.gov.bd"
DAM = "https://market.dam.gov.bd/market_daily_price_report"
CALENDAR = f"{BAMIS}/en/calendar/"
BULLETINS = f"{BAMIS}/en/bulletin/district/current/0/"
DHAKA_TIME = timezone(timedelta(hours=6))
PDF_URL = re.compile(r"https://www\.bamis\.gov\.bd/res/(?:public/)?calendars/\d{4}/\d{2}/\d{2}/\d+\.pdf")
HTML_URL = re.compile(r"https://www\.bamis\.gov\.bd/(?:en|bn)/(?:bulletin/district/(?:current|archive)/\d+|bulletin/view/\d+|calendar/1/\d+/\d+|diseases/1/all/\d+)/")


@dataclass(frozen=True)
class District:
    id: str
    name: str
    bangla: str
    region: str
    region_id: str


def _key(value: str) -> str:
    return re.sub(r"[\s.'’_-]+", "", unicodedata.normalize("NFC", value.casefold()))


# BAMIS district IDs come from its district selector. Calendar regions come from the
# district lists in its regional rice calendars; these differ from civil divisions.
_REGIONS = {
    ("Barishal", "5"): "19:Jhalokati:ঝালকাঠি 20:Patuakhali:পটুয়াখালী 21:Pirojpur:পিরোজপুর 24:Barguna:বরগুনা 22:Barishal:বরিশাল 23:Bhola:ভোলা",
    ("Bogura", "1"): "3:Bogura:বগুড়া 4:Joypurhat:জয়পুরহাট 2:Pabna:পাবনা 1:Sirajganj:সিরাজগঞ্জ",
    ("Chattogram", "13"): "57:Chattogram:চট্টগ্রাম 60:Lakshmipur:লক্ষ্মীপুর 61:Cox's_Bazar:কক্সবাজার 58:Noakhali:নোয়াখালী 59:Feni:ফেনী",
    ("Cumilla", "12"): "54:Cumilla:কুমিল্লা 56:Chandpur:চাঁদপুর 55:Brahmanbaria:ব্রাহ্মণবাড়িয়া",
    ("Dhaka", "9"): "37:Dhaka:ঢাকা 43:Tangail:টাঙ্গাইল 39:Gazipur:গাজীপুর 40:Narsingdi:নরসিংদী 38:Narayanganj:নারায়ণগঞ্জ 41:Munshiganj:মুন্সিগঞ্জ 42:Manikganj:মানিকগঞ্জ",
    ("Dinajpur", "6"): "26:Dinajpur:দিনাজপুর 27:Thakurgaon:ঠাকুরগাঁও 25:Panchagarh:পঞ্চগড়",
    ("Faridpur", "10"): "49:Faridpur:ফরিদপুর 46:Rajbari:রাজবাড়ী 47:Madaripur:মাদারীপুর 45:Shariatpur:শরীয়তপুর 48:Gopalganj:গোপালগঞ্জ",
    ("Jashore", "4"): "13:Jashore:যশোর 16:Kushtia:কুষ্টিয়া 15:Chuadanga:চুয়াডাঙ্গা 18:Jhenaidah:ঝিনাইদহ 14:Meherpur:মেহেরপুর 66:Magura:মাগুরা",
    ("Khulna", "3"): "65:Khulna:খুলনা 9:Satkhira:সাতক্ষীরা 12:Bagerhat:বাগেরহাট 10:Narail:নড়াইল",
    ("Mymensingh", "8"): "34:Mymensingh:ময়মনসিংহ 44:Kishoreganj:কিশোরগঞ্জ 33:Jamalpur:জামালপুর 35:Netrokona:নেত্রকোনা 36:Sherpur:শেরপুর",
    ("Rajshahi", "2"): "5:Rajshahi:রাজশাহী 7:Chapai_Nawabganj:চাঁপাইনবাবগঞ্জ 8:Naogaon:নওগাঁ 6:Natore:নাটোর",
    ("Rangamati", "14"): "62:Rangamati:রাঙ্গামাটি 63:Khagrachari:খাগড়াছড়ি 64:Bandarban:বান্দরবান",
    ("Rangpur", "7"): "31:Rangpur:রংপুর 32:Kurigram:কুড়িগ্রাম 30:Gaibandha:গাইবান্ধা 29:Nilphamari:নীলফামারী 28:Lalmonirhat:লালমনিরহাট",
    ("Sylhet", "11"): "50:Sylhet:সিলেট 51:Moulvibazar:মৌলভীবাজার 53:Sunamganj:সুনামগঞ্জ 52:Habiganj:হবিগঞ্জ",
}
_DISTRICTS = {}
for (region, region_id), entries in _REGIONS.items():
    for entry in entries.split():
        district_id, english, bangla = entry.split(":")
        district = District(district_id, english.replace("_", " "), bangla, region, region_id)
        _DISTRICTS[_key(english)] = _DISTRICTS[_key(bangla)] = district
for old, new in {"Chittagong": "Chattogram", "Comilla": "Cumilla", "Jessore": "Jashore",
                 "Bogra": "Bogura", "Barisal": "Barishal", "Netrakona": "Netrokona",
                 "Jhalakati": "Jhalokati", "রাজবাড়ি": "Rajbari"}.items():
    _DISTRICTS[_key(old)] = _DISTRICTS[_key(new)]


# Crop IDs and season names are those on the BAMIS calendar index.
_CROPS = {
    "13": ("Tomato", "টমেটো", "টমাটো"), "52": ("Potato", "আলু"),
    "74": ("Aman rice", "আমন ধান", "rice aman", "aman", "ধান আমন", "আমন"),
    "7": ("Aus rice", "আউশ ধান", "rice aus", "aus", "ধান আউশ", "আউশ"),
    "75": ("Boro rice", "বোরো ধান", "rice boro", "boro", "ধান বোরো", "বোরো"),
    "76": ("Rice", "ধান", "paddy"), "8": ("Maize", "ভুট্টা", "corn"),
    "78": ("Kharif maize", "খরিফ ভুট্টা", "maize kharif", "maize kharif 1"),
    "79": ("Rabi maize", "রবি ভুট্টা", "maize rabi", "winter maize"),
    "9": ("Wheat", "গম"), "44": ("Mustard", "সরিষা", "সরিষা শস্য"),
    "69": ("Banana", "কলা"), "15": ("Brinjal", "বেগুন", "eggplant"),
    "96": ("Cotton", "তুলা"), "19": ("Cucumber", "শসা"), "48": ("Garlic", "রসুন"),
    "14": ("Gourd", "লাউ"),
    "71": ("Guava", "পেয়ারা"), "70": ("Jackfruit", "কাঁঠাল"), "72": ("Jujube", "বরই"),
    "10": ("Jute", "পাট"), "58": ("Lentil", "মসুর"), "73": ("Litchi", "লিচু", "lychee"),
    "65": ("Mango", "আম"), "46": ("Onion", "পেঁয়াজ"), "67": ("Papaya", "পেঁপে"),
    "45": ("Pepper", "মরিচ", "chilli", "chili", "chili pepper"),
    "68": ("Pineapple", "আনারস"), "16": ("Pointed gourd", "পটল"), "32": ("Pumpkin", "কুমড়া"),
    "36": ("Soybean", "সয়াবিন"), "12": ("Sugarcane", "আখ"),
    "86": ("Kharif green gram", "খরিফ মুগ", "green gram kharif"),
    "85": ("Rabi green gram", "রবি মুগ", "green gram rabi"),
    "80": ("Rabi groundnut", "রবি চিনাবাদাম", "groundnut rabi"),
    "84": ("Kharif groundnut", "খরিফ চিনাবাদাম", "groundnut kharif"),
}
_CROP_IDS = {_key(name): cid for cid, names in _CROPS.items() for name in names if name}
_FRESH = {"13", "52", "69", "15", "19", "48", "14", "71", "70", "72", "73", "65", "46", "67", "45", "68", "16", "32"}
_RICE = {"74", "7", "75", "76"}


def _today():
    return datetime.now(DHAKA_TIME).date()


def _source(label, url, detail, status, **fields):
    return {"label": label, "url": url, "detail": detail, "status": status, **fields}


def _text(markup):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", markup)).split())


_CACHE = OrderedDict()
_CACHE_LOCK = Lock()


def _download(url, deadline, pdf):
    limit = 3_000_000 if pdf else 450_000
    timeout = min(4.0, deadline - monotonic())
    if timeout <= 0:
        return ""
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=False) as response:
        response.raise_for_status()
        buffer = bytearray()
        for chunk in response.iter_bytes(32_768):
            if monotonic() > deadline or len(buffer) + len(chunk) > limit:
                return ""
            buffer.extend(chunk)
    if pdf:
        if not buffer.startswith(b"%PDF-"):
            return ""
        return " ".join(PdfReader(BytesIO(buffer)).pages[0].extract_text().split())[:45_000]
    return buffer.decode("utf-8-sig", errors="replace")


def _read(url, deadline):
    pdf = PDF_URL.fullmatch(url) is not None
    if not pdf and not HTML_URL.fullmatch(url):
        return ""
    now = monotonic()
    with _CACHE_LOCK:
        item = _CACHE.get(url)
        if item and item[0] > now:
            _CACHE.move_to_end(url)
            return item[1]
    if now >= deadline:
        return ""
    try:
        value = _download(url, deadline, pdf)
    except (httpx.HTTPError, OSError, PyPdfError, ValueError, IndexError, KeyError, RecursionError):
        value = ""
    ttl = (900 if "/bulletin/" in url else 86_400) if value else 30
    with _CACHE_LOCK:
        _CACHE[url] = (monotonic() + ttl, value)
        _CACHE.move_to_end(url)
        if len(_CACHE) > 96:
            _CACHE.popitem(last=False)
    return value


_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_DATE = r"(\d{1,2}[./-]\d{1,2}[./-]\d{4})"


def _number_date(text):
    try:
        day, month, year = map(int, re.split(r"[./-]", text.translate(_DIGITS)))
        return date(year, month, day)
    except ValueError:
        return None


def _bulletin(d, crop_id, bn, deadline):
    url = f"{BAMIS}/en/bulletin/district/current/{d.id}/" if d else BULLETINS
    label = "বামিস জেলা বুলেটিন" if bn else "BAMIS district bulletin"
    fallback = _source(label, url, "উৎসের তালিকা। এই জেলার তারিখসহ বুলেটিন যাচাই করা যায়নি।" if bn else
                       "Source directory. A dated bulletin for the requested district could not be verified.", "directory")
    if not d:
        return fallback
    page = _read(url, deadline)
    header = re.search(r"<h2>\s*District AGROMETEOROLOGICAL ADVISORY SERVICE BULLETIN\s+(\d{1,2} [A-Za-z]+ \d{4})\s*</h2>", page, re.I)
    verified = None
    if header:
        verified = _parse_bulletin(page, header[1], d, crop_id, bn, label, url)
        if verified and verified["status"] == "dated_bulletin":
            return verified
    archive = _read(f"{BAMIS}/en/bulletin/district/archive/{d.id}/", deadline)
    rows = re.findall(r'<tr\b[^>]*>\s*<td[^>]*>\s*(\d{1,2} [A-Za-z]+ \d{4})\s*</td>\s*<td[^>]*>\s*<a href="https://www\.bamis\.gov\.bd/bulletin/view/(\d+)/?"', archive, re.S | re.I)
    candidates = []
    for when, bulletin_id in rows:
        try:
            day = datetime.strptime(when, "%d %B %Y").date()
        except ValueError:
            continue
        if day <= _today():
            candidates.append((day, when, bulletin_id))
    if candidates:
        newest, when, bulletin_id = max(candidates)
        if verified and verified["as_of"] >= newest.isoformat():
            return verified
        url = f"{BAMIS}/en/bulletin/view/{bulletin_id}/"
        archived = _parse_bulletin(_read(url, deadline), when, d, crop_id, bn, label, url)
        if archived:
            return archived
    return verified or fallback


def _parse_bulletin(page, header_date, d, crop_id, bn, label, url):
    body = re.search(r'id=["\']Weather_data_container["\'][^>]*>(.*?)id=["\'](?:text_data_container|AiContent)["\']', page, re.S | re.I)
    if not body:
        return None
    info = unicodedata.normalize("NFC", _text(body[1])).translate(_DIGITS)
    place = re.search(r"জেলা\s*[:ঃ]\s*([^\s,।]+)", info)
    issue = re.search(r"তারিখ\s*[:ঃ]\s*" + _DATE, info)
    span = re.search(_DATE + r"\s*থেকে\s*" + _DATE + r"\s*পর্যন্ত\s*কৃষি", info)
    if not place or _key(place[1]) != _key(d.bangla) or not issue or not span:
        return None
    try:
        issued = datetime.strptime(header_date, "%d %B %Y").date()
    except ValueError:
        return None
    start, end = _number_date(span[1]), _number_date(span[2])
    today = _today()
    if issued != _number_date(issue[1]) or start != issued or not end or not start <= end <= start + timedelta(days=10) or issued > today:
        return None
    dated = {"as_of": issued.isoformat(), "valid_until": end.isoformat()}
    name = d.bangla if bn else d.name
    detail = (f"{name} জেলার বুলেটিন প্রকাশ {issued}, মেয়াদ {end} পর্যন্ত।" if bn else
              f"The {name} district bulletin was issued {issued} and covers {start} through {end}.")
    if today > end:
        detail += " মেয়াদ শেষ।" if bn else " This issue has expired."
        return _source(label, url, detail, "expired_bulletin", **dated)

    # Read the forecast table only. The preceding observations use the same row labels.
    forecast = re.search(r"পূর্বাভাস.*?<table\b[^>]*>(.*?)</table>", body[1], re.S)
    if forecast:
        rows = [[_text(cell) for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
                for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", forecast[1], re.S | re.I)]
        if rows:
            rain = next((row for row in rows if row and row[0].startswith("বৃষ্টিপাত") and "মি" in row[0]), [])
            for col, day in enumerate(rows[0]):
                if _number_date(day) == today and col < len(rain):
                    amount = rain[col].translate(_DIGITS)
                    if re.fullmatch(r"\d{1,3}(?:\.\d{1,2})?", amount):
                        detail += (f" {today} তারিখের বৃষ্টিপাতের পূর্বাভাস {amount} মিমি।" if bn else
                                   f" Forecast rainfall for {today} is {amount} mm.")
                    break
    # Translate only these whole, unconditional general-agriculture bullets. Crop- or
    # stage-specific lists, dosages and warning prose must not become general advice.
    content = re.search(r'id=["\']AiContent["\'][^>]*>(.*?)</div>', page, re.S | re.I)
    if content and "সম্ভাব্য বৃষ্টিপাতের ক্ষতিকর প্রভাব" in _text(content[1].split("<ul", 1)[0]):
        listing = re.search(r"<ul\b[^>]*>(.*?)</ul>", content[1], re.S | re.I)
        items = {_text(item) for item in re.findall(r"<li\b[^>]*>(.*?)</li>", listing[1], re.S | re.I)} if listing else set()
        if "জমির নিষ্কাশন নালা পরিষ্কার রাখুন যেন জমিতে অতিরিক্ত পানি জমে না থাকতে পারে।" in items:
            detail += " জমিতে পানি জমা ঠেকাতে বামিস নালা পরিষ্কার রাখতে বলেছে।" if bn else " BAMIS advises clearing field drains so excess water can escape."
        if "বৃষ্টিপাতের আগেই পরিপক্ক ফসল সংগ্রহ করে নিরাপদ জায়গায় রাখুন।" in items:
            detail += " বৃষ্টির আগে পাকা ফসল তুলে নিরাপদ স্থানে রাখার পরামর্শও রয়েছে।" if bn else " It advises moving mature crops to a safe place before rain."
    elif content and crop_id:
        detail += _stage_advice(content[1], crop_id, bn)
    return _source(label, url, detail, "dated_bulletin", **dated)


def _stage_advice(markup, crop_id, bn):
    """Use the bulletin's crop section and carry its stage into the advice."""
    rules = [
        ("75", "বীজতলা", "উঁচু জায়গায় বীজতলা তৈরি করুন এবং জমি থেকে পানি নিষ্কাশনের ব্যবস্থা রাখুন।",
         " বোরো ধানের বীজতলা উঁচু জমিতে করে পানি বের হওয়ার পথ রাখতে বলেছে বামিস।",
         " For Boro rice nurseries, BAMIS advises preparing the seedbed on higher ground with drainage."),
        ("74", "পরিপক্ক থেকে কর্তন", "শতকরা ৮০ ভাগ ধান পরিপক্ক হলে রৌদ্রোজ্জ্বল দিনে ধান কর্তন করুন।",
         " কাটার পর্যায়ে আমন ধানের ৮০ শতাংশ পাকলে রৌদ্রোজ্জ্বল দিনে কাটতে বলেছে বামিস।",
         " For Aman rice at harvest, BAMIS advises cutting on a sunny day once 80% of the rice is mature."),
        ("9", "বপন", "উপযুক্ত জো অবস্থায় বপনের জন্য জমি তৈরি করুন।",
         " গম বপনের জন্য মাটি চাষের উপযোগী আর্দ্রতায় এলে জমি তৈরি করতে বলেছে বামিস।",
         " For wheat at sowing, BAMIS advises preparing the land when soil moisture allows cultivation."),
    ]
    sections = re.findall(r"<p\b[^>]*>\s*<strong[^>]*>([^<>]+)</strong>\s*</p>\s*<ul[^>]*>(.*?)</ul>", markup, re.S | re.I)
    for title, listing in sections:
        if _CROP_IDS.get(_key(_text(title))) != crop_id:
            continue
        items = [_text(item) for item in re.findall(r"<li\b[^>]*>(.*?)</li>", listing, re.S | re.I)]
        if not items or ":" not in items[0]:
            continue
        label, stage = items[0].split(":", 1)
        if _key(label) != _key("পর্যায়"):
            continue
        for cid, target_stage, sentence, bangla, english in rules:
            if cid == crop_id and _key(stage) == _key(target_stage) and any(sentence in item for item in items[1:]):
                return bangla if bn else english
    return ""


_MONTHS = [
    ("January", "জানুয়ারি"), ("February", "ফেব্রুয়ারি"), ("March", "মার্চ"),
    ("April", "এপ্রিল"), ("May", "মে"), ("June", "জুন"), ("July", "জুলাই"),
    ("August", "আগস্ট"), ("September", "সেপ্টেম্বর"), ("October", "অক্টোবর"),
    ("November", "নভেম্বর"), ("December", "ডিসেম্বর"),
]


def _calendar(crop_id, d, bn, deadline):
    base_label = "বামিস ফসল পঞ্জিকা" if bn else "BAMIS crop calendar"
    if crop_id in {"76", "8"}:
        seasons = ("আমন, আউশ বা বোরো" if bn else "Aman, Aus or Boro") if crop_id == "76" else ("রবি বা খরিফ" if bn else "Rabi or Kharif")
        return _source(base_label, CALENDAR, (f"মৌসুমভিত্তিক পঞ্জিকার তালিকা। কোন মৌসুম তা জানান ({seasons})।" if bn else
                       f"Seasonal calendar directory. Specify the season ({seasons}) to select the matching calendar."), "directory")
    if not crop_id or not d:
        return _source(base_label, CALENDAR, "ফসল ও অঞ্চল অনুযায়ী সরকারি পঞ্জিকা বেছে নিন।" if bn else
                       "Calendar directory. Select the crop and region to find the seasonal chart.", "directory")
    language_index = 1 if bn else 0
    crop = _CROPS[crop_id][language_index]
    url = f"{BAMIS}/en/calendar/1/{crop_id}/{d.region_id}/"
    directory = _source(base_label, f"{BAMIS}/en/calendar/1/{crop_id}/",
                        (f"{crop} ফসলের অঞ্চলভিত্তিক পঞ্জিকার তালিকা। সংশ্লিষ্ট অঞ্চলের সময়কাল যাচাই করা যায়নি।" if bn else
                         f"Regional directory for {crop}. The duration for the requested region could not be verified."), "directory")
    page = _read(url, deadline)
    download = re.search(r'<a\b[^>]*\bhref="([^"]+\.pdf)"[^>]*\bdownload=', page, re.I)
    if not download or not PDF_URL.fullmatch(download[1]):
        return directory
    pdf = _read(download[1], deadline)
    # The publisher occasionally files an English PDF under the wrong season.
    # Validate its printed title and region before quoting any number.
    title = re.split(r"\bDistricts?\b|\(", pdf[:350], maxsplit=1, flags=re.I)[0]
    normalized_title = _key(title)
    words = _CROPS[crop_id][0].lower().split()
    if crop_id in {"78", "79", "84", "80", "85", "86"}:
        # The season sometimes appears in the second header following the district list.
        title = pdf.split("Duration", 1)[0][:450]
        normalized_title = _key(title).replace("robi", "rabi")
    if _key(d.region) not in normalized_title or not all(word in normalized_title for word in words):
        return directory
    duration = re.search(r"\bduration\s*[:：]?\s*(\d{1,3}(?:\s*[-–]\s*\d{1,3})?)\s*days?\b", pdf, re.I)
    month_line = re.search(r"\bmonths?\s*[:：]?\s+([a-z.\s]+?)\s+(?:std\.?\s*week|standard\s+week)", pdf, re.I)
    if not duration or not month_line:
        return directory
    month_numbers = []
    for token in month_line[1].lower().replace(".", "").split():
        index = next((i for i, (en, _) in enumerate(_MONTHS) if token in {en.lower(), en[:3].lower()}), None)
        if index is None or (month_numbers and index != (month_numbers[-1] + 1) % 12):
            return directory
        month_numbers.append(index)
    if not month_numbers:
        return directory
    first, last = _MONTHS[month_numbers[0]][language_index], _MONTHS[month_numbers[-1]][language_index]
    region = _DISTRICTS[_key(d.region)].bangla if bn else d.region
    span = duration[1]
    if crop_id == "13" and re.search(r"rabi\s*season", title, re.I):
        crop = f"রবি মৌসুমের {crop}" if bn else f"Rabi {crop}"
    detail = (f"মৌসুমি পঞ্জিকা। {region} অঞ্চলের {crop} পঞ্জিকায় {first} থেকে {last} পর্যন্ত দেখানো হয়েছে। ফসলের সময়কাল {span} দিন।" if bn else
              f"Seasonal reference. The {region} region calendar for {crop} spans {first} through {last} and gives a crop duration of {span} days.")
    return _source(base_label, download[1], detail, "seasonal_reference", region=d.region)


def _health(crop_id, bn, deadline):
    lang = "bn" if bn else "en"
    label = "বামিস ফসলের রোগ নির্দেশিকা" if bn else "BAMIS crop disease guide"
    directory = _source(label, f"{BAMIS}/{lang}/diseases/",
                        "রোগ নির্দেশিকার তালিকা। ফসল বেছে নিয়ে লক্ষণ মিলিয়ে দেখুন।" if bn else
                        "Reference directory. Select your crop to compare its disease descriptions and illustrations.", "directory")
    if not crop_id:
        return directory
    url = f"{BAMIS}/{lang}/diseases/1/all/{crop_id}/"
    page = _read(url, deadline)
    headings = re.findall(r"<h2>(.*?)</h2>", page, re.I | re.S)
    if not headings or not any(_key(term) in _key(_text(headings[-1])) for term in _CROPS[crop_id]):
        return directory
    names = [_text(name) for name in re.findall(r'<th\b[^>]*colspan="2"[^>]*>(.*?)</th>', page, re.I | re.S)]
    names = list(dict.fromkeys(name for name in names if 1 < len(name) < 80))[:3]
    if not names:
        return directory
    crop = _CROPS[crop_id][1 if bn else 0]
    entries = ", ".join(names)
    detail = (f"রোগ শনাক্তকরণের সহায়িকা। {crop} ফসলের জন্য বামিসে {entries} আছে। মাঠের লক্ষণ ছবির সঙ্গে মিলিয়ে দেখুন।" if bn else
              f"Scouting reference. For {crop}, BAMIS lists {entries}. Compare symptoms with the illustrated entries before drawing a conclusion.")
    return _source(label, url, detail, "reference")


def _market(bn):
    # DAM requires a named market, price type and reporting date. Its public ticker
    # has no market/unit provenance and must never be quoted as a local price.
    return _source("কৃষি বিপণন অধিদপ্তরের দৈনিক বাজারদর" if bn else "DAM daily market price report",
                   f"{DAM}?L={'B' if bn else 'E'}", ("যাচাইকৃত স্থানীয় দর পাওয়া যায়নি। বাজার, তারিখ ও পাইকারি বা খুচরা ধরন বেছে প্রতিবেদন খুলে পণ্যের নাম ও একক মিলিয়ে দেখুন।" if bn else
                   "Source directory. No local price has been verified. Select the market, date and wholesale or retail price type, then check the commodity and unit."), "directory")


def _storage(crop_id, bn):
    if crop_id == "52":
        return _source("আলু সংরক্ষণ · মিনেসোটা বিশ্ববিদ্যালয়" if bn else "Potato storage · University of Minnesota Extension",
                       "https://blog-fruit-vegetable-ipm.extension.umn.edu/2019/10/potatoes-post-harvest-disorders-and.html",
                       ("আলু বাছাই করুন, সংরক্ষণের জায়গায় বাতাস চলাচলের ব্যবস্থা রাখুন এবং ভেজা জায়গা ও নতুন পচন নিয়মিত পরীক্ষা করুন।" if bn else
                        "Sort the potatoes, keep air moving in the store, and check regularly for wet areas and newly damaged tubers."), "reference")
    if crop_id in _RICE:
        return _source("ইরি ধান সংরক্ষণ নির্দেশিকা" if bn else "IRRI rice harvesting manual",
                       "https://www.knowledgebank.irri.org/images/docs/training-manual-harvesting.pdf",
                       ("সংরক্ষণ নির্দেশিকা। সংরক্ষণের আগে ধান শুকিয়ে আর্দ্রতা মাপুন। খাবার ধান ও বীজ ধানের জন্য নির্দেশিকায় ভিন্ন মাত্রা দেওয়া আছে।" if bn else
                        "Storage reference. Dry rice grain and check its moisture before storing. The manual distinguishes storage moisture for grain and for seed."), "reference")
    if crop_id in {"8", "78", "79", "9"}:
        return _source("এফএও শস্য সংরক্ষণ নির্দেশিকা" if bn else "FAO stored grain guide",
                       "https://www.fao.org/4/v5380e/v5380e06.htm",
                       ("সংরক্ষণ নির্দেশিকা। শস্য শুকিয়ে এবং গুদাম পরিষ্কার করে তারপর শস্য রাখুন। ভেজা দানায় ছত্রাক ও পোকা ছড়াতে পারে।" if bn else
                        "Storage reference. Dry the grain and clean the store before loading. Pockets of damp grain can allow insects and mould to spread."), "reference")
    if crop_id in _FRESH:
        return _source("এফএও ফল ও সবজি সংগ্রহ নির্দেশিকা" if bn else "FAO fresh produce handling guide",
                       "https://www.fao.org/4/ae075e/ae075e03.htm",
                       ("সংগ্রহ নির্দেশিকা। ফল ও সবজি সাবধানে তুলুন। পরিবহনে দেরি হলে ভরা পাত্রগুলো ছায়ায় রাখুন।" if bn else
                        "Handling reference. Pick fruit and vegetables gently. Keep filled field containers in the shade if transport is delayed."), "reference")
    return _source("বামিস ফসল নির্দেশিকা" if bn else "BAMIS crop directory", f"{BAMIS}/{'bn' if bn else 'en'}/crops/",
                   "এই ফসলের নির্দিষ্ট সংরক্ষণ পদ্ধতি যাচাই করা যায়নি।" if bn else "Source directory. Crop-specific storage guidance could not be verified.", "directory")


def resolve_crop(crop: str) -> str | None:
    return _CROP_IDS.get(_key(crop or ""))


def resolve_district(district: str) -> District | None:
    place = re.sub(r"(?:\s+(?:district|জেলা))?(?:\s*,\s*(?:bangladesh|বাংলাদেশ))?$", "", (district or "").strip(), flags=re.I)
    return _DISTRICTS.get(_key(place))


def collect_sources(topic: str, crop: str, district: str, locale: str) -> list[dict]:
    """Return documented facts and labelled directories; all links are publisher-owned."""
    bn = (locale or "").lower().startswith("bn")
    deadline = monotonic() + 7.0
    crop_id = resolve_crop(crop)
    d = resolve_district(district)
    if topic == "weather":
        return [_bulletin(d, crop_id, bn, deadline)]
    if topic == "calendar":
        return [_calendar(crop_id, d, bn, deadline)]
    if topic == "irrigation":
        reference = _source("এফএও সেচের সময় নির্ধারণ" if bn else "FAO irrigation scheduling",
                            "https://www.fao.org/4/w4367e/w4367e09.htm",
                            ("সাধারণ সেচ নির্দেশিকা। সেচের সময় নির্ধারণে মাটির আর্দ্রতা পরীক্ষা করুন এবং ফসল ও আবহাওয়ার তথ্য বিবেচনা করুন।" if bn else
                             "Irrigation reference. Assess soil moisture and account for the crop and weather when deciding when to irrigate."), "reference")
        return [_bulletin(d, crop_id, bn, deadline), reference]
    if topic == "market":
        return [_market(bn)]
    if topic == "health":
        return [_health(crop_id, bn, deadline)]
    if topic == "storage":
        return [_storage(crop_id, bn)]
    if topic == "briefing":
        return [_bulletin(d, crop_id, bn, deadline), _calendar(crop_id, d, bn, deadline), _market(bn)]
    return []
