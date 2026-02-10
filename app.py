# Flask Binance BTCUSDT Spot Trading Game (REST / Production Ready)
# ---------------------------------------------------------------
# - Designed for Railway.app + Gunicorn + Eventlet
# - Binance REST polling (1s)
# - Socket.IO for realtime UI update
# - Clear debug logs for observability

import time
import threading
import requests
import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template_string, request, make_response
from flask_socketio import SocketIO, emit

# ==================== APP SETUP ====================
app = Flask(__name__)

socketio = SocketIO(
    app,
    async_mode="eventlet",
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
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js
