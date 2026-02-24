import os
import json
import logging
import asyncio
from gigachat import GigaChat
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (WebAppInfo, ReplyKeyboardMarkup, KeyboardButton,
                           InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand)

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8462805267:AAGbaoUvOPO-o_Pd4ngRP1ZpLSGDu5Tl4MM"
CREDENTIALS = "MDE5YzgxZTYtNzBjNC03YTlhLWJhOTYtZmQ5ZDIwZDQwNjkwOmRhNWJhZDkwLTgxZGEtNGIzOC1iNTM5LWFiNmNmN2MzMzhiMA=="

ADMIN_CHAT_ID_CPPK = -5283408248  # Для МЦД
ADMIN_CHAT_ID_METRO = -5198371620  # Для Метро и МЦК

WEBAPP_URL = "https://n30n41ks.github.io/cppk-webapp/index.html?v=2"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# --- IN-MEMORY БАЗА ДАННЫХ (Для статистики) ---
user_stats = {}  # {user_id: count}
admin_stats = {
    'mcd_total': 0, 'mcd_resolved': 0,
    'metro_total': 0, 'metro_resolved': 0
}


class ReportState(StatesGroup):
    waiting_for_photo = State()


# --- ИИ ЛОГИКА (GigaChat) ---
async def formalize_with_priority(description: str) -> str:
    prompt = f"""Ты — строгий технический анализатор заявок метрополитена и МЦД.
Твоя задача — присвоить категорию и дать краткую, понятную выжимку проблемы без лишних слов.

КАТЕГОРИИ:
- [КРИТИЧЕСКИЙ]: угроза жизни, пожар, задымление, криминал.
- [СРЕДНИЙ]: поломка турникетов, эскалаторов, поездов, протечки.
- [НИЗКИЙ]: мусор, грязь, мелкие дефекты.
- [ОФФТОП]: бессмысленный набор букв ("рпа", "123"), приветствия ("привет"), спам, оскорбления бота.

ЖЕСТКИЕ ПРАВИЛА:
1. Если это ОФФТОП, верни строго: [ОФФТОП] : Пользователю не требуется помощь.
2. В остальных случаях переформулируй проблему кратко и профессионально.
3. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО придумывать названия станций, номера линий и несуществующие последствия.
4. Верни ТОЛЬКО одну строку по формату: [КАТЕГОРИЯ] : [Суть проблемы]

Текст пользователя: {description}"""

    try:
        loop = asyncio.get_event_loop()

        def get_giga():
            with GigaChat(credentials=CREDENTIALS, verify_ssl_certs=False) as giga:
                return giga.chat(prompt).choices[0].message.content.strip()

        result = await loop.run_in_executor(None, get_giga)

        if "\n" in result or "[" not in result:
            return f"[СРЕДНИЙ] : {description}"
        return result
    except Exception as e:
        logging.error(f"GigaChat Error: {e}")
        return f"[СРЕДНИЙ] : {description}"


def get_station_from_message(text: str) -> str:
    for line in text.split('\n'):
        if line.startswith("📍 Локация:"):
            return line.replace("📍 Локация:", "").strip()
    return "Неизвестная станция"


