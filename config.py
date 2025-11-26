# config.py
import logging # Модуль для настройки логирования

TOKEN = "TOKEN"  # Токен вашего Telegram-бота
MEXC_API_URL = "https://api.mexc.com/api/v3/defaultSymbols" # URL для получения рекомендуемых торговых пар (REST)
MEXC_WS_URL = "wss://wbs-api.mexc.com/ws" # Базовый WebSocket URL для подключения к бирже

logging.basicConfig(level=logging.INFO) # Настройка уровня логирования: INFO и выше будет выводиться в консоль
