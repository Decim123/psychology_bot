import sqlite3
import os
import zipfile
from io import BytesIO
from datetime import datetime, timedelta
import pytz

moscow_tz = pytz.timezone('Europe/Moscow')
moscow_time = datetime.now(moscow_tz)

def execute_query(query, params=()):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    result = cursor.fetchall()
    conn.close()
    return result

def answer(field_name):
    if field_name not in ['start', 'q1', 'q2', 'q3', 'q4', 'q5', 'thx', 'n1',  'n2', 'n3', 'empty']:
        raise ValueError(f"Поле '{field_name}' не существует в таблице answers.")
    query = f"SELECT {field_name} FROM answers LIMIT 1"
    result = execute_query(query)
    if result:
        return result[0][0]
    else:
        return None

def write_answer(field_name, new_value):
    if field_name not in ['start', 'q1', 'q2', 'q3', 'q4', 'q5', 'thx', 'n1',  'n2', 'n3', 'empty']:
        raise ValueError(f"Поле '{field_name}' не существует в таблице answers.")
    existing_record = execute_query("SELECT COUNT(*) FROM answers")
    if existing_record[0][0] == 0:
        execute_query("INSERT INTO answers (start, q1, q2, q3, q4, q5, thx, n1,  n2, n3, 'empty') VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ('', '', '', '', '', '', '', '', '', '', ''))  # Вставляем пустую запись, если таблица пустая
    query = f"UPDATE answers SET {field_name} = ?"
    execute_query(query, (new_value,))
    print(f"Значение в поле '{field_name}' успешно обновлено на '{new_value}'.")

def format_answer(field_name, username):
    message_template = answer(field_name)  # Получаем текст из базы
    if message_template:
        return message_template.format(username=username)  # Подставляем имя пользователя
    return None

def add_new_column_to_answers(column_name):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    try:
        cursor.execute(f"ALTER TABLE answers ADD COLUMN {column_name} TEXT")
        conn.commit()
        print(f"Поле '{column_name}' успешно добавлено в таблицу 'answers'.")
    except sqlite3.OperationalError as e:
        print(f"Ошибка при добавлении поля '{column_name}': {e}")
    finally:
        conn.close()

def add_user_if_not_exists(tg_id, username, tg_username):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users WHERE tg_id = ?", (tg_id,))
    user_exists = cursor.fetchone()[0]

    if user_exists == 0:
        cursor.execute("INSERT INTO users (tg_id, username, answer, tg_username) VALUES (?, ?, ?, ?)", (tg_id, username, '', tg_username))
        conn.commit()
        print(f"Пользователь с tg_id {tg_id} и именем {username} добавлен в базу данных.")
    else:
        print(f"Пользователь с tg_id {tg_id} уже существует в базе данных.")

    conn.close()

def add_answer_to_user(tg_id, question, answer_text):
    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow_tz)

    if question == 24:
        future_time = now + timedelta(hours=24)
        answer_text = f'уведомление на {future_time.strftime("%d.%m.%Y %H:%M")} установлено'
        question = '🔔'
    else:
        try:
            date = datetime.strptime(question, '%Y-%m-%d %H:%M:%S%z')
            date = date.astimezone(moscow_tz)
            answer_text = f'уведомление на {date.strftime("%d.%m.%Y %H:%M")} установлено'
            question = '🔔'
        except ValueError:
            pass

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT answer FROM users WHERE tg_id = ?", (tg_id,))
    user_answer = cursor.fetchone()

    if user_answer is not None:
        existing_answer = user_answer[0] if user_answer[0] else ''
        updated_answer = existing_answer + f"{now.strftime('%d.%m.%Y %H:%M')}\nВопрос: {question}\nОтвет: {answer_text}\n\n"
        cursor.execute("UPDATE users SET answer = ? WHERE tg_id = ?", (updated_answer, tg_id))
        conn.commit()
        print(f"Вопрос и ответ добавлены пользователю с tg_id {tg_id}.")
    else:
        print(f"Пользователь с tg_id {tg_id} не найден.")

    conn.close()


def add_admin(tg_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM administrators WHERE tg_id = ?", (tg_id,))
    admin_exists = cursor.fetchone()[0]

    if admin_exists == 0:
        cursor.execute("INSERT INTO administrators (tg_id) VALUES (?)", (tg_id,))
        conn.commit()
        print(f"Администратор с tg_id {tg_id} добавлен.")
    else:
        print(f"Администратор с tg_id {tg_id} уже существует.")
    
    conn.close()

def is_admin(tg_id):
    """Проверяем, является ли пользователь администратором"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM administrators WHERE tg_id = ?", (tg_id,))
    admin_exists = cursor.fetchone()[0]
    
    conn.close()
    return admin_exists > 0

def add_admin_if_password_correct(tg_id, password):
    """Добавляем администратора, если пароль верный"""
    correct_password = "123"  # Пароль для администраторов
    if password == correct_password:
        add_admin(tg_id)
        return True
    return False

def users():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, tg_id, username, tg_username FROM users")
    all_users = cursor.fetchall()
    formatted_users = [{"id": user_id, "tg_id": tg_id, "username": username, "tg_username": tg_username} for user_id, tg_id, username, tg_username in all_users]
    conn.close()
    
    return formatted_users

def format_texts(text_fields):
    formatted_texts = []
    for field in text_fields:
        text = answer(field)
        formatted_texts.append(f"**{field}**: {text}\n-------")
    return "\n".join(formatted_texts)

def format_users_page(users_list, page, max_chars=3000):
    total_chars = 0
    users_on_page = []
    for user in users_list:
        user_str = f"{user}\n"
        if total_chars + len(user_str) <= max_chars:
            users_on_page.append(user_str)
            total_chars += len(user_str)
        else:
            break
    return "".join(users_on_page), len(users_list) - len(users_on_page)

def get_user_answers(tg_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT answer FROM users WHERE tg_id = ?", (tg_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        return result[0]
    else:
        return None

def create_zip_for_users():
    users_list = users()
    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for user in users_list:
            filename = f"{user['username']} (@{user['tg_username']}) [tg_id: {user['tg_id']}].txt"
            content = get_user_answers(user['tg_id'])
            if not content:
                content = "Нет ответов."
            zip_file.writestr(filename, content)
    
    zip_buffer.seek(0)
    return zip_buffer

def disable_admin_notifications(tg_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE administrators SET notification = FALSE WHERE tg_id = ?", (tg_id,))
    conn.commit()

    conn.close()
    print(f"Уведомления для администратора с tg_id {tg_id} отключены.")

def enable_admin_notifications(tg_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE administrators SET notification = TRUE WHERE tg_id = ?", (tg_id,))
    conn.commit()

    conn.close()
    print(f"Уведомления для администратора с tg_id {tg_id} включены.")

def get_admin_notification_status(tg_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT notification FROM administrators WHERE tg_id = ?", (tg_id,))
    result = cursor.fetchone()
    conn.close()

    if result is not None:
        return result[0]
    else:
        print(f"Администратор с tg_id {tg_id} не найден.")
        return None

def get_admins_with_notifications_enabled():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT tg_id FROM administrators WHERE notification = TRUE")
    admins = cursor.fetchall()
    conn.close()
    return [{"tg_id": admin[0]} for admin in admins]

def get_user_data(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT username, tg_username, tg_id FROM users WHERE tg_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return {"username": user[0], "tg_username": user[1], "tg_id": user[2]}
    else:
        return None

def split_message(message: str, max_length: int = 4096):
    return [message[i:i+max_length] for i in range(0, len(message), max_length)]

#add_new_column_to_answers('empty')
#write_answer('start', text)