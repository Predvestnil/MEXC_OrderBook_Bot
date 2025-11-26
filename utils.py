# utils.py
from datetime import datetime

def format_compact_price(price):
    """
    Форматирует цену в компактный вид.
    Если цена имеет много нулей (например, 0.00000000123), используется нотация 0.0{8}123.
    Если цена > 1, отображается с двумя знаками после запятой.
    """
    f_price = float(price)
    
    # Если цена больше 1, используем стандартный формат (например, 45,000.00)
    if f_price > 1.0:
        return f"{f_price:,.2f}"
    
    # Преобразуем в строку с высокой точностью, чтобы избежать научной нотации (1e-10)
    # 20 знаков обычно достаточно для любой крипты
    s_price = f"{f_price:.20f}".rstrip('0')
    
    if '.' not in s_price:
        return s_price

    integer_part, decimal_part = s_price.split('.')
    
    # Считаем ведущие нули в дробной части
    leading_zeros = 0
    for char in decimal_part:
        if char == '0':
            leading_zeros += 1
        else:
            break
    
    # Порог срабатывания: если нулей больше 3 (например, 0.00005)
    if leading_zeros > 3:
        # Берем 4 значащих цифры после нулей
        significant_digits = decimal_part[leading_zeros:][:5]
        return f"0.0{{{leading_zeros}}}{significant_digits}"
    
    # Если нулей мало (например, 0.0012), просто возвращаем как есть (до 8 знаков)
    return f"{f_price:.8f}".rstrip('0')

def format_orderbook(symbol, data, depth):
    """
    Формирует финальный текст стакана для Telegram-сообщения.
    Использует невидимые символы (U+2800, '⠀') для выравнивания.
    data: структура {'asks': [{'price': ..., 'quantity': ...}], 'bids': ...}
    """
    if not data or not data.get('asks') or not data.get('bids'):
        return "⏳ Ожидание данных стакана..."

    # Берем срез данных согласно глубине
    asks = data['asks'][:depth]
    bids = data['bids'][:depth]
    
    # Инвертируем asks, чтобы самые дешевые продажи были внизу (ближе к спреду)
    asks = asks[::-1] 

    # Визуальный прогресс бар (эмуляция давления)
    try:
        total_ask_vol = sum(float(a['quantity']) for a in asks)
        total_bid_vol = sum(float(b['quantity']) for b in bids)
        total = total_ask_vol + total_bid_vol if (total_ask_vol + total_bid_vol) > 0 else 1
        
        buy_ratio = int((total_bid_vol / total) * 10) # Соотношение покупок (0-10)
        sell_ratio = 10 - buy_ratio
        progress_bar = f"[{'🟥' * sell_ratio}{'🟩' * buy_ratio}]"
    except Exception:
        progress_bar = "[-----]"
    
    time_now = datetime.now().strftime("%H:%M:%S")
    
    # Заголовки и начало списка
    lines = [f"📊 {symbol} | {time_now}", progress_bar, "", "🔴 SELL (Asks):"]
    
    # --- Форматирование ASK (Продажи) ---
    for ask in asks:
        p = format_compact_price(ask['price'])
        v = float(ask['quantity'])
        # Форматируем объем: если большой - без дробей, если маленький - с дробями
        v_str = f"{v:,.0f}" if v > 100 else f"{v:.4f}"
        v_usd = v * float(ask['price'])
        # Выравнивание с помощью невидимых символов '⠀'
        t1 = '⠀' * (12 - len(p))  # Выравнивание по цене
        t2 = '⠀' * (12 - len(v_str))  # Выравнивание по объему
        lines.append(f"{p} {t1}| {v_str} {t2}| ${v_usd:,.2f}")
        
    lines.append("")
    lines.append("🟢 BUY (Bids):")
    
    # --- Форматирование BID (Покупки) ---
    for bid in bids:
        p = format_compact_price(bid['price'])
        v = float(bid['quantity'])
        v_str = f"{v:,.0f}" if v > 100 else f"{v:.4f}"
        v_usd = v * float(bid['price'])
        # Выравнивание с помощью невидимых символов '⠀'
        t1 = '⠀' * (12 - len(p))  # Выравнивание по цене
        t2 = '⠀' * (12 - len(v_str))  # Выравнивание по объему
        lines.append(f"{p} {t1}| {v_str} {t2}| ${v_usd:,.2f}")
        
    # --- Расчет и вывод спреда ---
    if asks and bids:
        try:
            best_ask = float(asks[-1]['price']) # Самый нижний ask
            best_bid = float(bids[0]['price'])  # Самый верхний bid
            spread = best_ask - best_bid
            spread_percent = (spread / best_ask) * 100
            lines.append("")
            lines.append(f"Spread: {spread_percent:.3f}%")
        except Exception:
            pass
            
    return "\n".join(lines)