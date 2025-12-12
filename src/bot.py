import logging
import time
import json
from datetime import datetime
try:
    from config import Config
    from src.market_data import MarketData
    # from src.execution import ExecutionEngine # Deprecated for Phase 2
    from src.paper_execution import PaperExecutionEngine
    from src.risk import RiskEngine
    from src.alpha import AlphaEngine
    from src.llm_explainer import LLMExplainer
    import threading
except ImportError:
    # Fallback for relative
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from config import Config
    from src.market_data import MarketData
    from src.paper_execution import PaperExecutionEngine
    # from src.execution import ExecutionEngine
    from src.risk import RiskEngine
    from src.alpha import AlphaEngine
    from src.llm_explainer import LLMExplainer
    import threading

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
        logger.info("Initializing Agent (Paper Trading Mode)...")
        self.md = MarketData()
        # self.exec = ExecutionEngine(self.md.exchange)
        self.exec = PaperExecutionEngine(initial_equity=10000.0)
        self.risk = RiskEngine()
        self.alpha = AlphaEngine()
        self.explainer = LLMExplainer(Config.LLM_API_KEY)
        
        # State
        self.entry_time = None
        self.events_log_path = "events.log"
        
        # For PnL Tracking (simple)
        self.start_equity = 10000.0

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

    def _async_explain(self, log_entry):
        """
        Background task to generate explanation
        """
        try:
            explanation = self.explainer.generate_explanation(log_entry)
            # Log the explanation as a clear separate event
            logger.info(f"JARVIS_EXPLAINER: {explanation}")
        except Exception as e:
            logger.error(f"Explainer Failed: {e}")

    def log_decision(self, decision_type, reason, metrics):
        """
        Structured logging for Decision Explanations.
        decision_type: TRADE_EXECUTED | TRADE_SKIPPED | RISK_LOCKED
        """
        log_entry = {
            "ts": datetime.utcnow().isoformat(),
            "type": decision_type,
            "reason": reason,
            "metrics": metrics
        }
        
        # 1. Main Application Log
        logger.info(f"DECISION: {json.dumps(log_entry)}")
        
        # 2. Events Log (for UI/Backend)
        try:
            with open(self.events_log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write to events log: {e}")
        
        # 3. Trigger LLM Explanation in background
        threading.Thread(target=self._async_explain, args=(log_entry,)).start()

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
        
        # Metrics snapshot for logging
        current_metrics = {
            "price": mid_price,
            "spread": spread,
            "volatility": volatility,
            "score": direction_score,
            "equity": current_equity,
            "imbalance_book": book_imb,
            "imbalance_flow": flow_imb
        }

        # 5. Risk Checks (Global)
        self.exec.check_timeouts()
        if not self.risk.check_daily_drawdown(current_equity, self.start_equity):
            self.log_decision("RISK_LOCKED", "DAILY_DRAWDOWN_LIMIT", current_metrics)
            logger.critical("Global Risk Stop Triggered.")
            return # Stop trading

        # Internal lockout check (loss streak etc)
        if not self.risk.is_active:
             self.log_decision("RISK_LOCKED", "PREVIOUS_RISK_VIOLATION", current_metrics)
             return

        # Log Heartbeat
        log_entry = {
            "ts": datetime.utcnow().isoformat(),
            "mid": mid_price,
            "score": direction_score,
            "pos": position['amount'] if position else 0,
        }
        logger.info(f"Heartbeat: {json.dumps(log_entry)}")

        # 6. Trading Logic
        if position:
            self._handle_position(position, direction_score, volatility, mid_price, current_metrics, spread)
        else:
            self._handle_entry(direction_score, volatility, spread, mid_price, current_equity, current_metrics)

    def _handle_entry(self, score, volatility, spread, mid_price, equity, metrics):
        # Entry Threshold
        threshold = 0.4
        
        if abs(score) < threshold:
            self.log_decision("TRADE_SKIPPED", "WEAK_SIGNAL", metrics)
            return 
            
        direction_str = 'buy' if score > 0 else 'sell'
        
        # Risk Check
        can_trade = self.risk.check_can_trade(spread)
        if not can_trade:
            # Determine specific risk reason (approximate re-check for logging)
            reason = "RISK_CONSTRAINT"
            if spread > Config.MAX_SPREAD_THRESHOLD:
                reason = "SPREAD_TOO_HIGH"
            elif self.risk.consecutive_losses >= Config.MAX_CONSECUTIVE_LOSSES:
                reason = "MAX_CONSECUTIVE_LOSSES"
            
            self.log_decision("TRADE_SKIPPED", reason, metrics)
            return
            
        # Sizing
        # HARD-CODED FORMULA ENFORCEMENT via RiskEngine
        qty, leverage = self.risk.calculate_position_size(
            equity, volatility, mid_price, spread
        )
        
        metrics['calculated_leverage'] = leverage
        metrics['calculated_qty'] = qty

        if qty == 0:
            self.log_decision("TRADE_SKIPPED", "ZERO_SIZE_CALC (High Vol?)", metrics)
            logger.warning("Risk calc returned 0 size (volatility too high?).")
            return
            
        logger.info(f"Signal: {direction_str.upper()} | Score: {score:.2f} | Vol: {volatility:.4f} | Leverage: {leverage:.2f}x")
        
        # Place Order (SIMULATING SPREAD CROSSING)
        # Buy at Ask (Mid + Spread/2), Sell at Bid (Mid - Spread/2)
        fill_price = mid_price * (1 + spread/2) if direction_str == 'buy' else mid_price * (1 - spread/2)
        
        order = self.exec.place_limit_order(direction_str, qty, fill_price)
        
        if order:
            self.log_decision("TRADE_EXECUTED", f"ENTRY_{direction_str.upper()}", metrics)
            self.entry_time = datetime.utcnow()
        else:
            self.log_decision("TRADE_SKIPPED", "ORDER_SUBMISSION_FAILED", metrics)

    def _handle_position(self, position, score, volatility, mid_price, metrics, spread):
        side = position['side']
        should_exit = False
        exit_reason = ""
        
        metrics['position_pnl'] = position['unrealizedPnL'] # Placeholder, handled by exec generally
        metrics['position_side'] = side

        # 1. Signal Decay
        if side == 'long' and score < -0.1: 
            should_exit = True
            exit_reason = "SIGNAL_REVERSAL"
        elif side == 'short' and score > 0.1:
            should_exit = True
            exit_reason = "SIGNAL_REVERSAL"
            
        # 2. Volatility Stop
        entry_price = position['entryPrice']
        pnl_pct = (mid_price - entry_price) / entry_price if side == 'long' else (entry_price - mid_price) / entry_price
        
        stop_price = self.risk.get_stop_loss_price(entry_price, 1 if side == 'long' else -1, volatility)
        
        stop_hit = False
        if side == 'long' and mid_price < stop_price:
            stop_hit = True
        elif side == 'short' and mid_price > stop_price:
            stop_hit = True
            
        if stop_hit:
            should_exit = True
            exit_reason = "VOLATILITY_STOP"

        # 3. Time Stop
        if self.entry_time:
            duration_min = (datetime.utcnow() - self.entry_time).total_seconds() / 60
            if duration_min > Config.MAX_HOLD_DURATION_CANDLES: 
                if pnl_pct <= 0:
                    should_exit = True
                    exit_reason = "TIME_STOP"

        if should_exit:
            logger.info(f"Exiting Position ({side}). Reason: {exit_reason}")
            close_side = 'sell' if side == 'long' else 'buy'
            
            # SIMULATING SPREAD CROSSING
            fill_price = mid_price * (1 - spread/2) if close_side == 'sell' else mid_price * (1 + spread/2)

            self.exec.place_limit_order(close_side, position['amount'], fill_price)
            
            self.log_decision("TRADE_EXECUTED", f"EXIT_{exit_reason}", metrics)

            self.entry_time = None
            # Approx PnL update (Risk Engine tracks naive PnL for streaks)
            realized_pnl = (fill_price - entry_price) * position['amount'] if side == 'long' else (entry_price - fill_price) * position['amount']
            self.risk.update_pnl_state(realized_pnl, realized_pnl < 0)
        else:
            # Just holding
            pass 


if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
