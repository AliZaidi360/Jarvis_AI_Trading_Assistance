import logging
import time
try:
    from config import Config
except ImportError:
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from config import Config

logger = logging.getLogger(__name__)

class ExecutionEngine:
    def __init__(self, exchange):
        self.exchange = exchange
        self.symbol = Config.SYMBOL
        self.pending_orders = {} # {id: timestamp}

    def get_position(self):
        """
        Returns {'amount': float, 'entryPrice': float, 'unrealizedPnL': float, 'side': 'long'|'short'|None}
        """
        try:
            # CCXT fetch_position structure varies, often list.
            positions = self.exchange.fetch_positions([self.symbol])
            if not positions:
                return None
                
            # Find the specific symbol position
            # Binance returns a list, filter by symbol
            pos = next((p for p in positions if p['symbol'] == self.symbol), None)
            
            if not pos:
                return None
                
            qty = float(pos['contracts']) if 'contracts' in pos else float(pos['info']['positionAmt'])
            
            if qty == 0:
                return None
                
            side = 'long' if qty > 0 else 'short'
            
            return {
                'amount': abs(qty),
                'entryPrice': float(pos['entryPrice']),
                'unrealizedPnL': float(pos['unrealizedPnl']),
                'side': side,
                'raw': pos
            }
        except Exception as e:
            logger.error(f"Error fetching position: {e}")
            return None

    def place_limit_order(self, side, amount, price):
        """
        Places a limit order.
        side: 'buy' or 'sell'
        """
        try:
            logger.info(f"Placing {side} LIMIT order: {amount} @ {price}")
            order = self.exchange.create_order(
                symbol=self.symbol,
                type='limit',
                side=side,
                amount=amount,
                price=price
            )
            # Track for timeout
            self.pending_orders[order['id']] = time.time()
            return order
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return None

    def cancel_order(self, order_id):
        try:
            self.exchange.cancel_order(order_id, self.symbol)
            if order_id in self.pending_orders:
                del self.pending_orders[order_id]
            logger.info(f"Cancelled order {order_id}")
        except Exception as e:
            logger.warning(f"Error canceling order: {e}")

    def check_timeouts(self):
        """
        Cancels orders that have been open longer than timeout.
        """
        now = time.time()
        to_cancel = []
        
        for oid, ts in self.pending_orders.items():
            if (now - ts) > Config.ORDER_TIMEOUT_SECONDS:
                to_cancel.append(oid)
        
        for oid in to_cancel:
            logger.info(f"Order {oid} timed out. Cancelling.")
            self.cancel_order(oid)

    def fetch_balance(self):
        """
        Returns dict with 'total' and 'free' USDT (likely).
        """
        try:
            bal = self.exchange.fetch_balance()
            # Assuming trading USDT perpetual
            asset = 'USDT'
            if asset in bal:
                return bal[asset]
            return bal['total'] # Fallback
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return {'total': 0, 'free': 0}
