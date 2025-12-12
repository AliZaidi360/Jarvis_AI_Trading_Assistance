import unittest
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.risk import RiskEngine
from config import Config

class TestRiskEngine(unittest.TestCase):
    def test_loss_streak_halt(self):
        risk = RiskEngine()
        # Simulate losses
        for _ in range(Config.MAX_CONSECUTIVE_LOSSES):
            risk.update_pnl_state(-10, True)
            
        # Should be locked out
        self.assertFalse(risk.check_can_trade(0.0001))

    def test_daily_drawdown_stop(self):
        risk = RiskEngine()
        start_equity = 1000.0
        # Drawdown limit is 2% = $20
        
        # Current equity drops to 975 (> 2% drop)
        is_ok = risk.check_daily_drawdown(975.0, start_equity)
        pass_check = risk.check_can_trade(0.0001)
        
        self.assertFalse(is_ok)
        # Internal flag should have flipped
        self.assertFalse(risk.is_active)
        self.assertFalse(pass_check)

    def test_position_sizing_leverage_cap(self):
        risk = RiskEngine()
        equity = 10000.0
        mid_price = 50000.0
        
        # Super low volatility -> Huge size theoretically
        # But should be capped at MAX_LEVERAGE (5x)
        volatility = 0.00001 
        
        qty, leverage = risk.calculate_position_size(equity, volatility, mid_price)
        
        # Be lenient with float
        self.assertLessEqual(leverage, Config.MAX_LEVERAGE_CAP + 0.01)
        self.assertGreater(leverage, 0)

    def test_position_sizing_volatility_cap(self):
        risk = RiskEngine()
        equity = 10000.0
        mid_price = 50000.0
        
        # High volatility -> Reduced size
        # Vol = 5% per candle
        volatility = 0.05
        
        # Risk Budget = 0.5% = $50
        # Worst Case = 2 * 0.05 * sqrt(240) = 0.1 * 15.49 = 1.549 (155% move)
        # Notional = 50 / 1.549 = $32
        # Leverage = 32 / 10000 = 0.0032x
        
        qty, leverage = risk.calculate_position_size(equity, volatility, mid_price)
        
        self.assertLess(leverage, 0.1) # Should be very small

if __name__ == '__main__':
    unittest.main()
