"""
Tests for nae.core.licensing.

These tests exercise the full issuer→verifier pipeline using a
throwaway Ed25519 keypair generated inside each test, so they do not
depend on any real vendor key. The same ``canonical_signing_bytes``
helper the issuer tool uses is called here, which guarantees the test
suite catches any future serialization drift.
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import os
import tempfile
from pathlib import Path
from typing import Tuple

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from nae.core import licensing as L
from nae.core.feature_gates import FeatureGates, reset_gates


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def isolated_nae_dir(tmp_path, monkeypatch):
    """Redirect license file + activations to a temp dir so the tests
    never touch ``~/.nae/`` on the developer's machine.
    """
    monkeypatch.setenv("NAE_LICENSE_DIR", str(tmp_path))
    monkeypatch.delenv("NAE_LICENSE_FILE", raising=False)
    monkeypatch.delenv("NAE_DISABLE_LICENSE", raising=False)
    reset_gates()
    yield tmp_path
    reset_gates()


def _keypair() -> Tuple[Ed25519PrivateKey, bytes]:
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv, pub_bytes


def _sign_license(
    priv: Ed25519PrivateKey,
    key_id: str,
    *,
    tier: str = L.PRO_TIER,
    expires_in_days: int = 365,
    max_machines: int = 1,
    version_constraint=None,
    issued_at=None,
    license_id: str = "TEST-0001",
    extra_features: Tuple[str, ...] = (),
) -> dict:
    now = issued_at or _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    expires = now + _dt.timedelta(days=expires_in_days)
    payload = L.LicensePayload(
        license_id=license_id,
        customer_email="test@example.com",
        customer_name="Test User",
        tier=tier,
        issued_at=now.isoformat(),
        expires_at=expires.isoformat(),
        max_machines=max_machines,
        features=extra_features,
        version_constraint=version_constraint,
    )
    canonical = L.canonical_signing_bytes(payload)
    signature = priv.sign(canonical)
    return {
        "payload": payload.to_dict(),
        "signature": base64.b64encode(signature).decode("ascii"),
        "key_id": key_id,
        "signature_alg": "ed25519",
    }


def _install_license(envelope: dict, isolated_dir: Path) -> Path:
    path = isolated_dir / "license.nae"
    path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    return path


# ── Parsing / serialization ──────────────────────────────────────────


def test_canonical_bytes_are_deterministic():
    priv, _ = _keypair()
    env = _sign_license(priv, "k1")
    # Re-round-trip via the LicensePayload
    lic = L.License.from_dict(env)
    payload_bytes_a = L.canonical_signing_bytes(lic.payload)
    payload_bytes_b = L.canonical_signing_bytes(lic.payload)
    assert payload_bytes_a == payload_bytes_b
    # Must be stable under key ordering
    reordered = dict(reversed(list(env["payload"].items())))
    assert L.License.canonical_payload_bytes(reordered) == payload_bytes_a


def test_rejects_non_ed25519_algorithm():
    priv, _ = _keypair()
    env = _sign_license(priv, "k1")
    env["signature_alg"] = "rsa"
    with pytest.raises(L.LicenseSignatureError):
        L.License.from_dict(env)


def test_rejects_missing_payload_fields():
    priv, _ = _keypair()
    env = _sign_license(priv, "k1")
    del env["payload"]["tier"]
    with pytest.raises(L.LicenseMalformedError):
        L.License.from_dict(env)


def test_rejects_invalid_tier():
    priv, _ = _keypair()
    env = _sign_license(priv, "k1")
    env["payload"]["tier"] = "enterprise_platinum"
    with pytest.raises(L.LicenseMalformedError):
        L.License.from_dict(env)


# ── Signature verification ───────────────────────────────────────────


def test_valid_signature_verifies():
    priv, pub = _keypair()
    env = _sign_license(priv, "k1")
    lic = L.License.from_dict(env)
    lic.verify_signature({"k1": pub})  # should not raise


def test_tampered_payload_fails_verification():
    priv, pub = _keypair()
    env = _sign_license(priv, "k1", tier=L.PRO_TIER)
    env["payload"]["tier"] = L.TEAM_TIER  # attacker ups their tier
    lic = L.License.from_dict(env)
    with pytest.raises(L.LicenseSignatureError):
        lic.verify_signature({"k1": pub})


def test_wrong_key_id_fails_verification():
    priv, pub = _keypair()
    env = _sign_license(priv, "k1")
    lic = L.License.from_dict(env)
    with pytest.raises(L.LicenseSignatureError):
        lic.verify_signature({"k2": pub})


def test_wrong_public_key_fails_verification():
    priv, _ = _keypair()
    _, other_pub = _keypair()
    env = _sign_license(priv, "k1")
    lic = L.License.from_dict(env)
    with pytest.raises(L.LicenseSignatureError):
        lic.verify_signature({"k1": other_pub})


def test_malformed_signature_base64_is_rejected():
    priv, pub = _keypair()
    env = _sign_license(priv, "k1")
    env["signature"] = "!!! not base64 !!!"
    lic = L.License.from_dict(env)
    with pytest.raises(L.LicenseSignatureError):
        lic.verify_signature({"k1": pub})


# ── Expiry + grace ───────────────────────────────────────────────────


def test_not_expired_when_in_future():
    priv, pub = _keypair()
    env = _sign_license(priv, "k1", expires_in_days=30)
    lic = L.License.from_dict(env)
    assert lic.is_expired() is False
    assert lic.is_in_grace_period() is False


def test_expired_in_grace_window():
    priv, pub = _keypair()
    env = _sign_license(priv, "k1", expires_in_days=-1)
    lic = L.License.from_dict(env)
    assert lic.is_expired() is True
    assert lic.is_in_grace_period(grace_days=14) is True


def test_expired_beyond_grace_window():
    priv, pub = _keypair()
    env = _sign_license(priv, "k1", expires_in_days=-100)
    lic = L.License.from_dict(env)
    assert lic.is_expired() is True
    assert lic.is_in_grace_period(grace_days=14) is False


def test_load_and_verify_expired_beyond_grace_drops_to_free(isolated_nae_dir):
    priv, pub = _keypair()
    env = _sign_license(priv, "k1", tier=L.PRO_TIER, expires_in_days=-100)
    _install_license(env, isolated_nae_dir)

    v = L.load_and_verify(
        current_version="1.0.0",
        public_keys={"k1": pub},
    )
    assert v.effective_tier == L.FREE_TIER
    assert v.expired is True
    assert v.in_grace is False
    assert any("downgraded" in w for w in v.warnings)


def test_load_and_verify_in_grace_retains_tier(isolated_nae_dir):
    priv, pub = _keypair()
    env = _sign_license(priv, "k1", tier=L.PRO_TIER, expires_in_days=-3)
    _install_license(env, isolated_nae_dir)

    v = L.load_and_verify(
        current_version="1.0.0",
        public_keys={"k1": pub},
        grace_days=14,
    )
    assert v.effective_tier == L.PRO_TIER
    assert v.expired is True
    assert v.in_grace is True


# ── Version constraints ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "version,constraint,ok",
    [
        ("1.0.0", ">=1.0.0,<2.0.0", True),
        ("1.9.9", ">=1.0.0,<2.0.0", True),
        ("2.0.0", ">=1.0.0,<2.0.0", False),
        ("0.9.9", ">=1.0.0,<2.0.0", False),
        ("1.2.3", "==1.2.3", True),
        ("1.2.4", "==1.2.3", False),
        ("1.2.4", "!=1.2.3", True),
        ("1.5.0", ">=1.0.0", True),
        ("0.9.0", ">=1.0.0", False),
    ],
)
def test_version_constraints(version, constraint, ok):
    assert L._version_satisfies(version, constraint) is ok


def test_version_mismatch_raises(isolated_nae_dir):
    priv, pub = _keypair()
    env = _sign_license(priv, "k1", version_constraint=">=2.0.0")
    _install_license(env, isolated_nae_dir)

    with pytest.raises(L.LicenseVersionMismatchError):
        L.load_and_verify(current_version="1.0.0", public_keys={"k1": pub})


def test_version_constraint_none_passes(isolated_nae_dir):
    priv, pub = _keypair()
    env = _sign_license(priv, "k1", version_constraint=None)
    _install_license(env, isolated_nae_dir)

    v = L.load_and_verify(current_version="1.0.0", public_keys={"k1": pub})
    assert v.effective_tier == L.PRO_TIER


# ── Tiers & features ─────────────────────────────────────────────────


def test_free_tier_feature_list_is_subset_of_pro():
    free = set(L.TIER_FEATURES[L.FREE_TIER])
    pro = set(L.TIER_FEATURES[L.PRO_TIER])
    team = set(L.TIER_FEATURES[L.TEAM_TIER])
    assert free.issubset(pro)
    assert pro.issubset(team)


def test_pro_license_grants_multi_symbol_but_not_team_features():
    priv, pub = _keypair()
    env = _sign_license(priv, "k1", tier=L.PRO_TIER)
    lic = L.License.from_dict(env)
    lic.verify_signature({"k1": pub})
    assert lic.allows_feature("backtest_multi_symbol") is True
    assert lic.allows_feature("walkforward") is True
    assert lic.allows_feature("structured_json_logs") is False


def test_extra_license_features_are_additive():
    priv, pub = _keypair()
    env = _sign_license(
        priv,
        "k1",
        tier=L.FREE_TIER,
        extra_features=("beta_feature_x",),
    )
    lic = L.License.from_dict(env)
    assert "beta_feature_x" in lic.licensed_features()


# ── Load-effective behaviour (free tier fallback) ────────────────────


def test_load_effective_returns_free_when_no_license(isolated_nae_dir):
    v = L.load_effective(current_version="1.0.0", public_keys={})
    assert v.effective_tier == L.FREE_TIER
    assert v.license.payload.license_id == "FREE"


def test_load_effective_disabled_env(monkeypatch, isolated_nae_dir):
    priv, pub = _keypair()
    env = _sign_license(priv, "k1")
    _install_license(env, isolated_nae_dir)

    monkeypatch.setenv("NAE_DISABLE_LICENSE", "1")
    v = L.load_effective(current_version="1.0.0", public_keys={"k1": pub})
    assert v.effective_tier == L.FREE_TIER


def test_load_effective_hard_fails_on_tampered_license(isolated_nae_dir):
    priv, pub = _keypair()
    env = _sign_license(priv, "k1")
    env["payload"]["tier"] = L.TEAM_TIER
    _install_license(env, isolated_nae_dir)

    with pytest.raises(L.LicenseSignatureError):
        L.load_effective(current_version="1.0.0", public_keys={"k1": pub})


def test_load_effective_hard_fails_on_version_mismatch(isolated_nae_dir):
    priv, pub = _keypair()
    env = _sign_license(priv, "k1", version_constraint=">=2.0.0")
    _install_license(env, isolated_nae_dir)

    with pytest.raises(L.LicenseVersionMismatchError):
        L.load_effective(current_version="1.0.0", public_keys={"k1": pub})


def test_load_effective_soft_fails_on_malformed_license(isolated_nae_dir):
    (isolated_nae_dir / "license.nae").write_text("{ not json", encoding="utf-8")
    v = L.load_effective(current_version="1.0.0", public_keys={})
    assert v.effective_tier == L.FREE_TIER


# ── Machine binding ──────────────────────────────────────────────────


def test_machine_id_is_stable():
    assert L.compute_machine_id() == L.compute_machine_id()
    assert len(L.compute_machine_id()) == 16


def test_activation_recording_round_trip(isolated_nae_dir):
    record = L.record_activation("L1", "machine-a")
    assert "machine-a" in record["machines"]
    record2 = L.record_activation("L1", "machine-b")
    assert {"machine-a", "machine-b"} == set(record2["machines"])
    assert L.deactivate_machine("L1", "machine-a") is True
    assert L.deactivate_machine("L1", "unknown") is False


def test_machine_binding_exceeded_warns_but_does_not_fail(isolated_nae_dir):
    priv, pub = _keypair()
    env = _sign_license(priv, "k1", max_machines=1)
    _install_license(env, isolated_nae_dir)

    # Pre-seed the activation store with a different machine.
    L.record_activation(env["payload"]["license_id"], "other-machine-xyz")

    v = L.load_and_verify(
        current_version="1.0.0",
        public_keys={"k1": pub},
        machine_id="this-machine",
    )
    # Tier must be preserved — binding is soft.
    assert v.effective_tier == L.PRO_TIER
    assert v.machine_bound is False
    assert any("machines" in w.lower() for w in v.warnings)


# ── FeatureGates integration ─────────────────────────────────────────


def test_feature_gates_defaults_to_free_tier(isolated_nae_dir):
    g = FeatureGates(config_path=None)
    assert g.tier == L.FREE_TIER
    assert g.feature_allowed("research_basic") is True
    assert g.feature_allowed("walkforward") is False


def test_feature_gates_with_pro_license_unlocks_paid_features(isolated_nae_dir):
    priv, pub = _keypair()
    env = _sign_license(priv, "k1", tier=L.PRO_TIER)
    _install_license(env, isolated_nae_dir)

    v = L.load_and_verify(current_version="1.0.0", public_keys={"k1": pub})
    g = FeatureGates(config_path=None)
    g.attach_license(v)

    assert g.tier == L.PRO_TIER
    assert g.feature_allowed("walkforward") is True
    g.require_feature("walkforward")  # should not raise


def test_feature_gates_require_feature_raises_on_missing_tier(isolated_nae_dir):
    g = FeatureGates(config_path=None)
    with pytest.raises(L.FeatureNotLicensedError):
        g.require_feature("walkforward")


# ── The critical invariant ──────────────────────────────────────────


def test_license_never_affects_execution_allowed(isolated_nae_dir):
    """
    SAFETY CRITICAL: licensing must never enable execution. Even with a
    top-tier license attached, execution_allowed is still driven 100%
    by the user's config. Regressing this would be a compliance
    incident, so we pin it with a dedicated test.
    """
    priv, pub = _keypair()
    env = _sign_license(priv, "k1", tier=L.TEAM_TIER, extra_features=("team_seats",))
    _install_license(env, isolated_nae_dir)

    v = L.load_and_verify(current_version="1.0.0", public_keys={"k1": pub})
    g = FeatureGates(config_path=None)
    g.attach_license(v)

    assert g.tier == L.TEAM_TIER  # license did attach
    # ...but execution remains off because the user's config said so.
    assert g.execution_allowed is False
    with pytest.raises(PermissionError):
        g.require_execution()
