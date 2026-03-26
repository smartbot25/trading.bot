import os
import time
import json
import requests
import yfinance as yf
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURACIÓN CRÍTICA ---
TOKEN = os.getenv("TOKEN")
CHAT_ID = "8654226316"  # Tu ID verificado
URL = f"https://api.telegram.org{TOKEN}"
DATA_FILE = "data.json"

# Datos iniciales extraídos de tus reportes de Tyba
DEFAULT_DATA = {
    "saldo_efectivo": 1.16,
    "positions": {
        "NVDA": {"buy": 178.41, "shares": 0.61656428, "comm": 0.33},
        "TSLA": {"buy": 382.06, "shares": 0.13086881, "comm": 0.15},
        "SPY":  {"buy": 657.52, "shares": 0.13687838, "comm": 0.27},
        "QQQ":  {"buy": 603.10, "shares": 0.05, "comm": 0.15} # Estimado
    }
}

# Niveles para avisarte de compra (Precios accesibles)
BUY_LEVELS = {"NVDA": 170, "TSLA": 360, "SPY": 640, "QQQ": 580}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f: return json.load(f)
    return DEFAULT_DATA

def save_data(d):
    with open(DATA_FILE, "w") as f: json.dump(d, f, indent=4)

data = load_data()

def send_msg(text):
    requests.post(f"{URL}/sendMessage", data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})

def get_live_price(ticker):
    try:
        asset = yf.Ticker(ticker)
        return asset.fast_info['last_price']
    except: return None

# --- FUNCIONES DE ÉLITE ---

def registrar_operacion(ticker, monto_usd, precio_ejecucion):
    """Calcula costo promedio y resta comisión estimada de $0.15"""
    ticker = ticker.upper()
    comm = 0.15 
    shares_compradas = (monto_usd - comm) / precio_ejecucion
    
    pos = data["positions"].get(ticker, {"buy": 0, "shares": 0, "comm": 0})
    
    # Nuevo Costo Promedio Ponderado
    total_shares = pos["shares"] + shares_compradas
    nuevo_costo = ((pos["buy"] * pos["shares"]) + (precio_ejecucion * shares_compradas)) / total_shares
    
    data["positions"][ticker] = {
        "buy": round(nuevo_costo, 4),
        "shares": round(total_shares, 8),
        "comm": pos["comm"] + comm
    }
    save_data(data)
    return f"✅ Compra exitosa: {shares_compradas:.6f} un. de {ticker}"

def analizar_mercado():
    alertas = []
    total_valor_acciones = 0
    
    for ticker, info in data["positions"].items():
        p = get_live_price(ticker)
        if not p: continue
        
        # Cálculos de rentabilidad
        valor_actual = p * info["shares"]
        total_valor_acciones += valor_actual
        ganancia_pct = ((p - info["buy"]) / info["buy"]) * 100
        
        # 1. Alerta de Venta (Toma de ganancias escalonada)
        if ganancia_pct >= 20:
            alertas.append(f"💰 *{ticker} +{ganancia_pct:.2f}%*\n¡Momento de vender el 50% para asegurar profit!")
        
        # 2. Alerta de Compra (Precio accesible)
        if p <= BUY_LEVELS.get(ticker, 0):
            alertas.append(f"💎 *{ticker} en OFERTA*\nPrecio actual: ${p:.2f}\n(Tu meta: ${BUY_LEVELS[ticker]})")

    if alertas:
        send_msg("🔔 *ALERTAS DE TRADING*\n\n" + "\n\n".join(alertas))

def resumen_cartera():
    msg = "📊 *RESUMEN DE TU CUENTA TYBA*\n"
    msg += "───────────────────\n"
    total_invertido = 0
    total_actual = 0
    
    for t, i in data["positions"].items():
        p = get_live_price(t)
        if p:
            v_actual = p * i["shares"]
            v_inv = i["buy"] * i["shares"]
            gain = v_actual - v_inv
            total_actual += v_actual
            total_invertido += v_inv
            icon = "📈" if gain >= 0 else "📉"
            msg += f"{icon} *{t}*: ${v_actual:.2f} ({ (gain/v_inv)*100 :+.2f}%)\n"
    
    msg += "───────────────────\n"
    msg += f"💵 Acciones: ${total_actual:.2f}\n"
    msg += f"💰 Saldo Cash: ${data['saldo_efectivo']:.2f}\n"
    msg += f"🔥 *Balance Total: ${total_actual + data['saldo_efectivo']:.2f}*\n"
    send_msg(msg)

# --- BOT HANDLER ---

def main_loop():
    last_update = 0
    send_msg("🚀 *Bot de Inversiones Tyba Online*")
    
    while True:
        try:
            # Revisar mensajes de Telegram
            r = requests.get(f"{URL}/getUpdates", params={"offset": last_update, "timeout": 20}).json()
            for u in r.get("result", []):
                last_update = u["update_id"] + 1
                msg = u.get("message", {})
                text = msg.get("text", "")
                
                if str(msg.get("from", {}).get("id")) != CHAT_ID: continue

                if text == "/estado":
                    resumen_cartera()
                elif text.startswith("/comprar"): # /comprar NVDA 50 125.5
                    _, t, monto, precio = text.split()
                    confirmacion = registrar_operacion(t, float(monto), float(precio))
                    send_msg(confirmacion)
                elif text == "/analizar":
                    analizar_mercado()

            # Análisis automático cada 4 horas
            now = datetime.now()
            if now.hour % 4 == 0 and now.minute == 0:
                analizar_mercado()
                time.sleep(60)

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main_loop()
