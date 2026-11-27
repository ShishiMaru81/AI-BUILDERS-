"""Handle common conversation turns before calling a model or loading farm evidence."""

import re
import unicodedata

from .farmer_rag import _tokens


_SALAM = r"ass?alamu ala[iy]kum|asalamu ala[iy]kum|salam|আসসালামু আলাইকুম|আসসালামু আলায়কুম|সালাম"
_HELLO = r"hi+|hello+|hey+|good (?:morning|afternoon|evening)|namaskar|nomoskar|হাই|হ্যালো|নমস্কার|শুভ সকাল"
_GREETING = re.compile(rf"^(?P<salam>{_SALAM})\b|^(?P<hello>{_HELLO})\b")
_ARITHMETIC = re.compile(
    r"(?:what(?:'s| is)\s+|calculate\s+|solve\s+|evaluate\s+|compute\s+|please\s+|tell me\s+|koto\s+)*"
    r"[\d\s().,*+−%×÷^/=\-]+"
    r"(?:(?:plus|minus|times|divided by|যোগ|বিয়োগ|গুণ|ভাগ|আর)\s*[\d\s().,]+)*"
    r"(?:\s*(?:equal(?:s)?|কত|কতো|koto|please))?[!?.=\s]*"
)
_OFF_TOPIC = re.compile(
    r"\b(?:system prompt|developer instructions|api key|cricket (?:match|score)|football (?:match|score)|"
    r"stock market|bitcoin|python script|javascript code|capital of|"
    r"(?:write|tell) (?:me )?(?:a joke|a poem))\b|"
    r"সিস্টেম প্রম্পট|ক্রিকেটের স্কোর|ক্রিকেট ম্যাচ|কৌতুক বলো|কবিতা লেখ"
)
_OVERRIDE = re.compile(
    r"\b(?:ignore|disregard|override)\b.{0,65}\b(?:previous|instructions|rules|policy)\b|"
    r"(?:আগের|সব) নির্দেশনা (?:উপেক্ষা|ভুলে)"
)
_HARM = re.compile(
    r"\b(?:how (?:can|do|would) (?:i|we)|help me|steps to|how to)\s+"
    r"(?:(?:spread|disseminate)\b.{0,55}\b(?:disease|pathogens?|blight)\b|"
    r"(?:intentionally infect|sabotage)\b.{0,70}\b(?:crop|field|farm|plants?)\b)|"
    r"(?:ইচ্ছা করে|কীভাবে|কিভাবে).{0,35}(?:রোগ ছড়াব|ফসল নষ্ট করব)"
)
_FARM = re.compile(
    r"\b(?:agricultur\w*|agronom\w*|farm(?:er|ing|land|s)?|crops?|cultivat\w*|"
    r"soil|waterlog\w*|drainage|irrigat\w*|salinity|mulch\w*|compost\w*|"
    r"harvest\w*|transplant\w*|seed\w*|sowing|planting|nursery|fruit|vegetables?|"
    r"leaves|leaf|plants?|pest\w*|fungicide|pesticide|fertili[sz]\w*|"
    r"rice blast|agrodoctor|floodcrop|krishimarket|"
    r"upazila|mati|chash|foshol|poka|sech|pata[ry]?|bij|chara|bristi|brishti|lobonakto|"
    r"shobji|shossho|khet|gach|rog|shar|haor|ipm|awd)\b|"
    r"কৃষি|খামার|ফসল|পাত[াে]|বীজ|সেচ|চাষ|মাটি|পোকা|লবণাক্ত|বন্যা|বৃষ্ট|জলাবদ্ধ|আবহাও|"
    r"সংরক্ষণ|মালচ|কম্পোস্ট|বালাইনাশক|কীটনাশক|ফলন|চারা|রোপণ|বপন|নিষ্কাশন|হাওর|শাকসবজি|"
    r"(?<![\u0980-\u09ff])সার(?:ের|ে|টা)?(?![\u0980-\u09ff])"
)
_FARM_TASK = re.compile(
    r"\b(?:buyer|wholesale|farm.gate|crop price|bari|bamis|brri|open tasks?|my tasks|"
    r"advis[eo]r|extension officer|soil ph|rain|weather|forecast|monsoon|flood|cyclone|"
    r"what (?:should i check|do i do) (?:on my plot|today)|"
    r"what.{0,35}(?:show|say).{0,15}(?:photo|screening))\b|"
    r"^tasks[?.! ]*$|কর্মকর্তা|কল সেন্টার|কৃষি অফিস|আজকের কাজ|মহাজন|(?:ধান|ফসল|জমির) দাম|১৬১২৩|16123"
)
_FOLLOWUP = re.compile(
    r"^(?:(?:and |then |so |but )?(?:what (?:if|about|else|next)|"
    r"why|how (?:many|much|long|often|soon|certain)|is (?:that|it|this)|"
    r"can i|could it|should i|when|explain (?:this|that|the)|"
    r"compare (?:this|the)|does (?:that|this|it))\b|(?:আর কী|তারপর|এখন কী|এতে কি|কতদিন|কতটা|কেন|এটা কি|যদি))|"
    r"\b(?:last watered|yesterday|at root depth|the other photo|both photos|more plants)\b|"
    r"গতকাল|শেষ সেচ|শিকড়ের কাছে|আগের ছবি"
)
_MARKET_FOLLOWUP = re.compile(
    r"\d|\b(?:tk|bdt|taka|kg|kilo|sacks?|bags?|crates?|transport|handling)\b|৳|টাকা|কেজি|ভাড়|ভাড়"
)
_BANGLISH = re.compile(
    r"\b(?:amar|dhan|alu|pata|poka|sech|mati|chash|foshol|kobe|kokhon|keno|koto|korbo|korben|"
    r"bolun|gach|bhutta|vutta|peyaj|begun|morich|sorisha|shorisha|mosur|bristi|brishti|shukano)\b", re.I
)


