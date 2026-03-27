import os
import time
import json
import requests
import telebot
import threading
import redis
from telebot.types import ReplyKeyboardMarkup

# ================= CONFIGURACIÓN =================
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
if CHAT_ID:
    CHAT_ID = int(CHAT_ID)

# Conexión a Base de Datos Redis
REDIS_URL = os.getenv("REDIS_URL")
db = redis.from_url(REDIS_URL, decode_responses=True)

bot = telebot.TeleBot(TOKEN)

SYMBOLS = {
    "NVIDIA": "nvda.us",
    "Tesla": "tsla.us",
    "SPY": "spy.us",
    "QQQ": "qqq.us"
}

# ================= GESTIÓN DE DATOS (REDIS) =================
def load_data():
    stored = db.get("user_data")
    if stored:
        return json.loads(stored)
    else:
        # Valores iniciales si la base de datos está vacía
        initial = {
            "saldo": 0,
            "portfolio": {
                "NVIDIA": {"units": 0.62, "avg_price": 178.41},
                "Tesla": {"units": 0.13, "avg_price": 382.06},
                "SPY": {"units": 0.14, "avg_price": 657.52},
                "QQQ": {"units": 0.05, "avg_price": 603.10}
            }
        }
        db.set("user_data", json.dumps(initial))
        return initial

def save_data(current_data):
    db.set("user_data", json.dumps(current_data))

# Cargar datos al iniciar
user_data = load_data()

# ================= MOTOR DE MERCADO =================
def get_price(symbol):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            lines = r.text.strip().split("\n")
            if len(lines) > 1:
                price = lines[1].split(",")[6]
                if price != 'N/A':
                    return round(float(price), 2)
        return None
    except:
        return None

# ================= LÓGICA DE ANÁLISIS =================
def analyze(price, avg_price):
    if not price: return "⏳ SIN DATOS", "ESPERAR"
    change = ((price - avg_price) / avg_price) * 100
    
    if change <= -12: return "🔻 BAJADA FUERTE", "⚠️ VENDER (STOP LOSS)"
    elif change >= 35: return "🚀 EUPHORIA", "💰 VENDER 25% (PROFIT)"
    elif change >= 20: return "📈 SUBIDA", "VENDER 50%"
    elif change < -3: return "📉 CORRECCIÓN", "🛒 POSIBLE COMPRA"
    else: return "⚖️ LATERAL", "HOLD"

# ================= INTERFAZ DE TELEGRAM =================
def menu():
    m = ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("📊 Portafolio", "📈 Mercado")
    m.add("🧠 Recomendación", "💰 Actualizar saldo")
    return m

@bot.message_handler(commands=['start'])
def start(msg):
    bot.send_message(msg.chat.id, "🚀 Bot de Inversiones con Redis Activo", reply_markup=menu())

@bot.message_handler(func=lambda m: m.text == "📊 Portafolio")
def portfolio(msg):
    # Recargar datos de Redis para estar sincronizados
    curr_data = load_data()
    text = "📊 **TU PORTAFOLIO**\n" + "—" * 15 + "\n"
    total_market_val = 0
    total_invested = 0

    for asset, p in curr_data["portfolio"].items():
        price = get_price(SYMBOLS[asset])
        if price:
            val = p["units"] * price
            invested = p["units"] * p["avg_price"]
            profit = val - invested
            profit_pct = (profit / invested) * 100
            
            total_market_val += val
            total_invested += invested
            
            emoji = "🟢" if profit >= 0 else "🔴"
            text += f"🔹 **{asset}**: ${price}\n"
            text += f"   Valor: ${round(val,2)} ({emoji} {round(profit_pct,1)}%)\n"
        else:
            text += f"🔹 **{asset}**: Precio no disp.\n"

    total_profit_pct = ((total_market_val - total_invested) / total_invested) * 100 if total_invested > 0 else 0
    text += "—" * 15 + f"\n💰 **Total Acciones:** ${round(total_market_val,2)}\n"
    text += f"📈 **Rendimiento Global:** {round(total_profit_pct,2)}%\n"
    text += f"💵 **Saldo Cash:** ${curr_data['saldo']}"
    
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📈 Mercado")
def market(msg):
    text = "📈 **PRECIOS EN VIVO**\n"
    for name, sym in SYMBOLS.items():
        p = get_price(sym)
        text += f"• {name}: `${p if p else 'Cerrado'}`\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💰 Actualizar saldo")
def ask_saldo(msg):
    bot.send_message(msg.chat.id, "Envíame el comando: `saldo 100`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.startswith("saldo"))
def set_saldo(msg):
    try:
        new_val = float(msg.text.split()[1])
        curr_data = load_data()
        curr_data["saldo"] = new_val
        save_data(curr_data)
        bot.send_message(msg.chat.id, f"✅ Saldo en Redis actualizado: ${new_val}")
    except:
        bot.send_message(msg.chat.id, "❌ Error. Usa: saldo 50")

@bot.message_handler(func=lambda m: m.text == "🧠 Recomendación")
def recomendacion(msg):
    curr_data = load_data()
    text = "🧠 **ANÁLISIS DE ESTRATEGIA**\n\n"
    for asset, p in curr_data["portfolio"].items():
        price = get_price(SYMBOLS[asset])
        trend, action = analyze(price, p["avg_price"])
        text += f"● **{asset}**\n   Tendencia: {trend}\n   Acción: `{action}`\n\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# ================= MONITOR DE ALERTAS (HILO) =================
def alert_loop():
    while True:
        try:
            if CHAT_ID:
                text = "🔔 **REPORTE AUTOMÁTICO**\n"
                for name, sym in SYMBOLS.items():
                    p = get_price(sym)
                    text += f"{name}: ${p}\n"
                bot.send_message(CHAT_ID, text, parse_mode="Markdown")
            time.sleep(3600) 
        except:
            time.sleep(60)

# ================= EJECUCIÓN =================
if __name__ == "__main__":
    print("Bot Iniciado con Redis...")
    threading.Thread(target=alert_loop, daemon=True).start()
    bot.infinity_polling()
