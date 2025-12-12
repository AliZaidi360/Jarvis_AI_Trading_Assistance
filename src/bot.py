import logging
import time
import json
from datetime import datetime
try:
    from config import Config
    from src.market_data import MarketData
    from src.execution import ExecutionEngine
    from src.risk import RiskEngine
    from src.alpha import AlphaEngine
except ImportError:
    # Fallback for relative
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from config import Config
    from src.market_data import MarketData
    from src.execution import ExecutionEngine
    from src.risk import RiskEngine
    from src.alpha import AlphaEngine

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TradingBot")

class TradingBot:
    def __init__(self):
        logger.info("Initializing Agent...")
        self.md = MarketData()
        self.exec = ExecutionEngine(self.md.exchange)
        self.risk = RiskEngine()
        self.alpha = AlphaEngine()
        
        # State
        self.entry_time = None
        
        # For PnL Tracking (simple)
        self.start_equity = 0.0

    def run(self):
        logger.info("Agent Started. Waiting for data...")
        
        # Initial Balance
        bal = self.exec.fetch_balance()
        self.start_equity = float(bal['total'])
        logger.info(f"Start Equity: {self.start_equity}")
        
        while True:
            try:
                self.run_cycle()
            except Exception as e:
                logger.error(f"Cycle Error: {e}", exc_info=True)
            
            # Sleep to match timeframe or avoid spam
            # MVP: sleep 5s or 1m? Config says 1m candles.
            # Real-time data might need faster polling, but let's stick to simple loop.
            time.sleep(10) 

    def run_cycle(self):
        # 1. Update Market Data
        if not self.md.fetch_data():
            logger.warning("Data fetch failed. Skipping cycle.")
            return

        # 2. Compute Features
        mid_price = self.md.get_mid_price()
        spread = self.md.get_spread()
        volatility = self.md.get_realized_volatility()
        book_imb = self.md.get_order_book_imbalance()
        flow_imb = self.md.get_order_flow_imbalance()
        
        # 3. Compute Signal
        direction_score = self.alpha.get_direction_score(book_imb, flow_imb)
        
        # 4. Get Current Position
        position = self.exec.get_position()
        current_equity = float(self.exec.fetch_balance()['total'])
        
        # 5. Risk Checks (Global)
        self.exec.check_timeouts()
        if not self.risk.check_daily_drawdown(current_equity, self.start_equity):
            logger.critical("Global Risk Stop Triggered.")
            return # Stop trading
            
        # Log Heartbeat
        log_entry = {
            "ts": datetime.utcnow().isoformat(),
            "mid": mid_price,
            "spread": spread,
            "vol": volatility,
            "score": direction_score,
            "pos": position['amount'] if position else 0,
            "equity": current_equity
        }
        logger.info(f"Heartbeat: {json.dumps(log_entry)}")

        # 6. Trading Logic
        if position:
            self._handle_position(position, direction_score, volatility, mid_price)
        else:
            self._handle_entry(direction_score, volatility, spread, mid_price, current_equity)

    def _handle_entry(self, score, volatility, spread, mid_price, equity):
        # Entry Threshold: Score magnitude > 0.5 (arbitrary for MVP or define in config)
        # Prompt says: "Direction score" -> Long/Short.
        # Let's say abs(score) > 0.4 implies strong conviction.
        
        threshold = 0.4
        
        if abs(score) < threshold:
            return # No signal
            
        direction_str = 'buy' if score > 0 else 'sell'
        
        # Risk Check
        can_trade = self.risk.check_can_trade(spread)
        if not can_trade:
            return
            
        # Sizing
        qty, leverage = self.risk.calculate_position_size_with_spread(
            equity, volatility, mid_price, spread
        )
        
        if qty == 0:
            logger.warning("Risk calc returned 0 size (volatility too high?).")
            return
            
        logger.info(f"Signal: {direction_str.upper()} | Score: {score:.2f} | Vol: {volatility:.4f} | Leverage: {leverage:.2f}x")
        
        # Place Order
        # Using Limit order slightly better than best bid/ask or at mid?
        # Prompt: "Prefer limit orders near mid-price"
        limit_price = mid_price # Simple mid-fill attempt
        
        self.exec.place_limit_order(direction_str, qty, limit_price)
        self.entry_time = datetime.utcnow()

    def _handle_position(self, position, score, volatility, mid_price):
        # 1. Signal Decay
        # If long and score drops < 0, or short and score > 0 -> Exit?
        # Prompt: "Exit ... Signal decay"
        # Let's be strict: if signal flips, exit.
        
        side = position['side']
        should_exit = False
        exit_reason = ""
        
        if side == 'long' and score < -0.1: # Buffer
            should_exit = True
            exit_reason = "Signal Reversal"
        elif side == 'short' and score > 0.1:
            should_exit = True
            exit_reason = "Signal Reversal"
            
        # 2. Volatility Stop / Price Stop
        # Ideally, stop order is placed on exchange.
        # Here we check manually for MVP if we didn't place OCO.
        entry_price = position['entryPrice']
        pnl_pct = (mid_price - entry_price) / entry_price if side == 'long' else (entry_price - mid_price) / entry_price
        
        # Calc stop distance
        # Stop = m * sigma * sqrt(h)
        # If price hit stop -> Exit
        stop_price = self.risk.get_stop_loss_price(entry_price, 1 if side == 'long' else -1, volatility)
        
        stop_hit = False
        if side == 'long' and mid_price < stop_price:
            stop_hit = True
        elif side == 'short' and mid_price > stop_price:
            stop_hit = True
            
        if stop_hit:
            should_exit = True
            exit_reason = "Volatility Stop"

        # 3. Time Stop
        if self.entry_time:
            duration_min = (datetime.utcnow() - self.entry_time).total_seconds() / 60
            if duration_min > Config.MAX_HOLD_DURATION_CANDLES: # Assuming 1m candle count ~= min
                # Only exit if PnL is not favorable? Or hard exit?
                # Prompt: "Position open longer than ... without favorable movement"
                if pnl_pct <= 0:
                    should_exit = True
                    exit_reason = "Time Stop"

        if should_exit:
            logger.info(f"Exiting Position ({side}). Reason: {exit_reason}")
            # Place Market Order to close immediately?
            # Or aggressively priced limit.
            close_side = 'sell' if side == 'long' else 'buy'
            self.exec.place_limit_order(close_side, position['amount'], mid_price)
            
            # Note: A real system would track this close order until filled.
            # Here we reset entry_time
            self.entry_time = None
            
            # Update Risk State?
            # We need realized PnL. ExecutionEngine needs to track fills to give realized PnL.
            # For MVP, we estimate PnL from mid_price close.
            realized_pnl = position['unrealizedPnL'] # Approx
            self.risk.update_pnl_state(realized_pnl, realized_pnl < 0)

if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
