import time
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

@dataclass
class TickData:
    time: float
    price: float
    volume: float
    bid: float
    ask: float
    side: str  # "Buy" or "Sell"

@dataclass
class CandleM5:
    time_str: str
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    delta: float
    vwap: float

@dataclass
class PriceLevelFootprint:
    price: float
    bid_vol: float = 0.0
    ask_vol: float = 0.0

    @property
    def total_vol(self) -> float:
        return self.bid_vol + self.ask_vol

    @property
    def delta(self) -> float:
        return self.ask_vol - self.bid_vol  # Ask is buy taker, Bid is sell taker


class OrderFlowAggregator:
    """
    Real-Time Order Flow & Microstructure Footprint Aggregator.
    Captures tick streams (every 1-5s), computes Volume at Price (Footprint),
    POC, Stacked Imbalances, CVD Delta, and 50-candle M5 rolling history.
    """
    def __init__(self, symbol: str = "XAUUSD", price_step: float = 0.1, imbalance_ratio: float = 3.0):
        self.symbol = symbol
        self.price_step = price_step
        self.imbalance_ratio = imbalance_ratio
        
        # Current 5m Candle Tracking
        self.bar_start_time: float = 0.0
        self.current_open: float = 0.0
        self.current_high: float = 0.0
        self.current_low: float = 0.0
        self.current_close: float = 0.0
        self.current_volume: float = 0.0
        
        # Footprint Profile for the current 5m bar {rounded_price: PriceLevelFootprint}
        self.footprint: Dict[float, PriceLevelFootprint] = {}
        
        # 1-Minute Micro-Slices inside the 5m bar (list of dicts)
        self.minute_slices: List[Dict[str, Any]] = []
        self.current_slice_start: float = 0.0
        self.current_slice_delta: float = 0.0
        self.current_slice_vol: float = 0.0
        self.current_slice_high: float = 0.0
        self.current_slice_low: float = 0.0
        
        # Cumulative Volume Delta (CVD)
        self.bar_buy_vol: float = 0.0
        self.bar_sell_vol: float = 0.0
        self.cum_cvd: float = 0.0
        
        # Orderbook Resting Walls (DOM)
        self.best_bid: float = 0.0
        self.best_ask: float = 0.0
        self.bid_walls: List[Tuple[float, float]] = []  # [(price, size), ...]
        self.ask_walls: List[Tuple[float, float]] = []
        
        # 50-Bar Rolling History
        self.candles_history: deque[CandleM5] = deque(maxlen=50)
        self.last_candle_time: float = 0.0

    def round_price(self, price: float) -> float:
        return round(round(price / self.price_step) * self.price_step, 2)

    def on_tick(self, tick: TickData):
        now = tick.time if tick.time > 0 else time.time()
        
        # Initialize bar if empty or new 5-minute interval (300 seconds)
        if self.bar_start_time == 0.0 or (now - self.bar_start_time) >= 300.0:
            if self.bar_start_time > 0.0:
                self._finalize_current_bar(now)
            self._start_new_bar(now, tick.price)

        # Update Bar OHLC
        if self.current_open == 0.0:
            self.current_open = tick.price
            self.current_high = tick.price
            self.current_low = tick.price
        else:
            self.current_high = max(self.current_high, tick.price)
            self.current_low = min(self.current_low, tick.price)
        self.current_close = tick.price
        self.current_volume += tick.volume

        # Update Footprint at price level
        px_key = self.round_price(tick.price)
        if px_key not in self.footprint:
            self.footprint[px_key] = PriceLevelFootprint(price=px_key)
            
        if tick.side == "Buy":
            self.footprint[px_key].ask_vol += tick.volume
            self.bar_buy_vol += tick.volume
            self.cum_cvd += tick.volume
            self.current_slice_delta += tick.volume
        else:
            self.footprint[px_key].bid_vol += tick.volume
            self.bar_sell_vol += tick.volume
            self.cum_cvd -= tick.volume
            self.current_slice_delta -= tick.volume

        # Update 1-minute micro slices
        self.current_slice_vol += tick.volume
        self.current_slice_high = max(self.current_slice_high, tick.price)
        self.current_slice_low = min(self.current_slice_low, tick.price) if self.current_slice_low > 0 else tick.price
        
        if (now - self.current_slice_start) >= 60.0:
            self._finalize_slice(now)

    def update_dom(self, best_bid: float, best_ask: float, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]]):
        self.best_bid = best_bid
        self.best_ask = best_ask
        self.bid_walls = sorted(bids, key=lambda x: x[1], reverse=True)[:3]
        self.ask_walls = sorted(asks, key=lambda x: x[1], reverse=True)[:3]

    def _start_new_bar(self, start_time: float, price: float):
        self.bar_start_time = start_time
        self.current_open = price
        self.current_high = price
        self.current_low = price
        self.current_close = price
        self.current_volume = 0.0
        self.bar_buy_vol = 0.0
        self.bar_sell_vol = 0.0
        self.footprint.clear()
        self.minute_slices.clear()
        
        self.current_slice_start = start_time
        self.current_slice_delta = 0.0
        self.current_slice_vol = 0.0
        self.current_slice_high = price
        self.current_slice_low = price

    def _finalize_slice(self, now: float):
        minute_num = len(self.minute_slices) + 1
        self.minute_slices.append({
            "minute": f"Min {minute_num}",
            "high": round(self.current_slice_high, 2),
            "low": round(self.current_slice_low, 2),
            "volume": round(self.current_slice_vol, 2),
            "delta": round(self.current_slice_delta, 2)
        })
        self.current_slice_start = now
        self.current_slice_delta = 0.0
        self.current_slice_vol = 0.0
        self.current_slice_high = self.current_close
        self.current_slice_low = self.current_close

    def _finalize_current_bar(self, now: float):
        # Push completed candle into rolling history
        delta = self.bar_buy_vol - self.bar_sell_vol
        vwap = (self.current_high + self.current_low + self.current_close) / 3.0
        
        time_str = time.strftime("%H:%M", time.localtime(self.bar_start_time))
        candle = CandleM5(
            time_str=time_str,
            timestamp=self.bar_start_time,
            open=self.current_open,
            high=self.current_high,
            low=self.current_low,
            close=self.current_close,
            volume=round(self.current_volume, 2),
            delta=round(delta, 2),
            vwap=round(vwap, 2)
        )
        self.candles_history.append(candle)

    def seed_candles_from_mt5(self, ohlc_list: List[Dict[str, Any]]):
        """Pre-populate 50 historical candles from MT5 copy_rates"""
        self.candles_history.clear()
        for item in ohlc_list[-50:]:
            vwap = (item["high"] + item["low"] + item["close"]) / 3.0
            ts = item.get("time", 0)
            time_str = time.strftime("%H:%M", time.localtime(ts)) if ts > 0 else "N/A"
            candle = CandleM5(
                time_str=time_str,
                timestamp=ts,
                open=item["open"],
                high=item["high"],
                low=item["low"],
                close=item["close"],
                volume=round(item.get("volume", 0.0), 2),
                delta=round(item.get("delta", 0.0), 2),
                vwap=round(vwap, 2)
            )
            self.candles_history.append(candle)

    def calculate_poc(self) -> Tuple[float, float]:
        """Returns (poc_price, poc_volume)"""
        if not self.footprint:
            return (self.current_close, 0.0)
        poc = max(self.footprint.values(), key=lambda fp: fp.total_vol)
        return (poc.price, round(poc.total_vol, 2))

    def detect_stacked_imbalances(self) -> List[Dict[str, Any]]:
        """
        Detects diagonal or price-level volume imbalances (300%+ ratio).
        """
        imbalances = []
        sorted_levels = sorted(self.footprint.values(), key=lambda x: x.price, reverse=True)
        
        for fp in sorted_levels:
            if fp.bid_vol > 0 and (fp.ask_vol / fp.bid_vol) >= self.imbalance_ratio:
                ratio = round(fp.ask_vol / fp.bid_vol, 1)
                imbalances.append({
                    "price": fp.price,
                    "type": f"BUY_IMBALANCE_{ratio}X",
                    "bid_vol": round(fp.bid_vol, 2),
                    "ask_vol": round(fp.ask_vol, 2)
                })
            elif fp.ask_vol > 0 and (fp.bid_vol / fp.ask_vol) >= self.imbalance_ratio:
                ratio = round(fp.bid_vol / fp.ask_vol, 1)
                imbalances.append({
                    "price": fp.price,
                    "type": f"SELL_IMBALANCE_{ratio}X",
                    "bid_vol": round(fp.bid_vol, 2),
                    "ask_vol": round(fp.ask_vol, 2)
                })
        return imbalances[:5]

    def build_llm_payload(self) -> Dict[str, Any]:
        """
        Compiles the complete 50-candle context + 5-minute deep Order Flow
        ready to send to Claude Sonnet 5.
        """
        poc_price, poc_vol = self.calculate_poc()
        imbalances = self.detect_stacked_imbalances()
        net_delta = round(self.bar_buy_vol - self.bar_sell_vol, 2)
        tot_vol = max(self.current_volume, 0.001)
        bid_ratio = round((self.bar_buy_vol / (self.bar_buy_vol + self.bar_sell_vol + 0.001)) * 100)
        
        # 50 Candles Summary
        candles_data = []
        high_50 = 0.0
        low_50 = 999999.0
        for c in self.candles_history:
            high_50 = max(high_50, c.high)
            low_50 = min(low_50, c.low)
            candles_data.append({
                "time": c.time_str,
                "o": c.open,
                "h": c.high,
                "l": c.low,
                "c": c.close,
                "vol": c.volume,
                "delta": f"{c.delta:+.1f}"
            })
            
        current_vwap = round((self.current_high + self.current_low + self.current_close) / 3.0, 2)
        
        return {
            "symbol": self.symbol,
            "timeframe": "M5",
            "current_price": round(self.current_close, 2),
            "market_structure_m5": {
                "high_50_bars": round(high_50, 2) if high_50 > 0 else round(self.current_high, 2),
                "low_50_bars": round(low_50, 2) if low_50 < 999999.0 else round(self.current_low, 2),
                "vwap": current_vwap,
                "recent_candles": candles_data[-10:],  # Send last 10 candles detail + 50 bars macro
                "total_candles_analyzed": len(self.candles_history)
            },
            "order_flow_last_5m": {
                "bar_range": f"[{round(self.current_low, 2)} - {round(self.current_high, 2)}]",
                "total_volume": round(self.current_volume, 2),
                "cvd_net_delta": f"{net_delta:+.1f} oz",
                "delta_pct": f"{bid_ratio}% Buy vs {100 - bid_ratio}% Sell",
                "poc_price": poc_price,
                "poc_volume": f"{poc_vol} oz",
                "minute_by_minute_slices": self.minute_slices,
                "stacked_imbalances": imbalances,
                "dom_liquidity_walls": {
                    "top_bid_wall": self.bid_walls[0] if self.bid_walls else (0.0, 0.0),
                    "top_ask_wall": self.ask_walls[0] if self.ask_walls else (0.0, 0.0)
                }
            }
        }