# --- КОМАНДЫ ПОЛЬЗОВАТЕЛЯ ---

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    markup = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🚨 Отправить рапорт", web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True
    )
    first_name = message.from_user.first_name or "Пассажир"
    text = (
        f"👋 <b>Добро пожаловать, {first_name}!</b>\n\n"
        "Вы подключились к единой системе транспортного мониторинга Москвы и области.\n\n"
        "Здесь вы можете быстро сообщить о любой проблеме на станциях <b>МЦД</b> или <b>Метрополитена</b>. "
        "Наша нейросеть мгновенно проанализирует заявку и передаст её профильному диспетчеру.\n\n"
        "👇 <i>Нажмите кнопку ниже, чтобы открыть форму рапорта.</i>"
    )
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "🆘 <b>Как пользоваться системой:</b>\n\n"
        "1️⃣ Нажмите кнопку «🚨 Отправить рапорт» внизу экрана.\n"
        "2️⃣ Выберите нужную вкладку: МЦД (ЦППК) или Метро (Дептранс).\n"
        "3️⃣ Введите название станции и кратко опишите инцидент.\n"
        "4️⃣ Нажмите «Отправить».\n"
        "5️⃣ При необходимости бот попросит прикрепить фото с места.\n\n"
        "Бот сам определит приоритет заявки и направит её бригаде."
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("about"))
async def cmd_about(message: types.Message):
    text = (
        "🎓 <b>О проекте</b>\n\n"
        "Единая интеллектуальная система транспортного мониторинга.\n"
        "Проект разработан студентом специальности ИСП в качестве современного IT-решения "
        "для автоматизации и оптимизации работы диспетчерских служб транспортного комплекса Москвы.\n\n"
        "🧠 <i>Под капотом: интеграция с нейросетью GigaChat, Telegram WebApp и умная маршрутизация.</i>\n\n"
        "Версия: 1.0.0 Release Candidate"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    user_id = message.from_user.id
    count = user_stats.get(user_id, 0)

    if count == 0:
        rank = "🌱 Наблюдатель"
    elif count < 3:
        rank = "🕵️‍♂️ Бдительный пассажир"
    elif count < 10:
        rank = "🛡 Страж подземелий"
    else:
        rank = "🦸‍♂️ Легенда Метрополитена"

    text = (
        "📊 <b>Ваша статистика:</b>\n\n"
        f"Отправлено рапортов: <b>{count}</b>\n"
        f"Ваш ранг: <b>{rank}</b>\n\n"
        "Спасибо, что помогаете делать транспорт лучше!"
    )
    await message.answer(text, parse_mode="HTML")


# --- ДАШБОРД ДЛЯ АДМИНОВ ---
@router.message(Command("dashboard"))
async def cmd_dashboard(message: types.Message):
    text = (
        "📈 <b>ОПЕРАТИВНАЯ СВОДКА</b>\n\n"
        "🚆 <b>ЦППК (МЦД):</b>\n"
        f"Поступило заявок: {admin_stats['mcd_total']}\n"
        f"Успешно закрыто: {admin_stats['mcd_resolved']}\n\n"
        "🚇 <b>Дептранс (Метро/МЦК):</b>\n"
        f"Поступило заявок: {admin_stats['metro_total']}\n"
        f"Успешно закрыто: {admin_stats['metro_resolved']}\n\n"
        "<i>*Данные с момента последнего запуска сервера</i>"
    )
    await message.answer(text, parse_mode="HTML")


# --- ПРИЕМ ЗАЯВОК (WEBAPP) ---
@router.message(F.content_type == types.ContentType.WEB_APP_DATA)
async def handle_webapp(message: types.Message, state: FSMContext):
    data = json.loads(message.web_app_data.data)
    user_desc = data.get('description', '')
    category = data.get('category', 'mcd')

    wait_msg = await message.answer("🔄 Нейросеть анализирует рапорт...")
    ai_desc = await formalize_with_priority(user_desc)
    await wait_msg.delete()

    await state.update_data(
        station=data.get('station'),
        description=user_desc,
        category=category,
        ai_desc=ai_desc
    )

    # Считаем статистику
    user_id = message.from_user.id
    user_stats[user_id] = user_stats.get(user_id, 0) + 1
    if category == 'metro':
        admin_stats['metro_total'] += 1
    else:
        admin_stats['mcd_total'] += 1

    await message.answer(
        f"✅ <b>ИИ проанализировал ситуацию:</b>\n{ai_desc}\n\nПришлите фото инцидента или напишите 'Готово'.",
        parse_mode="HTML")
    await state.set_state(ReportState.waiting_for_photo)


async def send_to_admin(user_id, username, data, photo_id=None):
    if data['category'] == 'metro':
        target_chat = ADMIN_CHAT_ID_METRO
        department_name = "ДЕПТРАНС (Метро/МЦК)"
    else:
        target_chat = ADMIN_CHAT_ID_CPPK
        department_name = "ЦППК (МЦД)"

    if "КРИТИЧЕСКИЙ" in data['ai_desc']:
        prefix = "🔥"
    elif "ОФФТОП" in data['ai_desc']:
        prefix = "🚫"
    else:
        prefix = "📋"

    report_text = f"""{prefix} <b>НОВЫЙ ИНЦИДЕНТ: {department_name}</b>
📍 <b>Локация:</b> {data['station']}
🤖 <b>Вердикт ИИ:</b> {data['ai_desc']}
👤 <b>От:</b> @{username or user_id}"""

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ В работу", callback_data=f"adm_work_{user_id}")]
    ])

    try:
        if photo_id:
            await bot.send_photo(target_chat, photo_id, caption=report_text, parse_mode="HTML", reply_markup=admin_kb)
        else:
            await bot.send_message(target_chat, report_text, parse_mode="HTML", reply_markup=admin_kb)
    except Exception as e:
        logging.error(f"Ошибка отправки в чат {target_chat}: {e}")


