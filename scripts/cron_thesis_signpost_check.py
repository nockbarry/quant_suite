#!/usr/bin/env python3
"""Thesis Signpost Monitoring Cron Job.

Checks active theses for signpost triggers and sends alerts when
conditions may have been met. Run hourly during market hours.

Usage:
    # Run once
    PYTHONPATH=. python scripts/cron_thesis_signpost_check.py

    # Add to crontab (run every hour 6am-5pm ET on weekdays)
    0 6-17 * * 1-5 cd /home/nock/projects/quant_suite && PYTHONPATH=. python scripts/cron_thesis_signpost_check.py

Output:
    - Alerts written to ~/quant_results/alerts/signpost_alerts.json
    - Summary logged to stdout
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.core.paths import paths
from src.knowledge.thesis import ThesisTracker, Thesis
from src.synthesis.state import SignpostAlert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SignpostChecker:
    """Check thesis signposts for potential triggers."""

    def __init__(self):
        self.tracker = ThesisTracker(paths.theses)
        self.alerts_dir = paths.base / "alerts"
        self.alerts_dir.mkdir(parents=True, exist_ok=True)

    async def check_all_signposts(self) -> list[SignpostAlert]:
        """Check all active theses for signpost triggers.

        Returns:
            List of SignpostAlert objects for potential triggers
        """
        alerts = []
        theses = self.tracker.get_active_theses()

        logger.info(f"Checking {len(theses)} active theses for signpost triggers")

        for thesis in theses:
            thesis_alerts = await self._check_thesis_signposts(thesis)
            alerts.extend(thesis_alerts)

        return alerts

    async def _check_thesis_signposts(self, thesis: Thesis) -> list[SignpostAlert]:
        """Check signposts for a single thesis."""
        alerts = []

        for i, signpost in enumerate(thesis.signposts):
            if signpost.status != "pending":
                continue

            # Assess likelihood based on various factors
            likelihood = await self._assess_signpost_likelihood(thesis, signpost)

            if likelihood > 0.3:  # Threshold for alerting
                evidence = self._gather_evidence(thesis, signpost)
                alert = SignpostAlert(
                    thesis_id=thesis.id,
                    thesis_name=thesis.name,
                    signpost_description=signpost.description,
                    triggered_at=datetime.now().isoformat(),
                    outcome=getattr(signpost, "outcome", "neutral"),
                    news_headline=f"Signpost #{i} triggered ({likelihood:.0%})",
                    news_source="signpost_monitor",
                    recommended_action=f"Review: {signpost.description[:60]}. {evidence[:100]}",
                    urgency="high" if likelihood > 0.7 else "medium" if likelihood > 0.5 else "low",
                )
                alerts.append(alert)

                logger.info(
                    f"Potential signpost trigger: {thesis.name} - "
                    f"{signpost.description} (likelihood: {likelihood:.0%})"
                )

        return alerts

    async def _assess_signpost_likelihood(
        self,
        thesis: Thesis,
        signpost,
    ) -> float:
        """Assess the likelihood that a signpost has been triggered.

        This is a heuristic assessment based on:
        - Time proximity to target date
        - Recent news relevance
        - Price action in related positions
        """
        likelihood = 0.0

        # Factor 1: Target date proximity
        if signpost.target_date:
            try:
                target = datetime.strptime(signpost.target_date, "%Y-%m-%d")
                days_until = (target - datetime.now()).days

                if days_until <= 0:
                    # Past target date - should be evaluated
                    likelihood += 0.4
                elif days_until <= 3:
                    # Within 3 days
                    likelihood += 0.3
                elif days_until <= 7:
                    # Within a week
                    likelihood += 0.2
            except ValueError:
                pass

        # Factor 2: Thesis age without signpost activity
        days_active = (datetime.now() - thesis.created).days
        triggered_count = sum(1 for s in thesis.signposts if s.status == "triggered")

        if days_active > 14 and triggered_count == 0:
            # Old thesis with no activity - may need review
            likelihood += 0.1

        # Factor 3: Check recent news cache for keywords
        likelihood += await self._check_news_relevance(thesis, signpost)

        return min(likelihood, 1.0)

    async def _check_news_relevance(self, thesis: Thesis, signpost) -> float:
        """Check news cache for relevance to signpost."""
        news_path = paths.live / "news_cache.json"

        if not news_path.exists():
            return 0.0

        try:
            with open(news_path) as f:
                news_data = json.load(f)

            # Extract keywords from signpost
            keywords = self._extract_keywords(signpost.description)
            keywords.extend(thesis.positions)

            # Check news items
            relevance_score = 0.0
            news_items = news_data.get("items", [])

            for item in news_items[:50]:  # Check recent items
                title = item.get("title", "").lower()
                summary = item.get("summary", "").lower()
                content = f"{title} {summary}"

                matches = sum(1 for kw in keywords if kw.lower() in content)
                if matches >= 2:
                    relevance_score += 0.1

            return min(relevance_score, 0.3)

        except Exception as e:
            logger.debug(f"Error checking news relevance: {e}")
            return 0.0

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from signpost description."""
        # Simple keyword extraction - split on spaces, filter short words
        words = text.replace(",", " ").replace(".", " ").split()
        keywords = [w for w in words if len(w) > 3 and w[0].isupper()]
        return keywords[:10]

    def _gather_evidence(self, thesis: Thesis, signpost) -> str:
        """Gather evidence string for the alert."""
        evidence_parts = []

        if signpost.target_date:
            try:
                target = datetime.strptime(signpost.target_date, "%Y-%m-%d")
                days_until = (target - datetime.now()).days
                if days_until <= 0:
                    evidence_parts.append(f"Target date passed ({signpost.target_date})")
                else:
                    evidence_parts.append(f"Target date in {days_until} days")
            except ValueError:
                pass

        days_active = (datetime.now() - thesis.created).days
        evidence_parts.append(f"Thesis active for {days_active} days")

        if thesis.positions:
            evidence_parts.append(f"Positions: {', '.join(thesis.positions)}")

        return "; ".join(evidence_parts) if evidence_parts else "Routine check"

    def save_alerts(self, alerts: list[SignpostAlert]) -> Path:
        """Save alerts to JSON file."""
        alerts_file = self.alerts_dir / "signpost_alerts.json"

        # Load existing alerts
        existing = []
        if alerts_file.exists():
            try:
                with open(alerts_file) as f:
                    data = json.load(f)
                    existing = data.get("alerts", [])
            except Exception:
                pass

        # Add new alerts with timestamp
        new_alerts = []
        for alert in alerts:
            alert_dict = alert.to_dict()
            alert_dict["checked_at"] = datetime.now().isoformat()
            alert_dict["acknowledged"] = False
            new_alerts.append(alert_dict)

        # Combine and deduplicate (keep most recent)
        all_alerts = new_alerts + existing
        seen = set()
        deduped = []
        for a in all_alerts:
            key = (a["thesis_id"], a["signpost_index"])
            if key not in seen:
                seen.add(key)
                deduped.append(a)

        # Keep only recent alerts (last 7 days)
        cutoff = datetime.now() - timedelta(days=7)
        recent = [
            a for a in deduped
            if datetime.fromisoformat(a["checked_at"]) >= cutoff
        ]

        # Save
        with open(alerts_file, "w") as f:
            json.dump({
                "updated_at": datetime.now().isoformat(),
                "alerts": recent,
            }, f, indent=2)

        logger.info(f"Saved {len(new_alerts)} new alerts to {alerts_file}")
        return alerts_file

    def get_theses_due_for_review(self) -> list[Thesis]:
        """Get theses that are due for scheduled review."""
        return self.tracker.get_theses_due_for_review()


