import json
import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from trailing_stop_engine import PositionState
from orderflow_aggregator import TickData

logger = logging.getLogger("MT5Bridge")

class MT5Bridge:
    """
    Unified MT5 Bridge supporting:
    1. Direct Mode: Python MetaTrader5 package (on Windows)
    2. Bridge Mode: Local HTTP REST server for MQL5 WebRequest EA (Linux, VPS, Mac, Termux)
    3. Simulation Mode: Paper-trading engine
    """
    def __init__(self, symbol: str = "XAUUSD", host: str = "0.0.0.0", port: int = 8020, simulation: bool = False):
        self.symbol = symbol
        self.host = host
        self.port = port
        self.simulation = simulation
        
        # State
        self.current_price: float = 0.0
        self.active_position: Optional[PositionState] = None
        self.pending_commands: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
        
        # Callbacks
        self.on_tick_callback = None
        self.on_bar_callback = None
        
        self.is_native_mt5 = False
        self._init_native_mt5()
        
        if not self.is_native_mt5 and not self.simulation:
            self._start_http_bridge_server()
        elif self.simulation:
            logger.info("🎮 MT5Bridge running in SIMULATION (Paper-Trading) mode.")

    def _init_native_mt5(self):
        try:
            import MetaTrader5 as mt5
            if mt5.initialize():
                self.is_native_mt5 = True
                logger.info(f"✅ Native Windows MetaTrader5 initialized successfully. Terminal version: {mt5.version()}")
            else:
                logger.info("ℹ️ Native MetaTrader5 initialize returned False. Falling back to HTTP EA Bridge Mode.")
        except ImportError:
            logger.info("ℹ️ MetaTrader5 python package not available on this platform. Running in Cross-Platform HTTP Bridge Mode.")
        except Exception as e:
            logger.info(f"ℹ️ Native MT5 initialization skipped ({e}). Running in Cross-Platform HTTP Bridge Mode.")

    def _start_http_bridge_server(self):
        bridge = self
        
        class BridgeHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Silence default HTTP logs

            def do_POST(self):
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len).decode("utf-8")
                
                if self.path == "/api/market_data":
                    try:
                        data = json.loads(body)
                        bridge._handle_market_data(data)
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(b'{"status":"ok"}')
                    except Exception as e:
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(f'{{"error":"{e}"}}'.encode())
                
                elif self.path == "/api/order_result":
                    try:
                        data = json.loads(body)
                        logger.info(f"📬 EA Order Execution Feedback: {data}")
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b'{"status":"received"}')
                    except Exception as e:
                        self.send_response(400)
                        self.end_headers()

            def do_GET(self):
                if self.path == "/api/pending_commands":
                    with bridge.lock:
                        cmds = list(bridge.pending_commands)
                        bridge.pending_commands.clear()
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(cmds).encode("utf-8"))
                
                elif self.path == "/api/status":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    status = {
                        "symbol": bridge.symbol,
                        "current_price": bridge.current_price,
                        "has_position": bridge.active_position is not None
                    }
                    self.wfile.write(json.dumps(status).encode("utf-8"))

        server = HTTPServer((self.host, self.port), BridgeHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        logger.info(f"🌐 MT5 HTTP EA Bridge Server listening at http://{self.host}:{self.port}")

    def _handle_market_data(self, data: Dict[str, Any]):
        with self.lock:
            # Update Current Price
            px = float(data.get("price", 0.0))
            if px > 0.0:
                self.current_price = px
                
            # Update Position State
            pos = data.get("position")
            if pos and pos.get("ticket"):
                self.active_position = PositionState(
                    ticket=int(pos["ticket"]),
                    symbol=pos.get("symbol", self.symbol),
                    order_type=pos.get("type", "BUY"),
                    volume=float(pos.get("volume", 0.05)),
                    open_price=float(pos.get("open_price", px)),
                    current_sl=float(pos.get("sl", 0.0)),
                    current_tp=float(pos.get("tp", 0.0)),
                    highest_price=float(pos.get("highest_price", px)),
                    lowest_price=float(pos.get("lowest_price", px))
                )
            else:
                self.active_position = None

        # Route tick to callback
        if self.on_tick_callback and px > 0.0:
            tick = TickData(
                time=float(data.get("time", time.time())),
                price=px,
                volume=float(data.get("volume", 1.0)),
                bid=float(data.get("bid", px)),
                ask=float(data.get("ask", px)),
                side=data.get("side", "Buy")
            )
            self.on_tick_callback(tick)

    def get_active_position(self) -> Optional[PositionState]:
        with self.lock:
            return self.active_position

    def send_order(self, action: str, lot: float, sl: float, tp: float, comment: str = "Claude-Sonnet-5") -> bool:
        """Sends open order command (BUY or SELL)"""
        cmd = {
            "action": "OPEN",
            "type": action,
            "symbol": self.symbol,
            "volume": lot,
            "sl": sl,
            "tp": tp,
            "comment": comment,
            "timestamp": time.time()
        }
        
        if self.simulation:
            with self.lock:
                sim_ticket = int(time.time())
                self.active_position = PositionState(
                    ticket=sim_ticket,
                    symbol=self.symbol,
                    order_type=action,
                    volume=lot,
                    open_price=self.current_price,
                    current_sl=sl,
                    current_tp=tp,
                    highest_price=self.current_price,
                    lowest_price=self.current_price
                )
            logger.info(f"🎮 [SIMULATION] Position OPENED: {action} {lot} lots @ {self.current_price} | SL: {sl} | TP: {tp}")
            return True

        with self.lock:
            self.pending_commands.append(cmd)
        logger.info(f"📤 Queued Order Command for MT5: {cmd}")
        return True

    def modify_sl(self, ticket: int, new_sl: float) -> bool:
        """Sends SL update command for Trailing Stop"""
        cmd = {
            "action": "MODIFY_SL",
            "ticket": ticket,
            "new_sl": new_sl,
            "timestamp": time.time()
        }
        
        if self.simulation:
            with self.lock:
                if self.active_position and self.active_position.ticket == ticket:
                    self.active_position.current_sl = new_sl
            logger.info(f"🎮 [SIMULATION] SL Modified for #{ticket} -> {new_sl}")
            return True

        with self.lock:
            self.pending_commands.append(cmd)
        logger.info(f"📤 Queued Trailing SL Modification for MT5: #{ticket} -> {new_sl}")
        return True

    def close_position(self, ticket: int) -> bool:
        """Sends Market Close command"""
        cmd = {
            "action": "CLOSE",
            "ticket": ticket,
            "timestamp": time.time()
        }
        
        if self.simulation:
            with self.lock:
                self.active_position = None
            logger.info(f"🎮 [SIMULATION] Position #{ticket} CLOSED")
            return True

        with self.lock:
            self.pending_commands.append(cmd)
        logger.info(f"📤 Queued Position Close Command for MT5: #{ticket}")
        return True
