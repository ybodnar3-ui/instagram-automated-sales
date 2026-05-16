import logging
from datetime import datetime, timezone
from typing import Optional
import anthropic
from sqlalchemy.orm import Session
from config import settings
from models.conversation import Conversation
from models.message import Message, Direction
from models.stats import BotConfig

logger = logging.getLogger(__name__)

# Module-level singleton — avoids recreating HTTP connection pools on every call
_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


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
    if config is None:
        logger.error("conversation=%d has no BotConfig — cannot generate response", conversation.id)
        raise ValueError("BotConfig is required to generate a response")

    messages = build_messages(conversation, db)
    if not messages:
        logger.warning("conversation=%d has no messages — skipping LLM call", conversation.id)
        raise ValueError("No messages in conversation to respond to")

    system_prompt = build_system_prompt(config)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    logger.debug(
        "conversation=%d calling LLM model=%s messages=%d",
        conversation.id, config.llm_model, len(messages),
    )

    try:
        client = _get_client()
        response = client.messages.create(
            model=config.llm_model,
            max_tokens=500,
            system=f"{system_prompt}\n\nПоточна дата та час: {now}",
            messages=messages,
        )
    except anthropic.RateLimitError as exc:
        logger.error("Anthropic rate limit hit for conversation=%d: %s", conversation.id, exc)
        raise
    except anthropic.APIStatusError as exc:
        logger.error(
            "Anthropic API error conversation=%d status=%d: %s",
            conversation.id, exc.status_code, exc.message,
        )
        raise
    except anthropic.APIConnectionError as exc:
        logger.error("Anthropic connection error conversation=%d: %s", conversation.id, exc)
        raise

    if not response.content:
        logger.error("Anthropic returned empty content for conversation=%d", conversation.id)
        raise ValueError("Anthropic returned empty response content")

    text = response.content[0].text
    tokens = response.usage.input_tokens + response.usage.output_tokens
    logger.info(
        "conversation=%d LLM response generated tokens=%d model=%s",
        conversation.id, tokens, config.llm_model,
    )
    return text, tokens
