# Pixels Collaborative Canvas Backend

A real-time collaborative pixel art application backend built with FastAPI, WebSocket support, DynamoDB persistence, and Redis caching.

## Features

- **Real-time Collaboration**: WebSocket-based pixel updates with 50ms batching
- **Scalable Storage**: DynamoDB for persistent storage with Redis caching for hot canvas state
- **Rate Limiting**: Token bucket algorithm (10 pixels/sec) + Redis-based minute limits (100 pixels/min)
- **Moderation**: Region locking, audit logging, and admin endpoints
- **Performance**: Optimized for 900×900 canvas (810K pixels) with compressed bitmap storage

## Quick Start

### Docker Compose (Recommended)

```bash
# Start all services
make up

# Start with Redis Commander GUI
make tools

# View logs
make logs

# Stop services
make stop

# Clean up everything
make clean
```

**Services:**
- API: http://localhost:8000
- Redis Commander: http://localhost:8081 (when using `make tools`)
- DynamoDB: localhost:8001

### Local Development

**Prerequisites:**
- Python 3.13+
- Redis (optional but recommended)
- DynamoDB Local (optional)

**Installation:**
```bash
# Install dependencies
uv sync

# Copy environment configuration
cp .env.example .env
```

**Local Development:**
```bash
# Start Redis (optional)
redis-server

# Start DynamoDB Local (optional)
java -Djava.library.path=./DynamoDBLocal_lib -jar DynamoDBLocal.jar -sharedDb -inMemory

# Configure environment in .env:
DYNAMODB_LOCAL=true
REDIS_LOCAL=true

# Run the server
make local-dev
# or: uv run python -m app.main
```

### Development Tools

```bash
# Show all available commands
make help

# Run tests
make test

# Run linting
make lint
```

## API Endpoints

### REST Endpoints

- `GET /` - API status
- `GET /health` - Health check
- `GET /canvas` - Get canvas state as binary bitmap
- `GET /canvas/image` - Get canvas as PNG image
- `GET /palette` - Get color palette
- `GET /audit` - Get audit log (rate limited)
- `GET /locks` - Get region locks
- `POST /locks` - Create region lock
- `DELETE /locks/{x1}/{y1}/{x2}/{y2}` - Remove region lock

### WebSocket Endpoint

- `WS /ws` - Real-time pixel updates

#### WebSocket Message Types

**Client → Server:**
```json
{
  "type": "pixel:update",
  "data": {
    "x": 100,
    "y": 200,
    "color": "#FF0000",
    "tool": "brush",
    "clientTimestamp": "2025-01-18T19:53:00Z",
    "userId": "user123"
  }
}
```

**Server → Client:**
```json
{
  "type": "pixel:bulk_update",
  "data": {
    "pixels": [{"x": 100, "y": 200, "color": "#FF0000"}],
    "hash": "sha256hash"
  },
  "timestamp": "2025-01-18T19:53:00Z"
}
```

## Architecture

### Data Storage

- **DynamoDB**: Primary storage for canvas bitmap, audit logs, and region locks
- **Redis**: Caching layer for hot canvas state and rate limiting
- **Canvas Storage**: Single compressed bitmap item (not per-pixel storage)

### Rate Limiting

- **Token Bucket**: 10 pixels/second per user (burst up to 20)
- **Redis Limits**: 100 pixels/minute per user
- **REST Limits**: 10 requests/minute for canvas, 5/minute for audit

### Performance Optimizations

- **Batch Processing**: 50ms batching windows for pixel updates
- **Compression**: Gzip compression for canvas bitmap storage
- **Caching**: Redis caching for canvas state and region locks
- **Efficient Broadcasting**: Single WebSocket message for batched updates

## Deployment

### AWS Production

1. Set environment variables:
```env
DYNAMODB_LOCAL=false
REDIS_LOCAL=false
REDIS_HOST=your-redis-host
REDIS_PORT=6379
REDIS_PASSWORD=your-redis-password
```

2. Deploy with Docker:
```bash
docker build -t pixels-backend .
docker run -p 8000:8000 pixels-backend
```

### Terraform Infrastructure

The backend is designed to work with the Terraform stack defined in the PRD:
- EC2 instances for backend services
- DynamoDB tables for persistence
- Redis cluster for caching
- Application Load Balancer for WebSocket support

## Development

### Project Structure

```
app/
├── __init__.py
├── main.py          # FastAPI application and WebSocket handlers
├── models.py        # Pydantic data models
├── database.py      # DynamoDB integration
├── redis_cache.py   # Redis caching layer
└── rate_limiter.py  # Rate limiting logic
```

### Testing

```bash
# Run tests (when implemented)
uv run pytest

# Run with coverage
uv run pytest --cov=app
```

## Monitoring

The application includes:
- Structured logging for pixel updates and errors
- Health check endpoints for load balancers
- Rate limiting metrics and rejection tracking
- WebSocket connection monitoring

## License

MIT License