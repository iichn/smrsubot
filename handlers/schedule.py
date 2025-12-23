from aiogram import Router, types
from config import Texts, Buttons
from keyboards import schedule_menu

router = Router()

@router.message(F.text == Buttons.SCHEDULE)
async def handle_schedule(message: types.Message):
    await message.answer(Texts.SCHEDULE_PROMPT, reply_markup=schedule_menu())