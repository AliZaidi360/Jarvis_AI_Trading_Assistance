import math
import logging
try:
    from config import Config
except ImportError:
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from config import Config

logger = logging.getLogger(__name__)

class RiskEngine:
    def __init__(self):
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.is_active = True

    def update_pnl_state(self, trade_pnl, is_loss):
        """
        Updates internal risk counters based on closed trade.
        """
        self.daily_pnl += trade_pnl
        if is_loss:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
            
    def check_can_trade(self, spread, market_depth_healthy=True):
        """
        The Master Risk Switch. returns True only if ALL constraints pass.
        """
        # 1. Daily PnL Constraint
        # Daily PnL <= -2% of starting equity? 
        # (Assuming equity tracking is external, simplified here as hard % drop if we knew StartEquity)
        # For now, let's assume External/Bot tracks % Drawdown, or we interpret daily_pnl directly.
        # But Config.MAX_DAILY_DRAWDOWN_PERCENT (0.02) implies -2%.
        # We need equity to calc % drop. We'll pass it in or assume normalized.
        # Let's handle 'Daily PnL < -2%' check in Bot.py using this state or here if we have equity.
        # Here we just check the internal flag:
        if not self.is_active:
            logger.warning("Risk: Agent locked out due to previous risk violation.")
            return False

        # 2. Loss Streak
        if self.consecutive_losses >= Config.MAX_CONSECUTIVE_LOSSES:
            logger.warning(f"Risk: Max consecutive losses reached ({self.consecutive_losses}). Trading halted.")
            return False
            
        # 3. Spread Check
        if spread > Config.MAX_SPREAD_THRESHOLD:
            logger.warning(f"Risk: Spread {spread} exceeds max {Config.MAX_SPREAD_THRESHOLD}.")
            return False
            
        # 4. Liquidity/Conditions
        if not market_depth_healthy:
            logger.warning("Risk: Market depth unhealthy.")
            return False
            
        return True

    def check_daily_drawdown(self, equity, start_equity):
        """
        Called after PnL update to check if we breached the daily limit.
        """
        current_dd = (equity - start_equity) / start_equity
        if current_dd <= -Config.MAX_DAILY_DRAWDOWN_PERCENT:
            logger.critical(f"Risk: Daily drawdown {current_dd:.2%} exceeds limit {-Config.MAX_DAILY_DRAWDOWN_PERCENT:.2%}. STOPPING.")
            self.is_active = False
            return False
        return True

    def calculate_position_size(self, equity, volatility, mid_price, spread=None):
        """
        HARD-CODED FORMULAS (DO NOT OPTIMIZE):
        1. Worst Case Move: Delta_wc = 2 * sigma * sqrt(h)
        2. Notional: (0.005 * Equity) / Delta_wc
        3. Leverage Cap: min(5, 1/sigma, 0.5/spread)
        """
        # 1. Risk Budget: 0.5% of Equity
        # Formula: Notional = 0.005 * Equity / Delta_wc
        risk_per_trade = Config.RISK_PER_TRADE_PERCENT # 0.005
        
        # 2. Worst Case Move
        sqrt_h = math.sqrt(Config.HOLDING_HORIZON_CANDLES)
        if volatility <= 0:
            return 0.0, 0.0

        # Delta_wc = 2 * sigma * sqrt(h)
        worst_case_pct = 2.0 * volatility * sqrt_h
        
        # 3. Position Notional
        if worst_case_pct == 0:
            notional_size_usd = 0.0
        else:
            notional_size_usd = (risk_per_trade * equity) / worst_case_pct
        
        # 4. Leverage Caps
        # Lev = min(5, 1/sigma, 0.5/Spread)
        cap1 = Config.MAX_LEVERAGE_CAP # 5.0
        cap2 = 1.0 / volatility
        
        cap3 = float('inf')
        if spread and spread > 0:
            cap3 = 0.5 / spread
            
        final_leverage_cap = min(cap1, cap2, cap3)
        
        # Max Notional based on leverage
        max_notional_lev = equity * final_leverage_cap
        
        # Final Position (USD)
        final_position_usd = min(notional_size_usd, max_notional_lev)
        
        # Convert to Quantity (Coins)
        quantity = final_position_usd / mid_price
        
        return quantity, final_position_usd / equity  # Qty, LeverageUsed

    def get_stop_loss_price(self, entry_price, direction, volatility):
        """
        Stop = m * Sigma * sqrt(H)
        """
        sqrt_h = math.sqrt(Config.HOLDING_HORIZON_CANDLES)
        move_pct = Config.STOP_LOSS_M_FACTOR * volatility * sqrt_h
        
        if direction == 1: # Long
            return entry_price * (1 - move_pct)
        else: # Short
            return entry_price * (1 + move_pct)
