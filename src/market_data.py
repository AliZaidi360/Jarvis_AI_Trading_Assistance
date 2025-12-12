import ccxt
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import random # For fallback if needed, or strictly use ccxt

try:
    from config import Config
except ImportError:
    # Handle running from tests or different pwd
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from config import Config

logger = logging.getLogger(__name__)

class MarketData:
    def __init__(self, exchange_id=None):
        self.symbol = Config.SYMBOL
        self.timeframe = Config.TIMEFRAME
        self.limit = Config.ORDER_BOOK_DEPTH
        
        # Initialize Exchange
        exchange_class = getattr(ccxt, exchange_id or Config.EXCHANGE_ID)
        self.exchange = exchange_class({
            'apiKey': Config.API_KEY,
            'secret': Config.API_SECRET,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'  # PERPETUALS
            }
        })
        
        if Config.SANDBOX_MODE:
            self.exchange.set_sandbox_mode(True)
            
        # State Buffers
        self.recent_trades = []
        self.ohlcv_buffer = pd.DataFrame()
        self.current_orderbook = None
        self.current_ticker = None

    def fetch_data(self):
        """
        Main update loop. Fetches all required data from exchange.
        """
        try:
            # 1. Fetch Order Book
            self.current_orderbook = self.exchange.fetch_order_book(self.symbol, limit=self.limit)
            
            # 2. Fetch Recent Trades (for Flow Imbalance)
            trades = self.exchange.fetch_trades(self.symbol, limit=100)
            self.recent_trades = trades
            
            # 3. Fetch Ticker (for Mid Price, Funding)
            self.current_ticker = self.exchange.fetch_ticker(self.symbol)
            
            # 4. Fetch OHLCV (for Volatility)
            # We only need enough for the rolling window
            candles = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=Config.VOLATILITY_WINDOW * 2)
            self.ohlcv_buffer = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            return True
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            return False

    def get_mid_price(self):
        if not self.current_orderbook:
            return None
        bid = self.current_orderbook['bids'][0][0]
        ask = self.current_orderbook['asks'][0][0]
        return (bid + ask) / 2.0

    def get_spread(self):
        if not self.current_orderbook:
            return None
        bid = self.current_orderbook['bids'][0][0]
        ask = self.current_orderbook['asks'][0][0]
        mid = (bid + ask) / 2.0
        return (ask - bid) / mid  # Relative spread in %

    def get_funding_rate(self):
        # Some exchanges return funding info in ticker, otherwise needs fetchFundingRate
        if self.current_ticker and 'info' in self.current_ticker and 'lastFundingRate' in self.current_ticker['info']:
             # Binance specific usually
             return float(self.current_ticker['info']['lastFundingRate'])
        # Fallback/Generic
        try:
             # This is an extra API call, use sparingly or cache
             funding = self.exchange.fetch_funding_rate(self.symbol)
             return funding['fundingRate']
        except:
             return 0.0

    def get_realized_volatility(self):
        """
        Computes rolling realized volatility (standard deviation of returns)
        over Config.VOLATILITY_WINDOW.
        """
        if self.ohlcv_buffer.empty:
            return 0.0
            
        df = self.ohlcv_buffer.copy()
        df['returns'] = df['close'].pct_change()
        vol = df['returns'].rolling(window=Config.VOLATILITY_WINDOW).std().iloc[-1]
        
        # If NaN (at start), return 0
        if pd.isna(vol):
            return 0.0
        return vol

    def get_order_book_imbalance(self):
        """
        Weighted depth imbalance.
        I_book = (Sum(BidVol) - Sum(AskVol)) / (Sum(BidVol) + Sum(AskVol))
        """
        if not self.current_orderbook:
            return 0.0
            
        bids = self.current_orderbook['bids'] # List of [price, amount]
        asks = self.current_orderbook['asks']
        
        # Simple volume sum for MVP (or use weighted if desired)
        bid_vol = sum([b[1] for b in bids])
        ask_vol = sum([a[1] for a in asks])
        
        if (bid_vol + ask_vol) == 0:
            return 0.0
            
        return (bid_vol - ask_vol) / (bid_vol + ask_vol)

    def get_order_flow_imbalance(self):
        """
        I_flow = (BuyVol - SellVol) / (BuyVol + SellVol)
        Based on recent trades.
        """
        if not self.recent_trades:
            return 0.0
            
        buy_vol = 0.0
        sell_vol = 0.0
        
        for trade in self.recent_trades:
            if trade['side'] == 'buy':
                buy_vol += trade['amount']
            else:
                sell_vol += trade['amount']
                
        if (buy_vol + sell_vol) == 0:
            return 0.0
            
        return (buy_vol - sell_vol) / (buy_vol + sell_vol)
