import pytest
import json
import asyncio
from unittest.mock import patch, Mock
from datetime import datetime
import numpy as np

from app.main import app
from app.models import CanvasState, RegionLock


class TestMainEndpoints:
    """Test the main REST endpoints."""

    def test_root_endpoint(self, client):
        """Test the root endpoint returns API info."""
        response = client.get("/")
        assert response.status_code == 200
        assert "message" in response.json()
        assert "Pixels Collaborative Canvas" in response.json()["message"]

    def test_health_check(self, client):
        """Test the health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_get_canvas_empty(self, client, mock_dynamodb, mock_redis):
        """Test getting canvas when no canvas exists."""
        mock_dynamodb.get_canvas_state.return_value = None
        
        response = client.get("/canvas")
        assert response.status_code == 200
        
        data = response.json()
        assert data["width"] == 900
        assert data["height"] == 900
        assert "bitmap" in data
        assert "hash" in data
        assert "last_updated" in data
        
        # Verify save was called for new canvas
        mock_dynamodb.save_canvas_state.assert_called_once()

    def test_get_canvas_existing(self, client, mock_dynamodb, mock_redis, sample_canvas_state):
        """Test getting existing canvas."""
        mock_dynamodb.get_canvas_state.return_value = sample_canvas_state
        
        response = client.get("/canvas")
        assert response.status_code == 200
        
        data = response.json()
        assert data["width"] == 900
        assert data["height"] == 900
        assert data["hash"] == "test_hash_123"

    def test_get_canvas_image(self, client, mock_dynamodb):
        """Test getting canvas as PNG image."""
        # Create a simple canvas
        bitmap = np.zeros((900, 900, 3), dtype=np.uint8)
        bitmap[0, 0] = [255, 255, 255]  # White pixel
        canvas_state = CanvasState(
            width=900,
            height=900,
            bitmap=bitmap.tobytes(),
            hash="test_hash",
            last_updated=datetime.utcnow()
        )
        mock_dynamodb.get_canvas_state.return_value = canvas_state
        
        response = client.get("/canvas/image")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"

    def test_get_palette(self, client):
        """Test getting the color palette."""
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

    def test_get_audit_log(self, client, mock_dynamodb):
        """Test getting audit log."""
        mock_dynamodb.get_audit_log.return_value = []
        
        response = client.get("/audit")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_region_locks(self, client, mock_dynamodb, sample_region_lock):
        """Test getting region locks."""
        mock_dynamodb.get_region_locks.return_value = [sample_region_lock]
        
        response = client.get("/locks")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) == 1
        lock = data[0]
        assert lock["x1"] == 50
        assert lock["y1"] == 50
        assert lock["x2"] == 100
        assert lock["y2"] == 100
        assert lock["locked_by"] == "moderator123"

    def test_create_region_lock(self, client, mock_dynamodb):
        """Test creating a region lock."""
        lock_data = {
            "x1": 50,
            "y1": 50,
            "x2": 100,
            "y2": 100,
            "locked_by": "moderator123",
            "reason": "Test lock",
            "created_at": datetime.utcnow().isoformat()
        }
        
        response = client.post("/locks", json=lock_data)
        assert response.status_code == 200
        assert response.json()["message"] == "Region lock created"
        mock_dynamodb.add_region_lock.assert_called_once()

    def test_remove_region_lock(self, client, mock_dynamodb):
        """Test removing a region lock."""
        response = client.delete("/locks/50/50/100/100")
        assert response.status_code == 200
        assert response.json()["message"] == "Region lock removed"
        mock_dynamodb.remove_region_lock.assert_called_once_with(50, 50, 100, 100)

    def test_rate_limiting_canvas_endpoint(self, client, mock_dynamodb):
        """Test rate limiting on canvas endpoint."""
        mock_dynamodb.get_canvas_state.return_value = None
        
        # Make multiple requests quickly
        responses = []
        for _ in range(12):  # Exceed the limit of 10/minute
            responses.append(client.get("/canvas"))
        
        # First 10 should succeed, rest should be rate limited
        success_count = sum(1 for r in responses if r.status_code == 200)
        rate_limited_count = sum(1 for r in responses if r.status_code == 429)
        
        assert success_count == 10
        assert rate_limited_count == 2


class TestWebSocket:
    """Test WebSocket functionality."""

    def test_websocket_connection(self, client, mock_dynamodb, mock_redis):
        """Test WebSocket connection and heartbeat."""
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

    def test_websocket_pixel_update(self, client, mock_dynamodb, mock_redis, mock_pixel_update):
        """Test WebSocket pixel update."""
        mock_dynamodb.is_position_locked.return_value = False
        
        with client.websocket_connect("/ws") as websocket:
            # Send pixel update
            websocket.send_text(json.dumps({
                "type": "pixel:update",
                "data": mock_pixel_update
            }))
            
            # Should not receive immediate response (batched)
            # Wait for batch processing
            import time
            time.sleep(0.06)  # Wait for 50ms batch window
            
            # Check that update was queued (indirectly through no rejection)
            # In a real test, we'd check the pixel_update_queue

    def test_websocket_pixel_update_locked(self, client, mock_dynamodb, mock_redis, mock_pixel_update):
        """Test WebSocket pixel update on locked position."""
        mock_dynamodb.is_position_locked.return_value = True
        
        with client.websocket_connect("/ws") as websocket:
            # Send pixel update
            websocket.send_text(json.dumps({
                "type": "pixel:update",
                "data": mock_pixel_update
            }))
            
            # Should receive rejection
            data = websocket.receive_text()
            message = json.loads(data)
            assert message["type"] == "pixel:reject"
            assert "reason" in message["data"]

    @patch('app.main.check_pixel_rate_limit')
    def test_websocket_rate_limiting(self, mock_rate_limit, client, mock_pixel_update):
        """Test WebSocket rate limiting."""
        mock_rate_limit.return_value = (False, "Rate limit exceeded")
        
        with client.websocket_connect("/ws") as websocket:
            # Send pixel update
            websocket.send_text(json.dumps({
                "type": "pixel:update",
                "data": mock_pixel_update
            }))
            
            # Should receive rate limit rejection
            data = websocket.receive_text()
            message = json.loads(data)
            assert message["type"] == "pixel:reject"
            assert "Rate limit exceeded" in message["data"]["reason"]

    def test_websocket_invalid_message(self, client):
        """Test WebSocket with invalid message format."""
        with client.websocket_connect("/ws") as websocket:
            # Send invalid JSON
            websocket.send_text("invalid json")
            
            # Connection should remain open (error handling)
            # Send valid heartbeat to verify connection still works
            websocket.send_text(json.dumps({
                "type": "heartbeat"
            }))
            data = websocket.receive_text()
            message = json.loads(data)
            assert message["type"] == "heartbeat:ack"


class TestPixelBatching:
    """Test pixel update batching functionality."""

    @pytest.mark.asyncio
    async def test_pixel_batch_processing(self, mock_dynamodb, mock_redis):
        """Test that pixel updates are batched correctly."""
        from app.main import pixel_update_queue, process_pixel_batch
        from app.models import PixelUpdate
        
        # Create sample pixel updates
        updates = [
            PixelUpdate(
                x=100, y=200, color="#FF0000", tool="brush",
                client_timestamp=datetime.utcnow(), user_id="user1"
            ),
            PixelUpdate(
                x=101, y=201, color="#00FF00", tool="brush",
                client_timestamp=datetime.utcnow(), user_id="user2"
            )
        ]
        
        # Mock canvas state
        bitmap = np.zeros((900, 900, 3), dtype=np.uint8)
        mock_dynamodb.get_canvas_state.return_value = None
        
        # Process batch
        await process_pixel_batch(updates)
        
        # Verify database calls
        assert mock_dynamodb.save_canvas_state.called
        assert mock_dynamodb.add_audit_entry.call_count == len(updates)

    @pytest.mark.asyncio
    async def test_batch_task_lifecycle(self):
        """Test that background batch task starts and stops cleanly."""
        from app.main import batch_pixel_updates
        
        # Start the batch task
        task = asyncio.create_task(batch_pixel_updates())
        
        # Let it run briefly
        await asyncio.sleep(0.01)
        
        # Cancel and verify cleanup
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass  # Expected


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_pixel_coordinates(self, client, mock_pixel_update):
        """Test pixel updates with invalid coordinates."""
        invalid_pixel = mock_pixel_update.copy()
        invalid_pixel["x"] = 999  # Outside 900x900 canvas
        
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "type": "pixel:update",
                "data": invalid_pixel
            }))
            
            # Should handle gracefully (connection stays open)
            websocket.send_text(json.dumps({"type": "heartbeat"}))
            data = websocket.receive_text()
            assert json.loads(data)["type"] == "heartbeat:ack"

    def test_invalid_color_format(self, client, mock_pixel_update):
        """Test pixel updates with invalid color format."""
        invalid_pixel = mock_pixel_update.copy()
        invalid_pixel["color"] = "red"  # Invalid color format
        
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text(json.dumps({
                "type": "pixel:update",
                "data": invalid_pixel
            }))
            
            # Should handle gracefully
            websocket.send_text(json.dumps({"type": "heartbeat"}))
            data = websocket.receive_text()
            assert json.loads(data)["type"] == "heartbeat:ack"

    def test_database_error_handling(self, client, mock_dynamodb):
        """Test handling of database errors."""
        mock_dynamodb.get_canvas_state.side_effect = Exception("Database error")
        
        response = client.get("/canvas")
        # Should create new canvas despite error
        assert response.status_code == 200
        assert response.json()["width"] == 900
