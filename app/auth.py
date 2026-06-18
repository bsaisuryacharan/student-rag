# app/auth.py
import json
import logging
from typing import Annotated

import httpx
import jwt
from jwt.algorithms import ECAlgorithm, RSAAlgorithm
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger("app.auth")
_bearer = HTTPBearer()
_bearer_optional = HTTPBearer(auto_error=False)

_ALG_TO_CLASS = {"ES256": ECAlgorithm, "RS256": RSAAlgorithm}


async def _load_jwks(request: Request) -> dict[str, dict]:
    """Fetch JWKS from Supabase and cache by kid in app state."""
    if not hasattr(request.app.state, "_jwks"):
        settings = request.app.state.settings
        if not settings.supabase_url:
            raise HTTPException(status_code=500, detail="Auth not configured (SUPABASE_URL missing)")
        url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
        request.app.state._jwks = {k["kid"]: k for k in resp.json()["keys"]}
        logger.info("Loaded %d JWKS key(s) from Supabase", len(request.app.state._jwks))
    return request.app.state._jwks


async def _verify_raw_token(raw_token: str, request: Request) -> dict:
    _unauth = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        header = jwt.get_unverified_header(raw_token)
        kid, alg = header.get("kid"), header.get("alg", "ES256")

        jwks = await _load_jwks(request)
        key_data = jwks.get(kid)
        if not key_data:
            logger.warning("Unknown kid: %s", kid)
            raise _unauth

        algo_cls = _ALG_TO_CLASS.get(alg)
        if not algo_cls:
            logger.warning("Unsupported alg: %s", alg)
            raise _unauth

        public_key = algo_cls.from_jwk(json.dumps(key_data))
        return jwt.decode(raw_token, public_key, algorithms=[alg], options={"verify_aud": False})
    except jwt.ExpiredSignatureError:
        raise _unauth
    except jwt.PyJWTError as exc:
        logger.debug("JWT verification failed: %s", exc)
        raise _unauth


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_optional)],
    token: str | None = Query(default=None, include_in_schema=False),
) -> dict:
    # Accept token from Authorization header OR ?token= query param (for SSE browser/curl URLs)
    raw = (credentials.credentials if credentials else None) or token
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await _verify_raw_token(raw, request)


async def require_admin(
    user: Annotated[dict, Depends(get_current_user)],
    request: Request,
) -> dict:
    settings = request.app.state.settings
    admin_emails = {e.strip() for e in settings.admin_emails.split(",") if e.strip()}
    if user.get("email") not in admin_emails:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
