"""Contratos da confirmação humana persistida."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ConfirmationView(BaseModel):
    id: UUID
    command_id: UUID
    user_id: UUID
    command_type: str
    summary: str
    status: Literal["pending", "confirmed", "cancelled", "expired", "consumed"]
    expires_at: datetime

