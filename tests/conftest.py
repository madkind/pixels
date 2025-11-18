import pytest
import asyncio
from unittest.mock import Mock, patch
from typing import Generator
import numpy as np
from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app
from app.models import CanvasState, RegionLock
from app.database import dynamodb_canvas
from app.redis_cache import redis_cache


@pytest.fixture
def client() -> Generator:
    """Create a test client for the FastAPI app."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    with patch('app.redis_cache.RedisCache.__init__', return_value=None):
        with patch('app.redis_cache.redis_cache') as mock_cache:
            mock_cache.get_canvas_state.return_value = None
            mock_cache.set_canvas_state.return_value = None
            mock_cache.get_region_locks.return_value = []
            mock_cache.set_region_locks.return_value = None
            mock_cache.increment_pixel_count.return_value = 1
            mock_cache.get_pixel_count.return_value = 0
            mock_cache.publish_pixel_update.return_value = None
            mock_cache.subscribe_to_updates.return_value = None
            yield mock_cache


@pytest.fixture
def mock_dynamodb():
    """Mock DynamoDB client for testing."""
    with patch('app.database.dynamodb_canvas') as mock_dynamo:
        # Mock canvas state
        mock_dynamo.get_canvas_state.return_value = None
        mock_dynamo.save_canvas_state.return_value = None
        mock_dynamo.is_position_locked.return_value = False
        mock_dynamo.add_audit_entry.return_value = None
        mock_dynamo.get_region_locks.return_value = []
        mock_dynamo.add_region_lock.return_value = None
        mock_dynamo.remove_region_lock.return_value = None
        mock_dynamo.get_audit_log.return_value = []
        yield mock_dynamo


@pytest.fixture
def sample_canvas_state():
    """Create a sample canvas state for testing."""
    bitmap = np.zeros((900, 900, 3), dtype=np.uint8)
    bitmap[100, 200] = [255, 0, 0]  # Red pixel at (100, 200)
    return CanvasState(
        width=900,
        height=900,
        bitmap=bitmap.tobytes(),
        hash="test_hash_123",
        last_updated=datetime.utcnow()
    )


@pytest.fixture
def sample_region_lock():
    """Create a sample region lock for testing."""
    return RegionLock(
        x1=50,
        y1=50,
        x2=100,
        y2=100,
        locked_by="moderator123",
        reason="Test region",
        created_at=datetime.utcnow()
    )


@pytest.fixture
def mock_pixel_update():
    """Create a sample pixel update for testing."""
    return {
        "x": 100,
        "y": 200,
        "color": "#FF0000",
        "tool": "brush",
        "clientTimestamp": datetime.utcnow().isoformat(),
        "userId": "user123"
    }


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def cleanup_background_tasks():
    """Clean up background tasks after each test."""
    yield
    # Cancel any running background tasks
    try:
        tasks = [t for t in asyncio.all_tasks() if not t.done()]
        for task in tasks:
            task.cancel()
            try:
                asyncio.get_event_loop().run_until_complete(task)
            except asyncio.CancelledError:
                pass
    except RuntimeError:
        # No event loop running, skip cleanup
        pass
