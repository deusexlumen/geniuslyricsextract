#!/usr/bin/env python3
"""Genius-Lyrics: Links sammeln, Text holen, ein Album-Dokument schreiben.

  python web2txt.py collect --artist "Genetikk" --album "Voodoozirkus" -o urls/genetikk-voodoozirkus.urls
  python web2txt.py fetch urls/genetikk-voodoozirkus.urls

Ohne Album listet collect die Alben und endet mit Exit-Code 2.
Eine URL oder eine Bookmark-Datei geht weiter direkt an fetch.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
API_ROOT = "https://genius.com/api/"


@dataclass
class SongLink:
    url: str
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_url: str | None = None
    year: str | None = None
    folder: str | None = None


@dataclass
class AlbumGroup:
    artist: str | None
    album: str | None
    album_url: str | None
    year: str | None
    folder: str | None
    songs: list[SongLink] = field(default_factory=list)


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("&", " and ").replace("+", " plus ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def safe_name(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name)
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"-{2,}", "-", name).strip(" .-")
    if not name:
        return "untitled"
    return name[:max_len].rstrip(" .-")


def clean_title(title: str, artist: str | None = None) -> str:
    title = title.split("|")[0].strip()
    title = re.sub(r"\s+lyrics$", "", title, flags=re.IGNORECASE).strip()
    if artist:
        for sep in (" – ", " — ", " - "):
            prefix = artist + sep
            if title.casefold().startswith(prefix.casefold()):
                title = title[len(prefix) :].strip()
                break
    title = re.sub(r"\s+lyrics$", "", title, flags=re.IGNORECASE).strip()
    return title or "untitled"


def choose_by_name(query: str | None, items: list, name_fn) -> tuple[object | None, list]:
    """Ein Treffer, oder None plus die Liste, aus der gewählt werden muss."""
    if not items:
        return None, []
    if not query:
        return None, items
    exact = [item for item in items if norm(name_fn(item)) == norm(query)]
    if len(exact) == 1:
        return exact[0], []
    if len(exact) > 1:
        return None, exact
    needle = norm(query)
    partial = [
        item
        for item in items
        if needle and (needle in norm(name_fn(item)) or norm(name_fn(item)) in needle)
    ]
    if len(partial) == 1:
        return partial[0], []
    if partial:
        return None, partial
    return None, items


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": BROWSER_UA,
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        }
    )
    return session


def http_get(session: requests.Session, url: str, *, accept: str, timeout: int = 20) -> requests.Response:
    last: Exception | None = None
    for attempt in range(3):
        try:
            response = session.get(url, headers={"Accept": accept}, timeout=timeout)
        except requests.RequestException as exc:
            last = exc
            time.sleep(1.2 * (attempt + 1))
            continue
        if response.status_code in (429, 500, 502, 503, 504):
            last = requests.HTTPError(f"{response.status_code} für {url}")
            time.sleep(1.2 * (attempt + 1))
            continue
        response.raise_for_status()
        return response
    assert last is not None
    raise last


def genius_get_params(session: requests.Session, path: str, params: dict | None = None) -> dict:
    last: Exception | None = None
    url = API_ROOT + path.lstrip("/")
    for attempt in range(3):
        try:
            response = session.get(
                url,
                params=params,
                headers={"Accept": "application/json"},
                timeout=20,
            )
        except requests.RequestException as exc:
            last = exc
            time.sleep(1.2 * (attempt + 1))
            continue
        if response.status_code in (429, 500, 502, 503, 504):
            last = requests.HTTPError(f"{response.status_code} für {url}")
            time.sleep(1.2 * (attempt + 1))
            continue
        response.raise_for_status()
        payload = response.json()
        status = payload.get("meta", {}).get("status")
        if status not in (200, None):
            raise requests.HTTPError(f"Genius {path}: {payload.get('meta')}")
        return payload["response"]
    assert last is not None
    raise last


def iter_section_hits(payload: dict, hit_type: str):
    seen: set[int | str] = set()
    for section in payload.get("sections", []):
        for hit in section.get("hits") or []:
            if hit.get("type") != hit_type:
                continue
            result = hit.get("result") or {}
            key = result.get("id") or result.get("url")
            if key in seen:
                continue
            seen.add(key)
            yield result


def search_multi(session: requests.Session, query: str) -> dict:
    return genius_get_params(session, "search/multi", {"q": query})


def page_until(session: requests.Session, path: str, list_key: str) -> list[dict]:
    items: list[dict] = []
    page = 1
    while page:
        response = genius_get_params(session, path, {"per_page": 50, "page": page})
        batch = response.get(list_key) or []
        items.extend(batch)
        nxt = response.get("next_page")
        page = int(nxt) if nxt else 0
        if page:
            time.sleep(0.15)
    return items


def album_year(album: dict) -> str:
    parts = album.get("release_date_components") or {}
    year = parts.get("year")
    return str(year) if year else ""


def format_choice(kind: str, rows: list[str]) -> str:
    return "CHOOSE " + kind + "\n" + "\n".join(rows)


def album_row(album: dict) -> str:
    artist = (album.get("primary_artist_names") or (album.get("artist") or {}).get("name") or "")
    year = album_year(album)
    bits = [album.get("name") or ""]
    if artist:
        bits.append(artist)
    if year:
        bits.append(year)
    bits.append(album.get("url") or "")
    return "- " + " | ".join(bits)


def song_row(song: dict) -> str:
    return "- " + " | ".join(
        [
            song.get("title") or "",
            song.get("primary_artist_names") or "",
            song.get("url") or "",
        ]
    )


def resolve_artist(session: requests.Session, name: str) -> tuple[dict | None, str | None]:
    payload = search_multi(session, name)
    artists = list(iter_section_hits(payload, "artist"))
    exact = [artist for artist in artists if norm(artist.get("name") or "") == norm(name)]
    pool = exact or artists
    if len(pool) > 1:
        verified = [artist for artist in pool if artist.get("is_verified")]
        if len(exact) == 1:
            pool = exact
        elif len(verified) == 1 and exact:
            pool = verified
    chosen, options = choose_by_name(name, pool, lambda artist: artist.get("name") or "")
    if chosen is None:
        rows = [
            "- " + " | ".join([artist.get("name") or "", artist.get("url") or ""])
            for artist in options
        ]
        return None, format_choice("artist", rows or ["- (keine Treffer)"])
    return chosen, None


def artist_albums(session: requests.Session, artist_id: int) -> list[dict]:
    return page_until(session, f"artists/{artist_id}/albums", "albums")


def album_tracks(session: requests.Session, album_id: int) -> list[dict]:
    tracks = page_until(session, f"albums/{album_id}/tracks", "tracks")
    songs = []
    seen: set[str] = set()
    for track in tracks:
        song = track.get("song") or {}
        url = (song.get("url") or "").split("?")[0]
        if not url.lower().endswith("-lyrics") or url in seen:
            continue
        if is_instrumental(song.get("title"), url):
            continue
        seen.add(url)
        songs.append(song)
    return songs


def group_from_album(album: dict, songs: list[dict]) -> AlbumGroup:
    artist = album.get("primary_artist_names") or (album.get("artist") or {}).get("name")
    name = (album.get("name") or "").strip()
    group = AlbumGroup(
        artist=artist,
        album=name,
        album_url=album.get("url"),
        year=album_year(album),
        folder=None,
    )
    for song in songs:
        group.songs.append(
            SongLink(
                url=song["url"].split("?")[0],
                title=song.get("title"),
                artist=artist,
                album=name,
                album_url=album.get("url"),
                year=group.year,
            )
        )
    return group


def resolve_album_for_artist(session: requests.Session, artist: dict, album_name: str) -> tuple[dict | None, str | None]:
    albums = artist_albums(session, artist["id"])
    chosen, options = choose_by_name(album_name, albums, lambda album: album.get("name") or "")
    if chosen is None:
        rows = [album_row(album) for album in options]
        header = f"artist: {artist.get('name')}"
        return None, format_choice("album", [header, *rows] or [header, "- (keine Alben)"])
    return chosen, None


def collect_artist_album(session: requests.Session, artist_name: str, album_name: str | None, take_all: bool) -> tuple[list[AlbumGroup] | None, str | None]:
    artist, choice = resolve_artist(session, artist_name)
    if choice:
        return None, choice
    assert artist is not None
    if take_all:
        groups = []
        for album in artist_albums(session, artist["id"]):
            songs = album_tracks(session, album["id"])
            if songs:
                groups.append(group_from_album(album, songs))
            time.sleep(0.15)
        if not groups:
            return None, f"Keine Alben mit Lyrics-Links für {artist.get('name')}."
        return groups, None
    if not album_name:
        albums = artist_albums(session, artist["id"])
        rows = [f"artist: {artist.get('name')}", *[album_row(album) for album in albums]]
        return None, format_choice("album", rows)
    album, choice = resolve_album_for_artist(session, artist, album_name)
    if choice:
        return None, choice
    assert album is not None
    songs = album_tracks(session, album["id"])
    if not songs:
        return None, f"Keine Lyrics-Links auf {album.get('url')}."
    return [group_from_album(album, songs)], None


def collect_album_query(session: requests.Session, album_name: str, artist_name: str | None) -> tuple[list[AlbumGroup] | None, str | None]:
    if artist_name:
        return collect_artist_album(session, artist_name, album_name, take_all=False)
    payload = search_multi(session, album_name)
    albums = list(iter_section_hits(payload, "album"))
    chosen, options = choose_by_name(album_name, albums, lambda album: album.get("name") or "")
    if chosen is None:
        return None, format_choice("album", [album_row(album) for album in options] or ["- (keine Alben)"])
    songs = album_tracks(session, chosen["id"])
    if not songs:
        return None, f"Keine Lyrics-Links auf {chosen.get('url')}."
    return [group_from_album(chosen, songs)], None


def is_instrumental(title: str | None, url: str | None = None) -> bool:
    if url and "-instrumental" in url.lower():
        return True
    if not title:
        return False
    return re.search(
        r"(?i)(?:^|[\s\-(])instrumental(?:$|[\s)\].\-])",
        title,
    ) is not None


def is_lyric_song(song: dict) -> bool:
    url = (song.get("url") or "").split("?")[0].lower()
    return url.endswith("-lyrics") and not is_instrumental(song.get("title"), url)


def collect_song(session: requests.Session, title: str, artist_name: str | None) -> tuple[list[AlbumGroup] | None, str | None]:
    query = f"{artist_name} {title}" if artist_name else title
    payload = search_multi(session, query)
    songs = [song for song in iter_section_hits(payload, "song") if is_lyric_song(song)]
    if artist_name:
        artist_norm = norm(artist_name)
        by_primary = [
            song
            for song in songs
            if artist_norm == norm(song.get("primary_artist_names") or "")
            or artist_norm in norm(song.get("primary_artist_names") or "")
        ]
        if by_primary:
            songs = by_primary
    chosen, options = choose_by_name(title, songs, lambda song: song.get("title") or "")
    if chosen is None:
        return None, format_choice("song", [song_row(song) for song in options] or ["- (keine Songs)"])
    artist = chosen.get("primary_artist_names")
    group = AlbumGroup(artist=artist, album=None, album_url=None, year=None, folder=None)
    group.songs.append(
        SongLink(
            url=chosen["url"].split("?")[0],
            title=chosen.get("title"),
            artist=artist,
        )
    )
    return [group], None


def classify_genius_url(url: str) -> tuple[str, list[str]]:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) >= 3 and parts[0] == "albums":
        return "album", parts[1:]
    if len(parts) >= 2 and parts[0] == "artists":
        return "artist", parts[1:]
    if parts and parts[0].lower().endswith("-lyrics"):
        return "song", parts
    return "unknown", parts


def collect_url(session: requests.Session, url: str) -> tuple[list[AlbumGroup] | None, str | None]:
    kind, parts = classify_genius_url(url)
    if kind == "song":
        group = AlbumGroup(artist=None, album=None, album_url=None, year=None, folder=None)
        group.songs.append(SongLink(url=url.split("?")[0]))
        return [group], None
    if kind == "artist":
        slug = parts[0].replace("-", " ")
        return collect_artist_album(session, slug, None, take_all=False)
    if kind == "album":
        artist_slug = parts[0].replace("-", " ")
        album_slug = parts[1].replace("-", " ")
        return collect_artist_album(session, artist_slug, album_slug, take_all=False)
    return None, f"Die URL ist keine Genius-Album-, Künstler- oder Lyrics-Seite: {url}"


def render_url_file(groups: list[AlbumGroup]) -> str:
    blocks = []
    for group in groups:
        lines: list[str] = []
        if group.artist:
            lines.append(f"# artist: {group.artist}")
        if group.album:
            lines.append(f"# album: {group.album}")
        if group.year:
            lines.append(f"# year: {group.year}")
        if group.album_url:
            lines.append(f"# album-url: {group.album_url}")
        if group.folder:
            lines.append(f"# folder: {group.folder}")
        lines.append("")
        for song in group.songs:
            if song.title:
                lines.append(f"# title: {song.title}")
            lines.append(song.url)
        blocks.append("\n".join(lines).strip())
    return "\n\n".join(blocks).rstrip() + "\n"


def default_url_path(groups: list[AlbumGroup]) -> Path:
    group = groups[0]
    artist = safe_name(group.artist or "genius")
    if len(groups) > 1:
        name = f"{artist}-discography.urls"
    elif group.album:
        name = f"{artist}-{safe_name(group.album)}.urls"
    elif group.songs and group.songs[0].title:
        name = f"{artist}-{safe_name(group.songs[0].title)}.urls"
    else:
        name = f"{artist}.urls"
    return Path("urls") / name


def parse_url_file(content: str) -> list[SongLink]:
    artist = album = album_url = year = folder = title = None
    songs: list[SongLink] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            body = line[1:].strip()
            key, sep, value = body.partition(":")
            if not sep:
                continue
            key = key.strip().lower()
            value = value.strip()
            if key == "artist":
                artist = value or None
            elif key == "album":
                album = value or None
            elif key == "album-url":
                album_url = value or None
            elif key == "year":
                year = value or None
            elif key == "folder":
                folder = value or None
            elif key == "title":
                title = value or None
            continue
        if line.startswith(("http://", "https://")):
            songs.append(
                SongLink(
                    url=line,
                    title=title,
                    artist=artist,
                    album=album,
                    album_url=album_url,
                    year=year,
                    folder=folder,
                )
            )
            title = None
    return songs


def _bookmark_children(node):
    children = [child for child in node.children if getattr(child, "name", None)]
    if len(children) == 1 and children[0].name == "p":
        children = [child for child in children[0].children if getattr(child, "name", None)]
    return children


def _add_bookmark_link(anchor, stack: list[str], out: list[SongLink]) -> None:
    href = anchor["href"].strip()
    if not href.startswith(("http://", "https://")):
        return
    folder = "/".join(safe_name(part) for part in stack) or None
    out.append(
        SongLink(
            url=href,
            title=anchor.get_text(strip=True) or None,
            folder=folder,
        )
    )


def _walk_bookmark_dt(dt, stack: list[str], out: list[SongLink]) -> None:
    heading = dt.find("h3", recursive=False)
    anchor = dt.find("a", href=True, recursive=False)
    if heading:
        stack.append(heading.get_text(strip=True))
    if anchor:
        _add_bookmark_link(anchor, stack, out)
    for nested in dt.find_all("dl", recursive=False):
        _walk_bookmark_container(nested, stack, out)
    for nested in dt.find_all("dt", recursive=False):
        _walk_bookmark_dt(nested, stack, out)
    if heading:
        stack.pop()


def _walk_bookmark_container(node, stack: list[str], out: list[SongLink]) -> None:
    children = _bookmark_children(node)
    index = 0
    while index < len(children):
        child = children[index]
        sibling_dl = (
            child.name == "dt"
            and child.find("h3", recursive=False)
            and not child.find("dl", recursive=False)
            and index + 1 < len(children)
            and children[index + 1].name == "dl"
        )
        if sibling_dl:
            stack.append(child.find("h3", recursive=False).get_text(strip=True))
            _walk_bookmark_container(children[index + 1], stack, out)
            stack.pop()
            index += 2
            continue
        if child.name == "dt":
            _walk_bookmark_dt(child, stack, out)
        elif child.name in ("dl", "p"):
            _walk_bookmark_container(child, stack, out)
        index += 1


def parse_bookmarks(content: str) -> list[SongLink] | None:
    lowered = content.lower()
    if "<dt" not in lowered and "<dl" not in lowered:
        return None
    soup = BeautifulSoup(content, "html.parser")
    songs: list[SongLink] = []
    # Der Ordner-Titel kann über dem ersten <DL> stehen. Deshalb ab Dokumentwurzel.
    _walk_bookmark_container(soup, [], songs)
    return songs or None


def parse_text_urls(content: str) -> list[SongLink]:
    songs = []
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line.startswith(("http://", "https://")):
            songs.append(SongLink(url=line))
    return songs


def load_songs(path: Path) -> list[SongLink]:
    content = path.read_text(encoding="utf-8", errors="ignore")
    if "# artist:" in content or "# album:" in content or "# title:" in content:
        songs = parse_url_file(content)
        if songs:
            print(f"  URL-Datei ({len(songs)} Links)")
            return songs
    bookmarks = parse_bookmarks(content)
    if bookmarks:
        print(f"  HTML-Bookmarks ({len(bookmarks)} Links)")
        return bookmarks
    songs = parse_text_urls(content)
    print(f"  URL-Liste ({len(songs)} Links)")
    return songs


def container_text(container) -> str:
    # Genius packt "N Contributors" und den Seitentitel in diesen Knoten.
    for node in container.select("[data-exclude-from-selection]"):
        node.decompose()
    for br in container.find_all("br"):
        br.replace_with("\n")
    lines: list[str] = []
    for line in container.get_text().splitlines():
        line = line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).strip()


def extract_genius_lyrics(soup: BeautifulSoup) -> str | None:
    containers = soup.select('[data-lyrics-container="true"]')
    parts = [container_text(container) for container in containers]
    parts = [part for part in parts if part]
    if parts:
        return "\n\n".join(parts)

    lyric_div = soup.select_one(
        '.lyrics, .Lyrics__Container-sc-1ynbvzw-1, [class*="Lyrics__Container"]'
    )
    if lyric_div:
        text = container_text(lyric_div)
        if text:
            return text

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and data.get("articleBody"):
            body = str(data["articleBody"]).strip()
            if body:
                return body
    return None


def generic_text(soup: BeautifulSoup) -> str:
    for tag in soup(
        ["script", "style", "noscript", "header", "footer", "nav", "aside", "form", "iframe", "svg", "button"]
    ):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text(separator="\n").splitlines()]
    return "\n".join(line for line in lines if line)


def page_title(soup: BeautifulSoup) -> str | None:
    title = soup.find("title")
    if not title:
        return None
    text = title.get_text(strip=True)
    return text or None


def extract_document(session: requests.Session, url: str, *, raw: bool = False) -> tuple[str, str, str | None]:
    response = http_get(session, url, accept="text/html")
    soup = BeautifulSoup(response.text, "html.parser")
    title = page_title(soup)
    host = urlparse(url).netloc.lower()
    if not raw and "genius.com" in host:
        lyrics = extract_genius_lyrics(soup)
        if lyrics:
            return lyrics, "genius", title
    return generic_text(soup), "generic", title


def song_filename(song: SongLink, page_title_text: str | None) -> str:
    if song.title:
        title = clean_title(song.title, song.artist)
    elif page_title_text:
        title = clean_title(page_title_text, song.artist)
    else:
        parsed = urlparse(song.url)
        title = safe_name(parsed.path.strip("/")) or "untitled"
    return safe_name(title) + ".txt"


def song_directory(root: Path, song: SongLink) -> Path:
    if song.artist and song.album:
        return root / safe_name(song.artist) / safe_name(song.album)
    if song.folder:
        return root / Path(*[safe_name(part) for part in Path(song.folder).parts])
    if song.artist:
        return root / safe_name(song.artist)
    return root


def document_path(directory: Path, song: SongLink) -> Path:
    if song.artist and song.album:
        name = f"{safe_name(song.artist)} - {safe_name(song.album)}.txt"
    elif song.album:
        name = f"{safe_name(song.album)}.txt"
    elif song.folder:
        name = f"{safe_name(Path(song.folder).name)}.txt"
    else:
        name = "lyrics.txt"
    return directory / name


def song_file_text(title: str, body: str) -> str:
    return f"{title}\n{'=' * 40}\n\n{body.strip()}\n"


def read_song_file(path: Path) -> tuple[str, str] | None:
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 4 or lines[1] != "=" * 40 or lines[2] != "":
        return None
    title = lines[0].strip()
    body = "\n".join(lines[3:]).strip()
    if not title or not body:
        return None
    return title, body


def render_document(songs: list[tuple[SongLink, str, str]]) -> str:
    first = songs[0][0]
    heading = " - ".join(part for part in (first.artist, first.album) if part) or first.title or "Lyrics"
    if first.year:
        heading += f" ({first.year})"
    lines = [f"# {heading}"]
    if first.album_url:
        lines.append(f"# {first.album_url}")
    lines.append("")
    for song, title, body in songs:
        lines.append("---")
        lines.append(f"## {title}")
        lines.append("")
        lines.append(body.strip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def group_songs(songs: list[SongLink]) -> list[list[SongLink]]:
    groups: dict[tuple, list[SongLink]] = {}
    for song in songs:
        key = (song.artist, song.album, song.album_url, song.year, song.folder)
        groups.setdefault(key, []).append(song)
    return list(groups.values())


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fetch_songs(
    session: requests.Session,
    songs: list[SongLink],
    target_dir: Path,
    *,
    combine: bool,
    raw: bool,
    single_output: Path | None,
    delay: float,
    on_song=None,
) -> tuple[int, list[str], list[Path]]:
    ok = 0
    failed: list[str] = []
    documents: list[Path] = []
    written: dict[str, tuple[SongLink, str, str]] = {}
    songs = [song for song in songs if not is_instrumental(song.title, song.url)]

    if single_output and len(songs) != 1:
        raise SystemExit("--output gilt nur für eine URL.")

    networked = False
    for index, song in enumerate(songs):
        path = None if single_output else song_directory(target_dir, song) / song_filename(song, None)
        cached = read_song_file(path) if path is not None else None
        if cached and not is_instrumental(cached[0], song.url):
            title, body = cached
            print(f"[.] {title}  liegt schon da")
            ok += 1
            written[song.url] = (song, title, body)
            if on_song:
                on_song(index + 1, len(songs), title, song.album or "")
            continue
        if on_song:
            on_song(index + 1, len(songs), song.title or song.url, song.album or "")
        if networked:
            time.sleep(delay)
        networked = True
        try:
            body, source, html_title = extract_document(session, song.url, raw=raw)
        except Exception as exc:
            print(f"[X] {song.url}  ->  FEHLER: {exc}", file=sys.stderr)
            failed.append(song.url)
            continue
        if not body.strip():
            print(f"[X] {song.url}  ->  FEHLER: leerer Text", file=sys.stderr)
            failed.append(song.url)
            continue
        title = clean_title(song.title or html_title or song.url, song.artist)
        if single_output:
            path = single_output
        else:
            path = song_directory(target_dir, song) / song_filename(song, html_title)
        write_text(path, song_file_text(title, body))
        marker = "G" if source == "genius" else "W"
        print(f"[{marker}] {title}  ->  {path}  ({len(body)} Zeichen)")
        ok += 1
        written[song.url] = (song, title, body)

    if combine and not single_output:
        for batch in group_songs(songs):
            rows = []
            for song in batch:
                if song.url in written:
                    link, title, body = written[song.url]
                    rows.append((link, title, body))
            if not rows:
                continue
            directory = song_directory(target_dir, rows[0][0])
            doc = document_path(directory, rows[0][0])
            write_text(doc, render_document(rows))
            documents.append(doc)
            print(f"[D] {doc}  ({len(rows)} Songs)")
    elif combine and single_output and written:
        documents.append(single_output)

    failed_path = target_dir / "failed.txt"
    if failed:
        write_text(failed_path, "\n".join(failed) + "\n")
        print(f"Fehlgeschlagen: {failed_path}")
    elif failed_path.exists():
        failed_path.unlink()
    return ok, failed, documents


def run_collect(args: argparse.Namespace) -> int:
    session = make_session()
    groups: list[AlbumGroup] | None
    choice: str | None
    if args.url:
        groups, choice = collect_url(session, args.url)
    elif args.song:
        groups, choice = collect_song(session, args.song, args.artist)
    elif args.artist and args.all:
        groups, choice = collect_artist_album(session, args.artist, None, take_all=True)
    elif args.artist and args.album:
        groups, choice = collect_artist_album(session, args.artist, args.album, take_all=False)
    elif args.artist:
        groups, choice = collect_artist_album(session, args.artist, None, take_all=False)
    elif args.album:
        groups, choice = collect_album_query(session, args.album, None)
    else:
        print("collect braucht --artist, --album, --song oder --url.", file=sys.stderr)
        return 1
    if choice:
        print(choice)
        return 2
    assert groups is not None
    path = Path(args.output) if args.output else default_url_path(groups)
    write_text(path, render_url_file(groups))
    count = sum(len(group.songs) for group in groups)
    print(f"{count} Songs")
    if groups[0].artist:
        print(f"artist: {groups[0].artist}")
    if len(groups) == 1 and groups[0].album:
        print(f"album: {groups[0].album}")
    print(f"file: {path}")
    return 0


def run_fetch(args: argparse.Namespace) -> int:
    session = make_session()
    songs: list[SongLink] = []
    for item in args.input:
        path = Path(item)
        if path.exists():
            print(f"Lade: {path}")
            songs.extend(load_songs(path))
        elif item.startswith(("http://", "https://")):
            songs.append(SongLink(url=item))
        else:
            print(f"Warnung: überspringe '{item}'", file=sys.stderr)
    if not songs:
        print("Keine URLs gefunden.", file=sys.stderr)
        return 1
    print(f"\n{len(songs)} URLs. Starte Download...\n")
    ok, failed, documents = fetch_songs(
        session,
        songs,
        Path(args.dir),
        combine=args.combine,
        raw=args.raw,
        single_output=Path(args.output) if args.output else None,
        delay=args.delay,
    )
    print(f"\nFertig: {ok} Songs, {len(failed)} fehlgeschlagen.")
    for doc in documents:
        print(f"document: {doc}")
    return 0 if ok and not failed else (1 if not ok else 0)


def build_collect_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="web2txt.py collect", description="Genius-Links in eine URL-Datei schreiben")
    parser.add_argument("--artist", help="Interpret, wie er auf Genius heißt")
    parser.add_argument("--album", help="Albumname")
    parser.add_argument("--song", help="Ein einzelner Song")
    parser.add_argument("--url", help="Genius-URL eines Albums, Interpreten oder Songs")
    parser.add_argument("--all", action="store_true", help="Alle Alben des Interpreten")
    parser.add_argument("--output", "-o", help="Zieldatei für die URLs")
    return parser


def build_fetch_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="web2txt.py fetch", description="URL-Datei, Bookmarks oder URLs in Textdateien")
    parser.add_argument("input", nargs="+", help="URLs oder Dateien")
    parser.add_argument("--output", "-o", help="Eine Zieldatei, nur bei einer URL")
    parser.add_argument("--dir", "-d", default="lyrics", help="Zielordner (Standard: lyrics)")
    parser.add_argument("--combine", dest="combine", action="store_true", default=True)
    parser.add_argument("--no-combine", dest="combine", action="store_false", help="Kein Album-Dokument")
    parser.add_argument("--raw", action="store_true", help="Kein Genius-Lyrics-Filter")
    parser.add_argument("--delay", type=float, default=0.3, help="Pause zwischen Seiten in Sekunden")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        build_fetch_parser().print_help()
        return 1
    if args[0] == "ui":
        from ui_server import main as ui_main
        return ui_main(args[1:])
    if args[0] == "collect":
        return run_collect(build_collect_parser().parse_args(args[1:]))
    if args[0] == "fetch":
        return run_fetch(build_fetch_parser().parse_args(args[1:]))
    return run_fetch(build_fetch_parser().parse_args(args))


if __name__ == "__main__":
    raise SystemExit(main())
