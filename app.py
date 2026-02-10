# Flask Binance BTCUSDT Trading Game (Simple Spot Simulator)
# ----------------------------------------------------
# Features:
# - Live BTCUSDT orderbook via Binance WebSocket (Bid/Ask + Volume multi rows)
# - TradingView Chart Widget (replaces big ticker price)
# - Simple all-in spot trading game
# - Persistent portfolio via browser cookies (no expiry)
# - Commission 0.1% per trade
# - Minimum trade value: 10.1 USDT (by value)
# - Trade history table (client-side only)

import asyncio
import json
import threading
from flask import Flask, render_template_string, request, make_response
from flask_socketio import SocketIO, emit
import websockets

app = Flask(__name__)
socketio = SocketIO(app, async_mode="threading")

# -------------------- CONFIG --------------------
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/btcusdt@depth5@1000ms"
FEE_RATE = 0.001
MIN_TRADE_USDT = 10.1
BTC_PRECISION = 8
USDT_PRECISION = 8
DEFAULT_USDT = 100.0

# -------------------- MARKET DATA --------------------
market_data = {
    "bids": [],
    "asks": []
}

# -------------------- HTML --------------------
HTML = """
<!DOCTYPE html>
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

<!-- TradingView Widget -->
<div class="tradingview-widget-container" style="width:70%; margin:auto">
  <div id="tradingview_chart"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({
    "width": "100%",
    "height": 400,
    "symbol": "BINANCE:BTCUSDT",
    "interval": "1",
    "timezone": "Asia/Bangkok",
    "theme": "dark",
    "style": "1",
    "locale": "en",
    "toolbar_bg": "#111",
    "enable_publishing": false,
    "hide_top_toolbar": false,
    "save_image": false,
    "container_id": "tradingview_chart"
  });
  </script>
</div>

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

<h3>Trade History</h3>
<table>
<thead>
<tr><th>BTC</th><th>USDT</th></tr>
</thead>
<tbody id="history"></tbody>
</table>

<div class="notice">
⚠️ หากท่านไม่ได้ตั้งค่าให้เบราว์เซอร์เก็บคุกกี้<br>
ท่านอาจเล่นต่อไม่ได้หากพักการเล่นนานกว่า ~1 ชั่วโมง (เช่น ปิดเครื่อง หรือระบบล้าง session)
</div>

<script>
const socket = io();
let historyTable = document.getElementById("history");

function addHistory(btc, usdt){
    const row = `<tr><td>${btc}</td><td>${usdt}</td></tr>`;
    historyTable.innerHTML += row;
}

socket.on('market', data => {
    const bids = data.bids;
    const asks = data.asks;
    if(!bids.length || !asks.length) return;

    let rows = "";
    for(let i=0;i<Math.max(bids.length, asks.length);i++){
        const b = bids[i] || ["",""];
        const a = asks[i] || ["",""];
        rows += `<tr><td class='bid'>${b[0]}</td><td class='bid'>${b[1]}</td><td class='ask'>${a[0]}</td><td class='ask'>${a[1]}</td></tr>`;
    }
    document.getElementById('orderbook').innerHTML = rows;
});

socket.on('balance', data => {
    document.getElementById('balance').innerText = `BTC = ${data.btc} | USDT = ${data.usdt}`;
    addHistory(data.btc, data.usdt);
});

function trade(side){
    fetch('/trade', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({side:side})
    }).then(r=>r.json()).then(d=>alert(d.msg));
}
</script>

</body>
</html>
"""

# -------------------- ROUTES --------------------
@app.route('/')
def index():
    resp = make_response(render_template_string(HTML))

    if not request.cookies.get('usdt'):
        resp.set_cookie('usdt', f"{DEFAULT_USDT}")
        resp.set_cookie('btc', '0')
    return resp

@app.route('/trade', methods=['POST'])
def trade():
    side = request.json['side']
    usdt = float(request.cookies.get('usdt', DEFAULT_USDT))
    btc = float(request.cookies.get('btc', 0))

    bids = market_data['bids']
    asks = market_data['asks']

    if not bids or not asks:
        return {'msg':'Market data not ready'}

    bid = float(bids[0][0])
    ask = float(asks[0][0])

    if side == 'buy':
        if usdt < MIN_TRADE_USDT:
            return {'msg':'USDT not enough to buy'}
        fee = usdt * FEE_RATE
        net = usdt - fee
        btc = round(net / ask, BTC_PRECISION)
        usdt = 0

    if side == 'sell':
        value = btc * bid
        if value < MIN_TRADE_USDT:
            return {'msg':'BTC value not enough to sell'}
        fee = btc * FEE_RATE
        btc_after_fee = btc - fee
        usdt = round(btc_after_fee * bid, USDT_PRECISION)
        btc = 0

    resp = make_response({'msg':'Trade executed'})
    resp.set_cookie('usdt', f"{usdt}")
    resp.set_cookie('btc', f"{btc}")

    socketio.emit('balance', {'usdt':usdt,'btc':btc})
    return resp

# -------------------- SOCKET EVENTS --------------------
@socketio.on('connect')
def send_initial_balance():
    usdt = float(request.cookies.get('usdt', DEFAULT_USDT))
    btc = float(request.cookies.get('btc', 0))
    emit('balance', {'usdt':usdt, 'btc':btc})

# -------------------- BINANCE WS --------------------
def binance_ws_loop():
    while True:
        try:
            import websocket  # websocket-client
            ws = websocket.create_connection(
                "wss://stream.binance.com:9443/ws/btcusdt@depth5@1000ms",
                timeout=10
            )
            while True:
                msg = ws.recv()
                d = json.loads(msg)
                market_data['bids'] = d.get('bids', [])
                market_data['asks'] = d.get('asks', [])
                socketio.emit('market', market_data)
        except Exception as e:
            print("Binance WS error:", e)
            socketio.sleep(3)

# -------------------- MAIN --------------------
import os

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.start_background_task(binance_ws_loop)
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        allow_unsafe_werkzeug=True
    )

