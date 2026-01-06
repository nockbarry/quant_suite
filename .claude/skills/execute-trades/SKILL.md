---
name: execute-trades
description: Execute approved trading decisions via Alpaca API. Reads pending decisions from /trade-decision, validates against risk limits, and submits orders. Requires explicit approval before execution.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write
---

# Execute Trades Skill

Executes approved trading decisions through the Alpaca broker API.

## Purpose

This skill:
1. Reads pending decisions from `/trade-decision` output
2. Validates each decision against risk limits
3. **Requires explicit approval** before execution
4. Submits orders to Alpaca (paper or live)
5. Logs execution results

## Safety Features

- **Explicit approval required** - Never auto-execute without user confirmation
- **Risk limit validation** - Position sizing, sector exposure, daily loss limits
- **PDT compliance check** - Warns if day trade count is at limit
- **Paper trading default** - Uses paper account unless explicitly overridden

## Quick Start

```bash
# Check pending decisions
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.decision.decision_logger import DecisionLogger

logger = DecisionLogger()
pending = logger.get_pending_decisions()

print(f"Pending decisions: {len(pending)}")
for d in pending:
    print(f"  {d.action.value} {d.symbol}")
    print(f"    Size: {d.size_pct}% of portfolio")
    print(f"    Confidence: {d.confidence:.0%}")
    print(f"    Reasoning: {d.reasoning[:100]}...")
    print()
EOF
```

## Execution Flow

### Step 1: Review Pending Decisions
```python
from src.decision.decision_logger import DecisionLogger

logger = DecisionLogger()
pending = logger.get_pending_decisions()

for decision in pending:
    print(f"""
    Decision ID: {decision.id}
    Action: {decision.action.value} {decision.symbol}
    Size: {decision.size_pct}% of portfolio
    Confidence: {decision.confidence:.0%}
    Stop Loss: {decision.stop_loss_pct}%
    Take Profit: {decision.take_profit_pct}%

    Reasoning:
    {decision.reasoning}

    Key Factors:
    {', '.join(decision.key_factors)}

    Risks:
    {', '.join(decision.risks)}
    """)
```

### Step 2: Risk Validation
```python
from alpaca.trading.client import TradingClient
import yaml

# Load credentials
with open("/home/nock/projects/quant_suite/config/credentials.yaml") as f:
    creds = yaml.safe_load(f)

client = TradingClient(
    creds["alpaca"]["api_key"],
    creds["alpaca"]["secret_key"],
    paper=True
)

account = client.get_account()
positions = client.get_all_positions()

# Calculate current exposure
equity = float(account.equity)
cash = float(account.cash)

print(f"Account Equity: ${equity:,.2f}")
print(f"Cash Available: ${cash:,.2f}")
print(f"Buying Power: ${float(account.buying_power):,.2f}")
print(f"Day Trade Count: {account.daytrade_count}/3")

# For each pending decision, validate:
for decision in pending:
    proposed_size = equity * (decision.size_pct / 100)

    # Check 1: Cash available
    if proposed_size > cash:
        print(f"WARNING: {decision.symbol} size ${proposed_size:,.0f} exceeds cash ${cash:,.0f}")

    # Check 2: Position limit (25% max)
    if decision.size_pct > 25:
        print(f"WARNING: {decision.symbol} size {decision.size_pct}% exceeds 25% limit")

    # Check 3: PDT (if <$25k)
    if equity < 25000 and account.daytrade_count >= 3:
        print(f"WARNING: PDT limit reached - no day trades allowed")
```

### Step 3: User Approval

**CRITICAL: Never execute without explicit user approval.**

Present decisions and ask:
- "Approve all pending decisions?" → Execute all
- "Approve specific decisions?" → Execute selected
- "Cancel" → Do not execute

### Step 4: Execute Orders

