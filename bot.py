"""
Portfolio Bot PRO v5.0
Broker: TYBA
Novedades: resumen diario automatico + alerta caida brusca -3%
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
    "QQQ" : {"sl": 519, "tp1": 708, "tp2": 820},
}

ACTIVOS = {
    "QQQ" : "qqq.us",
    "NVDA": "nvda.us",
    "TSLA": "tsla.us",
    "SPY" : "spy.us",
}

INTERVALO_SEG      = 3600   # chequeo cada 1 hora
CAIDA_BRUSCA_PCT   = -3.0   # alerta si cae mas de 3% en el dia
RESUMEN_HORA_UTC   = 20     # 4PM EST = 20:00 UTC (cierre NYSE)

data_lock = threading.Lock()

# control para resumen diario
ultimo_resumen_dia = -1

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {
            "cash": 0.0,
            "positions": {
                "NVDA": {"buy_price": 177.42, "shares": 0.62, "amount_usd": 110.0},
                "SPY" : {"buy_price": 642.86, "shares": 0.14, "amount_usd": 90.0},
                "TSLA": {"buy_price": 384.62, "shares": 0.13, "amount_usd": 50.0},
                "QQQ" : {"buy_price": 604.80, "shares": 0.05, "amount_usd": 30.0},
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

def mercado_abierto():
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    hora = now.hour + now.minute / 60
    return 13.5 <= hora <= 20.0

# ═════════════════════════════════════════
#  RESUMEN DIARIO AUTOMATICO — 4PM EST
# ═════════════════════════════════════════
def enviar_resumen_diario():
    with data_lock:
        positions = dict(data["positions"])
        cash      = data["cash"]

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
        niveles  = NIVELES.get(sym, {})
        sl       = niveles.get("sl", 0)
        tp1      = niveles.get("tp1", 0)
        dist_sl  = ((price - sl) / price) * 100

        total_invertido += amount
        total_actual    += actual

        lines.append(
            f"{emoji} <b>{sym}</b>  ${price:.2f}  ({pct:+.1f}%)\n"
            f"   P&L: {'+' if ganancia>=0 else ''}${ganancia:.2f}\n"
            f"   🔴 SL: ${sl} ({dist_sl:.1f}% lejos)  |  🟢 TP: ${tp1}"
        )

    pnl_total  = total_actual - total_invertido
    patrimonio = total_actual + cash
    emoji_total = "🟢" if pnl_total >= 0 else "🔴"

    lines += [
        "",
        "─────────────────",
        f"💵 <b>Efectivo:</b>   ${cash:.2f}",
        f"📈 <b>En mercado:</b> ${total_actual:.2f}",
        f"{emoji_total} <b>P&L total:</b> {'+' if pnl_total>=0 else ''}${pnl_total:.2f}",
        f"💼 <b>Patrimonio:</b> ${patrimonio:.2f}",
        "",
        f"🕐 Cierre {datetime.now(timezone.utc).strftime('%d/%m/%Y')}",
        "Hasta mañana. Mercado cerrado. 💪",
    ]
    send("\n".join(lines))

# ═════════════════════════════════════════
#  COMANDOS
# ═════════════════════════════════════════
def cmd_status():
    with data_lock:
        positions = dict(data["positions"])
        cash      = data["cash"]

    lines = ["📊 <b>PORTAFOLIO COMPLETO</b>\n"]
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
        niveles  = NIVELES.get(sym, {})
        sl       = niveles.get("sl", 0)
        tp1      = niveles.get("tp1", 0)

        total_invertido += amount
        total_actual    += actual

        lines.append(
            f"{emoji} <b>{sym}</b>  ${price:.2f}  ({pct:+.1f}%)\n"
            f"   Compra: ${buy_price}  |  Shares: {shares}\n"
            f"   Invertido: ${amount:.2f}  Actual: ${actual:.2f}\n"
            f"   P&L: {'+' if ganancia>=0 else ''}${ganancia:.2f}\n"
            f"   🔴 SL: ${sl}  |  🟢 TP: ${tp1}"
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
        f"\n🕐 {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC",
    ]
    send("\n".join(lines))

def cmd_niveles():
    lines = ["📌 <b>NIVELES ACTUALES</b>\n"]
    for sym, n in NIVELES.items():
        lines.append(
            f"<b>{sym}</b>\n"
            f"   🔴 Stop Loss:     ${n['sl']}\n"
            f"   🟢 Take Profit 1: ${n['tp1']}\n"
            f"   🟢 Take Profit 2: ${n['tp2']}\n"
        )
    lines.append("Para cambiar: /setnivel NVDA sl 150")
    send("\n".join(lines))

def cmd_setnivel(args):
    parts = args.strip().split()
    if len(parts) != 3:
        send("Uso: /setnivel NVDA sl 150\nTipos: sl, tp1, tp2")
        return
    sym, tipo, valor = parts[0].upper(), parts[1].lower(), parts[2]
    if sym not in NIVELES:
        send(f"Simbolo {sym} no encontrado.")
        return
    if tipo not in ("sl", "tp1", "tp2"):
        send("Tipo debe ser: sl, tp1 o tp2")
        return
    try:
        NIVELES[sym][tipo] = float(valor)
        send(f"✅ <b>{sym}</b> {tipo.upper()} actualizado a ${valor}")
    except:
        send("Valor invalido.")

def cmd_update(args):
    parts = args.strip().split()
    if len(parts) != 4:
        send(
            "Uso: /update SIMBOLO PRECIO_COMPRA SHARES MONTO_USD\n"
            "Ejemplo: /update NVDA 177.42 0.62 110"
        )
        return
    sym = parts[0].upper()
    try:
        buy_price  = float(parts[1])
        shares     = float(parts[2])
        amount_usd = float(parts[3])
    except:
        send("Valores invalidos.")
        return

    with data_lock:
        data["positions"][sym] = {
            "buy_price" : buy_price,
            "shares"    : shares,
            "amount_usd": amount_usd,
        }
        save_data(data)

    for k in list(sent_alerts):
        if k.startswith(sym):
            sent_alerts.discard(k)
    save_alerts(sent_alerts)

    send(
        f"✅ <b>{sym} ACTUALIZADO</b>\n\n"
        f"Precio compra: ${buy_price}\n"
        f"Shares:        {shares}\n"
        f"Monto:         ${amount_usd}"
    )

def cmd_setcash(args):
    try:
        amount = float(args.strip())
        with data_lock:
            data["cash"] = amount
            save_data(data)
        send(f"✅ Efectivo actualizado: ${amount:.2f}")
    except:
        send("Uso: /setcash 150.00")

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

def cmd_precio(symbol):
    symbol = symbol.upper()
    stooq  = ACTIVOS.get(symbol)
    if not stooq:
        send(f"Simbolo {symbol} no configurado.\nDisponibles: {', '.join(ACTIVOS)}")
        return
    price = get_price(stooq)
    if price:
        niveles  = NIVELES.get(symbol, {})
        dist_sl  = ((price - niveles.get('sl', 0))  / price) * 100
        dist_tp1 = ((niveles.get('tp1', 0) - price) / price) * 100
        send(
            f"📌 <b>{symbol}</b>  ${price:.2f}\n\n"
            f"🔴 Stop Loss ${niveles.get('sl','-')}  ({dist_sl:+.1f}% desde aqui)\n"
            f"🟢 Take Profit ${niveles.get('tp1','-')}  ({dist_tp1:+.1f}% hasta aqui)"
        )
    else:
        send(f"No se pudo obtener precio de {symbol}.")

def cmd_plan():
    send(
        "📅 <b>PLAN 7 DIAS</b>\n\n"
        "✅ Solo observas\n"
        "✅ No compras mas\n"
        "✅ No vendes por miedo\n\n"
        "❌ No mires cada minuto\n"
        "❌ No intentes arreglar posiciones\n\n"
        "<b>LECTURAS ACTUALES</b>\n"
        "NVDA → bien posicionado\n"
        "SPY  → te da estabilidad\n"
        "TSLA → riesgo controlado\n"
        "QQQ  → exposicion tech extra\n\n"
        "💼 Esto ya es un portafolio serio."
    )

def cmd_reset_alertas():
    sent_alerts.clear()
    save_alerts(sent_alerts)
    send("🔄 Alertas reiniciadas.")

def cmd_help():
    send(
        "<b>COMANDOS DISPONIBLES</b>\n\n"
        "📊 <b>INFO</b>\n"
        "/status              portafolio completo\n"
        "/precio NVDA         precio + SL y TP\n"
        "/niveles             ver todos los niveles\n"
        "/plan                recordatorio del plan\n\n"
        "✏️ <b>ACTUALIZAR DATOS</b>\n"
        "/update NVDA 177.42 0.62 110\n"
        "/setnivel NVDA sl 150\n"
        "/setcash 150         actualizar efectivo\n"
        "/sell NVDA           cerrar posicion\n\n"
        "⚙️ <b>SISTEMA</b>\n"
        "/reset_alertas       limpiar alertas\n"
        "/help                este mensaje"
    )

# ═════════════════════════════════════════
#  LISTENER TELEGRAM
# ═════════════════════════════════════════
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
                    elif text == "/niveles":
                        cmd_niveles()
                    elif text == "/plan":
                        cmd_plan()
                    elif text.startswith("/precio"):
                        p = text.split()
                        cmd_precio(p[1]) if len(p) >= 2 else send("Uso: /precio NVDA")
                    elif text.startswith("/update"):
                        cmd_update(text[7:])
                    elif text.startswith("/setnivel"):
                        cmd_setnivel(text[9:])
                    elif text.startswith("/setcash"):
                        cmd_setcash(text[8:])
                    elif text.startswith("/sell"):
                        p = text.split()
                        cmd_sell(p[1]) if len(p) >= 2 else send("Uso: /sell NVDA")
                    elif text == "/reset_alertas":
                        cmd_reset_alertas()
                    elif text in ("/help", "/start"):
                        cmd_help()

        except Exception as e:
            log.error(f"listener error: {e}")
            time.sleep(10)

# ═════════════════════════════════════════
#  MARKET LOOP
# ═════════════════════════════════════════
def market_loop():
    global ultimo_resumen_dia
    log.info("Market loop iniciado.")

    while True:
        now_utc = datetime.now(timezone.utc)

        # ── RESUMEN DIARIO AL CIERRE 4PM EST ──────
        if (now_utc.hour == RESUMEN_HORA_UTC and
                now_utc.weekday() < 5 and
                now_utc.day != ultimo_resumen_dia):
            log.info("Enviando resumen diario...")
            enviar_resumen_diario()
            ultimo_resumen_dia = now_utc.day

        if not mercado_abierto():
            log.info("Mercado cerrado.")
            time.sleep(1800)
            continue

        log.info("Chequeando mercado...")

        with data_lock:
            positions = dict(data["positions"])

        for name, stooq in ACTIVOS.items():
            if name not in positions:
                continue

            price = get_price(stooq)
            if price is None:
                continue

            log.info(f"{name}: ${price:.2f}")

            niveles   = NIVELES.get(name, {})
            sl        = niveles.get("sl", 0)
            tp1       = niveles.get("tp1", 0)
            tp2       = niveles.get("tp2", 0)
            pos       = positions[name]
            buy_price = pos["buy_price"]
            shares    = pos["shares"]
            amount    = pos["amount_usd"]
            actual    = shares * price
            ganancia  = actual - amount
            pct       = ((price - buy_price) / buy_price) * 100

            # ── STOP LOSS ─────────────────────────
            if price <= sl and f"{name}_stop" not in sent_alerts:
                send(
                    f"🔴 <b>STOP LOSS — {name}</b>\n"
                    f"VENDER TODO\n\n"
                    f"Ve a TYBA y vende:\n"
                    f"📌 <b>{shares} acciones</b>\n"
                    f"💵 Recibirás aprox: <b>${actual:.2f}</b>\n\n"
                    f"Precio actual: ${price:.2f}\n"
                    f"Tu promedio:   ${buy_price}\n"
                    f"Perdida:       ${ganancia:.2f} ({pct:+.1f}%)"
                )
                sent_alerts.add(f"{name}_stop")
                save_alerts(sent_alerts)

            # ── TAKE PROFIT 2 ─────────────────────
            elif price >= tp2 and f"{name}_tp2" not in sent_alerts:
                shares_vender = round(shares * 0.25, 4)
                monto_vender  = round(actual * 0.25, 2)
                send(
                    f"🟢 <b>TAKE PROFIT 2 — {name}</b>\n"
                    f"VENDER 25%\n\n"
                    f"Ve a TYBA y vende:\n"
                    f"📌 <b>{shares_vender} acciones</b>\n"
                    f"💵 Recibirás aprox: <b>${monto_vender}</b>\n\n"
                    f"Precio actual: ${price:.2f}\n"
                    f"Ganancia:      +${ganancia:.2f} ({pct:+.1f}%)"
                )
                sent_alerts.add(f"{name}_tp2")
                sent_alerts.add(f"{name}_tp1")
                save_alerts(sent_alerts)

            # ── TAKE PROFIT 1 ─────────────────────
            elif price >= tp1 and f"{name}_tp1" not in sent_alerts:
                shares_vender = round(shares * 0.50, 4)
                monto_vender  = round(actual * 0.50, 2)
                send(
                    f"🟢 <b>TAKE PROFIT 1 — {name}</b>\n"
                    f"VENDER 50%\n\n"
                    f"Ve a TYBA y vende:\n"
                    f"📌 <b>{shares_vender} acciones</b>\n"
                    f"💵 Recibirás aprox: <b>${monto_vender}</b>\n\n"
                    f"Precio actual: ${price:.2f}\n"
                    f"Ganancia:      +${ganancia:.2f} ({pct:+.1f}%)"
                )
                sent_alerts.add(f"{name}_tp1")
                save_alerts(sent_alerts)

            # ── ALERTA PROXIMIDAD SL ──────────────
            dist_sl = ((price - sl) / price) * 100
            if 0 < dist_sl <= 10 and f"{name}_cerca_sl" not in sent_alerts:
                send(
                    f"⚠️ <b>CERCA DEL STOP LOSS — {name}</b>\n\n"
                    f"Precio actual: <b>${price:.2f}</b>\n"
                    f"Stop Loss:     ${sl}\n"
                    f"Distancia:     {dist_sl:.1f}%\n\n"
                    f"Mantente atento."
                )
                sent_alerts.add(f"{name}_cerca_sl")
                save_alerts(sent_alerts)

            # ── CAIDA BRUSCA -3% EN EL DIA ────────
            if pct <= CAIDA_BRUSCA_PCT and f"{name}_caida" not in sent_alerts:
                send(
                    f"📉 <b>CAIDA BRUSCA — {name}</b>\n\n"
                    f"Precio actual: <b>${price:.2f}</b>\n"
                    f"Caida desde tu compra: {pct:+.1f}%\n\n"
                    f"🔴 Stop Loss en: ${sl}\n"
                    f"Distancia al SL: {dist_sl:.1f}%\n\n"
                    f"Mantente firme. No vendas por miedo.\n"
                    f"Escribe /plan para recordar la estrategia."
                )
                sent_alerts.add(f"{name}_caida")
                save_alerts(sent_alerts)

        time.sleep(INTERVALO_SEG)

# ═════════════════════════════════════════
#  ARRANQUE
# ═════════════════════════════════════════
if __name__ == "__main__":
    log.info("Bot v5.0 iniciado")
    send(
        "🚀 <b>Portfolio Bot PRO v5.0</b>\n\n"
        "Monitoreando:\n"
        "📌 NVDA | SPY | TSLA | QQQ\n\n"
        "✅ Resumen diario automatico al cierre\n"
        "✅ Alerta de caida brusca activada\n\n"
        "Escribe /help para todos los comandos"
    )

    t = threading.Thread(target=telegram_listener, daemon=True)
    t.start()

    try:
        market_loop()
    except KeyboardInterrupt:
        log.info("Bot detenido.")
        send("⛔ Bot detenido.")
