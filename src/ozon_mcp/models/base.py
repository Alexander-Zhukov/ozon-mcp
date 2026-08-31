"""Shared base for all output DTOs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OzonModel(BaseModel):
    """Base DTO: tolerant of extra upstream fields, populated by field name."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")
