"""
Portfolio Bot PRO v3.0
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

ACTIVOS = {
    "QQQ" : "qqq.us",
    "NVDA": "nvda.us",
    "TSLA": "tsla.us",
    "SPY" : "spy.us",
}

BUY_LEVELS = {
    "QQQ" : 580,
    "NVDA": 170,
    "TSLA": 360,
    "SPY" : 600,
}

DISTRIBUTION = {
    "QQQ" : 40,
    "NVDA": 80,
    "TSLA": 40,
    "SPY" : 60,
}

STOP_LOSS_PCT = 0.88
TP1_PCT       = 1.20
TP2_PCT       = 1.35
INTERVALO_SEG = 21600

data_lock = threading.Lock()

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {
            "cash": 250.0,
            "positions": {
                "QQQ": {"buy_price": 604.8, "amount_usd": 30.0}
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

def buy_keyboard(symbol, price, amount):
    return {
        "inline_keyboard": [[
            {"text": f"Comprar ${amount}", "callback_data": f"BUY|{symbol}|{price}|{amount}"},
            {"text": "Ignorar",            "callback_data": "IGNORE"},
        ]]
    }

def mercado_abierto():
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    hora = now.hour + now.minute / 60
    return 13.5 <= hora <= 20.0

def cmd_status():
    with data_lock:
        positions = dict(data["positions"])
        cash      = data["cash"]

    lines = ["<b>PORTAFOLIO</b>\n"]
    total_invertido = 0.0
    total_actual    = 0.0

    for sym, stooq in ACTIVOS.items():
        if sym not in positions:
            continue
        pos       = positions[sym]
        buy_price = pos["buy_price"]
        amount    = pos["amount_usd"]
        price     = get_price(stooq)

        if price is None:
            lines.append(f"{sym}: sin datos")
            continue

        shares   = amount / buy_price
        actual   = shares * price
        ganancia = actual - amount
        pct      = ((price - buy_price) / buy_price) * 100
        emoji    = "🟢" if pct >= 0 else "🔴"

        total_invertido += amount
        total_actual    += actual

        lines.append(
            f"{emoji} <b>{sym}</b>  ${price:.2f}\n"
            f"   Compra: ${buy_price}  |  Shares: {shares:.4f}\n"
            f"   Invertido: ${amount:.2f}  Actual: ${actual:.2f}\n"
            f"   P&L: {'+' if ganancia>=0 else ''}${ganancia:.2f} ({pct:+.1f}%)"
        )

    pnl_total  = total_actual - total_invertido
    patrimonio = total_actual + cash

    lines += [
        "",
        "─────────────────",
        f"💵 <b>Efectivo:</b>   ${cash:.2f}",
        f"📈 <b>En mercado:</b> ${total_actual:.2f}",
        f"{'🟢' if pnl_total>=0 else '🔴'} <b>P&L total:</b> {'+' if pnl_total>=0 else ''}${pnl_total:.2f}",
        f"💼 <b>Patrimonio:</b> ${patrimonio:.2f}",
    ]
    send("\n".join(lines))

def cmd_cash():
    with data_lock:
        cash = data["cash"]
    send(f"💵 <b>Efectivo disponible:</b> ${cash:.2f}")

def cmd_precio(symbol):
    symbol = symbol.upper()
    stooq  = ACTIVOS.get(symbol)
    if not stooq:
        send(f"Simbolo {symbol} no configurado. Disponibles: {', '.join(ACTIVOS)}")
        return
    price = get_price(stooq)
    if price:
        send(f"<b>{symbol}</b>  ${price:.2f}")
    else:
        send(f"No se pudo obtener precio de {symbol}.")

def cmd_sell(symbol):
    symbol = symbol.upper()
    with data_lock:
        if symbol not in data["positions"]:
            send(f"No tienes posicion en <b>{symbol}</b>.")
            return
        pos    = data["positions"].pop(symbol)
        amount = pos["amount_usd"]
        data["cash"] = round(data["cash"] + amount, 2)
        save_data(data)

    for k in list(sent_alerts):
        if k.startswith(symbol):
            sent_alerts.discard(k)
    save_alerts(sent_alerts)

    send(
        f"✅ <b>POSICION CERRADA — {symbol}</b>\n\n"
        f"Monto recuperado: ${amount:.2f}\n"
        f"Efectivo actual:  ${data['cash']:.2f}"
    )

def cmd_reset_alertas():
    sent_alerts.clear()
    save_alerts(sent_alerts)
    send("Alertas reiniciadas. Las senales volveran a dispararse.")

def cmd_help():
    send(
        "<b>COMANDOS</b>\n\n"
        "/status          portafolio con P&L\n"
        "/cash            efectivo disponible\n"
        "/precio QQQ      precio on-demand\n"
        "/sell QQQ        cerrar posicion\n"
        "/reset_alertas   limpiar alertas\n"
        "/help            este mensaje"
    )

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

                if "callback_query" in upd:
                    cb    = upd["callback_query"]["data"]
                    parts = cb.split("|")

                    if parts[0] == "BUY" and len(parts) == 4:
                        _, sym, price_s, amount_s = parts
                        price_f  = float(price_s)
                        amount_f = float(amount_s)

                        with data_lock:
                            if data["cash"] < amount_f:
                                send(f"Efectivo insuficiente (${data['cash']:.2f})")
                            else:
                                data["positions"][sym] = {
                                    "buy_price" : price_f,
                                    "amount_usd": amount_f,
                                }
                                data["cash"] = round(data["cash"] - amount_f, 2)
                                save_data(data)
                                send(
                                    f"✅ <b>COMPRA REGISTRADA — {sym}</b>\n\n"
                                    f"Precio:  ${price_f}\n"
                                    f"Monto:   ${amount_f}\n"
                                    f"Efectivo restante: ${data['cash']:.2f}"
                                )

                if "message" in upd:
                    text = upd["message"].get("text", "").strip()

                    if text == "/status":
                        cmd_status()
                    elif text == "/cash":
                        cmd_cash()
                    elif text.startswith("/precio"):
                        p = text.split()
                        cmd_precio(p[1]) if len(p) >= 2 else send("Uso: /precio QQQ")
                    elif text.startswith("/sell"):
                        p = text.split()
                        cmd_sell(p[1]) if len(p) >= 2 else send("Uso: /sell QQQ")
                    elif text == "/reset_alertas":
                        cmd_reset_alertas()
                    elif text in ("/help", "/start"):
                        cmd_help()

        except Exception as e:
            log.error(f"listener error: {e}")
            time.sleep(10)

def market_loop():
    log.info("Market loop iniciado.")

    while True:
        if not mercado_abierto():
            log.info("Mercado cerrado.")
            time.sleep(1800)
            continue

        log.info("Chequeando mercado...")

        with data_lock:
            positions = dict(data["positions"])
            cash      = data["cash"]

        for name, stooq in ACTIVOS.items():
            price = get_price(stooq)
            if price is None:
                continue

            log.info(f"{name}: ${price:.2f}")

            if name in positions:
                pos       = positions[name]
                buy_price = pos["buy_price"]
                amount    = pos["amount_usd"]

                stop = buy_price * STOP_LOSS_PCT
                tp1  = buy_price * TP1_PCT
                tp2  = buy_price * TP2_PCT

                if price <= stop and f"{name}_stop" not in sent_alerts:
                    send(
                        f"🔴 <b>STOP LOSS — {name}</b>\n"
                        f"VENDER TODO\n\n"
                        f"Precio actual: <b>${price:.2f}</b>\n"
                        f"Tu promedio:   ${buy_price}\n"
                        f"Perdida est.:  ${price*(amount/buy_price)-amount:.2f}"
                    )
                    sent_alerts.add(f"{name}_stop")
                    save_alerts(sent_alerts)

                elif price >= tp2 and f"{name}_tp2" not in sent_alerts:
                    send(
                        f"🟢 <b>TAKE PROFIT 2 — {name}</b>\n"
                        f"VENDER 25%\n\n"
                        f"Precio actual: <b>${price:.2f}</b>\n"
                        f"Vender aprox:  ${amount*0.25:.2f}"
                    )
                    sent_alerts.add(f"{name}_tp2")
                    sent_alerts.add(f"{name}_tp1")
                    save_alerts(sent_alerts)

                elif price >= tp1 and f"{name}_tp1" not in sent_alerts:
                    send(
                        f"🟢 <b>TAKE PROFIT 1 — {name}</b>\n"
                        f"VENDER 50%\n\n"
                        f"Precio actual: <b>${price:.2f}</b>\n"
                        f"Vender aprox:  ${amount*0.50:.2f}"
                    )
                    sent_alerts.add(f"{name}_tp1")
                    save_alerts(sent_alerts)

            else:
                target = BUY_LEVELS.get(name, 0)
                budget = DISTRIBUTION.get(name, 0)
                key    = f"{name}_buy_{target}"

                if price <= target and cash >= budget and key not in sent_alerts:
                    send(
                        f"🟢 <b>COMPRAR — {name}</b>\n\n"
                        f"Precio actual: <b>${price:.2f}</b>\n"
                        f"Nivel objetivo: ${target}\n"
                        f"Monto sugerido: ${budget}",
                        buy_keyboard(name, price, budget),
                    )
                    sent_alerts.add(key)
                    save_alerts(sent_alerts)

        time.sleep(INTERVALO_SEG)

if __name__ == "__main__":
    log.info("Bot iniciado")
    send("🚀 <b>Portfolio Bot PRO v3.0</b> activo\nEscribe /help para ver los comandos.")

    t = threading.Thread(target=telegram_listener, daemon=True)
    t.start()

    try:
        market_loop()
    except KeyboardInterrupt:
        log.info("Bot detenido.")
        send("Bot detenido.")
