# storage.py
import json # Для работы с JSON-файлами
import os # Для проверки существования файла и создания директорий
import asyncio # Для асинхронного выполнения
from typing import Dict, Any, Optional
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType # Базовые классы для создания хранилища
from aiogram.fsm.state import State
import logging

# Настройка логирования для отладки
logger = logging.getLogger(__name__)

class JSONStorage(BaseStorage):
    """
    Файловое хранилище FSM, которое сохраняет состояние в states.json.
    Использует asyncio.to_thread для асинхронной записи, чтобы не блокировать
    основной цикл бота.
    """
    def __init__(self, filename: str = "states.json"):
        self.filename = filename
        # FIX: Загружаем данные синхронно, так как __init__ - синхронный метод
        self._data = self._sync_load_data() 
        logger.info(f"JSONStorage initialized. {len(self._data)} sessions loaded.")

    def _sync_load_data(self) -> Dict[str, Any]:
        """Синхронная загрузка данных из файла. Выполняется при запуске."""
        if not os.path.exists(self.filename):
            return {}
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, Exception) as e:
            logger.error(f"Error loading states from file (starting fresh): {e}")
            return {}

    def _sync_save_data(self):
        """Синхронное сохранение данных в файл. Выполняется в отдельном потоке."""
        try:
            # Создаем директорию, если это необходимо
            os.makedirs(os.path.dirname(self.filename) or '.', exist_ok=True) 
            with open(self.filename, "w", encoding="utf-8") as f:
                # dump сохраняет данные в файл. sort_keys=True для стабильного порядка.
                json.dump(self._data, f, ensure_ascii=False, indent=2, sort_keys=True)
            logger.debug(f"State data successfully saved to {self.filename}")
        except IOError as e:
            logger.error(f"Error saving states to file: {e}")

    async def _save_data(self):
        """Асинхронное сохранение с использованием отдельного потока."""
        await asyncio.to_thread(self._sync_save_data)
        
    def _get_key(self, key: StorageKey) -> str:
        # Уникальный ключ для пользователя: chat_id + user_id
        return f"{key.chat_id}:{key.user_id}"

    # --- Методы FSM API, требующие обязательной реализации ---

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        """Устанавливает новое состояние FSM для пользователя."""
        k = self._get_key(key)
        if k not in self._data:
            self._data[k] = {}
        
        self._data[k]["state"] = state.state if isinstance(state, State) else state
        await self._save_data() # Сохраняем на диск

    async def get_state(self, key: StorageKey) -> Optional[str]:
        """Получает текущее состояние FSM."""
        k = self._get_key(key)
        return self._data.get(k, {}).get("state")

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        """Устанавливает данные контекста FSM."""
        k = self._get_key(key)
        if k not in self._data:
            self._data[k] = {}
        self._data[k]["data"] = data.copy()
        await self._save_data()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        """Получает данные контекста FSM."""
        k = self._get_key(key)
        return self._data.get(k, {}).get("data", {})

    async def update_data(self, key: StorageKey, data: Dict[str, Any]) -> Dict[str, Any]:
        """Обновляет данные контекста FSM (мержит старые и новые)."""
        current_data = await self.get_data(key)
        current_data.update(data)
        await self.set_data(key, current_data) 
        return current_data

    async def close(self) -> None:
        """Вызывается при завершении работы диспетчера. Сохраняет последние данные."""
        await self._save_data()
        
    def get_all_active_users(self):
        """Возвращает список всех сохраненных сессий для восстановления."""
        return self._data