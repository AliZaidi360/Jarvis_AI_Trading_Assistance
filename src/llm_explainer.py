import logging
import json
import hashlib
from datetime import datetime

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------------
# LOCKED SYSTEM PROMPT (DO NOT MODIFY)
# --------------------------------------------------------------------------------
LOCKED_SYSTEM_PROMPT = """
You are the Explanation Layer for the JARVIS Trading System.
Your role is purely descriptive. You convert JSON decision logs into human-readable text.

RULES:
1. You have NO access to future market data.
2. You CANNOT predict price movements.
3. You CANNOT recommend trades or overrides.
4. You CANNOT suggest changes to risk parameters.
5. You MUST act as a disinterested observer explaining "Why" a decision was made based ONLY on the provided metrics.

INPUT FORMAT:
A JSON object containing:
- type: TRADE_EXECUTED | TRADE_SKIPPED | RISK_LOCKED
- reason: Code string
- metrics: {spread, volatility, score, equity, ...}

OUTPUT FORMAT:
A concise, professional explanation (1-2 sentences).

EXAMPLES:
Input: {"type": "TRADE_SKIPPED", "reason": "SPREAD_TOO_HIGH", "metrics": {"spread": 0.002, "limit": 0.001}}
Output: "Trade skipped because the current spread (0.20%) exceeds the maximum allowed limit (0.10%)."

Input: {"type": "TRADE_EXECUTED", "reason": "ENTRY_LONG", "metrics": {"score": 0.8, "volatility": 0.01}}
Output: "Long position executed. Direction score (0.80) indicates strong upward momentum signal."

Input: {"type": "RISK_LOCKED", "reason": "DAILY_DRAWDOWN_LIMIT", "metrics": {"equity": 980, "start_equity": 1000}}
Output: "System locked to prevent further losses. Daily drawdown limit (-2.00%) has been breached."

DO NOT deviate from the provided metrics. Do not hallucinate external factors.
"""
# --------------------------------------------------------------------------------

class LLMExplainer:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.cache = {} # Simple in-memory cache: hash(json_log) -> explanation
        self.cache_size = 1000

    def generate_explanation(self, decision_log):
        """
        Generates a human-readable explanation for a decision log.
        Uses caching to avoid redundant calls for identical states (unlikely for float metrics, but good for similar discrete states).
        """
        # Create a stable signature for caching
        # Rounding floats helps cache hit rate
        signature = self._create_signature(decision_log)
        
        if signature in self.cache:
            return self.cache[signature]

        # In a real implementation, this would call OpenAI/Anthropic API
        # with self.api_key and LOCKED_SYSTEM_PROMPT.
        # For MVP, we simulate the LLM's role with a determinstic fallback 
        # (or call the API if key is present).
        
        explanation = self._call_llm(decision_log)
        
        # Update Cache
        if len(self.cache) > self.cache_size:
            self.cache.pop(next(iter(self.cache))) # FIFO-ish
        self.cache[signature] = explanation
        
        return explanation

    def _call_llm(self, log):
        """
        Simulate LLM call or make real one.
        """
        if self.api_key:
            # TODO: Implement actual API call here (e.g. requests.post to OpenAI)
            # return self._query_openai(log)
            pass
            
        # Fallback Deterministic "LLM" for MVP/No-Key mode
        # This proves the "Explanation Layer" concept without cost.
        t = log.get("type", "UNKNOWN")
        r = log.get("reason", "UNKNOWN")
        m = log.get("metrics", {})
        
        if t == "TRADE_SKIPPED":
            if r == "SPREAD_TOO_HIGH":
                return f"Trade skipped: Spread ({m.get('spread',0):.4f}) > Limit."
            if r == "WEAK_SIGNAL":
                return f"Trade skipped: Signal strength ({abs(m.get('score',0)):.2f}) is below threshold."
            if r == "RISK_CONSTRAINT":
                return "Trade skipped: General risk constraint violation."
                
        if t == "RISK_LOCKED":
             return f"CRITICAL: System locked due to {r}. Intervention required."
             
        if t == "TRADE_EXECUTED":
             return f"Executed {r}. Volatility: {m.get('volatility',0):.4f}."
             
        return f"Event: {t} | Reason: {r}"

    def _create_signature(self, log):
        # Round metrics to reduced precision to increase cache hits
        # e.g. spread 0.00101 vs 0.00102 might be "same" context for explanation purposes if we want caching.
        # But generally, just hash the dict.
        try:
            s_log = json.dumps(log, sort_keys=True)
            return hashlib.md5(s_log.encode()).hexdigest()
        except:
            return str(log)
