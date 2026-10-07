import logging
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger("TrailingStopEngine")

@dataclass
class PositionState:
    ticket: int
    symbol: str
    order_type: str         # "BUY" or "SELL"
    volume: float
    open_price: float
    current_sl: float
    current_tp: float
    highest_price: float    # Peak price since entry (for BUY)
    lowest_price: float     # Lowest price since entry (for SELL)
    is_breakeven_set: bool = False


class TrailingStopEngine:
    """
    Local Rule-Based Trailing Stop Engine.
    Executes every 1 second when an order is open with ZERO LLM calls.
    Protects profits, moves SL to Breakeven, and locks in gains dynamically.
    """
    def __init__(
        self,
        point_value: float = 0.01,
        breakeven_trigger_points: float = 150.0,  # $1.5 on Gold
        breakeven_buffer_points: float = 20.0,    # $0.2 profit buffer
        trailing_distance_points: float = 200.0,  # $2.0 trailing distance
        trailing_step_points: float = 50.0        # $0.5 step update
    ):
        self.point_value = point_value
        self.be_trigger = breakeven_trigger_points * self.point_value
        self.be_buffer = breakeven_buffer_points * self.point_value
        self.trail_dist = trailing_distance_points * self.point_value
        self.trail_step = trailing_step_points * self.point_value

    def evaluate(self, pos: PositionState, current_price: float) -> Optional[float]:
        """
        Evaluates position state against current market price.
        Returns new SL price if an update is required, or None if no change.
        """
        if pos.order_type == "BUY":
            return self._evaluate_buy(pos, current_price)
        elif pos.order_type == "SELL":
            return self._evaluate_sell(pos, current_price)
        return None

    def _evaluate_buy(self, pos: PositionState, current_price: float) -> Optional[float]:
        # Track highest price
        if current_price > pos.highest_price:
            pos.highest_price = current_price

        profit_points = current_price - pos.open_price

        # 1. Breakeven Check
        if not pos.is_breakeven_set and profit_points >= self.be_trigger:
            new_sl = round(pos.open_price + self.be_buffer, 2)
            if new_sl > pos.current_sl:
                pos.is_breakeven_set = True
                logger.info(f"🛡️ [BUY #{pos.ticket}] Triggering BREAKEVEN! Move SL: {pos.current_sl} -> {new_sl}")
                return new_sl

        # 2. Dynamic Trailing Stop
        if profit_points >= self.trail_dist:
            target_sl = round(pos.highest_price - self.trail_dist, 2)
            # Only update if improvement is at least trail_step
            if target_sl >= (pos.current_sl + self.trail_step):
                logger.info(f"📈 [BUY #{pos.ticket}] Trailing SL Upward: {pos.current_sl} -> {target_sl} (Peak: {pos.highest_price})")
                return target_sl

        return None

    def _evaluate_sell(self, pos: PositionState, current_price: float) -> Optional[float]:
        # Track lowest price
        if current_price < pos.lowest_price or pos.lowest_price == 0.0:
            pos.lowest_price = current_price

        profit_points = pos.open_price - current_price

        # 1. Breakeven Check
        if not pos.is_breakeven_set and profit_points >= self.be_trigger:
            new_sl = round(pos.open_price - self.be_buffer, 2)
            if pos.current_sl == 0.0 or new_sl < pos.current_sl:
                pos.is_breakeven_set = True
                logger.info(f"🛡️ [SELL #{pos.ticket}] Triggering BREAKEVEN! Move SL: {pos.current_sl} -> {new_sl}")
                return new_sl

        # 2. Dynamic Trailing Stop
        if profit_points >= self.trail_dist:
            target_sl = round(pos.lowest_price + self.trail_dist, 2)
            # Only update if improvement is at least trail_step
            if pos.current_sl == 0.0 or target_sl <= (pos.current_sl - self.trail_step):
                logger.info(f"📉 [SELL #{pos.ticket}] Trailing SL Downward: {pos.current_sl} -> {target_sl} (Low: {pos.lowest_price})")
                return target_sl

        return None
