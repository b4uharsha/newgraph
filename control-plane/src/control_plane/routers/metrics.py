"""Prometheus metrics endpoint router."""

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["Metrics"])


@router.get("/metrics")
async def get_metrics() -> Response:
    """Expose Prometheus metrics.

    Returns metrics in Prometheus text format for scraping.
    This endpoint is typically scraped by Prometheus or compatible systems.
    """
    metrics_data = generate_latest()
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)
