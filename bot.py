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

# --- CONEXIÓN A REDIS (Memoria Permanente) ---
REDIS_URL = os.getenv("REDIS_URL")
db = None

try:
    if REDIS_URL:
        # Conexión con reintentos para estabilidad en la nube
        db = redis.from_url(
            REDIS_URL, 
            decode_responses=True, 
            socket_timeout=10,
            retry_on_timeout=True
        )
        db.ping()
        print("✅ CONEXIÓN EXITOSA A REDIS")
    else:
        print("❌ ERROR: Variable REDIS_URL no encontrada.")
except Exception as e:
    print(f"⚠️ FALLO DE CONEXIÓN A REDIS: {e}")
    db = None

bot = telebot.TeleBot(TOKEN)

SYMBOLS = {
    "NVIDIA": "nvda.us",
    "Tesla": "tsla.us",
    "SPY": "spy.us",
    "QQQ": "qqq.us"
}

# ================= GESTIÓN DE DATOS (REDIS / BACKUP) =================
def load_data():
    # Intentar cargar desde Redis
    if db:
        try:
            stored = db.get("user_data")
            if stored:
                return json.loads(stored)
        except Exception as e:
            print(f"Error leyendo de Redis: {e}")
    
    # Valores por defecto si falla Redis o es la primera vez
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

# Cargar datos iniciales
user_data = load_data()

# ================= MOTOR DE MERCADO (STOOQ) =================
def get_price(symbol):
    try:
        # User-Agent para evitar bloqueos de Stooq
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
        r = requests.get(url, headers=headers, timeout=15)
        
        if r.status_code == 200:
            lines = r.text.strip().split("\n")
            if len(lines) > 1:
                price_str = lines[1].split(",")[6]
                if price_str != 'N/A':
                    return round(float(price_str), 2)
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
    bot.send_message(msg.chat.id, "🚀 SmartBot Inversiones (Redis) Activo", reply_markup=menu())

@bot.message_handler(func=lambda m: m.text == "📊 Portafolio")
def portfolio(msg):
    # Recargar datos frescos de Redis
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
            profit_pct = (profit / invested) * 100
            
            total_market += val
            total_invested += invested
            
            emoji = "🟢" if profit >= 0 else "🔴"
            text += f"🔹 **{asset}**: ${price}\n"
            text += f"   Valor: ${round(val,2)} ({emoji} {round(profit_pct,1)}%)\n"
        else:
            text += f"🔹 **{asset}**: Precio N/D\n"

    total_pct = ((total_market - total_invested) / total_invested) * 100 if total_invested > 0 else 0
    text += "—" * 15 + f"\n💰 **Total Acciones:** ${round(total_market,2)}\n"
    text += f"📈 **Rendimiento Global:** {round(total_pct,2)}%\n"
    text += f"💵 **Saldo Cash:** ${data['saldo']}"
    
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
    bot.send_message(msg.chat.id, "Escribe: `saldo 100`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.startswith("saldo"))
def set_saldo(msg):
    try:
        new_val = float(msg.text.split()[1])
        data = load_data()
        data["saldo"] = new_val
        save_data(data)
        bot.send_message(msg.chat.id, f"✅ Saldo guardado en Redis: ${new_val}")
    except:
        bot.send_message(msg.chat.id, "❌ Error. Formato: `saldo 50`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🧠 Recomendación")
def recomendacion(msg):
    data = load_data()
    text = "🧠 **ANÁLISIS DE ESTRATEGIA**\n\n"
    for asset, p in data["portfolio"].items():
        price = get_price(SYMBOLS[asset])
        trend, action = analyze(price, p["avg_price"])
        text += f"● **{asset}**\n   Tendencia: {trend}\n   Acción: `{action}`\n\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")

# ================= MONITOR DE ALERTAS (HILO) =================
def alert_loop():
    while True:
        try:
            if CHAT_ID:
                text = "🔔 **REPORTE HORARIO**\n"
                for name, sym in SYMBOLS.items():
                    p = get_price(sym)
                    text += f"{name}: ${p}\n"
                bot.send_message(CHAT_ID, text, parse_mode="Markdown")
            time.sleep(3600) 
        except:
            time.sleep(60)
# ================= COMANDO DE COMPRA (DCA) =================
@bot.message_handler(func=lambda m: m.text == "🛒 Registrar Compra")
def ask_buy(msg):
    instrucciones = (
        "📝 **Cómo registrar una compra:**\n\n"
        "Escribe el comando así:\n"
        "`comprar NVIDIA 0.1 145.50`\n\n"
        "*(Activo, Unidades nuevas, Precio pagado)*"
    )
    bot.send_message(msg.chat.id, instrucciones, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.startswith("comprar"))
def execute_buy(msg):
    try:
        # Ejemplo: comprar NVIDIA 0.1 145.50
        parts = msg.text.split()
        asset = parts[1].upper()
        new_units = float(parts[2])
        buy_price = float(parts[3])

        data = load_data() # Carga de Redis

        if asset in data["portfolio"]:
            old_units = data["portfolio"][asset]["units"]
            old_avg = data["portfolio"][asset]["avg_price"]

            # FÓRMULA MATEMÁTICA DEL PROMEDIO (DCA)
            total_units = old_units + new_units
            new_avg = ((old_units * old_avg) + (new_units * buy_price)) / total_units

            # Actualizar datos
            data["portfolio"][asset]["units"] = round(total_units, 4)
            data["portfolio"][asset]["avg_price"] = round(new_avg, 2)
            
            save_data(data) # Guarda en Redis
            
            res = f"✅ **{asset} Actualizado**\n"
            res += f"Nuevas Unidades: {round(total_units, 4)}\n"
            res += f"Nuevo Promedio: ${round(new_avg, 2)}"
            bot.send_message(msg.chat.id, res, parse_mode="Markdown")
        else:
            bot.send_message(msg.chat.id, "❌ Ese activo no está en tu lista.")
    except Exception as e:
        bot.send_message(msg.chat.id, "❌ Error. Usa: `comprar ACTIVO UNIDADES PRECIO`")

# No olvides agregar el botón al menú principal
def menu():
    m = ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("📊 Portafolio", "📈 Mercado")
    m.add("🧠 Recomendación", "💰 Actualizar saldo")
    m.add("🛒 Registrar Compra") # <-- Agrega esta línea
    return m

# ================= INICIO =================
if __name__ == "__main__":
    print("Bot Iniciado...")
    # Hilo para alertas en paralelo
    threading.Thread(target=alert_loop, daemon=True).start()
    # Polling infinito
    bot.infinity_polling()
