# NAE Model A — Review & Improvement Plan

> **Scope:** this document covers improvements for the *public-sale* NAE
> Model A distribution. Every suggestion is constrained by the product
> boundaries declared in `README.md`, `nae/core/feature_gates.py`, and
> `legal/RISK_DISCLOSURE.md`:
>
> - **Research-only by default** — execution is off unless the end user
>   explicitly opts in via `config.yaml`.
> - **No trade recommendations, no signals, no "best strategy" rankings.**
> - **The user writes their own strategies**; NAE only computes,
>   backtests, and reports.
> - **No personal alpha or proprietary algorithms** ship in this repo.
>
> None of the items below violate those commitments. Anything that *would*
> violate them is listed explicitly under **Non-Goals** at the bottom.

---

## 1. Bugs fixed in this pass

| # | File | Severity | Bug | Fix |
|---|---|---|---|---|
| 1 | `nae/core/feature_gates.py` | **High** (state leak / latent compliance risk) | `FeatureGates.__init__` did `dict(_DEFAULT_CONFIG)` — a shallow copy. Because `_deep_merge` recurses into shared nested dicts, loading *any* config file (even once) permanently mutated the module-level `_DEFAULT_CONFIG`. A subsequently-constructed `FeatureGates(config_path=None)` would then inherit the previous run's settings — including `execution_enabled=True`. This was masked by the `get_gates()` singleton in normal usage but surfaced immediately under pytest (the `test_default_mode_is_research_only` test was failing on a fresh clone). | Use `copy.deepcopy(_DEFAULT_CONFIG)` so defaults are truly immutable across instances. The `.config` property also now returns a deep copy so callers cannot mutate internal state. |
| 2 | `tests/test_feature_gates.py` | **High** (missing regression coverage for the above) | No test asserted that loading a config into one gate could not leak into another. | Added `test_defaults_are_not_mutated_across_instances` and `test_config_property_returns_isolated_copy`. |
| 3 | `nae/tools/backtesting/engine.py` | **Medium** (misleading metric) | Sortino ratio fallback used `downside_std = 0.0001` when there were fewer than two negative daily returns, producing astronomically inflated Sortino values that could mislead users evaluating a strategy. | When there is no meaningful downside distribution, report `sortino_ratio = 0.0` instead of fabricating a denominator. |
| 4 | `nae/agents/strategy_validator.py` | **Medium** (crash on malformed strategy files) | Both `validate_strategy` and `run_backtest` called `spec.loader.exec_module(module)` without checking that `spec` / `spec.loader` were non-`None`. For unusual paths (e.g. symlinks, non-`.py` suffix that slipped through, bytecode-only files) this raises an uninformative `AttributeError` instead of the intended `StrategyValidationError`. | Guard both call sites and raise `StrategyValidationError` with a clear message. Also chain the re-raise with `from e` (PEP 3134 exception context). |
| 5 | `nae/tools/backtesting/engine.py`, `nae/agents/research_engine.py` | **Low** (style) | `raise ImportError(...)` inside `except ImportError:` did not preserve the original exception (`B904`). | Re-raise with `raise ... from e`. |
| 6 | `tests/test_backtest_engine.py` | **New** (no coverage) | The backtest engine — the single most important user-facing component — had zero automated tests. | Added three smoke tests using a stubbed `_fetch_data` so they run without yfinance/network. |

**Verification:** `python -m pytest tests -q` → 9/9 passed. `ruff check` → zero
issues on `E9/F7/F8/F82x/B006/B008/B904/E722/PLE`. `python
scripts/compliance_audit.py` → 18/18 passed.

---

## 2. High-value improvements (compliant with public-sale plan)

These are prioritised by impact-per-unit-effort. All of them *keep* the
product in research-only mode.

### 2.1 Reproducibility & UX — Quick wins (hours)

- **Deterministic report timestamps.**  
  `research_engine.generate_report` uses
  `datetime.date.today().isoformat()` for the file name. Across time
  zones and DST boundaries this produces the same report saved under two
  different dates. Switch to
  `datetime.datetime.now(datetime.timezone.utc).date().isoformat()`
  everywhere and add a `--as-of` CLI flag so customers can regenerate
  deterministic historical reports.

- **First-run wizard.**  
  `nae/__main__.py` currently drops straight into the CLI. Add a
  `nae init` command that:  
  1. Prints `FIRST_RUN_NOTICE` and requires `yes` confirmation.  
  2. Writes a sane `config.yaml` from `config.example.yaml`.  
  3. Creates `./strategies/`, `./reports/`, `./logs/`.  
  4. Emits a "you are in research-only mode; execution is disabled" banner.  
  This is the single biggest UX win for a public release.

