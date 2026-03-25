"""
BOT PRO v10 — CONTROL TOTAL DESDE TELEGRAM

✔ Botones interactivos
✔ Actualizar posiciones sin archivos
✔ Saldo TYBA desde Telegram
✔ Reglas automáticas (-12%, +20%, +35%)
✔ Cantidades exactas
✔ Acción diaria
"""

import os
import json
import time
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# ───── CONFIG ─────
load_dotenv()
TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

URL = f"https://api.telegram.org/bot{TOKEN}"

DATA_FILE = "data.json"
ALERTS_FILE = "alerts.json"

ACTIVOS = ["NVDA","TSLA","SPY","QQQ"]

BUY_LEVELS = {
    "NVDA":170,
    "TSLA":360,
    "SPY":600,
    "QQQ":580
}

# ───── DATA ─────
def load_json(file, default):
    try:
        with open(file,"r") as f:
            return json.load(f)
    except:
        return default

def save_json(file,data):
    with open(file,"w") as f:
        json.dump(data,f,indent=2)

data = load_json(DATA_FILE, {"tyba":0,"positions":{}})
alerts = set(load_json(ALERTS_FILE, []))

# ───── TELEGRAM ─────
def send(msg, keyboard=None):
    payload = {
        "chat_id": CHAT_ID,
        "text": msg
    }
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)

    requests.post(f"{URL}/sendMessage", data=payload)

# ───── BOTONES ─────
def menu():
    keyboard = {
        "keyboard":[
            ["📊 Estado","💰 TYBA"],
            ["➕ Actualizar","❌ Vender"],
            ["📌 Acción"]
        ],
        "resize_keyboard":True
    }
    send("📲 MENÚ PRINCIPAL", keyboard)

# ───── PRECIOS ─────
def price(sym):
    try:
        r = requests.get(f"https://stooq.com/q/l/?s={sym.lower()}.us&f=sd2t2ohlcv&h&e=csv")
        return float(r.text.split("\n")[1].split(",")[6])
    except:
        return None

# ───── LOGICA ─────
def analizar():
    accion = "NO HACER NADA"
    saldo = data.get("tyba",0)

    for name, pos in data["positions"].items():
        p = price(name)
        if not p: continue

        buy = pos["buy"]
        shares = pos["shares"]
        actual = shares * p

        pct = ((p - buy)/buy)*100

        if pct <= -12:
            send(f"🔴 VENDER TODO {name}\n{shares} acciones\n${actual:.2f}")
            accion = "VENDER"

        elif pct >= 35:
            vender = round(shares*0.25,4)
            send(f"🟢 VENDER 25% {name}\n{vender} acciones")
            accion = "VENDER PARCIAL"

        elif pct >= 20:
            vender = round(shares*0.5,4)
            send(f"🟢 VENDER 50% {name}\n{vender} acciones")
            accion = "VENDER PARCIAL"

    for name in ACTIVOS:
        if name not in data["positions"]:
            p = price(name)
            if p and p < BUY_LEVELS[name] and saldo > 0:
                acciones = round(saldo/p,4)
                send(f"🟢 COMPRAR {name}\n${saldo} → {acciones} acciones")
                accion = "COMPRAR"

    send(f"📌 ACCION HOY:\n👉 {accion}")

# ───── COMANDOS ─────
def handle(text):
    if text == "/start":
        menu()

    elif text == "📊 Estado":
        msg = "📊 PORTAFOLIO\n\n"
        for k,v in data["positions"].items():
            msg += f"{k}: {v['shares']} @ ${v['buy']}\n"
        send(msg)

    elif text == "💰 TYBA":
        send(f"Saldo: ${data['tyba']}")

    elif text.startswith("/settyba"):
        val = float(text.split()[1])
        data["tyba"] = val
        save_json(DATA_FILE,data)
        send("✅ actualizado")

    elif text.startswith("/update"):
        _, sym, buy, shares = text.split()
        data["positions"][sym] = {
            "buy":float(buy),
            "shares":float(shares)
        }
        save_json(DATA_FILE,data)
        send("✅ posición guardada")

    elif text.startswith("/sell"):
        sym = text.split()[1]
        if sym in data["positions"]:
            del data["positions"][sym]
            save_json(DATA_FILE,data)
            send("✅ vendido")

    elif text == "📌 Acción":
        analizar()

# ───── LISTENER ─────
def listener():
    last = None
    while True:
        r = requests.get(f"{URL}/getUpdates", params={"timeout":30,"offset":last}).json()

        for u in r["result"]:
            last = u["update_id"]+1
            text = u["message"].get("text","")
            handle(text)

# ───── START ─────
if __name__ == "__main__":
    send("🚀 BOT PRO v10 ACTIVO")
    listener()
