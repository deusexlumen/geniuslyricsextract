# web2txt

Holt Songtexte von Genius und schreibt sie als Textdateien. Genius ist die Quelle, weil dort die meisten Lyrics liegen.

Zwei Ergebnisse pro Album:

- eine URL-Datei, ein Song pro Zeile, in der Reihenfolge des Albums
- ein Dokument mit allen Texten, plus eine Datei pro Song

## Schnellstart

1. Das [ZIP-Archiv](https://github.com/deusexlumen/geniuslyricsextract/archive/refs/heads/main.zip) herunterladen.
2. Entpacken und den Ordner `geniuslyricsextract-main` öffnen, nicht im ZIP bleiben.
3. Unter Windows `start.bat` doppelklicken. Unter macOS oder Linux im Terminal in diesem Ordner `chmod +x start.sh && ./start.sh` ausführen.

Python 3.10 oder neuer muss bereits installiert sein. Beim ersten Start werden die benötigten Pakete automatisch eingerichtet. Danach öffnet sich der Browser unter `http://127.0.0.1:8765`. Die Seite läuft nur auf diesem Rechner.

Interpret eintragen, Alben anzeigen, die gewünschten Veröffentlichungen angehakt lassen und `Texte holen` drücken. Für einen Interpreten mit wenigen Alben alle Haken lassen.

Während des Downloads zeigt die Seite eine große Zahl, zum Beispiel `120 von 400`, einen Balken und den Song, der gerade geholt wird. Darunter stehen die Songs, die in diesem Lauf schon durch sind. Ein neuer Song dauert ungefähr 1,5 bis 2 Sekunden. Eine Discographie mit rund 1000 Songs braucht etwa eine halbe Stunde. Ein Album mit 15 Songs ist in unter einer Minute fertig. Die Seite offen lassen. Ein Neuladen zeigt denselben Lauf wieder an.

Die Dateien liegen danach an denselben Orten wie bei den Befehlen von Hand.

Im Terminal geht dasselbe so:

```bash
pip install -r requirements.txt
python web2txt.py ui
```

## Mit dem Skill

In Grok den Skill `/genius-lyrics` aufrufen und Interpret plus Album nennen:

```text
/genius-lyrics Genetikk, Album Voodoozirkus
```

Der Skill sucht den Interpreten und das Album, schreibt die URLs und baut das Dokument. Ohne Albumnamen kommt zuerst die Albumliste. „Nur die Links“ stoppt nach der URL-Datei.

## Von Hand

Alben eines Interpreten anzeigen. Der Befehl endet mit Code 2 und schreibt noch keine Datei:

```bash
python web2txt.py collect --artist "Genetikk"
```

Ein Album sammeln und danach die Texte holen:

```bash
python web2txt.py collect --artist "Genetikk" --album "Voodoozirkus" -o urls/genetikk-voodoozirkus.urls
python web2txt.py fetch urls/genetikk-voodoozirkus.urls
```

Ein einzelner Song:

```bash
python web2txt.py collect --artist "Genetikk" --song "Supa Dope Brothers" -o urls/genetikk-supa-dope-brothers.urls
python web2txt.py fetch urls/genetikk-supa-dope-brothers.urls
```

Alle Alben eines Interpreten:

```bash
python web2txt.py collect --artist "Genetikk" --all -o urls/genetikk-discography.urls
python web2txt.py fetch urls/genetikk-discography.urls
```

Eine Genius-URL geht auch direkt, Album, Interpret oder Song:

```bash
python web2txt.py collect --url "https://genius.com/albums/Genetikk/Voodoozirkus" -o urls/genetikk-voodoozirkus.urls
python web2txt.py "https://genius.com/Genetikk-supa-dope-brothers-lyrics"
```

Eigene Linkliste, eine URL pro Zeile, oder eine Netscape-Bookmark-Datei aus dem Browser. Ordner in der Bookmark-Datei werden als Ordner übernommen:

```bash
python web2txt.py fetch meine-urls.txt
python web2txt.py fetch bookmarks.html --dir lyrics
```

`--no-combine` lässt das Sammeldokument weg. `--output datei.txt` schreibt bei genau einer URL nur diese eine Datei. `--delay 0.5` verlängert die Pause zwischen den Seiten. `--raw` nimmt den ganzen Seitentext, ohne den Genius-Lyrics-Filter.

## Dateien

Die URL-Datei ist die Liste, von der `fetch` ausgeht:

```text
# artist: Genetikk
# album: Voodoozirkus
# year: 2012
# album-url: https://genius.com/albums/Genetikk/Voodoozirkus

# title: Supa Dope Brothers
https://genius.com/Genetikk-supa-dope-brothers-lyrics
```

Jede Lyrics-URL endet auf `-lyrics`. `collect` lässt Seiten mit `-annotated` oder `-sample` weg. Instrumentals fallen vorher raus: der Titel enthält das Wort Instrumental, zum Beispiel `Pharao (Instrumental)`, oder die Adresse enthält `-instrumental`. Ein normaler Song, der das Wort nur im Text hat, bleibt drin.

`fetch` legt die Texte hier ab:

```text
lyrics/Genetikk/Voodoozirkus/Supa Dope Brothers.txt
lyrics/Genetikk/Voodoozirkus/Genetikk - Voodoozirkus.txt
```

Die einzelne Songdatei hat den Titel und darunter den Text. Das Dokument fasst das Album zusammen:

```text
# Genetikk - Voodoozirkus (2012)
# https://genius.com/albums/Genetikk/Voodoozirkus

---
## Supa Dope Brothers

[Part 1: Karuzo]
...
```

Zeichen, die Windows in Dateinamen verbietet, werden ersetzt. `24/7` wird zur Datei `24-7.txt`. Im Dokument bleibt die Überschrift `24/7`.

## Wenn der Name nicht eindeutig ist

`collect` druckt eine Liste und endet mit Code 2:

```text
CHOOSE album
artist: Genetikk
- Voodoozirkus | Genetikk | 2012 | https://genius.com/albums/Genetikk/Voodoozirkus
- D.N.A. | Genetikk | 2013 | https://genius.com/albums/Genetikk/D-n-a
```

Den gewünschten Namen noch einmal an `--album`, `--artist` oder `--song` geben. `MDNA` trifft das Album `MDNA` und lässt `MDNA + 6` stehen, solange der Name exakt passt.

## Wenn ein Download fehlschlägt

Fehlerhafte URLs landen in `lyrics/failed.txt`, eine pro Zeile. Dieselbe Datei kann erneut an `fetch` gehen:

```bash
python web2txt.py fetch lyrics/failed.txt --dir lyrics
```

Ein Lauf ohne Fehler löscht eine alte `failed.txt`.

## Nochmal holen

`fetch` auf dieselbe URL-Datei lässt Songs aus, deren Textdatei schon da ist, und macht bei den fehlenden weiter. Schon geholte Songs erscheinen als `liegt schon da`. Das Album-Dokument wird am Ende neu geschrieben und enthält die alten und die neuen Songs. Instrumentals in einer älteren URL-Datei werden beim Holen übersprungen.

## Tests

```bash
python -m unittest test_web2txt.py
```
