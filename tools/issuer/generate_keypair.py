#!/usr/bin/env python3
"""
Generate a fresh Ed25519 keypair for NAE Model A license signing.

Usage
-----
    python -m tools.issuer.generate_keypair --key-id modela-2026-01 \\
        --out ./keys/

This writes:
    ./keys/modela-2026-01.private     (PRIVATE KEY — guard with your life)
    ./keys/modela-2026-01.public.b64  (base64 public key)

Also prints both to stdout so you can paste the base64 public key into
``nae/core/license_keys.py`` — the only file that's meant to be
committed after running this.

SAFETY
------
- The private key grants the ability to mint licenses for NAE Model A.
  If it leaks, rotate immediately:
    1. Add the old ``key_id`` to ``REVOKED_KEY_IDS`` in
       ``nae/core/license_keys.py``.
    2. Generate a new keypair.
    3. Issue replacement licenses to paying customers signed with the
       new key.
- Store the private key in a password manager or encrypted volume.
  Never commit it. ``tools/issuer/.gitignore`` already blocks common
  filenames, and ``scripts/compliance_audit.py`` double-checks.
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument(
        "--key-id",
        required=True,
        help="Identifier for the keypair (e.g. 'modela-2026-01').",
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output directory (created if missing).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting an existing key file.",
    )
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    priv_path = args.out / f"{args.key_id}.private"
    pub_path = args.out / f"{args.key_id}.public.b64"

    if (priv_path.exists() or pub_path.exists()) and not args.overwrite:
        print(
            f"Refusing to overwrite existing key files under {args.out}. "
            f"Pass --overwrite if you really mean it.",
            file=sys.stderr,
        )
        return 2

    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    priv_path.write_bytes(priv_bytes)
    pub_path.write_text(base64.b64encode(pub_bytes).decode("ascii") + "\n")

    try:
        priv_path.chmod(0o600)
    except (OSError, NotImplementedError):
        pass  # Windows / FS without perms — still gitignored.

    print(f"Generated Ed25519 keypair with key_id = {args.key_id!r}")
    print(f"  Private key -> {priv_path}  (chmod 600)")
    print(f"  Public key  -> {pub_path}")
    print()
    print("Paste this line into nae/core/license_keys.py  _PUBLIC_KEYS_B64:")
    print(f'    "{args.key_id}": "{base64.b64encode(pub_bytes).decode("ascii")}",')
    return 0


if __name__ == "__main__":
    sys.exit(main())
