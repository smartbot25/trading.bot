"""
Portfolio Bot PRO v7.0
Broker: TYBA (solo sugerencias)
"""

import os
import json
import time
import logging
import threading
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()
TOKEN   = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not TOKEN or not CHAT_ID:
    raise EnvironmentError("Falta TOKEN o CHAT_ID en .env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("Bot")

DATA_FILE   = "data.json"
ALERTS_FILE = "sent_alerts.json"

NIVELES = {
    "NVDA": {"sl": 156, "tp1": 214, "tp2": 250},
    "TSLA": {"sl": 335, "tp1": 457, "tp2": 530},
    "SPY" : {"sl": 578, "tp1": 788, "tp2": 900},
}

ACTIVOS = {
    "NVDA": "nvda.us",
    "TSLA": "tsla.us",
    "SPY" : "spy.us",
}

BUY_LEVELS = {
    "NVDA": 170,
    "TSLA": 360,
    "SPY" : 600,
}

INTERVALO_SEG    = 3600
CAIDA_BRUSCA_PCT = -3.0
RESUMEN_HORA_UTC = 20

data_lock          = threading.Lock()
ultimo_resumen_dia = -1

# ────────── PERSISTENCIA ──────────
def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {
            "cash"      : 0.0,
            "tyba_saldo": 0.0,
            "positions" : {
                "NVDA": {"buy_price": 177.42, "shares": 0.62, "amount_usd": 110.0},
                "SPY" : {"buy_price": 642.86, "shares": 0.14, "amount_usd": 90.0},
                "TSLA": {"buy_price": 384.62, "shares": 0.13, "amount_usd": 50.0},
            },
        }

def save_data(d):
    with open(DATA_FILE, "w") as f:
        json.dump(d, f, indent=2)

def load_alerts():
    try:
        with open(ALERTS_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_alerts(a):
    with open(ALERTS_FILE, "w") as f:
        json.dump(list(a), f)

data        = load_data()
sent_alerts = load_alerts()

# ────────── TELEGRAM ──────────
def send(msg, keyboard=None, retries=3):
    url     = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id"   : CHAT_ID,
        "text"      : msg,
        "parse_mode": "HTML",
    }
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    for intento in range(1, retries + 1):
        try:
            r = requests.post(url, data=payload, timeout=10)
            if r.ok:
                return True
        except requests.RequestException as e:
            log.warning(f"send() intento {intento}/{retries}: {e}")
            if intento < retries:
                time.sleep(4 * intento)
    return False

# ────────── PRECIOS ──────────
def get_price(symbol_stooq):
    url = f"https://stooq.com/q/l/?s={symbol_stooq}&f=sd2t2ohlcv&h&e=csv"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return None
        price = float(lines[1].split(",")[6])
        return price if price > 0 else None
    except Exception as e:
        log.error(f"get_price({symbol_stooq}): {e}")
        return None

# ────────── MERCADO ABIERTO ──────────
def mercado_abierto():
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    hora = now.hour + now.minute / 60
    return 13.5 <= hora <= 20.0

# ────────── SUGERENCIAS DE COMPRA ──────────
def sugerencias_compra(price, saldo):
    if saldo <= 0:
        return "   Sin saldo en TYBA. Usa /settyba para actualizar."

    opciones = [
        round(saldo * 0.25, 2),
        round(saldo * 0.50, 2),
        round(saldo, 2),
    ]
    opciones = list(dict.fromkeys([o for o in opciones if o >= 5]))

    lineas = []
    for monto in opciones:
        acciones = round(monto / price, 4)
        pct = round((monto / saldo) * 100, 1)
        etiqueta = "(todo)" if monto == round(saldo, 2) else ""
        lineas.append(f"💵 ${monto:.2f} ({pct}%) → {acciones} acciones {etiqueta}")
    return "\n".join(lineas)

# ────────── RESUMEN DIARIO ──────────
def enviar_resumen_diario():
    with data_lock:
        positions   = dict(data["positions"])
        cash        = data["cash"]
        tyba_saldo  = data.get("tyba_saldo", 0.0)

    lines = ["📊 <b>RESUMEN DEL DIA</b>\n"]
    total_invertido = 0.0
    total_actual    = 0.0

    for sym, stooq in ACTIVOS.items():
        if sym not in positions:
            continue
        pos       = positions[sym]
        buy_price = pos["buy_price"]
        shares    = pos["shares"]
        amount    = pos["amount_usd"]
        price     = get_price(stooq)

        if price is None:
            lines.append(f"⚪ <b>{sym}</b>: sin datos")
            continue

        actual   = shares * price
        ganancia = actual - amount
        pct      = ((price - buy_price) / buy_price) * 100
        emoji    = "🟢" if pct >= 0 else "🔴"
        sl       = NIVELES.get(sym, {}).get("sl", 0)
        tp1      = NIVELES.get(sym, {}).get("tp1", 0)
        dist_sl  = ((price - sl) / price) * 100

        total_invertido += amount
        total_actual    += actual

        lines.append(
            f"{emoji} <b>{sym}</b>  ${price:.2f}  ({pct:+.1f}%)\n"
            f"   P&L: {'+' if ganancia>=0 else ''}${ganancia:.2f}\n"
            f"   🔴 SL: ${sl} ({dist_sl:.1f}% lejos)  |  🟢 TP: ${tp1}"
        )

    pnl_total   = total_actual - total_invertido
    patrimonio  = total_actual + cash
    emoji_total = "🟢" if pnl_total >= 0 else "🔴"

    lines += [
        "",
        "─────────────────",
        f"💰 <b>Saldo TYBA:</b>  ${tyba_saldo:.2f}",
        f"📈 <b>En mercado:</b> ${total_actual:.2f}",
        f"{emoji_total} <b>P&L total:</b> {'+' if pnl_total>=0 else ''}${pnl_total:.2f}",
        f"💼 <b>Patrimonio:</b> ${patrimonio:.2f}",
        "",
        f"🕐 Cierre {datetime.now(timezone.utc).strftime('%d/%m/%Y')}",
        "Hasta mañana. Mercado cerrado. 💪",
    ]
    send("\n".join(lines))

# ────────── LISTENER TELEGRAM ──────────
def telegram_listener():
    last_update = None
    log.info("Listener iniciado.")

    while True:
        try:
            url    = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
            params = {"timeout": 30}
            if last_update:
                params["offset"] = last_update

            r       = requests.get(url, params=params, timeout=40)
            updates = r.json().get("result", [])

            for upd in updates:
                last_update = upd["update_id"] + 1
                if "message" in upd:
                    text = upd["message"].get("text", "").strip()
                    log.info(f"Comando: {text}")

                    if text == "/status":
                        cmd_status()
                    elif text == "/tyba":
                        cmd_tyba()
                    elif text.startswith("/settyba"):
                        cmd_settyba(text[8:])
                    elif text.startswith("/precio"):
                        p = text.split()
                        if len(p)>=2: cmd_precio(p[1])
                    elif text.startswith("/update"):
                        cmd_update(text[7:])
                    elif text == "/help":
                        cmd_help()
        except Exception as e:
            log.error(f"listener error: {e}")
            time.sleep(10)

# ────────── MARKET LOOP ──────────
def market_loop():
    global ultimo_resumen_dia
    log.info("Market loop iniciado.")

    while True:
        now_utc = datetime.now(timezone.utc)
        if (now_utc.hour == RESUMEN_HORA_UTC and
                now_utc.weekday() < 5 and
                now_utc.day != ultimo_resumen_dia):
            enviar_resumen_diario()
            ultimo_resumen_dia = now_utc.day

        if not mercado_abierto():
            time.sleep(1800)
            continue

        with data_lock:
            positions  = dict(data["positions"])
            tyba_saldo = data.get("tyba_saldo", 0.0)

        for name, stooq in ACTIVOS.items():
            if name in positions:
                continue
            price  = get_price(stooq)
            target = BUY_LEVELS.get(name, 0)
            key    = f"{name}_buy_{target}"

            if price and price <= target and key not in sent_alerts:
                sugerencias = sugerencias_compra(price, tyba_saldo)
                send(
                    f"🟢 <b>OPORTUNIDAD DE COMPRA — {name}</b>\n\n"
                    f"Precio actual: <b>${price:.2f}</b>\n"
                    f"Nivel objetivo: ${target}\n"
                    f"Tienes en TYBA: ${tyba_saldo:.2f}\n"
                    f"Sugerencias:\n{sugerencias}\n\n"
                    f"Ve a TYBA y compra la cantidad que elijas, luego registra con /update {name} {price} SHARES MONTO"
                )
                sent_alerts.add(key)
                save_alerts(sent_alerts)

        time.sleep(INTERVALO_SEG)

# ────────── ARRANQUE ──────────
if __name__ == "__main__":
    log.info("Bot v7.0 iniciado")
    send("🚀 <b>Portfolio Bot PRO v7.0 iniciado</b>")
    threading.Thread(target=telegram_listener, daemon=True).start()
    market_loop()
