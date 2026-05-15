from datetime import datetime, timezone
import anthropic
from sqlalchemy.orm import Session
from config import settings
from models.conversation import Conversation
from models.message import Message, Direction
from models.stats import BotConfig

SYSTEM_PROMPT_TEMPLATE = """\
Ти — менеджер з продажів компанії {business_name}.
Твоя задача — відповідати на повідомлення потенційних клієнтів в Instagram і доводити їх до покупки {service_description}.

Ціна: {price_info}

Правила:
- Пиши коротко, живо, без офіційщини
- не представляйся AI або ботом ні за яких обставин
- Задавай уточнюючі питання, якщо клієнт не конкретизував запит
- При запереченнях використовуй: {objections_script}
- Максимум 2-3 речення за повідомлення
- Ніколи не надсилай прайс без попереднього діалогу"""


def build_system_prompt(config: BotConfig) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        business_name=config.business_name,
        service_description=config.service_description,
        price_info=config.price_info,
        objections_script=config.objections_script,
    )


def build_messages(conversation: Conversation, db: Session) -> list[dict]:
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.sent_at.asc())
        .limit(20)
        .all()
    )
    return [
        {"role": "user" if m.direction == Direction.incoming else "assistant", "content": m.content}
        for m in msgs
    ]


def generate_response(conversation: Conversation, config: BotConfig, db: Session) -> tuple[str, int]:
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    system_prompt = build_system_prompt(config)
    messages = build_messages(conversation, db)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    response = client.messages.create(
        model=config.llm_model,
        max_tokens=500,
        system=f"{system_prompt}\n\nПоточна дата та час: {now}",
        messages=messages,
    )
    text = response.content[0].text
    tokens = response.usage.input_tokens + response.usage.output_tokens
    return text, tokens
