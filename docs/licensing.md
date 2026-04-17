# NAE Model A — Licensing

NAE Model A uses **offline-first, signature-based licensing**. Your
license is a small signed JSON file that verifies locally — the product
does not phone home to run, and your research can keep flowing even if
our servers are down.

## Tiers & features

| Feature                     | Free | Pro | Team |
|-----------------------------|:----:|:---:|:----:|
| Research reports            |  ✓   |  ✓  |  ✓   |
| CSV import                  |  ✓   |  ✓  |  ✓   |
| Single-symbol backtests     |  ✓   |  ✓  |  ✓   |
| Multi-symbol backtests      |      |  ✓  |  ✓   |
| Correlation matrix          |      |  ✓  |  ✓   |
| Walk-forward analysis       |      |  ✓  |  ✓   |
| Benchmark comparison        |      |  ✓  |  ✓   |
| Monte Carlo bootstrap       |      |  ✓  |  ✓   |
| Full regime detection       |      |  ✓  |  ✓   |
| Structured JSON logs        |      |     |  ✓   |
| Offline Docker image        |      |     |  ✓   |
| Team seats                  |      |     |  ✓   |

**Licensing gates paid features only.** Broker execution is *always*
controlled by your `config.yaml` — a license (or the absence of one)
will never turn on or off the `execute` command set. That separation
is enforced by a dedicated test (`test_license_never_affects_execution_allowed`)
and is a deliberate compliance boundary.

## Activating a license

```bash
nae license activate ./my-license.nae
```

This verifies the signature locally, installs the file to
`~/.nae/license.nae`, and records this machine in the activation list
for the license.

Check status at any time:

```bash
nae license show
```

## Where things live

| Path                         | Purpose                             |
|------------------------------|-------------------------------------|
| `~/.nae/license.nae`         | Your installed license file         |
| `~/.nae/activations.json`    | Local record of activated machines  |

Override either via the environment:

- `NAE_LICENSE_FILE=/path/to/license.nae` — point at a license
  elsewhere (useful for CI or shared filesystems).
- `NAE_LICENSE_DIR=/tmp/naedir` — override the whole directory (used
  by tests).
- `NAE_DISABLE_LICENSE=1` — force free-tier mode regardless of any
  installed license (used by tests and open-source installs).

## What happens when things go wrong

| Situation                               | Behaviour                                                          |
|----------------------------------------- |--------------------------------------------------------------------|
| No license file present                  | Free tier. Paid commands print a friendly upgrade prompt.          |
| License signature invalid / tampered     | **Hard fail** at startup. Product refuses to run until it's fixed. |
| License built for a different version    | **Hard fail** at startup with a message explaining how to resolve. |
| License expired, within grace (≤14 days) | Tier preserved; you get a warning. Renew before it lapses.         |
| License expired beyond grace             | Drops to free tier; paid features lock.                            |
| Machine binding exceeded                 | Warning only (soft). Contact support to re-balance activations.    |

Soft failures always fall back to the free tier — we'd rather you still
have a working research tool than see your workflow halted by a
network hiccup or a filesystem issue.

## Privacy

- No telemetry is sent when you run `nae license show`, `activate`,
  `deactivate`, or any other command in the Phase 0 build.
- The activation record stored locally contains only your license id,
  a fingerprint hash of the machine, and timestamps. It never leaves
  your computer.

## Vendor operations

This end of the pipeline (minting licenses, rotating keys) lives in
[`tools/issuer/README.md`](../tools/issuer/README.md). It is only used
on the vendor's machine; the private signing key never touches this
repo.

For the step-by-step workflow used on every new customer (intake,
issuance, verification, delivery, ledger, renewals, and the emergency
key-leak runbook), see [`docs/issuance-sop.md`](./issuance-sop.md).
