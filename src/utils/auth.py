# src/utils/auth.py

import os

from fastapi import Header, HTTPException

from src.utils.logger import logger

_API_KEY_ENV_VAR = "INGESTION_API_KEY"
_APP_ENV_ENV_VAR = "APP_ENV"


def _check_startup_auth(
    api_key: str | None,
    app_env: str,
    api_key_env_var: str = _API_KEY_ENV_VAR,
) -> None:
    """
    Fail closed, not open: outside a `development` environment, refuse to
    start at all without an API key rather than silently serving
    unauthenticated traffic. `APP_ENV` defaults to "development" so the
    existing no-env-vars-needed local dev workflow keeps working
    unchanged -- production deployments must set APP_ENV explicitly (to
    anything other than "development") to opt into this check, at which
    point a missing key is a startup-time RuntimeError, not a runtime
    surprise. Matters here specifically because this service and the
    sibling RAG_Project_1 API share one vector store -- an
    unauthenticated /ingest can poison the index the RAG side trusts,
    making auth on that side alone pointless. See docs/05-roadmap.md.
    """

    if api_key:
        return

    if app_env != "development":
        raise RuntimeError(
            f"{api_key_env_var} is not set and {_APP_ENV_ENV_VAR}={app_env!r} "
            f"(not 'development') -- refusing to start unauthenticated in a "
            f"non-dev environment. Set {api_key_env_var}, or explicitly set "
            f"{_APP_ENV_ENV_VAR}=development if this really is local dev."
        )

    logger.warning(
        f"{api_key_env_var} is not set -- /ingest is running "
        f"UNAUTHENTICATED. This is only allowed because "
        f"{_APP_ENV_ENV_VAR}=development (the default). Set "
        f"{api_key_env_var} before deploying anywhere else -- this will "
        f"refuse to start without it outside a dev environment."
    )


_API_KEY = os.getenv(_API_KEY_ENV_VAR)
_check_startup_auth(_API_KEY, os.getenv(_APP_ENV_ENV_VAR, "development"))


def require_api_key(x_api_key: str | None = Header(default=None)):
    """
    FastAPI dependency enforcing a shared-secret API key via the
    X-API-Key header. A no-op (allows everything) only if
    INGESTION_API_KEY isn't configured *and* APP_ENV=development -- see
    `_check_startup_auth` above, which refuses to even start otherwise.

    Intentionally minimal: one shared key, no per-client identity, no
    rotation. See docs/05-roadmap.md.
    """

    if _API_KEY is None:
        return

    if x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="invalid or missing API key")
