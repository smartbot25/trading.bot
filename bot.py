import os
import csv
import json
import time
import requests
import telebot
from dotenv import load_dotenv
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from threading import Thread

# ───────── CONFIG ─────────
load_dotenv()
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = telebot.TeleBot(TOKEN)

DATA_FILE = "data.json"

STOOQ_URL = "https://stooq.com/q/l/?s={}&f=sd2t2ohlcv&h&e=csv"

SYMBOLS = {
    "NVDA": "nvda.us",
    "TSLA": "tsla.us",
    "SPY": "spy.us",
    "QQQ": "qqq.us"
}

STOP_LOSS = -0.12
TP1 = 0.20
TP2 = 0.35

# ───────── DATA ─────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {
        "saldo": 0,
        "positions": {}
    }

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, indent=2)

data = load_data()

# ───────── TECLADO ─────────
def menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📊 Cartera", "🧠 Analizar")
    kb.row("💰 Saldo", "➕ Compré")
    return kb

# ───────── PRECIO ─────────
def get_price(symbol):
    try:
        r = requests.get(STOOQ_URL.format(symbol), timeout=10)
        lines = r.text.splitlines()
        return float(lines[1].split(",")[6])
    except:
        return None

# ───────── COMANDOS ─────────
@bot.message_handler(commands=["start"])
def start(msg):
    bot.send_message(msg.chat.id, "🤖 Bot PRO activo", reply_markup=menu())

# ───────── BOTONES ─────────
@bot.message_handler(func=lambda m: True)
def handle(msg):
    text = msg.text

    # ── CARTERA ──
    if text == "📊 Cartera":
        out = "📊 TU PORTAFOLIO\n\n"
        for sym, pos in data["positions"].items():
            price = get_price(SYMBOLS[sym])
            if not price:
                continue
            pct = (price - pos["buy"]) / pos["buy"] * 100
            out += f"{sym}: {pos['shares']} acc | {pct:+.1f}%\n"
        out += f"\n💰 Saldo: ${data['saldo']:.2f}"
        bot.send_message(msg.chat.id, out)

    # ── SALDO ──
    elif text == "💰 Saldo":
        msg2 = bot.send_message(msg.chat.id, "Ingresa saldo:")
        bot.register_next_step_handler(msg2, set_saldo)

    # ── ANALIZAR ──
    elif text == "🧠 Analizar":
        analizar(msg.chat.id)

    # ── COMPRÉ ──
    elif text == "➕ Compré":
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for s in SYMBOLS:
            kb.add(s)
        msg2 = bot.send_message(msg.chat.id, "¿Qué compraste?", reply_markup=kb)
        bot.register_next_step_handler(msg2, comprar)

# ───────── FUNCIONES ─────────
def set_saldo(msg):
    try:
        monto = float(msg.text)
        data["saldo"] = monto
        save_data(data)
        bot.send_message(msg.chat.id, f"Saldo actualizado: ${monto}", reply_markup=menu())
    except:
        bot.send_message(msg.chat.id, "Error", reply_markup=menu())

def comprar(msg):
    sym = msg.text.upper()
    if sym not in SYMBOLS:
        bot.send_message(msg.chat.id, "Error", reply_markup=menu())
        return

    price = get_price(SYMBOLS[sym])
    if not price:
        bot.send_message(msg.chat.id, "Error precio", reply_markup=menu())
        return

    monto = data["saldo"] * 0.25
    shares = monto / price

    data["saldo"] -= monto

    data["positions"][sym] = {
        "buy": price,
        "shares": round(shares, 4)
    }

    save_data(data)

    bot.send_message(
        msg.chat.id,
        f"✅ Compra registrada\n{sym}\n${monto:.2f}\n{shares:.4f} acciones",
        reply_markup=menu()
    )

def analizar(chat_id):
    saldo = data["saldo"]

    for sym, stooq in SYMBOLS.items():
        price = get_price(stooq)
        if not price:
            continue

        pos = data["positions"].get(sym)

        # SI TIENES POSICIÓN → VENDER
        if pos:
            pct = (price - pos["buy"]) / pos["buy"]

            if pct <= STOP_LOSS:
                bot.send_message(chat_id, f"🔴 {sym} VENDER TODO")

            elif pct >= TP1:
                bot.send_message(chat_id, f"🟢 {sym} VENDER 50%")

            elif pct >= TP2:
                bot.send_message(chat_id, f"🟢 {sym} VENDER 25%")

        # SI NO TIENES → COMPRA
        else:
            if saldo > 5:
                monto = saldo * 0.25
                acciones = monto / price

                bot.send_message(
                    chat_id,
                    f"💡 {sym}\nCompra ${monto:.2f}\n{acciones:.4f} acciones"
                )

# ───────── LOOP ─────────
def loop():
    while True:
        try:
            analizar(CHAT_ID)
            time.sleep(300)
        except:
            time.sleep(60)

# ───────── START ─────────
if __name__ == "__main__":
    Thread(target=loop, daemon=True).start()
    bot.infinity_polling()
