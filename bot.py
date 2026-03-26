import os
import json
import requests
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# Configuración de logs
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

load_dotenv()

# --- VARIABLES DE ENTORNO ---
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
DATA_FILE = "data.json"

# Estados para conversaciones
ESPERANDO_DEPOSITO, ESPERANDO_COMPRA_TICKER, ESPERANDO_COMPRA_MONTO = range(3)

# --- BASE DE DATOS LOCAL ---
DEFAULT_DATA = {
    "saldo_efectivo": 1.16,
    "positions": {
        "NVDA": {"buy": 178.41, "shares": 0.61656428},
        "TSLA": {"buy": 382.06, "shares": 0.13086881},
        "SPY":  {"buy": 657.52, "shares": 0.13687838},
        "QQQ":  {"buy": 603.10, "shares": 0.05}
    },
    "historial": []
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f: return json.load(f)
    return DEFAULT_DATA

def save_data(d):
    with open(DATA_FILE, "w") as f: json.dump(d, f, indent=4)

def get_price(ticker):
    try:
        url = f"https://query1.finance.yahoo.com{ticker}?interval=1m&range=1d"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10).json()
        return r['chart']['result'][0]['meta']['regularMarketPrice']
    except: return None

# --- FUNCIONES DE LÓGICA ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Verificación de seguridad
    if str(update.effective_chat.id) != str(CHAT_ID):
        return await update.message.reply_text("❌ No autorizado.")

    kb = [['📊 Cartera', '🔍 Analizar'], ['💰 Saldo/Depósito', '➕ Registrar Compra']]
    await update.message.reply_text(
        "🚀 *Tyba Financial Advisor Pro*\nBienvenido, analista. ¿Qué deseas gestionar hoy?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True)
    )

async def mostrar_cartera(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    msg = "📊 *ESTADO DE TU PORTAFOLIO*\n\n"
    total_inv = 0
    
    for t, i in data["positions"].items():
        p = get_price(t) or i["buy"]
        v_actual = p * i["shares"]
        gain_pct = ((p - i["buy"]) / i["buy"]) * 100
        total_inv += v_actual
        icon = "📈" if gain_pct >= 0 else "📉"
        msg += f"{icon} *{t}*: ${v_actual:.2f} ({gain_pct:+.2f}%)\n   _P. Promedio: ${i['buy']:.2f}_\n"
    
    saldo = data["saldo_efectivo"]
    msg += f"\n💵 *Efectivo:* ${saldo:.2f}\n🔥 *TOTAL:* ${total_inv + saldo:.2f}"
    await update.message.reply_text(msg, parse_mode="Markdown")

# --- GESTIÓN DE DEPÓSITO ---
async def iniciar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 *Depósito:* ¿Cuánto dinero ingresaste a Tyba?")
    return ESPERANDO_DEPOSITO

async def procesar_deposito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        monto = float(update.message.text)
        data = load_data()
        data["saldo_efectivo"] += monto
        data["historial"].append({"tipo": "deposito", "monto": monto, "fecha": str(datetime.now())})
        save_data(data)
        await update.message.reply_text(f"✅ Saldo actualizado: *${data['saldo_efectivo']:.2f}*", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Error. Envía solo el número.")
    return ConversationHandler.END

# --- ANÁLISIS ---
async def analizar_mercado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    msg = "🔍 *ANÁLISIS DE OPORTUNIDADES*\n\n"
    found = False
    for t, i in data["positions"].items():
        p = get_price(t)
        if not p: continue
        diff = ((p - i["buy"]) / i["buy"]) * 100
        if diff <= -5:
            sugerencia = (data["saldo_efectivo"] * 0.10) # Sugiere usar 10% del saldo
            msg += f"💎 *{t} en descuento:* ({diff:.1f}%)\nSugerencia: Compra *${sugerencia:.2f}* para promediar.\n\n"
            found = True
        elif diff >= 20:
            msg += f"💰 *{t} en ganancias:* (+{diff:.1f}%)\nSugerencia: Vende el 25% para asegurar.\n\n"
            found = True
    
    if not found: msg += "😴 El mercado está estable. No hay acciones en zona crítica."
    await update.message.reply_text(msg, parse_mode="Markdown")

# --- MAIN ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Manejador de conversación para depósitos
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^💰 Saldo/Depósito$'), iniciar_deposito)],
        states={ESPERANDO_DEPOSITO: [MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_deposito)]},
        fallbacks=[]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex('^📊 Cartera$'), mostrar_cartera))
    app.add_handler(MessageHandler(filters.Regex('^🔍 Analizar$'), analizar_mercado))
    app.add_handler(conv_handler)
    
    print("Bot Activo...")
    app.run_polling()
