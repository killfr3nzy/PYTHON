"""Telegram bot entrypoint for the fines-appeal service.

Flow:
    /start -> bot asks for license plate
    user sends plate -> parser.lookup -> Claude/template letters per fine
    bot returns: summary message + .txt attachment per appealable fine
"""

from __future__ import annotations

import asyncio
import io
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BufferedInputFile, Message

from config import settings
from llm import build_appeal
from parser import LookupResult, lookup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Flow(StatesGroup):
    waiting_for_plate = State()


dp = Dispatcher(storage=MemoryStorage())


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.set_state(Flow.waiting_for_plate)
    await message.answer(
        "שלום! Я проверю ваши штрафы за 2 минуты.\n\n"
        "Отправьте номер вашего автомобиля (только цифры, например 12345678)."
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    mode = "Claude API" if settings.use_claude else "шаблоны"
    parser_mode = settings.parser_mode
    await message.answer(
        "Сервис автоматических апелляций по израильским штрафам.\n\n"
        f"Режим генератора писем: {mode}\n"
        f"Режим парсера: {parser_mode}\n\n"
        "/start — проверить штрафы по номеру машины\n"
        "/help — эта справка"
    )


@dp.message(Flow.waiting_for_plate, F.text)
async def handle_plate(message: Message, state: FSMContext) -> None:
    plate = message.text.strip()
    await message.answer("🔍 Проверяю штрафы, это займёт до минуты...")

    result = await asyncio.to_thread(lookup, plate)
    if result.error:
        await message.answer(f"❌ {result.error}")
        await state.clear()
        return
    if not result.fines:
        await message.answer("✅ Штрафов не найдено. Чисто!")
        await state.clear()
        return

    await _send_report(message, result)
    await state.clear()


async def _send_report(message: Message, result: LookupResult) -> None:
    header = (
        f"📋 Найдено штрафов: {len(result.fines)}\n"
        f"💰 Общая сумма: {result.total_amount} ₪\n\n"
        "Готовлю апелляционные письма..."
    )
    await message.answer(header)

    for idx, fine in enumerate(result.fines, start=1):
        analysis, letter = await asyncio.to_thread(build_appeal, fine)
        summary = (
            f"<b>Штраф {idx}/{len(result.fines)}</b>\n"
            f"№ {fine.fine_id} от {fine.issued_at.isoformat()}\n"
            f"{fine.violation}\n"
            f"📍 {fine.location}\n"
            f"💵 {fine.amount_ils} ₪ · {fine.source}\n\n"
            f"<b>Анализ:</b>\n• " + "\n• ".join(analysis.grounds) + "\n\n"
            f"<i>{analysis.risk_note}</i>"
        )
        await message.answer(summary, parse_mode="HTML")

        filename = f"appeal_{fine.fine_id}.txt"
        document = BufferedInputFile(letter.encode("utf-8"), filename=filename)
        await message.answer_document(
            document,
            caption="📄 Готовое письмо на иврите — скопируйте в форму подачи апелляции.",
        )

    await message.answer(
        "Оплатить полный отчёт можно переводом на Bit/PayBox.\n"
        "Стоимость: 49 ₪ за разовый отчёт или 99 ₪/мес за подписку с автопроверкой раз в 2 недели."
    )


async def main() -> None:
    if not settings.tg_bot_token:
        raise SystemExit("TG_BOT_TOKEN is not set. See config.py for details.")
    bot = Bot(token=settings.tg_bot_token)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
