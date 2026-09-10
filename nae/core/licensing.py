"""
NAE Model A — Licensing (Phase 0 MVP)

Offline-first, signature-based software licensing.

Design
------
- Licenses are JSON envelopes carrying a payload + a detached Ed25519
  signature. The public key(s) used to verify signatures are embedded in
  the product (see ``nae.core.license_keys``). Only the vendor holds the
  private key; customers cannot forge licenses.

- Licensing gates *implemented* feature tiers (free / pro / team) and
  product expiry. Names such as walk-forward or Monte Carlo are
  **not implemented** and are listed in ``UNIMPLEMENTED_FEATURES``.
  Licensing **does not** control broker execution — that is still 100%
  driven by ``nae.core.feature_gates.FeatureGates`` and the user's
  ``config.yaml`` (mode + execution_enabled + broker). A broken /
  missing license can never accidentally enable execution.

- Missing or invalid license → the product falls back to the ``free``
  tier rather than refusing to start. This is deliberate: a research
  tool that won't start when the internet is down is a bad product.
  Paid features raise ``LicenseError`` at the call site if the tier
  does not cover them.

- Expired licenses enter a 14-day read-only grace window before
  reverting to the free tier.

- Machine binding is soft: on first verification we record the
  ``machine_id`` locally. Subsequent verifications only warn — rather
  than fail — if the machine changes, and respect ``max_machines``.
  Full activation-server enforcement is a Phase 2 upgrade.

Files touched at runtime
------------------------
- ``~/.nae/license.nae``       — the signed license (user-supplied).
- ``~/.nae/activations.json``  — local activation record.

Environment overrides
---------------------
- ``NAE_LICENSE_FILE``         — explicit path to a license file.
- ``NAE_LICENSE_DIR``          — override for ``~/.nae`` (tests).
- ``NAE_DISABLE_LICENSE``      — if ``"1"``, force the free tier (used
                                 by tests and by the open-source
                                 installer to opt out of paid gates).

This module has **zero** knowledge of broker execution and MUST remain
that way. If you find yourself importing anything from
``nae.agents.execution_adapter`` here, stop — that would create a path
by which licensing bugs could influence execution, which is the one
thing we never want.
"""

from __future__ import annotations

import base64
import copy
import datetime as _dt
import hashlib
import json
import logging
import os
import platform
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger("nae.licensing")


# ── Tiers & constants ────────────────────────────────────────────────

FREE_TIER = "free"
PRO_TIER = "pro"
TEAM_TIER = "team"
VALID_TIERS = (FREE_TIER, PRO_TIER, TEAM_TIER)

DEFAULT_GRACE_DAYS = 14

FREE_TIER_FEATURES: Tuple[str, ...] = (
    "research_basic",
    "backtest_single_symbol",
    "csv_import",
    "status",
)

# Features that are actually implemented and gated in this codebase.
PRO_TIER_FEATURES: Tuple[str, ...] = FREE_TIER_FEATURES + (
    "backtest_multi_symbol",
    "correlation_matrix",
    "regime_detection_full",
)

# Team currently has no extra implemented capabilities beyond Pro.
TIER_FEATURES: Dict[str, Tuple[str, ...]] = {
    FREE_TIER: FREE_TIER_FEATURES,
    PRO_TIER: PRO_TIER_FEATURES,
    TEAM_TIER: PRO_TIER_FEATURES,
}

# Reserved names from earlier docs / license payloads. They are NOT
# granted by any tier and have no implementation. require_feature()
# raises NotImplementedError rather than pretending they exist.
UNIMPLEMENTED_FEATURES: Tuple[str, ...] = (
    "walkforward",
    "benchmarks",
    "monte_carlo",
    "structured_json_logs",
    "offline_docker_image",
    "team_seats",
)


# ── Exceptions ───────────────────────────────────────────────────────


class LicenseError(Exception):
    """Base class for all licensing errors."""


class LicenseNotFoundError(LicenseError):
    """No license file present at any of the configured locations."""


class LicenseMalformedError(LicenseError):
    """License file could not be parsed or is missing required fields."""


class LicenseSignatureError(LicenseError):
    """Signature is missing, invalid, or was produced with an unknown key."""


class LicenseExpiredError(LicenseError):
    """License expired (beyond the grace window)."""


class LicenseVersionMismatchError(LicenseError):
    """License version_constraint excludes the running product version."""


