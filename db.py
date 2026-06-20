import sqlite3
from datetime import datetime

# Назва файлу бази даних
DB_NAME = 'dragpolit.db'

def create_connection():
    """Створює з'єднання з базою даних."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row # Щоб отримувати дані як словники, а не просто кортежі
    return conn

def init_db():
    """Ініціалізація бази даних та створення всіх необхідних таблиць."""
    conn = create_connection()
    cursor = conn.cursor()

    # 1. Таблиця Гравців (з колонкою last_rent для нерухомості)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 1000,
            job_id INTEGER DEFAULT 0,
            estate_id INTEGER DEFAULT 0,
            is_jailed INTEGER DEFAULT 0,
            last_active TIMESTAMP,
            last_rent TIMESTAMP
        )
    ''')

    # 2. Таблиця Бізнесів
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            owner_id INTEGER,
            budget INTEGER DEFAULT 0,
            salary INTEGER DEFAULT 100,
            level INTEGER DEFAULT 1,
            max_workers INTEGER DEFAULT 3
        )
    ''')

    # 3. Таблиця Держави (Казна, Посади та Налаштування)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            treasury INTEGER DEFAULT 50000,
            mayor_id INTEGER DEFAULT 0,
            police_chief_id INTEGER DEFAULT 0,
            min_wage INTEGER DEFAULT 50,
            police_salary INTEGER DEFAULT 500,
            business_tax_rate INTEGER DEFAULT 10
        )
    ''')

    # Створюємо державу, якщо її ще немає (ініціалізація 1-го рядка)
    cursor.execute('INSERT OR IGNORE INTO state (id) VALUES (1)')

    conn.commit()
    conn.close()
    print("✅ База даних успішно ініціалізована!")

# ==========================================
# ФУНКЦІЇ ДЛЯ РОБОТИ З БАЗОЮ (Викликаються з main.py)
# ==========================================

def add_user(user_id, username):
    """Реєструє нового гравця в базі."""
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, last_active)
        VALUES (?, ?, ?)
    ''', (user_id, username, datetime.now()))
    conn.commit()
    conn.close()

def get_user(user_id):
    """Отримує інформацію про гравця."""
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_balance(user_id, amount):
    """Змінює баланс гравця (може бути + або -)."""
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def get_state_info():
    """Отримує дані про казну, мера та податки."""
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM state WHERE id = 1')
    state = cursor.fetchone()
    conn.close()
    return state

# Якщо випадково запустити цей файл окремо, він просто створить таблиці
if __name__ == '__main__':
    init_db()
