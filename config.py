import os
import json
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class BotConfig:
    # API Configuration
    llm_api_base: str = "https://api.maxplus-ai.cc/v1"
    llm_api_key: str = "ccsk-32ae475c158bf286a8880a25cc1c68f9c556d1e123eca3a1af549ef258d92220"
    llm_model: str = "claude-sonnet-5"
    llm_timeout: int = 30
    
    # Trading Configuration
    symbol: str = "XAUUSD"
    timeframe: str = "M5"
    candle_history_bars: int = 50
    default_lot: float = 0.05
    max_slippage_points: int = 20
    magic_number: int = 888999
    
    # Order Flow & Footprint Settings
    tick_snapshot_interval_sec: float = 2.0  # 1 to 5 seconds
    imbalance_ratio_threshold: float = 3.0    # 300% volume imbalance
    min_confidence_to_trade: int = 70         # Minimum LLM confidence (0-100)
    
    # Local Trailing Stop Settings (Rule-Based Exit)
    trailing_enabled: bool = True
    trailing_type: str = "step"               # "step" | "atr" | "breakeven_only"
    breakeven_trigger_points: float = 150.0   # Move to BE when in profit by 150 points ($1.5 on Gold)
    breakeven_buffer_points: float = 20.0     # Buffer above entry price ($0.2)
    trailing_distance_points: float = 200.0   # Trailing distance ($2.0 on Gold)
    trailing_step_points: float = 50.0        # Step increment ($0.5 on Gold)
    
    # Bridge & Server Settings
    bridge_port: int = 8020
    bridge_host: str = "0.0.0.0"
    simulation_mode: bool = False             # Set True to paper-trade without live MT5

    @classmethod
    def load(cls, config_path: str = "config.json") -> "BotConfig":
        cfg = cls()
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if hasattr(cfg, k):
                            setattr(cfg, k, v)
            except Exception as e:
                print(f"⚠️ Failed to load {config_path}: {e}, using default config")
                
        # Override with environment variables if present
        cfg.llm_api_base = os.getenv("LLM_API_BASE", cfg.llm_api_base)
        cfg.llm_api_key = os.getenv("LLM_API_KEY", cfg.llm_api_key)
        cfg.llm_model = os.getenv("LLM_MODEL", cfg.llm_model)
        cfg.symbol = os.getenv("SYMBOL", cfg.symbol)
        
        return cfg

    def save(self, config_path: str = "config.json"):
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=4, ensure_ascii=False)
