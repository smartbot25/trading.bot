import os
import time
import json
import requests
import telebot
import threading
import redis
from telebot.types import ReplyKeyboardMarkup

# ================= CONFIGURACIÓN DE VARIABLES =================
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
if CHAT_ID:
    CHAT_ID = int(CHAT_ID)

# --- CONEXIÓN A REDIS (CON REINTENTOS) ---
REDIS_URL = os.getenv("REDIS_URL")
db = None

try:
    if REDIS_URL:
        # Configuración para evitar el error "Name or service not known"
        db = redis.from_url(
            REDIS_URL, 
            decode_responses=True,
            socket_connect_timeout=10,
            retry_on_timeout=True
        )
        db.ping() 
        print("✅ CONEXIÓN EXITOSA A REDIS")
    else:
        print("❌ ERROR: No se encontró REDIS_URL")
except Exception as e:
    print(f"❌ FALLO DE CONEXIÓN A REDIS: {e}")
    db = None

bot = telebot.TeleBot(TOKEN)

# Activos que monitoreamos en Stooq
SYMBOLS = {
    "NVIDIA": "nvda.us",
    "Tesla": "tsla.us",
    "SPY": "spy.us",
    "QQQ": "qqq.us"
}

# ================= GESTIÓN DE DATOS (REDIS) =================
def load_data():
    if db:
        try:
            stored = db.get("user_data")
            if stored:
                return json.loads(stored)
        except:
            pass
    
    # Valores iniciales si Redis está vacío
    return {
        "saldo": 0,
        "portfolio": {
            "NVIDIA": {"units": 0.62, "avg_price": 178.41},
            "Tesla": {"units": 0.13, "avg_price": 382.06},
            "SPY": {"units": 0.14, "avg_price": 657.52},
            "QQQ": {"units": 0.05, "avg_price": 603.10}
        }
    }

def save_data(current_data):
    if db:
        try:
            db.set("user_data", json.dumps(current_data))
        except Exception as e:
            print(f"Error guardando en Redis: {e}")

# ================= MOTOR DE PRECIOS (STOOQ) =================
def get_price(symbol):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            lines = r.text.strip().split("\n")
            if len(lines) > 1:
                price_str = lines[1].split(",")[6]
                if price_str != 'N/A':
                    return round(float(price_str), 2)
        return None
    except:
        return None

def analyze(price, avg_price):
    if not price: return "⏳ SIN DATOS", "ESPERAR"
    change = ((price - avg_price) / avg_price) * 100
    if change <= -12: return "🔻 BAJADA FUERTE", "⚠️ VENDER (STOP LOSS)"
    elif change >= 35: return "🚀 EUPHORIA", "💰 VENDER PROFIT"
    elif change < -3: return "📉 CORRECCIÓN", "🛒 POSIBLE COMPRA"
    else: return "⚖️ LATERAL", "HOLD"

# ================= INTERFAZ DE USUARIO =================
def menu():
    m = ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("📊 Portafolio", "📈 Mercado")
    m.add("🧠 Recomendación", "💰 Actualizar saldo")
    m.add("🛒 Registrar Compra")
    return m

@bot.message_handler(commands=['start'])
def start(msg):
    bot.send_message(msg.chat.id, "🚀 SmartBot Trading Activo (Conectado a Redis)", reply_markup=menu())

# --- FUNCIÓN PORTAFOLIO ---
@bot.message_handler(func=lambda m: m.text == "📊 Portafolio")
def portfolio(msg):
    data = load_data()
    text = "📊 **TU PORTAFOLIO**\n" + "—" * 15 + "\n"
    total_market = 0
    total_invested = 0

    for asset, p in data["portfolio"].items():
        price = get_price(SYMBOLS[asset])
        if price:
            val = p["units"] * price
            invested = p["units"] * p["avg_price"]
            profit = val - invested
            profit_pct = (profit / invested) * 100 if invested > 0 else 0
            total_market += val
            total_invested += invested
            emoji = "🟢" if profit >= 0 else "🔴"
            text += f"🔹 **{asset}**: ${price}\n   Valor: ${round(val,2)} ({emoji} {round(profit_pct,1)}%)\n"
    
    total_pct = ((total_market - total_invested) / total_invested) * 100 if total_invested > 0 else 0
    text += "—" * 15 + f"\n💰 **Total Acciones:** ${round(total_market,2)}\n"
    text += f"📈 **Rendimiento Global:** {round(total_pct,2)}%\n"
    text += f"💵 **Saldo Cash:** ${data['saldo']}"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# --- FUNCIÓN RECOMENDACIÓN (CALCULADORA TYBA) ---
