"""Skills API: list, get, invoke."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.llm import get_llm_client
from app.schemas.skill import SkillInfo, SkillInvokeRequest, SkillInvokeResponse
from app.skills.base import SkillContext
from app.skills.registry import get_registry

router = APIRouter()


@router.get("/")
async def list_skills() -> dict:
    """List all available skills."""
    registry = get_registry()
    items = [
        SkillInfo(
            name=s.name,
            description=s.description,
            trigger=getattr(s, "trigger", None),
            parameters=getattr(s, "parameters", {"type": "object", "properties": {}}),
            source="builtin",
        )
        for s in registry.list()
    ]
    return {
        "items": [i.model_dump() for i in items],
        "count": len(items),
    }


@router.get("/{name}")
async def get_skill(name: str) -> dict:
    """Get a single skill's info."""
    registry = get_registry()
    skill = registry.get(name)
    if not skill:
        # try by trigger
        for s in registry.list():
            if s.trigger == f"/{name}":
                skill = s
                break
    if not skill:
        raise HTTPException(status_code=404, detail=f"skill not found: {name}")
    return SkillInfo(
        name=skill.name,
        description=skill.description,
        trigger=getattr(skill, "trigger", None),
        parameters=getattr(skill, "parameters", {"type": "object", "properties": {}}),
        source="builtin",
    ).model_dump()


@router.post("/invoke", response_model=SkillInvokeResponse)
async def invoke(req: SkillInvokeRequest) -> SkillInvokeResponse:
    """Invoke a skill directly with JSON arguments."""
    registry = get_registry()
    skill = registry.get(req.name)
    if not skill:
        for s in registry.list():
            if s.trigger == f"/{req.name}":
                skill = s
                break
    if not skill:
        raise HTTPException(status_code=404, detail=f"skill not found: {req.name}")

    ctx = SkillContext(llm=get_llm_client())
    try:
        result = await skill.invoke(ctx, **req.arguments)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return SkillInvokeResponse(name=skill.name, result=result or "")