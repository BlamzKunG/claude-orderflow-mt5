#!/usr/bin/env python3
"""
Test script to verify calling Claude Sonnet 5 via maxplus-ai endpoint
"""
import sys
import logging
from config import BotConfig
from claude_client import ClaudeClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    print("==================================================")
    print("🧪 Testing Claude Sonnet 5 Connection & Decision")
    print("==================================================")
    
    cfg = BotConfig.load("config.json")
    print(f"• Endpoint: {cfg.llm_api_base}")
    print(f"• Model:    {cfg.llm_model}")
    print(f"• Symbol:   {cfg.symbol} ({cfg.timeframe})")
    
    client = ClaudeClient(
        api_base=cfg.llm_api_base,
        api_key=cfg.llm_api_key,
        model=cfg.llm_model,
        timeout=cfg.llm_timeout
    )
    
    # Mock realistic Gold 50-candle context + 5m Order Flow microstructure
    sample_payload = {
        "symbol": cfg.symbol,
        "timeframe": cfg.timeframe,
        "current_price": 4145.80,
        "market_structure_m5": {
            "trend": "BULLISH_PULLBACK_TO_SUPPORT",
            "last_50_bars_summary": {
                "high_50": 4158.00,
                "low_50": 4138.50,
                "vwap": 4144.20,
                "recent_candles": [
                    {"time": "14:20", "open": 4149.0, "high": 4151.0, "low": 4148.5, "close": 4150.2, "vol": 1200, "delta": "+150 oz"},
                    {"time": "14:25", "open": 4150.2, "high": 4150.5, "low": 4146.0, "close": 4146.5, "vol": 1800, "delta": "-220 oz"},
                    {"time": "14:30", "open": 4146.5, "high": 4147.0, "low": 4144.0, "close": 4145.8, "vol": 2400, "delta": "+380 oz"}
                ]
            }
        },
        "order_flow_last_5m": {
            "cvd_delta": "+380.0 oz",
            "delta_trend": "ACCUMULATION_AT_LOW",
            "poc_price": 4144.50,
            "poc_volume": "620 oz",
            "footprint_imbalances": [
                {"price": 4144.50, "bid_vol": 12.0, "ask_vol": 145.0, "type": "STACKED_BUY_IMBALANCE_12X"},
                {"price": 4145.00, "bid_vol": 25.0, "ask_vol": 110.0, "type": "BUY_IMBALANCE_4.4X"}
            ],
            "absorption_signal": "Sellers attempted to push below 4144.0 but met 145 oz passive bid absorption. Price rejected upward.",
            "dom_liquidity_walls": {
                "overhead_resistance_wall": {"price": 4155.0, "size": "190 oz", "distance": "+$9.20"},
                "supporting_bid_wall": {"price": 4144.0, "size": "210 oz", "distance": "-$1.80"}
            },
            "orderbook_pressure": "68% Bid vs 32% Ask"
        }
    }
    
    print("\n⏳ Sending Order Flow Payload to Claude Sonnet 5...")
    decision = client.analyze_order_flow(sample_payload)
    
    print("\n==================================================")
    print("🎯 Claude Sonnet 5 Trade Decision Result:")
    print("==================================================")
    print(f"Action:       {decision.action}")
    print(f"Confidence:   {decision.confidence}%")
    print(f"Entry Price:  ${decision.entry_price:,.2f}")
    print(f"Stop Loss:    ${decision.sl_price:,.2f}")
    print(f"Take Profit:  ${decision.tp_price:,.2f}")
    print(f"Risk/Reward:  1:{decision.risk_reward}")
    print(f"Valid Signal: {'✅ YES' if decision.is_valid_signal(cfg.min_confidence_to_trade) else '❌ NO / HOLD'}")
    print(f"Reason:       {decision.reason}")
    print("==================================================\n")

if __name__ == "__main__":
    main()
