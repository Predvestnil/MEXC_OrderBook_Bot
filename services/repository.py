# services/repository.py
import aiohttp # Библиотека для асинхронных HTTP-запросов
import logging
from typing import List

class MexcRepository:
    """
    Репозиторий для доступа к REST API MEXC.
    Отвечает за получение статических данных (список торговых пар).
    Использует aiohttp.ClientSession для эффективных асинхронных запросов.
    """
    BASE_URL = "https://api.mexc.com/api/v3"

    def __init__(self):
        self.session = None # Сессия aiohttp для переиспользования соединений

    async def _init_session(self):
        """Инициализирует сессию, если она еще не создана или закрыта."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Custom MEXC Bot)" 
                }
            )

    async def _close_session(self):
        """Закрывает активную сессию aiohttp."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def __aenter__(self):
        await self._init_session()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._close_session()

    async def get_default_symbols(self) -> List[str]:
        """Получает список рекомендуемых торговых пар."""
        url = f"{self.BASE_URL}/defaultSymbols"
        await self._init_session()
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    symbols = data.get('data', [])
                    
                    # Возвращаем полный список символов для корректного поиска
                    full_list = [s for s in symbols if isinstance(s, str)]
                    return full_list
                else:
                    logging.error(f"Error fetching default symbols: HTTP {response.status}")
                    return []
        except Exception as e:
            logging.error(f"Network error fetching default symbols: {e}")
            return []
