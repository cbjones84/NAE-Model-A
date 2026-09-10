"""
NAE Disclaimer System

Appends compliance disclaimers to all user-facing output.
"""

REPORT_DISCLAIMER = (
    "─" * 60 + "\n"
    "DISCLAIMER: This output is for informational purposes only.\n"
    "It is not a recommendation to buy, sell, or hold any security.\n"
    "All trading decisions are made solely by the user. Past\n"
    "performance in backtests does not indicate future results.\n"
    "Trading involves substantial risk of loss.\n"
    "─" * 60
)

SHORT_DISCLAIMER = (
    "Research data only — not a trade recommendation. "
    "Past performance does not indicate future results."
)

FIRST_RUN_NOTICE = """
╔══════════════════════════════════════════════════════════════╗
║                   NAE PLATFORM — RISK DISCLOSURE            ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  NAE is a software tool for research and analysis.           ║
║  It does NOT provide financial advice, trade                 ║
║  recommendations, or portfolio management services.          ║
║                                                              ║
║  • All trading decisions are made solely by the user.        ║
║  • Statistical analysis is not a guarantee of accuracy.      ║
║  • Past backtest performance does NOT indicate future        ║
║    results.                                                  ║
║  • Trading securities, options, and cryptocurrencies         ║
║    involves substantial risk of loss.                        ║
║  • You should consult a licensed financial advisor before    ║
║    making investment decisions.                              ║
║                                                              ║
║  The full Terms of Service and Risk Disclosure are files     ║
║  shipped with this software. Init will print their paths     ║
║  and a short excerpt before you accept.                      ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


LEGAL_FILENAMES = ("TERMS_OF_SERVICE.md", "RISK_DISCLOSURE.md")


def find_legal_dir():
    """Locate the directory that contains the shipped legal markdown files."""
    from pathlib import Path

    here = Path(__file__).resolve()
    candidates = [
        Path.cwd() / "legal",
        here.parents[2] / "legal",  # repo root when running from source
        here.parents[1] / "legal",
    ]
    for candidate in candidates:
        if (candidate / "TERMS_OF_SERVICE.md").is_file():
            return candidate
    return None


def legal_excerpt(path, max_lines: int = 12) -> str:
    """Return the first non-empty lines of a legal file for display at init."""
    from pathlib import Path

    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    excerpt = "\n".join(lines[:max_lines])
    if len(lines) > max_lines:
        excerpt += "\n  … (open the file for the full document)"
    return excerpt


def append_disclaimer(text: str, short: bool = False) -> str:
    """Append the appropriate disclaimer to output text."""
    d = SHORT_DISCLAIMER if short else REPORT_DISCLAIMER
    return f"{text}\n\n{d}"