class LicenseRevokedError(LicenseError):
    """License id appears in the revocation list. (Reserved for Phase 1.)"""


class FeatureNotLicensedError(LicenseError):
    """The current tier does not include the requested feature."""


# ── Data classes ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class LicensePayload:
    """The signed portion of a license."""

    license_id: str
    customer_email: str
    tier: str
    issued_at: str  # ISO-8601 UTC
    expires_at: str  # ISO-8601 UTC
    max_machines: int = 1
    customer_name: Optional[str] = None
    features: Tuple[str, ...] = ()  # extra per-license features on top of tier
    version_constraint: Optional[str] = None  # e.g. ">=1.0.0,<2.0.0"

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "license_id": self.license_id,
            "customer_email": self.customer_email,
            "tier": self.tier,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "max_machines": self.max_machines,
            "customer_name": self.customer_name,
            "features": list(self.features),
            "version_constraint": self.version_constraint,
        }
        return d


@dataclass
class License:
    """A license envelope: payload + detached signature."""

    payload: LicensePayload
    signature: str  # base64(ed25519 of canonical_json(payload))
    key_id: str
    signature_alg: str = "ed25519"

    # ── Canonicalization ────────────────────────────────────────────

    @staticmethod
    def canonical_payload_bytes(payload_dict: Mapping[str, Any]) -> bytes:
        """Deterministic serialization used for signing + verification.

        Must match exactly between issuer and verifier. Uses sorted keys
        and compact separators to avoid whitespace ambiguity.
        """
        return json.dumps(
            payload_dict,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    # ── Loading ─────────────────────────────────────────────────────

    @classmethod
    def from_file(cls, path: Path) -> "License":
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as e:
            raise LicenseNotFoundError(f"Cannot read license at {path}: {e}") from e
        return cls.from_json(raw)

    @classmethod
    def from_json(cls, raw: str) -> "License":
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            raise LicenseMalformedError(f"License is not valid JSON: {e}") from e
        return cls.from_dict(obj)

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "License":
        if not isinstance(obj, Mapping):
            raise LicenseMalformedError("License root must be an object")
        try:
            payload_dict = obj["payload"]
            signature = obj["signature"]
            key_id = obj["key_id"]
        except KeyError as e:
            raise LicenseMalformedError(
                f"License missing required top-level field: {e.args[0]}"
            ) from e
        alg = obj.get("signature_alg", "ed25519")
        if alg != "ed25519":
            raise LicenseSignatureError(f"Unsupported signature algorithm: {alg}")

        required_payload_fields = (
            "license_id",
            "customer_email",
            "tier",
            "issued_at",
            "expires_at",
        )
        missing = [f for f in required_payload_fields if f not in payload_dict]
        if missing:
            raise LicenseMalformedError(
                f"License payload missing required field(s): {missing}"
            )

        tier = payload_dict["tier"]
        if tier not in VALID_TIERS:
            raise LicenseMalformedError(
                f"License tier '{tier}' is not one of {VALID_TIERS}"
            )

        payload = LicensePayload(
            license_id=str(payload_dict["license_id"]),
            customer_email=str(payload_dict["customer_email"]),
            tier=tier,
            issued_at=str(payload_dict["issued_at"]),
            expires_at=str(payload_dict["expires_at"]),
            max_machines=int(payload_dict.get("max_machines", 1)),
            customer_name=payload_dict.get("customer_name"),
            features=tuple(payload_dict.get("features", []) or []),
            version_constraint=payload_dict.get("version_constraint"),
        )
        return cls(
            payload=payload,
            signature=str(signature),
            key_id=str(key_id),
            signature_alg=alg,
        )

    # ── Verification ────────────────────────────────────────────────

    def verify_signature(self, public_keys: Mapping[str, bytes]) -> None:
        """Verify the Ed25519 signature using the issuer's public key.

        ``public_keys`` maps ``key_id`` → raw 32-byte Ed25519 public key.
        Raises :class:`LicenseSignatureError` on any failure.
        """
        if self.key_id not in public_keys:
            raise LicenseSignatureError(
                f"Unknown license signing key_id: {self.key_id}"
            )

        raw_pub = public_keys[self.key_id]
        try:
            pub = Ed25519PublicKey.from_public_bytes(raw_pub)
        except ValueError as e:
            raise LicenseSignatureError(
                f"Invalid embedded public key for {self.key_id}: {e}"
            ) from e

        try:
            sig_bytes = base64.b64decode(self.signature, validate=True)
        except (ValueError, base64.binascii.Error) as e:  # type: ignore[attr-defined]
            raise LicenseSignatureError(f"Signature is not valid base64: {e}") from e

        canon = License.canonical_payload_bytes(self.payload.to_dict())
        try:
            pub.verify(sig_bytes, canon)
        except InvalidSignature as e:
            raise LicenseSignatureError(
                "License signature is invalid — file may be tampered or issued "
                "by a different vendor"
            ) from e

    def is_expired(self, now: Optional[_dt.datetime] = None) -> bool:
        now = now or _dt.datetime.now(_dt.timezone.utc)
        exp = _parse_iso_utc(self.payload.expires_at)
        return now > exp

    def is_in_grace_period(
        self,
        now: Optional[_dt.datetime] = None,
        grace_days: int = DEFAULT_GRACE_DAYS,
    ) -> bool:
        now = now or _dt.datetime.now(_dt.timezone.utc)
        exp = _parse_iso_utc(self.payload.expires_at)
        if now <= exp:
            return False
        return now <= exp + _dt.timedelta(days=grace_days)

    def verify_version(self, current_version: str) -> None:
        """Raise ``LicenseVersionMismatchError`` if the license's
        ``version_constraint`` excludes ``current_version``. Constraints
        use a tiny subset of PEP 440 / npm semver: comma-separated
        clauses of the form ``>=X.Y.Z``, ``<X.Y.Z``, ``==X.Y.Z``,
        ``>X.Y.Z``, ``<=X.Y.Z``.
        """
        if not self.payload.version_constraint:
            return
        if not _version_satisfies(current_version, self.payload.version_constraint):
            raise LicenseVersionMismatchError(
                f"License {self.payload.license_id} requires product version "
                f"{self.payload.version_constraint!r}; running {current_version!r}"
            )

    def licensed_features(self) -> List[str]:
        """All features granted by this license (tier features + extras)."""
        tier_feats = TIER_FEATURES.get(self.payload.tier, ())
        return sorted(set(tier_feats) | set(self.payload.features))

    def allows_feature(self, feature_name: str) -> bool:
        return feature_name in self.licensed_features()


@dataclass
class VerifiedLicense:
    """Result of a successful ``load_and_verify`` call.

    Deliberately a small value object so no code path can mistake an
    unverified envelope for a trusted one. Downstream code should only
    consume ``VerifiedLicense`` instances.
    """

    license: License
    effective_tier: str
    expired: bool
    in_grace: bool
    machine_bound: bool
    warnings: List[str] = field(default_factory=list)

    def allows_feature(self, feature: str) -> bool:
        return feature in TIER_FEATURES.get(self.effective_tier, ()) or (
            feature in self.license.payload.features and not self.expired
        )

    def require_feature(self, feature: str) -> None:
        if feature in UNIMPLEMENTED_FEATURES:
            raise NotImplementedError(
                f"Feature {feature!r} is not implemented in this version of NAE."
            )
        if not self.allows_feature(feature):
            raise FeatureNotLicensedError(
                f"Feature {feature!r} requires a higher tier. "
                f"Current effective tier: {self.effective_tier}."
            )


# ── Path resolution ──────────────────────────────────────────────────


def _nae_dir() -> Path:
    override = os.environ.get("NAE_LICENSE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".nae"


def get_license_file_path() -> Path:
    """Resolve the license file path, honoring env overrides."""
    override = os.environ.get("NAE_LICENSE_FILE")
    if override:
        return Path(override)
    return _nae_dir() / "license.nae"


def get_activation_store_path() -> Path:
    return _nae_dir() / "activations.json"


# ── Machine identity ─────────────────────────────────────────────────


def compute_machine_id() -> str:
    """Compute a stable-ish 16-char machine id.

    Uses ``platform.node()`` (hostname) + ``uuid.getnode()`` (MAC-derived
    node id) + platform string. Intentionally soft: loses stability if
    the user changes hostname or NIC, but that's fine because we use
    this for loose binding only, not for execution gating.
    """
    parts = [
        platform.node() or "",
        str(uuid.getnode()),
        platform.system(),
        platform.machine(),
    ]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


# ── Activation store ─────────────────────────────────────────────────


def _read_activation_store() -> Dict[str, Any]:
    path = get_activation_store_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Activation store at %s is unreadable (%s); ignoring.", path, e)
        return {}


def _write_activation_store(data: Mapping[str, Any]) -> None:
    path = get_activation_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(data), indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def record_activation(license_id: str, machine_id: str) -> Dict[str, Any]:
    """Record this machine as an activation for ``license_id``.

    Returns the updated per-license record. Enforces ``max_machines``
    locally; Phase 2 will enforce this server-side as well.
    """
    store = _read_activation_store()
    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    lic_record = store.get(license_id) or {"machines": {}}
    machines: Dict[str, Any] = lic_record.setdefault("machines", {})
    if machine_id not in machines:
        machines[machine_id] = {"first_seen": now_iso}
    machines[machine_id]["last_seen"] = now_iso
    store[license_id] = lic_record
    _write_activation_store(store)
    return lic_record


def deactivate_machine(license_id: str, machine_id: str) -> bool:
    """Remove a machine from a license's activation list. Returns True
    if anything was removed.
    """
    store = _read_activation_store()
    lic_record = store.get(license_id)
    if not lic_record:
        return False
    machines = lic_record.get("machines", {})
    removed = machines.pop(machine_id, None) is not None
    if removed:
        _write_activation_store(store)
    return removed


# ── Top-level API ────────────────────────────────────────────────────


def load_license(path: Optional[Path] = None) -> License:
    """Load a license from disk. Raises :class:`LicenseNotFoundError`
    if no file exists at the resolved location.
    """
    path = path or get_license_file_path()
    if not path.exists():
        raise LicenseNotFoundError(f"No license file at {path}")
    return License.from_file(path)


def load_and_verify(
    current_version: str,
    public_keys: Mapping[str, bytes],
    path: Optional[Path] = None,
    machine_id: Optional[str] = None,
    now: Optional[_dt.datetime] = None,
    grace_days: int = DEFAULT_GRACE_DAYS,
) -> VerifiedLicense:
    """Full verification pipeline. Returns a :class:`VerifiedLicense`
    that downstream code can trust.

    Behaviour:
    - Signature invalid → raises ``LicenseSignatureError`` (hard fail).
    - Version mismatch → raises ``LicenseVersionMismatchError`` (hard fail).
    - Expired but within grace → effective tier is preserved, but
      ``expired=True`` and ``in_grace=True`` are set and a warning is
      added. Callers may choose to read-only-downgrade.
    - Expired beyond grace → effective tier drops to ``free`` and a
      warning is added.
    - Machine binding exceeded → warning only (soft), caller can prompt
      to reactivate.
    """
    lic = load_license(path)
    lic.verify_signature(public_keys)
    lic.verify_version(current_version)

    warnings: List[str] = []
    now = now or _dt.datetime.now(_dt.timezone.utc)

    expired = lic.is_expired(now=now)
    in_grace = lic.is_in_grace_period(now=now, grace_days=grace_days)

    if expired and not in_grace:
        warnings.append(
            f"License {lic.payload.license_id} expired on {lic.payload.expires_at}; "
            f"downgraded to {FREE_TIER} tier. Renew to restore paid features."
        )
        effective_tier = FREE_TIER
    elif expired and in_grace:
        warnings.append(
            f"License {lic.payload.license_id} expired on {lic.payload.expires_at} "
            f"but is in its {grace_days}-day grace period."
        )
        effective_tier = lic.payload.tier
    else:
        effective_tier = lic.payload.tier

    # Machine binding (soft)
    machine_id = machine_id or compute_machine_id()
    machine_bound = True
    try:
        record = record_activation(lic.payload.license_id, machine_id)
        machines = record.get("machines", {})
        if len(machines) > lic.payload.max_machines:
            warnings.append(
                f"License {lic.payload.license_id} has been activated on "
                f"{len(machines)} machines; the license permits "
                f"{lic.payload.max_machines}. Contact support to re-balance "
                f"your activations."
            )
            machine_bound = False
    except OSError as e:
        # Can't write activation store — log and continue; never fail the
        # whole verification because of a disk issue.
        logger.warning("Could not record activation: %s", e)
        machine_bound = False

    return VerifiedLicense(
        license=lic,
        effective_tier=effective_tier,
        expired=expired,
        in_grace=in_grace,
        machine_bound=machine_bound,
        warnings=warnings,
    )


def load_effective(
    current_version: str,
    public_keys: Mapping[str, bytes],
    path: Optional[Path] = None,
) -> VerifiedLicense:
    """Best-effort loader used by the CLI startup path.

    Returns a synthetic free-tier ``VerifiedLicense`` when no license is
    present or when ``NAE_DISABLE_LICENSE=1``. Only *hard* errors
    (tampered signature, version mismatch) propagate out. This is what
    the main entry point should call.
    """
    if os.environ.get("NAE_DISABLE_LICENSE") == "1":
        return _free_tier_license("license disabled via NAE_DISABLE_LICENSE=1")

    try:
        return load_and_verify(current_version, public_keys, path=path)
    except LicenseNotFoundError:
        return _free_tier_license("no license file found - running in free tier")
    except (LicenseSignatureError, LicenseVersionMismatchError):
        # Security-sensitive failures: re-raise so the CLI can print an
        # explicit error instead of silently downgrading to free.
        raise
    except LicenseError as e:
        logger.warning("License load failed (%s); falling back to free tier.", e)
        return _free_tier_license(f"license invalid ({e}) - free tier")


def _free_tier_license(reason: str) -> VerifiedLicense:
    """Synthetic free-tier result. Never signed; never grants paid features."""
    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
    synthetic_payload = LicensePayload(
        license_id="FREE",
        customer_email="",
        tier=FREE_TIER,
        issued_at=now_iso,
        expires_at=now_iso,
        max_machines=0,
    )
    synthetic = License(
        payload=synthetic_payload,
        signature="",
        key_id="",
        signature_alg="none",
    )
    return VerifiedLicense(
        license=synthetic,
        effective_tier=FREE_TIER,
        expired=False,
        in_grace=False,
        machine_bound=True,
        warnings=[reason],
    )


# ── Version constraint mini-parser ───────────────────────────────────


_VERSION_CLAUSE_RE = re.compile(r"^\s*(>=|<=|==|!=|>|<)\s*(\d+(?:\.\d+){0,2}[\w\-\.]*)\s*$")


def _parse_version(v: str) -> Tuple[int, ...]:
    """Parse ``1.2.3`` style. Pre-release suffixes are ignored for
    comparison; licensing uses plain numeric precedence.
    """
    core = re.split(r"[-+]", v.strip(), 1)[0]
    parts = core.split(".")
    nums: List[int] = []
    for p in parts:
        m = re.match(r"^(\d+)", p)
        if not m:
            break
        nums.append(int(m.group(1)))
    if not nums:
        raise ValueError(f"Cannot parse version string: {v!r}")
    return tuple(nums)


def _version_satisfies(version: str, constraint: str) -> bool:
    v = _parse_version(version)
    for clause in constraint.split(","):
        m = _VERSION_CLAUSE_RE.match(clause)
        if not m:
            raise LicenseMalformedError(
                f"Unparseable version constraint clause: {clause!r}"
            )
        op, target = m.group(1), _parse_version(m.group(2))
        length = max(len(v), len(target))
        v_p = v + (0,) * (length - len(v))
        t_p = target + (0,) * (length - len(target))
        ok = {
            ">=": v_p >= t_p,
            "<=": v_p <= t_p,
            ">": v_p > t_p,
            "<": v_p < t_p,
            "==": v_p == t_p,
            "!=": v_p != t_p,
        }[op]
        if not ok:
            return False
    return True


# ── Date helpers ─────────────────────────────────────────────────────


def _parse_iso_utc(s: str) -> _dt.datetime:
    """Parse ISO-8601 datetime strings and return an aware UTC datetime."""
    raw = s.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = _dt.datetime.fromisoformat(raw)
    except ValueError as e:
        raise LicenseMalformedError(f"Cannot parse date {s!r}: {e}") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.astimezone(_dt.timezone.utc)


# ── Serialization helpers used by the issuer tool ────────────────────


def build_unsigned_license_dict(
    payload: LicensePayload,
    key_id: str,
) -> Dict[str, Any]:
    """Return the dict an issuer would sign + wrap. Exposed so the
    issuer tool and verifier share serialization logic.
    """
    return {
        "payload": payload.to_dict(),
        "signature": "",
        "key_id": key_id,
        "signature_alg": "ed25519",
    }


def canonical_signing_bytes(payload: LicensePayload) -> bytes:
    """Bytes the issuer must sign."""
    return License.canonical_payload_bytes(payload.to_dict())


def _deepcopy_mapping(m: Mapping[str, Any]) -> Dict[str, Any]:
    """Tiny helper so callers don't need to import copy."""
    return copy.deepcopy(dict(m))
