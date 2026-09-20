"""RAG API: upload, query, list, delete docs."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KnowledgeDoc
from app.deps import get_db
from app.rag.ingest import ingest_file
from app.rag.qdrant_store import get_qdrant_store
from app.rag.retriever import get_retriever, invalidate_lexical_index
from app.schemas.rag import (
    DocOut,
    QueryHit,
    QueryRequest,
    QueryResponse,
    UploadResponse,
)
from app.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/upload", response_model=UploadResponse)
async def upload_doc(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """Upload a file, chunk it, embed, and store in Qdrant."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")

    doc_id = uuid4()

    # Ingest into Qdrant
    try:
        result = await ingest_file(
            filename=file.filename,
            content=content,
            doc_id=str(doc_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("upload_failed", filename=file.filename)
        raise HTTPException(status_code=500, detail=f"ingest failed: {e}")

    # Persist metadata
    doc = KnowledgeDoc(
        id=doc_id,
        filename=file.filename,
        source_type="upload",
        mime_type=file.content_type,
        size_bytes=len(content),
        chunk_count=result.chunk_count,
        qdrant_point_ids=result.point_ids,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return UploadResponse(
        doc=DocOut(
            id=doc.id,
            filename=doc.filename,
            source_type=doc.source_type,
            mime_type=doc.mime_type,
            size_bytes=doc.size_bytes,
            chunk_count=doc.chunk_count,
            created_at=doc.created_at,
        ),
        message=f"ingested {result.chunk_count} chunks",
    )


@router.post("/query", response_model=QueryResponse)
async def query_rag(req: QueryRequest) -> QueryResponse:
    """Query the RAG knowledge base."""
    retriever = get_retriever()
    hits = await retriever.retrieve(
        query=req.query,
        top_k=req.top_k,
        score_threshold=req.score_threshold,
        filters=req.filters,
    )
    return QueryResponse(
        query=req.query,
        hits=[QueryHit(**h) for h in hits],
        count=len(hits),
    )


@router.get("/docs")
async def list_docs(
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """List all knowledge base docs."""
    rows = (
        await db.execute(
            sa_select(KnowledgeDoc).order_by(KnowledgeDoc.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    items = [
        DocOut(
            id=d.id,
            filename=d.filename,
            source_type=d.source_type,
            mime_type=d.mime_type,
            size_bytes=d.size_bytes,
            chunk_count=d.chunk_count,
            created_at=d.created_at,
        )
        for d in rows
    ]
    return {"items": [i.model_dump(mode="json") for i in items], "count": len(items)}


@router.delete("/docs/{doc_id}")
async def delete_doc(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a doc and its vectors from Qdrant."""
    doc = (
        await db.execute(sa_select(KnowledgeDoc).where(KnowledgeDoc.id == doc_id))
    ).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="doc not found")

    # Remove from Qdrant
    try:
        store = get_qdrant_store()
        store.delete_by_doc_id(str(doc_id))
        invalidate_lexical_index()
    except Exception as e:
        logger.warning("qdrant_delete_failed", error=str(e))
        invalidate_lexical_index()

    await db.delete(doc)
    await db.commit()
    return {"deleted": 1, "id": str(doc_id)}


@router.get("/stats")
async def rag_stats() -> dict:
    """RAG stats."""
    store = get_qdrant_store()
    return {
        "qdrant_collection": store.collection,
        "total_points": store.count(),
        "healthy": store.health_check(),
    }