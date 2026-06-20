import asyncio
import logging
import sqlite3
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import db  # Твій файл db.py

logging.basicConfig(level=logging.INFO)

# ==========================================
# КОНФІГУРАЦІЯ
# ==========================================
TOKEN = "ТУТ_ВСТАВ_ТОКЕН"
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Словник нерухомості
ESTATES = {
    1: {"name": "Комната в общежитии", "price": 10000, "income": 100},
    2: {"name": "Квартира в спальном районе", "price": 35000, "income": 400},
    3: {"name": "Коттедж за городом", "price": 100000, "income": 1200},
    4: {"name": "Элитный Пентхаус", "price": 300000, "income": 4000}
}

# Тимчасова пам'ять для ігор у Блекджек
bj_games = {}

# ==========================================
# ДОПОМІЖНІ ФУНКЦІЇ ТА ПАТЧІ БД
# ==========================================
def execute_query(query, params=(), fetch=True):
    conn = db.create_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return result

def patch_database():
    """Автоматично додає нові колонки в db.py, якщо їх там ще немає"""
    conn = db.create_connection()
    try:
        conn.execute("ALTER TABLE users ADD COLUMN last_rent TIMESTAMP")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Колонка вже існує
    conn.close()

def update_activity(user_id, username):
    """Оновлює час останньої активності (Анти-AFK) і реєструє гравця"""
    db.add_user(user_id, username)
    execute_query("UPDATE users SET last_active = ? WHERE user_id = ?", (datetime.now(), user_id), fetch=False)

# ==========================================
# 1. ПРОФІЛЬ ТА РЕЄСТРАЦІЯ
# ==========================================
@dp.message(F.text.lower().in_(["$профиль", "$статистика"]))
async def cmd_profile(message: Message):
    user_id = message.from_user.id
    update_activity(user_id, message.from_user.full_name)
    user = db.get_user(user_id)
    state = db.get_state_info()
    
    status = "Гражданин"
    if state['mayor_id'] == user_id: status = "👑 Мэр"
    elif state['police_chief_id'] == user_id: status = "🚓 Шеф Полиции"
    
    jail_status = "⛓ В тюрьме" if user['is_jailed'] else "🟢 На свободе"
    job_name = "🏛 Гос. служба" if user['job_id'] == 0 else f"🏭 Завод (ID: {user['job_id']})"
    estate_name = ESTATES[user['estate_id']]['name'] if user['estate_id'] in ESTATES else "Нет недвижимости"
    if user['estate_id'] == 4: status = "💎 Олигарх"
    
    text = (
        f"📊 <b>Паспорт DragPolit:</b> {message.from_user.full_name}\n\n"
        f"💰 <b>Баланс:</b> {user['balance']} DC\n"
        f"💼 <b>Работа:</b> {job_name}\n"
        f"🏡 <b>Недвижимость:</b> {estate_name}\n"
        f"🌟 <b>Статус:</b> {status}\n"
        f"⚖️ <b>Закон:</b> {jail_status}"
    )
    await message.reply(text, parse_mode="HTML")

# ==========================================
# 2. ЕКОНОМІКА: РОБОТА, БІЗНЕС ТА ВАКАНСІЇ
# ==========================================
@dp.message(F.text.lower() == "$работа")
async def cmd_work(message: Message):
    user_id = message.from_user.id
    update_activity(user_id, message.from_user.full_name)
    user = db.get_user(user_id)
    state = db.get_state_info()
    
    if user['is_jailed']:
        return await message.reply("⛓ Вы в тюрьме! Какая работа?")

    if user['job_id'] == 0:
        min_wage = state['min_wage']
        if state['treasury'] < min_wage:
            return await message.reply("📉 <b>Дефолт!</b> В казне нет денег. Вы отработали бесплатно.", parse_mode="HTML")
            
        execute_query('UPDATE state SET treasury = treasury - ? WHERE id = 1', (min_wage,), fetch=False)
        db.update_balance(user_id, min_wage)
        if state['mayor_id'] != 0 and state['mayor_id'] != user_id:
            db.update_balance(state['mayor_id'], 5) # Корупційна надбавка Мера
            
        await message.reply(f"🏛 Вы отработали на государство и получили <b>{min_wage} DC</b>.", parse_mode="HTML")
    else:
        factory = execute_query('SELECT * FROM businesses WHERE id = ?', (user['job_id'],))
        if not factory:
            execute_query('UPDATE users SET job_id = 0 WHERE user_id = ?', (user_id,), fetch=False)
            return await message.reply("⚠️ Завод закрыт. Вы переведены на Гос. службу.")
            
        factory = factory[0]
        salary = factory['salary']
        tax_rate = state['business_tax_rate']
        
        if factory['budget'] < salary:
            return await message.reply(f"⚠️ У завода <b>{factory['name']}</b> нет денег на зарплату!", parse_mode="HTML")
            
        tax_amount = int(salary * (tax_rate / 100))
        net_salary = salary - tax_amount
        factory_profit = salary * 2 # Прибуток заводу
        
        execute_query('UPDATE businesses SET budget = budget - ? + ? WHERE id = ?', (salary, factory_profit, factory['id']), fetch=False)
        execute_query('UPDATE state SET treasury = treasury + ? WHERE id = 1', (tax_amount,), fetch=False)
        db.update_balance(user_id, net_salary)
        
        await message.reply(f"🏭 Работа на <b>{factory['name']}</b>:\n💵 Зарплата: {salary}\n🏛 Налог Мэру: -{tax_amount}\n💰 На руки: <b>{net_salary} DC</b>", parse_mode="HTML")

