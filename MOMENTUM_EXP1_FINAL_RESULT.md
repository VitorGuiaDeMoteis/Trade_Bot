# Momentum Experiment V1.3 — Final Result

Protocol seal: `9da3c686a51d450c22d45cdc463c8d5ffe16f5d25c28f31de734724512a7d16e`
Holdout opened: `2026-09-18T18:41:10.678269+00:00`

## Sealed manifest

```json
{
  "protocol_seal_hash": "9da3c686a51d450c22d45cdc463c8d5ffe16f5d25c28f31de734724512a7d16e",
  "manifest": {
    "protocol_version": "1.3",
    "base_git_sha": "da6a90f474f67c74554d10da7267a27fb51243b5",
    "source_tree_hash": "3368a25b21287af5b2ad3892095ea8499a7dcda44029ca4b8049fd701cd38964",
    "config_hash": "7f5e81c79c00cd45329e9aa35f23f803cc1b2cf7ce3a8e4e4325d828636acdd1",
    "primary_dataset_hash": "8f5b870b21a70bd9e81175e9a167f5dd07b4632cc88c0ada82fa41c1b986e003",
    "fred_hash": "61e0802c775b398b8ef2f57a12499766a33b3602d261404374329b8a00da996b",
    "crosscheck_hashes": {
      "alpaca": "8ce33f16cde3e1a6dfb0c39de0ee747b7ed1f0f0ed5952794b5a8058e5a1c374"
    },
    "substitution_dataset_hashes": {
      "yahoo": "f4f1972796a402ef33512946640475493edeff362bb586ab38182f93390bd191"
    },
    "strategy_definitions_hash": "2b481c8e87a54db210e720db9ad0ee8ebfb7d5aab294415ab601a201b8ed1783",
    "cost_model_hash": "124afd0cdecc13277342fc01179cb4bfe88dc197dac9ccc2d3cc71b62fd0a640",
    "lock_hash": "344c1dca63a9cca70d0ca7fd37811362a3666e7fe8df459eef51b26cd9219a36",
    "created_at": "2026-09-18T18:41:00.296428+00:00"
  }
}
```

## Holdout marker

```json
{
  "opened_at": "2026-09-18T18:41:10.678269+00:00",
  "status": "COMPLETED",
  "protocol_seal_hash": "9da3c686a51d450c22d45cdc463c8d5ffe16f5d25c28f31de734724512a7d16e",
  "source_tree_hash": "3368a25b21287af5b2ad3892095ea8499a7dcda44029ca4b8049fd701cd38964",
  "config_hash": "7f5e81c79c00cd45329e9aa35f23f803cc1b2cf7ce3a8e4e4325d828636acdd1",
  "dataset_hashes": {
    "primary": "8f5b870b21a70bd9e81175e9a167f5dd07b4632cc88c0ada82fa41c1b986e003",
    "fred": "61e0802c775b398b8ef2f57a12499766a33b3602d261404374329b8a00da996b",
    "crosscheck": {
      "alpaca": "8ce33f16cde3e1a6dfb0c39de0ee747b7ed1f0f0ed5952794b5a8058e5a1c374"
    },
    "substitutions": {
      "yahoo": "f4f1972796a402ef33512946640475493edeff362bb586ab38182f93390bd191"
    }
  },
  "base_git_sha": "da6a90f474f67c74554d10da7267a27fb51243b5"
}
```

## Holdout metrics

| Strategy | CAGR | Sharpe | Sortino | MaxDD | Calmar | Ann_Vol | Worst_12m | Annual_Turnover | Trades_Per_Year | Cash_Pct | Average_Positions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 0.032189 | ZERO_EXCESS_VOLATILITY | ZERO_DOWNSIDE_VOLATILITY | 0.000000 | ZERO_DRAWDOWN | 0.001910 | 0.000449 | 0.000000 | 0.000000 | 1.000000 | 0.000000 |
| B1 | 0.076116 | 0.377648 | 0.545853 | 0.206939 | 0.367819 | 0.112660 | -0.191189 | 0.494923 | 84.195939 | 0.000000 | 7.000000 |
| B2 | 0.049824 | 0.137417 | 0.197303 | 0.275551 | 0.180816 | 0.124263 | -0.256903 | 0.405571 | 24.055982 | 0.000000 | 2.000000 |
| AM | 0.059738 | 0.199430 | 0.264405 | 0.291411 | 0.204994 | 0.133828 | -0.201615 | 4.725317 | 52.121295 | 0.033466 | 4.003984 |
| RAM | 0.101298 | 0.569463 | 0.753619 | 0.217806 | 0.465083 | 0.117605 | -0.131656 | 3.569377 | 35.883507 | 0.139735 | 2.582470 |

## 95% block-bootstrap confidence intervals

| Strategy | CAGR | Annualized volatility | MaxDD |
|---|---:|---:|---:|
| B0 | [0.020078, 0.045034] | [0.002534, 0.006747] | [0.000000, 0.000000] |
| B1 | [-0.027309, 0.158518] | [0.083637, 0.143606] | [0.058512, 0.325093] |
| B2 | [-0.070330, 0.162850] | [0.106782, 0.164937] | [0.092619, 0.438213] |
| AM | [-0.059905, 0.166770] | [0.092465, 0.129139] | [0.077551, 0.386652] |
| RAM | [0.005865, 0.193842] | [0.085107, 0.122167] | [0.048376, 0.224054] |

## AM gates

- FAIL — Sharpe_AM > Sharpe_B1 + 0.15
- FAIL — MaxDD_AM < 0.70 * MaxDD_B1
- FAIL — Calmar_AM > Calmar_B1
- FAIL — Survives 10 bps round-trip
- FAIL — ETF substitutions structurally stable
- PASS — 10m/12m/14m has no isolated 12m peak
- FAIL — >=2 AM sensitivities support core conclusion
- FAIL — Sharpe >= 0.30
- FAIL — MaxDD <= 20%
- FAIL — No leave-one-out Sharpe reduction >50%

## RAM gates

- NOT_APPLICABLE — Sharpe_RAM > Sharpe_AM + 0.10
- NOT_APPLICABLE — MaxDD_RAM < 1.30 * MaxDD_AM
- NOT_APPLICABLE — K=3 robust vs K=2/K=4
- NOT_APPLICABLE — Extra turnover justified by extra Sharpe
- NOT_APPLICABLE — RAM MaxDD <=25%

## Final decision

MOMENTUM — NO EDGE

## $50 micro-capital replay

NOT APPLICABLE. The replay is authorized only when AM or RAM wins.

## Permanent research disposition

This strategy family is closed on this dataset: **MOMENTUM — NO EDGE**. Experiment 2 must use another strategy family. Do not continue with RSI momentum, volatility-scaled momentum, dynamic momentum thresholds, additional lookback fishing, or further K optimization on this dataset.

## Known limitations

- Yahoo adjusted history can be revised by the provider.
- Alpaca is a cross-check over its available overlap, not the primary source.
- DTB3 cash accrual uses the same canonical series for B0 and excess-return metrics.
- The engine models next-session-open execution and pre-registered friction, not intraday market impact.

Paper V1 and its running worktree were untouched. No broker orders were sent.
