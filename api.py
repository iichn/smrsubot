import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

CLIENT_ID = 8
CLIENT_SECRET = "qweasd"
TOKEN_URL = "https://p.mrsu.ru/OAuth/Token"
USER_INFO_URL = "https://papi.mrsu.ru/v1/User"
TIMETABLE_URL = "https://papi.mrsu.ru/v1/StudentTimeTable"


# ---------- Data Models ----------
class ScheduleData:
    def __init__(self, raw_data: List[Dict]):
        self.groups = [GroupSchedule(data) for data in raw_data]


class GroupSchedule:
    def __init__(self, data: Dict):
        self.group_name = data.get("Group", "")
        self.faculty = data.get("FacultyName", "")
        self.lessons = [Lesson(lesson) for lesson in data.get("TimeTable", {}).get("Lessons", [])]


class Lesson:
    def __init__(self, data: Dict):
        self.number = data.get("Number", 0)
        self.subgroup_count = data.get("SubgroupCount", 0)
        self.disciplines = [Discipline(d) for d in data.get("Disciplines", [])]


class Discipline:
    def __init__(self, data: Dict):
        self.title = data.get("Title", "Нет названия")
        self.lesson_type = data.get("LessonType", 0)
        self.remote = data.get("Remote", False)
        self.teacher = Teacher(data.get("Teacher", {}))
        self.auditorium = Auditorium(data.get("Auditorium", {}))
        self.subgroup = data.get("SubgroupNumber", 0)


class Teacher:
    def __init__(self, data: Dict):
        self.name = data.get("FIO", "Нет преподавателя")


class Auditorium:
    def __init__(self, data: Dict):
        self.number = data.get("Number", "Нет аудитории")
        self.campus = data.get("CampusTitle", "")


# ---------- Formatters ----------
class ScheduleFormatter:
    DATE_FORMAT = "%d.%m.%Y"
    TIME_FORMAT = "%H:%M"
    EMPTY_SCHEDULE = "Нет занятий на этот день"

    LESSON_TIMES = {
        1: "8:00–9:30",
        2: "9:45–11:15",
        3: "11:35–13:05",
        4: "13:20–14:50",
        5: "15:00–16:30",
        6: "16:40–18:10",
        7: "18:15–19:45",
        8: "19:45–21:20",
    }

    WEEKDAYS = {
        0: "понедельник",
        1: "вторник",
        2: "среду",
        3: "четверг",
        4: "пятницу",
        5: "субботу",
        6: "воскресенье"
    }

    LESSON_TYPES = {
        0: "Лекция",
        1: "Практика",
        5: "Лабораторная",
        3: "Экзамен",
        4: "Консультация",
        2: "Зачет",
        6: "Другое"
    }

    # Formatting templates
    TEMPLATES = {
        # now includes both weekday and date
        "day_header": "Расписание на <b>{weekday}, {date}</b>:",
        "lesson_header": "\nПара №{number} <i>({time})</i>",
        "subgroup": "<u>Подгруппа: {number}</u>",
        "discipline": "<b>{title}</b> ({type})",
        "teacher": "Преподаватель: {name}",
        "auditorium": "Аудитория: {room} (к. {campus})",
        "remote": "Дистанционно",
    }

    def format_date(self, date_str: str) -> str:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        return date.strftime(self.DATE_FORMAT)

    def format_lesson_type(self, type_code: int) -> str:
        return self.LESSON_TYPES.get(type_code, "Неизвестный тип")

    def format_discipline(self, discipline: Discipline) -> str:
        parts = [
            self.TEMPLATES["discipline"].format(
                title=discipline.title,
                type=self.format_lesson_type(discipline.lesson_type)
            )
        ]

        if discipline.remote:
            parts.append(self.TEMPLATES["remote"])
        else:
            parts.append(self.TEMPLATES["auditorium"].format(
                room=discipline.auditorium.number,
                campus=discipline.auditorium.campus
            ))

        parts.append(self.TEMPLATES["teacher"].format(name=discipline.teacher.name))

        if discipline.subgroup > 0:
            parts.append(self.TEMPLATES["subgroup"].format(number=discipline.subgroup))

        return "\n".join(parts)

    def format_lesson(self, lesson: Lesson) -> str:
        time_range = self.LESSON_TIMES.get(lesson.number, "")
        lesson_header = self.TEMPLATES["lesson_header"].format(
            number=lesson.number,
            time=time_range
        )
        disciplines = "\n\n".join([self.format_discipline(d) for d in lesson.disciplines])
        return f"{lesson_header}\n{disciplines}"

    def format_day(self, schedule: ScheduleData, date_str: str) -> str:
        weekday = self.WEEKDAYS[datetime.strptime(date_str, "%Y-%m-%d").weekday()]
        date_fmt = self.format_date(date_str)
        header = self.TEMPLATES["day_header"].format(weekday=weekday, date=date_fmt)
        result = [header]

        if not schedule.groups:
            result.append(self.EMPTY_SCHEDULE)
            return "\n".join(result)

        for group in schedule.groups:
            if not group.lessons:
                result.append(self.EMPTY_SCHEDULE)
                continue

            result.extend([self.format_lesson(lesson) for lesson in sorted(
                group.lessons,
                key=lambda x: x.number
            )])

        return "\n".join(result)

    def format_week(self, daily_schedules: Dict[str, str]) -> str:
        dates = list(daily_schedules.keys())
        if not dates:
            return "Нет данных о расписании на неделю."

        start = self.format_date(dates[0])
        end = self.format_date(dates[-1])

        week_header = f"<b>Расписание на неделю: {start} – {end}</b>"
        day_blocks = [daily_schedules[date] for date in dates]

        # Build with separators only before days 2+ (Вт-Сб)
        parts = [week_header, day_blocks[0]]
        for block in day_blocks[1:]:
            parts.append(f"═════\n\n{block}")

        return "\n\n".join(parts)


