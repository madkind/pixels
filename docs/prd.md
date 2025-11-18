# Pixels Collaborative Canvas – Product Requirements Document

## 1. Overview
- **Objective:** Deliver a real-time collaborative pixel art application built on the existing uv-initialized Python backend, a WebSocket layer for live updates, and a React-based frontend.
- **Core Concept:** A 900×900 pixel canvas (810,000 pixels) rendered as an image in the browser. Users paint one pixel at a time using either a color palette picker or a drawing mode that streams brush movements to the backend.
- **Scope (MVP):** Shared canvas, authenticated sessions (lightweight), WebSocket-driven synchronization, change history for conflict resolution, and deployment-ready scripts for both backend and frontend.
- **Infrastructure:** Terraform-managed AWS stack with EC2 instances running the Python/WebSocket services and managed DynamoDB for durable storage.

## 2. Goals and Non-Goals
### Goals
1. Real-time collaborative editing with sub-second propagation to all connected clients.
2. Intuitive UI that supports precise single-pixel edits and click-drag drawing.
3. Reliable persistence so canvas state survives restarts and can be restored.
4. Modularity: backend (Python/uv), WebSocket service, and React frontend operate independently for easier scaling.
5. Observability hooks (metrics/logging) to track usage, latency, and errors.

### Non-Goals (MVP)
1. Advanced art tools (layers, blending, undo per user) – only basic draw/erase.
2. Mobile-native apps – responsive web only.
3. On-chain or NFT integrations.
4. Offline editing.

## 3. Target Users & Use Cases
- **Casual creators:** drop-in users painting collaboratively.
- **Community events:** time-bound art jams or competitions.
- **Moderators/admins:** manage palette, rate limits, and content moderation.

Primary user journeys:
1. Load canvas → observe current art → pick color → update pixels.
2. Toggle drawing mode → drag cursor to emit pixel stream.
3. Moderator locks regions, rewinds to previous state, or exports snapshot.

## 4. Functional Requirements
### Backend (Python with uv)
1. REST endpoints for auth bootstrap, fetching initial canvas bitmap, palette metadata, and audit logs.
2. WebSocket server broadcasting pixel diffs as events (`pixel:update`, `pixel:bulk_update`, `moderation:lock`).
3. Persistence layer backed by DynamoDB (managed AWS service) storing per-pixel color, timestamp, and user id. Local development can fall back to DynamoDB Local. Consider Redis cache for hot canvas state.
4. Rate limiting + flood protection (per IP/user) for pixel updates.

### Frontend (React)
1. Render 900×900 canvas efficiently (WebGL or Canvas 2D) with ability to zoom/pan.
2. Color palette selector + custom color input (restricted to safe values if needed).
3. Drawing tools: single-click paint, click-drag stroke, eraser (set to background color).
4. Connection status indicator, latency telemetry, and toast notifications for conflicts/moderation events.
5. Optimistic UI updates that reconcile with backend confirmations.

### Collaboration Flow
1. Client loads initial bitmap via REST (binary blob or compressed diff).
2. Client opens WebSocket, subscribes to canvas stream, and applies incoming diffs.
3. When user paints:
   - Optimistically render locally.
   - Send pixel payload `{x, y, color, tool, clientTimestamp}` via WebSocket.
   - Backend validates, persists, rebroadcasts authoritative event.

## 5. System Architecture
1. **Backend service (uv/fastapi or similar):** REST + WebSocket endpoints, orchestrates persistence and moderation rules.
2. **Data storage:** Primary DynamoDB table for canvas/user data. Optional Redis for caching entire bitmap to serve quickly.
3. **Static asset hosting:** Build React frontend and serve via CDN or reverse proxy.
4. **Deployment topology:** Dockerized services on AWS EC2; backend optionally scales horizontally with sticky sessions or shared Redis pub/sub for WebSocket fan-out.
5. **Infrastructure as Code:** Terraform modules provisioning EC2, networking (VPC, ALB), DynamoDB, Redis, and CI/CD wiring.
6. **Observability:** Structured logging, Prometheus metrics (update throughput, latency), health checks.

## 6. Detailed Requirements
### Canvas Representation
- Store pixels as 2D array flattened into byte array (RGB or indexed palette) for fast transfer.
- Provide snapshot endpoint that returns compressed PNG/JPEG plus hash for cache validation.
- Support partial updates: backend accumulates 50–100 ms batches before broadcasting to reduce chatter.

### WebSocket Protocol
- **Events from client:** `pixel:update`, `pixel:stroke:start`, `pixel:stroke:end`, `heartbeat`.
- **Events from server:** `pixel:ack`, `pixel:reject` (with reason), `pixel:bulk_update`, `canvas:state`, `moderation:*`.
- Heartbeat every 15 seconds to detect stale clients.

### Moderation & Safeguards
- Region locking API to prevent edits in protected zones.
- Simple profanity/shape filters deferred; MVP includes manual lock/unlock.
- Audit log accessible via admin endpoint.

### Performance Targets
- Initial canvas load < 2 s on broadband.
- WebSocket round-trip < 250 ms p95.
- Handle 1,000 concurrent clients with up to 200 pixel updates/sec aggregate without degradation.

## 7. UX Guidelines
1. Grid overlay toggle for precision.
2. Hover tooltip showing coordinates and current color.
3. Palette pinned to left/right, includes recent colors.
4. Keyboard shortcuts (e.g., `B` brush, `E` eraser, `Z` zoom toggle).
5. Screen-reader friendly controls for accessibility (announce coordinates and color changes).

## 8. Success Metrics
- Daily Active Users, average session length.
- Pixel updates per minute and successful vs rejected ratio.
- WebSocket uptime and reconnect rate.
- Canvas export/download usage.

## 9. Technical Risks & Mitigations
1. **High bandwidth usage:** Use delta encoding and throttled strokes.
2. **Server hot spots:** Introduce sharding or spatial partitioning if load spikes.
3. **Client performance:** Use offscreen canvas or WebGL to avoid DOM thrash.
4. **Data corruption:** Periodic snapshots + backups; versioned diffs for rollback.

## 10. Open Questions
1. Authentication mechanism: anonymous + optional name, or full auth provider?
2. Palette size governance: fixed 32 colors vs configurable.
3. Storage choice finalization (SQLite vs Postgres) and hosting environment.
4. Moderator tooling depth for MVP.

## 11. Next Steps
1. Finalize tech stack selections (FastAPI vs Starlette, canvas rendering engine, state store) including AWS EC2 sizing and DynamoDB capacity planning.
2. Produce architecture diagrams and interface contracts.
3. Build Terraform modules for core infrastructure.
4. Implement backend skeleton (REST + WebSocket) and React app shell.
5. Add automated tests (unit + integration) for pixel update logic.
