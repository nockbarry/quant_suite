"""Deep Learning Trading Strategies.

PRIORITY: P3 - DEFERRED
STATUS: Placeholder - models not trained, requires GPU and PyTorch
TODO: Implement proper deep learning pipeline when prioritized

Implements neural network-based strategies:
- LSTM: Long Short-Term Memory networks for sequence modeling
- Transformer: Attention-based architecture for long-range dependencies
- CNN: Convolutional networks for pattern recognition

Requires PyTorch: pip install torch

Requirements before production use:
1. GPU resources for training
2. Large historical dataset (5+ years)
3. Proper train/validation/test splits with purging
4. MCPT validation (p < 0.05)
5. Paper trade for 20+ days
6. Human approval via promotion pipeline
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from ...core import Direction, Signal, SignalType, Symbol, Timeframe
from ...data.features import FeatureEngine
from ..base import MLStrategy


class ModelArchitecture(str, Enum):
    """Available deep learning architectures."""

    LSTM = "lstm"
    GRU = "gru"
    TRANSFORMER = "transformer"
    CNN = "cnn"
    CNN_LSTM = "cnn_lstm"


@dataclass
class DeepLearningConfig:
    """Configuration for deep learning models."""

    # Architecture
    architecture: ModelArchitecture = ModelArchitecture.LSTM
    sequence_length: int = 60  # Lookback window
    hidden_size: int = 128
    num_layers: int = 2
    dropout: float = 0.2

    # Training
    batch_size: int = 32
    epochs: int = 100
    learning_rate: float = 0.001
    early_stopping_patience: int = 10
    weight_decay: float = 1e-5

    # Target
    target_type: str = "binary"  # binary, ternary, regression
    horizon: int = 5
    threshold: float = 0.0

    # Additional architecture-specific
    num_heads: int = 4  # For Transformer
    kernel_sizes: list[int] = field(default_factory=lambda: [3, 5, 7])  # For CNN
    n_filters: int = 64  # For CNN


class DeepLearningStrategy(MLStrategy, ABC):
    """
    Base class for deep learning trading strategies.

    Provides common functionality for neural network models:
    - Sequence data preparation
    - Model training with early stopping
    - GPU acceleration if available
    - Model checkpointing
    """

    name: str = "deep_learning"
    description: str = "Deep learning trading strategy"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        config: DeepLearningConfig | None = None,
        model: Any = None,
        **params: Any,
    ):
        """
        Initialize deep learning strategy.

        Args:
            universe: List of symbols to trade
            timeframe: Trading timeframe
            config: Deep learning configuration
            model: Pre-trained model (optional)
            **params: Additional parameters
        """
        super().__init__(universe, timeframe, model=model, **params)
        self.config = config or DeepLearningConfig()
        self._feature_engine = FeatureEngine()
        self.feature_columns: list[str] = []
        self.scaler = None
        self.device = None

        # Signal generation parameters
        self.signal_threshold = params.get("signal_threshold", 0.55)

    def _check_torch(self):
        """Check if PyTorch is available and set device."""
        try:
            import torch
            self.device = torch.device(
                "cuda" if torch.cuda.is_available() else "cpu"
            )
            return torch
        except ImportError:
            raise ImportError("PyTorch not installed. Run: pip install torch")

    def get_required_history(self) -> int:
        """Get required historical bars."""
        # Need enough for features + sequence length
        return self.config.sequence_length + 252

    def prepare_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare features for deep learning model.

        Args:
            data: Raw OHLCV data

        Returns:
            DataFrame with computed features
        """
        df = data.copy()

        # Add standard features
        df = self._feature_engine.add_returns(df, periods=[1, 5, 10, 21])
        df = self._feature_engine.add_volatility(df, windows=[5, 10, 21])
        df = self._feature_engine.add_moving_averages(df, windows=[5, 10, 20, 50])
        df = self._feature_engine.add_momentum_indicators(df)

        # Relative price features
        for ma in [5, 10, 20, 50]:
            if f"sma_{ma}" in df.columns:
                df[f"price_vs_sma_{ma}"] = df["close"] / df[f"sma_{ma}"] - 1

        # Exclude OHLCV
        exclude = {"open", "high", "low", "close", "volume", "adj_close"}
        feature_cols = [c for c in df.columns if c.lower() not in exclude]

        if not self.feature_columns:
            self.feature_columns = feature_cols

        features = df[feature_cols]

        # Handle NaN
        features = features.ffill().bfill()

        # Scale features
        if self.scaler is not None:
            try:
                scaled = self.scaler.transform(features)
                features = pd.DataFrame(
                    scaled, index=features.index, columns=features.columns
                )
            except Exception:
                pass

        return features

    def _prepare_sequences(
        self,
        features: pd.DataFrame,
        labels: pd.Series | None = None,
    ) -> tuple[np.ndarray, np.ndarray | None]:
        """
        Prepare sequences for RNN/CNN input.

        Args:
            features: Feature DataFrame
            labels: Optional labels for training

        Returns:
            Tuple of (sequences, labels) where sequences has shape
            (n_samples, sequence_length, n_features)
        """
        seq_len = self.config.sequence_length
        n_samples = len(features) - seq_len

        if n_samples <= 0:
            raise ValueError(
                f"Not enough data: {len(features)} < {seq_len}"
            )

        # Create sequences
        X = np.zeros((n_samples, seq_len, len(self.feature_columns)))

        for i in range(n_samples):
            X[i] = features.iloc[i:i + seq_len].values

        # Prepare labels if provided
        y = None
        if labels is not None:
            # Labels correspond to the next bar after each sequence
            y = labels.iloc[seq_len:].values

        return X, y

    def _prepare_labels(self, data: pd.DataFrame) -> pd.Series:
        """Prepare target labels."""
        return self._feature_engine.create_labels(
            data,
            horizon=self.config.horizon,
            method=self.config.target_type,
            threshold=self.config.threshold,
        )

    def _fit_scaler(self, features: pd.DataFrame) -> None:
        """Fit feature scaler."""
        try:
            from sklearn.preprocessing import RobustScaler
            self.scaler = RobustScaler()
            self.scaler.fit(features)
        except ImportError:
            self.scaler = None

    @abstractmethod
    def _build_model(self, n_features: int) -> Any:
        """Build the neural network model."""
        ...

    def predict(self, features: pd.DataFrame) -> pd.Series:
        """
        Generate predictions from features.

        Args:
            features: Feature DataFrame

        Returns:
            Series with predictions
        """
        torch = self._check_torch()

        if self.model is None:
            raise ValueError("Model not trained")

        # Prepare sequences
        X, _ = self._prepare_sequences(features)

        # Convert to tensor
        X_tensor = torch.FloatTensor(X).to(self.device)

        # Predict
        self.model.eval()
        with torch.no_grad():
            outputs = self.model(X_tensor)

            if self.config.target_type == "regression":
                predictions = outputs.squeeze().cpu().numpy()
            else:
                # Classification: get probabilities
                probs = torch.softmax(outputs, dim=1)
                if self.config.target_type == "binary":
                    predictions = probs[:, 1].cpu().numpy()
                else:
                    # Ternary: P(up) - P(down)
                    predictions = (probs[:, 2] - probs[:, 0]).cpu().numpy()

        # Align index (predictions start after sequence_length)
        pred_index = features.index[self.config.sequence_length:]

        return pd.Series(predictions, index=pred_index)

    def generate_signals(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        timestamp: datetime | None = None,
    ) -> list[Signal]:
        """
        Generate trading signals from market data.

        Args:
            data: OHLCV data
            timestamp: Current timestamp

        Returns:
            List of trading signals
        """
        signals = []
        timestamp = timestamp or datetime.now()

        if isinstance(data, pd.DataFrame):
            data_dict = {self.universe[0]: data}
        else:
            data_dict = data

        for symbol, df in data_dict.items():
            if symbol not in self.universe:
                continue

            if not self.validate_data(df):
                continue

            try:
                features = self.prepare_features(df)

                if len(features) < self.config.sequence_length + 1:
                    continue

                predictions = self.predict(features)
                latest_pred = predictions.iloc[-1]

                signal = self._prediction_to_signal(symbol, latest_pred, timestamp)
                if signal is not None:
                    signals.append(signal)

            except Exception:
                continue

        return signals

    def _prediction_to_signal(
        self,
        symbol: Symbol,
        prediction: float,
        timestamp: datetime,
    ) -> Signal | None:
        """Convert model prediction to trading signal."""

        if self.config.target_type == "regression":
            if abs(prediction) < self.config.threshold:
                return None

            direction = Direction.LONG if prediction > 0 else Direction.SHORT
            strength = min(abs(prediction) * 10, 1.0)
            confidence = min(abs(prediction) * 5, 1.0)
        else:
            if self.config.target_type == "binary":
                if prediction > self.signal_threshold:
                    direction = Direction.LONG
                    strength = (prediction - 0.5) * 2
                    confidence = prediction
                elif prediction < (1 - self.signal_threshold):
                    direction = Direction.SHORT
                    strength = (0.5 - prediction) * 2
                    confidence = 1 - prediction
                else:
                    return None
            else:
                if prediction > self.signal_threshold - 0.5:
                    direction = Direction.LONG
                    strength = min(prediction, 1.0)
                    confidence = (prediction + 1) / 2
                elif prediction < -(self.signal_threshold - 0.5):
                    direction = Direction.SHORT
                    strength = max(prediction, -1.0)
                    confidence = (-prediction + 1) / 2
                else:
                    return None

        signal_type = (
            SignalType.ENTRY_LONG if direction == Direction.LONG
            else SignalType.ENTRY_SHORT
        )

        return self.create_signal(
            symbol=symbol,
            direction=direction,
            strength=strength,
            confidence=confidence,
            timestamp=timestamp,
            signal_type=signal_type,
            metadata={
                "model": self.name,
                "architecture": self.config.architecture.value,
                "prediction": float(prediction),
            }
        )

    def save_model(self, path: str) -> None:
        """Save trained model."""
        torch = self._check_torch()

        if self.model is None:
            raise ValueError("No model to save")

        torch.save({
            "model_state_dict": self.model.state_dict(),
            "config": self.config,
            "feature_columns": self.feature_columns,
            "scaler": self.scaler,
        }, path)

    def load_model(self, path: str) -> None:
        """Load trained model."""
        torch = self._check_torch()

        checkpoint = torch.load(path, map_location=self.device)

        self.config = checkpoint.get("config", self.config)
        self.feature_columns = checkpoint.get("feature_columns", [])
        self.scaler = checkpoint.get("scaler")

        # Rebuild and load model
        self.model = self._build_model(len(self.feature_columns))
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.to(self.device)
        self.model.eval()
        self._is_trained = True


