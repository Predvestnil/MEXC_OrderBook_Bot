# services/socket.py
import json
import websockets # Библиотека для работы с WebSocket
import asyncio
import logging
import ssl # Для защищенного SSL/TLS соединения
import certifi # Для получения актуальных корневых сертификатов
import aiohttp
from typing import Dict, Any, List

# --- ВАЖНО: ИМПОРТ СГЕНЕРИРОВАННОГО ФАЙЛА ---
# Предполагается, что этот файл PushDataV3ApiWrapper_pb2 сгенерирован из .proto-файла MEXC
import PushDataV3ApiWrapper_pb2

# Поле Protobuf-объекта, содержащее данные стакана
DEPTH_FIELD_NAME = "publicAggreDepths" 

class MexcSocketService:
    """
    Асинхронный сервис для подключения к WebSocket MEXC и получения данных
    стакана (Order Book) в реальном времени. Использует Protobuf.
    """
    def __init__(self, symbol: str, update_callback):
        self.symbol = symbol.replace("/", "").upper() # Нормализация тикера
        self.callback = update_callback # Колбэк
        self.running = False # Флаг для управления циклом
        self.ws = None # Объект WebSocket-соединения
        self.last_data = None # Последние полученные данные стакана
        
        # Хранилище всего стакана (Локальный кэш)
        # Формат: { float(price): float(quantity) }
        self.asks_book = {}
        self.bids_book = {}
        
        # Флаг, что мы загрузили начальный снимок
        self.snapshot_loaded = False
        
        self.uri = "wss://wbs-api.mexc.com/ws" # Адрес WebSocket API
        self.rest_uri = "https://api.mexc.com/api/v3/depth" # Адрес REST API

    async def _fetch_snapshot(self):
        """Загружает полный снимок стакана через REST API."""
        try:
            params = {"symbol": self.symbol, "limit": 1000}
            async with aiohttp.ClientSession() as session:
                async with session.get(self.rest_uri, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        # Очищаем и заполняем стакан
                        self.asks_book = {float(p): float(q) for p, q in data.get('asks', [])}
                        self.bids_book = {float(p): float(q) for p, q in data.get('bids', [])}
                        
                        self.snapshot_loaded = True
                        logging.info(f"Snapshot loaded for {self.symbol}: {len(self.asks_book)} asks, {len(self.bids_book)} bids")
                    else:
                        logging.error(f"Failed to fetch snapshot: {resp.status}")
        except Exception as e:
            logging.error(f"Snapshot error: {e}")

    def _process_depth_update(self, update_data):
        """Применяет инкрементальные обновления к локальному стакану."""
        if not self.snapshot_loaded:
            return # Игнорируем обновления, пока нет базы

        # Обработка ASKS (Продажи)
        for item in update_data['asks']:
            price = float(item['price'])
            qty = float(item['quantity'])
            
            if qty == 0:
                # Удаляем цену, если объем 0
                if price in self.asks_book:
                    del self.asks_book[price]
            else:
                # Обновляем или добавляем уровень
                self.asks_book[price] = qty

        # Обработка BIDS (Покупки)
        for item in update_data['bids']:
            price = float(item['price'])
            qty = float(item['quantity'])
            
            if qty == 0:
                if price in self.bids_book:
                    del self.bids_book[price]
            else:
                self.bids_book[price] = qty

        # Формируем итоговый объект для отправки в UI
        # Нам нужно отсортировать и вернуть список словарей, как ждет utils.py
        
        # Asks: сортировка по возрастанию цены (дешевые внизу стакана продаж)
        sorted_asks = sorted(self.asks_book.items(), key=lambda x: x[0])
        
        # Bids: сортировка по убыванию цены (дорогие вверху стакана покупок)
        sorted_bids = sorted(self.bids_book.items(), key=lambda x: x[0], reverse=True)
        
        # Преобразуем в формат списка для utils.py [{'price': ..., 'quantity': ...}]
        # Берем топ-50 для экономии памяти, остальное храним в фоне
        final_asks = [{'price': f"{p}", 'quantity': f"{q}"} for p, q in sorted_asks[:50]]
        final_bids = [{'price': f"{p}", 'quantity': f"{q}"} for p, q in sorted_bids[:50]]
        
        self.last_data = {
            "asks": final_asks,
            "bids": final_bids,
            "symbol": self.symbol
        }

    def _deserialize_protobuf(self, raw_data: bytes) -> Dict[str, Any]:
        """Десериализует Protobuf и возвращает сырые данные обновления."""
        try:
            result = PushDataV3ApiWrapper_pb2.PushDataV3ApiWrapper()
            result.ParseFromString(raw_data)

            if hasattr(result, DEPTH_FIELD_NAME):
                depth_data_pb = getattr(result, DEPTH_FIELD_NAME)
                
                asks_list = [{'price': item.price, 'quantity': item.quantity} for item in depth_data_pb.asks]
                bids_list = [{'price': item.price, 'quantity': item.quantity} for item in depth_data_pb.bids]
                
                return {
                    "asks": asks_list,
                    "bids": bids_list,
                    "is_depth": True
                }
            
            if result.channel == "system@ping":
                return {"method": "PING"}

        except Exception:
            try:
                message = raw_data.decode('utf-8', errors='ignore')
                return json.loads(message)
            except:
                return {}
        return {}

    async def start(self):
        """Запускает цикл подключения и обработки сообщений WebSocket."""
        self.running = True
        
        # 1. Сначала загружаем снимок REST API
        logging.info(f"Fetching snapshot for {self.symbol}...")
        await self._fetch_snapshot()
        
        # Настройка SSL/TLS
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        while self.running:
            try:
                # Установка соединения с автоматическими пингами/понгами
                async with websockets.connect(
                    self.uri, 
                    ssl=ssl_context, 
                    open_timeout=10,
                    ping_interval=25, 
                    ping_timeout=10
                ) as websocket:
                    self.ws = websocket
                    logging.info(f"Connected to WS for {self.symbol}")
                    
                    # Подписка на Incremental Depth (изменения)
                    topic = f"spot@public.aggre.depth.v3.api.pb@100ms@{self.symbol}"
                    payload = {"method": "SUBSCRIPTION", "params": [topic]}
                    await websocket.send(json.dumps(payload))

                    while self.running:
                        try:
                            # Ожидаем входящее сообщение с таймаутом
                            raw_message = await asyncio.wait_for(self.ws.recv(), timeout=35.0)
                            
                            if isinstance(raw_message, bytes):
                                update_data = self._deserialize_protobuf(raw_message)
                            else: # Если вдруг пришел текст (например, JSON-ответ на подписку)
                                update_data = json.loads(raw_message)

                            if not update_data: continue

                            # Обработка PING
                            if update_data.get('method') == "PING":
                                await self.ws.send(json.dumps({"method": "PONG"}))
                                continue
                            
                            # Получение данных стакана (обновление last_data)
                            if update_data.get('is_depth'):
                                self._process_depth_update(update_data)
                                # Вызываем колбэк только если есть данные (last_data формируется внутри process)
                                if self.last_data:
                                    self.callback(self.last_data)

                        except asyncio.TimeoutError:
                            logging.warning("Timeout. Reconnecting...")
                            break 
                        except Exception as e:
                            logging.error(f"WS Error: {e}")
                            break
            
            except Exception as e:
                logging.error(f"Connection dropped: {e}. Retry in 5s...")
                await asyncio.sleep(5) # Пауза перед следующей попыткой

    async def stop(self):
        """Останавливает цикл и закрывает соединение."""
        self.running = False
        if self.ws:
            await self.ws.close()

    def get_latest_data(self) -> Dict[str, Any]:
        """Возвращает последние полученные данные стакана."""
        return self.last_data
