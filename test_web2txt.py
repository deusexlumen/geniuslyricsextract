import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

import web2txt


LYRICS_HTML = (
    "<html><head><title>Genetikk – Supa Dope Brothers Lyrics | Genius Lyrics</title></head><body>"
    '<div data-lyrics-container="true">'
    '<div data-exclude-from-selection="true"><span>28 Contributors</span>'
    "<h2>Supa Dope Brothers Lyrics</h2></div>"
    "[Part 1: Karuzo]<br>Zeile eins<br>"
    '<a class="ReferentFragment-desktop__ClickTarget"><span>Zeile zwei</span></a><br><br>'
    "[Hook]<br>Refrain</div>"
    '<div data-lyrics-container="true"></div>'
    '<div data-lyrics-container="true">[Part 2: Karuzo]<br>Weiter</div>'
    "</body></html>"
)

BOOKMARKS = """
<DL><p>
  <DT><H3>Voodoozirkus</H3>
  <DL><p>
    <DT><H3>Neuer Ordner</H3>
    <DL><p>
      <DT><A HREF="https://genius.com/Genetikk-supa-dope-brothers-lyrics">Genetikk – Supa Dope Brothers Lyrics | Genius Lyrics</A>
      <DT><A HREF="https://genius.com/Genetikk-wer-bist-du-lyrics">Genetikk – Wer bist du? Lyrics | Genius Lyrics</A>
    </DL><p>
  </DL><p>
</DL>
"""


class CleanTests(unittest.TestCase):
    def test_genius_lyrics_drop_contributor_chrome(self):
        text = web2txt.extract_genius_lyrics(BeautifulSoup(LYRICS_HTML, "html.parser"))
        self.assertEqual(
            text,
            "[Part 1: Karuzo]\nZeile eins\nZeile zwei\n\n[Hook]\nRefrain\n\n[Part 2: Karuzo]\nWeiter",
        )
        self.assertNotIn("Contributors", text)

    def test_safe_name_is_a_windows_filename(self):
        self.assertEqual(web2txt.safe_name("24/7"), "24-7")
        self.assertEqual(web2txt.safe_name("Wer bist du?"), "Wer bist du")
        self.assertEqual(web2txt.safe_name("G.E.N.E.T.I.K.K."), "G.E.N.E.T.I.K.K")

    def test_clean_title_strips_genius_suffix_and_artist(self):
        self.assertEqual(
            web2txt.clean_title(
                "Genetikk – Supa Dope Brothers Lyrics | Genius Lyrics",
                "Genetikk",
            ),
            "Supa Dope Brothers",
        )

    def test_choose_exact_album_over_longer_name(self):
        albums = [{"name": "MDNA"}, {"name": "MDNA + 6"}]
        chosen, options = web2txt.choose_by_name("MDNA", albums, lambda item: item["name"])
        self.assertEqual(chosen["name"], "MDNA")
        self.assertEqual(options, [])

    def test_choose_without_query_asks(self):
        albums = [{"name": "Voodoozirkus"}, {"name": "D.N.A."}]
        chosen, options = web2txt.choose_by_name(None, albums, lambda item: item["name"])
        self.assertIsNone(chosen)
        self.assertEqual(len(options), 2)


class InputTests(unittest.TestCase):
    def test_bookmarks_keep_folders(self):
        songs = web2txt.parse_bookmarks(BOOKMARKS)
        self.assertEqual(len(songs), 2)
        self.assertEqual(songs[0].folder, "Voodoozirkus/Neuer Ordner")
        self.assertTrue(songs[0].url.endswith("-lyrics"))

    def test_real_bookmark_export(self):
        path = Path("user_pasted_clipboard_long_content_as_file_DT.txt")
        if not path.exists():
            self.skipTest("export fehlt")
        songs = web2txt.parse_bookmarks(path.read_text(encoding="utf-8", errors="ignore"))
        self.assertIsNotNone(songs)
        self.assertGreaterEqual(len(songs), 15)
        self.assertTrue(all(song.folder and song.folder.startswith("Voodoozirkus") for song in songs))
        self.assertTrue(all(song.url.endswith("-lyrics") for song in songs))

    def test_url_file_roundtrip(self):
        group = web2txt.AlbumGroup(
            artist="Genetikk",
            album="Voodoozirkus",
            album_url="https://genius.com/albums/Genetikk/Voodoozirkus",
            year="2012",
            folder=None,
            songs=[
                web2txt.SongLink(
                    url="https://genius.com/Genetikk-supa-dope-brothers-lyrics",
                    title="Supa Dope Brothers",
                    artist="Genetikk",
                    album="Voodoozirkus",
                    year="2012",
                )
            ],
        )
        parsed = web2txt.parse_url_file(web2txt.render_url_file([group]))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].title, "Supa Dope Brothers")
        self.assertEqual(parsed[0].album, "Voodoozirkus")
        self.assertEqual(parsed[0].year, "2012")
        self.assertEqual(parsed[0].artist, "Genetikk")


class FetchTests(unittest.TestCase):
    def test_fetch_writes_song_and_document(self):
        def fake_extract(session, url, *, raw=False):
            return ("[Part 1: Karuzo]\nZeile", "genius", "ignored")

        original = web2txt.extract_document
        web2txt.extract_document = fake_extract
        try:
            songs = [
                web2txt.SongLink(
                    url="https://genius.com/Genetikk-supa-dope-brothers-lyrics",
                    title="Supa Dope Brothers",
                    artist="Genetikk",
                    album="Voodoozirkus",
                    album_url="https://genius.com/albums/Genetikk/Voodoozirkus",
                    year="2012",
                ),
                web2txt.SongLink(
                    url="https://genius.com/Genetikk-wer-bist-du-lyrics",
                    title="Wer bist du?",
                    artist="Genetikk",
                    album="Voodoozirkus",
                    album_url="https://genius.com/albums/Genetikk/Voodoozirkus",
                    year="2012",
                ),
            ]
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ok, failed, docs = web2txt.fetch_songs(
                    session=None,
                    songs=songs,
                    target_dir=root,
                    combine=True,
                    raw=False,
                    single_output=None,
                    delay=0,
                )
                self.assertEqual(ok, 2)
                self.assertEqual(failed, [])
                song_file = root / "Genetikk" / "Voodoozirkus" / "Supa Dope Brothers.txt"
                self.assertIn("[Part 1: Karuzo]", song_file.read_text(encoding="utf-8"))
                self.assertNotIn("Contributors", song_file.read_text(encoding="utf-8"))
                self.assertEqual(len(docs), 1)
                document = docs[0].read_text(encoding="utf-8")
                self.assertTrue(document.startswith("# Genetikk - Voodoozirkus (2012)\n"))
                self.assertIn("## Supa Dope Brothers\n\n[Part 1: Karuzo]", document)
                self.assertIn("## Wer bist du?", document)
                self.assertLess(document.index("Supa Dope Brothers"), document.index("Wer bist du?"))
        finally:
            web2txt.extract_document = original


if __name__ == "__main__":
    unittest.main()
