# NAE Model A — License Issuance SOP

Standard Operating Procedure for issuing, delivering, tracking, and
(if needed) revoking customer licenses.

Follow this checklist **every time** a new paying customer is onboarded.
Consistency here is what keeps the business safe: one missed step
(e.g. committing a private key, reusing a license id, forgetting the
expiry) can compromise the whole licensing model.

---

## Roles and assumptions

- **Vendor (you)** — holds the private key at
  `C:\Users\v-nat\NAE-Secure-Keys\keys\modela-2026-01.private`, issues
  licenses, maintains the customer ledger.
- **Customer** — pays, receives a `.nae` license file, runs
  `nae license activate` on their machine.

Before running this SOP for the first time, confirm:

- [ ] Public key `modela-2026-01` is pushed and lives in
      `nae/core/license_keys.py` on `main`.
- [ ] Private key is stored in at least **two** secure locations
      (password manager secure file + encrypted USB / encrypted backup).
- [ ] Customer ledger file exists and is backed up (see template below).

---

## Checklist: issuing a new license (every customer)

### 0. Pre-issue intake

Collect from the customer before doing anything:

- [ ] Full legal/company name
- [ ] Billing email (this becomes `customer_email` on the license)
- [ ] Tier purchased (`free` / `pro` / `team`)
- [ ] Seat count / max machines (`1` for single-seat, more for team)
- [ ] Term length (e.g. 365 days for annual)
- [ ] Payment reference (Stripe ID, invoice #, etc.)

Record in ledger as `pending`.

### 1. Verify payment

- [ ] Payment confirmed in processor (Stripe / manual invoice paid)
- [ ] Refund window considered (optional: wait X days for
      high-risk regions)
- [ ] Chargeback risk screened

If anything looks off → do **not** issue. Park in `pending_review`.

### 2. Open a secure PowerShell session

Always issue from the vendor machine, never from a shared machine.

```powershell
cd "C:\Users\v-nat\NAE Model A"
git branch --show-current     # confirm you are on a branch with the production public key
```

### 3. Pick license parameters

Set your variables up front so the command below stays clean:

```powershell
$PRIV = "C:\Users\v-nat\NAE-Secure-Keys\keys\modela-2026-01.private"
$KEYID = "modela-2026-01"

$EMAIL    = "customer@example.com"
$NAME     = "Customer Company Ltd."
$TIER     = "pro"              # free | pro | team
$DAYS     = 365
$MACHINES = 1
$VER      = ">=1.0.0,<2.0.0"

$ISSUED_DIR = "C:\Users\v-nat\NAE-Secure-Keys\issued"
New-Item -ItemType Directory -Force -Path $ISSUED_DIR | Out-Null

# License filename convention: yyyyMMdd-<lastname-or-slug>-<tier>.nae
$SLUG = "customerltd"          # short lowercase slug for the customer
$DATE = Get-Date -Format "yyyyMMdd"
$OUT  = Join-Path $ISSUED_DIR "$DATE-$SLUG-$TIER.nae"
```

### 4. Issue the license

```powershell
python -m tools.issuer.issue_license `
  --private-key $PRIV `
  --key-id $KEYID `
  --customer-email $EMAIL `
  --customer-name $NAME `
  --tier $TIER `
  --valid-days $DAYS `
  --max-machines $MACHINES `
  --version-constraint $VER `
  --out $OUT
```

Expected output includes a line like:

```
Issued license MDLA-2026-XXXXXX
```

Record `MDLA-2026-XXXXXX` — that is your `license_id`.

### 5. Local verification before delivery

Always dry-run verify before sending to the customer. The `verify`
command does **not** install, copy, or activate the license — it only
checks the signature, version, and expiry. That makes it safe to run
against any `.nae` file without touching your own installed license.

```powershell
python -m nae license verify $OUT
```

Expected:

- `[OK] License file verified`
- `Tier:` matches `$TIER`
- `License id:` matches what you recorded at issuance time
- `Expires at:` is roughly `now + $DAYS days`
- `Expired:` is `no`
- `Key id:` matches `$KEYID`

If any field looks wrong, stop and re-issue before delivering.

> If you need to go further (i.e. perform a full end-to-end
> installation test), use an isolated license directory so your own
> license is not overwritten:
>
> ```powershell
> $env:NAE_LICENSE_DIR = "$env:TEMP\nae-issue-test"
> Remove-Item $env:NAE_LICENSE_DIR -Recurse -Force -ErrorAction SilentlyContinue
> python -m nae license activate $OUT
> python -m nae license show
> Remove-Item $env:NAE_LICENSE_DIR -Recurse -Force -ErrorAction SilentlyContinue
> Remove-Item Env:NAE_LICENSE_DIR
> ```
>
> For routine issuance, `verify` alone is sufficient and leaves no
> side effects on disk.

### 6. Ledger entry

Add a row to your customer ledger (see template below) with:

- Date
- `license_id`
- `key_id` used
- Customer name + email
- Tier + seats + expiry
- Payment reference
- File path of the generated `.nae`
- Delivery method + date

Status: `issued`.

### 7. Deliver to the customer

- [ ] Send `.nae` file to the `customer_email` on record
- [ ] Include activation instructions (see "Customer email template"
      below)
- [ ] Do **not** share the license on a public channel

### 8. Post-delivery

- [ ] Ledger status: `delivered`
- [ ] Calendar reminder: `expires_at` minus 30 days → send renewal
      reminder
- [ ] Retain the `.nae` file in `ISSUED_DIR` — treat as internal
      business record, back it up with the rest of your ledger

---

## Customer ledger template (CSV)

Keep this file **off the public repo** and in the same secure vault as
your private key. Suggested filename:
`C:\Users\v-nat\NAE-Secure-Keys\ledger\licenses.csv`.

The repo ships a helper that generates the file with the correct
header and a commented example row. Run it once on the vendor
machine:

```powershell
python -m tools.issuer.init_ledger --path "C:\Users\v-nat\NAE-Secure-Keys\ledger\licenses.csv"
```

The helper is idempotent: if the file already exists, it is left
untouched and never overwrites existing data.

The header row is:

```csv
issued_at_utc,license_id,key_id,customer_name,customer_email,tier,max_machines,expires_at_utc,version_constraint,payment_reference,file_path,status,notes
```

A commented example row (ignored by parsers that honor `#`):

```csv
# 2026-04-17T16:30:00Z,MDLA-2026-XXXXXX,modela-2026-01,Customer Company Ltd.,customer@example.com,pro,1,2027-04-17T16:30:00Z,">=1.0.0,<2.0.0",stripe_ch_abc123,C:\Users\v-nat\NAE-Secure-Keys\issued\20260417-customerltd-pro.nae,issued,
```

Status values used:

| status              | meaning                                          |
|---------------------|--------------------------------------------------|
| `pending`           | Payment received, not yet issued                 |
| `pending_review`    | Held for fraud / payment verification            |
| `issued`            | `.nae` generated, not yet sent                   |
| `delivered`         | Sent to customer                                 |
| `expired`           | Past `expires_at`, no renewal                    |
| `renewed`           | Superseded by a newer `license_id`               |
| `revoked`           | Actively revoked (see revocation section)        |
| `refunded`          | Payment refunded; should be effectively revoked  |

Minimum backup policy: one copy in a cloud password-manager vault, one
copy on encrypted local backup. Never in git, never in email.

---

## Customer email template

Keep it short, professional, and technically correct. Don't include
support language that could be read as investment advice.

```text
Subject: Your NAE Model A license

Hi {customer_name},

Thank you for purchasing NAE Model A ({tier} tier).

Your license file is attached: {license_filename}

To activate on the machine you will use NAE on:

    1. Install NAE Model A (pip install . from the repo, or the
       provided wheel).
    2. Run:
           nae license activate /path/to/{license_filename}
    3. Verify with:
           nae license show
       You should see "Effective tier: {tier}".

Details:
    License id:     {license_id}
    Tier:           {tier}
    Seats / max:    {max_machines}
    Expires:        {expires_at_utc} UTC
    Version range:  {version_constraint}

Need a seat on another machine, or a renewal? Just reply to this
email with the license id above.

Important: This license grants access to the NAE Model A research
platform. NAE Model A is a research and analysis tool — it does not
provide financial advice or trade recommendations. All trading
decisions remain yours. See legal/TERMS_OF_SERVICE.md and
legal/RISK_DISCLOSURE.md in your installation.

— The NAE Model A Team
```

---

## Renewals

Roughly 30 days before a license expires:

1. Reach out to the customer with the renewal offer.
2. On payment, issue a **new** license with a new `license_id` and a
   new `expires_at` — do not try to extend the old one.
3. Ledger:
   - Mark the old row `renewed` with a `notes` pointer to the new
     `license_id`.
   - Add the new row as `issued` → `delivered`.
4. Customer re-runs `nae license activate` with the new `.nae`.

A renewed license carries the same `key_id` as long as your signing
key has not been rotated.

---

## Revocation (customer-initiated or fraud)

There is no online revocation in Phase 0. Your practical options are:

### Option A — ignore and let it expire

Appropriate for minor disputes, normal end-of-term churn.

### Option B — rotate the signing key (nuclear option)

Use only for serious compromise (leaked private key, high-impact
fraud, etc.). Steps:

1. Generate a new keypair with a fresh `key_id`:
```powershell
python -m tools.issuer.generate_keypair `
  --key-id modela-YYYY-NN `
  --out "C:\Users\v-nat\NAE-Secure-Keys\keys"
```
2. Add the new key to `_PUBLIC_KEYS_B64` in
   `nae/core/license_keys.py`.
3. Move the **old** `key_id` into `REVOKED_KEY_IDS` in the same file.
4. Commit + push + release a product update. Every license carrying
   the old `key_id` stops verifying on the next upgrade.
5. Re-issue licenses to *legitimate* customers with the new `key_id`.
6. Ledger: flip revoked rows to `revoked`; flip reissued rows to
   `issued` / `delivered`.

### Option C — license-id revocation list (Phase 2)

Not implemented in Phase 0. When built, it will allow revoking a
specific `license_id` without rotating the whole key. Until then,
Option A or B is the choice.

---

## Emergency runbook: "I think the private key leaked"

Treat as a security incident. Do these in order:

- [ ] Assume the key is compromised. Do not wait for confirmation.
- [ ] Generate a new keypair with a new `key_id` (see Option B above).
- [ ] Commit public-key change + `REVOKED_KEY_IDS` update. Push.
- [ ] Release a new product version.
- [ ] Re-issue licenses to legitimate customers.
- [ ] Audit the ledger: flag any license issued around the suspected
      leak window for extra scrutiny.
- [ ] Review how the leak happened (accidental commit, shared
      machine, malware, etc.) and fix the root cause.
- [ ] Retire the old private key file from all vaults; keep one
      copy offline in a sealed envelope labeled "COMPROMISED — DO NOT
      USE" for audit trail only.

---

## What to never, ever do

- Never commit a `.private` file. `scripts/compliance_audit.py` is
  there as a backstop — don't rely on it alone.
- Never email or DM a private key.
- Never issue a license without a ledger entry.
- Never reuse a `license_id` across customers.
- Never shorten the expiry on an already-issued license — issue a new
  one instead.
- Never adjust a license manually by hand-editing JSON. Always
  re-issue through `issue_license.py`, which handles signing for you.

---

## Quick reference: one-liner

The entire routine for "I just sold a pro, 1 machine, annual license":

```powershell
cd "C:\Users\v-nat\NAE Model A"
python -m tools.issuer.issue_license `
  --private-key "C:\Users\v-nat\NAE-Secure-Keys\keys\modela-2026-01.private" `
  --key-id modela-2026-01 `
  --customer-email "customer@example.com" `
  --customer-name "Customer Name" `
  --tier pro `
  --valid-days 365 `
  --max-machines 1 `
  --version-constraint ">=1.0.0,<2.0.0" `
  --out "C:\Users\v-nat\NAE-Secure-Keys\issued\$(Get-Date -Format yyyyMMdd)-customer-pro.nae"
```

Then: verify → log in ledger → email to customer → celebrate the sale.