```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from src.decision.decision_logger import DecisionLogger, Action

def execute_decision(client, decision, equity):
    """Execute a single trading decision."""

    # Calculate shares
    if decision.action in [Action.BUY, Action.ADD]:
        side = OrderSide.BUY
    else:
        side = OrderSide.SELL

    # Get current price for share calculation
    quote = client.get_latest_quote(decision.symbol)
    price = float(quote.ask_price) if side == OrderSide.BUY else float(quote.bid_price)

    # Calculate shares from size_pct
    dollar_amount = equity * (decision.size_pct / 100)
    shares = int(dollar_amount / price)

    if shares <= 0:
        print(f"ERROR: Calculated 0 shares for {decision.symbol}")
        return None

    # Create order
    if decision.limit_price:
        order_request = LimitOrderRequest(
            symbol=decision.symbol,
            qty=shares,
            side=side,
            time_in_force=TimeInForce.DAY,
            limit_price=decision.limit_price,
        )
    else:
        order_request = MarketOrderRequest(
            symbol=decision.symbol,
            qty=shares,
            side=side,
            time_in_force=TimeInForce.DAY,
        )

    # Submit order
    try:
        order = client.submit_order(order_request)
        print(f"ORDER SUBMITTED: {side.value} {shares} {decision.symbol}")
        print(f"  Order ID: {order.id}")
        print(f"  Status: {order.status}")
        return order
    except Exception as e:
        print(f"ORDER FAILED: {e}")
        return None

# Execute approved decisions
logger = DecisionLogger()

for decision in approved_decisions:
    order = execute_decision(client, decision, equity)

    if order:
        # Update decision log with execution
        logger.record_execution(
            decision_id=decision.id,
            execution_price=float(order.filled_avg_price) if order.filled_avg_price else None,
        )
```

## Example Session

```
User: /execute-trades

Claude: I'll review pending decisions and execute with your approval.

## Pending Decisions

### Decision 1: BUY HAL
- **Size:** 3% of portfolio (~$2,900)
- **Confidence:** 68%
- **Stop Loss:** -10%
- **Reasoning:** HAL benefits from Venezuela thesis, insider_technical signal

### Risk Validation
- Account Equity: $95,888
- Cash Available: $10,000
- Position Size: $2,877 (within limits)
- Day Trade Count: 0/3 (OK)
- Sector Exposure After: Energy 48% (approaching limit)

### Approval Required

Do you want to execute this trade?

Options:
1. **Execute HAL BUY** - Submit market order for ~$2,900
2. **Modify** - Change size or other parameters
3. **Skip** - Do not execute this decision
4. **Cancel all** - Exit without executing

---

User: Execute HAL BUY

Claude: Executing HAL BUY order...

**Order Submitted:**
- Symbol: HAL
- Side: BUY
- Quantity: 90 shares
- Type: Market
- Order ID: xyz789
- Status: PENDING

[Waiting for fill...]

**Order Filled:**
- Fill Price: $31.97
- Total Cost: $2,877.30
- Commission: $0

Decision logged as EXECUTED.
Updated decision ID: abc123 with execution details.

## Summary
- Executed: 1 order (HAL BUY)
- Skipped: 0
- Failed: 0

Run /monitor to check position status.
```

## Risk Limits Enforced

| Limit | Value | Action |
|-------|-------|--------|
| Single position | 25% max | Block if exceeded |
| Sector exposure | 40% max | Warn if exceeded |
| Daily loss | 5% max | Block new trades |
| PDT (if <$25k) | 3 day trades/5 days | Warn/block |
| Cash requirement | Must have cash | Block if insufficient |

## Order Types Supported

| Type | When to Use |
|------|-------------|
| Market | Default, immediate execution |
| Limit | When price matters (set limit_price in decision) |
| Stop | Not directly supported (use stop_loss_pct for tracking) |

## Key Files

| File | Purpose |
|------|---------|
| `/home/nock/quant_results/decisions/` | Pending decisions |
| `/home/nock/quant_results/executions/` | Execution logs |
| `config/credentials.yaml` | Alpaca credentials |

## Post-Execution

After execution:
1. Decision status updated to "executed"
2. Execution price and time recorded
3. Run `/monitor` to track position
4. Run `/eod-review` at end of day to evaluate