def language_hint(question, locale):
    if re.search(r"\bin english\b|ইংরেজিতে", question, re.I):
        return "en"
    if (re.search(r"[\u0985-\u09b9\u09dc-\u09df]|\bin (?:bangla|bengali)\b", question, re.I)
            or len(_BANGLISH.findall(question)) >= 2):
        return "bn"
    return locale


def classify_local(question, *, has_crop, topic, recent_topic, has_case):
    """A local disposition, or 'farm'/'unknown' for the cloud classifier."""
    question = "".join(c for c in unicodedata.normalize("NFKC", question).casefold()
                       if unicodedata.category(c) != "Cf")
    words = " ".join(_tokens(question))
    if not words:
        return "clarify"
    if words in {"thanks", "thank you", "thank you so much", "dhonnobad", "ধন্যবাদ", "অনেক ধন্যবাদ"}:
        return "thanks"
    if words in {"bye", "goodbye", "see you", "বিদায়", "আবার দেখা হবে", "আল্লাহ হাফেজ"}:
        return "goodbye"
    if words in {"help", "what can you do", "how can you help", "who are you", "কী করতে পারো", "কীভাবে সাহায্য করতে পারবেন"}:
        return "help"
    greeting = _GREETING.match(question)
    if greeting:
        remainder = question[greeting.end():].lstrip(" ,.!?।-👋")
        if " ".join(_tokens(remainder)) in {"", "there", "farmer chat", "how are you", "কেমন আছেন"}:
            return "salam" if greeting.group("salam") else "greeting"
        question = remainder
    if (_ARITHMETIC.fullmatch(question.strip()) and not words.isdecimal()) or _OVERRIDE.search(question):
        return "outside"
    if _HARM.search(question):
        return "harm"
    if _OFF_TOPIC.search(question) and not (has_crop or _FARM.search(question)):
        return "outside"
    if (recent_topic or has_case) and not has_crop and _FOLLOWUP.search(question):
        return "followup"
    if (has_crop or _FARM.search(question) or _FARM_TASK.search(question)
            or (has_case and re.search(r"\b(?:photo|case|screening|result|check next)\b|ছবি|পরীক্ষা|ফলাফল|এরপর কী", question))):
        return "farm"
    if (recent_topic == "market" and _MARKET_FOLLOWUP.search(question)
            and not _OFF_TOPIC.search(question)):
        return "followup"
    if topic == "market" and _MARKET_FOLLOWUP.search(question):
        return "farm"
    return "unknown"


def local_reply(scope, lang):
    replies = {
        "greeting": ("Hello! How can I help with your farm today?", "হ্যালো! আজ আপনার খামারের কী নিয়ে সাহায্য করতে পারি?"),
        "salam": ("Wa alaikum assalam! How can I help with your farm?",
                  "ওয়ালাইকুম আসসালাম! আপনার খামারের কী নিয়ে সাহায্য করতে পারি?"),
        "thanks": ("You're welcome! Ask anytime about your crops or farm.",
                   "স্বাগতম! ফসল বা খামার নিয়ে যেকোনো সময় প্রশ্ন করুন।"),
        "goodbye": ("Take care! Come back whenever you have a farm question.",
                    "ভালো থাকবেন! কৃষি নিয়ে প্রশ্ন থাকলে আবার আসবেন।"),
        "help": ("I can help with crop symptoms, planting seasons, soil, irrigation, rain and flood preparation, "
                 "storage, and selling your harvest in Bangladesh. What are you growing?",
                 "বাংলাদেশের ফসলের লক্ষণ, চাষের মৌসুম, মাটি, সেচ, বৃষ্টি ও বন্যার প্রস্তুতি, সংরক্ষণ আর ফসল বিক্রি নিয়ে সাহায্য করতে পারি। কী চাষ করছেন?"),
        "outside": ("That question is outside crop farming. I can help with crop health, soil, rain, "
                    "storage or selling your harvest in Bangladesh.",
                    "এটি কৃষিবিষয়ক প্রশ্ন নয়। বাংলাদেশের ফসলের রোগবালাই, মাটি, বৃষ্টি, সংরক্ষণ বা ফসল বিক্রি নিয়ে সাহায্য করতে পারি।"),
        "harm": ("I can help you protect crops and reduce the spread of disease. Tell me the crop and the signs you're seeing.",
                 "ফসল রক্ষা ও রোগের বিস্তার কমাতে সাহায্য করতে পারি। ফসলের নাম আর কী লক্ষণ দেখছেন বলুন।"),
        "clarify": ("What would you like to know about your farm? Tell me the crop, district and what you're seeing or planning.",
                    "খামারের কী নিয়ে জানতে চান? ফসলের নাম, জেলা আর কী দেখছেন বা কী পরিকল্পনা করছেন বলুন।"),
    }
    if scope in replies:
        return {"text": replies[scope][lang == "bn"], "mode": "local", "sources": [], "actions": []}
