"""Autonomous Code Upgrader.

Manages the branch-test-merge workflow for self-modification.
Called by the system-review skill when code changes are warranted.

Workflow:
1. Create branch: auto-upgrade/<date>-<description>
2. Make changes (max 10 files per session)
3. Run validation suite
4. If all pass -> merge to main
5. If any fail -> revert branch, log failure reason
6. Either way -> log everything to upgrade_log.jsonl
"""

import subprocess
import json
import logging
import os
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)

# Files that MUST NOT be modified by autonomous upgrades
FORBIDDEN_FILES = {
    # Upgrade system itself (prevents recursive self-modification)
    "src/upgrades/__init__.py",
    "src/upgrades/auto_upgrader.py",

    # Core safety mechanisms
    "scripts/auto_corrections.py",
    "src/execution/order_manager.py",  # Trade execution safety

    # Security
    "config/credentials.yaml",
    "config/credentials_beta.yaml",
    "config/credentials_gamma.yaml",
    "config/credentials_template.yaml",
    ".gitignore",

    # Instance infrastructure
    "src/core/instance.py",
    "src/core/paths.py",  # Path system is foundational
}

# Files that CAN be modified (whitelist approach for Tier 1)
TIER1_SAFE_FILES = {
    # Stress test scenarios
    "src/risk/stress_tester.py",
    # Signal weights and thresholds
    "src/signals/conviction_velocity.py",
    "src/signals/crisis_alpha.py",
    "src/signals/live_signal_generator.py",
    # Rules engine thresholds
    "src/execution/rules_engine.py",
    # Data source configs
    "src/data/sources/alternative/expanded_news.py",
    # Documentation
    "CLAUDE.md",
}

# Directories where NEW files can be created (Tier 2)
TIER2_NEW_FILE_DIRS = {
    "src/data/sources/alternative/",
    "src/signals/",
    "src/intelligence/",
    "src/web/routes/",
    "src/web/services/",
    "src/web/templates/",
    ".claude/skills/",
    "scripts/",
}

MAX_FILES_PER_SESSION = 10


@dataclass
class UpgradeProposal:
    """A proposed code change."""
    id: str  # upgrade_<timestamp>_<hash>
    timestamp: str
    tier: int  # 1, 2, or 3
    category: str  # "threshold", "data_source", "signal", "rule", "skill", "documentation", "evaluation"
    description: str
    files_to_modify: list[str]
    files_to_create: list[str]
    rationale: str  # Why this change improves the system
    evidence: str  # Data supporting the change (performance numbers, error rates, etc.)
    estimated_impact: str  # Expected improvement
    risk_level: str  # "low", "medium", "high"
    approved: bool = False
    applied: bool = False
    test_passed: bool = False
    rollback_needed: bool = False
    error: str = ""


@dataclass
class UpgradeResult:
    """Result of an upgrade attempt."""
    proposal_id: str
    timestamp: str
    branch_name: str
    files_changed: int
    tests_passed: bool
    merged: bool
    rollback: bool
    error: str = ""
    validation_output: str = ""


