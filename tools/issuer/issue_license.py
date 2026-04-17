#!/usr/bin/env python3
"""
Issue a new NAE Model A license.

Usage
-----
    python -m tools.issuer.issue_license \\
        --private-key ./keys/modela-2026-01.private \\
        --key-id modela-2026-01 \\
        --customer-email alice@example.com \\
        --customer-name "Alice Trader" \\
        --tier pro \\
        --valid-days 365 \\
        --max-machines 2 \\
        --version-constraint ">=1.0.0,<2.0.0" \\
        --out ./issued/alice-2026.nae

If ``--license-id`` is omitted, one is generated automatically in the
form ``MDLA-YYYY-XXXXXX``.

The resulting file is a plain JSON license envelope that can be emailed
to the customer, who installs it with::

    nae license activate ./alice-2026.nae

The signing logic MUST match ``License.canonical_payload_bytes`` in
``nae/core/licensing.py``. That function is the authoritative
serializer — do not duplicate it here; we import it directly.
"""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import json
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nae.core.licensing import (
    LicensePayload,
    VALID_TIERS,
    canonical_signing_bytes,
)


def _generate_license_id() -> str:
    year = _dt.datetime.now(_dt.timezone.utc).year
    suffix = secrets.token_hex(3).upper()
    return f"MDLA-{year}-{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--customer-email", required=True)
    parser.add_argument("--customer-name", default=None)
    parser.add_argument(
        "--tier", required=True, choices=VALID_TIERS,
        help=f"License tier (one of {VALID_TIERS}).",
    )
    parser.add_argument(
        "--valid-days", type=int, required=True,
        help="License duration in days from now (e.g. 365).",
    )
    parser.add_argument("--max-machines", type=int, default=1)
    parser.add_argument(
        "--version-constraint", default=None,
        help="Optional version constraint, e.g. '>=1.0.0,<2.0.0'.",
    )
    parser.add_argument(
        "--license-id", default=None,
        help="Override license id. Auto-generated if omitted.",
    )
    parser.add_argument(
        "--extra-feature", action="append", default=[],
        help="Add a per-license extra feature. Repeatable.",
    )
    parser.add_argument(
        "--out", required=True, type=Path,
        help="Output path for the signed license file.",
    )
    args = parser.parse_args()

    # Load private key
    try:
        priv_bytes = args.private_key.read_bytes()
    except OSError as e:
        print(f"Cannot read private key: {e}", file=sys.stderr)
        return 2
    if len(priv_bytes) != 32:
        print(
            f"Private key at {args.private_key} is not 32 bytes "
            f"(got {len(priv_bytes)}). Did you point at the wrong file?",
            file=sys.stderr,
        )
        return 2
    priv = Ed25519PrivateKey.from_private_bytes(priv_bytes)

    now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    expires = now + _dt.timedelta(days=args.valid_days)

    payload = LicensePayload(
        license_id=args.license_id or _generate_license_id(),
        customer_email=args.customer_email,
        customer_name=args.customer_name,
        tier=args.tier,
        issued_at=now.isoformat(),
        expires_at=expires.isoformat(),
        max_machines=args.max_machines,
        features=tuple(args.extra_feature),
        version_constraint=args.version_constraint,
    )

    canonical = canonical_signing_bytes(payload)
    signature = priv.sign(canonical)
    envelope = {
        "payload": payload.to_dict(),
        "signature": base64.b64encode(signature).decode("ascii"),
        "key_id": args.key_id,
        "signature_alg": "ed25519",
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")

    print(f"Issued license {payload.license_id}")
    print(f"  Customer:  {payload.customer_email}")
    print(f"  Tier:      {payload.tier}")
    print(f"  Expires:   {payload.expires_at}")
    print(f"  Machines:  {payload.max_machines}")
    print(f"  File:      {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
