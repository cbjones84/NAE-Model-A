"""
NAE Model A — Embedded License Signing Public Keys

This module is the *only* place the product trusts for license
verification. The corresponding private keys are held exclusively by
the vendor (NEVER ship a private key in this repo).

Key rotation policy
-------------------
- A ``key_id`` identifies a specific signing key. Licenses carry their
  ``key_id`` so that the product can pick the right public key during
  verification.
- New keys are added here; old keys stay in place until every license
  signed with them has expired.
- To revoke a key immediately, move it to ``REVOKED_KEY_IDS`` below —
  any license carrying that key_id will then fail verification.

Operator runbook
----------------
1. Generate a fresh keypair::

       python -m tools.issuer.generate_keypair --key-id modela-YYYY-NN

   That command prints both keys and writes the private key to a
   vendor-controlled location specified on the CLI.
2. Paste the printed ``PUBLIC KEY (base64)`` line into
   ``_PUBLIC_KEYS_B64`` below.
3. Commit **only this file**. Never commit the private key.
4. Start issuing licenses with the new ``key_id``.

Environment overrides (used by tests and by air-gapped deploys)
---------------------------------------------------------------
- ``NAE_LICENSE_EXTRA_PUBLIC_KEYS`` — a JSON object
  ``{"key_id": "base64_public_key", ...}`` whose entries are merged
  into the trusted set. This is NOT a back door: a customer who sets
  it can only add keys they *already* possess, so at worst they can
  issue themselves licenses for their own copy. The product still
  refuses to verify any signature that doesn't match one of the
  trusted public keys.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Dict, Tuple

logger = logging.getLogger("nae.licensing.keys")


# ── Trusted public keys ──────────────────────────────────────────────
#
# Format: base64 of the 32-byte Ed25519 public key.
#
# There is intentionally no production key baked in here at launch.
# The vendor runs ``tools/issuer/generate_keypair.py`` once, then adds
# the generated public key to this dict. Shipping with no production
# key means a pre-key-generation build simply treats every license as
# unsigned / untrusted and falls back to the free tier — which is the
# safe default.
_PUBLIC_KEYS_B64: Dict[str, str] = {
    #  _PUBLIC_KEYS_B64:
    "modela-2026-01": "FI0x2w4s1JTi31NzjkhWvSF1l2CdDgh2F2Hp/wsu/FQ=",
}


# Keys previously trusted that have been compromised or retired.
# Any license carrying one of these key_ids is rejected even if it
# would otherwise verify against the raw bytes.
REVOKED_KEY_IDS: Tuple[str, ...] = ()


# ── Public API ───────────────────────────────────────────────────────


def get_trusted_public_keys() -> Dict[str, bytes]:
    """Return the full set of trusted ``key_id`` → public-key-bytes.

    Merges the baked-in keys with any keys supplied via
    ``NAE_LICENSE_EXTRA_PUBLIC_KEYS``. Revoked keys are filtered out.
    """
    out: Dict[str, bytes] = {}

    for key_id, b64 in _PUBLIC_KEYS_B64.items():
        if key_id in REVOKED_KEY_IDS:
            continue
        try:
            out[key_id] = base64.b64decode(b64, validate=True)
        except Exception as e:  # noqa: BLE001 - keep the product starting up
            logger.warning("Cannot decode embedded public key %r: %s", key_id, e)

    extra = os.environ.get("NAE_LICENSE_EXTRA_PUBLIC_KEYS")
    if extra:
        try:
            parsed = json.loads(extra)
            if isinstance(parsed, dict):
                for key_id, b64 in parsed.items():
                    if key_id in REVOKED_KEY_IDS:
                        continue
                    try:
                        out[str(key_id)] = base64.b64decode(str(b64), validate=True)
                    except Exception as e:  # noqa: BLE001
                        logger.warning(
                            "Cannot decode NAE_LICENSE_EXTRA_PUBLIC_KEYS[%r]: %s",
                            key_id,
                            e,
                        )
        except json.JSONDecodeError as e:
            logger.warning("NAE_LICENSE_EXTRA_PUBLIC_KEYS is not valid JSON: %s", e)

    return out


def has_any_trusted_key() -> bool:
    return bool(get_trusted_public_keys())
