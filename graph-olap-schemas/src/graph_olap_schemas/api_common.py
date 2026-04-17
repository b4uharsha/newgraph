"""
Common API schemas for requests and responses.

Defines shared patterns used across all API endpoints:
- Response wrappers (data, meta, error)
- Pagination
- Error responses

All structures derived from docs/system-design/api.common.spec.md.
"""

from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Meta(BaseModel):
    """
    Response metadata included in all API responses.

    From api.common.spec.md:
    ```json
    "meta": {
      "request_id": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```
    """

    request_id: Annotated[
        str | None,
        Field(
            default=None,
            description="Unique request identifier for tracing",
            examples=["550e8400-e29b-41d4-a716-446655440000"],
        ),
    ]


class PaginationMeta(Meta):
    """
    Metadata for paginated list responses.

    From api.common.spec.md:
    ```json
    "meta": {
      "request_id": "req-uuid",
      "total": 150,
      "offset": 0,
      "limit": 50
    }
    ```
    """

    total: Annotated[
        int,
        Field(
            ge=0,
            description="Total number of matching records",
            examples=[150],
        ),
    ]

    offset: Annotated[
        int,
        Field(
            ge=0,
            description="Current offset (records skipped)",
            examples=[0, 50, 100],
        ),
    ]

    limit: Annotated[
        int,
        Field(
            ge=1,
            le=100,
            description="Current limit (records per page)",
            examples=[50],
        ),
    ]


class ErrorDetail(BaseModel):
    """
    Error detail structure for API error responses.

    From api.common.spec.md:
    ```json
    "error": {
      "code": "ERROR_CODE",
      "message": "Human-readable description",
      "details": {
        "field": "specific_field",
        "reason": "additional context"
      }
    }
    ```

    Error codes from api.common.spec.md Error Codes Reference section.
    """

    code: Annotated[
        str,
        Field(
            description="Machine-readable error code",
            examples=[
                "VALIDATION_FAILED",
                "UNAUTHORIZED",
                "PERMISSION_DENIED",
                "RESOURCE_NOT_FOUND",
                "RESOURCE_LOCKED",
                "CONCURRENCY_LIMIT_EXCEEDED",
                "INVALID_STATE",
            ],
        ),
    ]

    message: Annotated[
        str,
        Field(
            description="Human-readable error description",
            examples=["Request body validation failed", "User not authorized for operation"],
        ),
    ]

    details: Annotated[
        dict[str, Any],
        Field(
            default_factory=dict,
            description="Additional context about the error",
            examples=[{"field": "name", "reason": "Name is required"}],
        ),
    ]


class ErrorResponse(BaseModel):
    """
    Standard error response format.

    From api.common.spec.md:
    ```json
    {
      "error": {
        "code": "ERROR_CODE",
        "message": "Human-readable description",
        "details": {...}
      },
      "meta": {
        "request_id": "req-uuid"
      }
    }
    ```
    """

    error: ErrorDetail
    meta: Meta = Field(default_factory=Meta)


class DataResponse(BaseModel, Generic[T]):
    """
    Standard single-resource response wrapper.

    From api.common.spec.md:
    ```json
    {
      "data": {...},
      "meta": {
        "request_id": "req-uuid"
      }
    }
    ```
    """

    data: T
    meta: Meta = Field(default_factory=Meta)


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standard paginated list response wrapper.

    From api.common.spec.md:
    ```json
    {
      "data": [{...}, {...}],
      "meta": {
        "request_id": "req-uuid",
        "total": 150,
        "offset": 0,
        "limit": 50
      }
    }
    ```
    """

    data: list[T]
    meta: PaginationMeta


class PaginationParams(BaseModel):
    """
    Pagination query parameters for list endpoints.

    From api.common.spec.md:
    | Parameter | Type | Default | Max | Description |
    |-----------|------|---------|-----|-------------|
    | offset | integer | 0 | - | Records to skip |
    | limit | integer | 50 | 100 | Records to return |
    """

    offset: Annotated[
        int,
        Field(
            default=0,
            ge=0,
            description="Number of records to skip",
            examples=[0, 50, 100],
        ),
    ]

    limit: Annotated[
        int,
        Field(
            default=50,
            ge=1,
            le=100,
            description="Number of records to return (max 100)",
            examples=[50, 25, 100],
        ),
    ]


class SortParams(BaseModel):
    """
    Sorting query parameters for list endpoints.

    From api.common.spec.md Sorting Parameters section.
    """

    sort_by: Annotated[
        str,
        Field(
            default="created_at",
            description="Field to sort by",
            examples=["created_at", "updated_at", "name"],
        ),
    ]

    sort_order: Annotated[
        str,
        Field(
            default="desc",
            pattern=r"^(asc|desc)$",
            description="Sort order: 'asc' or 'desc'",
            examples=["desc", "asc"],
        ),
    ]


class FilterParams(BaseModel):
    """
    Common filter parameters for list endpoints.

    From api.common.spec.md Common Filter Parameters section.
    """

    owner: Annotated[
        str | None,
        Field(
            default=None,
            description="Filter by owner username",
            examples=["alice.smith"],
        ),
    ]

    search: Annotated[
        str | None,
        Field(
            default=None,
            max_length=255,
            description="Text search on name and description",
            examples=["customer"],
        ),
    ]

    created_after: Annotated[
        str | None,
        Field(
            default=None,
            pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
            description="Filter by created_at >= value (ISO 8601 UTC)",
            examples=["2025-01-01T00:00:00Z"],
        ),
    ]

    created_before: Annotated[
        str | None,
        Field(
            default=None,
            pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
            description="Filter by created_at <= value (ISO 8601 UTC)",
            examples=["2025-12-31T23:59:59Z"],
        ),
    ]

    status: Annotated[
        str | None,
        Field(
            default=None,
            description="Filter by resource status",
            examples=["ready", "running", "failed"],
        ),
    ]