class LSTMStrategy(DeepLearningStrategy):
    """
    LSTM-based trading strategy.

    Long Short-Term Memory networks are effective for:
    - Capturing long-range temporal dependencies
    - Learning from sequential patterns
    - Handling variable-length sequences
    """

    name: str = "lstm_strategy"
    description: str = "Trading strategy using LSTM neural network"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        config: DeepLearningConfig | None = None,
        model: Any = None,
        **params: Any,
    ):
        config = config or DeepLearningConfig(architecture=ModelArchitecture.LSTM)
        super().__init__(universe, timeframe, config=config, model=model, **params)

    def _build_model(self, n_features: int) -> Any:
        """Build LSTM model."""
        torch = self._check_torch()
        import torch.nn as nn

        class LSTMModel(nn.Module):
            def __init__(
                self,
                input_size: int,
                hidden_size: int,
                num_layers: int,
                output_size: int,
                dropout: float,
            ):
                super().__init__()
                self.lstm = nn.LSTM(
                    input_size=input_size,
                    hidden_size=hidden_size,
                    num_layers=num_layers,
                    batch_first=True,
                    dropout=dropout if num_layers > 1 else 0,
                    bidirectional=False,
                )
                self.dropout = nn.Dropout(dropout)
                self.fc = nn.Linear(hidden_size, output_size)

            def forward(self, x):
                lstm_out, _ = self.lstm(x)
                # Take last output
                last_out = lstm_out[:, -1, :]
                out = self.dropout(last_out)
                return self.fc(out)

        # Output size based on target type
        if self.config.target_type == "regression":
            output_size = 1
        elif self.config.target_type == "binary":
            output_size = 2
        else:
            output_size = 3

        model = LSTMModel(
            input_size=n_features,
            hidden_size=self.config.hidden_size,
            num_layers=self.config.num_layers,
            output_size=output_size,
            dropout=self.config.dropout,
        )

        return model.to(self.device)

    def train(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        validation_split: float = 0.2,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Train LSTM model.

        Args:
            data: Training data
            validation_split: Fraction for validation
            **kwargs: Additional parameters

        Returns:
            Training metrics
        """
        torch = self._check_torch()
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        # Combine data
        if isinstance(data, dict):
            combined = pd.concat(data.values(), keys=data.keys())
            combined = combined.reset_index(level=0, drop=True)
        else:
            combined = data.copy()

        # Prepare features and labels
        features = self.prepare_features(combined)
        labels = self._prepare_labels(combined)

        # Fit scaler
        self._fit_scaler(features)
        if self.scaler is not None:
            features = pd.DataFrame(
                self.scaler.transform(features),
                index=features.index,
                columns=features.columns
            )

        # Prepare sequences
        X, y = self._prepare_sequences(features, labels)

        # Remove NaN labels
        valid_mask = ~np.isnan(y)
        X = X[valid_mask]
        y = y[valid_mask]

        # Train/validation split (keeping temporal order)
        split_idx = int(len(X) * (1 - validation_split))
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]

        # Convert to tensors
        X_train_t = torch.FloatTensor(X_train)
        y_train_t = torch.LongTensor(y_train) if self.config.target_type != "regression" else torch.FloatTensor(y_train)
        X_val_t = torch.FloatTensor(X_val)
        y_val_t = torch.LongTensor(y_val) if self.config.target_type != "regression" else torch.FloatTensor(y_val)

        # Create data loaders
        train_dataset = TensorDataset(X_train_t, y_train_t)
        val_dataset = TensorDataset(X_val_t, y_val_t)

        train_loader = DataLoader(
            train_dataset,
            batch_size=self.config.batch_size,
            shuffle=True
        )
        val_loader = DataLoader(
            val_dataset,
            batch_size=self.config.batch_size,
            shuffle=False
        )

        # Build model
        self.model = self._build_model(len(self.feature_columns))

        # Loss and optimizer
        if self.config.target_type == "regression":
            criterion = nn.MSELoss()
        else:
            criterion = nn.CrossEntropyLoss()

        optimizer = torch.optim.Adam(
            self.model.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )

        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode="min", factor=0.5, patience=5
        )

        # Training loop
        best_val_loss = float("inf")
        patience_counter = 0
        history = {"train_loss": [], "val_loss": []}

        for epoch in range(self.config.epochs):
            # Train
            self.model.train()
            train_loss = 0
            for X_batch, y_batch in train_loader:
                X_batch = X_batch.to(self.device)
                y_batch = y_batch.to(self.device)

                optimizer.zero_grad()
                outputs = self.model(X_batch)

                if self.config.target_type == "regression":
                    loss = criterion(outputs.squeeze(), y_batch)
                else:
                    loss = criterion(outputs, y_batch)

                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()
                train_loss += loss.item()

            train_loss /= len(train_loader)

            # Validate
            self.model.eval()
            val_loss = 0
            with torch.no_grad():
                for X_batch, y_batch in val_loader:
                    X_batch = X_batch.to(self.device)
                    y_batch = y_batch.to(self.device)

                    outputs = self.model(X_batch)
                    if self.config.target_type == "regression":
                        loss = criterion(outputs.squeeze(), y_batch)
                    else:
                        loss = criterion(outputs, y_batch)
                    val_loss += loss.item()

            val_loss /= len(val_loader)

            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_loss)

            scheduler.step(val_loss)

            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                # Save best model state
                best_state = self.model.state_dict().copy()
            else:
                patience_counter += 1
                if patience_counter >= self.config.early_stopping_patience:
                    break

        # Restore best model
        self.model.load_state_dict(best_state)
        self._is_trained = True

        # Compute final metrics
        metrics = {
            "final_train_loss": history["train_loss"][-1],
            "final_val_loss": history["val_loss"][-1],
            "best_val_loss": best_val_loss,
            "epochs_trained": len(history["train_loss"]),
            "n_train_samples": len(X_train),
            "n_val_samples": len(X_val),
            "n_features": len(self.feature_columns),
        }

        return metrics


class TransformerStrategy(DeepLearningStrategy):
    """
    Transformer-based trading strategy.

    Attention-based architecture effective for:
    - Capturing long-range dependencies without recurrence
    - Parallel computation
    - Interpretable attention weights
    """

    name: str = "transformer_strategy"
    description: str = "Trading strategy using Transformer architecture"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        config: DeepLearningConfig | None = None,
        model: Any = None,
        **params: Any,
    ):
        config = config or DeepLearningConfig(architecture=ModelArchitecture.TRANSFORMER)
        super().__init__(universe, timeframe, config=config, model=model, **params)

    def _build_model(self, n_features: int) -> Any:
        """Build Transformer model."""
        torch = self._check_torch()
        import torch.nn as nn
        import math

        class PositionalEncoding(nn.Module):
            def __init__(self, d_model: int, max_len: int = 500, dropout: float = 0.1):
                super().__init__()
                self.dropout = nn.Dropout(p=dropout)

                pe = torch.zeros(max_len, d_model)
                position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
                div_term = torch.exp(
                    torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
                )
                pe[:, 0::2] = torch.sin(position * div_term)
                pe[:, 1::2] = torch.cos(position * div_term)
                pe = pe.unsqueeze(0)
                self.register_buffer("pe", pe)

            def forward(self, x):
                x = x + self.pe[:, :x.size(1), :]
                return self.dropout(x)

        class TransformerModel(nn.Module):
            def __init__(
                self,
                input_size: int,
                d_model: int,
                num_heads: int,
                num_layers: int,
                output_size: int,
                dropout: float,
                seq_len: int,
            ):
                super().__init__()
                self.input_projection = nn.Linear(input_size, d_model)
                self.pos_encoder = PositionalEncoding(d_model, seq_len, dropout)

                encoder_layer = nn.TransformerEncoderLayer(
                    d_model=d_model,
                    nhead=num_heads,
                    dim_feedforward=d_model * 4,
                    dropout=dropout,
                    batch_first=True,
                )
                self.transformer = nn.TransformerEncoder(
                    encoder_layer, num_layers=num_layers
                )

                self.fc = nn.Linear(d_model, output_size)
                self.dropout = nn.Dropout(dropout)

            def forward(self, x):
                x = self.input_projection(x)
                x = self.pos_encoder(x)
                x = self.transformer(x)
                # Use CLS token equivalent (mean pooling)
                x = x.mean(dim=1)
                x = self.dropout(x)
                return self.fc(x)

        # Output size
        if self.config.target_type == "regression":
            output_size = 1
        elif self.config.target_type == "binary":
            output_size = 2
        else:
            output_size = 3

        model = TransformerModel(
            input_size=n_features,
            d_model=self.config.hidden_size,
            num_heads=self.config.num_heads,
            num_layers=self.config.num_layers,
            output_size=output_size,
            dropout=self.config.dropout,
            seq_len=self.config.sequence_length,
        )

        return model.to(self.device)

    def train(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        validation_split: float = 0.2,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Train Transformer model."""
        torch = self._check_torch()
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        # Combine data
        if isinstance(data, dict):
            combined = pd.concat(data.values(), keys=data.keys())
            combined = combined.reset_index(level=0, drop=True)
        else:
            combined = data.copy()

        # Prepare features and labels
        features = self.prepare_features(combined)
        labels = self._prepare_labels(combined)

        # Fit scaler
        self._fit_scaler(features)
        if self.scaler is not None:
            features = pd.DataFrame(
                self.scaler.transform(features),
                index=features.index,
                columns=features.columns
            )

        # Prepare sequences
        X, y = self._prepare_sequences(features, labels)

        # Remove NaN labels
        valid_mask = ~np.isnan(y)
        X = X[valid_mask]
        y = y[valid_mask]

        # Train/val split
        split_idx = int(len(X) * (1 - validation_split))
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]

        # Convert to tensors
        X_train_t = torch.FloatTensor(X_train)
        y_train_t = torch.LongTensor(y_train) if self.config.target_type != "regression" else torch.FloatTensor(y_train)
        X_val_t = torch.FloatTensor(X_val)
        y_val_t = torch.LongTensor(y_val) if self.config.target_type != "regression" else torch.FloatTensor(y_val)

        train_dataset = TensorDataset(X_train_t, y_train_t)
        val_dataset = TensorDataset(X_val_t, y_val_t)

        train_loader = DataLoader(train_dataset, batch_size=self.config.batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=self.config.batch_size, shuffle=False)

        # Build model
        self.model = self._build_model(len(self.feature_columns))

        # Loss and optimizer
        if self.config.target_type == "regression":
            criterion = nn.MSELoss()
        else:
            criterion = nn.CrossEntropyLoss()

        optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )

        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=self.config.epochs
        )

        # Training loop
        best_val_loss = float("inf")
        patience_counter = 0
        history = {"train_loss": [], "val_loss": []}

        for epoch in range(self.config.epochs):
            # Train
            self.model.train()
            train_loss = 0
            for X_batch, y_batch in train_loader:
                X_batch = X_batch.to(self.device)
                y_batch = y_batch.to(self.device)

                optimizer.zero_grad()
                outputs = self.model(X_batch)

                if self.config.target_type == "regression":
                    loss = criterion(outputs.squeeze(), y_batch)
                else:
                    loss = criterion(outputs, y_batch)

                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()
                train_loss += loss.item()

            train_loss /= len(train_loader)
            scheduler.step()

            # Validate
            self.model.eval()
            val_loss = 0
            with torch.no_grad():
                for X_batch, y_batch in val_loader:
                    X_batch = X_batch.to(self.device)
                    y_batch = y_batch.to(self.device)

                    outputs = self.model(X_batch)
                    if self.config.target_type == "regression":
                        loss = criterion(outputs.squeeze(), y_batch)
                    else:
                        loss = criterion(outputs, y_batch)
                    val_loss += loss.item()

            val_loss /= len(val_loader)

            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_loss)

            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                best_state = self.model.state_dict().copy()
            else:
                patience_counter += 1
                if patience_counter >= self.config.early_stopping_patience:
                    break

        self.model.load_state_dict(best_state)
        self._is_trained = True

        return {
            "final_train_loss": history["train_loss"][-1],
            "final_val_loss": history["val_loss"][-1],
            "best_val_loss": best_val_loss,
            "epochs_trained": len(history["train_loss"]),
            "n_train_samples": len(X_train),
            "n_val_samples": len(X_val),
        }


