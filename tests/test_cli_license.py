"""
CLI tests for the ``nae license`` command group, focused on ``verify``.

These tests drive the CLI through Click's ``CliRunner``. They use a
disposable Ed25519 keypair and install it into the trusted set via the
``NAE_LICENSE_EXTRA_PUBLIC_KEYS`` env override, so none of the tests
require a real vendor key to be baked into ``license_keys.py``.

Key invariants exercised here:

1. ``verify`` exits 0 on a well-formed, correctly-signed license.
2. ``verify`` exits 2 on a tampered payload (signature no longer
   matches).
3. ``verify`` exits 2 on a version-constraint mismatch.
4. ``verify`` must NOT create or update ``activations.json``. A
   dry-run must be a true dry-run; if this assertion ever breaks, the
   "check before sending" workflow is silently leaking state.
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nae.cli.main import cli
from nae.core import licensing as L
from nae.core.feature_gates import reset_gates


# ── Helpers ─────────────────────────────────────────────────────────


def _keypair():
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv, pub_bytes


def _sign_envelope(priv, *, key_id, tier=L.PRO_TIER, days=365,
                   version_constraint=None, license_id="TEST-CLI-001"):
    now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    payload = L.LicensePayload(
        license_id=license_id,
        customer_email="cli-test@example.com",
        customer_name="CLI Test",
        tier=tier,
        issued_at=now.isoformat(),
        expires_at=(now + _dt.timedelta(days=days)).isoformat(),
        max_machines=1,
        features=(),
        version_constraint=version_constraint,
    )
    sig = priv.sign(L.canonical_signing_bytes(payload))
    return {
        "payload": payload.to_dict(),
        "signature": base64.b64encode(sig).decode("ascii"),
        "key_id": key_id,
        "signature_alg": "ed25519",
    }


@pytest.fixture
def isolated_license_env(tmp_path, monkeypatch):
    """Redirect the license dir and install an ephemeral trusted key.

    Also resets the FeatureGates singleton so the CLI's startup path
    starts fresh per test.
    """
    monkeypatch.setenv("NAE_LICENSE_DIR", str(tmp_path))
    monkeypatch.delenv("NAE_LICENSE_FILE", raising=False)
    monkeypatch.delenv("NAE_DISABLE_LICENSE", raising=False)
    reset_gates()

    priv, pub = _keypair()
    key_id = "test-cli-key"
    monkeypatch.setenv(
        "NAE_LICENSE_EXTRA_PUBLIC_KEYS",
        json.dumps({key_id: base64.b64encode(pub).decode("ascii")}),
    )

    yield {"tmp": tmp_path, "priv": priv, "key_id": key_id}

    reset_gates()


def _write_license(envelope: dict, path: Path) -> Path:
    path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    return path


# ── Tests ───────────────────────────────────────────────────────────


def test_verify_accepts_valid_license(isolated_license_env):
    env = _sign_envelope(
        isolated_license_env["priv"],
        key_id=isolated_license_env["key_id"],
        tier=L.PRO_TIER,
        days=30,
    )
    lic_path = _write_license(env, isolated_license_env["tmp"] / "good.nae")

    runner = CliRunner()
    result = runner.invoke(cli, ["license", "verify", str(lic_path)])

    assert result.exit_code == 0, result.output
    assert "License file verified" in result.output
    assert "Tier:          pro" in result.output


def test_verify_rejects_tampered_payload(isolated_license_env):
    env = _sign_envelope(
        isolated_license_env["priv"],
        key_id=isolated_license_env["key_id"],
        tier=L.PRO_TIER,
    )
    # Attacker bumps tier without re-signing.
    env["payload"]["tier"] = L.TEAM_TIER
    lic_path = _write_license(env, isolated_license_env["tmp"] / "tampered.nae")

    runner = CliRunner()
    result = runner.invoke(cli, ["license", "verify", str(lic_path)])

    assert result.exit_code == 2
    assert "Verification failed" in result.output


def test_verify_rejects_version_mismatch(isolated_license_env):
    env = _sign_envelope(
        isolated_license_env["priv"],
        key_id=isolated_license_env["key_id"],
        version_constraint=">=99.0.0",
    )
    lic_path = _write_license(env, isolated_license_env["tmp"] / "bad_version.nae")

    runner = CliRunner()
    result = runner.invoke(cli, ["license", "verify", str(lic_path)])

    assert result.exit_code == 2
    # The underlying error is a LicenseVersionMismatchError — the CLI
    # wraps it in the same "Verification failed" banner.
    assert "Verification failed" in result.output


def test_verify_rejects_wrong_key_id(isolated_license_env):
    env = _sign_envelope(
        isolated_license_env["priv"],
        key_id="some-other-key",  # not in trusted set
    )
    lic_path = _write_license(env, isolated_license_env["tmp"] / "wrong_key.nae")

    runner = CliRunner()
    result = runner.invoke(cli, ["license", "verify", str(lic_path)])

    assert result.exit_code == 2
    assert "Verification failed" in result.output


def test_verify_does_not_create_activation_store(isolated_license_env):
    """
    A verify is a dry-run. It must not create ``activations.json`` or
    otherwise mutate the license directory. This is the invariant that
    lets the vendor run ``verify`` during issuance without affecting
    their own development license state.
    """
    env = _sign_envelope(
        isolated_license_env["priv"],
        key_id=isolated_license_env["key_id"],
    )
    lic_path = _write_license(env, isolated_license_env["tmp"] / "dryrun.nae")
    activations = isolated_license_env["tmp"] / "activations.json"
    license_dest = isolated_license_env["tmp"] / "license.nae"
    assert not activations.exists()
    assert not license_dest.exists()

    runner = CliRunner()
    result = runner.invoke(cli, ["license", "verify", str(lic_path)])
    assert result.exit_code == 0, result.output

    # Neither of these should have been created by `verify`.
    assert not activations.exists(), (
        "verify must NOT write activations.json — that is activate's job"
    )
    assert not license_dest.exists(), (
        "verify must NOT copy the license into ~/.nae — that is activate's job"
    )


def test_verify_notes_expired_but_does_not_fail(isolated_license_env):
    env = _sign_envelope(
        isolated_license_env["priv"],
        key_id=isolated_license_env["key_id"],
        days=-100,  # expired long ago, past grace
    )
    lic_path = _write_license(env, isolated_license_env["tmp"] / "expired.nae")

    runner = CliRunner()
    result = runner.invoke(cli, ["license", "verify", str(lic_path)])

    # Signature is still valid — exit 0. The note flags that the
    # license is past its grace window and activating it would drop
    # the customer to free tier.
    assert result.exit_code == 0, result.output
    assert "Expired:       yes" in result.output
    assert "expired beyond the grace window" in result.output
