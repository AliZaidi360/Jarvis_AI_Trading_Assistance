import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

class PaperExecutionEngine:
    def __init__(self, initial_equity=10000.0):
        self.equity = initial_equity
        self.position = None # {amount, entry_price, side, timestamp}
        self.pending_orders = {}
        
    def fetch_balance(self):
        # Mimic CCXT structure: {'total': ...}
        return {'total': self.equity, 'free': self.equity} # Simplified
        
    def get_position(self):
        """
        Returns position dict if active, else None.
        Calculates unrealized PnL dynamically based on LAST execution fill logic?
        Actually, Caller (Bot) usually passes current mid_price to calc PnL.
        This function just returns state.
        """
        if not self.position:
            return None
            
        return {
            'amount': self.position['amount'],
            'entryPrice': self.position['entry_price'],
            'side': self.position['side'],
            'unrealizedPnL': 0.0, # Let Bot calc this with fresh price
            'timestamp': self.position['timestamp']
        }

    def place_limit_order(self, side, amount, price):
        """
        Paper Trading: Immediate fill logic based on current market data passed implicitly?
        Wait, I don't have current market data here.
        The caller passed 'price' (usually mid).
        
        Rule: 
        LONG -> mid * (1 + spread/2)
        SHORT -> mid * (1 - spread/2)
        
        The 'price' arg passed by Bot is 'mid_price' usually (see bot.py).
        So we will use that as the base 'mid'.
        We need 'spread' to apply the penalty. 
        Arg 'price' is strictly strictly the limit price. 
        But in Paper Sim, we assume we fill IF the market allows.
        For MVP, we will Assume Immediate Fill at the 'cost' price.
        
        We need 'spread' to calculate fill price. 
        I'll modify the signature or assume a fixed spread cost if strictly following interface?
        Actually, in `paper_execution.py`, I can't easily see the live spread unless passed.
        
        Modification: I'll assume the 'price' passed IS the fill price desired, 
        BUT the Bot calculates fill price? NO, Bot passes limit_price.
        
        Let's update the Logic:
        If `PaperExecutionEngine` needs to simulate spread cost, it needs the spread.
        However, the interface `place_limit_order(side, amount, price)` is fixed by `bot.py`.
        
        Option A: Update `bot.py` to pass spread.
        Option B: Assume 'price' passed IS the Mid Price (it is in bot.py) and apply valid fill logic here.
        But I don't know the spread here.
        
        Workaround: The User Req says "Entry fill: LONG -> mid_price * (1 + spread / 2)".
        I will add `set_market_state(mid, spread)` method or similar, OR just assume a default conservative spread for execution if not available, OR better:
        
        The `bot.py` calls `place_limit_order(..., limit_price)`.
        I will modify `bot.py` anyway for event logging. I can pass `spread` to execution there?
        Or, I can make `PaperExecutionEngine` take `current_spread` as a property set by the bot before execution.
        
        Let's go with: `execute_paper_trade(side, amount, mid_price, spread)` and update Bot to call THAT if paper.
        But to keep `ExecutionEngine` interface polymorphic:
        I will strictly just fill at `price`.
        The BOT should calculate the "Fill Price" (Mid + Spread/2) and pass IT as the limit price?
        No, Limit Price != Fill Price usually.
        
        Let's stick to the Interface. I will simply log the fill at `price` for now, 
        OR I'll update `bot.py` to calculate the "Simulated Fill Price" and pass THAT as `price`.
        
        Actually, the cleanest way for Phase 2:
        Update `bot.py` to calculate `fill_price = mid * (1 + spread/2)` and pass that to `place_limit_order`.
        So PaperExecutionEngine just treats `price` as the Execution Price.
        """
        fill_price = price
        cost = fill_price * amount
        
        ts = datetime.utcnow()
        
        if self.position:
            # Closing or Flipping?
            # MVP: Only 1 position. If side != pos.side, we are closing.
            if self.position['side'] != side:
                # Closing
                entry_val = self.position['entry_price'] * self.position['amount']
                exit_val = fill_price * amount
                
                # PnL
                if self.position['side'] == 'long': # Sell to close
                    pnl = exit_val - entry_val
                else: # Buy to close
                    pnl = entry_val - exit_val
                    
                self.equity += pnl
                logger.info(f"PAPER TRADE: Closed {self.position['side']} | PnL: {pnl:.2f} | New Equity: {self.equity:.2f}")
                self.position = None
                return {'id': f"paper_close_{int(time.time())}", 'price': fill_price, 'status': 'closed'}
                
            else:
                # Adding to position? Not supported in MVP usually.
                logger.warning("Paper: Adding to position not supported in MVP. Ignoring.")
                return None
        else:
            # Opening
            self.position = {
                'amount': amount,
                'entry_price': fill_price,
                'side': side,
                'timestamp': ts.isoformat()
            }
            logger.info(f"PAPER TRADE: Opened {side} @ {fill_price:.2f} | Size: {amount:.4f}")
            return {'id': f"paper_open_{int(time.time())}", 'price': fill_price, 'status': 'open'}

    def check_timeouts(self):
        pass # Immediate fills, no timeouts

