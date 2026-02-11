# Flask Binance BTCUSDT Spot Trading Game (REST / Production Ready)
# ---------------------------------------------------------------
# - Designed for Railway.app + Gunicorn + Eventlet
# - Binance REST polling (1s)
# - Socket.IO for realtime UI update
# - Clear debug logs for observability

import time
import threading
import requests

from flask import Flask, render_template_string, request, make_response
from flask_socketio import SocketIO, emit

# ==================== APP SETUP ====================
app = Flask(__name__)

socketio = SocketIO(
    app,
    async_mode="threading",
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True
)

# ==================== CONFIG ====================
BINANCE_DEPTH_URL = "https://api.binance.com/api/v3/depth"
SYMBOL = "BTCUSDT"
DEPTH_LIMIT = 5
FETCH_INTERVAL = 1  # seconds (respect Binance & Railway)

FEE_RATE = 0.001
MIN_TRADE_USDT = 10.1
BTC_PRECISION = 8
USDT_PRECISION = 8
DEFAULT_USDT = 100.0

# ==================== MARKET DATA ====================
market_data = {"bids": [], "asks": []}

# ==================== DEBUG ====================
def debug(msg):
    print(f"[DEBUG] {msg}", flush=True)

# ==================== HTML ====================
HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>BTC Spot Trading Game</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
<style>
body { background:#111; color:#eee; font-family:Arial; text-align:center }
table { margin:auto; border-collapse:collapse; width:70% }
th,td { border:1px solid #444; padding:6px }
th { background:#222 }
.bid { color:#00ff88 }
.ask { color:#ff6666 }
button { font-size:18px; padding:10px 20px; margin:10px; cursor:pointer }
.buy { background:#aa2222; color:white }
.sell { background:#22aa44; color:white }
.balance { margin-top:15px; font-size:18px }
</style>
</head>
<body>

<h1>BTCUSDT Spot Trading (Game)</h1>

<table>
<thead>
<tr><th>Bid</th><th>Vol</th><th>Ask</th><th>Vol</th></tr>
</thead>
<tbody id="orderbook"></tbody>
</table>

<div>
<button class="buy" onclick="trade('buy')">Buy BTC</button>
<button class="sell" onclick="trade('sell')">Sell BTC</button>
</div>

<div class="balance" id="balance"></div>

<script>
const socket = io();

socket.on("market", d => {
  let r = "";
  for(let i=0;i<Math.max(d.bids.length,d.asks.length);i++){
    const b=d.bids[i]||["",""];
    const a=d.asks[i]||["",""];
    r+=`<tr>
    <td class='bid'>${b[0]}</td><td class='bid'>${b[1]}</td>
    <td class='ask'>${a[0]}</td><td class='ask'>${a[1]}</td>
    </tr>`;
  }
  document.getElementById("orderbook").innerHTML=r;
});

socket.on("balance", d=>{
  document.getElementById("balance").innerText=
  `BTC=${d.btc} | USDT=${d.usdt}`;
});

function trade(side){
 fetch("/trade",{method:"POST",headers:{"Content-Type":"application/json"},
 body:JSON.stringify({side})})
 .then(r=>r.json()).then(d=>alert(d.msg));
}
</script>
</body>
</html>"""

# ==================== ROUTES ====================
@app.route("/")
def index():
    resp = make_response(render_template_string(HTML))
    if not request.cookies.get("usdt"):
        resp.set_cookie("usdt", str(DEFAULT_USDT))
        resp.set_cookie("btc", "0")
        debug("Initialize portfolio")
    return resp

@app.route("/trade", methods=["POST"])
def trade():
    side = request.json["side"]
    usdt = float(request.cookies.get("usdt", DEFAULT_USDT))
    btc = float(request.cookies.get("btc", 0))

    if not market_data["bids"]:
        return {"msg": "Market not ready"}

    bid = float(market_data["bids"][0][0])
    ask = float(market_data["asks"][0][0])

    debug(f"Trade: {side} | bid={bid} ask={ask}")

    if side == "buy" and usdt >= MIN_TRADE_USDT:
        btc = round((usdt * (1 - FEE_RATE)) / ask, BTC_PRECISION)
        usdt = 0

    if side == "sell" and btc * bid >= MIN_TRADE_USDT:
        usdt = round((btc * (1 - FEE_RATE)) * bid, USDT_PRECISION)
        btc = 0

    resp = make_response({"msg": "Trade executed"})
    resp.set_cookie("usdt", str(usdt))
    resp.set_cookie("btc", str(btc))
    socketio.emit("balance", {"btc": btc, "usdt": usdt})

    debug(f"Balance update BTC={btc} USDT={usdt}")
    return resp

# ==================== SOCKET ====================
@socketio.on("connect")
def on_connect():
    emit("balance", {
        "btc": float(request.cookies.get("btc", 0)),
        "usdt": float(request.cookies.get("usdt", DEFAULT_USDT))
    })
    debug("Client connected")

# ==================== BINANCE POLLER ====================
def poll_binance():
    debug("Start Binance REST poller")
    while True:
        try:
            r = requests.get(
                BINANCE_DEPTH_URL,
                params={"symbol": SYMBOL, "limit": DEPTH_LIMIT},
                timeout=5
            )
            d = r.json()
            market_data["bids"] = d["bids"]
            market_data["asks"] = d["asks"]
            socketio.emit("market", market_data)
            debug("Market updated")
        except Exception as e:
            debug(f"Polling error: {e}")
        time.sleep(FETCH_INTERVAL)

# ==================== BOOT ====================
threading.Thread(target=poll_binance, daemon=True).start()

# IMPORTANT:
# Do NOT call app.run() here — Gunicorn will handle it
