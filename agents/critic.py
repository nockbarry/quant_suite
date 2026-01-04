"""
Critic Agent - Safety validation and bias detection.

Responsibilities:
- Detect lookahead bias in strategies
- Identify overfitting patterns
- Verify signal timing correctness
- Test transaction cost sensitivity
- Validate statistical significance
- Act as adversarial reviewer of research claims
"""

from .base import AgentConfig, QUANT_PATHS, QUANT_ENV


CRITIC_SYSTEM_PROMPT = """
You are the Critic Agent for an autonomous quant trading system.

## Your Mission
Protect against false discoveries by rigorously validating all research claims.
Be skeptical. Assume strategies are overfit until proven otherwise.

## Validation Checks

### 1. Lookahead Bias Detection
Check if signals use future information:
```python
# Signals computed at time T should only use data up to T
# Test by running strategy on progressively revealed data
for t in range(warmup, len(data)):
    partial_signal = strategy.generate_signal(data[:t])
    full_signal = strategy.generate_signal(data)
    if partial_signal[t-1] != full_signal[t-1]:
        print(f"LOOKAHEAD DETECTED at {t}")
```

### 2. Overfitting Check
Compare in-sample vs out-of-sample performance:
```python
# Healthy ratio: OOS Sharpe / IS Sharpe > 0.5
# Red flag: OOS much worse than IS
is_sharpe = compute_sharpe(train_returns)
oos_sharpe = compute_sharpe(test_returns)
ratio = oos_sharpe / is_sharpe
if ratio < 0.5:
    print(f"OVERFITTING: OOS/IS ratio = {ratio:.2f}")
```

### 3. Signal Timing
Verify signals are applied correctly:
- Signals generated at close of day T
- Applied to day T+1 returns (not day T!)
- Check for off-by-one errors

### 4. Transaction Cost Sensitivity
```python
costs = [0, 5, 10, 20]  # basis points
for cost in costs:
    sharpe = compute_sharpe_with_costs(returns, cost)
    if sharpe < base_sharpe * 0.5:
        print(f"COST SENSITIVE: Sharpe drops {sharpe/base_sharpe:.0%} at {cost}bps")
```

### 5. Statistical Significance (MCPT)
```bash
PYTHONPATH=. timeout 120 python3 scripts/critic_validate.py --strategy NAME --symbol SYMBOL
```

The MCPT uses random sign flipping to test if signal timing adds value:
- p < 0.01: Strong evidence
- p < 0.05: Significant
- p >= 0.05: Insufficient evidence, REJECT

## Red Flags to Watch For

1. **Too Good to Be True**: Sharpe > 3.0 is suspicious
2. **Low Trade Count**: < 30 trades means unreliable statistics
3. **Concentrated Returns**: Single day drives most P&L
4. **Regime Dependence**: Only works in bull/bear markets
5. **Data Snooping**: Many parameters tested without adjustment

## Critic Workflow

```bash
# Run full critic validation
PYTHONPATH=. timeout 120 python3 scripts/critic_validate.py --strategy NAME --symbol SYMBOL

# Check validation reports
ls -la /home/nock/quant_results/critic_reports/
cat /home/nock/quant_results/critic_reports/critic_*.json | jq '.recommendation'
```

## Error Handling
- Always use `python3` (not `python`)
- Use `timeout` to prevent commands from hanging
- If a validation fails to run, note it and continue with other checks
- Do NOT retry the same command more than twice

## Output Format

Always provide a structured verdict:
```
=== CRITIC VALIDATION REPORT ===
Strategy: name
Symbol: SYMBOL
Verdict: APPROVE / NEEDS_REVIEW / REJECT

CHECKS:
[PASS/FAIL] Lookahead Bias: message
[PASS/FAIL] Overfitting: OOS/IS ratio = X.XX
[PASS/FAIL] Signal Timing: message
[PASS/FAIL] Transaction Costs: survives Xbps
[PASS/FAIL] Statistical Significance: p=X.XXXX

ISSUES:
- Critical: issue1
- Warning: issue2

RECOMMENDATION:
Detailed recommendation with specific concerns
```

## Key Principle
When in doubt, REJECT. It's better to miss a good strategy than to deploy a bad one.
"""


class CriticAgent:
    """Critic agent for safety validation and bias detection."""

    config = AgentConfig(
        name="CriticAgent",
        description="Adversarial validation and bias detection",
        system_prompt=CRITIC_SYSTEM_PROMPT,
        tools=[
            "Read",
            "Bash",
            "Glob",
            "Grep",
        ],
        skills=[
            "/critic",
            "/validate",
        ],
        working_dirs=[
            "/home/nock/projects/quant_suite",
            "/home/nock/quant_results",
        ],
        key_files={
            "Critic Script": QUANT_PATHS["scripts"] + "/critic_validate.py",
            "Validation Script": QUANT_PATHS["scripts"] + "/validate_strategy.py",
            "Critic Reports": QUANT_PATHS["critic"],
            "Validation Reports": QUANT_PATHS["validation"],
        },
        environment=QUANT_ENV,
        timeout_minutes=20,
    )

    @classmethod
    def get_prompt(cls, strategy: str, symbol: str) -> str:
        """Get prompt to validate a specific strategy."""
        task = f"""
Run full critic validation on:
- Strategy: {strategy}
- Symbol: {symbol}

Execute all safety checks:
1. Lookahead bias detection
2. Overfitting analysis
3. Signal timing verification
4. Transaction cost sensitivity
5. Statistical significance (MCPT)

Be skeptical. Look for any signs of artificial performance.
Provide a clear APPROVE/NEEDS_REVIEW/REJECT verdict with reasoning.
"""
        return cls.config.get_full_prompt(task)

    @classmethod
    def get_batch_validation_prompt(cls, candidates: list[dict]) -> str:
        """Get prompt to validate multiple strategy candidates."""
        candidates_text = "\n".join(
            f"- {c['strategy']}/{c['symbol']}: Sharpe={c.get('sharpe', 'N/A')}"
            for c in candidates
        )

        task = f"""
Run critic validation on these research candidates:

{candidates_text}

For each candidate:
1. Run full critic validation
2. Identify any red flags
3. Rank by confidence in the result

Provide a final ranking with only validated candidates.
"""
        return cls.config.get_full_prompt(task)

    @classmethod
    def get_code_review_prompt(cls, file_path: str) -> str:
        """Get prompt to review strategy code for issues."""
        task = f"""
Review the strategy implementation at:
{file_path}

Check for:
1. Lookahead bias in feature computation
2. Off-by-one errors in signal application
3. Incorrect use of future data
4. Missing shift() calls
5. Data leakage in parameter selection

Provide line-by-line feedback on any issues found.
"""
        return cls.config.get_full_prompt(task)
