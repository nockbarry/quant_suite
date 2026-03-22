"""Skill Contract Tests.

Verifies that Python code referenced in SKILL.md files actually works
with the current codebase. Catches contract drift between skills and runtime.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestTradeDecisionSkill:
    def test_unified_state_loads(self):
        from src.synthesis.state import UnifiedState
        from src.core.paths import paths
        assert hasattr(UnifiedState, 'load')

    def test_decision_logger_create(self):
        from src.decision.decision_logger import create_decision
        import inspect
        sig = inspect.signature(create_decision)
        assert 'symbol' in sig.parameters
        assert 'action' in sig.parameters
        assert 'confidence' in sig.parameters

    def test_adversarial_agent(self):
        from src.decision.adversary import AdversarialAgent
        assert hasattr(AdversarialAgent(), 'challenge')

    def test_context_builder(self):
        from src.intelligence.context_builder import DecisionContextBuilder


class TestMorningBriefingSkill:
    def test_situation_board(self):
        from src.swarm.situation_board import SituationBoard
        board = SituationBoard.load()
        assert hasattr(board, 'get_summary')
        assert hasattr(board, 'add_observation')

    def test_strategic_context(self):
        from src.swarm.strategic_context import StrategicContext
        ctx = StrategicContext.load()
        assert hasattr(ctx, 'get_summary')


class TestAnalystSkill:
    def test_add_research_hypothesis(self):
        from src.swarm.strategic_context import StrategicContext
        ctx = StrategicContext.load()
        assert hasattr(ctx, 'add_research_hypothesis')


class TestEODReviewSkill:
    def test_belief_updater(self):
        from src.intelligence.belief_updater import BeliefUpdater
        assert hasattr(BeliefUpdater, 'run_daily_update')


class TestSystemReviewSkill:
    def test_auto_upgrader(self):
        from src.upgrades.auto_upgrader import AutoUpgrader, UpgradeProposal
        upgrader = AutoUpgrader()
        assert hasattr(upgrader, 'validate_proposal')
        assert hasattr(upgrader, 'run_validation')

    def test_bug_monitor(self):
        from src.intelligence.bug_monitor import BugMonitor
        assert hasattr(BugMonitor(), 'scan_all')


class TestThesisSkill:
    def test_thesis_tracker_crud(self):
        from src.knowledge.thesis import ThesisTracker
        from src.core.paths import paths
        tracker = ThesisTracker(paths.theses)
        assert hasattr(tracker, 'create_thesis')
        assert hasattr(tracker, 'get_thesis')
        assert hasattr(tracker, 'get_active_theses')


class TestSignalEngines:
    def test_conviction_velocity(self):
        from src.signals.conviction_velocity import ConvictionVelocityEngine
        assert hasattr(ConvictionVelocityEngine(), 'scan_all_theses')

    def test_crisis_alpha(self):
        from src.signals.crisis_alpha import CrisisAlphaEngine
        engine = CrisisAlphaEngine()
        assert 'NVDA' in engine.TARGETS


class TestMultiInstance:
    def test_instance_config(self):
        from src.core.instance import instance_config
        assert hasattr(instance_config, 'instance_name')
        assert hasattr(instance_config, 'all_instance_dirs')

    def test_meta_observer(self):
        from src.parallel.meta_observer import MetaObserver
        assert hasattr(MetaObserver(), 'run')

    def test_ensemble(self):
        from src.decision.ensemble import DecisionEnsemble
        assert hasattr(DecisionEnsemble(), 'evaluate')


class TestSafetyGuardrails:
    def test_forbidden_files(self):
        from src.upgrades.auto_upgrader import AutoUpgrader, UpgradeProposal
        p = UpgradeProposal(id='t', timestamp='', tier=1, category='t',
            description='t', files_to_modify=['config/credentials.yaml'],
            files_to_create=[], rationale='', evidence='',
            estimated_impact='', risk_level='low')
        valid, _ = AutoUpgrader().validate_proposal(p)
        assert not valid

    def test_self_modification_blocked(self):
        from src.upgrades.auto_upgrader import AutoUpgrader, UpgradeProposal
        p = UpgradeProposal(id='t', timestamp='', tier=1, category='t',
            description='t', files_to_modify=['src/upgrades/auto_upgrader.py'],
            files_to_create=[], rationale='', evidence='',
            estimated_impact='', risk_level='low')
        valid, _ = AutoUpgrader().validate_proposal(p)
        assert not valid

    def test_adaptive_triggers(self):
        from src.intelligence.adaptive_triggers import TRIGGER_RULES
        assert len(TRIGGER_RULES) >= 10
