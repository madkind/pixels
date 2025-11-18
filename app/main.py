import asyncio
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Set
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .models import (
    PixelUpdate, BulkPixelUpdate, WebSocketMessage, PixelAck, PixelReject,
    CanvasState, Palette, PaletteColor, AuditLogEntry, RegionLock, UserSession
)
from .database import dynamodb_canvas
from .rate_limiter import check_pixel_rate_limit


limiter = Limiter(key_func=get_remote_address)
active_connections: Set[WebSocket] = set()
pixel_update_queue: List[PixelUpdate] = []
batch_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global batch_task
    batch_task = asyncio.create_task(batch_pixel_updates())
    yield
    if batch_task:
        batch_task.cancel()
        try:
            await batch_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Pixels Collaborative Canvas",
    description="Real-time collaborative pixel art application",
    version="0.1.0",
    lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def batch_pixel_updates():
    while True:
        await asyncio.sleep(0.05)  # 50ms batching window
        
        if not pixel_update_queue:
            continue
        
        batch = pixel_update_queue.copy()
        pixel_update_queue.clear()
        
        try:
            await process_pixel_batch(batch)
        except Exception as e:
            print(f"Error processing pixel batch: {e}")


async def process_pixel_batch(batch: List[PixelUpdate]):
    canvas_state = dynamodb_canvas.get_canvas_state()
    
    if not canvas_state:
        bitmap = np.zeros((900, 900, 3), dtype=np.uint8)
    else:
        bitmap = np.frombuffer(canvas_state.bitmap, dtype=np.uint8).reshape((900, 900, 3))
    
    acks = []
    rejects = []
    
    for update in batch:
        if dynamodb_canvas.is_position_locked(update.x, update.y):
            rejects.append(PixelReject(x=update.x, y=update.y, reason="Position locked"))
            continue
        
        color_rgb = tuple(int(update.color[i:i+2], 16) for i in (1, 3, 5))
        
        if update.tool == "eraser":
            bitmap[update.y, update.x] = [255, 255, 255]  # White background
        else:
            bitmap[update.y, update.x] = color_rgb
        
        acks.append(PixelAck(x=update.x, y=update.y, color=update.color, success=True))
        
        audit_entry = AuditLogEntry(
            timestamp=datetime.now(timezone.utc),
            user_id=update.user_id,
            action="pixel_update",
            details={"x": update.x, "y": update.y, "color": update.color, "tool": update.tool}
        )
        dynamodb_canvas.add_audit_entry(audit_entry)
    
    bitmap_bytes = bitmap.tobytes()
    hash_value = hashlib.sha256(bitmap_bytes).hexdigest()
    dynamodb_canvas.save_canvas_state(bitmap_bytes, hash_value)
    
    message = WebSocketMessage(
        type="pixel:bulk_update",
        data={
            "pixels": [{"x": p.x, "y": p.y, "color": p.color} for p in batch],
            "hash": hash_value
        },
        timestamp=datetime.now(timezone.utc)
    )
    
    await broadcast_message(message)


async def broadcast_message(message: WebSocketMessage):
    if not active_connections:
        return
    
    message_str = message.model_dump_json()
    disconnected = set()
    
    for connection in active_connections:
        try:
            await connection.send_text(message_str)
        except:
            disconnected.add(connection)
    
    active_connections.difference_update(disconnected)


@app.get("/")
async def root():
    return {"message": "Pixels Collaborative Canvas API"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/canvas", response_model=CanvasState)
@limiter.limit("10/minute")
async def get_canvas(request: Request):
    canvas_state = dynamodb_canvas.get_canvas_state()
    
    if not canvas_state:
        bitmap = np.zeros((900, 900, 3), dtype=np.uint8)
        bitmap_bytes = bitmap.tobytes()
        hash_value = hashlib.sha256(bitmap_bytes).hexdigest()
        
        canvas_state = CanvasState(
            width=900,
            height=900,
            bitmap=bitmap_bytes,
            hash=hash_value,
            last_updated=datetime.now(timezone.utc)
        )
        
        dynamodb_canvas.save_canvas_state(bitmap_bytes, hash_value)
    
    return canvas_state


@app.get("/canvas/image")
@limiter.limit("5/minute")
async def get_canvas_image(request: Request):
    canvas_state = dynamodb_canvas.get_canvas_state()
    
    if not canvas_state:
        bitmap = np.zeros((900, 900, 3), dtype=np.uint8)
    else:
        bitmap = np.frombuffer(canvas_state.bitmap, dtype=np.uint8).reshape((900, 900, 3))
    
    from PIL import Image
    import io
    
    image = Image.fromarray(bitmap, 'RGB')
    img_buffer = io.BytesIO()
    image.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    return Response(content=img_buffer.getvalue(), media_type="image/png")


@app.get("/palette", response_model=Palette)
async def get_palette():
    colors = [
        "#000000", "#FFFFFF", "#FF0000", "#00FF00", "#0000FF", "#FFFF00",
        "#FF00FF", "#00FFFF", "#800000", "#008000", "#000080", "#808000",
        "#800080", "#008080", "#C0C0C0", "#808080", "#FFA500", "#A52A2A",
        "#FFD700", "#4B0082", "#F0E68C", "#ADD8E6", "#F08080", "#E0FFFF",
        "#FAFAD2", "#D3D3D3", "#90EE90", "#FFB6C1", "#FFA07A", "#20B2AA",
        "#87CEEB", "#778899"
    ]
    
    palette_colors = [PaletteColor(color=color) for color in colors]
    return Palette(colors=palette_colors)


@app.get("/audit", response_model=List[AuditLogEntry])
@limiter.limit("5/minute")
async def get_audit_log(request: Request, limit: int = 100):
    return dynamodb_canvas.get_audit_log(limit)


@app.get("/locks", response_model=List[RegionLock])
async def get_region_locks():
    return dynamodb_canvas.get_region_locks()


@app.post("/locks")
async def create_region_lock(lock: RegionLock):
    dynamodb_canvas.add_region_lock(lock)
    return {"message": "Region lock created"}


@app.delete("/locks/{x1}/{y1}/{x2}/{y2}")
async def remove_region_lock(x1: int, y1: int, x2: int, y2: int):
    dynamodb_canvas.remove_region_lock(x1, y1, x2, y2)
    return {"message": "Region lock removed"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "pixel:update":
                pixel_data = message_data["data"]
                user_id = pixel_data.get("userId", "anonymous")
                
                # Check rate limits
                allowed, message = await check_pixel_rate_limit(user_id)
                if not allowed:
                    await websocket.send_text(json.dumps({
                        "type": "pixel:reject",
                        "data": {"reason": message, "timestamp": datetime.utcnow().isoformat()}
                    }))
                    continue
                
                update = PixelUpdate(
                    x=pixel_data["x"],
                    y=pixel_data["y"],
                    color=pixel_data["color"],
                    tool=pixel_data.get("tool", "brush"),
                    client_timestamp=datetime.fromisoformat(pixel_data["clientTimestamp"]),
                    user_id=user_id
                )
                
                pixel_update_queue.append(update)
                
            elif message_data.get("type") == "heartbeat":
                await websocket.send_text(json.dumps({
                    "type": "heartbeat:ack",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }))
                
    except WebSocketDisconnect:
        active_connections.discard(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        active_connections.discard(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
