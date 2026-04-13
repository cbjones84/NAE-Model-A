"""
NAE System Monitor (derived from Casey architecture)

Monitors system health, resource usage, and service status.
Provides operational visibility without any trading intelligence.

Reports factual system state — no financial analysis or trading logic.
"""

import os
import time
import datetime
import logging
import json
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger("nae.monitor")


class SystemMonitor:
    """
    Monitors NAE platform health and resource usage.

    Capabilities:
    - CPU/memory usage monitoring
    - Service health checks (broker connection, data feeds)
    - Log aggregation and status reporting
    - Uptime tracking

    This monitor does NOT:
    - Provide trading intelligence
    - Monitor portfolio performance
    - Generate financial alerts
    - Make any trading decisions
    """

    def __init__(self, log_dir: str = "./logs"):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._start_time = datetime.datetime.now(datetime.timezone.utc)

    def system_status(self) -> Dict[str, Any]:
        """Return current system health status."""
        status: Dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "uptime_seconds": (
                datetime.datetime.now(datetime.timezone.utc) - self._start_time
            ).total_seconds(),
            "platform": "NAE Model A",
            "version": "1.0.0",
        }

        # System resources
        try:
            import psutil
            status["cpu_percent"] = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            status["memory_used_mb"] = round(mem.used / (1024 * 1024), 1)
            status["memory_total_mb"] = round(mem.total / (1024 * 1024), 1)
            status["memory_percent"] = mem.percent
            disk = psutil.disk_usage("/")
            status["disk_used_gb"] = round(disk.used / (1024 ** 3), 1)
            status["disk_total_gb"] = round(disk.total / (1024 ** 3), 1)
        except ImportError:
            status["resources"] = "psutil not installed — install for resource monitoring"

        # Check data directory
        data_dir = Path("./data")
        if data_dir.exists():
            status["data_files"] = len(list(data_dir.rglob("*")))
        else:
            status["data_files"] = 0

        # Check log directory
        if self._log_dir.exists():
            log_files = list(self._log_dir.glob("*.log")) + list(self._log_dir.glob("*.jsonl"))
            status["log_files"] = len(log_files)
            total_log_size = sum(f.stat().st_size for f in log_files)
            status["log_size_mb"] = round(total_log_size / (1024 * 1024), 2)
        else:
            status["log_files"] = 0

        return status

    def check_broker_connection(self) -> Dict[str, Any]:
        """Test connectivity to the configured broker."""
        from nae.core.feature_gates import get_gates
        gates = get_gates()

        result = {
            "broker": gates.get("broker.name", "not configured"),
            "connected": False,
            "sandbox": gates.get("broker.sandbox", True),
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        if not gates.broker_configured:
            result["message"] = "No broker configured in config.yaml"
            return result

        broker_name = gates.get("broker.name")
        try:
            if broker_name == "tradier":
                import requests
                sandbox = gates.get("broker.sandbox", True)
                base = "https://sandbox.tradier.com/v1" if sandbox else "https://api.tradier.com/v1"
                resp = requests.get(
                    f"{base}/user/profile",
                    headers={
                        "Authorization": f"Bearer {gates.get('broker.api_key')}",
                        "Accept": "application/json",
                    },
                    timeout=10,
                )
                result["connected"] = resp.status_code == 200
                result["status_code"] = resp.status_code
            elif broker_name == "alpaca":
                import requests
                sandbox = gates.get("broker.sandbox", True)
                base = "https://paper-api.alpaca.markets/v2" if sandbox else "https://api.alpaca.markets/v2"
                resp = requests.get(
                    f"{base}/account",
                    headers={
                        "APCA-API-KEY-ID": gates.get("broker.api_key", ""),
                        "APCA-API-SECRET-KEY": gates.get("broker.api_secret", ""),
                    },
                    timeout=10,
                )
                result["connected"] = resp.status_code == 200
                result["status_code"] = resp.status_code
            else:
                result["message"] = f"Broker '{broker_name}' not supported for health check"
        except Exception as e:
            result["error"] = str(e)

        return result

    def check_data_feeds(self) -> Dict[str, Any]:
        """Test availability of data sources."""
        result = {
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "sources": {},
        }

        # yfinance
        try:
            import yfinance as yf
            ticker = yf.Ticker("SPY")
            hist = ticker.history(period="1d")
            result["sources"]["yahoo_finance"] = {
                "available": not hist.empty,
                "last_price": float(hist["Close"].iloc[-1]) if not hist.empty else None,
            }
        except Exception as e:
            result["sources"]["yahoo_finance"] = {
                "available": False,
                "error": str(e),
            }

        return result

    def full_health_check(self) -> Dict[str, Any]:
        """Run all health checks and return combined status."""
        return {
            "system": self.system_status(),
            "broker": self.check_broker_connection(),
            "data_feeds": self.check_data_feeds(),
        }
