"""Source-backed treatment navigation for photo screening and Farmer Chat."""

import re
import unicodedata


DAE_REGISTER = 'https://dae.gov.bd/sites/default/files/files/dae.portal.gov.bd/page/8a812db0_3544_4105_b066_df78074d3efb/2021-09-23-04-05-2d9b86a410f22be263f2f8a69ce8a4b0.pdf'
DAE_DIRECTORY = 'https://prism.dae.gov.bd/pesticide-list'
EARLY_GUIDE = 'https://extension.umn.edu/agriculture/specialty-crops/vegetable-farming/disease-management/early-blight-in-tomato-and-potato'
LATE_GUIDE = 'https://extension.umn.edu/agriculture/specialty-crops/vegetable-farming/disease-management/late-blight'
VIRUS_GUIDE = 'https://extension.umn.edu/agriculture/specialty-crops/vegetable-farming/disease-management/tomato-viruses'
TOMATO_DISORDERS = 'https://extension.umn.edu/garden-and-home/yard-and-garden/gardening-in-minnesota/yard-and-garden-problems/tomato-disorders'
STORAGE_GUIDE = 'https://www.fao.org/4/s8270e/S8270E07.htm'

RIDOMIL = {'name': 'Ridomil Gold MZ 68 WG', 'ingredient': 'Metalaxyl-M + mancozeb', 'registration': 'AP-1075'}
REVUS = {'name': 'Revus 250 SC', 'ingredient': 'Mandipropamid', 'registration': 'AP-2534'}
REGISTRY_EXAMPLES = {
    ('tomato', 'early'): (RIDOMIL,),
    ('tomato', 'late'): (RIDOMIL,),
    ('potato', 'late'): (REVUS,),
}
BLIGHTS = {
    'early': ('early blight', 'early blight alternaria', 'early blight alternaria solani', 'alternaria blight', 'আগাম ধসা', 'আগাম ধ্বসা'),
    'late': ('late blight', 'late blight phytophthora infestans', 'নাবি ধসা', 'নাবী ধসা', 'নাবি ধ্বসা', 'নাবী ধ্বসা', 'লেট ব্লাইট'),
}
VIRAL = re.compile(r'\b(?:virus|viral|mosaic|potato leafroll|potato leaf roll|yellow leaf curl)\b|ভাইরাস|মোজাইক')
TREATMENT = re.compile(
    r'\b(?:pesticides?|fungicides?|insecticides?|medicin(?:e|es)|treat(?:ment|ments)?|spray(?:ing)?|ridomil|revus|oshudh|oushodh)\b'
    r'|ওষুধ|ঔষধ|প্রতিকার|স্প্রে|ছত্রাকনাশক|বালাইনাশক|কীটনাশক'
)
DOSAGE = re.compile(
    r'\b(?:dos(?:e|age)|dilut\w*|mix(?:ing)?|spray rate|how (?:much|often)|how many (?:ml|litres?|liters?|grams?)|per (?:acre|litre|liter))\b'
    r'|\d\s*(?:mg|ml|grams?|litres?|liters?)\b|মেশা|মাত্রা|ডোজ|প্রতি লিটার|কত মিলি|কত গ্রাম'
)
NON_CROP = re.compile(r'\b(?:fever|headache|my child|my dog|swallowed|poisoning)\b|জ্বর|মাথাব্যথা|বিষক্রিয়া')
HARVESTED = re.compile(r'\b(?:harvested|after harvest|post harvest|rotten (?:potatoes?|tomatoes?)|in storage)\b|তোলা ফসল|পচা আলু|পচা টমেটো')


def _normalize(value):
    return ' '.join(re.sub(r'[_()–—-]', ' ', unicodedata.normalize('NFKC', str(value or '')).casefold()).split())


def _blight_name(condition):
    name = _normalize(condition).strip(' .')
    name = re.sub(r'^(?:possible |suspected |tomato |potato |সম্ভাব্য |টমেটোর |আলুর )+', '', name)
    name = name.removesuffix(' রোগ')
    return next((key for key, labels in BLIGHTS.items() if name in map(_normalize, labels)), None)


def _mentions_blight(text, label):
    label = _normalize(label)
    suffix = r'(?:র|য়|তে)?' if re.search(r'[\u0980-\u09ff]', label) else ''
    return re.search(r'(?<![\w\u0980-\u09ff])' + re.escape(label) + suffix + r'(?![\w\u0980-\u09ff])', text)


def _source(label, url):
    return {'label': label, 'url': url}


def _card(status, crop, locale, summary, steps=(), sources=(), products=(), condition=None):
    bn = locale == 'bn'
    directory = _source('ডিএই বালাইনাশকের তালিকা' if bn else 'DAE pesticide directory', DAE_DIRECTORY)
    return {
        'status': status, 'crop': crop, 'condition': condition,
        'summary': summary[bn], 'steps': [step[bn] for step in steps],
        'sources': [*sources, *([directory] if status in ('registry_reference', 'field_management', 'label') else [])],
        'products': list(products),
    }


