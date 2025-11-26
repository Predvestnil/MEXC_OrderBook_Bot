# states.py
from aiogram.fsm.state import State, StatesGroup # Импорт классов для создания машины состояний (FSM)

class UserStates(StatesGroup):
    choosing_pair = State() # Состояние выбора пары из списка
    settings = State() # Состояние нахождения в меню настроек
    parsing = State() # Состояние активного парсинга стакана
    entering_pair = State() # Состояние ввода тикера пары текстом

# Дефолтные настройки пользователя
DEFAULT_SETTINGS = {
    "interval": 3,  # Интервал обновления стакана в секундах
    "depth": 5      # Количество строк (глубина) в стакане для отображения
}