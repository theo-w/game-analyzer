"""Chat message sender classification for customer vs staff."""

import os
from src.support import LiveChat

def test_enrich_messages_staff_not_customer_when_same_viewer_name():
    """Admin viewing as chat owner must not label admin reply as customer."""
    messages = [
        {"username": "demo", "message": "有人么", "is_system": 0},
        {"username": "ai_assistant", "message": "AI reply", "is_system": 0},
        {"username": "admin", "message": "在的", "is_system": 0},
        {"username": "agent1", "message": "您好", "is_system": 0},
    ]
    enriched = LiveChat.enrich_messages(messages, chat_owner="demo")
    kinds = [m["sender_kind"] for m in enriched]
    assert kinds == ["customer", "ai", "staff", "staff"]

def test_enrich_messages_customer_on_owner_username_only():
    enriched = LiveChat.enrich_messages(
        [{"username": "demo", "message": "hi", "is_system": 0}],
        chat_owner="demo",
    )
    assert enriched[0]["sender_kind"] == "customer"

def test_demo_message_in_demo_chat_is_customer_not_staff():
    enriched = LiveChat.enrich_messages(
        [{"username": "demo", "message": "nihao", "is_system": 0}],
        chat_owner="demo",
    )
    assert enriched[0]["sender_kind"] == "customer"

def test_demo_message_in_agent1_chat_is_staff():
    enriched = LiveChat.enrich_messages(
        [{"username": "demo", "message": "nihao", "is_system": 0}],
        chat_owner="agent1",
    )
    assert enriched[0]["sender_kind"] == "staff"