@dp.message(F.text.lower() == "$вакансии")
async def cmd_vacancies(message: Message):
    factories = execute_query('SELECT id, name, salary FROM businesses ORDER BY salary DESC LIMIT 10')
    if not factories:
        return await message.reply("📋 Нет частных заводов. Все работают на государство.")
    
    text = "📋 <b>Биржа труда (Топ-10 зарплат):</b>\n\n"
    for f in factories:
        text += f"ID: <code>{f['id']}</code> | <b>{f['name']}</b> | Оклад: {f['salary']} DC\n"
    text += "\n<i>Чтобы устроиться, напишите: $устроиться [ID]</i>"
    await message.reply(text, parse_mode="HTML")

@dp.message(F.text.lower().startswith("$устроиться "))
async def cmd_hire(message: Message):
    user_id = message.from_user.id
    update_activity(user_id, message.from_user.full_name)
    try:
        f_id = int(message.text.split()[1])
        factory = execute_query('SELECT * FROM businesses WHERE id = ?', (f_id,))
        if not factory: return await message.reply("❌ Завод не найден.")
        
        execute_query('UPDATE users SET job_id = ? WHERE user_id = ?', (f_id, user_id), fetch=False)
        await message.reply(f"✅ Вы успешно устроились на завод <b>{factory[0]['name']}</b>!", parse_mode="HTML")
    except:
        await message.reply("⚠️ Формат: $устроиться [ID]")

@dp.message(F.text.lower() == "$уволиться")
async def cmd_quit_job(message: Message):
    user_id = message.from_user.id
    execute_query('UPDATE users SET job_id = 0 WHERE user_id = ?', (user_id,), fetch=False)
    await message.reply("📝 Вы уволились и перешли на Государственную службу.")

# ==========================================
# 3. НЕРУХОМІСТЬ (ПАСИВНИЙ ДОХІД)
# ==========================================
@dp.message(F.text.lower() == "$недвижимость")
async def cmd_estate_catalog(message: Message):
    text = "🏘 <b>Агентство недвижимости:</b>\n\n"
    for eid, data in ESTATES.items():
        text += f"{eid}. <b>{data['name']}</b>\nСтоимость: {data['price']} DC | Доход: +{data['income']} DC/день\n\n"
    text += "<i>Купить: $купить_дом [Номер]</i>\n<i>Собрать прибыль: $рента</i>"
    await message.reply(text, parse_mode="HTML")

@dp.message(F.text.lower().startswith("$купить_дом "))
async def cmd_buy_estate(message: Message):
    user_id = message.from_user.id
    update_activity(user_id, message.from_user.full_name)
    user = db.get_user(user_id)
    try:
        e_id = int(message.text.split()[1])
        if e_id not in ESTATES: return await message.reply("❌ Нет такого номера.")
        
        price = ESTATES[e_id]['price']
        if user['balance'] < price:
            return await message.reply("❌ Недостаточно средств!")
            
        db.update_balance(user_id, -price)
        execute_query('UPDATE users SET estate_id = ? WHERE user_id = ?', (e_id, user_id), fetch=False)
        await message.reply(f"🔑 Поздравляем! Вы купили: <b>{ESTATES[e_id]['name']}</b>", parse_mode="HTML")
    except:
        await message.reply("⚠️ Формат: $купить_дом [Номер]")

