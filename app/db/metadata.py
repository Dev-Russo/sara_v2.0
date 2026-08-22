"""Ponto único de importação do metadata para Alembic."""

from app.models import CommandExecution, ConfirmationRequest, Task, User  # noqa: F401
from app.models.base import Base

metadata = Base.metadata