- **`--deterministic` flag on backtests and research reports.**  
  Honour `NAE_DETERMINISTIC=1` (or a CLI flag) to fix all time-dependent
  output (report filenames, `generated_at`, any sort orders) so that two
  runs against the same data produce byte-identical artifacts. This is
  invaluable for customers who want to diff reports between runs.

- **Progress indicators.**  
  `ResearchEngine.scan_multiple` and `SimpleBacktestEngine.run` silently
  iterate through symbols. For >5 symbols, users assume the tool has
  hung. Wrap these loops in `tqdm` (already a lightweight dependency)
  behind a `--quiet` opt-out.

- **Clearer CLI error messages.**  
  Today every uncaught exception becomes a raw traceback. Wrap
  `nae/cli/main.py` command handlers in a single top-level try/except
  that formats known exceptions (`PermissionError`,
  `StrategyValidationError`, `ImportError`) into friendly messages and
  hides tracebacks unless `--debug` is passed.

### 2.2 Performance & timing — Quick wins (days)

- **Vectorise `SimpleBacktestEngine._build_bar`.**  
  It currently recomputes SMAs and RSI from scratch on every bar
  (`statistics.mean(closes[-20:])` etc.) inside an O(bars) outer loop →
  O(bars²) total work. For a 2-year daily backtest on ten symbols that
  is ~5 million redundant multiplications. Switch to rolling/pandas-
  based indicators once and index into them by bar. **Expected speedup:
  5–20× on the hot path.** This is a pure refactor, fully compatible
  with the user's `should_enter(data)` / `should_exit(data)` contract.

- **Cache `yfinance` downloads on disk.**  
  `ResearchEngine.fetch_market_data` re-downloads every time. Add a
  local parquet/CSV cache keyed by `(symbol, period, interval, date)`
  with a 24h freshness window. Customers running overnight scans
  repeatedly are currently rate-limited by Yahoo, not by NAE.

- **Parallelise multi-symbol scans.**  
  `ResearchEngine.scan_multiple` and the multi-symbol branch of
  `SimpleBacktestEngine.run` are embarrassingly parallel. A
  `ThreadPoolExecutor(max_workers=8)` (yfinance + metric compute is
  I/O-bound) would give a near-linear speedup for any scan over 4+
  symbols.

- **Avoid re-parsing the same module twice.**  
  `StrategyValidator.run_backtest` calls `validate_strategy` (which
  imports the strategy file) and then imports the same file again. Pass
  the already-loaded module through or memoise by `(path, mtime)`.

### 2.3 Analytical value — Medium effort (weeks)

All of these add *computed statistics* that help users interpret raw
backtest output. None of them rank strategies or produce recommendations.

- **Benchmark comparison.**  
  Given a user's backtest, fetch SPY (or a user-specified benchmark) for
  the same date range and surface:
  - Excess return vs benchmark
  - Beta, alpha (both purely descriptive)
  - Information ratio
  - Rolling 63-day correlation
  These are mathematical facts, not recommendations — same framing as
  the existing `max_drawdown_pct`.

- **Trade distribution statistics.**  
  Add to `BacktestResult`:
  - P95 / P5 trade return
  - Median holding period
  - Longest winning / losing streak
  - Profit factor (sum of wins / abs(sum of losses))
  - Kelly fraction (labelled clearly as an information-theoretic quantity, **not** a sizing recommendation).

- **Walk-forward analysis harness.**  
  Let the user slice their backtest window into N folds and get
  per-fold metrics to detect overfitting. Crucial for honest strategy
  evaluation and very aligned with the "no recommendation" ethos — it
  *reveals* when a strategy is brittle; the user decides what to do.

- **Regime detection expansion.**  
  `nae/tools/analysis/regime_detection.py` exists but is skeletal.
  Add:
  - Realised volatility buckets (low/mid/high with user-defined
    thresholds)
  - Correlation-to-SPY buckets
  - Trend regimes via SMA(50)/SMA(200) relation  
  Report results as *labels with numeric thresholds*, never as
  "favourable" or "unfavourable".

- **Monte Carlo bootstrap.**  
  Resample the trade-return distribution 1,000× to produce a confidence
  interval on total return and max drawdown. Present as
  "5th/50th/95th percentile outcomes under resampling", again purely
  descriptive.

### 2.4 Data & integrations — Medium effort

- **Second free data source.**  
  Yahoo Finance via yfinance is fragile. Add Stooq (free, no API key)
  as a fallback so the product still functions when yfinance breaks.