@dp.message(F.text.lower() == "$рента")
async def cmd_collect_rent(message: Message):
    user_id = message.from_user.id
    user = execute_query('SELECT estate_id, last_rent FROM users WHERE user_id = ?', (user_id,))[0]
    
    if user['estate_id'] == 0:
        return await message.reply("❌ У вас нет недвижимости. Бомжам ренту не платят.")
        
    last_rent = user['last_rent']
    now = datetime.now()
    
    if last_rent:
        last_time = datetime.strptime(last_rent, '%Y-%m-%d %H:%M:%S.%f')
        if now < last_time + timedelta(hours=24):
            remain = (last_time + timedelta(hours=24)) - now
            hours, remainder = divmod(remain.seconds, 3600)
            return await message.reply(f"⏳ Следующая рента доступна через {hours}ч {remainder//60}м.")

    income = ESTATES[user['estate_id']]['income']
    db.update_balance(user_id, income)
    execute_query('UPDATE users SET last_rent = ? WHERE user_id = ?', (now, user_id), fetch=False)
    await message.reply(f"💸 Вы собрали ренту: <b>+{income} DC</b>", parse_mode="HTML")

# ==========================================
# 4. ПОЛІТИКА, ВЛАДА ТА БУНТ
# ==========================================
@dp.message(F.text.lower() == "$отставка")
async def cmd_resign(message: Message):
    user_id = message.from_user.id
    state = db.get_state_info()
    if user_id != state['mayor_id']:
        return await message.reply("❌ Вы не Мэр!")
    execute_query('UPDATE state SET mayor_id = 0 WHERE id = 1', fetch=False)
    await message.reply("🏳️ <b>МЭР УШЕЛ В ОТСТАВКУ!</b>", parse_mode="HTML")

@dp.message(F.text.lower() == "$бунт")
async def cmd_riot(message: Message):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    cost = 1000
    
    if user['balance'] < cost:
        return await message.reply(f"❌ На организацию бунта нужно {cost} DC (оплата провокаторам).")
        
    db.update_balance(user_id, -cost)
    success = random.choice([True, False])
    
    if success:
        execute_query('UPDATE state SET mayor_id = 0, police_chief_id = 0 WHERE id = 1', fetch=False)
        execute_query('UPDATE users SET is_jailed = 0', fetch=False) # Амністія всім
        await message.reply("🔥 <b>РЕВОЛЮЦИЯ СВЕРШИЛАСЬ!</b>\nМэр и Шеф Полиции свергнуты! Тюрьмы открыты! Анархия!", parse_mode="HTML")
    else:
        execute_query('UPDATE users SET is_jailed = 1 WHERE user_id = ?', (user_id,), fetch=False)
        await message.reply("🩸 <b>Бунт подавлен полицией!</b>\nОрганизатор отправлен за решетку.", parse_mode="HTML")

@dp.message(F.text.lower().startswith("$арест"))
async def cmd_arrest(message: Message):
    user_id = message.from_user.id
    state = db.get_state_info()
    if user_id != state['police_chief_id']: return await message.reply("❌ Вы не Шеф Полиции.")
    if not message.reply_to_message: return await message.reply("⚠️ Ответьте на сообщение нарушителя.")
    
    target_id = message.reply_to_message.from_user.id
    # Імунітет Котеджу
    target_user = db.get_user(target_id)
    if target_user['estate_id'] == 3 and random.choice([True, False]):
        return await message.reply("🏰 Подозреваемый спрятался за забором своего Коттеджа. Арест сорван!")

    execute_query('UPDATE users SET is_jailed = 1 WHERE user_id = ?', (target_id,), fetch=False)
    await message.reply(f"🚨 Игрок <b>{message.reply_to_message.from_user.full_name}</b> арестован!", parse_mode="HTML")

@dp.message(F.text.lower().startswith("$выпустить"))
async def cmd_release(message: Message):
    user_id = message.from_user.id
    state = db.get_state_info()
    if user_id not in [state['police_chief_id'], state['mayor_id']]: return await message.reply("❌ Нет прав.")
    if not message.reply_to_message: return await message.reply("⚠️ Ответьте на сообщение заключенного.")
    
    execute_query('UPDATE users SET is_jailed = 0 WHERE user_id = ?', (message.reply_to_message.from_user.id,), fetch=False)
    await message.reply("⚖️ Игрок амнистирован.")