@router.message(ReportState.waiting_for_photo, F.photo)
async def proc_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await send_to_admin(message.from_user.id, message.from_user.username, data, message.photo[-1].file_id)
    await message.answer("🚀 Рапорт отправлен диспетчеру.")
    await state.clear()


@router.message(ReportState.waiting_for_photo, F.text)
async def proc_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await send_to_admin(message.from_user.id, message.from_user.username, data)
    await message.answer("✅ Отправлено без фото.")
    await state.clear()


# --- КНОПКИ ДИСПЕТЧЕРА ---
@router.callback_query(F.data.startswith("adm_"))
async def handle_adm(callback: CallbackQuery):
    _, action, user_id = callback.data.split("_")
    msg_text = callback.message.text or callback.message.caption or ""
    station = get_station_from_message(msg_text)

    if action == "work":
        await bot.send_message(user_id, f"⚙️ Ваша заявка ({station}) принята. Бригада уже в пути!")
        finish_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Завершить выполнение", callback_data=f"adm_done_{user_id}")]
        ])
        await callback.message.edit_reply_markup(reply_markup=finish_kb)
        await callback.answer("Заявка в работе")

    elif action == "done":
        admin_chat_id = callback.message.chat.id

        # Обновляем счетчик закрытых заявок
        if admin_chat_id == ADMIN_CHAT_ID_METRO:
            admin_stats['metro_resolved'] += 1
        elif admin_chat_id == ADMIN_CHAT_ID_CPPK:
            admin_stats['mcd_resolved'] += 1

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=str(i), callback_data=f"rate_{i}_{admin_chat_id}") for i in range(1, 6)]
        ])

        await bot.send_message(user_id, f"✅ Проблема на <b>{station}</b> устранена!\nОцените работу техслужбы:",
                               reply_markup=kb, parse_mode="HTML")
        await callback.message.edit_reply_markup(reply_markup=None)
        await bot.send_message(admin_chat_id, f"🏁 Задача по станции <b>{station}</b> закрыта.", parse_mode="HTML")
        await callback.answer("Готово!")


@router.callback_query(F.data.startswith("rate_"))
async def handle_rate(callback: CallbackQuery):
    parts = callback.data.split("_")
    score = parts[1]
    target_admin_chat = parts[2]

    msg_text = callback.message.text or ""
    station = "Неизвестно"
    if "Проблема на" in msg_text:
        station = msg_text.split("Проблема на ")[1].split(" устранена!")[0].strip()

    await callback.message.edit_text(f"🙏 Спасибо за отзыв! Ваша оценка: {score}/5")

    try:
        await bot.send_message(target_admin_chat, f"⭐️ <b>НОВАЯ ОЦЕНКА</b>\nСтанция: {station}\nБалл: {score}/5",
                               parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка отправки оценки: {e}")

    await callback.answer()


async def setup_bot_commands(bot: Bot):
    bot_commands = [
        BotCommand(command="/start", description="Запустить систему"),
        BotCommand(command="/help", description="Как отправить рапорт"),
        BotCommand(command="/stats", description="Мой профиль и статистика"),
        BotCommand(command="/dashboard", description="Оперативная сводка (для ДЦ)"),
        BotCommand(command="/about", description="Информация о проекте")
    ]
    await bot.set_my_commands(bot_commands)


async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await setup_bot_commands(bot)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())