"""
aria2 JSON-RPC client (async).
aria2 runs as a subprocess in RPC mode; this module communicates with it.
"""
import asyncio
import json
import os
import subprocess
import time
from typing import Any

import aiohttp

from config import Config
from utils.logger import logger

RPC_URL_TEMPLATE = "http://{host}:{port}/jsonrpc"


class Aria2RPC:
    def __init__(self):
        self.host = Config.ARIA2_RPC_HOST
        self.port = Config.ARIA2_RPC_PORT
        self.secret = Config.ARIA2_RPC_SECRET
        self.url = RPC_URL_TEMPLATE.format(host=self.host, port=self.port)
        self._session: aiohttp.ClientSession | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._req_id = 0

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def start_process(self) -> None:
        """Launch aria2c as a background subprocess."""
        os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
        cmd = [
            "aria2c",
            f"--enable-rpc=true",
            f"--rpc-listen-all=false",
            f"--rpc-listen-port={self.port}",
            "--rpc-allow-origin-all=true",
            f"--dir={Config.DOWNLOAD_DIR}",
            "--continue=true",
            "--max-connection-per-server=16",
            "--split=16",
            "--min-split-size=1M",
            "--max-concurrent-downloads=10",
            "--bt-enable-lpd=true",
            "--enable-dht=true",
            "--enable-dht6=false",
            "--bt-tracker-interval=10",
            "--seed-time=0",
            f"--seed-ratio={Config.SEED_RATIO}",
            "--follow-torrent=mem",
            "--bt-save-metadata=true",
            "--daemon=false",
            "--quiet=true",
        ]
        if self.secret:
            cmd.append(f"--rpc-secret={self.secret}")

        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Wait until RPC is ready
        for _ in range(30):
            await asyncio.sleep(1)
            try:
                await self._call("aria2.getVersion", [])
                logger.info("aria2 RPC connected")
                return
            except Exception:
                pass
        raise RuntimeError("aria2 RPC did not become ready in 30 seconds")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _call(self, method: str, params: list) -> Any:
        session = await self._get_session()
        token_params = [f"token:{self.secret}"] + params if self.secret else params
        payload = {
            "jsonrpc": "2.0",
            "id": str(self._next_id()),
            "method": method,
            "params": token_params,
        }
        async with session.post(
            self.url, json=payload, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            data = await resp.json()
        if "error" in data:
            raise RuntimeError(f"aria2 RPC error: {data['error']}")
        return data.get("result")

    # ── Torrent management ─────────────────────────────────────────────────

    async def add_magnet(self, magnet: str, download_dir: str) -> str:
        """Add a magnet link. Returns GID."""
        result = await self._call(
            "aria2.addUri",
            [[magnet], {"dir": download_dir, "bt-save-metadata": "true"}],
        )
        return result

    async def add_torrent_file(self, torrent_b64: str, download_dir: str) -> str:
        """Add a torrent file (base64-encoded). Returns GID."""
        result = await self._call(
            "aria2.addTorrent",
            [torrent_b64, [], {"dir": download_dir}],
        )
        return result

    async def add_torrent_url(self, url: str, download_dir: str) -> str:
        """Add a URL pointing to a .torrent file. Returns GID."""
        result = await self._call(
            "aria2.addUri",
            [[url], {"dir": download_dir}],
        )
        return result

    async def remove(self, gid: str) -> None:
        """Force-remove a download (active or waiting)."""
        try:
            await self._call("aria2.forceRemove", [gid])
        except Exception as e:
            logger.warning(f"aria2 remove {gid}: {e}")
        try:
            await self._call("aria2.removeDownloadResult", [gid])
        except Exception:
            pass

    async def get_status(self, gid: str) -> dict:
        """Return status dict for a download."""
        keys = [
            "gid", "status", "totalLength", "completedLength",
            "downloadSpeed", "uploadSpeed", "eta", "files",
            "bittorrent", "errorMessage", "dir",
        ]
        result = await self._call("aria2.tellStatus", [gid, keys])
        return result

    async def get_active(self) -> list:
        return await self._call("aria2.tellActive", [])

    async def pause(self, gid: str) -> None:
        await self._call("aria2.pause", [gid])

    async def unpause(self, gid: str) -> None:
        await self._call("aria2.unpause", [gid])

    def parse_status(self, raw: dict) -> dict:
        """Normalise aria2 status into our standard shape."""
        total = int(raw.get("totalLength", 0))
        done = int(raw.get("completedLength", 0))
        speed = int(raw.get("downloadSpeed", 0))
        up_speed = int(raw.get("uploadSpeed", 0))

        if total > 0:
            pct = done / total * 100
        else:
            pct = 0.0

        eta_raw = raw.get("eta")
        if eta_raw and int(eta_raw) > 0:
            eta = int(eta_raw)
        elif speed > 0 and total > done:
            eta = (total - done) // speed
        else:
            eta = 0

        # Try to get torrent name from bittorrent info
        bt = raw.get("bittorrent") or {}
        info = bt.get("info") or {}
        name = info.get("name") or ""

        # Fallback: first file path
        if not name:
            files = raw.get("files") or []
            if files:
                path = files[0].get("path", "")
                name = os.path.basename(path)

        # Seeders/peers from bittorrent
        num_seeders = int(bt.get("numSeeders", 0)) if bt else 0

        return {
            "gid": raw.get("gid"),
            "status": raw.get("status"),
            "name": name,
            "total": total,
            "downloaded": done,
            "speed": speed,
            "up_speed": up_speed,
            "eta": eta,
            "progress": round(pct, 2),
            "seeders": num_seeders,
            "peers": 0,  # aria2 doesn't easily expose connected peers count via RPC
            "error": raw.get("errorMessage"),
            "dir": raw.get("dir", ""),
            "files": raw.get("files", []),
        }

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        if self._proc:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()


# Singleton
aria2 = Aria2RPC()
