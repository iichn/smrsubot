import asyncio
import logging
import sqlite3
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError

DB_PATH = "data/database.db"

from datetime import timedelta
from api import get_formatted_schedule_for_date, get_week_schedule

#from forum import check_forum_updates
from db import (
    init_db,
    get_users_with_forum_enabled,
    get_forum_settings,
    save_forum_settings,
    get_user_token,
    save_user_disciplines,
    get_user_disciplines,
    get_last_forum_message_id,
    update_last_forum_message_id,
    get_notification_settings,
)
from states import LoginState, ScheduleState
from handlers import (
    cmd_start, cmd_login, process_login, process_password,
    handle_schedule, handle_notification_settings, handle_logout,
    process_schedule_callback, process_notification_callback,
    process_custom_date, handle_forum_settings, process_polling_callback,
    get_valid_token, format_forum_message
)

API_TOKEN = "8063631715:AAFRHC9OAddFxsU0d_ha4hzKRzTyH09Td-k"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)  # Объект bot определён здесь
dp = Dispatcher(storage=MemoryStorage())

# Обновляем DB для поддержки логаута
def update_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        # Проверяем существование колонок и добавляем при необходимости
        c.execute("PRAGMA table_info(notifications)")
        columns = [column[1] for column in c.fetchall()]

        if 'frequency' not in columns:
            c.execute("ALTER TABLE notifications ADD COLUMN frequency TEXT")
        if 'schedule_type' not in columns:
            c.execute("ALTER TABLE notifications ADD COLUMN schedule_type TEXT")
        if 'preferred_day' not in columns:
            c.execute("ALTER TABLE notifications ADD COLUMN preferred_day INTEGER")
        if 'preferred_time' not in columns:
            c.execute("ALTER TABLE notifications ADD COLUMN preferred_time TEXT")

        conn.commit()

# Вспомогательные функции для корректной работы с корутинами
async def password_handler(message, state):
    await process_password(message, state, bot)


async def logout_handler(message: Message, state: FSMContext):
    await handle_logout(message, bot, state)


# Регистрация обработчиков
def register_handlers():
    # Команды
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_login, Command("login"))

    # Обработка входа
    dp.message.register(process_login, LoginState.waiting_for_login)
    dp.message.register(password_handler, LoginState.waiting_for_password)

    # Обработка основного меню
    dp.message.register(handle_schedule, F.text == "Расписание")
    dp.message.register(handle_notification_settings, F.text == "Управление рассылкой")
    dp.message.register(logout_handler, F.text == "Выйти из аккаунта")
    dp.message.register(cmd_login, F.text == "Войти в аккаунт")

    # Обработка inline кнопок
    dp.callback_query.register(process_schedule_callback, F.data.startswith("schedule_"))
    dp.callback_query.register(process_notification_callback, F.data.startswith("notif_"))
    dp.message.register(process_custom_date, ScheduleState.waiting_for_date)

    dp.message.register(handle_forum_settings, F.text == "Настройки уведомлений")
    dp.callback_query.register(process_polling_callback, F.data.startswith("forum_"))
    dp.callback_query.register(process_polling_callback, F.data.startswith("polling_"))

    dp.message.register(handle_forum_settings, F.text == "Интервал проверки")
    dp.callback_query.register(process_polling_callback, F.data.startswith("polling_"))

    dp.callback_query.register(process_polling_callback, F.data.startswith("polling_"))

