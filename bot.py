import os
import time
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURACIÓN CRÍTICA ---
TOKEN = os.getenv("TOKEN")
CHAT_ID = "8654226316"  # Tu ID verificado
URL = f"https://api.telegram.org{TOKEN}"
DATA_FILE = "data.json"

# Datos iniciales reales de tu Tyba
DEFAULT_DATA = {
    "saldo_efectivo": 1.16,
    "positions": {
        "NVDA": {"buy": 178.41, "shares": 0.61656428, "comm": 0.33},
        "TSLA": {"buy": 382.06, "shares": 0.13086881, "comm": 0.15},
        "SPY":  {"buy": 657.52, "shares": 0.13687838, "comm": 0.27},
        "QQQ":  {"buy": 603.10, "shares": 0.05, "comm": 0.15}
    }
}

BUY_LEVELS = {"NVDA": 170, "TSLA": 360, "SPY": 640, "QQQ": 580}

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f: return json.load(f)
        except: return DEFAULT_DATA
    return DEFAULT_DATA

def save_data(d):
    with open(DATA_FILE, "w") as f: json.dump(d, f, indent=4)

data = load_data()

def send_msg(text):
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(f"{URL}/sendMessage", data=payload)

def get_live_price(ticker):
    """Obtiene precio desde Stooq (Ligero para Termux)"""
    try:
        symbol = f"{ticker.lower()}.us"
        url = f"https://stooq.com{symbol}&f=sd2t2ohlcv&h&e=csv"
        r = requests.get(url, timeout=10)
        lines = r.text.strip().split('\n')
        if len(lines) > 1:
            datos = lines[1].split(',')
            return float(datos[6]) # El precio actual es la columna 7
        return None
    except: return None

# --- FUNCIONES DE LOGICA ---

def registrar_compra(ticker, monto_usd, precio_ejecucion):
    ticker = ticker.upper()
    comm = 0.15 # Comisión estándar Tyba
    shares_compradas = (monto_usd - comm) / precio_ejecucion
    
    pos = data["positions"].get(ticker, {"buy": 0, "shares": 0, "comm": 0})
    total_shares = pos["shares"] + shares_compradas
    nuevo_costo = ((pos["buy"] * pos["shares"]) + (precio_ejecucion * shares_compradas)) / total_shares
    
    data["positions"][ticker] = {
        "buy": round(nuevo_costo, 4),
        "shares": round(total_shares, 8),
        "comm": pos["comm"] + comm
    }
    save_data(data)
    return f"✅ *Compra registrada*\n{ticker}: {shares_compradas:.6f} un.\nNuevo Promedio: ${nuevo_costo:.2f}"

def analizar_mercado():
    alertas = []
    for t, info in data["positions"].items():
        p = get_live_price(t)
        if not p: continue
        ganancia_pct = ((p - info["buy"]) / info["buy"]) * 100
        
        if ganancia_pct >= 20:
            alertas.append(f"🟢 *{t} +{ganancia_pct:.1f}%*\nVende 50% para asegurar.")
        if p <= BUY_LEVELS.get(t, 0):
            alertas.append(f"💎 *{t} EN OFERTA*\nPrecio: ${p:.2f} (Meta: ${BUY_LEVELS[t]})")

    if alertas: send_msg("🔔 *ALERTAS HOY*\n\n" + "\n\n".join(alertas))
    else: send_msg("😴 Sin movimientos urgentes.")

def resumen_cartera():
    msg = "📊 *MI CUENTA TYBA*\n"
    total_actual = 0
    for t, i in data["positions"].items():
        p = get_live_price(t) or i["buy"]
        v_actual = p * i["shares"]
        gain = v_actual - (i["buy"] * i["shares"])
        total_actual += v_actual
        icon = "📈" if gain >= 0 else "📉"
        msg += f"{icon} *{t}*: ${v_actual:.2f} ({ (gain/(i['buy']*i['shares']))*100 :+.1f}%)\n"
    msg += f"\n🔥 *Total: ${total_actual + data['saldo_efectivo']:.2f}*"
    send_msg(msg)

# --- BUCLE PRINCIPAL ---
def main():
    last_update = 0
    send_msg("🚀 *Bot Tyba Online (Modo Ligero)*")
    while True:
        try:
            r = requests.get(f"{URL}/getUpdates", params={"offset": last_update, "timeout": 20}).json()
            for u in r.get("result", []):
                last_update = u["update_id"] + 1
                msg = u.get("message", {})
                if str(msg.get("from", {}).get("id")) != CHAT_ID: continue
                
                text = msg.get("text", "")
                if text == "/estado": resumen_cartera()
                elif text == "/analizar": analizar_mercado()
                elif text.startswith("/comprar"):
                    # Uso: /comprar NVDA 50 120.5
                    p = text.split()
                    send_msg(registrar_compra(p[1], float(p[2]), float(p[3])))
            
            # Auto-análisis a las 15:00 UTC (Cierre de mercado aprox)
            now = datetime.now(timezone.utc)
            if now.hour == 15 and now.minute == 0:
                analizar_mercado()
                time.sleep(60)
        except: time.sleep(10)

if __name__ == "__main__":
    main()
