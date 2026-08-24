#!/usr/bin/env python3
"""Jeopardy Studio: a dependency-free, locally hosted game-board web app."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote
from wsgiref.simple_server import make_server

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("JEOPARDY_DATA_DIR", ROOT / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "jeopardy.db"
MAX_UPLOAD = 250 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS games (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, data TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")


def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def response(start, status="200 OK", body=b"", content_type="application/json", headers=None):
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
    if isinstance(body, str):
        body = body.encode()
    h = [("Content-Type", content_type), ("Content-Length", str(len(body))),
         ("X-Content-Type-Options", "nosniff")]
    h.extend(headers or [])
    start(status, h)
    return [body]


def read_json(env):
    length = int(env.get("CONTENT_LENGTH") or 0)
    if length > 2_000_000:
        raise ValueError("Request is too large")
    return json.loads(env["wsgi.input"].read(length) or b"{}")


def row_game(row):
    game = json.loads(row["data"])
    game.update(id=row["id"], title=row["title"], createdAt=row["created_at"], updatedAt=row["updated_at"])
    return game


def safe_game(payload):
    title = str(payload.get("title", "Untitled Game")).strip()[:120] or "Untitled Game"
    data = {
        "contestants": payload.get("contestants", []),
        "categories": payload.get("categories", []),
        "clues": payload.get("clues", []),
        "finalJeopardy": payload.get("finalJeopardy", {
            "category": "Final Jeopardy", "value": 1000, "question": "", "answer": "",
            "questionMedia": None, "answerMedia": None, "played": False
        }),
        "activeContestant": payload.get("activeContestant"),
        "settings": payload.get("settings", {"currency": "$"}),
    }
    return title, data


def static_file(start, path, base, env=None):
    try:
        target = (base / unquote(path)).resolve()
        if base.resolve() not in target.parents and target != base.resolve():
            return response(start, "403 Forbidden", {"error": "Forbidden"})
        size = target.stat().st_size
    except (FileNotFoundError, IsADirectoryError):
        return response(start, "404 Not Found", {"error": "Not found"})
    mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    common = [("Cache-Control", "no-cache"), ("Accept-Ranges", "bytes")]
    range_header = (env or {}).get("HTTP_RANGE", "")
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not match or not size:
            return response(start, "416 Range Not Satisfiable", b"", mime,
                            common + [("Content-Range", f"bytes */{size}")])
        first, last = match.groups()
        if not first and not last:
            return response(start, "416 Range Not Satisfiable", b"", mime,
                            common + [("Content-Range", f"bytes */{size}")])
        if first:
            begin = int(first)
            end = min(int(last), size - 1) if last else size - 1
        else:
            suffix = int(last)
            begin = max(size - suffix, 0)
            end = size - 1
        if begin >= size or begin > end:
            return response(start, "416 Range Not Satisfiable", b"", mime,
                            common + [("Content-Range", f"bytes */{size}")])
        length = end - begin + 1
        with target.open("rb") as source:
            source.seek(begin)
            raw = source.read(length)
        return response(start, "206 Partial Content", raw, mime, common + [
            ("Content-Range", f"bytes {begin}-{end}/{size}")
        ])
    return response(start, body=target.read_bytes(), content_type=mime, headers=common)


def application(env, start):
    init_db()
    method, path = env["REQUEST_METHOD"], env.get("PATH_INFO", "/")
    try:
        if path == "/" and method == "GET":
            return static_file(start, "index.html", ROOT / "static", env)
        if path.startswith("/static/") and method == "GET":
            return static_file(start, path[8:], ROOT / "static", env)
        if path.startswith("/uploads/") and method == "GET":
            return static_file(start, path[9:], UPLOAD_DIR, env)

        if path == "/api/games" and method == "GET":
            with connect() as db:
                rows = db.execute("SELECT * FROM games ORDER BY updated_at DESC").fetchall()
            return response(start, body=[row_game(r) for r in rows])

        if path == "/api/games" and method == "POST":
            payload = read_json(env); title, data = safe_game(payload)
            gid, stamp = uuid.uuid4().hex[:12], now()
            with connect() as db:
                db.execute("INSERT INTO games VALUES (?,?,?,?,?)", (gid, title, json.dumps(data), stamp, stamp))
            return response(start, "201 Created", {"id": gid})

        match = re.fullmatch(r"/api/games/([a-f0-9]{12})", path)
        if match:
            gid = match.group(1)
            if method == "GET":
                with connect() as db: row = db.execute("SELECT * FROM games WHERE id=?", (gid,)).fetchone()
                return response(start, body=row_game(row)) if row else response(start, "404 Not Found", {"error":"Game not found"})
            if method == "PUT":
                payload = read_json(env); title, data = safe_game(payload); stamp = now()
                with connect() as db:
                    cur = db.execute("UPDATE games SET title=?,data=?,updated_at=? WHERE id=?", (title,json.dumps(data),stamp,gid))
                return response(start, body={"ok": bool(cur.rowcount), "updatedAt": stamp})
            if method == "DELETE":
                with connect() as db: db.execute("DELETE FROM games WHERE id=?", (gid,))
                return response(start, body={"ok": True})

        if path == "/api/upload" and method == "POST":
            length = int(env.get("CONTENT_LENGTH") or 0)
            if not 0 < length <= MAX_UPLOAD:
                return response(start, "413 Payload Too Large", {"error": "Files must be between 1 byte and 250 MB"})
            original = unquote(env.get("HTTP_X_FILENAME", "media"))
            mime = env.get("CONTENT_TYPE", "application/octet-stream").split(";",1)[0]
            allowed = mime.startswith(("audio/", "video/", "image/"))
            if not allowed:
                return response(start, "415 Unsupported Media Type", {"error": "Only audio, video and image files are supported"})
            ext = Path(original).suffix.lower() or mimetypes.guess_extension(mime) or ".bin"
            filename = uuid.uuid4().hex + ext[:10]
            (UPLOAD_DIR / filename).write_bytes(env["wsgi.input"].read(length))
            return response(start, "201 Created", {"url": f"/uploads/{filename}", "type": mime, "name": original[:160]})

        return response(start, "404 Not Found", {"error": "Not found"})
    except (ValueError, json.JSONDecodeError) as exc:
        return response(start, "400 Bad Request", {"error": str(exc)})
    except Exception as exc:
        print(f"Server error: {exc}", file=sys.stderr)
        return response(start, "500 Internal Server Error", {"error": "Server error"})


if __name__ == "__main__":
    init_db()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"Jeopardy Studio is running at http://{host}:{port}")
    make_server(host, port, application).serve_forever()
