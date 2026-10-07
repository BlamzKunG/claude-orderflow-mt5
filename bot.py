#!/usr/bin/env python3
"""
Claude Sonnet 5 + Institutional Order Flow MT5 Trading Bot
Author: Antigravity AI
"""
import sys
import os
import time
import signal
import logging
from typing import Optional

from config import BotConfig
from claude_client import ClaudeClient, TradeDecision
from orderflow_aggregator import OrderFlowAggregator, TickData
from trailing_stop_engine import TrailingStopEngine, PositionState
from mt5_bridge import MT5Bridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ClaudeOrderFlowBot")

class OrderFlowTradingBot:
    def __init__(self, config_path: str = "config.json"):
        self.cfg = BotConfig.load(config_path)
        self.is_running = True
        
        # 1. Initialize Claude Client
        self.llm = ClaudeClient(
            api_base=self.cfg.llm_api_base,
            api_key=self.cfg.llm_api_key,
            model=self.cfg.llm_model,
            timeout=self.cfg.llm_timeout
        )
        
        # 2. Initialize Order Flow & Footprint Aggregator
        self.aggregator = OrderFlowAggregator(
            symbol=self.cfg.symbol,
            price_step=0.1,  # 0.1 for Gold / XAUUSD
            imbalance_ratio=self.cfg.imbalance_ratio_threshold
        )
        
        # 3. Initialize Rule-Based Trailing Stop Engine
        self.trailing_engine = TrailingStopEngine(
            point_value=0.01,
            breakeven_trigger_points=self.cfg.breakeven_trigger_points,
            breakeven_buffer_points=self.cfg.breakeven_buffer_points,
            trailing_distance_points=self.cfg.trailing_distance_points,
            trailing_step_points=self.cfg.trailing_step_points
        )
        
        # 4. Initialize MT5 Bridge
        self.bridge = MT5Bridge(
            symbol=self.cfg.symbol,
            host=self.cfg.bridge_host,
            port=self.cfg.bridge_port,
            simulation=self.cfg.simulation_mode
        )
        
        # Route live incoming ticks to OrderFlowAggregator
        self.bridge.on_tick_callback = self.on_tick_received
        
        # Timer tracking
        self.last_m5_eval_time = 0.0

    def on_tick_received(self, tick: TickData):
        self.aggregator.on_tick(tick)

    def start(self):
        logger.info("================================================================")
        logger.info(f"🚀 Starting Claude Sonnet 5 Order Flow MT5 Bot ({self.cfg.symbol})")
        logger.info(f"• LLM Model:        {self.cfg.llm_model} via {self.cfg.llm_api_base}")
        logger.info(f"• Timeframe:        {self.cfg.timeframe} (5-Minute Evaluation Cycle)")
        logger.info(f"• Mode:             {'SIMULATION (Paper)' if self.cfg.simulation_mode else 'LIVE MT5 BRIDGE'}")
        logger.info(f"• Trailing Stop:    Breakeven +${self.cfg.breakeven_trigger_points * 0.01:.2f} | Trail ${self.cfg.trailing_distance_points * 0.01:.2f}")
        logger.info("================================================================")
        
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        
        while self.is_running:
            now = time.time()
            current_px = self.bridge.current_price
            active_pos = self.bridge.get_active_position()

            # -------------------------------------------------------------
            # PRIORITY 1: Active Position Management (Local Trailing Stop)
            # -------------------------------------------------------------
            if active_pos and current_px > 0.0:
                # Rule-based trailing stop runs every 1 second with ZERO LLM calls
                new_sl = self.trailing_engine.evaluate(active_pos, current_px)
                if new_sl:
                    self.bridge.modify_sl(active_pos.ticket, new_sl)
            
            # -------------------------------------------------------------
            # PRIORITY 2: 5-Minute LLM Decision Cycle (Only when FLAT)
            # -------------------------------------------------------------
            if (now - self.last_m5_eval_time) >= 300.0:  # 5 minutes = 300s
                self.last_m5_eval_time = now
                
                if active_pos:
                    logger.info(f"⏸️ [M5 CYCLE] Active position #{active_pos.ticket} ({active_pos.order_type}) in progress. SKIPPING LLM call to save costs.")
                elif current_px <= 0.0:
                    logger.info("⏳ Waiting for initial market price stream from MT5...")
                else:
                    self.run_llm_decision_cycle()

            time.sleep(1.0)

    def run_llm_decision_cycle(self):
        logger.info(f"🧠 [M5 CYCLE] No open positions. Gathering Order Flow Footprint for {self.cfg.symbol}...")
        
        # Build comprehensive 50-candle + 5-minute Microstructure payload
        payload = self.aggregator.build_llm_payload()
        
        logger.info(f"📊 Calling Claude Sonnet 5 with POC: ${payload['order_flow_last_5m']['poc_price']} | Delta: {payload['order_flow_last_5m']['cvd_net_delta']}")
        decision = self.llm.analyze_order_flow(payload)
        
        logger.info("----------------------------------------------------------------")
        logger.info(f"🎯 Claude Decision: {decision.action} (Confidence: {decision.confidence}%)")
        logger.info(f"• R:R: 1:{decision.risk_reward} | Entry: {decision.entry_price} | SL: {decision.sl_price} | TP: {decision.tp_price}")
        logger.info(f"• Thesis: {decision.reason}")
        logger.info("----------------------------------------------------------------")

        if decision.is_valid_signal(self.cfg.min_confidence_to_trade):
            logger.info(f"⚡ Executing {decision.action} Signal on MT5...")
            self.bridge.send_order(
                action=decision.action,
                lot=self.cfg.default_lot,
                sl=decision.sl_price,
                tp=decision.tp_price,
                comment=f"Claude5: {decision.action}"
            )
        else:
            logger.info("⏸️ Signal is HOLD or Confidence below threshold. Waiting for next M5 candle.")

    def stop(self, *args):
        logger.info("🛑 Shutting down Claude Order Flow Bot...")
        self.is_running = False


if __name__ == "__main__":
    bot = OrderFlowTradingBot()
    bot.start()
