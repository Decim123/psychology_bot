import asyncio
import tempfile
from aiogram import Router, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.types.input_file import FSInputFile
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.services import *
from keyboards.keyboard import *
router = Router()
user_states = {}
notification_states = {}

async def send_reminder(bot: Bot, user_id: int, delay: int, message_text: str, retries_left: int):
    await asyncio.sleep(delay)
    
    if notification_states.get(user_id, True) and user_states.get(user_id) not in ['q1', 'q2', 'q3', 'q4', 'thx']:
        await bot.send_message(user_id, message_text, reply_markup=get_answer_keyboard())

        if retries_left > 0:
            next_delay = 10 if retries_left == 2 else 10
            next_message = str(answer('n1'))
            await send_reminder(bot, user_id, next_delay, next_message, retries_left - 1)

async def notify_admins_about_answers(user_id: int, bot: Bot):
    admins = get_admins_with_notifications_enabled()  # Получаем список администраторов с включенными уведомлениями
    user_data = get_user_data(user_id)  # Получаем данные о пользователе

    # Формируем короткое сообщение с инлайн-кнопкой
    message_text = (
        f"Пользователь: {user_data['username']} (@{user_data['tg_username']})\n"
        f"tg_id: {user_data['tg_id']} ответил на вопросы."
    )

    # Создаем инлайн-клавиатуру с кнопкой "Посмотреть"
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Посмотреть", callback_data=f"view_answers_{user_data['tg_id']}")
        ]
    ])

    for admin in admins:
        # Отправляем короткое сообщение каждому администратору с инлайн-кнопкой
        await bot.send_message(chat_id=admin['tg_id'], text=message_text, reply_markup=inline_kb)

@router.message(CommandStart())
async def process_start_command(message: Message, bot: Bot):
    add_user_if_not_exists(message.from_user.id, message.from_user.full_name, message.from_user.username)
    user_states[message.from_user.id] = 'start'
    formatted_message = format_answer('start', message.from_user.first_name)
    await message.answer(formatted_message)

    notification_states[message.from_user.id] = True
    delay_in_seconds = 0
    reminder_message = str(answer('n2'))
    await send_reminder(bot, message.from_user.id, delay_in_seconds, reminder_message, 2)

@router.message(Command(commands='admin'))
async def process_admin_command(message: Message):
    tg_id = message.from_user.id

    if is_admin(tg_id):
        await message.answer("🎛️ Панель управления", reply_markup=get_admin_panel_keyboard())
    else:
        user_states[tg_id] = 'admin_password_wait'
        await message.answer("Введите пароль:")

@router.message(Command(commands='questions'))
async def process_question_command(message: Message):
    tg_id = message.from_user.id
    try:
        del user_states[tg_id]
    except:
        pass

    user_states[tg_id] = 'q1'
    await message.answer(answer('q1'))

