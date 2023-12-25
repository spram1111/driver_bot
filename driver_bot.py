import time
import logging
import os
import sqlite3

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler,
                          CallbackQueryHandler, ConversationHandler,
                          MessageHandler, filters)
from dotenv import load_dotenv


conn = sqlite3.connect('bot.db')
cursor = conn.cursor()

# Создаем таблицу для хранения состояний чата и пользователей
cursor.execute('''
CREATE TABLE IF NOT EXISTS chat_state (
    chat_id INTEGER PRIMARY KEY,
    state INTEGER
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS drivers (
    chat_id INTEGER PRIMARY KEY,
    driver_name TEXT,
    seats INTEGER
)
''')

conn.commit()


# устанавливаем уровень логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()
secret_token = os.getenv('TOKEN')
# определяем состояния чата
START, ADD_DRIVER, SELECT_DRIVER = range(3)

# определяем клавиатуру
keyboard = [[InlineKeyboardButton("Добавить водителя",
                                  callback_data='add_driver')],
            [InlineKeyboardButton("Выбрать водителя",
                                  callback_data='select_driver')],
            [InlineKeyboardButton("Сбросить",
                                  callback_data='reset')]]
reply_markup = InlineKeyboardMarkup(keyboard)


async def start(update: Update, context):
    """Обработчик команды /start. Отправляет
    пользователю клавиатуру с доступными функциями."""
    chat_id = update.message.chat_id

    # Получаем состояние чата из базы данных
    cursor.execute(
        'SELECT state FROM chat_state WHERE chat_id = ?',
        (chat_id,)
    )
    row = cursor.fetchone()
    if row is not None:
        state = row[0]
    else:
        # Если состояние чата не найдено, устанавливаем состояние в START
        state = START
        cursor.execute(
            'INSERT INTO chat_state (chat_id, state) VALUES (?, ?)',
            (chat_id, state)
        )
        conn.commit()

    await update.message.reply_text('Привет! Я бот, который поможет'
                                    ' вам распределить компанию'
                                    ' друзей по машинам. '
                                    'Выберите одну из следующих опций:',
                                    reply_markup=reply_markup)

    # сохраняем время начала сессии
    context.user_data['start_time'] = time.time()
    cursor.execute(
        'UPDATE chat_state SET state = ? WHERE chat_id = ?',
        (state, chat_id)
    )
    conn.commit()
    # устанавливаем состояние чата в START
    return state


async def add_driver(update: Update, context):
    """Обработчик команды добавления водителя."""

    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text="Введите имя водителя и количество"
        "доступных мест в его автомобиле "
        "через пробел (например, 'Иван 3'):"
    )

    return ADD_DRIVER


