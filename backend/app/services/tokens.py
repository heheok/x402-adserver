"""JWT helpers for proof_context tokens.

A proof_context is the self-contained authorization we hand to the publisher on
every winning bid. The publisher echoes it back on the `/proof` call; we verify
the signature and settle without needing to store bid state.

Session 16.9: `amount_micro` (int microUSDC) replaces `amount_usdc` (float).
A `v` claim version field is included; v=2 is the current schema. Old in-flight
JWTs minted before this change carry `amount_usdc` (no `v`) and will fail to
decode — that's fine because the TTL window covers the deploy.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from jose import jwt
from jose.exceptions import JWTError


PROOF_CONTEXT_VERSION = 2


class ProofContextError(RuntimeError):
    pass


@dataclass
class ProofContextClaims:
    campaign_id: str
    bid_id: str
    wallet_id: str
    nonce: str
    created_at: int
    amount_micro: int
    # device_id is optional so JWTs minted before the field was added still
    # decode cleanly (no migration needed for outstanding bids). /bid populates
    # it from imp.ext.device_id; /proof persists it on the settlement so the
    # dashboard can resolve DMA + venue per play.
    device_id: str | None = None
    v: int = PROOF_CONTEXT_VERSION


def encode_proof_context(claims: ProofContextClaims, secret: str, algorithm: str = "HS256") -> str:
    return jwt.encode(asdict(claims), secret, algorithm=algorithm)


def decode_proof_context(token: str, secret: str, algorithm: str = "HS256") -> ProofContextClaims:
    try:
        data = jwt.decode(token, secret, algorithms=[algorithm])
    except JWTError as e:
        raise ProofContextError(f"invalid proof_context: {e}") from e
    required = {"campaign_id", "bid_id", "wallet_id", "nonce", "created_at", "amount_micro"}
    missing = required - data.keys()
    if missing:
        raise ProofContextError(f"proof_context missing fields: {missing}")
    version = int(data.get("v", 1))
    if version != PROOF_CONTEXT_VERSION:
        raise ProofContextError(
            f"proof_context version mismatch: got v{version}, expected v{PROOF_CONTEXT_VERSION}"
        )
    device_id = data.get("device_id")
    return ProofContextClaims(
        campaign_id=data["campaign_id"],
        bid_id=data["bid_id"],
        wallet_id=data["wallet_id"],
        nonce=data["nonce"],
        created_at=int(data["created_at"]),
        amount_micro=int(data["amount_micro"]),
        device_id=str(device_id) if device_id else None,
        v=version,
    )
