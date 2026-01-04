"""
Financial NLP Pipeline.

Comprehensive NLP processing for financial text data including:
- Entity recognition (companies, people, products, tickers)
- Sentiment analysis (financial-specific)
- Text embeddings for similarity/clustering
- Source-specific adjustments

As specified in Section 3.5.3 of the Testing Suite documentation.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class EntityType(str, Enum):
    """Types of financial entities."""
    COMPANY = "company"
    TICKER = "ticker"
    PERSON = "person"
    PRODUCT = "product"
    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    MONEY = "money"
    DATE = "date"
    ORGANIZATION = "organization"


@dataclass
class FinancialEntity:
    """An extracted financial entity."""
    text: str
    entity_type: EntityType
    start: int
    end: int
    confidence: float = 1.0
    normalized: str | None = None  # Normalized form (e.g., ticker)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityResult:
    """Result of entity extraction."""
    entities: list[FinancialEntity]
    tickers: list[str]
    companies: list[str]
    people: list[str]
    monetary_values: list[dict[str, Any]]

    def get_by_type(self, entity_type: EntityType) -> list[FinancialEntity]:
        """Get entities by type."""
        return [e for e in self.entities if e.entity_type == entity_type]


@dataclass
class SentimentResult:
    """Result of sentiment analysis."""
    score: float  # -1 to 1
    positive: float  # 0 to 1
    negative: float  # 0 to 1
    neutral: float  # 0 to 1
    confidence: float
    method: str  # 'finbert', 'lexicon', 'ensemble'
    contrarian_signal: float | None = None  # Inverse for social media


@dataclass
class ProcessedText:
    """Full NLP processing result for a text."""
    original_text: str
    cleaned_text: str
    entities: EntityResult
    sentiment: SentimentResult
    embeddings: np.ndarray | None
    source_type: str
    processed_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# LOUGHRAN-MCDONALD FINANCIAL LEXICON
# =============================================================================

class LoughranMcDonaldLexicon:
    """
    Loughran-McDonald financial sentiment lexicon.

    Contains word lists specifically designed for financial text analysis.
    """

    # Core sentiment words (subset for illustration - full lexicon has 2000+ words)
    POSITIVE_WORDS = frozenset([
        "achieve", "achieved", "achieves", "achieving", "advancement", "advancements",
        "advantage", "advantages", "beneficial", "benefit", "benefits", "best",
        "boost", "breakthrough", "creative", "deliver", "delivered", "delivers",
        "efficient", "efficiency", "enjoy", "enjoyed", "enjoys", "excellent",
        "exceed", "exceeded", "exceeding", "exceeds", "exceptional", "excited",
        "exciting", "favorable", "gain", "gained", "gaining", "gains", "good",
        "great", "greater", "greatest", "growing", "growth", "higher", "highest",
        "improve", "improved", "improvement", "improvements", "improves", "improving",
        "increase", "increased", "increases", "increasing", "innovative", "opportunity",
        "opportunities", "optimistic", "outperform", "outperformed", "outperforming",
        "positive", "profit", "profitable", "profits", "progress", "prosper",
        "record", "recovery", "rise", "risen", "rising", "solid", "strength",
        "strong", "stronger", "strongest", "succeed", "succeeded", "succeeds",
        "success", "successful", "successfully", "superior", "surpass", "surpassed",
        "up", "upgrade", "upgraded", "upgrades", "upside", "upturn", "win", "winner",
    ])

    NEGATIVE_WORDS = frozenset([
        "abandon", "abandoned", "abandons", "adverse", "adversely", "against",
        "bad", "bankrupt", "bankruptcy", "cautious", "challenge", "challenges",
        "close", "closed", "closing", "concern", "concerned", "concerns", "cut",
        "cuts", "decline", "declined", "declines", "declining", "decrease",
        "decreased", "decreases", "decreasing", "default", "defaulted", "defaults",
        "deficit", "deficits", "delay", "delayed", "delays", "deteriorate",
        "deteriorated", "deteriorating", "difficult", "difficulties", "difficulty",
        "disappointing", "disappointment", "doubt", "doubted", "doubtful", "down",
        "downgrade", "downgraded", "downgrades", "downside", "downturn", "drop",
        "dropped", "dropping", "drops", "fail", "failed", "failing", "fails",
        "failure", "failures", "fear", "fears", "hurt", "hurts", "impair",
        "impaired", "impairing", "impairment", "impairments", "impairs", "lack",
        "lacked", "lacking", "lacks", "layoff", "layoffs", "loss", "losses",
        "lost", "lower", "lowest", "miss", "missed", "misses", "missing",
        "negative", "negatively", "poor", "poorly", "problem", "problems",
        "recession", "recessions", "restructure", "restructured", "restructures",
        "restructuring", "risk", "risks", "risky", "slow", "slowed", "slower",
        "slowest", "slowing", "slowdown", "struggle", "struggled", "struggles",
        "struggling", "threat", "threaten", "threatened", "threatening", "threatens",
        "trouble", "troubled", "troubles", "uncertain", "uncertainties", "uncertainty",
        "underperform", "underperformed", "underperforming", "unfavorable", "volatile",
        "volatility", "warn", "warned", "warning", "warnings", "warns", "weak",
        "weaken", "weakened", "weakening", "weakness", "worse", "worsen", "worsened",
        "worsening", "worst", "write-off", "writeoff",
    ])

    UNCERTAINTY_WORDS = frozenset([
        "almost", "anticipate", "anticipated", "anticipates", "anticipating",
        "appear", "appeared", "appearing", "appears", "approximate", "approximately",
        "assume", "assumed", "assumes", "assuming", "assumption", "assumptions",
        "believe", "believed", "believes", "believing", "conceivable", "conditional",
        "depend", "depended", "depending", "depends", "doubt", "doubted", "doubtful",
        "doubts", "estimate", "estimated", "estimates", "estimating", "expect",
        "expectation", "expectations", "expected", "expecting", "expects", "forecast",
        "forecasted", "forecasting", "forecasts", "hope", "hoped", "hopeful",
        "hopefully", "hoping", "if", "indefinite", "indefinitely", "indicate",
        "indicated", "indicates", "indicating", "indication", "indications",
        "likelihood", "may", "maybe", "might", "nearly", "occasionally", "opinion",
        "opinions", "perceive", "perceived", "perceives", "perceiving", "perhaps",
        "possible", "possibly", "potential", "potentially", "predict", "predicted",
        "predicting", "prediction", "predictions", "predicts", "preliminary",
        "presumably", "probable", "probably", "project", "projected", "projecting",
        "projection", "projections", "projects", "risk", "risks", "risky", "seem",
        "seemed", "seeming", "seemingly", "seems", "sometime", "sometimes",
        "somewhat", "suggest", "suggested", "suggesting", "suggestion", "suggestions",
        "suggests", "suppose", "supposed", "supposedly", "supposes", "supposing",
        "tend", "tended", "tendency", "tending", "tends", "tentative", "tentatively",
        "think", "thinking", "thinks", "thought", "uncertain", "uncertainties",
        "uncertainty", "unclear", "unknown", "unlikely", "unpredictable", "unsure",
        "usually", "variable", "variably", "variation", "variations", "vary",
        "varied", "varies", "varying", "volatile", "volatility",
    ])

    LITIGIOUS_WORDS = frozenset([
        "acquit", "acquits", "acquitted", "acquitting", "adjudicate", "adjudicated",
        "adjudicates", "adjudicating", "adjudication", "allege", "alleged",
        "allegedly", "alleges", "alleging", "allegation", "allegations", "antitrust",
        "appeal", "appealed", "appealing", "appeals", "arbitrate", "arbitrated",
        "arbitrates", "arbitrating", "arbitration", "arbitrations", "arraign",
        "arraigned", "arraigning", "arraignment", "arraigns", "arrest", "arrested",
        "arresting", "arrests", "bankruptcy", "claim", "claimed", "claiming",
        "claims", "claimant", "claimants", "complaint", "complaints", "conviction",
        "convictions", "court", "courtroom", "courts", "crime", "crimes",
        "criminal", "criminally", "damages", "defendant", "defendants", "deposition",
        "depositions", "discovery", "embezzle", "embezzled", "embezzlement",
        "embezzler", "embezzles", "embezzling", "felonies", "felony", "fraud",
        "frauds", "fraudulent", "fraudulently", "guilty", "indictment", "indictments",
        "infringement", "infringements", "injunction", "injunctions", "insolvent",
        "judge", "judgment", "judgments", "judicial", "judicially", "jury",
        "juries", "law", "laws", "lawsuit", "lawsuits", "lawyer", "lawyers",
        "legal", "legally", "litigate", "litigated", "litigates", "litigating",
        "litigation", "litigations", "mistrial", "mistrials", "plaintiff",
        "plaintiffs", "plea", "plead", "pleaded", "pleading", "pleadings", "pleads",
        "pleas", "prison", "prisoner", "prisoners", "prisons", "prosecute",
        "prosecuted", "prosecutes", "prosecuting", "prosecution", "prosecutions",
        "prosecutor", "prosecutors", "regulatory", "regulators", "sentence",
        "sentenced", "sentencing", "sentences", "settlement", "settlements",
        "settle", "settled", "settles", "settling", "subpoena", "subpoenaed",
        "subpoenas", "sue", "sued", "sues", "suing", "suit", "suits", "summons",
        "testimony", "testify", "testified", "testifies", "trial", "trials",
        "tribunal", "verdict", "verdicts", "violation", "violations", "violate",
        "violated", "violates", "violating",
    ])

    @classmethod
    def score_text(cls, text: str) -> dict[str, float]:
        """
        Score text using Loughran-McDonald lexicon.

        Returns word counts and ratios for each category.
        """
        words = re.findall(r"\b[a-z]+\b", text.lower())
        total_words = len(words) if words else 1

        positive_count = sum(1 for w in words if w in cls.POSITIVE_WORDS)
        negative_count = sum(1 for w in words if w in cls.NEGATIVE_WORDS)
        uncertainty_count = sum(1 for w in words if w in cls.UNCERTAINTY_WORDS)
        litigious_count = sum(1 for w in words if w in cls.LITIGIOUS_WORDS)

        return {
            "positive_count": positive_count,
            "negative_count": negative_count,
            "uncertainty_count": uncertainty_count,
            "litigious_count": litigious_count,
            "positive_ratio": positive_count / total_words,
            "negative_ratio": negative_count / total_words,
            "uncertainty_ratio": uncertainty_count / total_words,
            "litigious_ratio": litigious_count / total_words,
            "net_sentiment": (positive_count - negative_count) / total_words,
            "total_words": len(words),
        }


# =============================================================================
# ENTITY EXTRACTION
# =============================================================================

class FinancialEntityExtractor:
    """
    Extract financial entities from text.

    Uses pattern-based extraction with optional NER model enhancement.
    """

    # Known ticker patterns
    TICKER_PATTERN = re.compile(
        r"(?:^|[\s(:\[\{])([A-Z]{1,5})(?:[\s):\]\}.,!?]|$)"
    )

    # Money pattern
    MONEY_PATTERN = re.compile(
        r"\$\s*[\d,]+(?:\.\d{1,2})?\s*(?:million|billion|trillion|M|B|K|k)?",
        re.IGNORECASE,
    )

    # Percentage pattern
    PERCENT_PATTERN = re.compile(
        r"[\d.]+\s*%|[\d.]+\s*percent|[\d.]+\s*basis\s*points?",
        re.IGNORECASE,
    )

    # Common false positive tickers
    FALSE_POSITIVE_TICKERS = frozenset([
        "THE", "AND", "FOR", "INC", "LLC", "LTD", "CEO", "CFO", "COO", "CTO",
        "IPO", "ETF", "SEC", "NYSE", "NASDAQ", "API", "USA", "GDP", "CPI",
        "FED", "IMF", "USD", "EUR", "GBP", "JPY", "CNY", "CAD", "AUD",
        "EPS", "ROI", "ROE", "ROA", "EBITDA", "P/E", "P/B", "P/S",
        "IT", "AI", "ML", "UI", "UX", "PR", "HR", "IR", "AM", "PM",
        "Q1", "Q2", "Q3", "Q4", "FY", "YTD", "QTD", "MOM", "YOY", "QOQ",
        "EST", "PST", "CST", "MST", "UTC", "GMT",
    ])

    # Major company name patterns (simplified)
    COMPANY_SUFFIXES = re.compile(
        r"\b(\w+(?:\s+\w+)*)\s+(?:Inc\.?|Corp\.?|Corporation|Company|Co\.?|Ltd\.?|LLC|LP|PLC)\b",
        re.IGNORECASE,
    )

    def __init__(self, use_ner_model: bool = False):
        """
        Initialize entity extractor.

        Args:
            use_ner_model: Whether to use spaCy NER (requires spacy + model)
        """
        self.use_ner_model = use_ner_model
        self._nlp = None

        if use_ner_model:
            try:
                import spacy
                self._nlp = spacy.load("en_core_web_sm")
            except (ImportError, OSError):
                logger.warning("spaCy not available, falling back to pattern matching")
                self.use_ner_model = False

    def extract(self, text: str) -> EntityResult:
        """
        Extract financial entities from text.

        Args:
            text: Text to process

        Returns:
            EntityResult with extracted entities
        """
        entities = []

        # Extract tickers
        tickers = self._extract_tickers(text)
        for ticker, start, end in tickers:
            entities.append(FinancialEntity(
                text=ticker,
                entity_type=EntityType.TICKER,
                start=start,
                end=end,
                normalized=ticker,
            ))

        # Extract money
        for match in self.MONEY_PATTERN.finditer(text):
            entities.append(FinancialEntity(
                text=match.group(),
                entity_type=EntityType.MONEY,
                start=match.start(),
                end=match.end(),
            ))

        # Extract percentages
        for match in self.PERCENT_PATTERN.finditer(text):
            entities.append(FinancialEntity(
                text=match.group(),
                entity_type=EntityType.PERCENTAGE,
                start=match.start(),
                end=match.end(),
            ))

        # Extract company names
        for match in self.COMPANY_SUFFIXES.finditer(text):
            company = match.group(1)
            entities.append(FinancialEntity(
                text=match.group(),
                entity_type=EntityType.COMPANY,
                start=match.start(),
                end=match.end(),
                normalized=company.strip(),
            ))

        # Use NER if available
        if self.use_ner_model and self._nlp:
            ner_entities = self._extract_with_ner(text)
            entities.extend(ner_entities)

        # Build result
        unique_tickers = list(set(e.normalized for e in entities if e.entity_type == EntityType.TICKER))
        unique_companies = list(set(e.normalized for e in entities if e.entity_type == EntityType.COMPANY and e.normalized))
        unique_people = list(set(e.text for e in entities if e.entity_type == EntityType.PERSON))

        monetary = [
            {"text": e.text, "start": e.start, "end": e.end}
            for e in entities if e.entity_type == EntityType.MONEY
        ]

        return EntityResult(
            entities=entities,
            tickers=unique_tickers,
            companies=unique_companies,
            people=unique_people,
            monetary_values=monetary,
        )

    def _extract_tickers(self, text: str) -> list[tuple[str, int, int]]:
        """Extract stock tickers from text."""
        tickers = []

        for match in self.TICKER_PATTERN.finditer(text):
            ticker = match.group(1)
            if ticker not in self.FALSE_POSITIVE_TICKERS:
                # Additional validation - check if it looks like a real ticker
                if len(ticker) >= 1 and len(ticker) <= 5:
                    tickers.append((ticker, match.start(1), match.end(1)))

        return tickers

    def _extract_with_ner(self, text: str) -> list[FinancialEntity]:
        """Extract entities using spaCy NER."""
        entities = []
        doc = self._nlp(text)

        for ent in doc.ents:
            entity_type = None

            if ent.label_ == "ORG":
                entity_type = EntityType.ORGANIZATION
            elif ent.label_ == "PERSON":
                entity_type = EntityType.PERSON
            elif ent.label_ == "MONEY":
                entity_type = EntityType.MONEY
            elif ent.label_ == "PERCENT":
                entity_type = EntityType.PERCENTAGE
            elif ent.label_ == "DATE":
                entity_type = EntityType.DATE

            if entity_type:
                entities.append(FinancialEntity(
                    text=ent.text,
                    entity_type=entity_type,
                    start=ent.start_char,
                    end=ent.end_char,
                    confidence=0.8,  # NER confidence estimate
                ))

        return entities


# =============================================================================
# FINANCIAL NLP PIPELINE
# =============================================================================

class FinancialNLPPipeline:
    """
    Full NLP pipeline for financial text data.

    As specified in Section 3.5.3 of the Testing Suite documentation.

    Provides:
    - Text cleaning and normalization
    - Entity recognition (companies, people, products, tickers)
    - Sentiment analysis (FinBERT + Loughran-McDonald)
    - Text embeddings for similarity/clustering
    - Source-specific adjustments
    """

    def __init__(
        self,
        use_finbert: bool = True,
        use_embeddings: bool = True,
        use_ner: bool = False,
    ):
        """
        Initialize NLP pipeline.

        Args:
            use_finbert: Use FinBERT for sentiment (requires transformers)
            use_embeddings: Generate text embeddings (requires sentence-transformers)
            use_ner: Use spaCy NER for entities (requires spacy)
        """
        self.use_finbert = use_finbert
        self.use_embeddings = use_embeddings

        self.entity_extractor = FinancialEntityExtractor(use_ner_model=use_ner)
        self.lexicon = LoughranMcDonaldLexicon()

        # Lazy loading for models
        self._sentiment_model = None
        self._embedding_model = None

    def _load_sentiment_model(self):
        """Load FinBERT sentiment model."""
        if self._sentiment_model is not None:
            return self._sentiment_model

        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
            import torch

            model_name = "ProsusAI/finbert"
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            model = AutoModelForSequenceClassification.from_pretrained(model_name)

            device = 0 if torch.cuda.is_available() else -1
            self._sentiment_model = pipeline(
                "sentiment-analysis",
                model=model,
                tokenizer=tokenizer,
                device=device,
                truncation=True,
                max_length=512,
            )
            logger.info("Loaded FinBERT sentiment model")
        except ImportError:
            logger.warning("transformers not available, using lexicon-only sentiment")
            self._sentiment_model = None

        return self._sentiment_model

    def _load_embedding_model(self):
        """Load sentence embedding model."""
        if self._embedding_model is not None:
            return self._embedding_model

        try:
            from sentence_transformers import SentenceTransformer
            self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Loaded embedding model")
        except ImportError:
            logger.warning("sentence-transformers not available, embeddings disabled")
            self._embedding_model = None

        return self._embedding_model

    def clean_text(self, text: str) -> str:
        """
        Clean and normalize text.

        Args:
            text: Raw text

        Returns:
            Cleaned text
        """
        # Remove URLs
        text = re.sub(r"https?://\S+", "", text)
        # Remove email addresses
        text = re.sub(r"\S+@\S+", "", text)
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        # Remove leading/trailing whitespace
        text = text.strip()

        return text

    def analyze_sentiment(self, text: str, method: str = "ensemble") -> SentimentResult:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze
            method: 'finbert', 'lexicon', or 'ensemble'

        Returns:
            SentimentResult with sentiment scores
        """
        cleaned = self.clean_text(text)

        # Lexicon-based sentiment
        lexicon_scores = self.lexicon.score_text(cleaned)
        lexicon_sentiment = lexicon_scores["net_sentiment"]

        # Normalize to -1 to 1 range
        lexicon_normalized = max(-1.0, min(1.0, lexicon_sentiment * 10))

        if method == "lexicon" or not self.use_finbert:
            positive = max(0, lexicon_normalized)
            negative = max(0, -lexicon_normalized)
            neutral = 1 - abs(lexicon_normalized)

            return SentimentResult(
                score=lexicon_normalized,
                positive=positive,
                negative=negative,
                neutral=neutral,
                confidence=0.6,
                method="lexicon",
            )

        # FinBERT sentiment
        model = self._load_sentiment_model()
        if model is None:
            # Fallback to lexicon
            return self.analyze_sentiment(text, method="lexicon")

        try:
            # Truncate text for model
            truncated = cleaned[:500]
            result = model(truncated)[0]

            label = result["label"].lower()
            score_raw = result["score"]

            if label == "positive":
                finbert_score = score_raw
            elif label == "negative":
                finbert_score = -score_raw
            else:  # neutral
                finbert_score = 0.0

            if method == "finbert":
                return SentimentResult(
                    score=finbert_score,
                    positive=max(0, finbert_score),
                    negative=max(0, -finbert_score),
                    neutral=1 - abs(finbert_score) if abs(finbert_score) < 1 else 0,
                    confidence=score_raw,
                    method="finbert",
                )

            # Ensemble: weighted average
            ensemble_score = 0.7 * finbert_score + 0.3 * lexicon_normalized
            ensemble_confidence = 0.7 * score_raw + 0.3 * 0.6

            return SentimentResult(
                score=ensemble_score,
                positive=max(0, ensemble_score),
                negative=max(0, -ensemble_score),
                neutral=1 - abs(ensemble_score) if abs(ensemble_score) < 1 else 0,
                confidence=ensemble_confidence,
                method="ensemble",
            )

        except Exception as e:
            logger.warning(f"FinBERT analysis failed: {e}, falling back to lexicon")
            return self.analyze_sentiment(text, method="lexicon")

    def generate_embeddings(self, text: str) -> np.ndarray | None:
        """
        Generate text embeddings.

        Args:
            text: Text to embed

        Returns:
            Embedding vector or None if not available
        """
        if not self.use_embeddings:
            return None

        model = self._load_embedding_model()
        if model is None:
            return None

        try:
            cleaned = self.clean_text(text)
            embeddings = model.encode(cleaned, convert_to_numpy=True)
            return embeddings
        except Exception as e:
            logger.warning(f"Embedding generation failed: {e}")
            return None

    def process_text(
        self,
        text: str,
        source_type: Literal["news", "social_media", "earnings_call", "filing", "other"] = "other",
    ) -> ProcessedText:
        """
        Full NLP pipeline for financial text.

        Args:
            text: Text to process
            source_type: Type of source (affects processing)

        Returns:
            ProcessedText with all extracted information
        """
        cleaned = self.clean_text(text)

        # Entity recognition
        entities = self.entity_extractor.extract(cleaned)

        # Sentiment analysis
        sentiment = self.analyze_sentiment(cleaned)

        # Source-specific adjustments
        if source_type == "social_media":
            # Social media often has inverse signal (contrarian)
            sentiment.contrarian_signal = -sentiment.score

        # Generate embeddings
        embeddings = self.generate_embeddings(cleaned)

        return ProcessedText(
            original_text=text,
            cleaned_text=cleaned,
            entities=entities,
            sentiment=sentiment,
            embeddings=embeddings,
            source_type=source_type,
            processed_at=datetime.now(),
        )

    def process_batch(
        self,
        texts: list[str],
        source_type: str = "other",
    ) -> list[ProcessedText]:
        """
        Process multiple texts.

        Args:
            texts: List of texts
            source_type: Source type for all texts

        Returns:
            List of ProcessedText results
        """
        return [self.process_text(t, source_type) for t in texts]