async def select_driver(update: Update, context):
    """Обработчик команды выбора водителя."""

    await update.callback_query.answer()
    cursor.execute('SELECT driver_name, seats FROM drivers')
    drivers = cursor.fetchall()
    # создаем клавиатуру с кнопками выбора водителя
    keyboard = []
    for driver, seats in drivers:
        if seats > 0:
            keyboard.append(
                [InlineKeyboardButton(
                    f"{driver} ({seats} мест)", callback_data=driver
                )]
            )
    keyboard.append([InlineKeyboardButton("Отмена", callback_data='cancel')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    if not drivers:
        await update.callback_query.edit_message_text(
            text="Нет доступных водителей."
            "Пожалуйста, добавьте водителя.", reply_markup=reply_markup
        )
        return SELECT_DRIVER
    else:
        await update.callback_query.edit_message_text(
            text="Выберите водителя:", reply_markup=reply_markup
        )
        return SELECT_DRIVER


async def reset(update: Update, context):
    """Обработчик команды сброса."""
    chat_id = update.callback_query.message.chat_id

    await update.callback_query.answer()
    context.user_data.clear()
    await update.callback_query.edit_message_text(
        text="Счетчики сброшены.",
        reply_markup=reply_markup)
    cursor.execute(
        'UPDATE chat_state SET state = ? WHERE chat_id = ?',
        (START, chat_id)
    )
    conn.commit()


async def add_driver_callback(update: Update, context):
    """Обработчик ввода имени водителя и количества мест."""
    driver_info = update.message.text.split()
    if len(driver_info) != 2:
        update.message.reply_text("Неверный формат ввода. Попробуйте еще раз.")
        return ADD_DRIVER

    driver_name, seats = driver_info
    if not seats.isdigit() or int(seats) <= 0:
        update.message.reply_text(
            "Неверное количество мест. Попробуйте еще раз."
        )
        return ADD_DRIVER

    cursor.execute('INSERT INTO drivers (driver_name, seats) VALUES (?, ?)', (driver_name, int(seats)))
    conn.commit()

    await update.message.reply_text(
        f"Водитель {driver_name} добавлен. В его автомобиле {seats} мест."
    )
    await update.message.reply_text('Выберите одну из следующих опций:',
                                    reply_markup=reply_markup)

    return START


async def select_driver_callback(update: Update, context):
    """Обработчик выбора водителя."""
    passengers = context.user_data.get('passengers', {})
    driver = update.callback_query.data
    # drivers = context.user_data.get('drivers', {})
    # if driver in drivers:
    #     seats = drivers[driver]
    cursor.execute('SELECT driver_name, seats FROM drivers WHERE driver_name = ?', (driver,))
    result = cursor.fetchone()
    if result:
        driver_name, seats = result
        if seats > 0:
            seats -= 1
            cursor.execute('UPDATE drivers SET seats = ? WHERE driver_name = ?', (seats, driver_name))
            conn.commit()
            passengers[driver_name] = passengers.get(driver_name, []) + [update.callback_query.from_user.username]
            await update.callback_query.edit_message_text(
                text=f"Вы выбрали водителя {driver_name}."
                f"Осталось {seats} мест.\n\n"
                f"Список пассажиров:\n" + '\n'.join(f"- {passenger} ({seats - i} мест)" for i, passenger in enumerate(passengers[driver_name], 1)),
                reply_markup=reply_markup
            )
        # if result:
        #     driver_name, seats = result  
        #     if seats > 0:
        #         seats -= 1
        #         context.user_data['drivers'] = drivers
        #         passengers[driver] = passengers.get(driver, []) + [update.callback_query.from_user.username]
        #         await update.callback_query.edit_message_text(
        #             text=f"Вы выбрали водителя {driver}."
        #             f"Осталось {seats - 1} мест.\n\n"
        #             f"Список пассажиров:\n" + '\n'.join(f"- {passenger} ({seats - i} мест)" for i, passenger in enumerate(passengers[driver], 1)),
        #             reply_markup=reply_markup
        #         )
        else:
            await update.callback_query.edit_message_text(
                text="Извините, все места в автомобиле заняты.",
                reply_markup=reply_markup
            )
    else:
        await update.callback_query.edit_message_text(
            text="Неверный выбор водителя.",
            reply_markup=reply_markup
        )
    return START


async def cancel(update: Update, context):
    """Обработчик отмены действия."""
    update.callback_query.answer()
    await update.callback_query.edit_message_text(
        text="Действие отменено.",
        reply_markup=reply_markup
    )
    return START


def main():
    application = Application.builder().token(secret_token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            START: [CallbackQueryHandler(add_driver,
                                         pattern='^add_driver$'),
                    CallbackQueryHandler(select_driver,
                                         pattern='^select_driver$')],
            ADD_DRIVER: [MessageHandler(filters.TEXT & ~filters.COMMAND,
                                        add_driver_callback)],
            SELECT_DRIVER: [CallbackQueryHandler(select_driver_callback),
                            CallbackQueryHandler(cancel, pattern='^cancel$')]
        },
        fallbacks=[CallbackQueryHandler(reset, pattern='^reset$')]
    )

    application.add_handler(conv_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