@router.message()
async def process_user_message(message: Message, bot: Bot):
    tg_id = message.from_user.id

    if tg_id in user_states and user_states[tg_id] == 'search_user_input':
        search_query = message.text.lower()
        users_list = users()
        results = []
        inline_kb = InlineKeyboardMarkup(inline_keyboard=[])
        
        for user in users_list:
            if (user['username'] and search_query in user['username'].lower()) or \
               (user['tg_username'] and search_query in user['tg_username'].lower()) or \
               search_query in str(user['tg_id']):
                results.append(f"{user['username']} (@{user['tg_username']}) [tg_id: {user['tg_id']}]")
                inline_kb.inline_keyboard.append([InlineKeyboardButton(text=f"Ответы для {user['username']}", callback_data=f"view_answers_{user['tg_id']}")])
        
        if results:
            inline_kb.inline_keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back_to_menu")])
            await message.answer("\n".join(results), reply_markup=inline_kb)
        else:
            await message.answer("Ничего не найдено.", reply_markup=get_back_keyboard())

        del user_states[tg_id]

    elif tg_id in user_states and user_states[tg_id] == 'admin_password_wait':
        password = message.text

        if add_admin_if_password_correct(tg_id, password):
            await message.answer("✅ Пароль верный.\n/admin откроет панель управления")
        else:
            await message.answer("🚫 Пароль неверный")

        del user_states[tg_id]

    elif tg_id in user_states and user_states[tg_id].startswith("editing_"):
        field = user_states[tg_id].split("_")[1]
        new_text = message.text
        current_page = int(user_states[tg_id].split("_")[2])

        if new_text == "0":
            await message.answer(f"❌ Текст для ключа **{field}** не был изменен.", parse_mode="Markdown")
        else:
            write_answer(field, new_text)
            await message.answer(f"✅ Текст для ключа **{field}** был успешно обновлен.", parse_mode="Markdown")

        del user_states[tg_id]

        text_fields = ['start', 'q1', 'q2', 'q3', 'q4', 'q5', 'thx', 'n1', 'n2', 'n3', 'empty']
        texts_per_page = 3
        total_pages = (len(text_fields) + texts_per_page - 1) // texts_per_page
        start_idx = (current_page - 1) * texts_per_page
        end_idx = start_idx + texts_per_page
        formatted_texts = format_texts(text_fields[start_idx:end_idx])

        await message.answer(
            formatted_texts,
            reply_markup=get_text_navigation_keyboard(current_page, total_pages, text_fields),
            parse_mode="Markdown"
        )

    elif tg_id in user_states and user_states[tg_id] == 'q1':
        add_answer_to_user(tg_id, answer('q1'), message.text)
        user_states[tg_id] = 'q2'
        notification_states[tg_id] = True
        await message.answer(answer('q2'))


    elif tg_id in user_states and user_states[tg_id] == 'q2':
        add_answer_to_user(tg_id, answer('q2'), message.text)
        user_states[tg_id] = 'q3'
        notification_states[tg_id] = True
        await message.answer(answer('q3'))

    elif tg_id in user_states and user_states[tg_id] == 'q3':
        add_answer_to_user(tg_id, answer('q3'), message.text)
        user_states[tg_id] = 'q4'
        notification_states[tg_id] = True
        await message.answer(answer('q4'))


    elif tg_id in user_states and user_states[tg_id] == 'q4':
        add_answer_to_user(tg_id, answer('q4'), message.text)
        user_states[tg_id] = 'thx'
        notification_states[tg_id] = True
        await message.answer(answer('q5'))


    elif tg_id in user_states and user_states[tg_id] == 'thx':
        add_answer_to_user(tg_id, answer('q5'), message.text)
        del user_states[tg_id]
        notification_states[tg_id] = False
        await message.answer(answer('thx'))
        await notify_admins_about_answers(tg_id, bot)

    # Если пользователь уже завершил все вопросы
    else:
        add_answer_to_user(tg_id, answer('empty'), message.text)
        await message.answer(answer('empty'))
        await notify_admins_about_answers(tg_id, bot)

