# 🤖 Claude Sonnet 5 + Institutional Order Flow MT5 Trading Bot

High-performance AI trading bot integrating **Claude 3.5 / Sonnet 5** with **Institutional Order Flow Microstructure (Footprint, CVD, POC, Stacked Imbalances, DOM Liquidity)** for **MetaTrader 5 (MT5)**, specifically optimized for **Gold (XAUUSD)**.

---

## ⚡ Core Philosophy & Architecture

1. **High-Alpha Order Flow Analysis (Every 5 Minutes):**
   * Aggregates real-time tick and depth data every 1–5 seconds into Footprint bars, Point of Control (POC), Stacked Imbalances, and Cumulative Volume Delta (CVD) minute-by-minute slices.
   * Every 5 minutes (at M5 bar close), if the portfolio is **FLAT (No Open Position)**, sends the uncompromised 50-candle macro structure and 5-minute deep Order Flow payload to **Claude Sonnet 5** via `https://api.maxplus-ai.cc`.
   * Claude evaluates institutional absorption, trapped traders, and liquidity voids, returning structured decisions: `BUY`, `SELL`, or `HOLD` with precise SL, TP, and R:R.

2. **Zero-Token Local Rule-Based Trailing Stop (Every 1 Second):**
   * Once an order is entered, **Claude Sonnet 5 is NOT called** while the position is active!
   * The local engine monitors the position every second in milliseconds, managing Breakeven triggers, trailing steps, and profit locking with **0 API cost** and **zero network latency**.

```mermaid
flowchart TD
    subgraph MarketStream [1. Market Data Stream (1-5s)]
        MT5[MetaTrader 5 Terminal] -->|WebRequest / DLL| Bridge[MT5Bridge (Port 8020)]
        Bridge --> Aggregator[OrderFlowAggregator]
        Aggregator --> Footprint[Compute Footprint, POC, CVD & Slices]
    end

    subgraph DecisionEngine [2. Decision & Position Evaluator]
        Footprint --> CheckPos{Have Open Position?}
        CheckPos -- "YES (Holding)" --> Trailing[Rule-Based Trailing Stop Engine (1s)]
        Trailing -->|Modify SL / Breakeven| Bridge
        
        CheckPos -- "NO (Flat)" --> TimeCheck{5-Minute Bar Close?}
        TimeCheck -- Yes --> Payload[Compile 50 M5 Bars + 5m Flow Payload]
        Payload --> Claude[Claude Sonnet 5 Engine]
        Claude --> Decision{Signal Decision}
        Decision -- "HOLD" --> Wait[Wait for Next 5m Bar]
        Decision -- "BUY / SELL" --> Order[Send Order + Initial SL/TP to MT5]
        Order --> Trailing
    end
```

---

## 📂 Project Structure

```text
claude-orderflow-mt5/
├── bot.py                     # Main bot orchestrator (M5 LLM cycle + 1s Trailing cycle)
├── claude_client.py           # Claude Sonnet 5 client with institutional prompt & JSON parser
├── orderflow_aggregator.py    # Order Flow & Footprint processor (POC, CVD, Imbalances)
├── trailing_stop_engine.py    # Local Rule-based trailing stop & breakeven engine
├── mt5_bridge.py              # Cross-platform MT5 Bridge (REST / Native / Simulation)
├── ClaudeOrderFlowBridge.mq5  # MQL5 Expert Advisor for MetaTrader 5
├── config.py                  # Dataclass config manager
├── config.json                # User settings (API keys, symbol, risk, trailing points)
├── test_claude.py             # Standalone test script for Claude Sonnet 5
├── requirements.txt           # Python dependencies
└── README.md                  # Documentation
```

---

## 🚀 Quick Start Guide

### 1. Requirements & Installation

```bash
cd claude-orderflow-mt5
pip install -r requirements.txt
```

### 2. Verify Claude Sonnet 5 Connection

Run the standalone verification script to test communication with Claude Sonnet 5:
```bash
python test_claude.py
```
Expected output:
```text
✅ Received response from claude-sonnet-5
Action:       BUY (or SELL / HOLD)
Confidence:   85%
Risk/Reward:  1:4.0
Reason:       ABSORPTION REVERSAL at 4144.0 low...
```

### 3. Setup in MetaTrader 5 (MT5)

1. Open MetaTrader 5 Terminal.
2. In MT5, go to **Tools -> Options -> Expert Advisors**:
   * Check **Allow WebRequest for listed URL**
   * Add URL: `http://127.0.0.1:8020`
3. Copy `ClaudeOrderFlowBridge.mq5` into your MT5 `MQL5/Experts/` folder.
4. Compile the EA in MetaEditor (F7).
5. Attach `ClaudeOrderFlowBridge` to your **XAUUSD (M5)** chart and enable **Algo Trading**.

### 4. Run the Bot

```bash
python bot.py
```

---

## ⚙️ Configuration (`config.json`)

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `llm_model` | `claude-sonnet-5` | Target Claude Model |
| `symbol` | `XAUUSD` | Trading Asset |
| `timeframe` | `M5` | Bar cycle (5 minutes) |
| `default_lot` | `0.05` | Position volume |
| `breakeven_trigger_points` | `150.0` | Move to BE after $1.50 profit on Gold |
| `breakeven_buffer_points` | `20.0` | Buffer above entry ($0.20 on Gold) |
| `trailing_distance_points` | `200.0` | Trailing distance ($2.00 on Gold) |
| `trailing_step_points` | `50.0` | Step update ($0.50 on Gold) |
| `simulation_mode` | `false` | Set `true` to paper trade without MT5 |

---

## 🇹🇭 สรุปการทำงานภาษาไทย

* **เมื่อพอร์ตว่าง (ไม่มีออเดอร์):** ทุกๆ 5 นาที ระบบจะรวบรวมข้อมูลแท่งเทียน 50 แท่ง พร้อม Order Flow Footprint (POC, Delta นาทีต่อนาที, Stacked Imbalances, แนวรับต้าน DOM) ส่งให้ **Claude Sonnet 5** วิเคราะห์แบบเจาะลึก เพื่อหาจังหวะ Absorption และ Momentum ที่มีความได้เปรียบสูง
* **เมื่อมีออเดอร์แล้ว:** ระบบจะ**ไม่เรียก LLM** ให้เปลืองค่าใช้จ่าย แต่จะส่งต่อให้ **Local Trailing Stop Engine** เฝ้าราคาทุกๆ 1 วินาที ทำหน้าที่ล็อกกำไร, ขยับ Breakeven และ Trailing Stop ด้วยความเร็วระดับมิลลิวินาที

---

## 📄 License
MIT License. Created for institutional & quantitative trading research.