# =============================================================================
# SENTIMENT AGGREGATION
# =============================================================================

def aggregate_sentiment_over_time(
    texts_with_timestamps: list[tuple[str, datetime]],
    entity: str | None = None,
    time_window: timedelta = timedelta(days=7),
    pipeline: FinancialNLPPipeline | None = None,
) -> dict[str, Any]:
    """
    Aggregate sentiment for an entity over time.

    As specified in Section 3.5.3 of the Testing Suite documentation.

    Args:
        texts_with_timestamps: List of (text, timestamp) tuples
        entity: Entity to filter for (ticker or company name)
        time_window: Time window for analysis
        pipeline: NLP pipeline to use

    Returns:
        Aggregated sentiment metrics
    """
    if pipeline is None:
        pipeline = FinancialNLPPipeline(use_finbert=False)  # Fast mode

    # Filter and process texts
    now = datetime.now()
    recent_cutoff = now - time_window

    all_results = []
    recent_results = []

    for text, timestamp in texts_with_timestamps:
        # Process text
        processed = pipeline.process_text(text)

        # Check if entity is mentioned
        if entity:
            tickers = [t.upper() for t in processed.entities.tickers]
            companies = [c.lower() for c in processed.entities.companies]

            entity_found = (
                entity.upper() in tickers or
                entity.lower() in companies or
                entity.lower() in processed.cleaned_text.lower()
            )

            if not entity_found:
                continue

        all_results.append((processed, timestamp))

        if timestamp > recent_cutoff:
            recent_results.append((processed, timestamp))

    if not all_results:
        return {
            "entity": entity,
            "sentiment": 0.0,
            "sentiment_momentum": 0.0,
            "volume": 0,
            "confidence": 0.0,
        }

    # Calculate aggregated sentiment
    total_sentiment = sum(r.sentiment.score for r, _ in all_results)
    avg_sentiment = total_sentiment / len(all_results)

    # Calculate sentiment momentum (recent vs older)
    if recent_results and len(all_results) > len(recent_results):
        recent_sentiment = sum(r.sentiment.score for r, _ in recent_results) / len(recent_results)

        older_results = [(r, t) for r, t in all_results if t <= recent_cutoff]
        older_sentiment = sum(r.sentiment.score for r, _ in older_results) / len(older_results) if older_results else 0

        momentum = recent_sentiment - older_sentiment
    else:
        momentum = 0.0

    # Calculate confidence based on volume
    volume = len(all_results)
    confidence = min(1.0, volume / 10)  # Max confidence at 10+ mentions

    return {
        "entity": entity,
        "sentiment": avg_sentiment,
        "sentiment_momentum": momentum,
        "volume": volume,
        "confidence": confidence,
        "recent_volume": len(recent_results),
        "time_window_days": time_window.days,
    }
