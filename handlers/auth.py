from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from states import LoginState
from db import db_instance
from config import Texts
from keyboards import main_menu
from api import get_token, get_user_info

router = Router()


@router.message(Command("login"))
async def cmd_login(message: types.Message, state: FSMContext):
    await state.set_state(LoginState.waiting_for_login)
    await message.answer(Texts.LOGIN_PROMPT)


@router.message(LoginState.waiting_for_login)
async def process_login(message: types.Message, state: FSMContext):
    await state.update_data(login=message.text)
    await state.set_state(LoginState.waiting_for_password)
    await message.answer(Texts.PASSWORD_PROMPT)


@router.message(LoginState.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    token_data = await get_token(data['login'], message.text)

    if token_data:
        user_info = await get_user_info(token_data['access_token'])
        if user_info:
            db_instance.save_user_token(
                message.from_user.id,
                data['login'],
                token_data
            )
            await message.answer(
                Texts.AUTH_SUCCESS.format(name=user_info.get('FIO', 'пользователь')),
                reply_markup=main_menu()
            )
            await state.clear()
            return

    await message.answer(Texts.AUTH_FAIL)
    await state.clear()