#!/usr/bin/env python3
"""
Full ML Pipeline Execution Script

Runs the complete ML pipeline:
1. Load all available data
2. Compute features across universes
3. Train models with walk-forward validation
4. Evaluate and document findings
5. Save validated models

Usage:
    PYTHONPATH=. python scripts/run_ml_pipeline.py
    PYTHONPATH=. python scripts/run_ml_pipeline.py --quick  # Quick test with fewer symbols
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Project imports
from src.data.sources.yahoo import YahooFinanceSource
from src.data.features import FeatureEngine
from src.data.feature_engineering import (
    FeatureComputer,
    EnhancedTechnicalFeatures,
    LatentKnowledgeFeatures,
)
from src.ml import (
    MLTrainingPipeline,
    ModelRegistry,
    MODELS,
    TARGETS,
    UNIVERSE_CONFIGS,
    create_target,
)

# Output directories
RESULTS_DIR = Path("~/quant_results").expanduser()
MODELS_DIR = RESULTS_DIR / "models"
FINDINGS_DIR = RESULTS_DIR / "ml_findings"
LEARNINGS_DIR = RESULTS_DIR / "learnings"

# Ensure directories exist
MODELS_DIR.mkdir(parents=True, exist_ok=True)
FINDINGS_DIR.mkdir(parents=True, exist_ok=True)


async def load_price_data(symbols: list[str], period: str = "2y") -> dict[str, pd.DataFrame]:
    """Load price data for symbols."""
    logger.info(f"Loading price data for {len(symbols)} symbols...")

    from datetime import datetime, timedelta
    from src.core import Timeframe

    # Calculate date range
    end_date = datetime.now()
    if period == "2y":
        start_date = end_date - timedelta(days=730)
    elif period == "1y":
        start_date = end_date - timedelta(days=365)
    else:
        start_date = end_date - timedelta(days=730)

    data_source = YahooFinanceSource()
    price_data = {}

    for symbol in symbols:
        try:
            df = await data_source.fetch_ohlcv(
                symbol=symbol,
                start=start_date,
                end=end_date,
                timeframe=Timeframe.DAILY,
            )
            if df is not None and len(df) > 100:
                price_data[symbol] = df
                logger.info(f"  {symbol}: {len(df)} days")
            else:
                logger.warning(f"  {symbol}: Insufficient data")
        except Exception as e:
            logger.warning(f"  {symbol}: Failed - {e}")

    logger.info(f"Loaded data for {len(price_data)} symbols")
    return price_data


async def compute_features(price_data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Compute all features for each symbol."""
    logger.info("Computing features...")

    feature_engine = FeatureEngine()
    enhanced_features = EnhancedTechnicalFeatures()
    latent_features = LatentKnowledgeFeatures()

    features_by_symbol = {}

    for symbol, df in price_data.items():
        try:
            # Start with price data
            features = df.copy()

            # Add basic technical features
            features = feature_engine.add_all_features(features)

            # Add enhanced features
            enhanced = enhanced_features.compute_all(df)
            features = pd.concat([features, enhanced], axis=1)

            # Add latent knowledge features
            latent = latent_features.compute_all(df, symbol=symbol)
            features = pd.concat([features, latent], axis=1)

            # Remove duplicate columns
            features = features.loc[:, ~features.columns.duplicated()]

            # Drop price columns (keep only features)
            price_cols = ['open', 'high', 'low', 'close', 'volume', 'adj_close']
            feature_cols = [c for c in features.columns if c.lower() not in price_cols]
            features = features[feature_cols]

            # Handle NaN - forward/back fill first
            features = features.ffill().bfill()

            # Drop columns that are still all NaN (missing external data)
            all_nan_cols = features.columns[features.isna().all()].tolist()
            if all_nan_cols:
                logger.debug(f"  {symbol}: Dropping {len(all_nan_cols)} columns with all NaN")
                features = features.drop(columns=all_nan_cols)

            # Fill any remaining NaN with 0
            features = features.fillna(0)

            features_by_symbol[symbol] = features
            logger.info(f"  {symbol}: {len(features.columns)} features")

        except Exception as e:
            logger.warning(f"  {symbol}: Feature computation failed - {e}")

    return features_by_symbol


