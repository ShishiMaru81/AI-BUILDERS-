"""Rank vetted agricultural passages within the farmer's crop and location scope."""

from collections import Counter
from functools import lru_cache
import json
from math import log
from pathlib import Path
import unicodedata

from pydantic import BaseModel, HttpUrl

from . import farmer_rag_vectors
from .farmer_chat_sources import _CROPS, _DISTRICTS, resolve_crop, resolve_district


class PassageText(BaseModel, frozen=True):
    title: str
    text: str


class Guide(BaseModel, frozen=True):
    id: str
    topics: tuple[str, ...]
    crops: tuple[str, ...] = ()
    districts: tuple[str, ...] = ()
    stages: tuple[str, ...] = ()
    terms: tuple[str, ...]
    publisher: str
    url: HttpUrl
    en: PassageText
    bn: PassageText

    def source(self, language: str) -> dict:
        passage = self.bn if language == "bn" else self.en
        return {"label": f"{passage.title} · {self.publisher}", "detail": passage.text, "url": str(self.url),
                "status": "knowledge_reference", "publisher": self.publisher, "scope": {
                    "crops": [_CROPS[crop][0] for crop in self.crops], "districts": self.districts,
                    "stages": self.stages,
                }}


def _tokens(text: str) -> list[str]:
    # Bengali vowel signs are Unicode combining marks, which Python's \w would split off.
    normalized = unicodedata.normalize("NFKC", text.casefold())
    letters = "".join(char if unicodedata.category(char)[0] in "LMN" else " "
                      for char in normalized if unicodedata.category(char) != "Cf")
    return letters.split()


def _phrase(text: str) -> str:
    return " " + " ".join(_tokens(text)) + " "


@lru_cache(maxsize=1)
def _guides() -> tuple[Guide, ...]:
    raw = json.loads(Path(__file__).with_name("farmer_knowledge.json").read_text(encoding="utf-8"))
    return tuple(Guide.model_validate(value) for value in raw)


@lru_cache(maxsize=1)
def _lexical_index():
    guides = _guides()
    passages = tuple((guide.en.title + ". " + guide.en.text, guide.bn.title + ". " + guide.bn.text) for guide in guides)
    words = [Counter(_tokens(" ".join((*pair, *guide.terms)))) for guide, pair in zip(guides, passages)]
    frequency = Counter(term for entry in words for term in entry)
    return passages, words, frequency


_EXTRA_CROPS = {
    "tomatoes": "13", "tomato plant": "13", "টমেটোর": "13", "টমাটোর": "13", "tomato gach": "13",
    "potatoes": "52", "আলুর": "52", "alu": "52", "dhan": "76", "aman dhan": "74",
    "boro dhan": "75", "aus dhan": "7", "bhutta": "8", "vutta": "8", "begun": "15",
    "morich": "45", "peyaj": "46", "piyaj": "46", "sorisha": "44", "shorisha": "44",
    "mosur": "58", "mung bean": "85", "mungbean": "85", "green gram": "85", "মুগ": "85",
    "sweet potato": "sweet-potato", "মিষ্টি আলু": "sweet-potato",
}
_CROP_NAMES = sorted(((_phrase(term), key) for term, key in {
    **{name + suffix: crop_id for crop_id, names in _CROPS.items() for name in names
       for suffix in (("", "র", "ের", "ে", "তে") if any("\u0980" <= c <= "\u09ff" for c in name) else ("",))},
    **_EXTRA_CROPS,
}.items()), key=lambda entry: -len(entry[0]))
_DISTRICT_NAMES = tuple((_phrase(term), district.name) for district in sorted(set(_DISTRICTS.values()), key=lambda d: d.name)
                        for term in (district.name, *(district.bangla + suffix for suffix in ("", "ে", "তে", "র", "ের"))))
_DISTRICT_NAMES += tuple((_phrase(alias), place.name) for alias in
                         ("Chittagong", "Comilla", "Jessore", "Bogra", "Barisal", "Netrakona", "Jhalakati")
                         if (place := resolve_district(alias)))
_SEEDLING_TERMS = tuple(map(_phrase, ("nursery", "seedling", "seedlings", "seedbed", "বীজতলা", "চারা", "চারায়", "chara")))


def mentioned_crops(question: str) -> set[str]:
    text = _phrase(question)
    # Match longer names first so "sweet potato" and "Aman rice" keep their own scope.
    named = set()
    for phrase, crop in _CROP_NAMES:
        if phrase in text:
            named.add(crop)
            text = text.replace(phrase, " ")
    return named


def mentioned_districts(question: str) -> set[str]:
    text = _phrase(question)
    return {name for phrase, name in _DISTRICT_NAMES if phrase in text}


def retrieve(question: str, topic: str, crop: str, district: str, *, stage: str = "") -> list[Guide]:
    """Retrieve up to three supported passages. Semantic ranking keeps the same scope."""
    if topic in {"market", "handoff"}:
        return []
    text = _phrase(question)
    crops = mentioned_crops(question) or ({crop_id} if (crop_id := resolve_crop(crop)) else set())
    locations = mentioned_districts(question)
    if not locations and (place := resolve_district(district)):
        locations.add(place.name)
    norm_stage = "seedling" if any(term in text for term in _SEEDLING_TERMS) else stage.casefold().strip()
    query_terms = set(_tokens(question))
    passages, index, frequency = _lexical_index()
    guides = _guides()
    scores = {}
    for i, guide in enumerate(guides):
        if topic != "general" and topic not in guide.topics:
            continue
        if guide.crops and not crops.intersection(guide.crops):
            continue
        if guide.districts and (not locations or not locations.issubset(guide.districts)):
            continue
        if guide.stages and norm_stage not in guide.stages:
            continue
        matches = [_phrase(term).split() for term in guide.terms if _phrase(term) in text]
        if not matches:
            continue
        words = index[i]
        # Specific multiword phrases dominate ordinary word overlap across both languages.
        lexical = sum(log((1 + len(guides)) / (1 + frequency[word]))
                      for word in query_terms if word in words)
        scores[i] = 3 * max(map(len, matches)) + len(matches) + lexical
    if not scores:
        return []
    lexical_rank = sorted(scores, key=lambda i: (-scores[i], guides[i].id))
    # Keep weak generic matches from adding noise below a precise symptom or task match.
    candidates = [i for i in lexical_rank if scores[i] >= scores[lexical_rank[0]] * .52][:8]
    if len(candidates) > 1:
        semantic = farmer_rag_vectors.semantic_scores(question, passages, candidates)
        if semantic:
            rank = {i: n for n, i in enumerate(sorted(candidates, key=lambda i: -semantic[i]))}
            fused = {i: 2 / (4 + n) + 1 / (4 + rank[i]) for n, i in enumerate(candidates)}
            candidates.sort(key=lambda i: -fused[i])
    return [guides[i] for i in candidates[:3]]
