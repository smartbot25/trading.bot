import os
import json
import logging
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ─────────────────────────────
# CONFIG
# ─────────────────────────────
load_dotenv()
TOKEN = os.getenv("TOKEN")

DATA_FILE = "data.json"

logging.basicConfig(level=logging.INFO)

# ─────────────────────────────
# DATA
# ─────────────────────────────
DEFAULT_DATA = {
    "saldo": 1.16,
    "positions": {
        "NVDA": {"buy": 178.41, "shares": 0.61},
        "TSLA": {"buy": 382.06, "shares": 0.13},
        "SPY":  {"buy": 657.52, "shares": 0.13},
        "QQQ":  {"buy": 603.10, "shares": 0.05}
    },
    "historial": []
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return DEFAULT_DATA

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, indent=2)

# ─────────────────────────────
# PRECIO (STOOQ)
# ─────────────────────────────
def get_price(symbol):
    try:
        url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
        r = requests.get(url, timeout=10)
        price = float(r.text.split("\n")[1].split(",")[6])
        return price
    except:
        return None

MAP = {
    "NVDA": "nvda.us",
    "TSLA": "tsla.us",
    "SPY": "spy.us",
    "QQQ": "qqq.us"
}

# ─────────────────────────────
# BOTONES
# ─────────────────────────────
def menu():
    return ReplyKeyboardMarkup(
        [
            ["📊 Cartera", "🧠 Analizar"],
            ["💰 Saldo", "➕ Compré"],
            ["📈 Mercado", "📜 Historial"]
        ],
        resize_keyboard=True
    )

# ─────────────────────────────
# START
# ─────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot PRO activo",
        reply_markup=menu()
    )

# ─────────────────────────────
# CARTERA
# ─────────────────────────────
async def cartera(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    msg = "📊 PORTAFOLIO\n\n"

    total = 0

    for k, v in data["positions"].items():
        price = get_price(MAP[k]) or v["buy"]
        value = price * v["shares"]
        pct = ((price - v["buy"]) / v["buy"]) * 100
        total += value

        msg += f"{k} → {v['shares']} acc | {pct:+.2f}%\n"

    msg += f"\n💰 Saldo: ${data['saldo']:.2f}"
    msg += f"\n💼 Total: ${total + data['saldo']:.2f}"

    await update.message.reply_text(msg)

# ─────────────────────────────
# MERCADO
# ─────────────────────────────
async def mercado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "📈 MERCADO\n\n"
    for k, s in MAP.items():
        p = get_price(s)
        if p:
            msg += f"{k}: ${p:.2f}\n"
    await update.message.reply_text(msg)

# ─────────────────────────────
# ANALISIS SIMPLE
# ─────────────────────────────
async def analizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    msg = "🧠 ANÁLISIS\n\n"

    for k, v in data["positions"].items():
        price = get_price(MAP[k])
        if not price:
            continue

        diff = ((price - v["buy"]) / v["buy"]) * 100

        if diff > 10:
            estado = "CARO ❌"
        elif diff < -5:
            estado = "BARATO ✅"
        else:
            estado = "NORMAL ⚖️"

        msg += f"{k} → {estado}\n"

    await update.message.reply_text(msg)

# ─────────────────────────────
# SALDO
# ─────────────────────────────
async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    await update.message.reply_text(f"💰 Saldo actual: ${data['saldo']:.2f}")

# ─────────────────────────────
# REGISTRAR COMPRA
# ─────────────────────────────
async def comprar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Escribe:\nSIMBOLO MONTO\nEj: NVDA 10")

# ─────────────────────────────
# PROCESAR TEXTO
# ─────────────────────────────
async def texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()

    data = load_data()

    try:
        sym, monto = txt.split()
        monto = float(monto)
        sym = sym.upper()

        if sym in MAP:
            price = get_price(MAP[sym])
            shares = monto / price

            data["saldo"] -= monto

            if sym in data["positions"]:
                data["positions"][sym]["shares"] += shares
            else:
                data["positions"][sym] = {"buy": price, "shares": shares}

            data["historial"].append({
                "tipo": "compra",
                "sym": sym,
                "monto": monto,
                "fecha": str(datetime.now())
            })

            save_data(data)

            await update.message.reply_text(
                f"✅ Compra registrada\n\n{sym}\n${monto}\n{shares:.4f} acciones"
            )
    except:
        pass

# ─────────────────────────────
# HISTORIAL
# ─────────────────────────────
async def historial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()

    msg = "📜 HISTORIAL\n\n"

    for h in data["historial"][-5:]:
        msg += f"{h['tipo']} {h['sym']} ${h['monto']}\n"

    await update.message.reply_text(msg)

# ─────────────────────────────
# MAIN
# ─────────────────────────────
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Regex("📊 Cartera"), cartera))
app.add_handler(MessageHandler(filters.Regex("🧠 Analizar"), analizar))
app.add_handler(MessageHandler(filters.Regex("💰 Saldo"), saldo))
app.add_handler(MessageHandler(filters.Regex("➕ Compré"), comprar))
app.add_handler(MessageHandler(filters.Regex("📈 Mercado"), mercado))
app.add_handler(MessageHandler(filters.Regex("📜 Historial"), historial))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, texto))

print("Bot corriendo...")
app.run_polling()
