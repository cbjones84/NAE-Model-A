"""
Private issuer tooling for NAE Model A licensing.

Everything in this package runs ONLY on the vendor's machine. It never
ships in a customer build (the ``nae-platform`` wheel's setuptools
config only includes ``nae*``). The tools here need access to the
private Ed25519 signing key, which must never be committed to git.

See ``tools/issuer/README.md`` for the operator runbook.
"""