# ==========================================
# 5. КАЗИНО: БЛЕКДЖЕК (МІНІ-ГРА)
# ==========================================
def draw_card():
    ranks = {'2':2, '3':3, '4':4, '5':5, '6':6, '7':7, '8':8, '9':9, '10':10, 'J':10, 'Q':10, 'K':10, 'A':11}
    suits = ['♠', '♥', '♦', '♣']
    rank = random.choice(list(ranks.keys()))
    return f"{rank}{random.choice(suits)}", ranks[rank]

def calculate_score(cards):
    score = sum(c[1] for c in cards)
    aces = sum(1 for c in cards if 'A' in c[0])
    while score > 21 and aces:
        score -= 10
        aces -= 1
    return score

@dp.message(F.text.lower().startswith("$блекджек "))
async def cmd_blackjack(message: Message):
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    try:
        bet = int(message.text.split()[1])
        if bet <= 0 or bet > user['balance']:
            return await message.reply("❌ Некорректная ставка или недостаточно средств.")
            
        db.update_balance(user_id, -bet)
        
        p_cards = [draw_card(), draw_card()]
        d_cards = [draw_card()]
        
        bj_games[user_id] = {'bet': bet, 'player': p_cards, 'dealer': d_cards}
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🃏 Взять карту", callback_data="bj_hit")
        builder.button(text="🛑 Хватит", callback_data="bj_stand")
        
        pscore = calculate_score(p_cards)
        await message.reply(
            f"🎰 <b>Блекджек</b> (Ставка: {bet})\n\n"
            f"Ваши карты: {' '.join(c[0] for c in p_cards)} <b>({pscore})</b>\n"
            f"Карта дилера: {d_cards[0][0]}\n\n"
            f"Ваш ход:", parse_mode="HTML", reply_markup=builder.as_markup()
        )
    except:
        await message.reply("⚠️ Формат: $блекджек [ставка]")

@dp.callback_query(F.data.startswith("bj_"))
async def callback_blackjack(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in bj_games:
        return await callback.answer("Игра устарела.", show_alert=True)
        
    game = bj_games[user_id]
    action = callback.data.split("_")[1]
    
    if action == "hit":
        game['player'].append(draw_card())
        pscore = calculate_score(game['player'])
        
        if pscore > 21:
            del bj_games[user_id]
            await callback.message.edit_text(f"💥 Перебор! Вы проиграли {game['bet']} DC.\nВаши карты: {' '.join(c[0] for c in game['player'])} <b>({pscore})</b>", parse_mode="HTML")
        else:
            builder = InlineKeyboardBuilder()
            builder.button(text="🃏 Взять карту", callback_data="bj_hit")
            builder.button(text="🛑 Хватит", callback_data="bj_stand")
            await callback.message.edit_text(
                f"🎰 <b>Блекджек</b> (Ставка: {game['bet']})\n\n"
                f"Ваши карты: {' '.join(c[0] for c in game['player'])} <b>({pscore})</b>\n"
                f"Карта дилера: {game['dealer'][0][0]}\n\n"
                f"Ваш ход:", parse_mode="HTML", reply_markup=builder.as_markup()
            )
            
    elif action == "stand":
        pscore = calculate_score(game['player'])
        
        # Дилер добирає до 17
        while calculate_score(game['dealer']) < 17:
            game['dealer'].append(draw_card())
            
        dscore = calculate_score(game['dealer'])
        
        result_text = f"Ваши карты: {' '.join(c[0] for c in game['player'])} <b>({pscore})</b>\n"
        result_text += f"Карты дилера: {' '.join(c[0] for c in game['dealer'])} <b>({dscore})</b>\n\n"
        
        if dscore > 21 or pscore > dscore:
            win = game['bet'] * 2
            db.update_balance(user_id, win)
            result_text = f"🎉 <b>ПОБЕДА!</b> Вы выиграли {win} DC!\n\n" + result_text
        elif pscore == dscore:
            db.update_balance(user_id, game['bet']) # Повернення
            result_text = f"🤝 <b>НИЧЬЯ!</b> Ставка возвращена.\n\n" + result_text
        else:
            result_text = f"💀 <b>ПОРАЖЕНИЕ!</b> Вы потеряли {game['bet']} DC.\n\n" + result_text
            
        del bj_games[user_id]
        await callback.message.edit_text(result_text, parse_mode="HTML")

# ==========================================
# ЗАПУСК БОТА
# ==========================================
async def main():
    db.init_db()        # Створюємо базові таблиці
    patch_database()    # Накатуємо оновлення (колонки для нерухомості)
    print("🚀 DragPolit (Max Version) запущено!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