async def train_models(
    price_data: dict[str, pd.DataFrame],
    features_by_symbol: dict[str, pd.DataFrame],
    targets: list[str] = None,
    models: list[str] = None,
) -> list[dict]:
    """Train ML models and return results."""

    targets = targets or ["direction_5d", "direction_1d"]
    models = models or ["xgboost", "lightgbm", "random_forest"]

    logger.info(f"Training models: {models} for targets: {targets}")

    pipeline = MLTrainingPipeline(models_dir=MODELS_DIR)
    registry = ModelRegistry(MODELS_DIR)

    all_results = []

    for target_name in targets:
        target_config = TARGETS.get(target_name)
        if not target_config:
            logger.warning(f"Unknown target: {target_name}")
            continue

        logger.info(f"\n{'='*60}")
        logger.info(f"TARGET: {target_name}")
        logger.info(f"{'='*60}")

        for model_name in models:
            model_config = MODELS.get(model_name)
            if not model_config:
                logger.warning(f"Unknown model: {model_name}")
                continue

            logger.info(f"\n--- Model: {model_name} ---")

            # Aggregate features and targets across symbols
            all_features = []
            all_targets = []

            for symbol, features in features_by_symbol.items():
                if symbol not in price_data:
                    continue

                # Create target
                target = create_target(price_data[symbol], target_config)

                # Align indices
                common_idx = features.index.intersection(target.index)
                if len(common_idx) < 200:
                    continue

                X = features.loc[common_idx]
                y = target.loc[common_idx]

                # Drop rows with NaN
                mask = X.notna().all(axis=1) & y.notna()
                X = X[mask]
                y = y[mask]

                if len(X) > 100:
                    all_features.append(X)
                    all_targets.append(y)

            if not all_features:
                logger.warning(f"No valid data for {model_name} on {target_name}")
                continue

            # Combine all symbols
            X_combined = pd.concat(all_features, axis=0)
            y_combined = pd.concat(all_targets, axis=0)

            logger.info(f"Training on {len(X_combined)} samples, {len(X_combined.columns)} features")

            try:
                result = await pipeline.train_model(
                    model_config=model_config,
                    target_config=target_config,
                    X=X_combined,
                    y=y_combined,
                    train_days=252,
                    test_days=63,
                    gap_days=5,
                    n_permutations=500,  # Reduced for speed
                )

                # Store result
                model_result = {
                    "target": target_name,
                    "model": model_name,
                    "mean_test_score": result.mean_test_score,
                    "p_value": result.mcpt_result.p_value,
                    "is_significant": result.is_significant,
                    "n_samples": len(X_combined),
                    "n_features": len(X_combined.columns),
                    "top_features": sorted(
                        result.feature_importance.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )[:10],
                }
                all_results.append(model_result)

                logger.info(f"  Test Score: {result.mean_test_score:.4f}")
                logger.info(f"  P-Value: {result.mcpt_result.p_value:.4f}")
                logger.info(f"  Significant: {result.is_significant}")

                # Register if significant
                if result.is_significant:
                    model_id = registry.register(result.model)
                    logger.info(f"  Registered: {model_id}")
                    model_result["model_id"] = model_id

            except Exception as e:
                logger.error(f"Training failed: {e}")
                import traceback
                traceback.print_exc()

    return all_results


