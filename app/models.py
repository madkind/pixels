from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class Tool(str, Enum):
    BRUSH = "brush"
    ERASER = "eraser"


class PixelUpdate(BaseModel):
    x: int = Field(ge=0, lt=900)
    y: int = Field(ge=0, lt=900)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    tool: Tool = Tool.BRUSH
    client_timestamp: datetime
    user_id: Optional[str] = None


class BulkPixelUpdate(BaseModel):
    pixels: List[PixelUpdate]


class WebSocketMessage(BaseModel):
    type: str
    data: Dict[str, Any]
    timestamp: datetime


class PixelAck(BaseModel):
    x: int
    y: int
    color: str
    success: bool
    reason: Optional[str] = None


class PixelReject(BaseModel):
    x: int
    y: int
    reason: str


class CanvasState(BaseModel):
    width: int = 900
    height: int = 900
    bitmap: bytes  # Compressed image data
    hash: str
    last_updated: datetime


class PaletteColor(BaseModel):
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    name: Optional[str] = None


class Palette(BaseModel):
    colors: List[PaletteColor]
    max_colors: int = 32


class AuditLogEntry(BaseModel):
    timestamp: datetime
    user_id: Optional[str]
    action: str
    details: Dict[str, Any]
    ip_address: Optional[str] = None


class RegionLock(BaseModel):
    x1: int = Field(ge=0, lt=900)
    y1: int = Field(ge=0, lt=900)
    x2: int = Field(ge=0, lt=900)
    y2: int = Field(ge=0, lt=900)
    locked_by: str
    reason: Optional[str] = None
    created_at: datetime


class UserSession(BaseModel):
    session_id: str
    user_id: Optional[str]
    name: Optional[str]
    created_at: datetime
    last_active: datetime
    ip_address: str