def _blight_card(crop, condition, locale, from_photo=False):
    bn = locale == 'bn'
    products = REGISTRY_EXAMPLES.get((crop, condition), ())
    disease = ('early blight' if condition == 'early' else 'late blight', 'আগাম ধসা' if condition == 'early' else 'নাবি ধসা')
    guide = EARLY_GUIDE if condition == 'early' else LATE_GUIDE
    fields = (_source('মাঠ ব্যবস্থাপনার নির্দেশিকা' if bn else 'Field management reference', guide),)
    if products:
        fields += (_source('ডিএই নিবন্ধন তালিকা · ৮১তম পিটিএসি' if bn else 'DAE register · 81st PTAC', DAE_REGISTER),)
    if from_photo:
        summary = (f'The photo suggests {disease[0]}. Ask a local agricultural extension officer to confirm it before choosing a treatment.',
                   f'ছবিতে {disease[1]}র সম্ভাবনা দেখা যাচ্ছে। প্রতিকার বাছার আগে স্থানীয় কৃষি কর্মকর্তার মাধ্যমে লক্ষণ মিলিয়ে নিন।')
    else:
        summary = (f'These options apply when {disease[0]} is confirmed for {crop}.',
                   f'{"টমেটো" if crop == "tomato" else "আলু"}তে {disease[1]} নিশ্চিত হলে এই তথ্য প্রযোজ্য।')
    steps = [
        ('Check several plants and water at soil level so the leaves stay dry.',
         'কয়েকটি গাছ পরীক্ষা করুন এবং পাতা শুকনো রাখতে মাটির কাছে পানি দিন।'),
    ]
    if products:
        steps.append(('Show the registration number to your extension officer. Verify the current Bangladesh label for the crop, disease and waiting period before harvest.',
                      'নিবন্ধন নম্বরটি কৃষি কর্মকর্তাকে দেখান। বর্তমান বাংলাদেশি লেবেলে ফসল, রোগ ও ফসল তোলার আগের অপেক্ষার সময় মিলিয়ে নিন।'))
    else:
        steps.append(('Ask the extension officer to check the current DAE list for a fungus-control product labeled for this crop and disease.',
                      'এই ফসল ও রোগের জন্য ডিএইর বর্তমান তালিকায় অনুমোদিত ছত্রাকনাশক কৃষি কর্মকর্তার মাধ্যমে যাচাই করুন।'))
    return _card('registry_reference' if products else 'field_management', crop, locale, summary, steps,
                 fields, products, condition)


def _storage_card(crop, locale):
    return _card('storage', crop, locale,
                 ('For harvested produce, sort the affected items before deciding how to handle the batch.',
                  'তোলা ফসলে ক্ষতিগ্রস্ত ফল বা কন্দ আগে আলাদা করুন, তারপর চালানটি কীভাবে রাখবেন ঠিক করুন।'),
                 [('Check the remaining items for similar damage and keep sound produce separate from the affected lot.',
                   'অন্য ফল বা কন্দে একই ক্ষতি আছে কি না দেখুন এবং ভালো ফসল আলাদা রাখুন।')],
                 [_source('FAO', STORAGE_GUIDE)])


def guidance_for_screening(result, locale):
    crop = _normalize(result.get('crop'))
    assessment = result.get('assessment') or {}
    classification = result.get('classification') or {}
    raw = str(classification.get('top_label') or '')
    label_crop, separator, local_condition = raw.partition('___')
    part = assessment.get('part')
    if part == 'produce' or (result.get('model') or {}).get('model_id') == 'agrodoctor-research-produce':
        return _storage_card(crop, locale)
    if assessment.get('outcome') == 'no_visible_damage' or (classification.get('abstained') is False and _normalize(local_condition) == 'healthy'):
        return _card('monitor', crop, locale,
                     ('No visible finding currently supports a crop protection treatment. Keep checking the crop.',
                      'বর্তমান ছবিতে বালাইনাশক ব্যবহারের পক্ষে স্পষ্ট লক্ষণ নেই। ফসল পর্যবেক্ষণ চালিয়ে যান।'))
    supported = (classification.get('abstained') is False and not result.get('quality_flags')
                 and not (result.get('meta') or {}).get('is_simulated'))
    if assessment:
        supported = (supported and part == 'leaf' and assessment.get('outcome') == 'possible_condition'
                     and assessment.get('crop_match') == 'match' and bool(assessment.get('distinguishing_sign')))
        condition = assessment.get('condition')
    else:
        supported = supported and bool(separator) and _normalize(label_crop) == crop
        condition = local_condition
    condition = _normalize(condition)
    if supported and crop in ('potato', 'tomato'):
        if key := _blight_name(condition):
            return _blight_card(crop, key, locale, from_photo=True)
        if VIRAL.search(condition):
            return _card('nonchemical', crop, locale,
                         ('This pattern could be consistent with a virus. A fungicide cannot cure a plant virus.',
                          'লক্ষণ ভাইরাসের সঙ্গে মিলতে পারে। ছত্রাকনাশক দিয়ে গাছের ভাইরাস সারানো যায় না।'),
                         [('Mark the affected plants and ask an extension officer to identify the cause and advise on spread prevention.',
                           'আক্রান্ত গাছ চিহ্নিত করুন। কারণ ও ছড়ানো কমানোর উপায় জানতে কৃষি কর্মকর্তার সাহায্য নিন।')],
                         [_source('Plant virus reference', VIRUS_GUIDE)])
    return _card('uncertain', crop, locale,
                 ('There is not enough crop and disease evidence here to identify a treatment option.',
                  'প্রতিকারের বিকল্প বাছতে ফসল ও রোগের নির্ভরযোগ্য তথ্য এখনো যথেষ্ট নয়।'),
                 [('Show clear photos of the affected part and the whole plant to your local agricultural extension officer.',
                   'আক্রান্ত অংশ ও পুরো গাছের পরিষ্কার ছবি স্থানীয় কৃষি কর্মকর্তাকে দেখান।')])


