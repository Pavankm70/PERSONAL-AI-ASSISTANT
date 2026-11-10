import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, Conversation, Message
from app.middleware.auth_middleware import get_current_user
from app.schemas import ChatMessageRequest, ChatMessageResponse
from app.agent.graph import agent_orchestrator

router = APIRouter(prefix="", tags=["Chat & Conversations"])

@router.post("/chat")
async def chat_endpoint(
    req: ChatMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Find or create conversation
    conv = None
    if req.conversationId:
        conv = db.query(Conversation).filter(
            Conversation.id == req.conversationId,
            Conversation.user_id == user.id
        ).first()

    if not conv:
        conv = Conversation(user_id=user.id, title=req.message[:30])
        db.add(conv)
        db.commit()
        db.refresh(conv)

    conv_id = conv.id

    # Save user message
    user_msg = Message(
        conversation_id=conv_id,
        role="user",
        content=req.message
    )
    db.add(user_msg)
    db.commit()

    # Orchestrate agent execution
    assistant_result = await agent_orchestrator.run(
        user_id=user.id,
        query=req.message,
        conversation_id=conv_id,
        db=db
    )

    # Check for generation / API error: DO NOT persist as a successful assistant message!
    if assistant_result.get("status") == "error":
        err_info = assistant_result.get("error", {})
        err_status = err_info.get("statusCode") or 503
        if err_status not in (400, 401, 403, 429, 500, 502, 503, 504):
            err_status = 503
        raise HTTPException(
            status_code=err_status,
            detail=err_info.get("message", assistant_result.get("content", "Gemini service is temporarily unavailable."))
        )

    # Save successful assistant message
    asst_msg = Message(
        conversation_id=conv_id,
        role="assistant",
        content=assistant_result["content"],
        tool_executions=assistant_result.get("toolExecutions", []),
        citations=assistant_result.get("citations", []),
        suggested_action=assistant_result.get("suggestedAction")
    )
    db.add(asst_msg)
    db.commit()
    db.refresh(asst_msg)

    return {
        "id": asst_msg.id,
        "conversationId": conv_id,
        "role": "assistant",
        "content": asst_msg.content,
        "createdAt": asst_msg.created_at.isoformat(),
        "toolExecutions": asst_msg.tool_executions or [],
        "citations": asst_msg.citations or [],
        "suggestedAction": asst_msg.suggested_action
    }

@router.get("/conversations")
def list_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    convs = db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).all()
    return [
        {
            "id": c.id,
            "title": c.title,
            "createdAt": c.created_at.isoformat(),
            "updatedAt": c.updated_at.isoformat()
        }
        for c in convs
    ]

@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    msgs = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.created_at.asc()).all()
    return {
        "id": conv.id,
        "title": conv.title,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "toolExecutions": m.tool_executions or [],
                "citations": m.citations or [],
                "suggestedAction": m.suggested_action,
                "createdAt": m.created_at.isoformat()
            }
            for m in msgs
        ]
    }

@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user.id).delete()
    db.commit()
    return {"success": True}

@router.delete("/chat/history")
@router.delete("/conversations")
def purge_conversation_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Transactionally purges all conversations and messages belonging to the authenticated user.
    """
    user_convs = db.query(Conversation).filter(Conversation.user_id == user.id).all()
    conv_ids = [c.id for c in user_convs]

    if conv_ids:
        db.query(Message).filter(Message.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
        db.query(Conversation).filter(Conversation.user_id == user.id).delete(synchronize_session=False)
        db.commit()

    return {
        "success": True,
        "message": f"Purged {len(conv_ids)} conversation(s) from persistent database."
    }