@router.callback_query()
async def process_callback(callback: CallbackQuery, bot: Bot):
    tg_id = callback.from_user.id

    if callback.data == "answer":
        user_states[tg_id] = 'q1'
        notification_states[tg_id] = True
        await bot.send_message(tg_id, answer('q1'))
        await callback.answer()

    elif callback.data == "disable_notifications":
        notification_states[tg_id] = False
        await bot.send_message(tg_id, str(answer('n3')))
        await callback.answer()


    if callback.data == "download_zip":
        zip_buffer = create_zip_for_users()
        zip_buffer.seek(0)

        if zip_buffer.getbuffer().nbytes == 0:
            await bot.edit_message_text("Архив пуст.", chat_id=tg_id, message_id=callback.message.message_id)
            await callback.answer()
            return

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(zip_buffer.read())  # Записываем буфер в файл
            temp_file_path = temp_file.name

        if os.stat(temp_file_path).st_size == 0:
            await bot.edit_message_text("Файл пуст.", chat_id=tg_id, message_id=callback.message.message_id)
            await callback.answer()
            return

        # Редактируем сообщение, добавляя текст, что архив готов
        await bot.edit_message_text(
            chat_id=tg_id,
            message_id=callback.message.message_id,
            text="Архив с ответами пользователей готов. Вы можете скачать его ниже.",
            reply_markup=get_back_keyboard()
        )

        # Отправляем сам архив как отдельное сообщение
        document = FSInputFile(temp_file_path)
        await bot.send_document(
            chat_id=tg_id,
            document=document,
            caption="Архив с ответами пользователей"
        )

        # Удаляем временный файл
        os.remove(temp_file_path)
        await callback.answer()

    text_fields = ['start', 'q1', 'q2', 'q3', 'q4', 'q5', 'thx', 'n1', 'n2', 'n3', 'empty']
    texts_per_page = 3
    total_pages = (len(text_fields) + texts_per_page - 1) // texts_per_page
    
    if callback.data == "admin_texts":
        page = 1
        start_idx = (page - 1) * texts_per_page
        end_idx = start_idx + texts_per_page
        formatted_texts = format_texts(text_fields[start_idx:end_idx])

        await bot.edit_message_text(
            formatted_texts,
            chat_id=tg_id,
            message_id=callback.message.message_id,
            reply_markup=get_text_navigation_keyboard(page, total_pages, text_fields),
            parse_mode="Markdown"
        )
        await callback.answer()

    elif callback.data == "admin_users":
        users_list = users()
        total_users = len(users_list)
        formatted_users = "\n".join([f"{user['username']} (@{user['tg_username']}) [tg_id: {user['tg_id']}]" for user in users_list[:3000]])
        formatted_users += f"\n🟢 количество пользователей: {total_users}"

        await bot.edit_message_text(
            f"📗 Пользователи:\n{formatted_users}",
            chat_id=tg_id,
            message_id=callback.message.message_id,
            reply_markup=get_user_navigation_keyboard(1, total_users // 3000 + 1)
        )
        await callback.answer()

    elif callback.data == "admin_notifications":
        notification_status = 'Включенны 🟩' if get_admin_notification_status(tg_id) == 1 else  'Выключены 🟥'
        await bot.edit_message_text(
            f"Уведомления: {notification_status}\n\n*это изменение касается только вас, другие администраторы продолжат получать уведомления",
            chat_id=tg_id,
            message_id=callback.message.message_id,
            reply_markup=get_admin_notification_keyboard()
        )
        await callback.answer()

    elif callback.data == "disable_admin_notification":
        disable_admin_notifications(tg_id)
        notification_status = 'Включенны 🟩' if get_admin_notification_status(tg_id) == 1 else  'Выключены 🟥'
        await bot.edit_message_text(
            f"Уведомления: {notification_status}\n\n*это изменение касается только вас, другие администраторы продолжат получать уведомления",
            chat_id=tg_id,
            message_id=callback.message.message_id,
            reply_markup=get_admin_notification_keyboard()
        )
        await callback.answer()

    elif callback.data == "enable_admin_notification":
        enable_admin_notifications(tg_id)
        notification_status = 'Включенны 🟩' if get_admin_notification_status(tg_id) == 1 else  'Выключены 🟥'
        await bot.edit_message_text(
            f"Уведомления: {notification_status}\n\n*это изменение касается только вас, другие администраторы продолжат получать уведомления",
            chat_id=tg_id,
            message_id=callback.message.message_id,
            reply_markup=get_admin_notification_keyboard()
        )
        await callback.answer()

    elif callback.data.startswith("prev_page_"):
        page = int(callback.data.split("_")[-1]) - 1
        start_idx = (page - 1) * texts_per_page
        end_idx = start_idx + texts_per_page
        formatted_texts = format_texts(text_fields[start_idx:end_idx])

        await bot.edit_message_text(
            formatted_texts,
            chat_id=tg_id,
            message_id=callback.message.message_id,
            reply_markup=get_text_navigation_keyboard(page, total_pages, text_fields),
            parse_mode="Markdown"
        )
        await callback.answer()

    elif callback.data.startswith("next_page_"):
        page = int(callback.data.split("_")[-1]) + 1
        start_idx = (page - 1) * texts_per_page
        end_idx = start_idx + texts_per_page
        formatted_texts = format_texts(text_fields[start_idx:end_idx])

        await bot.edit_message_text(
            formatted_texts,
            chat_id=tg_id,
            message_id=callback.message.message_id,
            reply_markup=get_text_navigation_keyboard(page, total_pages, text_fields),
            parse_mode="Markdown"
        )
        await callback.answer()

    elif callback.data.startswith("text_"):
        field, page = callback.data.split("_")[1], int(callback.data.split("_")[-1])
        current_text = answer(field)
        user_states[tg_id] = f"editing_{field}_{page}"
        await bot.send_message(
            tg_id, 
            f"Вы выбрали текст: **{field}**\n{current_text}\n\nВведите текст, который заменит этот. Если не хотите ничего менять, введите 0.",
            parse_mode="Markdown"
        )
        await callback.answer()

    elif callback.data == "back_to_menu":
        await bot.edit_message_text(
            "Панель управления",
            chat_id=tg_id,
            message_id=callback.message.message_id,
            reply_markup=get_admin_panel_keyboard()
        )
        await callback.answer()

    elif callback.data == "ignore":
        await callback.answer()

    elif callback.data == "search_user":
        user_states[tg_id] = 'search_user_input'
        await bot.send_message(tg_id, "Введите имя, tg_username или tg_id для поиска.")
        await callback.answer()

    if callback.data.startswith("view_answers_"):
        user_id = int(callback.data.split("_")[2])
        user_data = get_user_data(user_id)
        user_answers = get_user_answers(user_id)

        if not user_answers:
            user_answers = "Ответов пользователя не найдено."

        # Формируем сообщение с ответами пользователя
        message_text = (
            f"Пользователь: {user_data['username']} (@{user_data['tg_username']})\n"
            f"tg_id: {user_data['tg_id']}\n\n"
            f"Ответы:\n{user_answers}"
        )

        # Разбиваем сообщение на части, если оно слишком длинное
        parts = split_message(message_text)

        # Если сообщение состоит из нескольких частей, отправляем их по очереди
        for part in parts:
            await bot.send_message(
                chat_id=callback.message.chat.id,
                text=part
            )

        # Отправляем ответ на callback, чтобы убрать индикатор ожидания
        await callback.answer()