#!/usr/bin/env python3
"""
NAE Model A — Initialize the vendor customer-license ledger.

Creates a CSV file outside the repository with the header row used by
the issuance SOP (see ``docs/issuance-sop.md``). If the file already
exists it is left untouched so repeated runs never destroy your data.

Typical usage on the vendor machine::

    python -m tools.issuer.init_ledger \\
        --path "C:\\Users\\v-nat\\NAE-Secure-Keys\\ledger\\licenses.csv"

The ledger is intentionally stored *outside* the repo — it contains
customer PII and business records that must never be committed.

The file format is plain CSV with a header row, plus one commented
example row starting with ``#``. Most spreadsheet tools open it
natively; parsers that honor a ``#`` comment prefix (pandas with
``comment='#'``, csvkit, etc.) will ignore the example automatically.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HEADER = (
    "issued_at_utc,license_id,key_id,customer_name,customer_email,"
    "tier,max_machines,expires_at_utc,version_constraint,"
    "payment_reference,file_path,status,notes"
)

EXAMPLE = (
    '# 2026-04-17T16:30:00Z,MDLA-2026-XXXXXX,modela-2026-01,'
    'Customer Company Ltd.,customer@example.com,pro,1,'
    '2027-04-17T16:30:00Z,">=1.0.0,<2.0.0",stripe_ch_abc123,'
    'C:\\Users\\v-nat\\NAE-Secure-Keys\\issued\\20260417-customerltd-pro.nae,'
    'issued,'
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument(
        "--path",
        required=True,
        type=Path,
        help="Target CSV path (created with parents if missing).",
    )
    args = parser.parse_args()

    target: Path = args.path
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        print(f"Ledger already exists at {target}. Leaving unchanged.")
        return 0

    target.write_text(HEADER + "\n" + EXAMPLE + "\n", encoding="utf-8")
    print(f"Created ledger at {target}")
    print("Next: add your first row after a real license issuance.")
    print("See docs/issuance-sop.md for the full workflow.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
