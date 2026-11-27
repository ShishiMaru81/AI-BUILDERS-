"""Checks retrieval scope, citation validation and the persisted chat response."""

import pytest

from app import farmer_chat as chat
from app import farmer_rag as rag
from tests.test_farmer_chat import client, send, session


@pytest.mark.parametrize(("language", "question", "topic", "expected"), [
    ("en", "What do the concentric rings on older tomato leaves suggest?", "health", "leaf-early-blight"),
    ("bn", "আলুর পাতার নিচে অনিয়মিত দাগ আর সাদা আবরণ দেখা যাচ্ছে।", "health", "leaf-late-blight"),
    ("bn", "Alu patar niche shada aboron keno?", "health", "leaf-late-blight"),
    ("en", "The bottom of my tomato is dark and sunken opposite the stem.", "health", "tomato-blossom-end"),
    ("bn", "কিছু পচা আলু পেলাম। সংরক্ষণের আগে কী করব?", "storage", "potato-tuber-sorting"),
    ("en", "What preparation helps drainage before heavy rain?", "weather", "rain-field-drainage"),
    ("bn", "ভেজা ধান সংরক্ষণের আগে কী করব?", "storage", "rice-drying-before-storage"),
    ("en", "How do I scout for rice blast in Naogaon?", "health", "rice-blast-scouting"),
    ("bn", "বোরো ধানের পাতাপোড়া হলে কী লক্ষণ দেখা যায়?", "health", "rice-bacterial-leaf-blight"),
    ("bn", "আমন ধানের খোলপোড়া কীভাবে বুঝব?", "health", "rice-sheath-blight"),
    ("bn", "Dhan e gach foring dekhle ki korbo?", "health", "rice-planthopper"),
    ("bn", "বোরো ধানে এডব্লিউডি কী?", "irrigation", "boro-awd-irrigation"),
    ("bn", "ধানের বীজ সংরক্ষণ কীভাবে করব?", "storage", "rice-seed-storage"),
    ("en", "How can I plan Boro rice with coastal salinity in Satkhira?", "general", "coastal-rice-salinity"),
    ("bn", "সুনামগঞ্জে হাওরের বোরো ধানে আগাম বন্যা এলে কী করব?", "weather", "haor-boro-flash-flood"),
    ("bn", "সার দেওয়ার আগে মাটি পরীক্ষা করাব কোথায়?", "general", "soil-test-srdi"),
    ("bn", "Bhutta poka, ki dekhbo?", "health", "maize-armyworm-scouting"),
    ("bn", "বেগুনে ছিদ্র আর ঢলে পড়া ডগা দেখছি।", "health", "brinjal-shoot-fruit-borer"),
    ("en", "What conditions favour wheat blast?", "health", "wheat-blast-flowering"),
    ("bn", "সরিষার পাতার দাগ কীভাবে যাচাই করব?", "health", "mustard-alternaria"),
    ("en", "Lentil leaves turning brown: is this Stemphylium?", "health", "lentil-stemphylium"),
    ("bn", "আমে কালো দাগ পড়েছে।", "health", "mango-anthracnose"),
    ("en", "What does chilli anthracnose look like?", "health", "chilli-anthracnose"),
    ("bn", "পেঁয়াজে বেগুনি দাগ দেখলে কী পরীক্ষা করব?", "health", "onion-purple-blotch"),
    ("bn", "পেঁয়াজ সংরক্ষণ করার আগে কীভাবে শুকাব?", "storage", "onion-curing-storage"),
    ("en", "How do I dry chilli after harvest?", "storage", "chilli-drying"),
    ("bn", "বরিশালে আমন পঞ্জিকা কোথায় পাব?", "calendar", "barishal-aman-calendar"),
    ("bn", "আউশ আমন বোরো ধানের মৌসুম কীভাবে বাছাই করব?", "calendar", "rice-season-selection"),
    ("en", "When to sow jute in Faridpur?", "calendar", "region-crop-calendar-index"),
])
def test_keyword_retrieval_matches_reviewed_passage(monkeypatch, language, question, topic, expected):
    monkeypatch.setattr(rag.farmer_rag_vectors, "semantic_scores", lambda *_: {})
    best, *_ = rag.retrieve(question, topic, "", "")
    assert best.id == expected
    source = best.source(language)
    assert source["status"] == "knowledge_reference"
    assert source["url"].startswith("https://")
    assert source["detail"] == getattr(best, language).text


