from __future__ import annotations

from typing import Any

import httpx
from fastapi import Depends, Header, HTTPException, status
from jose import jwt
from jose.exceptions import JWTError

from .config import Settings, get_settings


def require_publisher_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not x_api_key or x_api_key != settings.publisher_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
        )


class AdvertiserIdentity:
    def __init__(self, user_id: str, wallet_address: str | None = None) -> None:
        self.user_id = user_id
        self.wallet_address = wallet_address


def _jwks_url(settings: Settings) -> str:
    return settings.privy_jwks_url.replace("{app_id}", settings.privy_app_id)


_jwks_cache: dict[str, Any] = {}


def _fetch_jwks(settings: Settings) -> dict[str, Any]:
    if _jwks_cache:
        return _jwks_cache
    with httpx.Client(timeout=10.0) as c:
        r = c.get(_jwks_url(settings))
        r.raise_for_status()
        _jwks_cache.update(r.json())
    return _jwks_cache


def _verify_privy_jwt(token: str, settings: Settings) -> dict[str, Any]:
    try:
        jwks = _fetch_jwks(settings)
        return jwt.decode(
            token,
            key=jwks,
            algorithms=["ES256"],
            audience=settings.privy_app_id,
            issuer="privy.io",
            options={"verify_at_hash": False},
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid Privy token: {e}",
        ) from e


def require_advertiser(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> AdvertiserIdentity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="empty token",
        )

    claims = _verify_privy_jwt(token, settings)
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token missing sub",
        )
    # wallet_address is resolved lazily via PrivyClient in routers that need it
    return AdvertiserIdentity(user_id=user_id, wallet_address=None)
