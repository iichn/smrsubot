from aiogram import types, F
import logging
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from states import LoginState, ScheduleState, NotificationState
from aiogram import Bot, types
from typing import Optional, Dict, List, Any
from db import save_user_token, get_user_token, get_notification_settings, save_notification_settings, get_forum_settings, save_forum_settings
from notifications import (
    TEXTS, get_frequency_keyboard, get_daily_type_keyboard,
    get_weekdays_keyboard, get_time_keyboard, get_confirmation_keyboard,
    get_main_notif_keyboard, format_polling_interval, get_forum_settings_keyboard
)
from datetime import datetime, timedelta
from api import (
    get_token, get_user_info, get_formatted_schedule_for_date,
    get_week_schedule, get_current_date, get_tomorrow_date
)

class ForumSettings(StatesGroup):
    choosing_setting = State()
    choosing_interval = State()

class NotificationState(StatesGroup):
    selecting_frequency = State()
    selecting_daily_type = State()
    selecting_weekly_day = State()
    selecting_time = State()
    selecting_polling = State()
    confirmation = State()

async def cmd_start(message: Message):
    await message.answer("Привет! Я бот для работы с ЭИОС.\nВведите /login, чтобы авторизоваться.")

async def cmd_login(message: Message, state: FSMContext):
    await state.set_state(LoginState.waiting_for_login)
    login_prompt = await message.answer("Введите логин:")
    await state.update_data(login_prompt_id=login_prompt.message_id)

def format_forum_settings_text(settings: Dict) -> str:
    last_check = datetime.fromisoformat(settings['last_polling_time']).strftime("%d.%m.%Y %H:%M") if settings['last_polling_time'] else "Никогда"
    return (
        "Настройки уведомлений о сообщениях:\n\n"
        f"Статус: {'Включены' if settings['forum_enabled'] else 'Выключены'}\n"
        f"Интервал проверки: {format_polling_interval(settings['polling_interval'])}\n"
        f"Последняя проверка: {last_check}"
    )

def format_forum_message(message: dict) -> str:
    """Форматирует сообщение форума для отправки пользователю."""
    try:
        msg_date = datetime.fromisoformat(message['CreateDate'].replace('Z', '+00:00'))
        formatted_date = msg_date.strftime("%d.%m.%Y %H:%M")
        author = message.get('User', {}).get('FIO', 'Неизвестный автор')
        text = message.get('Text', 'Без текста')
        return (
            f"Непрочитанное сообщение на форуме ({discipline_title}):\n"
            f"{formatted_date}\n"
            f"{author}:\n"
            f"\"{text}\""
        )
    except Exception as e:
        return f"Ошибка форматирования сообщения: {str(e)}"

async def process_forum_callback(callback: CallbackQuery):
    action = callback.data.split("_")[1]
    user_id = callback.from_user.id
    if action == "toggle":
        current = get_notification_settings(user_id)
        new_status = not current['forum_enabled']
        save_notification_settings(user_id, forum_enabled=new_status)
        updated_settings = get_notification_settings(user_id)
        await callback.message.edit_text(
            format_forum_settings_text(updated_settings),
            reply_markup=get_forum_settings_keyboard(updated_settings)
        )
    elif action == "interval":
        await handle_forum_settings(callback.message, callback.from_user.id)
    await callback.answer()

async def process_login(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(login=message.text)
    password_prompt = await message.answer("Введите пароль:")
    await state.set_state(LoginState.waiting_for_password)
    await state.update_data(
        password_prompt_id=password_prompt.message_id,
        login_message_id=message.message_id
    )

async def process_login(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(login=message.text)
    password_prompt = await message.answer("Введите пароль:")
    await state.set_state(LoginState.waiting_for_password)
    await state.update_data(
        password_prompt_id=password_prompt.message_id,
        login_message_id=message.message_id
    )

async def process_password(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if 'login_prompt_id' in data:
        try:
            await bot.delete_message(message.chat.id, data['login_prompt_id'])
        except Exception as e:
            logging.error(f"Error deleting login prompt: {e}")
    data = await state.get_data()
    messages_to_delete = [
        data.get('password_prompt_id'),
        data.get('login_message_id'),
        message.message_id
    ]
    for msg_id in messages_to_delete:
        if msg_id:
            try:
                await bot.delete_message(message.chat.id, msg_id)
            except Exception as e:
                logging.error(f"Error deleting message {msg_id}: {e}")
    login = data.get('login')
    password = message.text
    progress_msg = await message.answer("Проверяем данные...")
    token_data = await get_token(login, password)
    if token_data and "access_token" in token_data:
        user_info = await get_user_info(token_data["access_token"])
        if user_info:
            save_user_token(message.from_user.id, login, token_data)
            await bot.delete_message(message.chat.id, progress_msg.message_id)
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Расписание")],
                    [KeyboardButton(text="Управление рассылкой")],
                    [KeyboardButton(text="Настройки уведомлений")],
                    [KeyboardButton(text="Выйти из аккаунта")]
                ],
                resize_keyboard=True
            )
            await message.answer(
                f"Добро пожаловать, {user_info.get('FIO', 'пользователь')}!",
                reply_markup=keyboard
            )
            await state.clear()
            return
    await message.answer("Ошибка авторизации. Проверьте данные и попробуйте снова через /login")
    await state.clear()
    try:
        await bot.delete_message(message.chat.id, progress_msg.message_id)
    except:
        pass

async def handle_schedule(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сегодня", callback_data="schedule_today"),
                InlineKeyboardButton(text="Завтра", callback_data="schedule_tomorrow")
            ],
            [
                InlineKeyboardButton(text="Текущая неделя", callback_data="schedule_current"),
                InlineKeyboardButton(text="Следующая неделя", callback_data="schedule_next")
            ],
            [
                InlineKeyboardButton(text="Ввести дату", callback_data="schedule_custom"),
            ]
        ]
    )
    await message.answer("Выберите период:", reply_markup=keyboard)