def analyze_results(results: list[dict]) -> dict:
    """Analyze training results and generate insights."""

    if not results:
        return {"error": "No results to analyze"}

    df = pd.DataFrame(results)

    analysis = {
        "timestamp": datetime.now().isoformat(),
        "total_models_trained": len(df),
        "significant_models": int(df["is_significant"].sum()),
        "significance_rate": float(df["is_significant"].mean()),
        "by_target": {},
        "by_model": {},
        "top_features": {},
        "recommendations": [],
    }

    # Analysis by target
    for target in df["target"].unique():
        target_df = df[df["target"] == target]
        analysis["by_target"][target] = {
            "n_models": len(target_df),
            "n_significant": int(target_df["is_significant"].sum()),
            "best_score": float(target_df["mean_test_score"].max()),
            "best_model": target_df.loc[target_df["mean_test_score"].idxmax(), "model"],
            "avg_p_value": float(target_df["p_value"].mean()),
        }

    # Analysis by model type
    for model in df["model"].unique():
        model_df = df[df["model"] == model]
        analysis["by_model"][model] = {
            "n_trained": len(model_df),
            "n_significant": int(model_df["is_significant"].sum()),
            "avg_score": float(model_df["mean_test_score"].mean()),
            "significance_rate": float(model_df["is_significant"].mean()),
        }

    # Aggregate feature importance
    feature_counts = {}
    for result in results:
        for feature, importance in result.get("top_features", []):
            if feature not in feature_counts:
                feature_counts[feature] = {"count": 0, "total_importance": 0}
            feature_counts[feature]["count"] += 1
            feature_counts[feature]["total_importance"] += importance

    # Top features
    analysis["top_features"] = sorted(
        [
            {"feature": f, "count": v["count"], "avg_importance": v["total_importance"] / v["count"]}
            for f, v in feature_counts.items()
        ],
        key=lambda x: x["count"] * x["avg_importance"],
        reverse=True
    )[:20]

    # Recommendations
    if analysis["significance_rate"] > 0.3:
        analysis["recommendations"].append("Good significance rate - proceed with paper trading")
    if analysis["significance_rate"] < 0.1:
        analysis["recommendations"].append("Low significance rate - need more feature engineering or data")

    # Best target
    best_target = max(
        analysis["by_target"].items(),
        key=lambda x: x[1]["n_significant"]
    )
    analysis["recommendations"].append(f"Best target: {best_target[0]} ({best_target[1]['n_significant']} significant models)")

    # Best model type
    best_model = max(
        analysis["by_model"].items(),
        key=lambda x: x[1]["significance_rate"]
    )
    analysis["recommendations"].append(f"Best model type: {best_model[0]} ({best_model[1]['significance_rate']:.1%} significance rate)")

    return analysis


