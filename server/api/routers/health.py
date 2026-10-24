from __future__ import annotations

import platform

from fastapi import APIRouter

from shared.schemas import HealthOut

VERSION = "1.0.0"
router = APIRouter(tags=["salud"])


@router.get("/health", response_model=HealthOut)
def health():
    return {"estado": "ok", "version": VERSION, "so": platform.system()}