# ---------- API Client ----------
async def check_forum_updates(access_token: str, last_check: datetime = None) -> List[Dict]:
    headers = {"Authorization": f"Bearer {access_token}"}
    updates = []

    try:
        # Получаем текущие дисциплины
        async with aiohttp.ClientSession() as session:
            # Получаем текущий семестр
            async with session.get(
                    "https://papi.mrsu.ru/v1/StudentSemester_selector",
                    headers=headers
            ) as resp:
                semesters = await resp.json()
                current_semester = next(s for s in semesters if s['IsCurrent'])

            # Проверяем каждую дисциплину
            for discipline in current_semester['Disciplines']:
                discipline_id = discipline['Id']

                # Проверяем непрочитанные сообщения
                async with session.get(
                        f"https://papi.mrsu.ru/v1/DisciplineReaded/{discipline_id}",
                        headers=headers
                ) as resp:
                    read_status = await resp.json()
                    if read_status['UnreadCount'] == 0:
                        continue

                # Получаем последние сообщения
                async with session.get(
                        f"https://papi.mrsu.ru/v1/ForumMessage/{discipline_id}/{read_status['UnreadCount']}/0",
                        headers=headers
                ) as resp:
                    messages = await resp.json()
                    new_messages = [
                        {
                            'text': msg['Text'],
                            'date': datetime.strptime(msg['DateCreated'], "%Y-%m-%dT%H:%M:%S"),
                            'author': msg['AuthorName']
                        }
                        for msg in messages
                        if not last_check or datetime.strptime(msg['DateCreated'], "%Y-%m-%dT%H:%M:%S") > last_check
                    ]

                    if new_messages:
                        updates.append({
                            'discipline': discipline['DisciplineName'],
                            'messages': new_messages
                        })

    except Exception as e:
        logging.error(f"Ошибка при проверке форума: {str(e)}")

    return updates

async def refresh_access_token(refresh_token: str) -> Optional[Dict]:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(TOKEN_URL, data=data) as resp:
            if resp.status == 200:
                return await resp.json()
            logging.error(f"Ошибка обновления токена: {await resp.text()}")
            return None

class ScheduleAPIClient:
    @staticmethod
    async def fetch_token(login: str, password: str) -> Optional[Dict]:
        data = {
            "grant_type": "password",
            "username": login,
            "password": password,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(TOKEN_URL, data=data) as resp:
                return await resp.json() if resp.status == 200 else None

    @staticmethod
    async def fetch_user_info(access_token: str) -> Optional[Dict]:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(USER_INFO_URL, headers=headers) as resp:
                return await resp.json() if resp.status == 200 else None

    @staticmethod
    async def fetch_schedule(access_token: str, date: str) -> ScheduleData:
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"date": date}
        async with aiohttp.ClientSession() as session:
            async with session.get(TIMETABLE_URL, headers=headers, params=params) as resp:
                data = await resp.json() if resp.status == 200 else []
                return ScheduleData(data)


# ---------- Service Functions ----------
class ScheduleService:
    def __init__(self):
        self.client = ScheduleAPIClient()
        self.formatter = ScheduleFormatter()

    async def get_daily_schedule(self, access_token: str, date: str) -> str:
        raw_data = await self.client.fetch_schedule(access_token, date)
        return self.formatter.format_day(raw_data, date)

    async def get_weekly_schedule(self, access_token: str, is_next_week: bool = False) -> str:
        dates = self._get_week_dates(is_next_week)
        daily_schedules = {}

        for date in dates:
            raw_data = await self.client.fetch_schedule(access_token, date)
            daily_schedules[date] = self.formatter.format_day(raw_data, date)

        return self.formatter.format_week(daily_schedules)

    @staticmethod
    def _get_week_dates(is_next_week: bool) -> List[str]:
        today = datetime.now()
        start = today - timedelta(days=today.weekday())  # Понедельник
        if is_next_week:
            start += timedelta(weeks=1)
        return [
            (start + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(6)  # Только Пн-Сб (0–5)
        ]


# ---------- Helper Functions ----------
def get_current_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def get_tomorrow_date() -> str:
    return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

# ---------- Совместимость со старым интерфейсом ----------
"""
def get_today_date() -> str:
    return get_current_date()
"""

async def get_token(login: str, password: str):
    return await ScheduleAPIClient.fetch_token(login, password)

async def get_user_info(access_token: str):
    return await ScheduleAPIClient.fetch_user_info(access_token)

async def get_formatted_schedule_for_date(access_token: str, date: str) -> str:
    """

    :rtype: object
    """
    service = ScheduleService()
    return await service.get_daily_schedule(access_token, date)

async def get_week_schedule(access_token: str, is_next_week: bool = False):
    service = ScheduleService()
    return await service.get_weekly_schedule(access_token, is_next_week)