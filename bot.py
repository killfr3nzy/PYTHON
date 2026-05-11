"""Telegram bot entrypoint for the fines-appeal service.

Flow:
    Menu -> "🚗 Проверить штрафы" or /start
    bot asks plate -> (live mode) ID -> fine_number -> lookup
    bot returns detailed analysis per fine (text only)
    inline button "📄 Создать апелляционные письма (PDF)"
    on click -> generate PDFs and attach
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from config import settings
from llm import build_appeal
from parser import Fine, LookupResult, lookup
from pdf_appeal import render_appeal_pdf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants / menus
# ---------------------------------------------------------------------------

BTN_CHECK = "🚗 Проверить штрафы"
BTN_PRICING = "💰 Цены"
BTN_ABOUT = "ℹ️ О сервисе"
BTN_HELP = "❓ Помощь"

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_CHECK)],
        [KeyboardButton(text=BTN_PRICING), KeyboardButton(text=BTN_ABOUT)],
        [KeyboardButton(text=BTN_HELP)],
    ],
    resize_keyboard=True,
    persistent=True,
)

LETTERS_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="📄 Да, создать письма (PDF)", callback_data="gen_letters"),
            InlineKeyboardButton(text="Нет, спасибо", callback_data="skip_letters"),
        ]
    ]
)


# ---------------------------------------------------------------------------
# FSM
# ---------------------------------------------------------------------------

class Flow(StatesGroup):
    waiting_for_plate = State()
    waiting_for_id = State()
    waiting_for_fine_number = State()
    awaiting_letter_decision = State()


dp = Dispatcher(storage=MemoryStorage())


# ---------------------------------------------------------------------------
# Top-level handlers
# ---------------------------------------------------------------------------

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "שלום! 👋\n\n"
        "Я проверю ваши израильские штрафы по 9 муниципальным базам "
        "(Иерусалим, Тель-Авив, Хайфа, Беэр-Шева, Ришон, Нетания, "
        "Петах-Тиква, Холон + полиция) и подготовлю апелляционные письма "
        "на иврите.\n\n"
        "Нажмите «🚗 Проверить штрафы» в меню снизу или используйте /check.",
        reply_markup=MAIN_MENU,
    )


@dp.message(Command("help"))
@dp.message(F.text == BTN_HELP)
async def cmd_help(message: Message) -> None:
    llm = "Claude API" if settings.use_claude else "шаблоны"
    parts = [
        "<b>Как пользоваться</b>",
        "",
        "1. Нажмите «🚗 Проверить штрафы»",
        "2. Отправьте номер машины (8 цифр)",
        "3. В live-режиме — отправьте ID (תעודת זהות, 9 цифр)",
        "4. Отправьте номер любого вашего штрафа (из SMS/уведомления)",
        "5. Получите детальный анализ по каждому штрафу",
        "6. Решите, генерировать ли апелляционные письма в PDF",
        "",
        "<b>Команды</b>",
        "/start — главное меню",
        "/check — начать проверку",
        "/cancel — прервать текущий запрос",
        "",
        f"<b>Режим</b>: парсер {settings.parser_mode}, LLM {llm}",
    ]
    await message.answer("\n".join(parts), parse_mode="HTML", reply_markup=MAIN_MENU)


@dp.message(F.text == BTN_PRICING)
async def show_pricing(message: Message) -> None:
    text = (
        "<b>💰 Цены</b>\n\n"
        "• <b>49 ₪</b> — разовая проверка + апелляционные письма по всем найденным штрафам\n"
        "• <b>99 ₪/мес</b> — подписка: автопроверка раз в 2 недели + неограниченные письма\n"
        "• <b>199 ₪</b> — VIP-пакет: проверка + письма + ручная проверка юристом перед подачей\n\n"
        "Оплата: Bit, PayBox, банковский перевод.\n"
        "Возврат: если бот не нашёл ни одного штрафа — 100% возврат."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=MAIN_MENU)


@dp.message(F.text == BTN_ABOUT)
async def show_about(message: Message) -> None:
    text = (
        "<b>ℹ️ О сервисе</b>\n\n"
        "Автоматизирую процесс обжалования штрафов в Израиле:\n"
        "• Параллельная проверка по 9 источникам\n"
        "• Юридический анализ оснований для апелляции\n"
        "• Готовые письма на иврите (Claude AI)\n"
        "• Подача через стандартные муниципальные формы\n\n"
        "<b>Что я НЕ делаю:</b>\n"
        "• Не даю официальных юридических консультаций\n"
        "• Не сохраняю ваш ID/номер машины после генерации\n"
        "• Не гарантирую отмену штрафа — решение за муниципалитетом\n\n"
        "Все письма проверяйте перед подачей."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=MAIN_MENU)


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено. Главное меню снизу.", reply_markup=MAIN_MENU)


@dp.message(Command("check"))
@dp.message(F.text == BTN_CHECK)
async def start_check(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Flow.waiting_for_plate)
    await message.answer(
        "Отправьте номер вашего автомобиля (только цифры, например 12345678)."
    )


# ---------------------------------------------------------------------------
# Lookup pipeline
# ---------------------------------------------------------------------------

@dp.message(Flow.waiting_for_plate, F.text)
async def handle_plate(message: Message, state: FSMContext) -> None:
    plate = message.text.strip()
    await state.update_data(plate=plate)

    if settings.parser_mode == "live":
        await state.set_state(Flow.waiting_for_id)
        await message.answer(
            "Теперь отправьте номер удостоверения личности (תעודת זהות) — "
            "9 цифр. Это нужно для запроса в муниципальные базы. "
            "Данные не сохраняются после ответа."
        )
        return

    await _run_lookup_and_reply(message, state, plate=plate, israeli_id=None, fine_number=None)


@dp.message(Flow.waiting_for_id, F.text)
async def handle_id(message: Message, state: FSMContext) -> None:
    israeli_id = message.text.strip()
    await state.update_data(israeli_id=israeli_id)
    await state.set_state(Flow.waiting_for_fine_number)
    await message.answer(
        "И последнее — номер любого штрафа, который вы помните "
        "(из SMS, бумажного уведомления или прошлого отчёта).\n\n"
        "Без него gov.il не отдаёт список — это защита приватности. "
        "Зная один штраф, мы найдём все остальные."
    )


@dp.message(Flow.waiting_for_fine_number, F.text)
async def handle_fine_number(message: Message, state: FSMContext) -> None:
    fine_number = message.text.strip()
    data = await state.get_data()
    await _run_lookup_and_reply(
        message,
        state,
        plate=data.get("plate", ""),
        israeli_id=data.get("israeli_id", ""),
        fine_number=fine_number,
    )


async def _run_lookup_and_reply(
    message: Message,
    state: FSMContext,
    plate: str,
    israeli_id: Optional[str],
    fine_number: Optional[str],
) -> None:
    await message.answer("🔍 Проверяю штрафы во всех источниках, это займёт до минуты...")

    result = await asyncio.to_thread(lookup, plate, israeli_id, fine_number)
    if result.error:
        await message.answer(f"❌ {result.error}", reply_markup=MAIN_MENU)
        await state.clear()
        return
    if not result.fines:
        msg = "✅ Штрафов не найдено. Чисто!"
        if result.warnings:
            msg += "\n\nЗамечания:\n" + "\n".join(f"• {w}" for w in result.warnings)
        await message.answer(msg, reply_markup=MAIN_MENU)
        await state.clear()
        return

    await _send_detailed_analysis(message, result)

    # Stash fines + applicant for the inline-callback step.
    await state.update_data(
        fines=[f.to_dict() for f in result.fines],
        applicant=plate[-4:],
    )
    await state.set_state(Flow.awaiting_letter_decision)
    await message.answer(
        "Подготовить апелляционные письма в PDF (на иврите, готовые к подаче)?",
        reply_markup=LETTERS_KB,
    )


async def _send_detailed_analysis(message: Message, result: LookupResult) -> None:
    # Import here to avoid circular import with templates -> parser.
    from templates import analyse

    by_src = result.by_source
    header = [
        "📋 <b>Результаты проверки</b>",
        f"Найдено штрафов: <b>{len(result.fines)}</b>",
        f"Общая сумма: <b>{result.total_amount} ₪</b>",
        "",
        "<b>По городам:</b>",
    ]
    for src, fines in by_src.items():
        total = sum(f.amount_ils for f in fines)
        header.append(f"  · {src}: {len(fines)} шт · {total} ₪")
    if result.warnings:
        header.append("")
        header.append("<i>⚠️ Замечания по источникам:</i>")
        for w in result.warnings:
            header.append(f"  · {w}")

    await message.answer("\n".join(header), parse_mode="HTML")

    total_estimated_savings = 0
    for idx, fine in enumerate(result.fines, start=1):
        analysis = await asyncio.to_thread(analyse, fine)
        total_estimated_savings += analysis.estimated_savings_ils

        block = [
            f"<b>━━━ Штраф {idx}/{len(result.fines)} ━━━</b>",
            f"<b>№:</b> {fine.fine_id}",
            f"<b>Дата:</b> {fine.issued_at.isoformat()} ({fine.days_old} дн. назад)",
            f"<b>Орган:</b> {fine.source}",
            f"<b>Локация:</b> {fine.location}",
            f"<b>Нарушение:</b> {fine.violation}",
            f"<b>Сумма:</b> {fine.amount_ils} ₪",
            f"<b>Статус:</b> {fine.status or '—'}",
            "",
            f"<b>🎯 Вероятность отмены:</b> {analysis.success_probability} ({analysis.success_score}/100)",
            f"<b>💵 Ожидаемая выгода:</b> {analysis.estimated_savings_ils} ₪",
            f"<b>📅 Дедлайн:</b> {analysis.deadline}",
            "",
            "<b>Основания для апелляции:</b>",
        ]
        for g in analysis.grounds:
            block.append(f"  • {g}")
        block.append("")
        block.append("<b>Что делать:</b>")
        for a in analysis.recommended_actions:
            block.append(f"  ▸ {a}")
        if analysis.evidence_to_request:
            block.append("")
            block.append("<b>Какие доказательства запросить у органа:</b>")
            for e in analysis.evidence_to_request:
                block.append(f"  • {e}")
        block.append("")
        block.append(f"<i>{analysis.risk_note}</i>")

        await message.answer("\n".join(block), parse_mode="HTML")

    summary = (
        f"\n<b>💡 Итог по портфелю</b>\n"
        f"При успешной апелляции вы потенциально сэкономите "
        f"<b>~{total_estimated_savings} ₪</b> из {result.total_amount} ₪."
    )
    await message.answer(summary, parse_mode="HTML")


# ---------------------------------------------------------------------------
# Inline callbacks — letter generation
# ---------------------------------------------------------------------------

@dp.callback_query(F.data == "gen_letters", Flow.awaiting_letter_decision)
async def cb_gen_letters(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer("📝 Генерирую письма на иврите через Claude AI...")

    data = await state.get_data()
    fine_dicts = data.get("fines", [])
    if not fine_dicts:
        await cb.message.answer("Сессия истекла, начните заново через /check.", reply_markup=MAIN_MENU)
        await state.clear()
        return

    for idx, fine_dict in enumerate(fine_dicts, start=1):
        fine = _fine_from_dict(fine_dict)
        analysis, letter = await asyncio.to_thread(build_appeal, fine)
        pdf_bytes = await asyncio.to_thread(render_appeal_pdf, fine, letter)

        filename = f"appeal_{fine.fine_id}.pdf"
        document = BufferedInputFile(pdf_bytes, filename=filename)
        await cb.message.answer_document(
            document,
            caption=(
                f"📄 <b>Штраф {idx}/{len(fine_dicts)}</b> · {fine.amount_ils} ₪\n"
                f"Готовое письмо на иврите. Приложите к форме подачи апелляции "
                f"на сайте муниципалитета."
            ),
            parse_mode="HTML",
        )

    await cb.message.answer(
        "✅ Все письма готовы.\n\n"
        "<b>Что дальше:</b>\n"
        "1. Откройте сайт нужного муниципалитета (раздел «הגשת ערעור»).\n"
        "2. Приложите PDF и отправьте.\n"
        "3. Сохраните номер обращения — он понадобится для отслеживания статуса.\n\n"
        "Удачи! 🤞",
        parse_mode="HTML",
        reply_markup=MAIN_MENU,
    )
    await state.clear()


@dp.callback_query(F.data == "skip_letters", Flow.awaiting_letter_decision)
async def cb_skip_letters(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer("Понял, письма не создаём")
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        "Хорошо, письма не создаю. Если передумаете — нажмите «🚗 Проверить штрафы» ещё раз.",
        reply_markup=MAIN_MENU,
    )
    await state.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fine_from_dict(d: dict) -> Fine:
    import datetime as dt
    return Fine(
        fine_id=d["fine_id"],
        issued_at=dt.date.fromisoformat(d["issued_at"]),
        location=d["location"],
        violation=d["violation"],
        amount_ils=d["amount_ils"],
        status=d.get("status", ""),
        source=d["source"],
        photo_url=d.get("photo_url"),
        notes=d.get("notes", ""),
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main() -> None:
    if not settings.tg_bot_token:
        raise SystemExit("TG_BOT_TOKEN is not set. See config.py for details.")
    bot = Bot(token=settings.tg_bot_token)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
