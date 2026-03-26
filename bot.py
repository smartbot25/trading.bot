import os
import time
import json
import requests
import telebot
from telebot.types import ReplyKeyboardMarkup

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

bot = telebot.TeleBot(TOKEN)

DATA_FILE = "data.json"

SYMBOLS = {
    "NVIDIA": "nvda.us",
    "Tesla": "tsla.us",
    "SPY": "spy.us",
    "QQQ": "qqq.us"
}

# ================= DATA =================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "saldo": 0,
            "portfolio": {
                "NVIDIA": {"units": 0.62, "avg_price": 178.41},
                "Tesla": {"units": 0.13, "avg_price": 382.06},
                "SPY": {"units": 0.14, "avg_price": 657.52},
                "QQQ": {"units": 0.05, "avg_price": 603.10}
            }
        }
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

# ================= MARKET =================
def get_price(symbol):
    try:
        url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
        r = requests.get(url).text.split("\n")[1]
        return float(r.split(",")[6])
    except:
        return None

# ================= ANALYSIS =================
def analyze(asset, price, avg_price):
    if not price:
        return "SIN DATOS", "ESPERAR"

    change = ((price - avg_price) / avg_price) * 100

    if change <= -12:
        return "BAJADA FUERTE", "VENDER TODO"
    elif change >= 35:
        return "SUBIDA FUERTE", "VENDER 25%"
    elif change >= 20:
        return "SUBIDA", "VENDER 50%"
    elif change < -3:
        return "CORRECCIÓN", "POSIBLE COMPRA"
    else:
        return "LATERAL", "ESPERAR"

# ================= UI =================
def menu():
    m = ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("📊 Portafolio", "📈 Mercado")
    m.add("🧠 Recomendación", "💰 Actualizar saldo")
    return m

# ================= BOTONES =================
@bot.message_handler(commands=['start'])
def start(msg):
    bot.send_message(msg.chat.id, "🚀 Bot activo", reply_markup=menu())

@bot.message_handler(func=lambda m: m.text == "📊 Portafolio")
def portfolio(msg):
    text = "📊 TU PORTAFOLIO\n\n"
    total = 0

    for asset in data["portfolio"]:
        p = data["portfolio"][asset]
        price = get_price(SYMBOLS[asset])
        value = p["units"] * price if price else 0
        total += value

        text += f"{asset}\n"
        text += f"Unidades: {p['units']}\n"
        text += f"Promedio: ${p['avg_price']}\n"
        text += f"Hoy: ${price}\n"
        text += f"Valor: ${round(value,2)}\n\n"

    text += f"💰 Total: ${round(total,2)}\n"
    text += f"💵 Saldo: ${data['saldo']}"

    bot.send_message(msg.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "📈 Mercado")
def market(msg):
    text = "📈 MERCADO\n\n"
    for name, sym in SYMBOLS.items():
        price = get_price(sym)
        text += f"{name}: ${price}\n"
    bot.send_message(msg.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "💰 Actualizar saldo")
def ask_saldo(msg):
    bot.send_message(msg.chat.id, "Escribe tu saldo así:\nsaldo 40")

@bot.message_handler(func=lambda m: m.text.startswith("saldo"))
def set_saldo(msg):
    try:
        amount = float(msg.text.split()[1])
        data["saldo"] = amount
        save_data(data)
        bot.send_message(msg.chat.id, f"✅ Saldo actualizado: ${amount}")
    except:
        bot.send_message(msg.chat.id, "Formato incorrecto")

@bot.message_handler(func=lambda m: m.text == "🧠 Recomendación")
def recomendacion(msg):
    saldo = data["saldo"]
    text = "🧠 ANÁLISIS\n\n"

    for asset in data["portfolio"]:
        p = data["portfolio"][asset]
        price = get_price(SYMBOLS[asset])
        trend, action = analyze(asset, price, p["avg_price"])

        text += f"{asset}\n"
        text += f"Precio: ${price}\n"
        text += f"Tendencia: {trend}\n"

        if action == "POSIBLE COMPRA" and saldo > 10:
            invertir = round(saldo * 0.3, 2)
            acciones = invertir / price

            text += "📢 OPORTUNIDAD\n"
            text += f"Invertir: ${invertir}\n"
            text += f"Comprar: {acciones:.4f}\n"
            text += f"Saldo restante: ${round(saldo - invertir,2)}\n\n"

        elif "VENDER" in action:
            text += f"⚠️ {action}\n\n"
        else:
            text += "Esperar\n\n"

    bot.send_message(msg.chat.id, text)

# ================= ALERTAS =================
def alert_loop():
    while True:
        try:
            text = "📊 MONITOREO\n\n"
            for name, sym in SYMBOLS.items():
                price = get_price(sym)
                text += f"{name}: ${price}\n"

            bot.send_message(CHAT_ID, text)
            time.sleep(3600)
        except:
            time.sleep(60)

# ================= START =================
if __name__ == "__main__":
    print("Bot corriendo...")
    bot.infinity_polling()
