from pydantic import BaseModel, Field
from typing import Optional
import uuid


class ChatRequest(BaseModel):
    prompt: str
    project_root: str = "."
    thread_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class ResumeRequest(BaseModel):
    thread_id: str
    approval: str = "approved"  # "approved" or "rejected"


class SessionResponse(BaseModel):
    thread_id: str
    title: str
    project_root: str
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    id: Optional[str] = None
    type: str
    content: str
    tool_calls: Optional[list] = None
    tool_call_id: Optional[str] = None
