//+------------------------------------------------------------------+
//|                                     ClaudeOrderFlowBridge.mq5     |
//|                        Copyright 2026, Claude Order Flow Trading |
//|                                             https://maxplus-ai.cc|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Claude Order Flow Trading"
#property link      "https://maxplus-ai.cc"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//--- Input Parameters
input group "=== Server Connection Settings ==="
input string   InpServerURL      = "http://127.0.0.1:8020"; // Python Bridge Server URL
input int      InpPollIntervalMs = 1000;                     // Sync Interval (ms)

input group "=== Trading Settings ==="
input ulong    InpMagicNumber    = 888999;                   // EA Magic Number
input ulong    InpSlippage       = 30;                       // Max Slippage (points)
input double   InpDefaultLot     = 0.05;                     // Default Lot Size

//--- Global Variables
CTrade         trade;
datetime       last_poll_time    = 0;
string         active_symbol     = "";

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   active_symbol = _Symbol;
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippage);
   
   Print("🚀 [ClaudeOrderFlowBridge] Initializing Expert Advisor on ", active_symbol);
   Print("⚠️ [ClaudeOrderFlowBridge] IMPORTANT: Ensure '", InpServerURL, "' is added to Allowed WebRequest URLs in Tools -> Options -> Expert Advisors.");
   
   EventSetMillisecondTimer(InpPollIntervalMs);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("🚪 [ClaudeOrderFlowBridge] Expert Advisor Stopped.");
}

//+------------------------------------------------------------------+
//| Timer event function                                             |
//+------------------------------------------------------------------+
void OnTimer()
{
   SyncWithPythonBridge();
}

//+------------------------------------------------------------------+
//| Tick event function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
   // Ticks are synced smoothly in OnTimer to avoid network congestion
}

//+------------------------------------------------------------------+
//| Sync market data and process pending commands                    |
//+------------------------------------------------------------------+
void SyncWithPythonBridge()
{
   MqlTick tick;
   if(!SymbolInfoTick(active_symbol, tick)) return;
   
   // 1. Gather active position details
   string pos_json = "null";
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionGetString(POSITION_SYMBOL) == active_symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
      {
         long pos_type = PositionGetInteger(POSITION_TYPE);
         string type_str = (pos_type == POSITION_TYPE_BUY) ? "BUY" : "SELL";
         double open_px  = PositionGetDouble(POSITION_PRICE_OPEN);
         double sl_px    = PositionGetDouble(POSITION_SL);
         double tp_px    = PositionGetDouble(POSITION_TP);
         double vol      = PositionGetDouble(POSITION_VOLUME);
         
         pos_json = StringFormat(
            "{\"ticket\":%I64u,\"symbol\":\"%s\",\"type\":\"%s\",\"open_price\":%.2f,\"sl\":%.2f,\"tp\":%.2f,\"volume\":%.2f}",
            ticket, active_symbol, type_str, open_px, sl_px, tp_px, vol
         );
         break;
      }
   }
   
   // 2. Build market data payload
   string side = (tick.last >= tick.ask) ? "Buy" : "Sell";
   string payload = StringFormat(
      "{\"symbol\":\"%s\",\"time\":%d,\"price\":%.2f,\"bid\":%.2f,\"ask\":%.2f,\"volume\":%.2f,\"side\":\"%s\",\"position\":%s}",
      active_symbol, (int)tick.time, tick.last > 0 ? tick.last : tick.bid, tick.bid, tick.ask, (double)tick.volume_real, side, pos_json
   );
   
   // 3. Send market data to Python bridge
   char post_data[], result[];
   string result_headers;
   StringToCharArray(payload, post_data, 0, WHOLE_ARRAY, CP_UTF8);
   
   string url_market = InpServerURL + "/api/market_data";
   string headers = "Content-Type: application/json\r\n";
   
   ResetLastError();
   int res = WebRequest("POST", url_market, headers, 2000, post_data, result, result_headers);
   if(res != 200)
   {
      // WebRequest failed or server not yet reachable
      return;
   }
   
   // 4. Poll pending commands from Python bridge
   string url_cmds = InpServerURL + "/api/pending_commands";
   char empty_post[];
   ResetLastError();
   res = WebRequest("GET", url_cmds, headers, 2000, empty_post, result, result_headers);
   if(res == 200 && ArraySize(result) > 2)
   {
      string resp_str = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
      ProcessCommands(resp_str);
   }
}

