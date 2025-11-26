# main.py
import asyncio # Для асинхронного программирования и управления задачами
import logging # Для логирования
from aiogram import Bot, Dispatcher, F # Основные классы Aiogram
from aiogram.types import Message, CallbackQuery # Типы сообщений и колбэков
from aiogram.filters import Command # Фильтр для команд /start
from aiogram.fsm.context import FSMContext # Контекст FSM (хранение данных и состояния)
from aiogram.enums import ParseMode # Режим парсинга (Markdown, HTML)

# --- Импорты ---
from config import TOKEN 
from states import UserStates, DEFAULT_SETTINGS
from services.repository import MexcRepository # Для получения списка пар
from services.socket import MexcSocketService # Для работы с WebSocket
from keyboards import get_pairs_keyboard, get_settings_keyboard, get_stop_parsing_keyboard, get_cancel_keyboard
from aiogram.utils.keyboard import InlineKeyboardBuilder # Для динамического создания клавиатур
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton 
from utils import format_orderbook # Для форматирования вывода стакана
from storage import JSONStorage # Файловое хранилище FSM

# --- Инициализация ---
storage = JSONStorage("states.json") # Создание файлового хранилища
bot = Bot(token=TOKEN, parse_mode=ParseMode.MARKDOWN) # Инициализация бота
dp = Dispatcher(storage=storage) # Инициализация диспетчера с файловым хранилищем
 
# Хранилище активных задач парсинга: {user_id: asyncio.Task}
parsing_tasks = {}
mexc_repository = MexcRepository() # Репозиторий для API запросов


# --- HANDLERS(Обработчики команд и событий)---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработка команды /start."""
    await state.set_state(UserStates.choosing_pair) # Переход в состояние выбора пары
    
    data = await state.get_data()
    if not data:
        await state.set_data(DEFAULT_SETTINGS) # Установка дефолтных настроек, если данных нет

    pairs = await mexc_repository.get_default_symbols() # Получение списка пар
    
    if not pairs:
        # Попытка повторной загрузки, если не удалось с первого раза
        await message.answer("Загружаю список монет...")
        await asyncio.sleep(1) 
        pairs = await mexc_repository.get_default_symbols()

    await message.answer(
        "Привет! Выбери пару для отслеживания стакана:",
        reply_markup=get_pairs_keyboard(pairs, page=0)
    )

@dp.callback_query(F.data.startswith("page_"), UserStates.choosing_pair)
async def paginate_pairs(callback: CallbackQuery):
    """Обработка пагинации (кнопки Назад/Далее)."""
    page = int(callback.data.split("_")[1])
    pairs = await mexc_repository.get_default_symbols() 
    
    # Защита от выхода за пределы списка
    if not pairs:
        return
        
    await callback.message.edit_reply_markup(
        reply_markup=get_pairs_keyboard(pairs, page=page)
    )

@dp.callback_query(F.data == "settings")
async def open_settings(callback: CallbackQuery, state: FSMContext):
    """Открытие меню настроек."""
    await state.set_state(UserStates.settings)
    data = await state.get_data()
    await callback.message.edit_text(
        "Настройки парсера:",
        reply_markup=get_settings_keyboard(data['interval'], data['depth'])
    )

@dp.callback_query(UserStates.settings, F.data.in_({"interval_inc", "interval_dec", "depth_inc", "depth_dec"}))
async def change_settings(callback: CallbackQuery, state: FSMContext):
    """Изменение настроек интервала и глубины."""
    data = await state.get_data()
    action = callback.data
    
    # Логика изменения настроек с проверками границ
    if action == "interval_inc":
        data['interval'] += 1
    elif action == "interval_dec" and data['interval'] > 1:
        data['interval'] -= 1
    elif action == "depth_inc" and data['depth'] < 20:
        data['depth'] += 1
    elif action == "depth_dec" and data['depth'] > 1:
        data['depth'] -= 1
        
    await state.update_data(data) # Обновление данных FSM (сохраняется в states.json)
    await callback.message.edit_reply_markup(
        reply_markup=get_settings_keyboard(data['interval'], data['depth'])
    )

@dp.callback_query(F.data == "back_to_pairs", UserStates.settings)
async def back_to_pairs(callback: CallbackQuery, state: FSMContext):
    """Возврат из настроек к выбору пары."""
    await state.set_state(UserStates.choosing_pair)
    pairs = await mexc_repository.get_default_symbols()
    await callback.message.edit_text(
        "Выберите валютную пару:",
        reply_markup=get_pairs_keyboard(pairs, page=0)
    )

