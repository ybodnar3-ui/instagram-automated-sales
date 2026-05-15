import pytest
from unittest.mock import MagicMock
from models.message import Message, Direction
from models.conversation import Conversation
from models.stats import BotConfig


def make_config(**kwargs):
    config = MagicMock(spec=BotConfig)
    config.business_name = kwargs.get("business_name", "Beauty Studio")
    config.service_description = kwargs.get("service_description", "nail art services")
    config.price_info = kwargs.get("price_info", "from $50")
    config.objections_script = kwargs.get("objections_script", "We offer flexible payment")
    config.llm_model = "claude-haiku-3-5-20251001"
    return config


class TestBuildSystemPrompt:
    def test_contains_business_name(self):
        from services.llm import build_system_prompt
        config = make_config(business_name="Nail Queen Studio")
        prompt = build_system_prompt(config)
        assert "Nail Queen Studio" in prompt

    def test_contains_service_description(self):
        from services.llm import build_system_prompt
        config = make_config(service_description="premium nail art")
        prompt = build_system_prompt(config)
        assert "premium nail art" in prompt

    def test_prohibits_ai_disclosure(self):
        from services.llm import build_system_prompt
        config = make_config()
        prompt = build_system_prompt(config)
        assert "не представляйся AI або ботом" in prompt

    def test_contains_objections_script(self):
        from services.llm import build_system_prompt
        config = make_config(objections_script="Ми даємо гарантію повернення грошей")
        prompt = build_system_prompt(config)
        assert "Ми даємо гарантію повернення грошей" in prompt

    def test_contains_price_info(self):
        from services.llm import build_system_prompt
        config = make_config(price_info="$999 one-time")
        prompt = build_system_prompt(config)
        assert "$999 one-time" in prompt


class TestBuildMessages:
    def test_incoming_maps_to_user_role(self):
        from services.llm import build_messages
        msg = MagicMock(spec=Message)
        msg.direction = Direction.incoming
        msg.content = "Hello!"
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [msg]
        conv = MagicMock(spec=Conversation)
        conv.id = 1
        result = build_messages(conv, db)
        assert result == [{"role": "user", "content": "Hello!"}]

    def test_outgoing_maps_to_assistant_role(self):
        from services.llm import build_messages
        msg = MagicMock(spec=Message)
        msg.direction = Direction.outgoing
        msg.content = "Hi there!"
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [msg]
        conv = MagicMock(spec=Conversation)
        conv.id = 1
        result = build_messages(conv, db)
        assert result == [{"role": "assistant", "content": "Hi there!"}]

    def test_alternating_direction_order_preserved(self):
        from services.llm import build_messages
        m1 = MagicMock(spec=Message, direction=Direction.incoming, content="Q")
        m2 = MagicMock(spec=Message, direction=Direction.outgoing, content="A")
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [m1, m2]
        conv = MagicMock(spec=Conversation)
        conv.id = 1
        result = build_messages(conv, db)
        assert result[0] == {"role": "user", "content": "Q"}
        assert result[1] == {"role": "assistant", "content": "A"}

    def test_empty_conversation_returns_empty_list(self):
        from services.llm import build_messages
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        conv = MagicMock(spec=Conversation)
        conv.id = 1
        result = build_messages(conv, db)
        assert result == []