def guidance_by_language(result):
    return {lang: guidance_for_screening(result, lang) for lang in ('en', 'bn')}


def chat_treatment(question, locale, crops, saved_guidance, continuing):
    """Handle product questions locally so generated text cannot invent a product or a dose."""
    text = _normalize(question)
    if NON_CROP.search(text):
        return None
    asks_treatment = TREATMENT.search(text)
    dose = DOSAGE.search(text)
    if not (asks_treatment or (continuing and dose)):
        return None
    if not (crops or saved_guidance or continuing or re.search(r'pesticide|fungicide|insecticide|বালাইনাশক|ছত্রাকনাশক|কীটনাশক', text)):
        return None
    crop = next(iter(crops)) if len(crops) == 1 else ''
    if dose:
        return _card('label', crop, locale,
                     ('Check the exact product’s current label with a local agricultural extension officer for the approved use, protective equipment and harvest waiting period.',
                      'অনুমোদিত ব্যবহার, সুরক্ষা সরঞ্জাম ও ফসল তোলার অপেক্ষার সময় জানতে নির্দিষ্ট পণ্যের বর্তমান লেবেল কৃষি কর্মকর্তার সঙ্গে মিলিয়ে নিন।'))
    if HARVESTED.search(text):
        return _storage_card(crop, locale)
    hits = {key for key, labels in BLIGHTS.items() if any(_mentions_blight(text, label) for label in labels)}
    ambiguous = re.search(
        r'\b(?:early|late)\s*(?:and|or|[&/])\s*(?:early|late)\s+blight\b'
        r'|(?:আগাম|নাবি|নাবী)\s*(?:বা|ও|এবং|/)\s*(?:আগাম|নাবি|নাবী)\s+ধ[্ব]?সা',
        text,
    )
    if saved_guidance:
        if ((not crops or crops == {saved_guidance['crop']}) and not ambiguous
                and (not hits or not saved_guidance['condition'] or hits == {saved_guidance['condition']})):
            return saved_guidance
        return _card('uncertain', crop, locale,
                     ('The saved screening and the condition or crop in this question do not match. Ask about the saved crop or review a matching case.',
                      'সংরক্ষিত পরীক্ষা ও এই প্রশ্নের ফসল বা রোগ মেলেনি। সংরক্ষিত ফসল নিয়ে প্রশ্ন করুন অথবা মেলে এমন পরীক্ষা খুলুন।'))
    if crop == 'tomato' and 'blossom end rot' in text:
        return _card('nonchemical', crop, locale,
                     ('Blossom-end rot is a growing disorder. Keep soil moisture even while the fruit develops.',
                      'ব্লসম-এন্ড রট ফলের বৃদ্ধিজনিত সমস্যা। ফল বড় হওয়ার সময় মাটির আর্দ্রতা সমান রাখুন।'),
                     sources=[_source('Tomato disorders reference', TOMATO_DISORDERS)])
    if crop in ('potato', 'tomato') and len(hits) == 1 and not ambiguous:
        return _blight_card(crop, next(iter(hits)), locale)
    return _card('uncertain', crop, locale,
                 ('What crop and confirmed condition are you treating? Share the result or ask an agricultural extension officer to confirm the cause.',
                  'কোন ফসল ও কোন নিশ্চিত সমস্যা নিয়ে জানতে চান? পরীক্ষার ফল দিন বা কৃষি কর্মকর্তার মাধ্যমে কারণ নিশ্চিত করুন।'))
