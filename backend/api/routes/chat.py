"""Stateless AI Career Assistant chat endpoints scoped to active ephemeral session."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.agents.chat_agent import ConversationalAIAgent
from backend.api.deps import get_session_id, require_api_auth
from backend.db.session import get_db
from backend.schemas.chat import ChatMessageResponse, ChatRequest, ChatResponse
from backend.services.session_store import EphemeralChatMessage, get_session_store

router = APIRouter(prefix="/api/v1/chat", tags=["AI Assistant"], dependencies=[Depends(require_api_auth)])


@router.post("", response_model=ChatResponse)
def chat_with_assistant(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    session_key: str = Depends(get_session_id),
):
    """Answer questions using the current session's resume and verified job pool (no DB storage)."""
    sess = get_session_store().get_or_create(session_key)
    history = [
        {"role": m.role, "content": m.content}
        for m in sess.chat_messages
        if m.session_id == payload.session_id
    ]
    reply, ref_ids, used_llm = ConversationalAIAgent().answer_ephemeral(
        db=db,
        resume=sess.active_resume,
        matches_by_job=sess.active_matches,
        history=history,
        message=payload.message,
        focused_job_id=payload.job_id,
    )

    sess.chat_messages.append(
        EphemeralChatMessage(
            id=sess._next_chat_id,
            session_id=payload.session_id,
            role="user",
            content=payload.message,
            referenced_job_ids_json=ref_ids,
        )
    )
    sess._next_chat_id += 1
    sess.chat_messages.append(
        EphemeralChatMessage(
            id=sess._next_chat_id,
            session_id=payload.session_id,
            role="assistant",
            content=reply,
            referenced_job_ids_json=ref_ids,
        )
    )
    sess._next_chat_id += 1

    return ChatResponse(
        session_id=payload.session_id,
        reply=reply,
        referenced_job_ids=ref_ids,
        used_llm=used_llm,
    )


@router.get("/history", response_model=List[ChatMessageResponse])
def get_chat_history(
    session_id: str = "default",
    session_key: str = Depends(get_session_id),
):
    sess = get_session_store().get_or_create(session_key)
    rows = [m for m in sess.chat_messages if m.session_id == session_id][-100:]
    return [
        ChatMessageResponse(
            id=r.id,
            session_id=r.session_id,
            role=r.role,
            content=r.content,
            referenced_job_ids=r.referenced_job_ids_json or [],
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.delete("/history")
def clear_chat_history(
    session_id: str = "default",
    session_key: str = Depends(get_session_id),
):
    sess = get_session_store().get_or_create(session_key)
    before = len(sess.chat_messages)
    sess.chat_messages = [m for m in sess.chat_messages if m.session_id != session_id]
    return {"cleared": before - len(sess.chat_messages), "session_id": session_id}
