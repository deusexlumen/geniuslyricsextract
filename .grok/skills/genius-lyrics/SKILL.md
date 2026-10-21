---
name: genius-lyrics
description: >
  Use when the user wants Genius lyrics, song lyrics, Songtexte, an album,
  an artist or Interpret, lyric links, or a lyrics document. Triggers include
  Genius, Lyrics, Songtext, Album, Interpret, and /genius-lyrics.
---

# Genius lyrics

Genius is the source. The result is two files: a URL list, and one lyrics document. Run the commands from the repo root. Answer in the user's language. Do not paste lyrics into the chat.

## What to collect

Read the artist and, if named, the album or the song.

- Album named: collect that album, full track order.
- Only the artist: list the albums and wait for the choice.
- Only a song: collect that one lyric URL.
- "nur die Links" / links only: stop after the URL file.
- Whole discography: `--all`.

A lyric URL ends in `-lyrics`. Leave out `-annotated`, `-sample`, and translation pages unless the user asked for those.

## Commands

List albums when none was named:

```
python web2txt.py collect --artist "ARTIST"
```

Write the album URL file, then the document:

```
python web2txt.py collect --artist "ARTIST" --album "ALBUM" -o urls/artist-album.urls
python web2txt.py fetch urls/artist-album.urls
```

One song:

```
python web2txt.py collect --artist "ARTIST" --song "TITLE" -o urls/artist-title.urls
python web2txt.py fetch urls/artist-title.urls
```

Exit code 2 prints a choice list. The first line is `CHOOSE artist`, `CHOOSE album`, or `CHOOSE song`. Show that list and wait. Run collect again with the chosen name. Do not browse Genius to invent a different list.

## Files

The URL file is the source of truth:

```
# artist: Genetikk
# album: Voodoozirkus
# year: 2012
# album-url: https://genius.com/albums/Genetikk/Voodoozirkus

# title: Supa Dope Brothers
https://genius.com/Genetikk-supa-dope-brothers-lyrics
```

Keep that order. `fetch` writes one text file per song under `lyrics/<Artist>/<Album>/` and the document `lyrics/<Artist>/<Album>/<Artist> - <Album>.txt`. Report both paths and the song count.

If collect cannot reach Genius, write that same URL-file shape by hand from the album tracklist, then run fetch on it. `failed.txt` in the lyrics folder is the next fetch input.
