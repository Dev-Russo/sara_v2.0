"""Ponto único de importação do metadata para Alembic."""

from app.models import (  # noqa: F401
    CommandExecution,
    ConfirmationRequest,
    ProcessedUpdate,
    Task,
    User,
)
from app.models.base import Base

metadata = Base.metadata
