# Flask Binance BTCUSDT Trading Game (REST API version for Railway)
# ---------------------------------------------------------------
# - Replace Binance WebSocket with REST polling (every 1 second)
# - Easy-to-read debug logs
# - Simple spot all-in trading game (education only)

import time
import threading
import requests
from flask import Flask, render_template_string, request, make_response
from flask_socketio import SocketIO, emit

# ==================== APP SETUP ====================
app = Flask(__name__)
socketio = SocketIO(app, async_mode="threading")

# ==================== CONFIG ====================
BINANCE_DEPTH_URL = "https://api.binance.com/api/v3/depth"
SYMBOL = "BTCUSDT"
DEPTH_LIMIT = 5
FETCH_INTERVAL = 1  # seconds

FEE_RATE = 0.001
MIN_TRADE_USDT = 10.1
BTC_PRECISION = 8
USDT_PRECISION = 8
DEFAULT_USDT = 100.0

# ==================== MARKET DATA ====================
market_data = {
    "bids": [],
    "asks": []
}

# ==================== DEBUG HELPER ====================
def debug(msg):
    print(f"[DEBUG] {msg}", flush=True)

# ==================== HTML (unchanged logic) ====================
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
.notice { font-size:14px; color:#ffaa00; margin-top:10px }
.balance { margin-top:15px; font-size:18px }
</style>
</head>
<body>

<h1>BTCUSDT Spot Trading (Game)</h1>

<h3>Orderbook</h3>
<table>
<thead>
<tr>
<th>Bid Price</th><th>Bid Vol</th>
<th>Ask Price</th><th>Ask Vol</th>
</tr>
</thead>
<tbody id="orderbook"></tbody>
</table>

<div>
<button class="buy" onclick="trade('buy')">Spot Buy BTC</button>
<button class="sell" onclick="trade('sell')">Spot Sell BTC</button>
</div>

<div class="balance" id="balance"></div>

<script>
const socket = io();

socket.on('market', data => {
    let rows = "";
    for(let i=0;i<Math.max(data.bids.length, data.asks.length);i++){
        const b = data.bids[i] || ["",""];
        const a = data.asks[i] || ["",""];
        rows += `<tr>
        <td class='bid'>${b[0]}</td><td class='bid'>${b[1]}</td>
        <td class='ask'>${a[0]}</td><td class='ask'>${a[1]}</td>
        </tr>`;
    }
    document.getElementById("orderbook").innerHTML = rows;
});

socket.on('balance', d => {
    document.getElementById("balance").innerText =
        `BTC = ${d.btc} | USDT = ${d.usdt}`;
});

function trade(side){
    fetch('/trade', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({side})
    }).then(r=>r.json()).then(d=>alert(d.msg));
}
</script>
</body>
</html>"""

# ==================== ROUTES ====================
@app.route("/")
def index():
    resp = make_response(render_template_string(HTML))
    if not request.cookies.get("usdt"):
        resp.set_cookie("usdt", f"{DEFAULT_USDT}")
        resp.set_cookie("btc", "0")
        debug("Initialize new player balance")
    return resp

@app.route("/trade", methods=["POST"])
def trade():
    side = request.json["side"]
    usdt = float(request.cookies.get("usdt", DEFAULT_USDT))
    btc = float(request.cookies.get("btc", 0))

    if not market_data["bids"] or not market_data["asks"]:
        debug("Trade rejected: market data not ready")
        return {"msg": "Market data not ready"}

    bid = float(market_data["bids"][0][0])
    ask = float(market_data["asks"][0][0])

    debug(f"Trade request: {side} | bid={bid} ask={ask}")

    if side == "buy":
        if usdt < MIN_TRADE_USDT:
            return {"msg": "USDT not enough"}
        fee = usdt * FEE_RATE
        btc = round((usdt - fee) / ask, BTC_PRECISION)
        usdt = 0

    if side == "sell":
        value = btc * bid
        if value < MIN_TRADE_USDT:
            return {"msg": "BTC value not enough"}
        fee = btc * FEE_RATE
        usdt = round((btc - fee) * bid, USDT_PRECISION)
        btc = 0

    resp = make_response({"msg": "Trade executed"})
    resp.set_cookie("usdt", str(usdt))
    resp.set_cookie("btc", str(btc))

    socketio.emit("balance", {"btc": btc, "usdt": usdt})
    debug(f"Trade done → BTC={btc} USDT={usdt}")
    return resp

# ==================== SOCKET ====================
@socketio.on("connect")
def on_connect():
    usdt = float(request.cookies.get("usdt", DEFAULT_USDT))
    btc = float(request.cookies.get("btc", 0))
    emit("balance", {"btc": btc, "usdt": usdt})
    debug("Client connected")

# ==================== BINANCE REST POLLER ====================
def poll_binance():
    debug("Start Binance REST polling thread")
    while True:
        try:
            r = requests.get(
                BINANCE_DEPTH_URL,
                params={"symbol": SYMBOL, "limit": DEPTH_LIMIT},
                timeout=5
            )
            data = r.json()
            market_data["bids"] = data["bids"]
            market_data["asks"] = data["asks"]

            socketio.emit("market", market_data)
            debug("Market data updated")

        except Exception as e:
            debug(f"Fetch error: {e}")

        time.sleep(FETCH_INTERVAL)

# ==================== MAIN ====================
if __name__ == "__main__":
    threading.Thread(target=poll_binance, daemon=True).start()
    socketio.run(app, host="0.0.0.0", port=5000)
