"""Chatbot endpoint: `POST /chat`.

Thin HTTP wrapper around ``ChatbotModule.handle_query`` — see
app/ai/chatbot.py for the retrieval-augmented grounding and graceful
degradation behavior.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.chatbot import ChatbotModule
from app.database import get_db

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    response: str


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    # A fresh ChatbotModule per request is cheap — conversation history lives
    # in the module-level dict in app/ai/chatbot.py, not on this instance, so
    # it persists across requests regardless.
    chatbot = ChatbotModule()
    response_text = await chatbot.handle_query(payload.session_id, payload.message, db)
    return ChatResponse(response=response_text)