@dp.callback_query(F.data == "start_pair_input", UserStates.choosing_pair)
async def start_pair_input_handler(callback: CallbackQuery, state: FSMContext):
    """Переключение в режим текстового ввода пары."""
    await state.set_state(UserStates.entering_pair)
    await callback.message.edit_text(
        "📝 Введите тикер (например, BTCUSDT) или часть названия пары для поиска. Используйте кнопку ниже, чтобы отменить.",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "cancel_input", UserStates.entering_pair)
async def cancel_input_handler(callback: CallbackQuery, state: FSMContext):
    """Отмена текстового ввода и возврат к списку пар."""
    await state.set_state(UserStates.choosing_pair)
    pairs = await mexc_repository.get_default_symbols()
    await callback.message.edit_text(
        "Вернулись к выбору. Выберите пару:",
        reply_markup=get_pairs_keyboard(pairs, page=0)
    )
    await callback.answer()

@dp.message(UserStates.entering_pair)
async def process_pair_input_handler(message: Message, state: FSMContext):
    """Обрабатывает текстовый ввод пользователя для поиска пары."""
    user_input = message.text.upper().strip()

    # Используем список рекомендуемых пар для поиска
    all_pairs = await mexc_repository.get_default_symbols() 

    # Поиск пар, которые начинаются или содержат введенный текст
    matching_pairs = [
        p for p in all_pairs 
        if p.startswith(user_input) or user_input in p
    ]

    if len(matching_pairs) == 1:
        # Найдено одно точное совпадение -> Запускаем парсинг
        symbol = matching_pairs[0]

        # --- Логика запуска парсинга (скопирована из start_parsing_pair) ---
        user_id = message.from_user.id

        if user_id in parsing_tasks:
            parsing_tasks[user_id].cancel()

        await state.set_state(UserStates.parsing)
        data = await state.get_data()
        interval = data.get('interval', 3)
        depth = data.get('depth', 5)

        msg = await message.answer(
            f"✅ Найдена и выбрана пара: **{symbol}**. \n🚀 Запускаю парсинг...",
            reply_markup=get_stop_parsing_keyboard()
        )

        task = asyncio.create_task(parsing_loop(
            message.chat.id,
            msg.message_id,
            symbol,
            interval,
            depth
        ))

        await state.update_data(current_message_id=msg.message_id, current_symbol=symbol)
        parsing_tasks[user_id] = task

    elif 1 < len(matching_pairs) <= 10:
        # Найдено несколько совпадений (до 10) -> Предлагаем выбрать кнопками
        builder = InlineKeyboardBuilder()
        for symbol in matching_pairs:
            # Callback 'select_' будет обработан существующей функцией start_parsing_pair
            builder.button(text=symbol, callback_data=f"select_{symbol}")
        builder.adjust(2)
        builder.row(InlineKeyboardButton(text="❌ Отмена (Текстом)", callback_data="cancel_input"))
        print(builder.as_markup())

        await message.answer(
            f"Найдены {len(matching_pairs)} совпадений. Выберите точное:",
            reply_markup=builder.as_markup()
        )
        # Пользователь остается в состоянии entering_pair, чтобы выбрать кнопку или ввести новый текст

    else:
        # 0 совпадений или слишком много (> 10)
        await message.answer(
            f"❌ Не найдено совпадений для `{user_input}` или слишком много результатов. Попробуйте ввести точный тикер (например, ETH) или часть названия.",
            reply_markup=get_cancel_keyboard()
        )

# --- Логика парсинга ---

async def parsing_loop(chat_id: int, message_id: int, symbol: str, interval: int, depth: int):
    """
    Бесконечный цикл, который подключается к WebSocket и периодически
    обновляет сообщение с данными стакана.
    """
    # Создаем и запускаем сервис WebSocket
    socket_service = MexcSocketService(symbol, None)
    socket_task = asyncio.create_task(socket_service.start())
    
    try:
        while True:
            await asyncio.sleep(interval)  # Пауза между обновлениями
            data = socket_service.get_latest_data() # Получаем последние данные
            if data and 'asks' in data:
                text = format_orderbook(symbol, data, depth)
                try:
                    # Редактирование сообщения
                    await bot.edit_message_text(
                        text=text,
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=get_stop_parsing_keyboard()
                    )
                except Exception as e:
                    if "message is not modified" not in str(e):
                        # Если сообщение не найдено (удалено пользователем или старое), останавливаем
                        if "message to edit not found" in str(e):
                             raise asyncio.CancelledError
                        logging.error(f"Edit error: {e}")
            else:
                pass
                
    except asyncio.CancelledError:
        logging.info(f"🛑 Parsing task cancelled for {symbol}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error in loop: {e}")
    finally:
        # Очистка ресурсов при выходе из цикла
        logging.info(f"Closing socket connection for {symbol}...")
        await socket_service.stop()
        socket_task.cancel()
        try:
            await socket_task
        except asyncio.CancelledError:
            pass

