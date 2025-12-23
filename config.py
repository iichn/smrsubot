from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

class Texts:
    START = "Привет! Я бот для работы с ЭИОС.\nВведите /login, чтобы авторизоваться."
    LOGIN_PROMPT = "Введите логин:"
    PASSWORD_PROMPT = "Введите пароль:"
    AUTH_SUCCESS = "Добро пожаловать, {name}!"
    AUTH_FAIL = "Ошибка авторизации.\n Введите /login и попробуйте еще раз."
    LOGOUT = "Вы успешно вышли из аккаунта.\nЧтобы войти снова, используйте команду /login"
    SCHEDULE_PROMPT = "Выберите период:"
    NOTIFICATIONS_PROMPT = "Управление рассылкой:"

class Buttons:
    SCHEDULE = "Расписание"
    NOTIFICATIONS = "Управление рассылкой"
    LOGOUT = "Выйти из аккаунта"
    TODAY = "Сегодня"
    TOMORROW = "Завтра"
    CURRENT_WEEK = "Текущая неделя"
    NEXT_WEEK = "Следующая неделя"
    NOTIF_ENABLE = "Включить"
    NOTIF_DISABLE = "Отключить"
    NOTIF_SETTINGS = "Настройки уведомлений"