# NAE Model A — Vendor Issuer Toolkit

Private vendor tooling. Do **not** ship in customer wheels.
The setuptools config in `pyproject.toml` only packages `nae*`, so this
directory is never included in distributions.

## One-time setup

1. Generate a signing keypair on a machine you control (ideally
   air-gapped, or at minimum a password-manager-backed volume):

   ```bash
   python -m tools.issuer.generate_keypair \
       --key-id modela-2026-01 \
       --out ./keys/
   ```

   This writes `./keys/modela-2026-01.private` (never commit!) and
   `./keys/modela-2026-01.public.b64`. The command also prints the exact
   line to paste into `nae/core/license_keys.py`.

2. Edit `nae/core/license_keys.py` and add the printed line to
   `_PUBLIC_KEYS_B64`. Commit that file (only).

3. Store the private key in a password manager (1Password / Bitwarden)
   or on an encrypted USB. Ideally keep an offline backup too.

## Issuing a license

```bash
python -m tools.issuer.issue_license \
    --private-key ./keys/modela-2026-01.private \
    --key-id modela-2026-01 \
    --customer-email alice@example.com \
    --customer-name "Alice Trader" \
    --tier pro \
    --valid-days 365 \
    --max-machines 2 \
    --version-constraint ">=1.0.0,<2.0.0" \
    --out ./issued/alice-2026.nae
```

Email `./issued/alice-2026.nae` to the customer. They activate with:

```bash
nae license activate alice-2026.nae
```

## Key rotation

When a private key is compromised or retired:

1. Add the compromised `key_id` to `REVOKED_KEY_IDS` in
   `nae/core/license_keys.py`. Every license carrying that key_id now
   fails verification.
2. Generate a new keypair with a fresh `key_id`.
3. Re-issue replacement licenses to paying customers.
4. Keep the revoked key_id listed for at least the longest license
   duration you ever issued, plus a buffer.

## Never commit

- `*.private`
- `*.pem`, `*.key`
- `keys/`, `secrets/`

`tools/issuer/.gitignore` blocks these patterns, and
`scripts/compliance_audit.py` fails the build if a 32-byte raw private
key ever lands in the repo.