@dp.callback_query(F.data.startswith("select_"))
async def start_parsing_pair(callback: CallbackQuery, state: FSMContext):
    """
    Запускает парсинг после выбора пары (из списка или после поиска).
    """
    ss = await state.get_state()
    if ss in [UserStates.choosing_pair, UserStates.entering_pair]:
        symbol = callback.data.split("_")[1]
        user_id = callback.from_user.id

        # Отмена предыдущей активной задачи, если есть
        if user_id in parsing_tasks:
            parsing_tasks[user_id].cancel()
            
        await state.set_state(UserStates.parsing)
        data = await state.get_data()
        interval = data.get('interval', 3)
        depth = data.get('depth', 5)
        
        # Редактируем сообщение для запуска парсинга
        msg = await callback.message.edit_text(
            f"🚀 Запускаю парсинг {symbol}...\nЗагрузка снапшота...",
            reply_markup=get_stop_parsing_keyboard()
        )
        
        # Сохраняем данные о текущей задаче для восстановления после перезагрузки
        await state.update_data(current_message_id=msg.message_id, current_symbol=symbol)
        
        # Запуск нового асинхронного цикла парсинга
        task = asyncio.create_task(parsing_loop(
            callback.message.chat.id,
            msg.message_id, # Используем ID сообщения
            symbol,
            interval,
            depth
        ))
        
        parsing_tasks[user_id] = task

@dp.callback_query(F.data == "stop_parsing", UserStates.parsing)
async def stop_parsing_handler(callback: CallbackQuery, state: FSMContext):
    """Остановка активного парсинга."""
    user_id = callback.from_user.id
    
    # Отмена задачи парсинга
    if user_id in parsing_tasks:
        parsing_tasks[user_id].cancel()
        await asyncio.sleep(0.1) 
        del parsing_tasks[user_id]
    
    # Очищаем временные данные о текущем парсинге
    await state.update_data(current_message_id=None, current_symbol=None)
    
    
    await state.set_state(UserStates.choosing_pair)
    pairs = await mexc_repository.get_default_symbols()
    
    # Удаляем сообщение стакана и отправляем новое с меню выбора
    try:
        await callback.message.delete()
    except:
        pass

    await callback.message.answer(
        "Парсинг остановлен. Выберите пару:",
        reply_markup=get_pairs_keyboard(pairs, page=0)
    )

# --- ВОССТАНОВЛЕНИЕ ПОСЛЕ СБОЯ ---

async def on_startup(bot: Bot):
    """Функция, запускается один раз при старте бота. Восстанавливает активные задачи."""
    logging.info("♻️ Checking for interrupted tasks...")
    
    # Получаем все данные из нашего JSON-хранилища
    all_users = storage.get_all_active_users()
    
    count = 0
    for key_str, user_info in all_users.items():
        # key_str имеет формат "chat_id:user_id"
        try:
            chat_id, user_id = map(int, key_str.split(":"))
            state_str = user_info.get("state")
            data = user_info.get("data", {})
            
            # Если пользователь был в состоянии парсинга
            if state_str == UserStates.parsing.state:
                symbol = data.get("current_symbol")
                message_id = data.get("current_message_id")
                interval = data.get("interval", 3)
                depth = data.get("depth", 5)
                
                if symbol and message_id:
                    logging.info(f"🔄 Restoring task for user {user_id}, pair {symbol}")
                    
                    # Отправляем уведомление, что мы вернулись (опционально, можно не делать)
                    try:
                        # Пытаемся сразу перезапустить задачу на том же сообщении
                        task = asyncio.create_task(parsing_loop(
                            chat_id,
                            message_id,
                            symbol,
                            interval,
                            depth
                        ))
                        parsing_tasks[user_id] = task
                        count += 1
                    except Exception as e:
                        logging.error(f"Failed to restore task for {user_id}: {e}")
                        
        except Exception as e:
            logging.error(f"Error parsing user data key {key_str}: {e}")
            
    if count > 0:
        logging.info(f"✅ Restored {count} parsing tasks.")
    else:
        logging.info("No active tasks to restore.")

async def main():
    """Основная функция запуска бота."""
    async with mexc_repository:
        await mexc_repository.get_default_symbols() # Предварительная загрузка символов

    # Регистрация функции восстановления при старте
    dp.startup.register(on_startup)

    logging.info("Bot started")
    # Запуск бота (бесконечный цикл обработки событий)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
    finally:
        asyncio.run(mexc_repository._close_session())