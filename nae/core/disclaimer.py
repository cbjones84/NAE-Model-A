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
║  • AI analysis is not a guarantee of accuracy.               ║
║  • Past backtest performance does NOT indicate future        ║
║    results.                                                  ║
║  • Trading securities, options, and cryptocurrencies         ║
║    involves substantial risk of loss.                        ║
║  • You should consult a licensed financial advisor before    ║
║    making investment decisions.                              ║
║                                                              ║
║  By using NAE, you acknowledge that you have read and        ║
║  accept the full Terms of Service and Risk Disclosure        ║
║  documents included with this software.                      ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


def append_disclaimer(text: str, short: bool = False) -> str:
    """Append the appropriate disclaimer to output text."""
    d = SHORT_DISCLAIMER if short else REPORT_DISCLAIMER
    return f"{text}\n\n{d}"
