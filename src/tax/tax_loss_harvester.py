#!/usr/bin/env python3
"""Tax-Loss Harvesting Scanner - Identify opportunities to realize losses for tax benefits.

Scans portfolio for positions with unrealized losses and suggests:
1. Which positions to sell for tax loss
2. Substitute securities to maintain exposure
3. Wash sale rule compliance (30-day tracking)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from decimal import Decimal

import yaml

logger = logging.getLogger(__name__)

# Substitute pairs - similar exposure without triggering wash sale
SUBSTITUTE_PAIRS = {
    # Broad market
    "SPY": ["VOO", "IVV", "SPLG"],
    "VOO": ["SPY", "IVV", "SPLG"],
    "IVV": ["SPY", "VOO", "SPLG"],
    "QQQ": ["QQQM", "VGT", "XLK"],
    "QQQM": ["QQQ", "VGT", "XLK"],
    "IWM": ["VB", "IJR", "SCHA"],
    "DIA": ["VTI", "SCHX"],

    # Sector ETFs
    "XLE": ["VDE", "IYE", "FENY"],
    "VDE": ["XLE", "IYE", "FENY"],
    "XLF": ["VFH", "IYF", "FNCL"],
    "XLK": ["VGT", "IYW", "FTEC"],
    "VGT": ["XLK", "IYW", "FTEC"],
    "XLV": ["VHT", "IYH", "FHLC"],
    "XLI": ["VIS", "IYJ"],
    "XLU": ["VPU", "IDU"],
    "XLP": ["VDC", "IYK"],
    "XLY": ["VCR", "IYC"],
    "XLB": ["VAW", "IYM"],
    "XLRE": ["VNQ", "IYR"],

    # Gold/Precious Metals
    "GLD": ["IAU", "SGOL", "GLDM"],
    "IAU": ["GLD", "SGOL", "GLDM"],
    "GDX": ["GDXJ", "RING", "GOAU"],
    "GDXJ": ["GDX", "RING"],
    "SLV": ["SIVR", "SIL"],

    # Bonds
    "TLT": ["VGLT", "SPTL", "EDV"],
    "BND": ["AGG", "SCHZ", "IUSB"],
    "AGG": ["BND", "SCHZ", "IUSB"],
    "HYG": ["JNK", "USHY", "SHYG"],

    # International
    "EFA": ["VEA", "IEFA", "SCHF"],
    "VEA": ["EFA", "IEFA", "SCHF"],
    "EEM": ["VWO", "IEMG", "SCHE"],
    "VWO": ["EEM", "IEMG", "SCHE"],
    "FXI": ["MCHI", "KWEB", "CQQQ"],

    # Energy stocks
    "XOM": ["CVX", "COP", "OXY"],
    "CVX": ["XOM", "COP", "OXY"],
    "SLB": ["HAL", "BKR", "NOV"],
    "HAL": ["SLB", "BKR", "NOV"],

    # Tech stocks
    "AAPL": ["MSFT", "GOOGL"],  # Not perfect substitutes
    "MSFT": ["AAPL", "GOOGL"],
    "NVDA": ["AMD", "AVGO", "QCOM"],
    "AMD": ["NVDA", "INTC", "QCOM"],
}


@dataclass
class TaxLossOpportunity:
    """A tax-loss harvesting opportunity."""
    symbol: str
    quantity: int
    cost_basis: float
    current_price: float
    unrealized_loss: float
    loss_percent: float
    holding_period_days: int
    is_long_term: bool
    substitute_symbols: list[str]
    wash_sale_risk: bool
    wash_sale_clear_date: Optional[datetime]
    tax_benefit_estimate: float  # Assuming 35% marginal rate

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "cost_basis": self.cost_basis,
            "current_price": self.current_price,
            "unrealized_loss": self.unrealized_loss,
            "loss_percent": self.loss_percent,
            "holding_period_days": self.holding_period_days,
            "is_long_term": self.is_long_term,
            "substitute_symbols": self.substitute_symbols,
            "wash_sale_risk": self.wash_sale_risk,
            "wash_sale_clear_date": self.wash_sale_clear_date.isoformat() if self.wash_sale_clear_date else None,
            "tax_benefit_estimate": self.tax_benefit_estimate,
        }


@dataclass
class WashSaleRecord:
    """Track wash sale window for a symbol."""
    symbol: str
    sale_date: datetime
    shares_sold: int
    loss_realized: float
    clear_date: datetime  # 30 days after sale
    substitute_bought: Optional[str] = None

    def is_active(self) -> bool:
        return datetime.now() < self.clear_date


class TaxLossHarvester:
    """Scan portfolio for tax-loss harvesting opportunities."""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path.home() / "quant_results" / "tax"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.wash_sale_file = self.config_dir / "wash_sales.json"
        self.harvest_log_file = self.config_dir / "harvest_log.json"

        # Tax settings
        self.short_term_rate = 0.37  # Ordinary income
        self.long_term_rate = 0.20  # Long-term capital gains
        self.min_loss_threshold = 100  # Minimum loss to consider
        self.min_loss_percent = 5.0   # Minimum loss percentage

        # Load wash sale records
        self.wash_sales = self._load_wash_sales()

    def _load_wash_sales(self) -> list[WashSaleRecord]:
        """Load wash sale tracking records."""
        if not self.wash_sale_file.exists():
            return []

        with open(self.wash_sale_file) as f:
            data = json.load(f)

        records = []
        for item in data:
            records.append(WashSaleRecord(
                symbol=item["symbol"],
                sale_date=datetime.fromisoformat(item["sale_date"]),
                shares_sold=item["shares_sold"],
                loss_realized=item["loss_realized"],
                clear_date=datetime.fromisoformat(item["clear_date"]),
                substitute_bought=item.get("substitute_bought"),
            ))

        return records

    def _save_wash_sales(self):
        """Save wash sale records."""
        data = []
        for ws in self.wash_sales:
            data.append({
                "symbol": ws.symbol,
                "sale_date": ws.sale_date.isoformat(),
                "shares_sold": ws.shares_sold,
                "loss_realized": ws.loss_realized,
                "clear_date": ws.clear_date.isoformat(),
                "substitute_bought": ws.substitute_bought,
            })

        with open(self.wash_sale_file, "w") as f:
            json.dump(data, f, indent=2)

    def get_active_wash_sales(self) -> list[WashSaleRecord]:
        """Get wash sales still in their 30-day window."""
        return [ws for ws in self.wash_sales if ws.is_active()]

    def is_in_wash_sale_window(self, symbol: str) -> tuple[bool, Optional[datetime]]:
        """Check if symbol is in a wash sale window."""
        for ws in self.wash_sales:
            if ws.symbol == symbol and ws.is_active():
                return True, ws.clear_date
        return False, None

    def scan_opportunities(self, positions: list[dict]) -> list[TaxLossOpportunity]:
        """Scan positions for tax-loss harvesting opportunities.

        Args:
            positions: List of position dicts with keys:
                - symbol, quantity, cost_basis, current_price, purchase_date
        """
        opportunities = []

        for pos in positions:
            symbol = pos["symbol"]
            quantity = pos.get("quantity", pos.get("qty", 0))
            cost_basis = pos.get("cost_basis", pos.get("avg_entry_price", 0))
            current_price = pos.get("current_price", pos.get("market_value", 0) / quantity if quantity else 0)

            # Calculate unrealized P&L
            total_cost = cost_basis * quantity
            current_value = current_price * quantity
            unrealized_pnl = current_value - total_cost

            # Only consider losses
            if unrealized_pnl >= 0:
                continue

            unrealized_loss = abs(unrealized_pnl)
            loss_percent = (unrealized_loss / total_cost) * 100 if total_cost > 0 else 0

            # Skip if below thresholds
            if unrealized_loss < self.min_loss_threshold:
                continue
            if loss_percent < self.min_loss_percent:
                continue

            # Calculate holding period
            purchase_date = pos.get("purchase_date")
            if purchase_date:
                if isinstance(purchase_date, str):
                    purchase_date = datetime.fromisoformat(purchase_date.replace("Z", "+00:00"))
                holding_days = (datetime.now() - purchase_date.replace(tzinfo=None)).days
            else:
                holding_days = 0  # Unknown

            is_long_term = holding_days > 365

            # Get substitute securities
            substitutes = SUBSTITUTE_PAIRS.get(symbol, [])

            # Check wash sale status
            in_wash_sale, clear_date = self.is_in_wash_sale_window(symbol)

            # Calculate tax benefit
            tax_rate = self.long_term_rate if is_long_term else self.short_term_rate
            tax_benefit = unrealized_loss * tax_rate

            opportunities.append(TaxLossOpportunity(
                symbol=symbol,
                quantity=quantity,
                cost_basis=cost_basis,
                current_price=current_price,
                unrealized_loss=unrealized_loss,
                loss_percent=loss_percent,
                holding_period_days=holding_days,
                is_long_term=is_long_term,
                substitute_symbols=substitutes,
                wash_sale_risk=in_wash_sale,
                wash_sale_clear_date=clear_date,
                tax_benefit_estimate=tax_benefit,
            ))

        # Sort by tax benefit (largest first)
        opportunities.sort(key=lambda x: x.tax_benefit_estimate, reverse=True)

        return opportunities

    def record_harvest(self, symbol: str, shares: int, loss_realized: float,
                      substitute_symbol: Optional[str] = None):
        """Record a tax-loss harvest sale."""
        sale_date = datetime.now()
        clear_date = sale_date + timedelta(days=31)  # 30 days + 1 for safety

        wash_sale = WashSaleRecord(
            symbol=symbol,
            sale_date=sale_date,
            shares_sold=shares,
            loss_realized=loss_realized,
            clear_date=clear_date,
            substitute_bought=substitute_symbol,
        )

        self.wash_sales.append(wash_sale)
        self._save_wash_sales()

        # Log the harvest
        self._log_harvest(symbol, shares, loss_realized, substitute_symbol)

        logger.info(f"Recorded tax-loss harvest: {symbol} ({shares} shares, ${loss_realized:.2f} loss)")
        logger.info(f"Wash sale window clears: {clear_date.strftime('%Y-%m-%d')}")

        return wash_sale

    def _log_harvest(self, symbol: str, shares: int, loss: float, substitute: Optional[str]):
        """Log harvest to history file."""
        if self.harvest_log_file.exists():
            with open(self.harvest_log_file) as f:
                log = json.load(f)
        else:
            log = {"harvests": [], "total_loss_realized": 0, "total_tax_saved": 0}

        entry = {
            "date": datetime.now().isoformat(),
            "symbol": symbol,
            "shares": shares,
            "loss_realized": loss,
            "substitute": substitute,
            "tax_saved_estimate": loss * self.short_term_rate,
        }

        log["harvests"].append(entry)
        log["total_loss_realized"] += loss
        log["total_tax_saved"] += entry["tax_saved_estimate"]

        with open(self.harvest_log_file, "w") as f:
            json.dump(log, f, indent=2)

    def get_harvest_summary(self) -> dict:
        """Get summary of tax-loss harvesting activity."""
        if not self.harvest_log_file.exists():
            return {
                "total_loss_realized": 0,
                "total_tax_saved": 0,
                "harvest_count": 0,
                "active_wash_sales": 0,
            }

        with open(self.harvest_log_file) as f:
            log = json.load(f)

        return {
            "total_loss_realized": log.get("total_loss_realized", 0),
            "total_tax_saved": log.get("total_tax_saved", 0),
            "harvest_count": len(log.get("harvests", [])),
            "active_wash_sales": len(self.get_active_wash_sales()),
            "ytd_harvests": [
                h for h in log.get("harvests", [])
                if h["date"].startswith(str(datetime.now().year))
            ],
        }

    def generate_report(self, opportunities: list[TaxLossOpportunity]) -> str:
        """Generate human-readable tax-loss harvesting report."""
        lines = [
            "Tax-Loss Harvesting Report",
            "=" * 50,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        if not opportunities:
            lines.append("No tax-loss harvesting opportunities found.")
            return "\n".join(lines)

        total_loss = sum(o.unrealized_loss for o in opportunities)
        total_benefit = sum(o.tax_benefit_estimate for o in opportunities)

        lines.extend([
            f"Total Opportunities: {len(opportunities)}",
            f"Total Unrealized Loss: ${total_loss:,.2f}",
            f"Estimated Tax Benefit: ${total_benefit:,.2f}",
            "",
            "Opportunities (sorted by tax benefit):",
            "-" * 50,
        ])

        for opp in opportunities[:10]:  # Top 10
            wash_status = "WASH SALE RISK" if opp.wash_sale_risk else "Clear"
            term = "Long-term" if opp.is_long_term else "Short-term"

            lines.extend([
                f"\n{opp.symbol} ({opp.quantity} shares)",
                f"  Loss: ${opp.unrealized_loss:,.2f} ({opp.loss_percent:.1f}%)",
                f"  Tax Benefit: ${opp.tax_benefit_estimate:,.2f} ({term})",
                f"  Status: {wash_status}",
            ])

            if opp.substitute_symbols:
                lines.append(f"  Substitutes: {', '.join(opp.substitute_symbols[:3])}")

        # Active wash sales
        active = self.get_active_wash_sales()
        if active:
            lines.extend([
                "",
                "Active Wash Sale Windows:",
                "-" * 50,
            ])
            for ws in active:
                lines.append(
                    f"  {ws.symbol}: clears {ws.clear_date.strftime('%Y-%m-%d')} "
                    f"(${ws.loss_realized:,.2f} loss)"
                )

        return "\n".join(lines)


async def scan_portfolio_for_harvesting():
    """Scan current portfolio for tax-loss opportunities."""
    from src.execution.alpaca_broker import AlpacaBroker
    from src.core.paths import paths
    import yaml

    # Load credentials
    with open(paths.config / "credentials.yaml") as f:
        creds = yaml.safe_load(f)

    broker = AlpacaBroker(
        api_key=creds["alpaca"]["api_key"],
        secret_key=creds["alpaca"]["secret_key"],
        paper=True,
    )

    await broker.connect()
    positions = await broker.get_positions()

    # Convert to dict format
    pos_list = []
    for pos in positions:
        pos_list.append({
            "symbol": pos.symbol,
            "quantity": int(pos.quantity),
            "cost_basis": float(pos.avg_entry_price),
            "current_price": float(pos.current_price),
        })

    harvester = TaxLossHarvester()
    opportunities = harvester.scan_opportunities(pos_list)

    report = harvester.generate_report(opportunities)
    print(report)

    # Save opportunities
    output_file = harvester.config_dir / "opportunities.json"
    with open(output_file, "w") as f:
        json.dump([o.to_dict() for o in opportunities], f, indent=2)

    print(f"\nSaved to: {output_file}")

    return opportunities


if __name__ == "__main__":
    import asyncio
    asyncio.run(scan_portfolio_for_harvesting())
