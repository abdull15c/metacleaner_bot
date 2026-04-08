import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from core.database import Base


class DownloadFormat(str, enum.Enum):
    best_1080 = "best_1080"
    best_720  = "best_720"
    best_480  = "best_480"
    best_360  = "best_360"
    best_auto = "best_auto"
    mp3_320   = "mp3_320"
    mp3_192   = "mp3_192"
    m4a_best  = "m4a_best"


class SourceType(str, enum.Enum):
    upload = "upload"
    youtube = "youtube"


class JobAction(str, enum.Enum):
    clean = "clean"
    extract_audio = "extract_audio"
    screenshot = "screenshot"


class JobStatus(str, enum.Enum):
    pending = "pending"
    downloading = "downloading"
    processing = "processing"
    sending = "sending"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class BroadcastStatus(str, enum.Enum):
    draft = "draft"
    running = "running"
    paused = "paused"
    done = "done"
    failed = "failed"


class RecipientStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class LogLevel(str, enum.Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    daily_job_count: Mapped[int] = mapped_column(Integer, default=0)
    daily_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="user")
    broadcast_recipients: Mapped[list["BroadcastRecipient"]] = relationship("BroadcastRecipient", back_populates="user")


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    job_action: Mapped[JobAction] = mapped_column(Enum(JobAction), default=JobAction.clean, nullable=False)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    youtube_consent: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    youtube_consent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    original_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    processed_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    temp_original_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    temp_processed_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.pending, nullable=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_before: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metadata_after: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    cleanup_done: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    cleanup_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    user: Mapped["User"] = relationship("User", back_populates="jobs")
    reports: Mapped[list["JobReport"]] = relationship("JobReport", back_populates="job")
    __table_args__ = (Index("ix_jobs_user_status", "user_id", "status"),)


class JobReport(Base):
    __tablename__ = "job_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    job: Mapped["Job"] = relationship("Job", back_populates="reports")


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    broadcasts: Mapped[list["Broadcast"]] = relationship("Broadcast", back_populates="creator")
    settings_updates: Mapped[list["Setting"]] = relationship("Setting", back_populates="updated_by_admin")


class Broadcast(Base):
    __tablename__ = "broadcasts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[BroadcastStatus] = mapped_column(Enum(BroadcastStatus), default=BroadcastStatus.draft, nullable=False, index=True)
    target_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("admins.id"), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    creator: Mapped["Admin"] = relationship("Admin", back_populates="broadcasts")
    recipients: Mapped[list["BroadcastRecipient"]] = relationship("BroadcastRecipient", back_populates="broadcast")


class BroadcastRecipient(Base):
    __tablename__ = "broadcast_recipients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(Integer, ForeignKey("broadcasts.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[RecipientStatus] = mapped_column(Enum(RecipientStatus), default=RecipientStatus.pending, nullable=False, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    broadcast: Mapped["Broadcast"] = relationship("Broadcast", back_populates="recipients")
    user: Mapped["User"] = relationship("User", back_populates="broadcast_recipients")


class SystemLog(Base):
    __tablename__ = "system_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[LogLevel] = mapped_column(Enum(LogLevel), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class SponsorChannel(Base):
    __tablename__ = "sponsor_channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Setting(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("admins.id"), nullable=True)
    updated_by_admin: Mapped[Optional["Admin"]] = relationship("Admin", back_populates="settings_updates")


class SiteDownloadJob(Base):
    __tablename__ = "site_download_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    platform: Mapped[str] = mapped_column(String(30), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    clean_metadata: Mapped[bool] = mapped_column(Boolean, default=False)
    original_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.pending, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cleanup_done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