async def check_notifications():
    while True:
        #logging.info(f"Выполняется проверка уведомлений")
        try:
            # Текущее время и день недели
            now = datetime.now()
            current_time = now.strftime("%H:%M")  # Формат HH:MM
            current_weekday = now.weekday()  # 0 = понедельник, 6 = воскресенье

            # Подключение к базе данных и поиск пользователей
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute(
                    """
                    SELECT 
                        n.telegram_id, 
                        n.frequency, 
                        n.schedule_type,
                        n.preferred_time,
                        n.preferred_day
                    FROM notifications n
                    WHERE n.schedule_enabled = 1
                    AND (
                        (n.frequency = 'daily' AND n.preferred_time = ?)
                        OR
                        (n.frequency = 'weekly' AND n.preferred_day = ? AND n.preferred_time = ?)
                    )
                    """, (current_time, current_weekday, current_time)
                )
                users = c.fetchall()

            # Обработка каждого пользователя
            for user in users:
                user_id = user[0]  # telegram_id
                frequency = user[1]  # 'daily' или 'weekly'
                schedule_type = user[2]  # Например, 'На завтра' или 'На сегодня'
                preferred_time = user[3]  # Время в формате HH:MM
                preferred_day = user[4]  # День недели (0-6) для weekly

                # Получение токена
                access_token = await get_valid_token(user_id)
                if not access_token:
                    logging.warning(f"Не удалось получить токен для пользователя {user_id}")
                    continue

                try:
                    # Определяем, какое расписание запрашивать
                    if frequency == 'weekly':
                        schedule = await get_week_schedule(access_token)
                    elif frequency == 'daily':
                        if schedule_type == 'На завтра':
                            date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
                        else:
                            date = now.strftime("%Y-%m-%d")
                        schedule = await get_formatted_schedule_for_date(access_token, date)

                    # Отправка расписания, если оно получено
                    if schedule:
                        await bot.send_message(user_id, schedule, parse_mode="HTML")
                        logging.info(f"Отправлено уведомление для {user_id} с типом {frequency}")
                    else:
                        logging.info(f"Расписание не найдено для {user_id} на {date if frequency == 'daily' else 'неделю'}")

                except TelegramAPIError as e:
                    logging.error(f"Ошибка Telegram API для {user_id}: {str(e)}")
                    if "Forbidden" in str(e):
                        logging.info(f"Пользователь {user_id} заблокировал бота")
                except Exception as e:
                    logging.error(f"Ошибка обработки для {user_id}: {str(e)}")
                    if "Invalid token" in str(e):
                        await handle_logout(user_id, bot, None)  # Разлогиниваем пользователя

        except Exception as e:
            logging.error(f"Ошибка в check_notifications: {str(e)}")

        # Пауза 60 секунд перед следующей проверкой
        logging.info(f"Проверка рассылки завершена")
        await asyncio.sleep(60)