- **First-class CSV import pipeline.**  
  The `import_csv` method works but is undocumented in the README.
  Promote it to a CLI command (`nae import-csv --symbol SPY --file
  ./spy.csv`) and validate schema early with clear errors.

- **Optional broker adapters are sandbox-only.**  
  `nae/agents/execution_adapter.py` exists so users can hook their own
  broker. Ship concrete adapters **only for paper/sandbox endpoints**
  (Alpaca paper, Tradier sandbox) with live endpoints gated behind a
  separate opt-in flag. This keeps the product useful for end-to-end
  workflow testing while preserving the research-only default.

### 2.5 Packaging & distribution — Medium effort

- **Ship as a `pip install nae-platform` wheel.**  
  `pyproject.toml` is in place. Add a GitHub Actions workflow that
  builds the wheel, runs the full test suite + compliance audit on
  Python 3.10/3.11/3.12 on Linux/macOS/Windows, and publishes tagged
  releases to PyPI.

- **Signed releases.**  
  Sign release wheels with Sigstore so customers can verify they're
  running an official build. This is a legitimate compliance
  differentiator for a product sold into the retail-trader space.

- **Pre-built Docker image.**  
  `Dockerfile` exists but isn't published. Publish
  `ghcr.io/cbjones84/nae-model-a:<version>` on release tags; the
  `docker-compose.yml` already wires it up.

- **Offline-capable Docker image.**  
  A variant image that embeds `ta-lib`, `yfinance`, and CA bundles so
  Model A can run in air-gapped research environments (a real use case
  for institutional buyers who don't want their research flows hitting
  the public internet).

### 2.6 Compliance, reliability, security — Always-on

- **Run `compliance_audit.py` in CI on every PR.**  
  It's great that it exists; make it a required check.

- **Add an `execution_denied_total` counter to the CLI.**  
  Every time `FeatureGates.require_execution` raises, increment a
  counter persisted to `./logs/gate_denials.jsonl`. Gives the user (and
  you, if they ever open a support ticket) auditable proof that the
  software refused to execute.

- **Structured JSON logs.**  
  Today logging is human-readable. Add `--log-format json` so enterprise
  customers can ship logs into Splunk/Datadog.

- **Type-check in CI.**  
  Add `mypy --strict nae/` (or `pyright`) to the GitHub Actions
  workflow. The codebase is small enough that `--strict` is realistic,
  and it will catch a whole class of bugs before users do.

- **Dependency pinning & Dependabot.**  
  `requirements.txt` / `pyproject.toml` should have upper bounds.
  Enable Dependabot on the repo to get weekly PRs for security updates.

- **Secret-scanning pre-commit.**  
  Add a pre-commit hook that rejects any commit containing something
  that looks like an API key. For a product marketed to retail traders
  this is table stakes.

---

## 3. Non-goals (explicitly excluded to protect the product boundary)

The following are **out of scope** for NAE Model A, even though they'd
be technically feasible, because they'd break the public-sale plan:

- ❌ Ship any pre-trained model (`.pt`, `.pkl`, `.onnx`, etc.) — the
  `compliance_audit.py` check #2 is there for a reason.
- ❌ Ship any "signal generator", scored indicator, or strategy ranker.
- ❌ Rank strategies by "best" or "recommended" anywhere in the UI or
  report output.
- ❌ Auto-route validated strategies to execution.
- ❌ Ship *any* of the base-NAE proprietary algorithms
  (`profit_algorithms/*`, `iv_surface_model`, RL trader, etc.).  
  Model A's `ResearchEngine` is deliberately a thin shell.
- ❌ Default to live-trading broker endpoints, even if the user has
  opted into `execution_enabled: true`. Sandbox/paper endpoints must
  remain the default even then.
- ❌ Automatically fetch or display the user's account balances or
  positions without an explicit `--show-account` flag.

---

## 4. Suggested roadmap

| Phase | Timeframe | Contents |
|---|---|---|
| **0 — Ship this PR** | Immediate | Bug fixes + new tests in this commit |
| **1 — Polish & Release** | 1–2 weeks | §2.1 quick wins, CI wiring, first PyPI release |
| **2 — Performance & Data** | 2–4 weeks | §2.2 vectorisation + caching + parallel scans, second data source |
| **3 — Analytical Depth** | 4–8 weeks | §2.3 benchmark comparison, trade stats, walk-forward, Monte Carlo |
| **4 — Enterprise polish** | 8+ weeks | §2.5/2.6 signed releases, offline Docker, structured logs, type-checked CI |

Every phase is independent of the others and can ship on its own.

---

*This document is owned by the Model A repository. It does not reference,
nor is it coupled to, any code or strategy in the private base-NAE
codebase.*
