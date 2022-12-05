from aiogram.utils.markdown import hbold
from aiogram.dispatcher.filters import Text
from aiogram import Bot, Dispatcher, executor, types
from config import token
import json

bot = Bot(token=token, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)


@dp.message_handler(commands="start")
async def start(message: types.Message):
    start_buttons = ["Оглосите весь список пожайлуста!", "Последние 5 квартир"]
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(*start_buttons)
    await message.answer("Квартиры на сьём", reply_markup=keyboard)


@dp.message_handler(Text(equals="Оглосите весь список пожайлуста!"))
async def get_all_dirot(message: types.Message):
    with open("data/filtered_data.json", encoding="utf-8") as file:
        dirot_dict = json.load(file)

    for k, v in sorted(dirot_dict.items()):
        dirot = f"{v['add_date']}\n" \
                f"{v['address']}\n" \
                f"{hbold(v['price'])}\n" \
                f"{hbold(v['info'])}\n" \
                f"{v['dira_url']}\n"

        await message.answer(dirot)


@dp.message_handler(Text(equals="Последние 5 квартир"))
async def last_five_dirot(message: types.Message):
    with open("data/filtered_data.json", encoding="utf-8") as file:
        dirot_dict = json.load(file)

    for k, v in sorted(dirot_dict.items('price'))[-5:]:
        dirot = f"{v['add_date']}\n" \
                f"{v['address']}\n" \
                f"{hbold(v['price'])}\n" \
                f"{hbold(v['info'])}\n" \
                f"{v['dira_url']}\n"

        await message.answer(dirot)


if __name__ == '__main__':
    executor.start_polling(dp)
