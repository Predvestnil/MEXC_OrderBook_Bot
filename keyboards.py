# keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder # Удобный инструмент для построения клавиатур

def get_pairs_keyboard(pairs, page=0, items_per_page=5):
    """Генерирует Inline-клавиатуру для выбора торговой пары."""
    builder = InlineKeyboardBuilder()
    
    start = page * items_per_page
    end = start + items_per_page
    current_pairs = pairs[start:end]

    # Добавляем кнопки для текущей страницы
    for symbol in current_pairs:
        builder.button(text=symbol, callback_data=f"select_{symbol}")

    # По одной кнопке в ряд
    builder.adjust(1) 

    # Навигационные кнопки (Назад, Настройки, Далее)
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(text="⚙️ Настр.", callback_data="settings"))
    
    if end < len(pairs):
        nav_buttons.append(InlineKeyboardButton(text="Далее ➡️", callback_data=f"page_{page+1}"))
        
    builder.row(*nav_buttons)
    
    # Кнопка для переключения в режим ввода текста
    builder.row(InlineKeyboardButton(text="🔍 Ввести пару текстом", callback_data="start_pair_input"))
    
    return builder.as_markup()

def get_settings_keyboard(current_interval, current_depth):
    """Генерирует Inline-клавиатуру для изменения интервала и глубины стакана."""
    builder = InlineKeyboardBuilder()
    
    # Интервал
    builder.row(
        InlineKeyboardButton(text="-", callback_data="interval_dec"),
        InlineKeyboardButton(text=f"Интервал: {current_interval}с", callback_data="ignore"),
        InlineKeyboardButton(text="+", callback_data="interval_inc")
    )
    
    # Глубина
    builder.row(
        InlineKeyboardButton(text="-", callback_data="depth_dec"),
        InlineKeyboardButton(text=f"Глубина: {current_depth}", callback_data="ignore"),
        InlineKeyboardButton(text="+", callback_data="depth_inc")
    )
    
    builder.row(InlineKeyboardButton(text="🔙 Назад к парам", callback_data="back_to_pairs"))
    
    return builder.as_markup()

def get_stop_parsing_keyboard():
    """Клавиатура для остановки активного парсинга."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛑 Остановить парсинг", callback_data="stop_parsing")]
    ])

def get_cancel_keyboard():
    """Клавиатура для отмены текстового ввода пары."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена (Вернуться к списку)", callback_data="cancel_input")]
    ])