//+------------------------------------------------------------------+
//| Simple Command Parser for Python Commands                        |
//+------------------------------------------------------------------+
void ProcessCommands(string json_str)
{
   if(StringFind(json_str, "[]") >= 0) return; // No commands
   
   Print("📥 [ClaudeOrderFlowBridge] Received commands from Python: ", json_str);
   
   // Check for OPEN action
   if(StringFind(json_str, "\"action\": \"OPEN\"") >= 0 || StringFind(json_str, "\"action\":\"OPEN\"") >= 0)
   {
      bool is_buy = (StringFind(json_str, "\"BUY\"") >= 0);
      double sl = ExtractDouble(json_str, "\"sl\":");
      double tp = ExtractDouble(json_str, "\"tp\":");
      double vol = ExtractDouble(json_str, "\"volume\":");
      if(vol <= 0.0) vol = InpDefaultLot;
      
      MqlTick tick;
      SymbolInfoTick(active_symbol, tick);
      
      if(is_buy)
      {
         PrintFormat("⚡ [EXECUTE BUY] Lot: %.2f | Ask: %.2f | SL: %.2f | TP: %.2f", vol, tick.ask, sl, tp);
         trade.Buy(vol, active_symbol, tick.ask, sl, tp, "Claude Sonnet 5 Buy");
      }
      else
      {
         PrintFormat("⚡ [EXECUTE SELL] Lot: %.2f | Bid: %.2f | SL: %.2f | TP: %.2f", vol, tick.bid, sl, tp);
         trade.Sell(vol, active_symbol, tick.bid, sl, tp, "Claude Sonnet 5 Sell");
      }
   }
   
   // Check for MODIFY_SL action (Trailing Stop)
   if(StringFind(json_str, "MODIFY_SL") >= 0)
   {
      double new_sl = ExtractDouble(json_str, "\"new_sl\":");
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(PositionGetString(POSITION_SYMBOL) == active_symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
         {
            double cur_tp = PositionGetDouble(POSITION_TP);
            PrintFormat("🛡️ [TRAILING STOP UPDATE] Position #%I64u New SL -> %.2f", ticket, new_sl);
            trade.PositionModify(ticket, new_sl, cur_tp);
            break;
         }
      }
   }
   
   // Check for CLOSE action
   if(StringFind(json_str, "\"action\": \"CLOSE\"") >= 0 || StringFind(json_str, "\"action\":\"CLOSE\"") >= 0)
   {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(PositionGetString(POSITION_SYMBOL) == active_symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
         {
            PrintFormat("🚪 [CLOSE POSITION] Closing #%I64u", ticket);
            trade.PositionClose(ticket);
            break;
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Helper: Extract double value by key from JSON string             |
//+------------------------------------------------------------------+
double ExtractDouble(string json, string key)
{
   int pos = StringFind(json, key);
   if(pos < 0) return 0.0;
   
   int start = pos + StringLen(key);
   while(start < StringLen(json) && (StringGetCharacter(json, start) == ' ' || StringGetCharacter(json, start) == ':'))
      start++;
      
   int end = start;
   while(end < StringLen(json))
   {
      ushort ch = StringGetCharacter(json, end);
      if((ch >= '0' && ch <= '9') || ch == '.' || ch == '-')
         end++;
      else
         break;
   }
   
   string val_str = StringSubstr(json, start, end - start);
   return StringToDouble(val_str);
}