def test_district_crop_and_stage_scope():
    question = "What is the potato planting calendar in Gazipur?"
    assert rag.retrieve(question, "calendar", "tomato", "Gazipur")[0].id == "dhaka-potato-stage-calendar"
    assert not rag.retrieve(question.replace("Gazipur", "Natore"), "calendar", "potato", "Gazipur")
    assert not rag.retrieve(question.replace("potato", "sweet potato"), "calendar", "potato", "Gazipur")
    assert not rag.retrieve("potato planting calendar", "calendar", "potato", "")
    assert not rag.retrieve("How do I find my account settings?", "general", "potato", "Gazipur")
    assert not rag.retrieve("When to check the Aman rice calendar in Cumilla?", "calendar", "Aman rice", "Barishal")
    assert not rag.retrieve("How do I scout a mustard disease called stemphylium?", "health", "lentil", "")
    assert not rag.retrieve("Is AWD suitable for my Aman rice?", "irrigation", "Boro rice", "")
    assert "tomato-nursery-drainage" in {
        guide.id for guide in rag.retrieve("tomato drainage", "weather", "tomato", "", stage="Seedling")
    }
    assert "tomato-nursery-drainage" not in {
        guide.id for guide in rag.retrieve("tomato drainage", "weather", "tomato", "", stage="Harvest")
    }


def test_semantic_reranks_eligible_passages_only(monkeypatch):
    candidates = []

    def rerank(question, passages, ids):
        candidates.extend(ids)
        return {index: float(index) for index in ids}

    monkeypatch.setattr(rag.farmer_rag_vectors, "semantic_scores", rerank)
    guides = rag.retrieve("Tomato leaves have gray center spots and concentric rings", "health", "", "")
    assert len(candidates) >= 2
    assert {guide.id for guide in guides} == {"leaf-early-blight", "tomato-septoria-spots"}


@pytest.fixture
def no_live_sources(monkeypatch):
    monkeypatch.setattr(chat, "collect_sources", lambda *args: [])


def test_rag_passages_and_publisher_link_persist(client, session, no_live_sources, monkeypatch):
    reply_text = "The rings are consistent with early blight. Check the oldest leaves for the same pattern."
    key = "guide:leaf-early-blight"

    def ask(system, data, tokens):
        if "evidence" not in data:
            return {"topic": "health", "language": "en"}
        assert system == chat.RAG_ANSWER
        assert "several rings" in data["evidence"][key]["detail"]
        return {"reply": reply_text, "citations": [key, "guide:unverified", key]}

    monkeypatch.setattr(chat, "groq_json", ask)
    response = send(client, "What could be causing concentric rings on older tomato leaves?", plot_id=session["plot_id"])
    assert response.status_code == 200, response.text
    thread = response.json()
    reply = thread["messages"][-1]
    assert reply["mode"] == "rag"
    assert reply["text"] == reply_text
    assert len(reply["sources"]) == 1
    assert "/early-blight-in-tomato-and-potato" in reply["sources"][0]["url"]
    assert client.get("/api/v1/farmer-chat/conversations/" + thread["conversation_id"]).json() == thread


@pytest.mark.parametrize("model_reply", [
    {},
    {"reply": "Made-up ungrounded reply.", "citations": ["guide:unverified"]},
    {"reply": "Apply fungicide.", "citations": ["guide:leaf-early-blight"]},
    {"reply": "Mix 2 g/L and apply to the leaves.", "citations": ["guide:leaf-early-blight"]},
])
def test_empty_unverified_or_unsafe_model_answers_use_reviewed_passage(no_live_sources, monkeypatch, model_reply):
    def ask(system, data, tokens):
        return model_reply if "evidence" in data else {}

    monkeypatch.setattr(chat, "groq_json", ask)
    reply, _ = chat.make_turn("Concentric rings on older tomato leaves?", "en", [], {}, {})
    assert reply["mode"] == "tool"
    assert "several rings" in reply["text"]
    assert len(reply["sources"]) == 1


def test_unsupported_storage_specification_reports_gap(monkeypatch):
    monkeypatch.setattr(chat, "groq_json", lambda *_: {})
    reply, _ = chat.make_turn("What precise temperature should I use for potato storage?", "en", [], {}, {})
    assert reply["mode"] == "tool"
    assert reply["text"].startswith("I could not verify that specific storage requirement")


def test_adviser_handoff_still_works_for_a_known_disease(no_live_sources, monkeypatch):
    monkeypatch.setattr(chat, "groq_json", lambda *_: {})
    reply, _ = chat.make_turn("What should I tell an officer about potato late blight?", "en", [], {}, {})
    assert reply["mode"] == "tool"
    assert {action["kind"] for action in reply["actions"]} == {"call", "handoff"}