@bot.message_handler(func=lambda m: m.text == "🧠 Recomendación")
def recomendacion(msg):
    data = load_data()
    saldo_cash = data.get("saldo", 0)
    text = "🧠 **ASISTENTE DE EJECUCIÓN TYBA**\n"
    text += f"💵 Efectivo disponible: `${saldo_cash}`\n"
    text += "—" * 20 + "\n\n"
    
    hay_oportunidad = False
    for asset, p in data["portfolio"].items():
        price = get_price(SYMBOLS[asset])
        trend, action = analyze(price, p["avg_price"])
        
        if "COMPRA" in action and price and saldo_cash > 0:
            hay_oportunidad = True
            monto_invertir = saldo_cash * 0.25
            unidades_a_comprar = monto_invertir / price
            text += f"🚨 **OPORTUNIDAD EN {asset}**\n"
            text += f"👉 **INSTRUCCIONES TYBA:**\n"
            text += f"✅ COMPRA: `{round(unidades_a_comprar, 4)}` unidades\n"
            text += f"✅ PAGA APROX: `${round(monto_invertir, 2)}` \n"
            text += "—" * 15 + "\n"

    if not hay_oportunidad:
        text += "⚖️ No hay oportunidades claras de compra o no tienes saldo suficiente."
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# --- GESTIÓN DE SALDO ---
@bot.message_handler(func=lambda m: m.text == "💰 Actualizar saldo")
def ask_saldo(msg):
    bot.send_message(msg.chat.id, "Escribe el comando: `saldo 35`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().startswith("saldo"))
def set_saldo(msg):
    try:
        valor = float(msg.text.replace("saldo", "").strip())
        data = load_data()
        data["saldo"] = valor
        save_data(data)
        bot.send_message(msg.chat.id, f"✅ Saldo guardado: `${valor}`")
    except:
        bot.send_message(msg.chat.id, "❌ Error. Usa: `saldo 100`")

# --- REGISTRO DE COMPRA (DCA) ---
@bot.message_handler(func=lambda m: m.text == "🛒 Registrar Compra")
def ask_buy(msg):
    bot.send_message(msg.chat.id, "Escribe: `comprar NVIDIA 0.1 165.50`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().startswith("comprar"))
def execute_buy(msg):
    try:
        p = msg.text.split()
        asset, n_units, b_price = p[1].upper(), float(p[2]), float(p[3])
        data = load_data()
        if asset in data["portfolio"]:
            old_u = data["portfolio"][asset]["units"]
            old_a = data["portfolio"][asset]["avg_price"]
            total_u = old_u + n_units
            new_a = ((old_u * old_a) + (n_units * b_price)) / total_u
            data["portfolio"][asset]["units"] = round(total_u, 4)
            data["portfolio"][asset]["avg_price"] = round(new_a, 2)
            save_data(data)
            bot.send_message(msg.chat.id, f"✅ Compra registrada. Nuevo promedio {asset}: ${round(new_a, 2)}")
    except:
        bot.send_message(msg.chat.id, "❌ Error en formato de compra.")

# --- MERCADO ---
@bot.message_handler(func=lambda m: m.text == "📈 Mercado")
def market(msg):
    text = "📈 **PRECIOS EN VIVO**\n"
    for name, sym in SYMBOLS.items():
        p = get_price(sym)
        text += f"• {name}: `${p if p else 'Cerrado'}`\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# --- HILO DE ALERTAS ---
def alert_loop():
    while True:
        try:
            if CHAT_ID:
                data = load_data()
                # (Lógica de alerta de pánico aquí...)
            time.sleep(14400) # 4 horas
        except:
            time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=alert_loop, daemon=True).start()
    bot.infinity_polling()

