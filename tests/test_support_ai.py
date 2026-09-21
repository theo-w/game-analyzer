"""Support chatbot keyword and LLM helper tests."""
import os

from src.support import AIChatbot

def test_capability_question_not_default_template():
    bot = AIChatbot()
    bot.load_knowledge_base()
    reply = bot.generate_response("你可以做什么", [])
    assert "数据看板" in reply
    assert "工单系统提交详细信息" not in reply
