"""
Socket.IO Relay Server — Android → Browser
-------------------------------------------
Android devices JOIN the "streamer" room and emit frames.
Browser viewers JOIN the "viewer" room and receive relayed frames.

Install:
    pip install python-socketio[asyncio] aiohttp

Run locally:    python server.py
Render.com:     Start command → python server.py
"""

import os
import logging
from datetime import datetime
import socketio
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

sio = socketio.AsyncServer(
    async_mode="aiohttp",
    cors_allowed_origins="*",
    max_http_buffer_size=10 * 1024 * 1024,
    ping_timeout=60,
    ping_interval=25,
)
app = web.Application()
sio.attach(app)

# ── Two separate registries ────────────────────────────────────────────────────
streamers: dict = {}   # sid → { frames, connected_at }
viewers:   dict = {}   # sid → { connected_at }


# ── Connect / Disconnect ───────────────────────────────────────────────────────
@sio.event
async def connect(sid, environ):
    ip = environ.get("REMOTE_ADDR", "unknown")
    log.info(f"[CONNECT] sid={sid}  ip={ip}")


@sio.event
async def disconnect(sid):
    if sid in streamers:
        info = streamers.pop(sid)
        log.info(f"[STREAMER LEFT] sid={sid}  frames={info['frames']}")
        await sio.emit("streamer_left", {"sid": sid}, room="viewers")
    elif sid in viewers:
        viewers.pop(sid)
        log.info(f"[VIEWER LEFT] sid={sid}")


# ── Role registration ──────────────────────────────────────────────────────────
@sio.on("register_streamer")
async def register_streamer(sid, data=None):
    """Android calls this once after connecting."""
    streamers[sid] = {"frames": 0, "connected_at": datetime.utcnow().isoformat()}
    await sio.enter_room(sid, "streamers")
    log.info(f"[STREAMER REGISTERED] sid={sid}")
    await sio.emit("ack", {"status": "registered_as_streamer", "sid": sid}, to=sid)
    await sio.emit("streamer_joined", {"sid": sid}, room="viewers")


@sio.on("register_viewer")
async def register_viewer(sid, data=None):
    """Browser calls this once after connecting."""
    viewers[sid] = {"connected_at": datetime.utcnow().isoformat()}
    await sio.enter_room(sid, "viewers")
    log.info(f"[VIEWER REGISTERED] sid={sid}")
    await sio.emit("ack", {
        "status": "registered_as_viewer",
        "sid": sid,
        "streamers": list(streamers.keys()),
    }, to=sid)


# ── Frame relay ────────────────────────────────────────────────────────────────
@sio.on("frame")
async def on_frame(sid, data: bytes):
    """Android emits raw JPEG bytes → relay to every viewer instantly."""
    if sid not in streamers:
        return

    streamers[sid]["frames"] += 1

    # Relay binary frame to every connected viewer
    await sio.emit("frame", {"sid": sid, "data": data}, room="viewers")

    if streamers[sid]["frames"] % 100 == 0:
        log.info(f"[RELAY] sid={sid}  frames={streamers[sid]['frames']}")


# ── Health check ───────────────────────────────────────────────────────────────
async def health(request):
    return web.json_response({
        "status": "ok",
        "streamers": len(streamers),
        "viewers": len(viewers),
        "streamer_list": [{"sid": sid, **meta} for sid, meta in streamers.items()],
        "viewer_list":   [{"sid": sid, **meta} for sid, meta in viewers.items()],
    })

app.router.add_get("/health", health)
app.router.add_get("/", lambda r: web.Response(text="Socket.IO relay server is running"))

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    log.info(f"Starting relay server on 0.0.0.0:{PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)
