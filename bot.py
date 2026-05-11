"""Telegram bot entrypoint for the fines-appeal service.

Flow:
    /start -> bot asks for license plate
    user sends plate -> bot asks for Israeli ID (only in live mode)
    user sends ID    -> parser.lookup -> Claude/template letters per fine
    bot returns: summary message + .txt attachment per appealable fine

In mock mode (PARSER_MODE=mock) the ID step is skipped.
"""

from __future__ import annotations

import asyncio
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
    waiting_for_id = State()
    waiting_for_fine_number = State()


dp = Dispatcher(storage=MemoryStorage())


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Flow.waiting_for_plate)
    await message.answer(
        "שלום! Я проверю ваши штрафы и подготовлю апелляции.\n\n"
        "Отправьте номер вашего автомобиля (только цифры, например 12345678)."
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    llm = "Claude API" if settings.use_claude else "шаблоны"
    parts = [
        "Сервис автоматических апелляций по израильским штрафам.",
        "",
        f"Генератор писем: {llm}",
        f"Парсер: {settings.parser_mode}",
        f"Капча: {settings.captcha_provider}",
        "",
        "/start — проверить штрафы",
        "/help — эта справка",
    ]
    await message.answer("\n".join(parts))


@dp.message(Flow.waiting_for_plate, F.text)
async def handle_plate(message: Message, state: FSMContext) -> None:
    plate = message.text.strip()
    await state.update_data(plate=plate)

    if settings.parser_mode == "live":
        await state.set_state(Flow.waiting_for_id)
        await message.answer(
            "Теперь отправьте номер удостоверения личности (תעודת זהות) — "
            "9 цифр. Это нужно для запроса в gov.il. Данные не сохраняются."
        )
        return

    await _run_lookup_and_reply(message, plate=plate, israeli_id=None, fine_number=None)
    await state.clear()


@dp.message(Flow.waiting_for_id, F.text)
async def handle_id(message: Message, state: FSMContext) -> None:
    israeli_id = message.text.strip()
    await state.update_data(israeli_id=israeli_id)
    await state.set_state(Flow.waiting_for_fine_number)
    await message.answer(
        "И последнее — номер любого штрафа, который вы помните "
        "(из SMS, бумажного уведомления или предыдущего отчёта).\n\n"
        "Без него gov.il не отдаёт список — это защита приватности. "
        "Зная один штраф, мы найдём все остальные."
    )


@dp.message(Flow.waiting_for_fine_number, F.text)
async def handle_fine_number(message: Message, state: FSMContext) -> None:
    fine_number = message.text.strip()
    data = await state.get_data()
    plate = data.get("plate", "")
    israeli_id = data.get("israeli_id", "")
    await _run_lookup_and_reply(message, plate=plate, israeli_id=israeli_id, fine_number=fine_number)
    await state.clear()


async def _run_lookup_and_reply(
    message: Message,
    plate: str,
    israeli_id: str | None,
    fine_number: str | None,
) -> None:
    await message.answer("🔍 Проверяю штрафы, это займёт до минуты...")

    result = await asyncio.to_thread(lookup, plate, israeli_id, fine_number)
    if result.error:
        await message.answer(f"❌ {result.error}")
        return
    if not result.fines:
        await message.answer("✅ Штрафов не найдено. Чисто!")
        return

    await _send_report(message, result)


async def _send_report(message: Message, result: LookupResult) -> None:
    header_lines = [
        f"📋 Найдено штрафов: {len(result.fines)}",
        f"💰 Общая сумма: {result.total_amount} ₪",
    ]
    if result.fines:
        by_src = result.by_source
        header_lines.append("\nПо городам:")
        for src, fines in by_src.items():
            total = sum(f.amount_ils for f in fines)
            header_lines.append(f"  · {src}: {len(fines)} шт · {total} ₪")
    if result.warnings:
        header_lines.append("\n⚠️ Замечания:")
        for w in result.warnings:
            header_lines.append(f"  · {w}")
    header_lines.append("\nГотовлю апелляционные письма...")
    await message.answer("\n".join(header_lines))

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
