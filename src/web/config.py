"""Web dashboard configuration."""

import os
from pathlib import Path

import yaml


class WebConfig:
    """Configuration loaded from config/web.yaml or environment."""

    def __init__(self):
        self.host = "0.0.0.0"
        self.port = 8000
        self.auth_token = ""
        self.debug = False
        self.results_dir = Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))
        self._load_yaml()

    def _load_yaml(self):
        config_path = Path(__file__).parents[2] / "config" / "web.yaml"
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text()) or {}
            self.host = data.get("host", self.host)
            self.port = data.get("port", self.port)
            self.auth_token = data.get("auth_token", self.auth_token)
            self.debug = data.get("debug", self.debug)

        # Environment overrides
        self.auth_token = os.environ.get("ATHENA_WEB_TOKEN", self.auth_token)
        self.port = int(os.environ.get("ATHENA_WEB_PORT", self.port))


web_config = WebConfig()