async def check_forum_updates(telegram_id: int):
    settings = get_forum_settings(telegram_id)
    if not settings or not settings.get('forum_enabled', False):
        logging.info(f"Forum updates skipped for user {telegram_id}: notifications disabled or no settings")
        return

    token_data = get_user_token(telegram_id)
    if not token_data:
        logging.warning(f"No token found for user {telegram_id}")
        return

    access_token = await get_valid_token(telegram_id)
    if not access_token:
        logging.warning(f"Failed to get valid token for user {telegram_id}")
        return

    headers = {"Authorization": f"Bearer {access_token}"}

    async with aiohttp.ClientSession() as session:
        # Получаем дисциплины текущего семестра
        async with session.get("https://papi.mrsu.ru/v1/StudentSemester?selector=current", headers=headers) as resp:
            if resp.status == 401:
                logging.warning(f"Token invalid for user {telegram_id}, attempting to refresh")
                access_token = await get_valid_token(telegram_id)
                if not access_token:
                    logging.error(f"Failed to refresh token for user {telegram_id}")
                    return
                headers = {"Authorization": f"Bearer {access_token}"}
                async with session.get("https://papi.mrsu.ru/v1/StudentSemester?selector=current", headers=headers) as resp:
                    if resp.status != 200:
                        logging.error(f"Failed to fetch disciplines for user {telegram_id}: {resp.status}")
                        return
                    semester_data = await resp.json()
            elif resp.status != 200:
                logging.error(f"Failed to fetch disciplines for user {telegram_id}: {resp.status}")
                return
            else:
                semester_data = await resp.json()

            disciplines = semester_data.get('RecordBooks', [{}])[0].get('Disciplines', [])
            logging.info(f"User {telegram_id} has {len(disciplines)} disciplines")

        for discipline in disciplines:
            discipline_id = discipline.get('Id')
            unread_count = discipline.get('UnreadedMessageCount', 0)
            if unread_count == 0:
                logging.debug(f"No unread messages in discipline {discipline_id} for user {telegram_id}")
                continue

            # Получаем ID последнего прочитанного сообщения
            async with session.get(f"https://papi.mrsu.ru/v1/DisciplineReaded/{discipline_id}", headers=headers) as resp:
                if resp.status != 200:
                    logging.warning(f"Failed to fetch read status for discipline {discipline_id}: {resp.status}")
                    continue
                readed_data = await resp.json()
                last_read_id = readed_data.get('ReadedMessageId', 0)
                logging.debug(f"Last read message ID for discipline {discipline_id}: {last_read_id}")

            # Получаем последние сообщения дисциплины
            params = {
                "disciplineId": discipline_id,
                "count": 50
            }
            async with session.get("https://papi.mrsu.ru/v1/ForumMessage", params=params, headers=headers) as resp:
                if resp.status != 200:
                    logging.warning(f"Failed to fetch messages for discipline {discipline_id}: {resp.status}")
                    continue
                messages = await resp.json()
                logging.debug(f"Fetched {len(messages)} messages for discipline {discipline_id}")

                # Фильтруем непрочитанные сообщения
                unread_messages = [msg for msg in messages if msg['Id'] > last_read_id]
                if unread_messages:
                    logging.info(f"Found {len(unread_messages)} unread messages for user {telegram_id} in discipline {discipline_id}")

                # Отправляем уведомления
                for msg in unread_messages:
                    notification_text = format_forum_message(msg)
                    notification_text += "\n\n[Перейти к форуму](https://p.mrsu.ru/Learning/Student/Subjects?t=m)"
                    try:
                        if bot is None:
                            logging.error(f"Bot object is not defined for user {telegram_id}")
                            continue
                        await bot.send_message(telegram_id, notification_text, parse_mode="Markdown")
                        logging.info(f"Sent notification for message {msg['Id']} to user {telegram_id}")
                    except Exception as e:
                        logging.error(f"Failed to send message to user {telegram_id}: {str(e)}")

    # Обновляем время последней проверки
    save_forum_settings(telegram_id, last_polling_time=datetime.now().isoformat())

async def forum_polling_task():
    while True:
        users = get_users_with_forum_enabled()
        if not users:
            logging.info("No users with forum notifications enabled")
        else:
            logging.info(f"Checking forum updates for {len(users)} users: {users}")

        tasks = []
        for telegram_id in users:
            settings = get_forum_settings(telegram_id)
            if not settings:
                logging.warning(f"No forum settings for user {telegram_id}")
                continue
            last_polling_time = datetime.fromisoformat(settings['last_polling_time']) if settings['last_polling_time'] else datetime.min
            time_since_last_poll = (datetime.now() - last_polling_time).total_seconds()
            if time_since_last_poll >= settings['polling_interval'] * 60:
                logging.debug(f"Scheduling forum update check for user {telegram_id} (last poll: {settings['last_polling_time']})")
                tasks.append(check_forum_updates(telegram_id))
            else:
                logging.debug(f"Skipping user {telegram_id}: {int(settings['polling_interval'] * 60 - time_since_last_poll)} seconds until next poll")

        if tasks:
            await asyncio.gather(*tasks)
            logging.info(f"Completed forum update checks for {len(tasks)} users")
        await asyncio.sleep(60)

async def main():
    init_db()
    update_db()
    register_handlers()
    asyncio.create_task(check_notifications())
    asyncio.create_task(forum_polling_task())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())