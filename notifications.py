from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

TEXTS = {
    "setup_start": "Настройка уведомлений:",
    "select_frequency": "Выберите частоту получения расписания:",
    "select_daily_type": "Какое расписание вы хотите получать?",
    "daily_types": {
        "today": "На сегодня",
        "tomorrow": "На завтра"
    },
    "weekly_types": {
        "monday": "Понедельник",
        "tuesday": "Вторник",
        "wednesday": "Среда",
        "thursday": "Четверг",
        "friday": "Пятница",
        "saturday": "Суббота",
        "sunday": "Воскресенье"
    },
    "select_weekly_day": "Выберите день для еженедельной рассылки:",
    "select_time": "Выберите время для рассылки:",
    "summary": "Итоговые настройки:\n\nЧастота: {frequency}\nТип: {schedule_type}\nВремя: {time}:00",
    "notif_off": "Уведомления успешно отключены",
    "current_settings": "Текущие настройки рассылки:\n{status}",
    "settings_status_on": "Включена\nЧастота: {frequency}\nТип: {schedule_type}\nВремя: {time}:00",
    "settings_status_off": "Выключена",
    "polling_header": "Выберите интервал проверки сообщений:",
    "current_polling": (
        "Текущие настройки проверки форума:\n"
        "Статус: {status}\n"
        "Интервал: {interval}\n"
        "Последняя проверка: {last_check}"
    ),
    "polling_updated": "Интервал проверки обновлен на {interval}!"
}

def format_forum_message(msg: dict) -> str:
    """Форматирует сообщение форума для уведомления"""
    try:
        date = datetime.fromisoformat(msg['CreateDate'].replace('Z', '')).strftime("%d.%m.%Y %H:%M")
        author = msg.get('User', {}).get('FIO', 'Неизвестный автор')
        text = msg.get('Text', 'Без текста')
        return (
            f"Непрочитанное сообщение на форуме ({discipline_title}):\n"
            f"{formatted_date}\n"
            f"{author}:\n"
            f"\"{text}\""
        )
    except Exception as e:
        return f"Ошибка форматирования сообщения: {str(e)}"

def format_forum_settings_text(settings: dict) -> str:
    """Форматирует настройки форума для отображения"""
    status = "Включены" if settings['forum_enabled'] else "Выключены"
    interval = format_polling_interval(settings['polling_interval'])
    last_check = (
        datetime.fromisoformat(settings['last_polling_time']).strftime("%d.%m.%Y %H:%M")
        if settings['last_polling_time']
        else "Никогда"
    )
    return TEXTS["current_polling"].format(status, interval, last_check)

def get_forum_settings_keyboard(settings: dict):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'Выключить' if settings['forum_enabled'] else 'Включить'}",
                    callback_data="polling_toggle"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Интервал: {format_polling_interval(settings['polling_interval'])}",
                    callback_data="polling_interval"
                )
            ]
        ]
    )

def format_polling_interval(interval: int) -> str:
    intervals = {
        1: "1 минута",
        60: "1 час",
        360: "6 часов",
        1440: "1 сутки (в 18:00)"
    }
    return intervals.get(interval, f"{interval} минут")

def get_main_notif_keyboard(has_active: bool, has_settings: bool):
    buttons = [[InlineKeyboardButton(
        text="Настроить уведомления",
        callback_data="notif_setup"
    )]]
    buttons.append([InlineKeyboardButton(
        text="Отключить уведомления" if has_active else "Включить уведомления",
        callback_data="notif_toggle"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_frequency_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Раз в день", callback_data="notif_freq_daily")],
        [InlineKeyboardButton(text="Раз в неделю", callback_data="notif_freq_weekly")],
        [InlineKeyboardButton(text="Отменить", callback_data="notif_cancel")]
    ])

def get_daily_type_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="На сегодня", callback_data="notif_type_today")],
        [InlineKeyboardButton(text="На завтра", callback_data="notif_type_tomorrow")],
        [InlineKeyboardButton(text="Назад", callback_data="notif_back_freq")]
    ])

def get_weekdays_keyboard():
    days = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=day, callback_data=f"notif_day_{i}")]
        for i, day in enumerate(days)
    ] + [[InlineKeyboardButton(text="Назад", callback_data="notif_back_freq")]])

def get_time_keyboard():
    times = []
    for hour in range(6, 24):
        for minute in [0, 30]:
            if hour == 23 and minute == 30:
                break
            times.append(f"{hour:02d}:{minute:02d}")
    keyboard = []
    row = []
    for i, time in enumerate(times):
        row.append(InlineKeyboardButton(text=time, callback_data=f"notif_time_{time}"))
        if (i + 1) % 4 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.extend([
        [InlineKeyboardButton(text="Назад", callback_data="notif_back_type")],
        [InlineKeyboardButton(text="Отменить", callback_data="notif_cancel")]
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_confirmation_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сохранить", callback_data="notif_confirm")],
        [InlineKeyboardButton(text="Настроить заново", callback_data="notif_restart")],
        [InlineKeyboardButton(text="Отменить", callback_data="notif_cancel")]
    ])