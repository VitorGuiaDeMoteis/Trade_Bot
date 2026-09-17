# M8 Research Conclusion: ML/AI Predictive Model

**Status**: NO EDGE — ABANDON ML SIGNAL V1

## Summary
The M8 research branch aimed to introduce predictive capabilities using LLMs and classic ML models over deterministic features. The results were conclusively negative under operational economic constraints.

1. **qwen3:4b**: LOW_INFORMATION (Severe mode collapse to TRENDING/BULLISH).
2. **qwen2.5-coder:7b**: LOW_INFORMATION (Severe mode collapse to TRENDING, high latency).
3. **HistGradientBoosting**: Overfit on DEV (99% win rate). On VALIDATION, it could not sustain a positive edge over trading costs (0.15% round-trip), resulting in negative net expectancy (-0.0287%) and a catastrophic drawdown (-225%).
4. **BLIND TEST**: Kept untouched (0% exposure).

## Action Taken
ML and LLM components were isolated to standalone scripts (`scripts/m87_*.py`) and have been completely removed/excluded from the operational trading critical path. The system reverts to pure deterministic rules for PAPER V1.
