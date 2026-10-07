import requests
import json
import logging
import re
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger("ClaudeClient")

@dataclass
class TradeDecision:
    action: str            # "BUY", "SELL", "HOLD"
    confidence: int        # 0 - 100
    entry_price: float
    sl_price: float
    tp_price: float
    risk_reward: float
    reason: str
    raw_response: str = ""

    def is_valid_signal(self, min_confidence: int = 70) -> bool:
        if self.action not in ["BUY", "SELL"]:
            return False
        if self.confidence < min_confidence:
            return False
        if self.entry_price <= 0.0 or self.sl_price <= 0.0:
            return False
        # Sanity check SL distance
        if self.action == "BUY" and self.sl_price >= self.entry_price:
            return False
        if self.action == "SELL" and self.sl_price <= self.entry_price:
            return False
        return True


class ClaudeClient:
    """
    Dedicated Client for Claude Sonnet 5 via maxplus-ai OpenAI-compatible Endpoint.
    Specially tuned for Order Flow Footprint, DOM Liquidity, and Auction Market Theory.
    """
    def __init__(self, api_base: str, api_key: str, model: str = "claude-sonnet-5", timeout: int = 30):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

    def analyze_order_flow(self, market_data_payload: Dict[str, Any]) -> TradeDecision:
        """
        Sends the 50-candle M5 context + 5-minute deep Order Flow microstructure
        to Claude Sonnet 5 and returns a structured TradeDecision.
        """
        system_prompt = (
            "You are a Senior Institutional Order Flow & Auction Market Trader specializing in Gold (XAUUSD).\n"
            "Your methodology is based on Volume Profile, Footprint Stacked Imbalances, Cumulative Volume Delta (CVD) Divergences, "
            "Absorption at Key Levels, and Liquidity Voids.\n\n"
            "Trading Rules:\n"
            "1. ABSORPTION REVERSAL: High delta at extreme highs/lows with no price advance -> Strong Reversal signal.\n"
            "2. MOMENTUM CONTINUATION: Aggressive delta breakout with stacked imbalances and thin overhead liquidity -> Follow trend.\n"
            "3. TRAPPED TRADERS: Failed auction outside Value Area with trapped volume -> Target opposite liquidity pool.\n"
            "4. NO EDGE / BALANCE: If market is consolidating with mixed delta -> Output 'HOLD'. DO NOT OVERTRADE.\n"
            "5. RISK/REWARD: Target minimum 1:1.5 R:R. Place Stop Loss beyond absorption wick or major resting liquidity wall.\n\n"
            "CRITICAL: Output strictly pure JSON matching this exact schema:\n"
            "{\n"
            '  "action": "BUY" | "SELL" | "HOLD",\n'
            '  "confidence": <integer 0-100>,\n'
            '  "entry_price": <float>,\n'
            '  "sl_price": <float>,\n'
            '  "tp_price": <float>,\n'
            '  "risk_reward": <float>,\n'
            '  "reason": "<clear institutional orderflow rationale>"\n'
            "}"
        )

        user_content = json.dumps(market_data_payload, indent=2, ensure_ascii=False)
        user_message = f"Market State & Order Flow Snapshot:\n```json\n{user_content}\n```\nWhat is your trading decision?"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.15,
            "max_tokens": 400
        }

        url = f"{self.api_base}/chat/completions"

        for attempt in range(1, 4):
            try:
                logger.info(f"🚀 Sending order flow analysis to {self.model} (Attempt {attempt}/3)...")
                response = self.session.post(url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                
                resp_data = response.json()
                raw_text = resp_data["choices"][0]["message"]["content"]
                logger.info(f"✅ Received response from {self.model}")
                return self._parse_response(raw_text)

            except Exception as e:
                logger.warning(f"⚠️ Error calling Claude API (Attempt {attempt}): {e}")
                if attempt == 3:
                    logger.error(f"❌ Failed all 3 attempts to call {self.model}.")
                    return TradeDecision(
                        action="HOLD",
                        confidence=0,
                        entry_price=0.0,
                        sl_price=0.0,
                        tp_price=0.0,
                        risk_reward=0.0,
                        reason=f"API Connection Failure: {e}",
                        raw_response=""
                    )

        return TradeDecision(
            action="HOLD",
            confidence=0,
            entry_price=0.0,
            sl_price=0.0,
            tp_price=0.0,
            risk_reward=0.0,
            reason="Unknown error",
            raw_response=""
        )

    def _parse_response(self, text: str) -> TradeDecision:
        cleaned = text.strip()
        # Remove markdown code fences if present
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        
        try:
            data = json.loads(cleaned)
            action = str(data.get("action", "HOLD")).strip().upper()
            confidence = int(data.get("confidence", 0))
            entry_price = float(data.get("entry_price", 0.0))
            sl_price = float(data.get("sl_price", 0.0))
            tp_price = float(data.get("tp_price", 0.0))
            rr = float(data.get("risk_reward", 0.0))
            reason = str(data.get("reason", ""))

            # Calculate R:R if not given or zero
            if rr == 0.0 and entry_price > 0.0 and sl_price > 0.0 and tp_price > 0.0:
                risk = abs(entry_price - sl_price)
                reward = abs(tp_price - entry_price)
                if risk > 0.0:
                    rr = round(reward / risk, 2)

            return TradeDecision(
                action=action,
                confidence=confidence,
                entry_price=entry_price,
                sl_price=sl_price,
                tp_price=tp_price,
                risk_reward=rr,
                reason=reason,
                raw_response=text
            )
        except Exception as err:
            logger.error(f"❌ Failed to parse JSON from Claude response: {err}\nRaw text: {text}")
            return TradeDecision(
                action="HOLD",
                confidence=0,
                entry_price=0.0,
                sl_price=0.0,
                tp_price=0.0,
                risk_reward=0.0,
                reason=f"JSON Parse Error: {err}",
                raw_response=text
            )
