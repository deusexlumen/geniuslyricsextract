#!/usr/bin/env python3
"""Lokale Seite für web2txt. Hört nur auf 127.0.0.1."""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import web2txt

ROOT = Path(__file__).resolve().parent
LYRICS = ROOT / "lyrics"
PAGE = ROOT / "ui" / "index.html"
HOST = "127.0.0.1"

_lock = threading.Lock()
_job = {
    "status": "idle",
    "message": "",
    "album": "",
    "song": "",
    "index": 0,
    "total": 0,
    "documents": [],
    "failed": 0,
}


def job_snapshot() -> dict:
    with _lock:
        return dict(_job)


def job_update(**fields) -> None:
    with _lock:
        _job.update(fields)


def lyrics_file(rel: str) -> Path | None:
    if not rel or rel.startswith(("/", "\\")) or ":" in rel:
        return None
    path = (LYRICS / rel).resolve()
    try:
        path.relative_to(LYRICS.resolve())
    except ValueError:
        return None
    if path.suffix.lower() != ".txt" or not path.is_file():
        return None
    return path


def album_payload(album: dict) -> dict:
    return {
        "id": album.get("id"),
        "name": (album.get("name") or "").strip(),
        "year": web2txt.album_year(album),
        "url": album.get("url") or "",
    }


def lookup_albums(name: str) -> dict:
    session = web2txt.make_session()
    artist, choice = web2txt.resolve_artist(session, name)
    if choice or artist is None:
        options = []
        for line in (choice or "").splitlines():
            if not line.startswith("- "):
                continue
            parts = [part.strip() for part in line[2:].split("|")]
            if parts and parts[0] and parts[0] != "(keine Treffer)":
                options.append({"name": parts[0], "url": parts[1] if len(parts) > 1 else ""})
        if not options:
            return {"error": f"Kein Interpret für „{name}“."}
        return {"choose": options}
    albums = web2txt.artist_albums(session, artist["id"])
    return {
        "artist": artist.get("name") or name,
        "albums": [album_payload(album) for album in albums],
    }


def _run(artist_name: str, album_ids: set[int]) -> None:
    try:
        session = web2txt.make_session()
        job_update(status="running", message="Suche den Interpreten", album="", song="", index=0, total=0, documents=[], failed=0)
        artist, choice = web2txt.resolve_artist(session, artist_name)
        if choice or artist is None:
            job_update(status="error", message="Der Interpret ist nicht eindeutig. Such noch einmal und wähl den Namen aus der Liste.")
            return
        known = {album["id"]: album for album in web2txt.artist_albums(session, artist["id"])}
        chosen = [known[album_id] for album_id in album_ids if album_id in known]
        if not chosen:
            job_update(status="error", message="Keine der ausgewählten Alben liegt bei diesem Interpreten.")
            return
        groups = []
        for album in chosen:
            job_update(album=album.get("name") or "", message="Lies die Titelliste", song="")
            songs = web2txt.album_tracks(session, album["id"])
            if songs:
                groups.append(web2txt.group_from_album(album, songs))
        if not groups:
            job_update(status="error", message="Diese Alben haben keine Lyrics-Links.")
            return
        if len(groups) == len(known) and len(groups) > 1:
            url_path = ROOT / "urls" / f"{web2txt.safe_name(groups[0].artist or 'genius')}-discography.urls"
        else:
            url_path = ROOT / web2txt.default_url_path(groups)
        web2txt.write_text(url_path, web2txt.render_url_file(groups))
        songs = [song for group in groups for song in group.songs]
        job_update(message="Hol die Texte", total=len(songs), album="")

        def on_song(index: int, total: int, title: str) -> None:
            job_update(index=index, total=total, song=title, message="Hol die Texte")

        _ok, failed, documents = web2txt.fetch_songs(
            session,
            songs,
            LYRICS,
            combine=True,
            raw=False,
            single_output=None,
            delay=0.3,
            on_song=on_song,
        )
        docs = []
        for path in documents:
            rel = path.resolve().relative_to(LYRICS.resolve()).as_posix()
            docs.append({"label": path.parent.name, "path": rel})
        job_update(
            status="done",
            message=f"Fertig. {len(songs) - len(failed)} von {len(songs)} Songs.",
            documents=docs,
            failed=len(failed),
            song="",
            album="",
        )
    except Exception as exc:
        job_update(status="error", message=str(exc), song="", album="")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[ui] {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 100_000:
            raise ValueError("Anfrage ist zu groß.")
        raw = self.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON-Objekt erwartet.")
        return data

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/status":
            self._json(200, job_snapshot())
            return
        if parsed.path == "/api/text":
            rel = (parse_qs(parsed.query).get("path") or [""])[0]
            path = lyrics_file(rel)
            if path is None:
                self._json(404, {"error": "Die Datei liegt nicht im Lyrics-Ordner."})
                return
            self._send(200, path.read_bytes(), "text/plain; charset=utf-8")
            return
        self._json(404, {"error": "Nicht gefunden."})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            data = self._read_json()
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        if parsed.path == "/api/albums":
            name = str(data.get("artist") or "").strip()
            if not name:
                self._json(400, {"error": "Trag einen Interpreten ein."})
                return
            try:
                self._json(200, lookup_albums(name))
            except Exception as exc:
                self._json(502, {"error": str(exc)})
            return
        if parsed.path == "/api/run":
            name = str(data.get("artist") or "").strip()
            raw_ids = data.get("album_ids") or []
            if not name:
                self._json(400, {"error": "Trag einen Interpreten ein."})
                return
            if not isinstance(raw_ids, list) or not raw_ids:
                self._json(400, {"error": "Wähl mindestens ein Album."})
                return
            try:
                album_ids = {int(item) for item in raw_ids}
            except (TypeError, ValueError):
                self._json(400, {"error": "Die Album-Auswahl ist ungültig."})
                return
            with _lock:
                if _job["status"] == "running":
                    self._json(409, {"error": "Es läuft schon ein Download."})
                    return
                _job.update(status="running", message="Start", documents=[], failed=0, index=0, total=0, song="", album="")
            threading.Thread(target=_run, args=(name, album_ids), daemon=True).start()
            self._json(200, {"ok": True})
            return
        self._json(404, {"error": "Nicht gefunden."})


def serve(port: int = 8765, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((HOST, port), Handler)
    url = f"http://{HOST}:{port}/"
    print(f"Oberfläche: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopp.")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="web2txt.py ui", description="Lokale Oberfläche öffnen")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    serve(args.port, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
