import os
import csv
import json
import requests
import datetime
import telebot
from dotenv import load_dotenv
from threading import Thread, Event
import time

# Carga variables de .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # Tu ID de Telegram para recibir alertas

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Archivo de datos del portafolio
DATA_FILE = "data.json"

# Reglas de trading
SELL_FULL_LOSS = -0.12    # -12%
SELL_HALF_GAIN = 0.20     # +20%
SELL_QUARTER_GAIN = 0.35  # +35%
MAX_ALLOCATION = 0.5      # No más de 50% en una acción

# Symbols y link Stooq
SYMBOLS = {
    "NVIDIA": "NVDA.US",
    "TESLA": "TSLA.US",
    "SPY": "SPY.US",
    "QQQ": "QQQ.US"
}
STOQ_LINK = "https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"

# Control de hilos
stop_event = Event()

# Inicializa portafolio si no existe
if not os.path.exists(DATA_FILE):
    portfolio = {
        "balance_total": 280.98,
        "saldo_disponible": 1.16,
        "acciones": {
            "NVIDIA": {"unidades": 0.61, "precio_promedio": 178.41},
            "TESLA": {"unidades": 0.13, "precio_promedio": 382.06},
            "SPY": {"unidades": 0.13, "precio_promedio": 657.52},
            "QQQ": {"unidades": 0.05, "precio_promedio": 603.10}
        }
    }
    with open(DATA_FILE, "w") as f:
        json.dump(portfolio, f)
else:
    with open(DATA_FILE, "r") as f:
        portfolio = json.load(f)

# Función para obtener precio actual desde Stooq
def get_current_price(symbol):
    url = STOQ_LINK.format(symbol=symbol)
    try:
        response = requests.get(url)
        decoded = response.content.decode('utf-8').splitlines()
        reader = csv.DictReader(decoded)
        for row in reader:
            price = float(row['Close'])
            return price
    except Exception as e:
        print(f"Error al obtener precio de {symbol}: {e}")
        return None

# Función para calcular alertas de compra/venta
def check_trading_opportunities():
    alerts = []
    for name, symbol in SYMBOLS.items():
        data = portfolio["acciones"].get(name, {"unidades":0, "precio_promedio":0})
        precio_actual = get_current_price(symbol)
        if not precio_actual:
            continue
        unidades = data["unidades"]
        precio_prom = data["precio_promedio"]
        ganancia = (precio_actual - precio_prom) / precio_prom if precio_prom > 0 else 0

        # Venta por pérdida total
        if ganancia <= SELL_FULL_LOSS and unidades > 0:
            alerts.append(f"⚠️ {name}: cayó -12% → vender 100% ({unidades:.4f} acciones)")
            portfolio["saldo_disponible"] += unidades * precio_actual
            data["unidades"] = 0

        # Venta por ganancia +20%
        elif ganancia >= SELL_HALF_GAIN and unidades > 0:
            to_sell = unidades * 0.5
            alerts.append(f"💰 {name}: +20% → vender 50% ({to_sell:.4f} acciones)")
            portfolio["saldo_disponible"] += to_sell * precio_actual
            data["unidades"] -= to_sell

        # Venta adicional por +35%
        elif ganancia >= SELL_QUARTER_GAIN and unidades > 0:
            to_sell = unidades * 0.25
            alerts.append(f"💵 {name}: +35% → vender 25% adicional ({to_sell:.4f} acciones)")
            portfolio["saldo_disponible"] += to_sell * precio_actual
            data["unidades"] -= to_sell

        # Oportunidad de compra si saldo disponible >0
        if portfolio["saldo_disponible"] > 0:
            max_compra = portfolio["balance_total"] * MAX_ALLOCATION
            cantidad_compra = min(portfolio["saldo_disponible"], max_compra)
            unidades_compra = cantidad_compra / precio_actual
            if unidades_compra > 0:
                alerts.append(f"💡 Puedes comprar {name}: ${cantidad_compra:.2f} → {unidades_compra:.4f} acciones")
    
    # Guardar portafolio actualizado
    with open(DATA_FILE, "w") as f:
        json.dump(portfolio, f)
    
    return alerts

# Función para enviar informe diario
def send_daily_report():
    msg = f"📊 Informe de portafolio {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    msg += f"Balance total: ${portfolio['balance_total']:.2f}\n"
    msg += f"Saldo disponible: ${portfolio['saldo_disponible']:.2f}\n\n"
    for name, data in portfolio["acciones"].items():
        precio_actual = get_current_price(SYMBOLS[name])
        unidades = data["unidades"]
        precio_prom = data["precio_promedio"]
        ganancia = (precio_actual - precio_prom) / precio_prom if precio_prom > 0 else 0
        msg += f"- {name}: {unidades:.4f} acciones | Precio actual: ${precio_actual:.2f} | Ganancia: {ganancia*100:.2f}%\n"
    bot.send_message(CHAT_ID, msg)

# Hilo para alertas periódicas
def trading_loop():
    while not stop_event.is_set():
        alerts = check_trading_opportunities()
        for alert in alerts:
            bot.send_message(CHAT_ID, alert)
        time.sleep(60*5)  # Cada 5 minutos

# Comandos de Telegram
@bot.message_handler(commands=["start"])
def cmd_start(message):
    bot.send_message(message.chat.id, "🤖 Bot activo. Recibirás alertas de trading y reportes diarios.")

@bot.message_handler(commands=["balance"])
def cmd_balance(message):
    send_daily_report()

@bot.message_handler(commands=["aporte"])
def cmd_aporte(message):
    msg = bot.send_message(message.chat.id, "Ingresa el monto que depositaste esta semana:")
    bot.register_next_step_handler(msg, process_aporte)

def process_aporte(message):
    try:
        aporte = float(message.text)
        portfolio["saldo_disponible"] += aporte
        with open(DATA_FILE, "w") as f:
            json.dump(portfolio, f)
        bot.send_message(message.chat.id, f"Aporte recibido: ${aporte:.2f}. Saldo disponible actualizado: ${portfolio['saldo_disponible']:.2f}")
    except:
        bot.send_message(message.chat.id, "Error: ingresa un número válido.")

# Inicia el bot y el hilo de trading
if __name__ == "__main__":
    Thread(target=trading_loop, daemon=True).start()
    bot.infinity_polling()
