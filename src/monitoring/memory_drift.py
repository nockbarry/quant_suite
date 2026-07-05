"""
Memory-State Drift Detector.

The operator's auto-memory file (~/.claude/projects/.../memory/MEMORY.md)
narrates active thesis convictions in markdown form. Over a session it
drifts away from the canonical `ThesisTracker` state — convictions get
quoted from the previous day, theses get reorganized in the tracker,
or the belief updater applies a change that memory hasn't been updated
to reflect.

This module:
  1) Parses memory claims of the form `**<thesis name> <N>%**`
  2) Matches each claim to an active thesis by name-token overlap
  3) Returns a list of drifts > threshold for the operator to surface

Independent reliability fix A (per plan). Logging-only — does not
mutate memory or thesis state.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Look for **<text> <N>%** patterns. Anchors: bold opening + bold closing,
# percentage at the end. Non-greedy match on the name, restricted to title-case
# alphanumeric / common separators to avoid matching figures inside paragraphs.
_CONVICTION_PATTERN = re.compile(
    r"\*\*\s*([A-Z][\w\s\-/&]{2,60}?)\s+(\d{1,3})%\s*\*\*"
)

DEFAULT_MEMORY_PATH = (
    Path.home()
    / ".claude/projects/-home-nock-projects-quant-suite/memory/MEMORY.md"
)
DEFAULT_DRIFT_THRESHOLD_PP = 5.0  # percentage points


@dataclass
class MemoryClaim:
    """A conviction claim parsed from the memory file."""
    raw_name: str          # exact text from memory: "Rare Earth"
    conviction_pct: float  # the number after the name


@dataclass
class DriftFinding:
    """A drift between memory's claim and the canonical tracker state."""
    memory_name: str
    memory_conviction: float
    thesis_id: str
    thesis_name: str
    actual_conviction: float
    delta_pp: float        # signed; positive means memory > actual
    match_score: float     # token-overlap quality of the name match (0..1)

    @property
    def severity(self) -> str:
        a = abs(self.delta_pp)
        if a >= 15:
            return "critical"
        if a >= 10:
            return "high"
        return "medium"

    def to_dict(self) -> dict:
        return {
            "memory_name": self.memory_name,
            "memory_conviction": self.memory_conviction,
            "thesis_id": self.thesis_id,
            "thesis_name": self.thesis_name,
            "actual_conviction": self.actual_conviction,
            "delta_pp": self.delta_pp,
            "match_score": self.match_score,
            "severity": self.severity,
        }


def parse_memory_claims(memory_path: Optional[Path] = None) -> list[MemoryClaim]:
    """Read the memory file and return all conviction claims found."""
    path = memory_path or DEFAULT_MEMORY_PATH
    if not path.exists():
        logger.debug(f"memory file not present at {path}")
        return []
    try:
        text = path.read_text()
    except Exception as e:
        logger.warning(f"could not read memory file {path}: {e}")
        return []

    claims: list[MemoryClaim] = []
    seen: set[tuple[str, float]] = set()  # dedupe near-duplicates
    for match in _CONVICTION_PATTERN.finditer(text):
        name = match.group(1).strip()
        try:
            pct = float(match.group(2))
        except ValueError:
            continue
        if pct < 0 or pct > 100:
            continue
        # Heuristic filter: skip terms that look like generic adjectives /
        # non-thesis labels (e.g. "ALPHA POSITIONS 99%").
        if name.upper() in {"ALPHA POSITIONS", "BETA", "GAMMA", "ALPHA"}:
            continue
        key = (name.lower(), pct)
        if key in seen:
            continue
        seen.add(key)
        claims.append(MemoryClaim(raw_name=name, conviction_pct=pct))
    return claims


_NAME_STOPWORDS = frozenset({
    "the", "a", "an", "of", "and", "or", "with", "for", "to",
    "thesis", "play", "trade", "supercycle", "crisis", "renaissance",
    "infrastructure", "monopoly", "premium",
})


def _tokenize(name: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z]+", name.lower())
    return {t for t in tokens if len(t) >= 3 and t not in _NAME_STOPWORDS}


def _match_thesis(claim_name: str, theses) -> Optional[tuple[object, float]]:
    """Find the best-matching active thesis for a claim name.

    Score is max(Jaccard, coverage_of_smaller). Coverage handles cases like
    memory's "Cyber" vs tracker's "Cyber Defense Compliance Supercycle" —
    Jaccard is 0.33 there but coverage is 1.0 (the claim's only token is
    fully contained in the thesis). Threshold 0.5 is permissive enough for
    short names but rejects spurious one-token coincidences.
    """
    claim_tokens = _tokenize(claim_name)
    if not claim_tokens:
        return None
    best = None
    best_score = 0.0
    for thesis in theses:
        thesis_tokens = _tokenize(thesis.name or "")
        if not thesis_tokens:
            continue
        union = claim_tokens | thesis_tokens
        inter = claim_tokens & thesis_tokens
        if not inter:
            continue
        jaccard = len(inter) / len(union)
        coverage = len(inter) / min(len(claim_tokens), len(thesis_tokens))
        score = max(jaccard, coverage)
        if score > best_score:
            best = thesis
            best_score = score
    if best is None or best_score < 0.5:
        return None
    return best, best_score


def detect_drift(
    memory_path: Optional[Path] = None,
    threshold_pp: float = DEFAULT_DRIFT_THRESHOLD_PP,
    thesis_tracker=None,
) -> list[DriftFinding]:
    """Compare memory's conviction claims against the canonical tracker.

    Returns drifts whose absolute delta exceeds threshold_pp. Empty list
    means memory is in sync (or no claims could be parsed).
    """
    if thesis_tracker is None:
        from src.knowledge.thesis import ThesisTracker
        from src.core.paths import paths
        thesis_tracker = ThesisTracker(paths.theses)

    claims = parse_memory_claims(memory_path)
    if not claims:
        return []

    active = thesis_tracker.get_active_theses()
    if not active:
        return []

    findings: list[DriftFinding] = []
    matched_thesis_ids: set[str] = set()

    for claim in claims:
        match = _match_thesis(claim.raw_name, active)
        if match is None:
            continue
        thesis, score = match
        # Avoid double-counting: if a thesis already matched a more
        # specific claim, skip subsequent looser matches.
        if thesis.id in matched_thesis_ids:
            continue
        actual = float(thesis.conviction)
        delta = claim.conviction_pct - actual
        if abs(delta) >= threshold_pp:
            findings.append(DriftFinding(
                memory_name=claim.raw_name,
                memory_conviction=claim.conviction_pct,
                thesis_id=thesis.id,
                thesis_name=thesis.name,
                actual_conviction=actual,
                delta_pp=delta,
                match_score=score,
            ))
        matched_thesis_ids.add(thesis.id)

    findings.sort(key=lambda f: abs(f.delta_pp), reverse=True)
    return findings
