"""
Socket.IO Frame Receiver Server
--------------------------------
Receives JPEG frames from Android device over Socket.IO.
Runs on any machine (VPS, local, Docker).

Install dependencies:
    pip install python-socketio[asyncio] aiohttp

Run:
    python server.py
"""

import asyncio
import logging
from datetime import datetime
import socketio
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── Socket.IO server (async mode) ──────────────────────────────────────────────
sio = socketio.AsyncServer(
    async_mode="aiohttp",
    cors_allowed_origins="*",          # tighten this in production
    max_http_buffer_size=10 * 1024 * 1024,  # 10 MB — enough for a full JPEG frame
    ping_timeout=60,
    ping_interval=25,
)
app = web.Application()
sio.attach(app)

# ── Track connected Android streamers ─────────────────────────────────────────
streamers: dict[str, dict] = {}   # sid → metadata


# ── Connection events ──────────────────────────────────────────────────────────
@sio.event
async def connect(sid, environ):
    ip = environ.get("REMOTE_ADDR", "unknown")
    log.info(f"[CONNECT] sid={sid}  ip={ip}")
    streamers[sid] = {"ip": ip, "frames": 0, "connected_at": datetime.utcnow().isoformat()}
    await sio.emit("ack", {"status": "connected", "sid": sid}, to=sid)


@sio.event
async def disconnect(sid):
    info = streamers.pop(sid, {})
    log.info(f"[DISCONNECT] sid={sid}  total_frames={info.get('frames', 0)}")


# ── Frame receiver ─────────────────────────────────────────────────────────────
@sio.on("frame")
async def on_frame(sid, data: bytes):
    """
    Android sends raw JPEG bytes under the event name 'frame'.
    `data` is bytes here because Socket.IO treats binary payloads automatically.
    """
    if sid not in streamers:
        return

    streamers[sid]["frames"] += 1
    frame_count = streamers[sid]["frames"]

    # ── Do whatever you want with the JPEG bytes ──
    # Option 1: just log receipt
    log.debug(f"[FRAME] sid={sid}  frame={frame_count}  size={len(data)} bytes")

    # Option 2: save every N-th frame to disk  (uncomment to enable)
    # if frame_count % 30 == 0:
    #     path = f"frames/frame_{sid}_{frame_count}.jpg"
    #     with open(path, "wb") as f:
    #         f.write(data)
    #     log.info(f"[SAVED] {path}")

    # Option 3: confirm receipt back to Android  (uncomment to enable)
    # await sio.emit("frame_ack", {"frame": frame_count}, to=sid)


# ── Simple health-check HTTP endpoint ─────────────────────────────────────────
async def health(request):
    return web.json_response({
        "status": "ok",
        "streamers": len(streamers),
        "clients": [
            {"sid": sid, **meta} for sid, meta in streamers.items()
        ],
    })

app.router.add_get("/health", health)


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    HOST = "0.0.0.0"   # listen on all interfaces
    PORT = 8080         # change if needed

    log.info(f"Starting Socket.IO server on {HOST}:{PORT}")
    log.info("Health check → http://<your-ip>:8080/health")
    web.run_app(app, host=HOST, port=PORT)