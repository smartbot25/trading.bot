import os.
import time
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
URL = f"https://api.telegram.org/bot{TOKEN}"

DATA_FILE = "data.json"

# ───── TUS DATOS INICIALES ─────
DEFAULT_DATA = {
    "saldo": 0,
    "usar_saldo": False,
    "positions": {
        "NVDA": {"buy": 178.41, "shares": 0.61},
        "SPY":  {"buy": 657.52, "shares": 0.13},
        "TSLA": {"buy": 382.06, "shares": 0.13},
        "QQQ":  {"buy": 603.10, "shares": 0.05},
    }
}

BUY_LEVELS = {
    "NVDA":170,
    "TSLA":360,
    "SPY":600,
    "QQQ":580
}

# ───── DATA ─────
def load_data():
    try:
        with open(DATA_FILE,"r") as f:
            return json.load(f)
    except:
        return DEFAULT_DATA

def save_data(d):
    with open(DATA_FILE,"w") as f:
        json.dump(d,f,indent=2)

data = load_data()

# ───── TELEGRAM ─────
def send(msg, keyboard=None):
    payload = {"chat_id": CHAT_ID, "text": msg}
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    requests.post(f"{URL}/sendMessage", data=payload)

def menu():
    keyboard = {
        "keyboard":[
            ["📊 Estado","💰 Saldo"],
            ["💵 Cargar saldo","📌 Acción"],
        ],
        "resize_keyboard":True
    }
    send("📲 MENÚ", keyboard)

# ───── PRECIO ─────
def price(sym):
    try:
        r = requests.get(f"https://stooq.com/q/l/?s={sym.lower()}.us&f=sd2t2ohlcv&h&e=csv")
        return float(r.text.split("\n")[1].split(",")[6])
    except:
        return None

# ───── HORARIO ─────
def mercado_abierto():
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    h = now.hour + now.minute/60
    return 13.5 <= h <= 20

# ───── ANALISIS ─────
def analizar():

    acciones = []
    saldo = data["saldo"]
    usar = data["usar_saldo"]

    for name, pos in data["positions"].items():
        p = price(name)
        if not p:
            continue

        buy = pos["buy"]
        sh = pos["shares"]
        pct = ((p - buy)/buy)*100
        actual = sh * p

        # VENTAS
        if pct <= -12:
            acciones.append(
                f"🔴 {name}\nVENDER TODO\n{sh} → ${actual:.2f}"
            )

        elif pct >= 35:
            v = round(sh*0.25,4)
            m = round(actual*0.25,2)
            acciones.append(
                f"🟢 {name}\nVENDER 25%\n{v} → ${m}"
            )

        elif pct >= 20:
            v = round(sh*0.5,4)
            m = round(actual*0.5,2)
            acciones.append(
                f"🟢 {name}\nVENDER 50%\n{v} → ${m}"
            )

    # COMPRAS (SIEMPRE)
    for name in data["positions"].keys():
        p = price(name)
        if p and p < BUY_LEVELS[name]:

            monto = 50  # fijo disciplinado
            acciones_calc = round(monto/p,4)

            if usar and saldo >= monto:
                data["saldo"] -= monto
                save_data(data)
                acciones.append(
                    f"🟢 {name}\nCOMPRAR ${monto}\n{acciones_calc} acciones\nSaldo restante: ${data['saldo']}"
                )
            else:
                acciones.append(
                    f"🟢 {name}\nOPORTUNIDAD\nComprar ${monto} → {acciones_calc} acciones\n(Sin saldo)"
                )

    if acciones:
        send("📊 ACCIONES HOY\n\n" + "\n\n".join(acciones))
    else:
        send("📌 HOY: NO HACER NADA")

# ───── RESUMEN ─────
def resumen():
    msg = "📊 RESUMEN DEL DÍA\n\n"
    for name, pos in data["positions"].items():
        p = price(name)
        if p:
            pct = ((p-pos["buy"])/pos["buy"])*100
            msg += f"{name}: {pct:+.2f}%\n"
    send(msg)

# ───── COMANDOS ─────
def handle(text):

    if text == "/start":
        menu()

    elif text == "📊 Estado":
        msg = "📊 PORTAFOLIO\n\n"
        for k,v in data["positions"].items():
            msg += f"{k}: {v['shares']} @ ${v['buy']}\n"
        send(msg)

    elif text == "💰 Saldo":
        send(f"💰 Saldo: ${data['saldo']}")

    elif text == "💵 Cargar saldo":
        data["usar_saldo"] = True
        save_data(data)
        send("✅ Modo compra ACTIVADO\nAhora usa: /saldo 100")

    elif text.startswith("/saldo"):
        val = float(text.split()[1])
        data["saldo"] = val
        save_data(data)
        send(f"✅ Saldo actualizado: ${val}")

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

# ───── LOOP ─────
def loop():
    send("🚀 BOT ACTIVO")

    while True:
        if mercado_abierto():
            analizar()
            time.sleep(3600)
        else:
            now = datetime.now(timezone.utc)
            if now.hour == 20:
                resumen()
            time.sleep(1800)

# ───── START ─────
if __name__ == "__main__":
    import threading
    threading.Thread(target=listener).start()
    loop()
