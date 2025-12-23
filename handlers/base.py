from aiogram import Router, types
from aiogram.filters import Command
from config import Texts

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(Texts.START)