def save_findings(analysis: dict, results: list[dict]):
    """Save findings to appropriate directories."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save detailed analysis
    findings_file = FINDINGS_DIR / f"ml_analysis_{timestamp}.json"
    with open(findings_file, "w") as f:
        json.dump({
            "analysis": analysis,
            "detailed_results": results,
        }, f, indent=2, default=str)
    logger.info(f"Saved findings to {findings_file}")

    # Handle empty results
    if "error" in analysis:
        logger.warning(f"No models trained: {analysis['error']}")
        return findings_file

    # Save learning to learnings directory
    learning = {
        "pattern": "ml_pipeline_run",
        "timestamp": datetime.now().isoformat(),
        "what_happened": f"Trained {analysis.get('total_models_trained', 0)} ML models across targets",
        "what_learned": [],
        "how_changes_approach": [],
        "tags": ["ml", "training", "validation"],
    }

    # Add insights
    if analysis.get("significance_rate", 0) > 0:
        learning["what_learned"].append(
            f"{analysis['significance_rate']:.1%} of models were statistically significant (p < 0.05)"
        )

    if analysis.get("top_features"):
        top_3 = [f["feature"] for f in analysis["top_features"][:3]]
        learning["what_learned"].append(f"Top features: {', '.join(top_3)}")

    for rec in analysis.get("recommendations", []):
        learning["how_changes_approach"].append(rec)

    # Append to monthly learnings file
    month = datetime.now().strftime("%Y-%m")
    learnings_file = LEARNINGS_DIR / f"{month}.json"

    try:
        if learnings_file.exists():
            with open(learnings_file, "r") as f:
                learnings = json.load(f)
        else:
            learnings = []

        # Handle both list and dict formats
        if isinstance(learnings, dict):
            if "learnings" in learnings:
                learnings["learnings"].append(learning)
            else:
                learnings = [learning]
        else:
            learnings.append(learning)

        with open(learnings_file, "w") as f:
            json.dump(learnings, f, indent=2)
        logger.info(f"Added learning to {learnings_file}")
    except Exception as e:
        logger.warning(f"Failed to save learning: {e}")

    return findings_file


def print_summary(analysis: dict):
    """Print summary of findings."""

    print("\n" + "="*70)
    print("ML PIPELINE EXECUTION SUMMARY")
    print("="*70)

    print(f"\nTotal models trained: {analysis['total_models_trained']}")
    print(f"Significant models: {analysis['significant_models']}")
    print(f"Significance rate: {analysis['significance_rate']:.1%}")

    print("\n--- By Target ---")
    for target, stats in analysis.get("by_target", {}).items():
        print(f"\n{target}:")
        print(f"  Best score: {stats['best_score']:.4f} ({stats['best_model']})")
        print(f"  Significant: {stats['n_significant']}/{stats['n_models']}")

    print("\n--- By Model Type ---")
    for model, stats in analysis.get("by_model", {}).items():
        print(f"\n{model}:")
        print(f"  Avg score: {stats['avg_score']:.4f}")
        print(f"  Significance rate: {stats['significance_rate']:.1%}")

    print("\n--- Top Features ---")
    for i, feat in enumerate(analysis.get("top_features", [])[:10], 1):
        print(f"  {i}. {feat['feature']} (count={feat['count']}, importance={feat['avg_importance']:.4f})")

    print("\n--- Recommendations ---")
    for rec in analysis.get("recommendations", []):
        print(f"  - {rec}")

    print("\n" + "="*70)


async def main(quick_mode: bool = False):
    """Main execution."""

    logger.info("Starting ML Pipeline Execution")
    logger.info(f"Mode: {'Quick' if quick_mode else 'Full'}")

    # Select symbols based on mode
    if quick_mode:
        symbols = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]
        targets = ["direction_5d"]
        models = ["xgboost", "lightgbm"]
    else:
        # Full mode - use multiple universes
        symbols = list(set(
            UNIVERSE_CONFIGS["mega_cap"]["symbols"] +
            UNIVERSE_CONFIGS["major_etfs"]["symbols"]
        ))
        targets = ["direction_5d", "direction_1d", "return_5d"]
        models = ["xgboost", "lightgbm", "random_forest"]

    logger.info(f"Symbols: {symbols}")
    logger.info(f"Targets: {targets}")
    logger.info(f"Models: {models}")

    # Step 1: Load price data
    price_data = await load_price_data(symbols)

    if not price_data:
        logger.error("No price data loaded. Exiting.")
        return

    # Step 2: Compute features
    features = await compute_features(price_data)

    if not features:
        logger.error("No features computed. Exiting.")
        return

    # Step 3: Train models
    results = await train_models(
        price_data=price_data,
        features_by_symbol=features,
        targets=targets,
        models=models,
    )

    # Step 4: Analyze and document
    analysis = analyze_results(results)

    # Step 5: Save findings
    findings_file = save_findings(analysis, results)

    # Step 6: Print summary
    print_summary(analysis)

    logger.info(f"\nFindings saved to: {findings_file}")
    logger.info("ML Pipeline execution complete!")

    return analysis


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run ML Pipeline")
    parser.add_argument("--quick", action="store_true", help="Quick mode with fewer symbols")
    args = parser.parse_args()

    asyncio.run(main(quick_mode=args.quick))
