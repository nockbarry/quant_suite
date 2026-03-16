"""Instance-aware configuration for multi-Athena parallel operation.

Each Athena instance runs the same codebase but with isolated:
- QUANT_RESULTS_DIR (state, theses, decisions, learnings)
- Alpaca credentials (separate paper accounts)
- tmux session (separate terminal)
- cron block (separate scheduling)

Usage:
    from src.core.instance import instance_config

    creds_path = instance_config.credentials_path()
    tmux_name = instance_config.tmux_session_name()
"""

import os
from pathlib import Path


class InstanceConfig:
    """Instance-aware configuration singleton."""

    @staticmethod
    def instance_name() -> str:
        """Get current instance name. Defaults to 'default' for backward compatibility."""
        return os.environ.get("ATHENA_INSTANCE", "default")

    @staticmethod
    def is_multi_instance() -> bool:
        """Check if running in multi-instance mode."""
        return os.environ.get("ATHENA_INSTANCE", "default") != "default"

    @staticmethod
    def results_dir() -> Path:
        """Get instance-specific results directory."""
        return Path(os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results")))

    @staticmethod
    def credentials_path() -> Path:
        """Get instance-specific credentials file.

        For named instances, looks for config/credentials_<name>.yaml first.
        Falls back to config/credentials.yaml for default or if instance file missing.
        """
        instance = InstanceConfig.instance_name()
        project_dir = Path(__file__).parent.parent.parent
        if instance != "default":
            instance_creds = project_dir / "config" / f"credentials_{instance}.yaml"
            if instance_creds.exists():
                return instance_creds
        return project_dir / "config" / "credentials.yaml"

    @staticmethod
    def tmux_session_name() -> str:
        """Get instance-specific tmux session name."""
        instance = InstanceConfig.instance_name()
        return f"athena-{instance}" if instance != "default" else "athena-auto"

    @staticmethod
    def cron_marker() -> str:
        """Get instance-specific cron block marker."""
        instance = InstanceConfig.instance_name()
        if instance == "default":
            return "QUANT_SUITE_AUTO"
        return f"QUANT_SUITE_AUTO_{instance.upper()}"

    @staticmethod
    def all_instance_dirs() -> list[Path]:
        """Discover all instance result directories for meta-observer."""
        home = Path.home()
        dirs = []
        # Default instance
        default = home / "quant_results"
        if default.exists():
            dirs.append(default)
        # Named instances (quant_results_alpha, quant_results_beta, etc.)
        for p in sorted(home.glob("quant_results_*")):
            if p.is_dir() and (p / "live" / "state.json").exists():
                dirs.append(p)
        return dirs

    @staticmethod
    def instance_name_from_dir(results_dir: Path) -> str:
        """Extract instance name from a results directory path.

        ~/quant_results -> 'default'
        ~/quant_results_alpha -> 'alpha'
        """
        name = results_dir.name
        if name == "quant_results":
            return "default"
        if name.startswith("quant_results_"):
            return name[len("quant_results_"):]
        return name


# Global singleton
instance_config = InstanceConfig()
