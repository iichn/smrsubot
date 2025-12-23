from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from config import Buttons

def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text=Buttons.SCHEDULE)
    builder.button(text=Buttons.NOTIFICATIONS)
    builder.button(text=Buttons.LOGOUT)
    return builder.as_markup(resize_keyboard=True)

def schedule_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text=Buttons.TODAY, callback_data="schedule_today")
    builder.button(text=Buttons.TOMORROW, callback_data="schedule_tomorrow")
    builder.button(text=Buttons.CURRENT_WEEK, callback_data="schedule_current")
    builder.button(text=Buttons.NEXT_WEEK, callback_data="schedule_next")
    builder.adjust(2)
    return builder.as_markup()

def notifications_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text=Buttons.NOTIF_ENABLE, callback_data="notif_enable")
    builder.button(text=Buttons.NOTIF_DISABLE, callback_data="notif_disable")
    builder.button(text=Buttons.NOTIF_SETTINGS, callback_data="notif_settings")
    builder.adjust(2, 1)
    return builder.as_markup()