async def handle_notification_settings(message: Message):
    settings = get_notification_settings(message.from_user.id)
    has_settings = all([
        settings.get('frequency'),
        settings.get('preferred_time'),
        settings.get('schedule_type') if settings.get('frequency') == 'daily' else True
    ])
    time_value = settings.get('preferred_time', 'Не указано') or 'Не указано'
    formatted_time = time_value.replace(":00", "") if time_value else 'Не указано'
    status_text = TEXTS["settings_status_on"].format(
        frequency="Ежедневно" if settings.get('frequency') == 'daily' else "Еженедельно",
        schedule_type=settings.get('schedule_type', 'Не указано'),
        time=formatted_time
    ) if settings.get('schedule_enabled') and has_settings else TEXTS["settings_status_off"]
    await message.answer(
        TEXTS["current_settings"].format(status=status_text),
        reply_markup=get_main_notif_keyboard(
            has_active=settings.get('schedule_enabled', False) and has_settings,
            has_settings=has_settings
        )
    )

async def handle_logout(message: Message, bot: Bot, state: FSMContext):
    from db import logout_user
    logout_user(message.from_user.id)
    await state.clear()
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Войти в аккаунт")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        "Вы успешно вышли из аккаунта.",
        reply_markup=keyboard
    )

async def process_schedule_callback(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    action = callback.data.split('_')[1]
    user_id = callback.from_user.id
    loading_msg = None
    try:
        access_token = await get_valid_token(user_id)
        if not access_token:
            await callback.message.answer("Сессия истекла. Пожалуйста, войдите снова.")
            await callback.answer()
            return
        if action == "custom":
            await state.set_state(ScheduleState.waiting_for_date)
            prompt = await callback.message.answer("Введите дату в формате ДД.ММ.ГГГГ:")
            await state.update_data(date_prompt_id=prompt.message_id)
            await callback.answer()
            return
        loading_msg = await callback.message.answer("Загрузка расписания...")
        schedule = None
        if action == "today":
            date = get_current_date()
            schedule = await get_formatted_schedule_for_date(access_token, date)
        elif action == "tomorrow":
            date = get_tomorrow_date()
            schedule = await get_formatted_schedule_for_date(access_token, date)
        elif action == "current":
            schedule = await get_week_schedule(access_token, is_next_week=False)
        elif action == "next":
            schedule = await get_week_schedule(access_token, is_next_week=True)
        if schedule:
            if len(schedule) > 4000:
                parts = [schedule[i:i+4000] for i in range(0, len(schedule), 4000)]
                for part in parts:
                    await callback.message.answer(part, parse_mode="HTML", disable_web_page_preview=True)
            else:
                await callback.message.answer(schedule, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logging.error(f"Error processing schedule: {str(e)}")
        await callback.message.answer("Ошибка при получении расписания")
    finally:
        if loading_msg:
            try:
                await bot.delete_message(callback.message.chat.id, loading_msg.message_id)
            except Exception as e:
                logging.error(f"Ошибка удаления сообщения: {str(e)}")
        await callback.answer()

async def handle_forum_settings(message: Message):
    settings = get_forum_settings(message.from_user.id)
    if not settings:
        settings = {'forum_enabled': False, 'polling_interval': 15, 'last_polling_time': None}
        save_forum_settings(message.from_user.id, **settings)
    await message.answer(format_forum_settings_text(settings), reply_markup=get_forum_settings_keyboard(settings))

async def process_custom_date(message: Message, state: FSMContext):
    data = await state.get_data()
    prompt_id = data.get("date_prompt_id")
    try:
        await message.bot.delete_message(message.chat.id, prompt_id)
    except:
        pass
    try:
        await message.delete()
    except:
        pass
    text = message.text.strip()
    try:
        date_obj = datetime.strptime(text, "%d.%m.%Y")
        date = date_obj.strftime("%Y-%m-%d")
    except Exception:
        await message.answer("Неверный формат даты. Пожалуйста, введите в формате ДД.ММ.ГГГГ.")
        return
    user_id = message.from_user.id
    loading_msg = None
    try:
        access_token = await get_valid_token(user_id)
        if not access_token:
            await message.answer("Сессия истекла. Пожалуйста, войдите снова через /login")
            await state.clear()
            return
        loading_msg = await message.answer("Загрузка расписания...")
        schedule = await get_formatted_schedule_for_date(access_token, date)
        if schedule:
            await message.answer(schedule, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        await message.answer(f"Ошибка при получения расписания: {e}")
    finally:
        if loading_msg:
            try:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=loading_msg.message_id)
            except Exception as e:
                print(f"Ошибка при удалении сообщения о загрузке: {e}")

async def handle_forum_settings(message: Message):
    settings = get_forum_settings(message.from_user.id)
    if not settings:
        settings = {'forum_enabled': False, 'polling_interval': 60, 'last_polling_time': None}
        save_forum_settings(message.from_user.id, **settings)
    await message.answer(format_forum_settings_text(settings), reply_markup=get_forum_settings_keyboard(settings))

async def process_polling_callback(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    settings = get_forum_settings(telegram_id)
    if not settings:
        settings = {'forum_enabled': False, 'polling_interval': 60, 'last_polling_time': None}

    data = callback.data
    if data == "polling_toggle":
        settings['forum_enabled'] = not settings.get('forum_enabled', False)
        logging.info(f"User {telegram_id} toggled forum notifications to {settings['forum_enabled']}")
    elif data == "polling_interval":
        intervals = [1, 60, 360, 1440]
        current = settings['polling_interval']
        next_interval = intervals[(intervals.index(current) + 1) % len(intervals)] if current in intervals else 60
        settings['polling_interval'] = next_interval
        logging.info(f"User {telegram_id} changed polling interval to {next_interval}")

    save_forum_settings(telegram_id, **settings)
    await callback.message.edit_text(format_forum_settings_text(settings), reply_markup=get_forum_settings_keyboard(settings))
    await callback.answer()

def get_polling_keyboard(forum_enabled: bool, current_interval: int):
    intervals = {
        1: "1 минута",
        60: "1 час",
        360: "6 часов",
        1440: "1 сутки (18:00)"
    }
    buttons = [
        [
            InlineKeyboardButton(
                text="Включить" if not forum_enabled else "Выключить",
                callback_data="polling_toggle"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Интервал: {intervals[current_interval]}",
                callback_data="polling_cycle"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_next_check_time(interval: int) -> str:
    now = datetime.now()
    if interval == 1440:
        return (now.replace(hour=18, minute=0, second=0) + timedelta(days=1)).strftime("%H:%M %d.%m")
    return (now + timedelta(minutes=interval)).strftime("%H:%M %d.%m")

async def process_notification_callback(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split('_')[1]
    user_id = callback.from_user.id
    current_settings = get_notification_settings(user_id)
    if action == "toggle":
        new_status = not current_settings.get('schedule_enabled', False)
        save_notification_settings(
            telegram_id=user_id,
            schedule_enabled=new_status,
            frequency=current_settings.get('frequency'),
            schedule_type=current_settings.get('schedule_type'),
            preferred_day=current_settings.get('preferred_day'),
            preferred_time=current_settings.get('preferred_time')
        )
        updated_settings = get_notification_settings(user_id)
        has_settings = all([
            updated_settings.get('frequency'),
            updated_settings.get('preferred_time'),
            updated_settings.get('schedule_type') if updated_settings['frequency'] == 'daily' else True
        ])
        time_value = updated_settings.get('preferred_time', 'Не указано') or 'Не указано'
        formatted_time = time_value.replace(":00", "") if time_value else 'Не указано'
        status_text = TEXTS["settings_status_on"].format(
            frequency="Ежедневно" if updated_settings.get('frequency') == 'daily' else "Еженедельно",
            schedule_type=updated_settings.get('schedule_type', 'Не указано'),
            time=formatted_time
        ) if new_status and has_settings else TEXTS["settings_status_off"]
        await callback.message.edit_text(
            TEXTS["current_settings"].format(status=status_text),
            reply_markup=get_main_notif_keyboard(
                has_active=new_status and has_settings,
                has_settings=has_settings
            )
        )
        await callback.answer()
        return
    if action == "setup":
        await state.set_state(NotificationState.selecting_frequency)
        await callback.message.edit_text(TEXTS["select_frequency"], reply_markup=get_frequency_keyboard())
        await callback.answer()
        return
    if action == "cancel":
        await callback.message.edit_text("Настройка отменена")
        await state.clear()
        return
    if action == "back":
        current_state = await state.get_state()
        if current_state == NotificationState.selecting_daily_type:
            await state.set_state(NotificationState.selecting_frequency)
            await callback.message.edit_text(TEXTS["select_frequency"], reply_markup=get_frequency_keyboard())
        elif current_state == NotificationState.selecting_weekly_day:
            await state.set_state(NotificationState.selecting_frequency)
            await callback.message.edit_text(TEXTS["select_frequency"], reply_markup=get_frequency_keyboard())
        elif current_state == NotificationState.selecting_time:
            if current_settings.get('frequency') == 'daily':
                await state.set_state(NotificationState.selecting_daily_type)
                await callback.message.edit_text(TEXTS["select_daily_type"], reply_markup=get_daily_type_keyboard())
            else:
                await state.set_state(NotificationState.selecting_weekly_day)
                await callback.message.edit_text(TEXTS["select_weekly_day"], reply_markup=get_weekdays_keyboard())
        elif current_state == NotificationState.confirmation:
            await state.set_state(NotificationState.selecting_time)
            await callback.message.edit_text(TEXTS["select_time"], reply_markup=get_time_keyboard())
        await callback.answer()
        return
    if action == "freq":
        freq_type = callback.data.split('_')[2]
        await state.update_data(frequency=freq_type)
        if freq_type == "daily":
            await state.set_state(NotificationState.selecting_daily_type)
            await callback.message.edit_text(TEXTS["select_daily_type"], reply_markup=get_daily_type_keyboard())
        else:
            await state.set_state(NotificationState.selecting_weekly_day)
            await callback.message.edit_text(TEXTS["select_weekly_day"], reply_markup=get_weekdays_keyboard())
    elif action == "type":
        selected_type = callback.data.split('_')[2]
        type_mapping = {
            "today": "На сегодня",
            "tomorrow": "На завтра"
        }
        await state.update_data(schedule_type=type_mapping[selected_type])
        await state.set_state(NotificationState.selecting_time)
        await callback.message.edit_text(TEXTS["select_time"], reply_markup=get_time_keyboard())
    elif action == "day":
        day = int(callback.data.split('_')[2])
        await state.update_data(
            preferred_day=day,
            schedule_type=f"{['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'][day]}"
        )
        await state.set_state(NotificationState.selecting_time)
        await callback.message.edit_text(TEXTS["select_time"], reply_markup=get_time_keyboard())
    elif action == "time":
        selected_time = callback.data.split('_')[2]
        await state.update_data(preferred_time=selected_time)
        await state.set_state(NotificationState.confirmation)
        data = await state.get_data()
        summary = TEXTS["summary"].format(
            frequency="Ежедневно" if data['frequency'] == 'daily' else "Еженедельно",
            schedule_type=data.get('schedule_type', 'Не указано'),
            time=data['preferred_time']
        )
        await callback.message.edit_text(summary, reply_markup=get_confirmation_keyboard())
    elif action == "restart":
        await state.clear()
        await state.set_state(NotificationState.selecting_frequency)
        await callback.message.edit_text(
            TEXTS["select_frequency"],
            reply_markup=get_frequency_keyboard()
        )
        await callback.answer()
    elif action == "confirm":
        data = await state.get_data()
        required_fields = ['frequency', 'preferred_time']
        if not all(data.get(field) for field in required_fields):
            await callback.answer("Заполните все обязательные настройки!")
            return
        save_notification_settings(
            telegram_id=user_id,
            schedule_enabled=True,
            frequency=data['frequency'],
            schedule_type=data.get('schedule_type'),
            preferred_day=data.get('preferred_day'),
            preferred_time=data['preferred_time']
        )
        await callback.message.edit_text("Настройки успешно сохранены!")
        await state.clear()
        await callback.answer()

async def get_valid_token(telegram_id: int) -> Optional[str]:
    from db import get_user_token, update_user_tokens
    from api import refresh_access_token
    token_data = get_user_token(telegram_id)
    if not token_data:
        return None
    if token_data.get("needs_refresh"):
        new_tokens = await refresh_access_token(token_data["refresh_token"])
        if not new_tokens:
            return None
        await update_user_tokens(telegram_id, new_tokens)
        return new_tokens["access_token"]
    return token_data["access_token"]