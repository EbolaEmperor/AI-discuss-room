# server/schemas.py
from datetime import datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, Field, ConfigDict


class RoomCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    problem: str = Field(min_length=1)
    max_rounds: int = Field(default=20, ge=1, le=1000)


class RoomProblemUpdate(BaseModel):
    problem: str = Field(min_length=1)


class RoomSummary(BaseModel):
    id: int
    title: str
    status: str
    participant_count: int
    post_count: int

    model_config = ConfigDict(from_attributes=True)


class RoomDetail(RoomSummary):
    problem: str
    max_rounds: int
    closed_proof_id: Optional[int] = None
    created_at: datetime
    closed_at: Optional[datetime] = None


class ParticipantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    role: Literal["producer", "reviewer"]


class ParticipantRegistered(BaseModel):
    participant_id: int
    token: str
    name: str
    role: str


class ParticipantSummary(BaseModel):
    name: str
    role: str
    has_published_first: bool


class PostCreate(BaseModel):
    type: Literal["proof", "revision", "comment", "agree"]
    parent_id: Optional[int] = None
    body: Optional[str] = None


class PostMeta(BaseModel):
    id: int
    type: str
    author: str
    parent_id: Optional[int] = None
    superseded_by: Optional[int] = None
    ts: datetime


class PostDetail(PostMeta):
    body: Optional[str] = None


class ProofSummary(BaseModel):
    id: int
    author: str
    agree_count: int
    agreed_by_me: bool


class StatusMe(BaseModel):
    name: str
    role: str
    has_published_first: bool
    first_post_id: Optional[int] = None
    first_post_at: Optional[datetime] = None


class StatusRoom(BaseModel):
    id: int
    title: str
    state: str
    participant_count: int
    post_count: int
    max_rounds: int


class StatusResponse(BaseModel):
    room: StatusRoom
    me: StatusMe
    new_since_my_last_read: List[PostMeta]
    current_proofs: List[ProofSummary]


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[dict] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class AuditEvent(BaseModel):
    kind: Literal["post", "read"]
    ts: datetime
    by: str
    detail: dict
