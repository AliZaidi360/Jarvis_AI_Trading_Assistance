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

    def calculate_position_size(self, equity, volatility, mid_price):
        """
        Uses the Volatility-Sizing Logic.
        Notional = (0.005 * Equity) / (2 * Sigma * sqrt(H))
        """
        # 1. Risk Budget: 0.5% of Equity
        risk_amt = Config.RISK_PER_TRADE_PERCENT * equity
        
        # 2. Worst Case Move: 2 * Sigma * sqrt(H)
        # Sigma is per-period (e.g. 1m). H is holding period in candles.
        sqrt_h = math.sqrt(Config.HOLDING_HORIZON_CANDLES)
        worst_case_pct = 2.0 * volatility * sqrt_h
        
        if worst_case_pct == 0:
            return 0.0, 0.0 # No volatility, no trade
            
        # 3. Notional Position Size (USD)
        # RiskAmt = Notional * WorstCasePct
        # -> Notional = RiskAmt / WorstCasePct
        notional_size_usd = risk_amt / worst_case_pct
        
        # 4. Leverage Caps
        # Cap 1: Hard Cap (5x)
        cap1 = Config.MAX_LEVERAGE_CAP
        
        # Cap 2: Volatility scaling (1/Sigma) - "Kelly-ish" heuristic
        cap2 = 1.0 / volatility if volatility > 0 else 5.0
        
        # Cap 3: Spread impact (0.5 / Spread) - Avoid trading when spread ~ edge
        # Assume generic spread for calc or ignore if safe. 
        # Plan said: Leverage = min(5, 1/sigma, 0.5/Spread)
        # We need spread passed in? Let's assume passed in or ignored here.
        # Let's refine signature to take spread if we strictly follow the requirement.
        # I'll stick to the args and maybe assume a safe spread or add it.
        # Let's add 'spread' to args.
        
        final_leverage_cap = min(cap1, cap2)
        
        # Max Notional based on leverage
        max_notional_lev = equity * final_leverage_cap
        
        # Final Position (USD)
        final_position_usd = min(notional_size_usd, max_notional_lev)
        
        # Convert to Quantity (Coins)
        quantity = final_position_usd / mid_price
        
        return quantity, final_position_usd / equity  # Qty, LeverageUsed

    def calculate_position_size_with_spread(self, equity, volatility, mid_price, spread):
        # Overloaded/Helper to include spread cap
        qty, lev = self.calculate_position_size(equity, volatility, mid_price)
        
        # Check Spread Cap
        if spread > 0:
            spread_cap = 0.5 / spread
            current_lev = lev
            if current_lev > spread_cap:
                # Reduce
                target_lev = spread_cap
                qty = (equity * target_lev) / mid_price
                lev = target_lev
        
        return qty, lev

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
