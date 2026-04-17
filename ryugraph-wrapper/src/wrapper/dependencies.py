"""FastAPI dependency injection providers.

Provides dependency functions for injecting services and configuration
into route handlers.

Authentication trusts X-Username header per ADR-104.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from wrapper.config import Settings, get_settings
from wrapper.logging import get_logger

# Import types for Annotated aliases
# Note: These are imported conditionally to avoid circular imports at module level
# but the dependency functions return the actual types from app state
if TYPE_CHECKING:
    from wrapper.clients.control_plane import ControlPlaneClient
    from wrapper.services.algorithm import AlgorithmService
    from wrapper.services.database import DatabaseService
    from wrapper.services.lock import LockService

logger = get_logger(__name__)


# =============================================================================
# Configuration Dependencies
# =============================================================================


def get_app_settings() -> Settings:
    """Get application settings.

    Returns cached singleton Settings instance.
    """
    return get_settings()


# =============================================================================
# Service Dependencies
# =============================================================================


def get_database_service(request: Request) -> DatabaseService:
    """Get the database service from app state.

    Args:
        request: FastAPI request object.

    Returns:
        DatabaseService instance.

    Raises:
        HTTPException: If service not initialized.
    """
    service = getattr(request.app.state, "db_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service not initialized",
        )
    return service


def get_lock_service(request: Request) -> LockService:
    """Get the lock service from app state.

    Args:
        request: FastAPI request object.

    Returns:
        LockService instance.

    Raises:
        HTTPException: If service not initialized.
    """
    service = getattr(request.app.state, "lock_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lock service not initialized",
        )
    return service


def get_algorithm_service(request: Request) -> AlgorithmService:
    """Get the algorithm service from app state.

    Args:
        request: FastAPI request object.

    Returns:
        AlgorithmService instance.

    Raises:
        HTTPException: If service not initialized.
    """
    service = getattr(request.app.state, "algorithm_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Algorithm service not initialized",
        )
    return service


def get_control_plane_client(request: Request) -> ControlPlaneClient:
    """Get the Control Plane client from app state.

    Args:
        request: FastAPI request object.

    Returns:
        ControlPlaneClient instance.

    Raises:
        HTTPException: If client not initialized.
    """
    client = getattr(request.app.state, "control_plane_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Control Plane client not initialized",
        )
    return client


# =============================================================================
# User Context Dependencies
# =============================================================================


def get_user_id(
    x_username: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[str | None, Header()] = None,
) -> str:
    """Extract user ID from request headers.

    Per ADR-105, `X-Username` is the canonical identity header sent by the SDK.
    `X-User-ID` is accepted as a deprecated alias for backward compatibility with
    legacy callers. Prefer `X-Username` in new code and clients.

    Args:
        x_username: Canonical identity from X-Username header (ADR-105).
        x_user_id: Legacy identity from X-User-ID header (deprecated alias).

    Returns:
        User ID or "anonymous" if neither header is present.
    """
    return x_username or x_user_id or "anonymous"


def get_user_name(
    x_username: Annotated[str | None, Header()] = None,
    x_user_name: Annotated[str | None, Header()] = None,
) -> str:
    """Extract username from request headers.

    Per ADR-105, `X-Username` is the canonical identity header sent by the SDK.
    `X-User-Name` is accepted as a deprecated alias for backward compatibility.

    Args:
        x_username: Canonical identity from X-Username header (ADR-105).
        x_user_name: Legacy username from X-User-Name header (deprecated alias).

    Returns:
        Username or "anonymous" if neither header is present.
    """
    return x_username or x_user_name or "anonymous"


# =============================================================================
# Authorization Dependencies
# =============================================================================


async def require_algorithm_permission(
    request: Request,
    x_username: Annotated[str | None, Header()] = None,
) -> str:
    """Check user has permission to execute algorithms on this instance.

    Fast path: if username matches instance owner, allow immediately.
    Slow path: call control plane /authorize endpoint for cross-instance access.

    Args:
        request: FastAPI request (used to access app-state ControlPlaneClient).
        x_username: Username from X-Username header.

    Returns:
        Username if authorized.

    Raises:
        HTTPException: 403 if not authorized.
    """
    username = x_username or "anonymous"

    # Fast path: instance owner always allowed (no network call)
    owner_id = get_settings().wrapper.owner_id
    if username == owner_id:
        return username

    # Slow path: ask control plane if this user can access this instance
    settings = get_settings()
    cp_url = settings.wrapper.control_plane_url
    # The CP authorize endpoint expects url_slug, not integer instance_id
    url_slug = settings.wrapper.url_slug

    if not url_slug:
        logger.warning("No url_slug configured — cannot authorize cross-instance access")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "CONFIGURATION_ERROR", "message": "Permission denied: wrapper url_slug not configured for cross-instance auth"}},
        )

    try:
        import httpx

        authorize_url = f"{cp_url}/api/internal/instances/{url_slug}/authorize"
        logger.info("authorize_cross_instance", url=authorize_url, username=username, url_slug=url_slug)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                authorize_url,
                params={"username": username},
                timeout=5.0,
            )
            logger.info("authorize_response", status_code=resp.status_code, body=resp.text[:200])
            if resp.status_code == 200:
                data = resp.json()
                if data.get("allowed"):
                    return username
                reason = data.get("reason", "authorization denied")
                logger.warning("authorize_denied", reason=reason, username=username)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": {"code": "FORBIDDEN", "message": f"Permission denied: {reason}"}},
                )
            else:
                logger.error("authorize_failed", status_code=resp.status_code, body=resp.text[:200])
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": {"code": "AUTHORIZATION_ERROR", "message": f"Authorization check failed (HTTP {resp.status_code})"}},
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("authorize_exception", error=str(e), username=username, url_slug=url_slug)

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": {"code": "FORBIDDEN", "message": "Permission denied: authorization service unavailable"}},
    )


# =============================================================================
# Type Aliases for Common Dependencies
# =============================================================================

SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DatabaseServiceDep = Annotated["DatabaseService", Depends(get_database_service)]
LockServiceDep = Annotated["LockService", Depends(get_lock_service)]
AlgorithmServiceDep = Annotated["AlgorithmService", Depends(get_algorithm_service)]
ControlPlaneClientDep = Annotated["ControlPlaneClient", Depends(get_control_plane_client)]
UserIdDep = Annotated[str, Depends(get_user_id)]
UserNameDep = Annotated[str, Depends(get_user_name)]
AlgorithmPermissionDep = Annotated[str, Depends(require_algorithm_permission)]
