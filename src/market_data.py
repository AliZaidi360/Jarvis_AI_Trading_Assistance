import requests
import pandas as pd
import numpy as np
import logging
import time
from datetime import datetime

try:
    from config import Config
except ImportError:
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from config import Config

logger = logging.getLogger(__name__)

class MarketData:
    def __init__(self):
        self.symbol_id = "BTC-USD" # Coinbase format
        self.base_url = "https://api.exchange.coinbase.com"
        
        # Buffers
        self.ohlcv_buffer = pd.DataFrame()
        self.current_book = None
        self.current_ticker = None
        
        # Fallback/Init values
        self.last_mid = None
        
    def fetch_data(self):
        try:
            # 1. Fetch Book (Level 1 as requested)
            # Response: {bids:['price', 'size', num], asks:...}
            book_resp = requests.get(f"{self.base_url}/products/{self.symbol_id}/book?level=1", timeout=5)
            book_data = book_resp.json()
            
            # Simple validation
            if 'bids' not in book_data or 'asks' not in book_data:
                logger.warning("Coinbase Book data invalid")
                return False
                
            self.current_book = book_data
            
            # 2. Fetch Candles for Volatility
            # Granularity 60 = 1 minute
            # Coinbase returns [time, low, high, open, close, volume]
            candles_resp = requests.get(
                f"{self.base_url}/products/{self.symbol_id}/candles?granularity=60", 
                timeout=5
            )
            candles = candles_resp.json()
            
            # Coinbase returns NEWEST first. We flip for pandas usually.
            if isinstance(candles, list) and len(candles) > 0:
                # Cols: time, low, high, open, close, volume
                # We need close for vol.
                df = pd.DataFrame(candles, columns=['time', 'low', 'high', 'open', 'close', 'volume'])
                df = df.sort_values('time')
                self.ohlcv_buffer = df
                
            return True
            
        except Exception as e:
            logger.error(f"Coinbase Fetch Error: {e}")
            return False

    def get_mid_price(self):
        if not self.current_book:
            return None
        # Level 1 book: bids[0] is [price, size, num_orders]
        best_bid = float(self.current_book['bids'][0][0])
        best_ask = float(self.current_book['asks'][0][0])
        self.last_mid = (best_bid + best_ask) / 2.0
        return self.last_mid

    def get_spread(self):
        if not self.current_book:
            return 0.0
        best_bid = float(self.current_book['bids'][0][0])
        best_ask = float(self.current_book['asks'][0][0])
        mid = (best_bid + best_ask) / 2.0
        if mid == 0: return 0.0
        return (best_ask - best_bid) / mid

    def get_realized_volatility(self):
        if self.ohlcv_buffer.empty:
            return 0.0
        
        # Calculate returns
        df = self.ohlcv_buffer.copy()
        df['close'] = df['close'].astype(float)
        df['returns'] = df['close'].pct_change()
        
        # Rolling std of last N candles
        vol = df['returns'].tail(Config.VOLATILITY_WINDOW).std()
        
        if pd.isna(vol):
            return 0.0
        return float(vol)

    def get_order_book_imbalance(self):
        """
        HARD-CODED FORMULA (DO NOT OPTIMIZE):
        I_book = (Sum(w_i * V_bid) - Sum(w_i * V_ask)) / (Sum(w_i * V_bid) + Sum(w_i * V_ask))
        
        With Level 1 data, this simplifies to just the imbalance of the best bid/ask size.
        """
        if not self.current_book:
            return 0.0
            
        # Coinbase top level: [price, size, num]
        bid_size = float(self.current_book['bids'][0][1])
        ask_size = float(self.current_book['asks'][0][1])
        
        # Weighted sum where w_i=1 for the single level
        bid_w_vol_sum = bid_size
        ask_w_vol_sum = ask_size
        
        if (bid_w_vol_sum + ask_w_vol_sum) == 0:
            return 0.0
            
        return (bid_w_vol_sum - ask_w_vol_sum) / (bid_w_vol_sum + ask_w_vol_sum)

    def get_order_flow_imbalance(self):
        # Coinbase Public API doesn't give easy "recent trades" via REST without auth or heavy polling
        # For this MVP, we will return 0.0 to focus on Book Imbalance + Volatility,
        # OR we could poll /products/BTC-USD/trades
        # Let's try fetching trades if easy, else 0.
        
        try:
             trades_resp = requests.get(f"{self.base_url}/products/{self.symbol_id}/trades", timeout=2)
             trades = trades_resp.json()
             if not isinstance(trades, list):
                 return 0.0
                 
             buy_vol = 0.0
             sell_vol = 0.0
             
             # Coinbase side: "buy" = taker bought (up-tick/at-ask), "sell" = taker sold
             for t in trades[:50]: # Last 50 trades
                 size = float(t['size'])
                 if t['side'] == 'buy':
                     buy_vol += size
                 else:
                     sell_vol += size
            
             if (buy_vol + sell_vol) == 0:
                 return 0.0
             
             return (buy_vol - sell_vol) / (buy_vol + sell_vol)
             
        except:
            return 0.0
