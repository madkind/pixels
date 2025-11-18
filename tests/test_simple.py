import pytest
import json
from unittest.mock import patch, Mock
from datetime import datetime, timezone


class TestBasicFunctionality:
    """Test basic functionality without complex mocking."""

    def test_root_endpoint(self):
        """Test the root endpoint returns API info."""
        from fastapi.testclient import TestClient
        from app.main import app
        
        with TestClient(app) as client:
            response = client.get("/")
            assert response.status_code == 200
            assert "message" in response.json()
            assert "Pixels Collaborative Canvas" in response.json()["message"]

    def test_health_check(self):
        """Test the health check endpoint."""
        from fastapi.testclient import TestClient
        from app.main import app
        
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "timestamp" in data

    def test_palette_endpoint(self):
        """Test getting the color palette."""
        from fastapi.testclient import TestClient
        from app.main import app
        
        with TestClient(app) as client:
            response = client.get("/palette")
            assert response.status_code == 200
            
            data = response.json()
            assert "colors" in data
            assert len(data["colors"]) == 32  # Default palette size
            assert data["max_colors"] == 32
            
            # Check color format
            for color in data["colors"]:
                assert "color" in color
                assert color["color"].startswith("#")
                assert len(color["color"]) == 7

    @patch('app.database.dynamodb_canvas')
    @patch('app.redis_cache.redis_cache')
    def test_models_validation(self, mock_redis, mock_dynamo):
        """Test Pydantic model validation."""
        from app.models import PixelUpdate, CanvasState, RegionLock
        
        # Test valid pixel update
        pixel_data = {
            "x": 100,
            "y": 200,
            "color": "#FF0000",
            "tool": "brush",
            "client_timestamp": datetime.now(timezone.utc),
            "user_id": "user123"
        }
        pixel = PixelUpdate(**pixel_data)
        assert pixel.x == 100
        assert pixel.y == 200
        assert pixel.color == "#FF0000"
        assert pixel.tool == "brush"
        
        # Test invalid coordinates
        with pytest.raises(ValueError):
            PixelUpdate(**{**pixel_data, "x": 999})
        
        # Test invalid color
        with pytest.raises(ValueError):
            PixelUpdate(**{**pixel_data, "color": "red"})

    def test_rate_limiter_basic(self):
        """Test basic rate limiter functionality."""
        from app.rate_limiter import WebSocketRateLimiter
        
        limiter = WebSocketRateLimiter()
        
        # Test initial state
        assert limiter.capacity == 10
        assert limiter.refill_rate == 10.0
        assert limiter.burst_capacity == 20

    @patch('app.database.dynamodb_canvas')
    def test_websocket_connection(self, mock_dynamo):
        """Test WebSocket connection and heartbeat."""
        from fastapi.testclient import TestClient
        from app.main import app
        
        mock_dynamo.is_position_locked.return_value = False
        
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as websocket:
                # Send heartbeat
                websocket.send_text(json.dumps({
                    "type": "heartbeat"
                }))
                
                # Receive heartbeat ack
                data = websocket.receive_text()
                message = json.loads(data)
                assert message["type"] == "heartbeat:ack"
                assert "timestamp" in message

    def test_imports(self):
        """Test that all modules can be imported."""
        from app.main import app
        from app.models import PixelUpdate, CanvasState
        from app.database import dynamodb_canvas
        from app.redis_cache import redis_cache
        from app.rate_limiter import ws_rate_limiter
        
        assert app is not None
        assert PixelUpdate is not None
        assert CanvasState is not None
        assert dynamodb_canvas is not None
        assert redis_cache is not None
        assert ws_rate_limiter is not None

    def test_pixel_update_model(self):
        """Test pixel update model creation and validation."""
        from app.models import PixelUpdate, Tool
        
        # Test valid pixel update
        pixel = PixelUpdate(
            x=100,
            y=200,
            color="#FF0000",
            tool=Tool.BRUSH,
            client_timestamp=datetime.now(timezone.utc),
            user_id="user123"
        )
        
        assert pixel.x == 100
        assert pixel.y == 200
        assert pixel.color == "#FF0000"
        assert pixel.tool == Tool.BRUSH
        assert pixel.user_id == "user123"

    def test_canvas_state_model(self):
        """Test canvas state model creation."""
        from app.models import CanvasState
        
        canvas = CanvasState(
            width=900,
            height=900,
            bitmap=b"test_bitmap_data",
            hash="test_hash_123",
            last_updated=datetime.now(timezone.utc)
        )
        
        assert canvas.width == 900
        assert canvas.height == 900
        assert canvas.bitmap == b"test_bitmap_data"
        assert canvas.hash == "test_hash_123"

    def test_region_lock_model(self):
        """Test region lock model creation."""
        from app.models import RegionLock
        
        lock = RegionLock(
            x1=50,
            y1=50,
            x2=100,
            y2=100,
            locked_by="moderator123",
            reason="Test region",
            created_at=datetime.now(timezone.utc)
        )
        
        assert lock.x1 == 50
        assert lock.y1 == 50
        assert lock.x2 == 100
        assert lock.y2 == 100
        assert lock.locked_by == "moderator123"
        assert lock.reason == "Test region"
