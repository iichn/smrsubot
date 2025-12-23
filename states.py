from aiogram.fsm.state import State, StatesGroup

class LoginState(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()

class ScheduleState(StatesGroup):
    waiting_for_date = State()

class NotificationState(StatesGroup):
    selecting_frequency = State()
    selecting_daily_type = State()
    selecting_weekly_day = State()
    selecting_time = State()
    confirmation = State()