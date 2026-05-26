# server/models.py
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey, Enum, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from server.db import Base


class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    problem = Column(Text, nullable=False)
    status = Column(
        Enum("open", "closed_consensus", "closed_capped", "closed_manual", name="room_status"),
        nullable=False,
        default="open",
    )
    max_rounds = Column(Integer, nullable=False, default=20)
    closed_proof_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    participants = relationship("Participant", back_populates="room", cascade="all, delete-orphan")
    posts = relationship("Post", back_populates="room",
                         foreign_keys="Post.room_id", cascade="all, delete-orphan")


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("room_id", "name", name="uq_room_name"),
        UniqueConstraint("token", name="uq_token"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    name = Column(String(64), nullable=False)
    role = Column(Enum("producer", "reviewer", name="participant_role"), nullable=False)
    token = Column(String(64), nullable=False)
    registered_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    first_post_at = Column(DateTime, nullable=True)
    unregistered_at = Column(DateTime, nullable=True)

    room = relationship("Room", back_populates="participants")
    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan")
    reads = relationship("Read", back_populates="participant", cascade="all, delete-orphan")


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        Index("idx_room_created", "room_id", "created_at"),
        Index("idx_room_type", "room_id", "type"),
        Index("idx_parent", "parent_id"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("participants.id"), nullable=False)
    type = Column(Enum("proof", "revision", "comment", "agree", name="post_type"), nullable=False)
    parent_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    body = Column(Text, nullable=True)
    superseded_by = Column(Integer, ForeignKey("posts.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    room = relationship("Room", foreign_keys=[room_id], back_populates="posts")
    author = relationship("Participant", back_populates="posts")
    parent = relationship("Post", foreign_keys=[parent_id], remote_side="Post.id")
    superseder = relationship("Post", foreign_keys=[superseded_by], remote_side="Post.id")


class Read(Base):
    __tablename__ = "reads"
    __table_args__ = (
        Index("idx_participant_post", "participant_id", "post_id"),
        Index("idx_post", "post_id"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    participant_id = Column(Integer, ForeignKey("participants.id"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    read_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    participant = relationship("Participant", back_populates="reads")
    post = relationship("Post")


class AdminUser(Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_admin_username"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
