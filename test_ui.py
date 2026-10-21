import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import ui_server


class PathTests(unittest.TestCase):
    def test_rejects_paths_outside_lyrics(self):
        self.assertIsNone(ui_server.lyrics_file("../README.md"))
        self.assertIsNone(ui_server.lyrics_file("..\\web2txt.py"))
        self.assertIsNone(ui_server.lyrics_file("/etc/passwd"))
        self.assertIsNone(ui_server.lyrics_file("C:/Windows/win.ini"))
        self.assertIsNone(ui_server.lyrics_file("missing.txt"))


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_page_has_the_actions(self):
        with urllib.request.urlopen(self.url("/")) as response:
            body = response.read().decode("utf-8")
        self.assertIn("Alben zeigen", body)
        self.assertIn("Texte holen", body)
        self.assertIn("Schließen", body)
        self.assertNotIn("\u2014", body)

    def test_status_starts_idle_and_hides_other_files(self):
        with urllib.request.urlopen(self.url("/api/status")) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["status"], "idle")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(self.url("/api/text?path=../README.md"))
        self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
