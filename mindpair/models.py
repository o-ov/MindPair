from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class RoleConfig(BaseModel):
    name: str = "产品大神张小龙"
    system_prompt: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048


class SessionCreate(BaseModel):
    title: str = "新会话"


class SessionResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    session_id: int
    role: str
    content: str
    round: int = 0


class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    round: int
    created_at: datetime

    class Config:
        from_attributes = True


class TaskSubmit(BaseModel):
    session_id: int
    task: str
    first_mover: str = "A"


class SettingsUpdate(BaseModel):
    config_a: Optional[RoleConfig] = None
    config_b: Optional[RoleConfig] = None
