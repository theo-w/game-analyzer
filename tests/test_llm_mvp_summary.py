import os
import pytest

from src.services.llm_mvp_summary import build_mvp_facts_for_llm

def test_build_mvp_facts_excludes_raw_comment_bodies():
    analysis = {
        "summary": {"total_comments": 2},
        "product_reports": [
            {
                "product": "730",
                "product_name": "CS2",
                "sample_size": 2,
                "positive_rate": 50.0,
                "risk_level": "medium",
                "top_negative_themes": [{"theme": "performance", "count": 1}],
                "recommendation": "fix crashes",
                "representative_negative_reviews": ["long raw comment text should not appear in facts"],
            }
        ],
        "ai_strategy": {
            "user_needs": [{"need": "fair matchmaking", "signal_count": 1}],
            "prioritized_actions": [{"priority": 1, "title": "anti-cheat"}],
            "peer_comparison": [],
            "opportunity_summary": "CS2 leads the sample.",
        },
    }
    facts = build_mvp_facts_for_llm(analysis)
    dumped = str(facts)
    assert "long raw comment" not in dumped
    assert facts["product_reports"][0]["product"] == "730"
    assert facts["validation_required"] is True

@pytest.mark.asyncio
async def test_summarize_returns_none_without_validation(monkeypatch):
    from src.services import llm_mvp_summary

    monkeypatch.setattr(llm_mvp_summary, "mvp_validation_passed", lambda: False)
    result = await llm_mvp_summary.summarize_mvp_with_llm({"product_reports": []})
    assert result is None