class AutoUpgrader:
    """Manages autonomous code upgrades with safety guardrails."""

    UPGRADE_LOG = paths.base / "logs" / "upgrade_log.jsonl"
    PROPOSALS_DIR = paths.base / "upgrades"

    def __init__(self):
        self.PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
        self.project_dir = Path(__file__).parent.parent.parent

    def validate_proposal(self, proposal: UpgradeProposal) -> tuple[bool, str]:
        """Check if a proposal is safe to apply.

        Returns (is_valid, reason).
        """
        # Check forbidden files
        all_files = proposal.files_to_modify + proposal.files_to_create
        for f in all_files:
            # Normalize path
            try:
                if Path(f).is_absolute():
                    rel_path = str(Path(f).relative_to(self.project_dir))
                else:
                    rel_path = f
            except ValueError:
                return False, f"File {f} is outside project directory"

            # Check against forbidden list
            if rel_path in FORBIDDEN_FILES:
                return False, f"FORBIDDEN: Cannot modify {rel_path}"

            # Also check if any file is inside src/upgrades/ directory
            if rel_path.startswith("src/upgrades/"):
                return False, f"FORBIDDEN: Cannot modify upgrade system files ({rel_path})"

            # Check .git/ directory
            if rel_path.startswith(".git/"):
                return False, f"FORBIDDEN: Cannot modify git internals ({rel_path})"

        # Check file count limit
        if len(all_files) > MAX_FILES_PER_SESSION:
            return False, f"Too many files ({len(all_files)} > {MAX_FILES_PER_SESSION})"

        # Check tier-specific rules
        if proposal.tier == 1:
            for f in proposal.files_to_modify:
                try:
                    if Path(f).is_absolute():
                        rel_path = str(Path(f).relative_to(self.project_dir))
                    else:
                        rel_path = f
                except ValueError:
                    return False, f"File {f} is outside project directory"

                if rel_path not in TIER1_SAFE_FILES:
                    return False, f"Tier 1 cannot modify {rel_path} (not in safe list)"

            # Tier 1 should not create new files
            if proposal.files_to_create:
                return False, "Tier 1 upgrades cannot create new files (use Tier 2)"

        elif proposal.tier == 2:
            for f in proposal.files_to_create:
                try:
                    if Path(f).is_absolute():
                        rel_path = str(Path(f).relative_to(self.project_dir))
                    else:
                        rel_path = f
                except ValueError:
                    return False, f"File {f} is outside project directory"

                parent = str(Path(rel_path).parent) + "/"
                if parent not in TIER2_NEW_FILE_DIRS and not any(
                    rel_path.startswith(d) for d in TIER2_NEW_FILE_DIRS
                ):
                    return False, f"Tier 2 cannot create files in {parent}"

        elif proposal.tier == 3:
            return False, "Tier 3 proposals require human review (logged for manual inspection)"

        else:
            return False, f"Invalid tier: {proposal.tier} (must be 1, 2, or 3)"

        return True, "Proposal is valid"

    def save_proposal(self, proposal: UpgradeProposal) -> Path:
        """Save a proposal to disk for tracking."""
        proposal_file = self.PROPOSALS_DIR / f"{proposal.id}.json"
        with open(proposal_file, 'w') as f:
            json.dump(asdict(proposal), f, indent=2)
        logger.info(f"Saved proposal: {proposal_file}")
        return proposal_file

    def create_branch(self, description: str) -> str:
        """Create a git branch for the upgrade."""
        date = datetime.now().strftime("%Y%m%d")
        # Sanitize description for branch name
        safe_desc = description.replace(' ', '-').replace('/', '-')[:30]
        safe_desc = ''.join(c for c in safe_desc if c.isalnum() or c == '-')
        branch = f"auto-upgrade/{date}-{safe_desc}"

        result = subprocess.run(
            ["git", "checkout", "-b", branch],
            cwd=self.project_dir,
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create branch: {result.stderr}")

        logger.info(f"Created branch: {branch}")
        return branch

    def run_validation(self) -> tuple[bool, str]:
        """Run validation suite after changes.

        Tests:
        1. All modified files pass Python syntax check (py_compile)
        2. Core imports work
        3. Key functional tests pass
        """
        errors = []
        env = {**os.environ, "PYTHONPATH": str(self.project_dir)}

        # 1. Syntax check all Python files that were changed
        result = subprocess.run(
            ["git", "diff", "--name-only", "main"],
            cwd=self.project_dir,
            capture_output=True, text=True
        )
        changed_files = [f for f in result.stdout.strip().split('\n') if f.endswith('.py') and f]

        for f in changed_files:
            filepath = self.project_dir / f
            if filepath.exists():
                check = subprocess.run(
                    ["python3", "-m", "py_compile", str(filepath)],
                    capture_output=True, text=True
                )
                if check.returncode != 0:
                    errors.append(f"Syntax error in {f}: {check.stderr}")

        # 2. Core imports
        import_test = subprocess.run(
            ["python3", "-c", "\n".join([
                "from src.core.paths import paths",
                "from src.core.instance import instance_config",
                "from src.risk.stress_tester import PortfolioStressTester",
                "from src.signals.conviction_velocity import ConvictionVelocityEngine",
                "from src.signals.crisis_alpha import CrisisAlphaEngine",
                "from src.intelligence.cross_reference import CrossReferenceEngine",
                "from src.decision.ensemble import DecisionEnsemble",
                "from src.parallel.meta_observer import MetaObserver",
                "print('All core imports OK')",
            ])],
            cwd=self.project_dir,
            capture_output=True, text=True,
            env=env,
            timeout=30,
        )
        if import_test.returncode != 0:
            errors.append(f"Import test failed: {import_test.stderr}")

        # 3. Quick functional test - stress tester still works
        func_test = subprocess.run(
            ["python3", "-c", "\n".join([
                "from src.risk.stress_tester import PortfolioStressTester",
                "t = PortfolioStressTester()",
                "r = t.run_full_report()",
                "assert r.portfolio_equity > 0, 'Stress tester returned zero equity'",
                "assert len(r.scenario_results) >= 6, f'Expected 6+ scenarios, got {len(r.scenario_results)}'",
                "print('Functional tests OK')",
            ])],
            cwd=self.project_dir,
            capture_output=True, text=True,
            env=env,
            timeout=60,
        )
        if func_test.returncode != 0:
            errors.append(f"Functional test failed: {func_test.stderr}")

        if errors:
            return False, "\n".join(errors)
        return True, "All validations passed"

    def merge_to_main(self, branch: str) -> bool:
        """Merge upgrade branch to main."""
        # Switch to main
        checkout_result = subprocess.run(
            ["git", "checkout", "main"],
            cwd=self.project_dir,
            capture_output=True, text=True
        )
        if checkout_result.returncode != 0:
            logger.error(f"Failed to checkout main: {checkout_result.stderr}")
            return False

        # Merge
        result = subprocess.run(
            ["git", "merge", branch, "--no-edit"],
            cwd=self.project_dir,
            capture_output=True, text=True
        )

        if result.returncode != 0:
            logger.error(f"Merge failed: {result.stderr}")
            # Abort merge if it failed
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=self.project_dir,
                capture_output=True
            )
            return False

        # Delete branch
        subprocess.run(
            ["git", "branch", "-d", branch],
            cwd=self.project_dir,
            capture_output=True
        )
        logger.info(f"Merged and deleted branch: {branch}")
        return True

    def rollback(self, branch: str) -> None:
        """Rollback a failed upgrade."""
        # Switch to main, discarding changes
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=self.project_dir,
            capture_output=True
        )
        subprocess.run(
            ["git", "branch", "-D", branch],
            cwd=self.project_dir,
            capture_output=True
        )
        logger.info(f"Rolled back branch {branch}")

    def apply_upgrade(self, proposal: UpgradeProposal) -> UpgradeResult:
        """Start the upgrade workflow: validate proposal and create branch.

        NOTE: The actual file modifications are done by the calling Claude session
        BETWEEN apply_upgrade() and finalize_upgrade(). This method orchestrates
        the git workflow around those changes.

        Usage:
            result = upgrader.apply_upgrade(proposal)
            if result.error:
                print(f"Rejected: {result.error}")
            else:
                # Make file changes here using Claude Code tools
                result = upgrader.finalize_upgrade(result)
        """
        # Validate proposal
        is_valid, reason = self.validate_proposal(proposal)
        if not is_valid:
            # Save rejected proposal for audit trail
            proposal.error = reason
            self.save_proposal(proposal)

            result = UpgradeResult(
                proposal_id=proposal.id,
                timestamp=datetime.now().isoformat(),
                branch_name="",
                files_changed=0,
                tests_passed=False,
                merged=False,
                rollback=False,
                error=reason,
            )
            self._log_result(result)
            return result

        # Save approved proposal
        proposal.approved = True
        self.save_proposal(proposal)

        # Create branch
        try:
            branch = self.create_branch(proposal.category)
        except RuntimeError as e:
            result = UpgradeResult(
                proposal_id=proposal.id,
                timestamp=datetime.now().isoformat(),
                branch_name="",
                files_changed=0,
                tests_passed=False,
                merged=False,
                rollback=False,
                error=str(e),
            )
            self._log_result(result)
            return result

        # Return result for the caller to make changes, then call finalize_upgrade()
        return UpgradeResult(
            proposal_id=proposal.id,
            timestamp=datetime.now().isoformat(),
            branch_name=branch,
            files_changed=0,  # Updated after changes
            tests_passed=False,  # Updated after validation
            merged=False,  # Updated after merge
            rollback=False,
        )

    def finalize_upgrade(self, result: UpgradeResult) -> UpgradeResult:
        """After changes are made, validate and merge or rollback."""
        if not result.branch_name:
            result.error = "No branch to finalize (apply_upgrade failed)"
            return result

        # Count changed files
        count_result = subprocess.run(
            ["git", "diff", "--name-only", "main"],
            cwd=self.project_dir,
            capture_output=True, text=True
        )
        changed = [f for f in count_result.stdout.strip().split('\n') if f]
        result.files_changed = len(changed)

        if result.files_changed == 0:
            # No changes were actually made
            self.rollback(result.branch_name)
            result.rollback = True
            result.error = "No files were changed"
            self._log_result(result)
            return result

        # Commit changes on branch
        subprocess.run(
            ["git", "add", "-A"],
            cwd=self.project_dir,
            capture_output=True
        )
        commit_msg = f"Auto-upgrade: {result.branch_name.split('/')[-1] if '/' in result.branch_name else result.branch_name}"
        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=self.project_dir,
            capture_output=True
        )

        # Run validation
        tests_passed, validation_output = self.run_validation()
        result.tests_passed = tests_passed
        result.validation_output = validation_output

        if tests_passed:
            # Merge to main
            merged = self.merge_to_main(result.branch_name)
            result.merged = merged
            if not merged:
                self.rollback(result.branch_name)
                result.rollback = True
                result.error = "Merge failed after tests passed"
        else:
            # Rollback
            self.rollback(result.branch_name)
            result.rollback = True
            result.error = validation_output

        # Update proposal status
        self._update_proposal_status(result)

        # Log result
        self._log_result(result)
        return result

    def _update_proposal_status(self, result: UpgradeResult) -> None:
        """Update the saved proposal with the result."""
        proposal_file = self.PROPOSALS_DIR / f"{result.proposal_id}.json"
        if proposal_file.exists():
            try:
                with open(proposal_file) as f:
                    data = json.load(f)
                data['applied'] = result.merged
                data['test_passed'] = result.tests_passed
                data['rollback_needed'] = result.rollback
                data['error'] = result.error
                with open(proposal_file, 'w') as f:
                    json.dump(data, f, indent=2)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Could not update proposal status: {e}")

    def _log_result(self, result: UpgradeResult) -> None:
        """Log upgrade result to JSONL."""
        self.UPGRADE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(self.UPGRADE_LOG, 'a') as f:
            f.write(json.dumps(asdict(result)) + '\n')
        logger.info(
            f"Upgrade {result.proposal_id}: "
            f"{'MERGED' if result.merged else 'ROLLED BACK' if result.rollback else 'REJECTED'}"
        )

    def get_recent_upgrades(self, days: int = 30) -> list[dict]:
        """Get recent upgrade results."""
        if not self.UPGRADE_LOG.exists():
            return []
        results = []
        cutoff = datetime.now() - timedelta(days=days)
        with open(self.UPGRADE_LOG) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    ts_str = data.get("timestamp", "")
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str)
                        if ts > cutoff:
                            results.append(data)
                except (json.JSONDecodeError, ValueError):
                    continue
        return results

    def get_pending_proposals(self) -> list[dict]:
        """Get Tier 3 proposals awaiting human review."""
        proposals = []
        if not self.PROPOSALS_DIR.exists():
            return proposals
        for f in sorted(self.PROPOSALS_DIR.glob("*.json"), reverse=True):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                # Tier 3 proposals or failed proposals that need review
                if data.get('tier') == 3 or (
                    not data.get('applied') and not data.get('approved')
                ):
                    proposals.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        return proposals
