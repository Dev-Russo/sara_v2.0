"""Endpoint de saúde da aplicação."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Indica que o processo HTTP está respondendo."""

    return HealthResponse(status="ok", service="sara")