class CNNStrategy(DeepLearningStrategy):
    """
    CNN-based trading strategy.

    1D Convolutional neural networks effective for:
    - Local pattern recognition
    - Multi-scale feature extraction
    - Translation invariance
    """

    name: str = "cnn_strategy"
    description: str = "Trading strategy using 1D CNN"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        config: DeepLearningConfig | None = None,
        model: Any = None,
        **params: Any,
    ):
        config = config or DeepLearningConfig(architecture=ModelArchitecture.CNN)
        super().__init__(universe, timeframe, config=config, model=model, **params)

    def _build_model(self, n_features: int) -> Any:
        """Build 1D CNN model."""
        torch = self._check_torch()
        import torch.nn as nn

        class CNN1DModel(nn.Module):
            def __init__(
                self,
                input_channels: int,
                n_filters: int,
                kernel_sizes: list[int],
                output_size: int,
                dropout: float,
                seq_len: int,
            ):
                super().__init__()

                # Multi-scale convolutions
                self.convs = nn.ModuleList([
                    nn.Sequential(
                        nn.Conv1d(input_channels, n_filters, kernel_size=k, padding=k//2),
                        nn.BatchNorm1d(n_filters),
                        nn.ReLU(),
                        nn.MaxPool1d(2),
                    )
                    for k in kernel_sizes
                ])

                # Second conv layer
                self.conv2 = nn.Sequential(
                    nn.Conv1d(n_filters * len(kernel_sizes), n_filters * 2, kernel_size=3, padding=1),
                    nn.BatchNorm1d(n_filters * 2),
                    nn.ReLU(),
                    nn.AdaptiveAvgPool1d(1),
                )

                self.dropout = nn.Dropout(dropout)
                self.fc = nn.Linear(n_filters * 2, output_size)

            def forward(self, x):
                # x: (batch, seq_len, features) -> (batch, features, seq_len)
                x = x.transpose(1, 2)

                # Multi-scale convolutions
                conv_outputs = [conv(x) for conv in self.convs]
                x = torch.cat(conv_outputs, dim=1)

                # Second conv
                x = self.conv2(x)
                x = x.squeeze(-1)

                x = self.dropout(x)
                return self.fc(x)

        # Output size
        if self.config.target_type == "regression":
            output_size = 1
        elif self.config.target_type == "binary":
            output_size = 2
        else:
            output_size = 3

        model = CNN1DModel(
            input_channels=n_features,
            n_filters=self.config.n_filters,
            kernel_sizes=self.config.kernel_sizes,
            output_size=output_size,
            dropout=self.config.dropout,
            seq_len=self.config.sequence_length,
        )

        return model.to(self.device)

    def train(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        validation_split: float = 0.2,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Train CNN model."""
        torch = self._check_torch()
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        # Combine data
        if isinstance(data, dict):
            combined = pd.concat(data.values(), keys=data.keys())
            combined = combined.reset_index(level=0, drop=True)
        else:
            combined = data.copy()

        # Prepare features and labels
        features = self.prepare_features(combined)
        labels = self._prepare_labels(combined)

        # Fit scaler
        self._fit_scaler(features)
        if self.scaler is not None:
            features = pd.DataFrame(
                self.scaler.transform(features),
                index=features.index,
                columns=features.columns
            )

        # Prepare sequences
        X, y = self._prepare_sequences(features, labels)

        # Remove NaN labels
        valid_mask = ~np.isnan(y)
        X = X[valid_mask]
        y = y[valid_mask]

        # Train/val split
        split_idx = int(len(X) * (1 - validation_split))
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]

        # Convert to tensors
        X_train_t = torch.FloatTensor(X_train)
        y_train_t = torch.LongTensor(y_train) if self.config.target_type != "regression" else torch.FloatTensor(y_train)
        X_val_t = torch.FloatTensor(X_val)
        y_val_t = torch.LongTensor(y_val) if self.config.target_type != "regression" else torch.FloatTensor(y_val)

        train_dataset = TensorDataset(X_train_t, y_train_t)
        val_dataset = TensorDataset(X_val_t, y_val_t)

        train_loader = DataLoader(train_dataset, batch_size=self.config.batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=self.config.batch_size, shuffle=False)

        # Build model
        self.model = self._build_model(len(self.feature_columns))

        # Loss and optimizer
        if self.config.target_type == "regression":
            criterion = nn.MSELoss()
        else:
            criterion = nn.CrossEntropyLoss()

        optimizer = torch.optim.Adam(
            self.model.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )

        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode="min", factor=0.5, patience=5
        )

        # Training loop
        best_val_loss = float("inf")
        patience_counter = 0
        history = {"train_loss": [], "val_loss": []}

        for epoch in range(self.config.epochs):
            # Train
            self.model.train()
            train_loss = 0
            for X_batch, y_batch in train_loader:
                X_batch = X_batch.to(self.device)
                y_batch = y_batch.to(self.device)

                optimizer.zero_grad()
                outputs = self.model(X_batch)

                if self.config.target_type == "regression":
                    loss = criterion(outputs.squeeze(), y_batch)
                else:
                    loss = criterion(outputs, y_batch)

                loss.backward()
                optimizer.step()
                train_loss += loss.item()

            train_loss /= len(train_loader)

            # Validate
            self.model.eval()
            val_loss = 0
            with torch.no_grad():
                for X_batch, y_batch in val_loader:
                    X_batch = X_batch.to(self.device)
                    y_batch = y_batch.to(self.device)

                    outputs = self.model(X_batch)
                    if self.config.target_type == "regression":
                        loss = criterion(outputs.squeeze(), y_batch)
                    else:
                        loss = criterion(outputs, y_batch)
                    val_loss += loss.item()

            val_loss /= len(val_loader)

            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_loss)

            scheduler.step(val_loss)

            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                best_state = self.model.state_dict().copy()
            else:
                patience_counter += 1
                if patience_counter >= self.config.early_stopping_patience:
                    break

        self.model.load_state_dict(best_state)
        self._is_trained = True

        return {
            "final_train_loss": history["train_loss"][-1],
            "final_val_loss": history["val_loss"][-1],
            "best_val_loss": best_val_loss,
            "epochs_trained": len(history["train_loss"]),
            "n_train_samples": len(X_train),
            "n_val_samples": len(X_val),
        }


class CNNLSTMStrategy(DeepLearningStrategy):
    """
    CNN-LSTM hybrid strategy.

    Combines CNN for local pattern extraction with LSTM for
    sequential modeling. Effective for capturing both local
    patterns and long-range dependencies.
    """

    name: str = "cnn_lstm_strategy"
    description: str = "Trading strategy using CNN-LSTM hybrid"

    def __init__(
        self,
        universe: list[Symbol],
        timeframe: Timeframe = Timeframe.DAILY,
        config: DeepLearningConfig | None = None,
        model: Any = None,
        **params: Any,
    ):
        config = config or DeepLearningConfig(architecture=ModelArchitecture.CNN_LSTM)
        super().__init__(universe, timeframe, config=config, model=model, **params)

    def _build_model(self, n_features: int) -> Any:
        """Build CNN-LSTM hybrid model."""
        torch = self._check_torch()
        import torch.nn as nn

        class CNNLSTMModel(nn.Module):
            def __init__(
                self,
                input_size: int,
                n_filters: int,
                hidden_size: int,
                num_layers: int,
                output_size: int,
                dropout: float,
            ):
                super().__init__()

                # CNN for local feature extraction
                self.conv1 = nn.Sequential(
                    nn.Conv1d(input_size, n_filters, kernel_size=3, padding=1),
                    nn.BatchNorm1d(n_filters),
                    nn.ReLU(),
                )
                self.conv2 = nn.Sequential(
                    nn.Conv1d(n_filters, n_filters * 2, kernel_size=3, padding=1),
                    nn.BatchNorm1d(n_filters * 2),
                    nn.ReLU(),
                )

                # LSTM for sequential modeling
                self.lstm = nn.LSTM(
                    input_size=n_filters * 2,
                    hidden_size=hidden_size,
                    num_layers=num_layers,
                    batch_first=True,
                    dropout=dropout if num_layers > 1 else 0,
                )

                self.dropout = nn.Dropout(dropout)
                self.fc = nn.Linear(hidden_size, output_size)

            def forward(self, x):
                # x: (batch, seq, features) -> (batch, features, seq)
                x = x.transpose(1, 2)

                # CNN
                x = self.conv1(x)
                x = self.conv2(x)

                # Back to (batch, seq, features)
                x = x.transpose(1, 2)

                # LSTM
                lstm_out, _ = self.lstm(x)
                out = lstm_out[:, -1, :]

                out = self.dropout(out)
                return self.fc(out)

        # Output size
        if self.config.target_type == "regression":
            output_size = 1
        elif self.config.target_type == "binary":
            output_size = 2
        else:
            output_size = 3

        model = CNNLSTMModel(
            input_size=n_features,
            n_filters=self.config.n_filters,
            hidden_size=self.config.hidden_size,
            num_layers=self.config.num_layers,
            output_size=output_size,
            dropout=self.config.dropout,
        )

        return model.to(self.device)

    def train(
        self,
        data: pd.DataFrame | dict[Symbol, pd.DataFrame],
        validation_split: float = 0.2,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Train CNN-LSTM model."""
        # Implementation similar to LSTM/CNN train methods
        torch = self._check_torch()
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        if isinstance(data, dict):
            combined = pd.concat(data.values(), keys=data.keys())
            combined = combined.reset_index(level=0, drop=True)
        else:
            combined = data.copy()

        features = self.prepare_features(combined)
        labels = self._prepare_labels(combined)

        self._fit_scaler(features)
        if self.scaler is not None:
            features = pd.DataFrame(
                self.scaler.transform(features),
                index=features.index,
                columns=features.columns
            )

        X, y = self._prepare_sequences(features, labels)

        valid_mask = ~np.isnan(y)
        X = X[valid_mask]
        y = y[valid_mask]

        split_idx = int(len(X) * (1 - validation_split))
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]

        X_train_t = torch.FloatTensor(X_train)
        y_train_t = torch.LongTensor(y_train) if self.config.target_type != "regression" else torch.FloatTensor(y_train)
        X_val_t = torch.FloatTensor(X_val)
        y_val_t = torch.LongTensor(y_val) if self.config.target_type != "regression" else torch.FloatTensor(y_val)

        train_loader = DataLoader(TensorDataset(X_train_t, y_train_t), batch_size=self.config.batch_size, shuffle=True)
        val_loader = DataLoader(TensorDataset(X_val_t, y_val_t), batch_size=self.config.batch_size, shuffle=False)

        self.model = self._build_model(len(self.feature_columns))

        if self.config.target_type == "regression":
            criterion = nn.MSELoss()
        else:
            criterion = nn.CrossEntropyLoss()

        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.config.learning_rate, weight_decay=self.config.weight_decay)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=5)

        best_val_loss = float("inf")
        patience_counter = 0
        history = {"train_loss": [], "val_loss": []}

        for epoch in range(self.config.epochs):
            self.model.train()
            train_loss = 0
            for X_batch, y_batch in train_loader:
                X_batch = X_batch.to(self.device)
                y_batch = y_batch.to(self.device)

                optimizer.zero_grad()
                outputs = self.model(X_batch)

                if self.config.target_type == "regression":
                    loss = criterion(outputs.squeeze(), y_batch)
                else:
                    loss = criterion(outputs, y_batch)

                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                optimizer.step()
                train_loss += loss.item()

            train_loss /= len(train_loader)

            self.model.eval()
            val_loss = 0
            with torch.no_grad():
                for X_batch, y_batch in val_loader:
                    X_batch = X_batch.to(self.device)
                    y_batch = y_batch.to(self.device)
                    outputs = self.model(X_batch)
                    if self.config.target_type == "regression":
                        loss = criterion(outputs.squeeze(), y_batch)
                    else:
                        loss = criterion(outputs, y_batch)
                    val_loss += loss.item()

            val_loss /= len(val_loader)

            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_loss)
            scheduler.step(val_loss)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                best_state = self.model.state_dict().copy()
            else:
                patience_counter += 1
                if patience_counter >= self.config.early_stopping_patience:
                    break

        self.model.load_state_dict(best_state)
        self._is_trained = True

        return {
            "final_train_loss": history["train_loss"][-1],
            "final_val_loss": history["val_loss"][-1],
            "best_val_loss": best_val_loss,
            "epochs_trained": len(history["train_loss"]),
            "n_train_samples": len(X_train),
            "n_val_samples": len(X_val),
        }


# Factory function
def create_deep_learning_strategy(
    architecture: str | ModelArchitecture,
    universe: list[Symbol],
    config: DeepLearningConfig | None = None,
    **params: Any,
) -> DeepLearningStrategy:
    """
    Factory function to create deep learning strategies.

    Args:
        architecture: One of 'lstm', 'gru', 'transformer', 'cnn', 'cnn_lstm'
        universe: List of symbols
        config: Model configuration
        **params: Additional parameters

    Returns:
        Instantiated strategy
    """
    if isinstance(architecture, str):
        architecture = ModelArchitecture(architecture.lower())

    strategies = {
        ModelArchitecture.LSTM: LSTMStrategy,
        ModelArchitecture.GRU: LSTMStrategy,  # GRU uses same class, different config
        ModelArchitecture.TRANSFORMER: TransformerStrategy,
        ModelArchitecture.CNN: CNNStrategy,
        ModelArchitecture.CNN_LSTM: CNNLSTMStrategy,
    }

    if architecture not in strategies:
        raise ValueError(
            f"Unknown architecture: {architecture}. "
            f"Available: {[a.value for a in strategies.keys()]}"
        )

    return strategies[architecture](universe, config=config, **params)
