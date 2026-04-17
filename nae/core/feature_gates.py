"""
NAE Feature Gate System

Enforces Model A boundaries at the architecture level.
No code path can bypass these gates without the user explicitly
changing their configuration file.
"""

import copy
import yaml
from pathlib import Path
from typing import Any, Dict, Optional


_DEFAULT_CONFIG = {
    "nae": {
        "mode": "research_only",
        "execution_enabled": False,
    },
    "broker": {
        "name": None,
        "api_key": None,
        "api_secret": None,
        "sandbox": True,
    },
    "research": {
        "data_sources": ["yahoo_finance"],
        "assets": [],
    },
    "backtesting": {
        "default_period_days": 365,
        "output_format": "csv",
        "output_directory": "./reports",
    },
    "execution": {
        "require_confirmation": True,
        "max_order_size_usd": 1000.0,
        "paper_mode": True,
    },
    "logging": {
        "level": "INFO",
        "directory": "./logs",
    },
}


class FeatureGates:
    """
    Central enforcement layer for Model A compliance.

    Every module that touches execution, broker connections, or output
    generation checks these gates before proceeding.
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config_path = config_path or self._find_config()
        # Deep-copy the defaults so per-instance mutations (via _deep_merge)
        # cannot leak back into the module-level template. A shallow dict()
        # copy would share nested dicts and corrupt later FeatureGates()
        # instances — a real bug the singleton masked in normal usage but
        # that surfaces under tests or when multiple gates coexist.
        self._config: Dict[str, Any] = copy.deepcopy(_DEFAULT_CONFIG)
        if self._config_path and Path(self._config_path).exists():
            self._load()

    @staticmethod
    def _find_config() -> Optional[str]:
        candidates = [
            Path.cwd() / "config.yaml",
            Path.cwd() / "config.yml",
            Path.home() / ".nae" / "config.yaml",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        return None

    def _load(self) -> None:
        with open(self._config_path, "r") as f:
            user_cfg = yaml.safe_load(f) or {}
        self._deep_merge(self._config, user_cfg)

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                FeatureGates._deep_merge(base[k], v)
            else:
                base[k] = v

    def get(self, dotted_key: str, default: Any = None) -> Any:
        parts = dotted_key.split(".")
        node = self._config
        for p in parts:
            if isinstance(node, dict) and p in node:
                node = node[p]
            else:
                return default
        return node

    @property
    def config(self) -> Dict[str, Any]:
        # Deep copy so callers cannot mutate internal gate state by accident.
        return copy.deepcopy(self._config)

    # ── Gate checks ─────────────────────────────────────────────

    @property
    def execution_allowed(self) -> bool:
        return bool(self.get("nae.execution_enabled", False))

    @property
    def confirmation_required(self) -> bool:
        return bool(self.get("execution.require_confirmation", True))

    @property
    def paper_mode(self) -> bool:
        return bool(self.get("execution.paper_mode", True))

    @property
    def broker_configured(self) -> bool:
        return bool(self.get("broker.name")) and bool(self.get("broker.api_key"))

    @property
    def mode(self) -> str:
        return str(self.get("nae.mode", "research_only"))

    def require_execution(self) -> None:
        """Raise if execution is not explicitly enabled by the user."""
        if not self.execution_allowed:
            raise PermissionError(
                "Execution is disabled. Set 'nae.execution_enabled: true' "
                "in your config.yaml to enable trading. You accept full "
                "responsibility for all trades executed through NAE."
            )
        if not self.broker_configured:
            raise PermissionError(
                "No broker configured. Set 'broker.name' and 'broker.api_key' "
                "in your config.yaml before enabling execution."
            )

    def require_confirmation(self, action_description: str) -> bool:
        """Prompt user for Y/N confirmation. Returns True if confirmed."""
        if not self.confirmation_required:
            return True
        print(f"\n{'=' * 60}")
        print(f"  CONFIRMATION REQUIRED")
        print(f"  {action_description}")
        print(f"{'=' * 60}")
        response = input("  Type 'yes' to confirm: ").strip().lower()
        return response in ("yes", "y")


_gates: Optional[FeatureGates] = None


def get_gates(config_path: Optional[str] = None) -> FeatureGates:
    """Singleton accessor for the global feature gates."""
    global _gates
    if _gates is None:
        _gates = FeatureGates(config_path)
    return _gates


def reset_gates() -> None:
    """Reset the singleton (used in tests)."""
    global _gates
    _gates = None
