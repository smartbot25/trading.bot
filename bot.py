import os
import csv
import json
import time
import requests
import telebot
from dotenv import load_dotenv
from threading import Thread
from datetime import datetime, timezone

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

# reglas
STOP_LOSS = -0.12
TP1 = 0.20
TP2 = 0.35

# ───────── DATA ─────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {
        "saldo": 1.16,
        "positions": {
            "NVDA": {"buy": 178.41, "shares": 0.61},
            "TSLA": {"buy": 382.06, "shares": 0.13},
            "SPY": {"buy": 657.52, "shares": 0.13},
            "QQQ": {"buy": 603.10, "shares": 0.05},
        }
    }

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

data = load_data()

# ───────── PRECIO ─────────
def get_price(symbol):
    try:
        url = STOOQ_URL.format(symbol)
        r = requests.get(url, timeout=10)
        lines = r.text.splitlines()
        return float(lines[1].split(",")[6])
    except:
        return None

# ───────── LÓGICA ─────────
def analizar():
    mensajes = []

    for sym, stooq in SYMBOLS.items():
        price = get_price(stooq)
        if not price:
            continue

        pos = data["positions"].get(sym)
        if not pos:
            continue

        buy = pos["buy"]
        shares = pos["shares"]

        pct = (price - buy) / buy

        # STOP LOSS
        if pct <= STOP_LOSS:
            mensajes.append(
                f"🔴 {sym}\nVENDER TODO\n"
                f"{shares:.4f} acciones\n"
                f"${shares*price:.2f}"
            )

        # TAKE PROFIT 1
        elif pct >= TP1:
            vender = shares * 0.5
            mensajes.append(
                f"🟢 {sym}\nVENDER 50%\n"
                f"{vender:.4f} acciones\n"
                f"${vender*price:.2f}"
            )

        # TAKE PROFIT 2
        elif pct >= TP2:
            vender = shares * 0.25
            mensajes.append(
                f"🟢 {sym}\nVENDER 25%\n"
                f"{vender:.4f} acciones\n"
                f"${vender*price:.2f}"
            )

    # COMPRA
    saldo = data["saldo"]

    if saldo > 5:
        for sym, stooq in SYMBOLS.items():
            price = get_price(stooq)
            if not price:
                continue

            monto = saldo * 0.25
            acciones = monto / price

            mensajes.append(
                f"💡 COMPRA {sym}\n"
                f"Usa: ${monto:.2f}\n"
                f"{acciones:.4f} acciones"
            )

    return mensajes

# ───────── LOOP ─────────
def loop():
    while True:
        try:
            mensajes = analizar()
            for m in mensajes:
                bot.send_message(CHAT_ID, m)
            time.sleep(300)
        except Exception as e:
            print("Error:", e)
            time.sleep(60)

# ───────── COMANDOS ─────────
@bot.message_handler(commands=["start"])
def start(msg):
    bot.send_message(msg.chat.id, "✅ Bot activo y monitoreando mercado")

@bot.message_handler(commands=["saldo"])
def saldo(msg):
    bot.send_message(msg.chat.id, f"💰 Saldo: ${data['saldo']:.2f}")

@bot.message_handler(commands=["setsaldo"])
def setsaldo(msg):
    try:
        monto = float(msg.text.split()[1])
        data["saldo"] = monto
        save_data(data)
        bot.send_message(msg.chat.id, f"Saldo actualizado: ${monto}")
    except:
        bot.send_message(msg.chat.id, "Uso: /setsaldo 50")

# ───────── INICIO ─────────
if __name__ == "__main__":
    bot.send_message(CHAT_ID, "🚀 Bot iniciado en Railway")
    Thread(target=loop, daemon=True).start()
    bot.infinity_polling()
