"""JWT helpers for proof_context tokens.

A proof_context is the self-contained authorization we hand to the publisher on
every winning bid. The publisher echoes it back on the `/proof` call; we verify
the signature and settle without needing to store bid state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from jose import jwt
from jose.exceptions import JWTError


class ProofContextError(RuntimeError):
    pass


@dataclass
class ProofContextClaims:
    campaign_id: str
    bid_id: str
    wallet_id: str
    nonce: str
    created_at: int
    amount_usdc: float
    # device_id is optional so JWTs minted before the field was added still
    # decode cleanly (no migration needed for outstanding bids). /bid populates
    # it from imp.ext.device_id; /proof persists it on the settlement so the
    # dashboard can resolve DMA + venue per play.
    device_id: str | None = None


def encode_proof_context(claims: ProofContextClaims, secret: str, algorithm: str = "HS256") -> str:
    return jwt.encode(asdict(claims), secret, algorithm=algorithm)


def decode_proof_context(token: str, secret: str, algorithm: str = "HS256") -> ProofContextClaims:
    try:
        data = jwt.decode(token, secret, algorithms=[algorithm])
    except JWTError as e:
        raise ProofContextError(f"invalid proof_context: {e}") from e
    required = {"campaign_id", "bid_id", "wallet_id", "nonce", "created_at", "amount_usdc"}
    missing = required - data.keys()
    if missing:
        raise ProofContextError(f"proof_context missing fields: {missing}")
    device_id = data.get("device_id")
    return ProofContextClaims(
        campaign_id=data["campaign_id"],
        bid_id=data["bid_id"],
        wallet_id=data["wallet_id"],
        nonce=data["nonce"],
        created_at=int(data["created_at"]),
        amount_usdc=float(data["amount_usdc"]),
        device_id=str(device_id) if device_id else None,
    )
