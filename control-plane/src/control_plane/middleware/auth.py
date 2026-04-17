# Backward-compatible re-exports from identity.py (renamed per ADR-104).
# New code should import from control_plane.middleware.identity.
from control_plane.middleware.identity import (  # noqa: F401
    CurrentUser,
    RequireAdmin,
    RequireOps,
    get_request_user,
    get_request_user as get_current_user,  # alias for backward compat
    require_role,
)