async def main():
    parser = argparse.ArgumentParser(description="Check thesis signposts for triggers")
    parser.add_argument("--dry-run", action="store_true", help="Don't save alerts")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    checker = SignpostChecker()

    # Check signposts
    alerts = await checker.check_all_signposts()

    # Check theses due for review
    due_for_review = checker.get_theses_due_for_review()

    # Summary
    print("\n" + "=" * 60)
    print("THESIS SIGNPOST CHECK SUMMARY")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Active theses checked: {len(checker.tracker.get_active_theses())}")
    print(f"Potential signpost triggers: {len(alerts)}")
    print(f"Theses due for review: {len(due_for_review)}")

    if alerts:
        print("\nPOTENTIAL TRIGGERS:")
        for alert in alerts:
            print(f"  - [{alert.thesis_name}] {alert.signpost_description}")
            print(f"    Likelihood: {alert.trigger_likelihood:.0%}")
            print(f"    Evidence: {alert.evidence}")

    if due_for_review:
        print("\nDUE FOR REVIEW:")
        for thesis in due_for_review:
            print(f"  - {thesis.name} (conviction: {thesis.conviction:.0f}%)")

    print("=" * 60)

    # Save alerts
    if not args.dry_run and alerts:
        checker.save_alerts(alerts)

    return len(alerts)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(0 if exit_code == 0 else 1)
