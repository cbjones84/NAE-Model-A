#!/usr/bin/env python3
"""
NAE Model A — Automated Compliance Audit

Scans the codebase to detect accidental drift out of Model A territory.
Run before every release and in CI to catch issues early.

Checks:
1. Banned advisory language in user-facing code
2. No pre-trained model files shipped
3. No pre-built strategy files (outside examples/)
4. Config defaults are safe (execution disabled, paper mode on)
5. Disclaimer text present in report generators
6. No personal financial targets or alpha leaked

Usage:
    python scripts/compliance_audit.py
    python scripts/compliance_audit.py --strict   (fail on warnings too)

Exit codes:
    0 = all checks passed
    1 = one or more checks failed
"""

import os
import sys
import re
import yaml
from pathlib import Path
from typing import List, Tuple

# Audit from repo root
REPO_ROOT = Path(__file__).resolve().parent.parent


# ── Check definitions ────────────────────────────────────────

class AuditResult:
    def __init__(self):
        self.passed: List[str] = []
        self.failed: List[str] = []
        self.warnings: List[str] = []

    def ok(self, msg: str):
        self.passed.append(msg)

    def fail(self, msg: str):
        self.failed.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    @property
    def success(self):
        return len(self.failed) == 0

    def report(self):
        print("\n" + "=" * 60)
        print("  NAE MODEL A — COMPLIANCE AUDIT REPORT")
        print("=" * 60)

        if self.passed:
            print(f"\n  PASSED ({len(self.passed)}):")
            for p in self.passed:
                print(f"    [OK] {p}")

        if self.warnings:
            print(f"\n  WARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                print(f"    [!!] {w}")

        if self.failed:
            print(f"\n  FAILED ({len(self.failed)}):")
            for f in self.failed:
                print(f"    [FAIL] {f}")

        print(f"\n  {'-' * 50}")
        if self.success:
            print("  RESULT: ALL CHECKS PASSED")
        else:
            print(f"  RESULT: {len(self.failed)} CHECK(S) FAILED")
        print("=" * 60 + "\n")


def check_banned_language(result: AuditResult) -> None:
    """Scan Python files for advisory language in non-disclaimer context."""
    # These patterns are problematic when used as labels/outputs, not in negations
    banned_patterns = [
        (r'\b(recommended|suggested)\s+(trade|strategy|setup)', "Advisory recommendation"),
        (r'best\s+(trade|setup|strategy)\s+(right now|today|this week)', "Advisory recommendation"),
        (r'high\s+probability\s+(trade|setup|signal)', "Probability claim on trades"),
        (r'guaranteed\s+(return|profit|income)', "Guarantee claim"),
        (r'\$\d+[kK]?\s*→\s*\$\d+[kK]', "Performance projection"),
        (r'beat\s+the\s+market', "Market-beating claim"),
    ]

    nae_dir = REPO_ROOT / "nae"
    violations = []

    for py_file in nae_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for pattern, desc in banned_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for m in matches:
                # Get line number
                line_num = content[:m.start()].count("\n") + 1
                violations.append(f"{py_file.relative_to(REPO_ROOT)}:{line_num} — {desc}: '{m.group()}'")

    if violations:
        for v in violations:
            result.fail(v)
    else:
        result.ok("No banned advisory language found in nae/ source code")


def check_no_model_files(result: AuditResult) -> None:
    """Ensure no trained model weights are in the repo."""
    model_extensions = {".pt", ".pkl", ".h5", ".onnx", ".pb", ".safetensors"}
    found = []

    for ext in model_extensions:
        for f in REPO_ROOT.rglob(f"*{ext}"):
            if ".git" not in str(f):
                found.append(str(f.relative_to(REPO_ROOT)))

    if found:
        for f in found:
            result.fail(f"Trained model file found: {f}")
    else:
        result.ok("No trained model files (.pt, .pkl, .h5, .onnx) in repo")


def check_no_strategy_leak(result: AuditResult) -> None:
    """Ensure no pre-built strategies exist outside examples/."""
    nae_dir = REPO_ROOT / "nae"
    suspicious = []

    for py_file in nae_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        # Check for hardcoded strategy logic that generates trade decisions
        if re.search(r'def\s+generate_signal', content, re.IGNORECASE):
            suspicious.append(str(py_file.relative_to(REPO_ROOT)))
        if re.search(r'def\s+auto_trade', content, re.IGNORECASE):
            suspicious.append(str(py_file.relative_to(REPO_ROOT)))

    if suspicious:
        for s in suspicious:
            result.fail(f"Potential strategy/signal generator found: {s}")
    else:
        result.ok("No signal generators or auto-trade functions found in nae/")


def check_config_defaults(result: AuditResult) -> None:
    """Verify config.example.yaml has safe defaults."""
    config_path = REPO_ROOT / "config.example.yaml"

    if not config_path.exists():
        result.fail("config.example.yaml not found")
        return

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # execution_enabled must be false
    exec_enabled = cfg.get("nae", {}).get("execution_enabled", True)
    if exec_enabled:
        result.fail("config.example.yaml: nae.execution_enabled must be false")
    else:
        result.ok("config.example.yaml: execution_enabled = false")

    # paper_mode must be true
    paper = cfg.get("execution", {}).get("paper_mode", False)
    if not paper:
        result.fail("config.example.yaml: execution.paper_mode must be true")
    else:
        result.ok("config.example.yaml: paper_mode = true")

    # require_confirmation must be true
    confirm = cfg.get("execution", {}).get("require_confirmation", False)
    if not confirm:
        result.fail("config.example.yaml: execution.require_confirmation must be true")
    else:
        result.ok("config.example.yaml: require_confirmation = true")

    # broker should not have a key set
    broker_key = cfg.get("broker", {}).get("api_key")
    if broker_key and broker_key != "null":
        result.fail("config.example.yaml: broker.api_key should be null (not shipped with a key)")
    else:
        result.ok("config.example.yaml: no API keys in template")


def check_disclaimers(result: AuditResult) -> None:
    """Verify disclaimer module exists and has required text."""
    disclaimer_path = REPO_ROOT / "nae" / "core" / "disclaimer.py"

    if not disclaimer_path.exists():
        result.fail("nae/core/disclaimer.py not found")
        return

    content = disclaimer_path.read_text(encoding="utf-8")
    required_phrases = [
        "not a recommendation",
        "informational purposes only",
        "past performance",
        "substantial risk of loss",
    ]

    for phrase in required_phrases:
        if phrase.lower() not in content.lower():
            result.fail(f"Disclaimer missing required phrase: '{phrase}'")
        else:
            result.ok(f"Disclaimer contains: '{phrase}'")


def check_no_personal_targets(result: AuditResult) -> None:
    """Ensure no personal financial targets are in the codebase."""
    patterns = [
        r'\$5[,.]?000[,.]?000',
        r'5M\s+target',
        r'generational\s+wealth',
        r'VERY_AGGRESSIVE',
        r'growth_milestones',
        r'goal_manager',
    ]

    nae_dir = REPO_ROOT / "nae"
    found = []

    for py_file in nae_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                line_num = 0
                for i, line in enumerate(content.split("\n"), 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        line_num = i
                        break
                found.append(f"{py_file.relative_to(REPO_ROOT)}:{line_num} — matches '{pattern}'")

    if found:
        for f in found:
            result.fail(f"Personal target leaked: {f}")
    else:
        result.ok("No personal financial targets found in nae/ source")


def check_legal_docs(result: AuditResult) -> None:
    """Verify legal documents exist."""
    required = [
        "legal/TERMS_OF_SERVICE.md",
        "legal/RISK_DISCLOSURE.md",
    ]

    for doc in required:
        path = REPO_ROOT / doc
        if path.exists() and path.stat().st_size > 100:
            result.ok(f"{doc} exists ({path.stat().st_size} bytes)")
        else:
            result.fail(f"{doc} missing or empty")


def check_examples_have_disclaimers(result: AuditResult) -> None:
    """Verify all example strategies have disclaimer headers."""
    examples_dir = REPO_ROOT / "examples"
    if not examples_dir.exists():
        result.warn("examples/ directory not found")
        return

    for py_file in examples_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "DEMONSTRATION PURPOSES ONLY" in content or "STRATEGY TEMPLATE" in content:
            result.ok(f"examples/{py_file.name} has disclaimer header")
        else:
            result.fail(f"examples/{py_file.name} missing disclaimer header")


# ── Main ──────────────────────────────────────────────────────

def main():
    strict = "--strict" in sys.argv

    result = AuditResult()

    check_banned_language(result)
    check_no_model_files(result)
    check_no_strategy_leak(result)
    check_config_defaults(result)
    check_disclaimers(result)
    check_no_personal_targets(result)
    check_legal_docs(result)
    check_examples_have_disclaimers(result)

    result.report()

    if not result.success:
        sys.exit(1)
    if strict and result.warnings:
        print("  (Strict mode: warnings treated as failures)")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
