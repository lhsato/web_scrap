"""
bible_structure.py
──────────────────
Hierarchical data structure for bible.com NET Bible chapters,
with full MongoDB document compatibility.

PYTHON OBJECT HIERARCHY
═══════════════════════
ChapterPage
 ├── metadata             (book, chapter, version, url, scraped_at)
 └── sections[]
      ├── heading         (str | None)
      └── paragraphs[]
           └── verses[]
                ├── number     (int | None)
                └── chunks[]
                     ├── text          (str — Bible text fragment)
                     └── footnotes[]
                          ├── type    ("tn" | "sn" | "tc" | "unknown")
                          └── text    (str — full note body)

HOW THE RAW TEXT IS STRUCTURED
═══════════════════════════════
The raw paragraph text uses '#' as the delimiter between Bible text and footnotes:

    "1 In the beginning#tn Note body.sn Another note. God#sn Note. created#tn Note."
     ─── bible ─────── ─── notes block ─────────────────── ─── notes ─── ────────

  - '#' always introduces a footnote block.
  - Inside a block, multiple notes are concatenated after punctuation:
        "tn First note body.sn Second note body."
  - The note type is the first 2 characters: tn / sn / tc.
  - Trailing bible text (e.g. "God", "created") lives at the END of a
    non-last block, after the final note's closing punctuation.

MONGODB DOCUMENT SHAPE  (collection: "chapters")
════════════════════════════════════════════════
{
  "_id":        "GEN_1_NET",
  "book":       "GEN",
  "chapter":    1,
  "version":    "NET",
  "title":      "Genesis 1",
  "source_url": "https://...",
  "scraped_at": "2026-01-01T00:00:00Z",
  "sections": [
    {
      "heading": "The Creation of the World",
      "paragraphs": [
        {
          "verses": [
            {
              "number": 1,
              "plain_text": "In the beginning God created...",
              "chunks": [
                {
                  "text": "In the beginning",
                  "footnotes": [
                    { "type": "tn", "text": "The translation assumes..." },
                    { "type": "sn", "text": "In the beginning..."       }
                  ]
                },
                ...
              ]
            }
          ]
        }
      ]
    }
  ]
}

FOOTNOTE TYPES
══════════════
  tn  Translator's Note   -- translation choices, Hebrew/Greek word meanings
  sn  Study Note          -- biblical, historical, theological context
  tc  Textual Criticism   -- manuscript variants and textual traditions

RECOMMENDED MONGODB INDEXES
════════════════════════════
  db.chapters.create_index([("book",1),("chapter",1),("version",1)], unique=True)
  db.chapters.create_index("version")
  db.chapters.create_index([("sections.paragraphs.verses.plain_text","text")])
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import requests
from bs4 import BeautifulSoup, NavigableString, Tag


# ── Constants ─────────────────────────────────────────────────────────────────

FootnoteType = Literal["tn", "sn", "tc", "unknown"]
KNOWN_PREFIXES: set[str] = {"tn", "sn", "tc"}

CLS_HEADING = "ChapterContent-module__cat7xG__heading"
CLS_CHAPTER = "ChapterContent-module__cat7xG__chapter"
CLS_P       = "ChapterContent-module__cat7xG__p"
CLS_FT      = "ft"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Note boundary: start-of-string OR after punctuation, then known prefix + space
_NOTE_BOUNDARY = re.compile(r'(?:^|(?<=[.!?"\])])) *(tn|sn|tc)(?= )')


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Footnote:
    """One tn / sn / tc annotation attached to a Bible text chunk."""
    type: FootnoteType
    text: str

    def to_doc(self) -> dict[str, Any]:
        return {"type": self.type, "text": self.text}

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Footnote:
        return cls(type=doc["type"], text=doc["text"])

    def __repr__(self) -> str:
        return f"Footnote(type={self.type!r}, text={self.text[:60]!r})"


@dataclass
class Chunk:
    """
    Atomic unit: a Bible text fragment + its immediately following footnotes.
    Preserves the inline order the text will be displayed:
        text -> [fn, fn, ...] -> next text -> [fn] -> ...
    """
    text: str
    footnotes: list[Footnote] = field(default_factory=list)

    def to_doc(self) -> dict[str, Any]:
        return {
            "text":      self.text,
            "footnotes": [fn.to_doc() for fn in self.footnotes],
        }

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Chunk:
        return cls(
            text=doc["text"],
            footnotes=[Footnote.from_doc(f) for f in doc.get("footnotes", [])],
        )

    def __repr__(self) -> str:
        return f"Chunk({self.text[:45]!r}, fns={len(self.footnotes)})"


@dataclass
class Verse:
    """One verse (or unnumbered poetic line) composed of ordered Chunks."""
    number: int | None
    chunks: list[Chunk] = field(default_factory=list)

    @property
    def plain_text(self) -> str:
        return " ".join(c.text for c in self.chunks if c.text).strip()

    @property
    def all_footnotes(self) -> list[Footnote]:
        return [fn for chunk in self.chunks for fn in chunk.footnotes]

    def footnotes_by_type(self, ftype: FootnoteType) -> list[Footnote]:
        return [fn for fn in self.all_footnotes if fn.type == ftype]

    def to_doc(self) -> dict[str, Any]:
        return {
            "number":     self.number,
            "plain_text": self.plain_text,
            "chunks":     [c.to_doc() for c in self.chunks],
        }

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Verse:
        v = cls(number=doc["number"])
        v.chunks = [Chunk.from_doc(c) for c in doc.get("chunks", [])]
        return v

    def __repr__(self) -> str:
        return (
            f"Verse(number={self.number}, "
            f"chunks={len(self.chunks)}, "
            f"footnotes={len(self.all_footnotes)})"
        )


@dataclass
class Paragraph:
    """One <div class='__p'> block -- a group of consecutive verses."""
    verses: list[Verse] = field(default_factory=list)

    @property
    def plain_text(self) -> str:
        return " ".join(v.plain_text for v in self.verses).strip()

    def to_doc(self) -> dict[str, Any]:
        return {"verses": [v.to_doc() for v in self.verses]}

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Paragraph:
        p = cls()
        p.verses = [Verse.from_doc(v) for v in doc.get("verses", [])]
        return p

    def __repr__(self) -> str:
        return f"Paragraph(verses={len(self.verses)})"


@dataclass
class Section:
    """One heading + its paragraphs."""
    heading: str | None
    paragraphs: list[Paragraph] = field(default_factory=list)

    def to_doc(self) -> dict[str, Any]:
        return {
            "heading":    self.heading,
            "paragraphs": [p.to_doc() for p in self.paragraphs],
        }

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> Section:
        s = cls(heading=doc.get("heading"))
        s.paragraphs = [Paragraph.from_doc(p) for p in doc.get("paragraphs", [])]
        return s

    def __repr__(self) -> str:
        return f"Section(heading={self.heading!r}, paragraphs={len(self.paragraphs)})"


@dataclass
class ChapterPage:
    """Root object for one scraped Bible chapter page."""
    book:       str
    chapter:    int
    version:    str
    title:      str
    source_url: str
    scraped_at: datetime
    sections:   list[Section] = field(default_factory=list)

    @property
    def all_paragraphs(self) -> list[Paragraph]:
        return [p for s in self.sections for p in s.paragraphs]

    @property
    def all_verses(self) -> list[Verse]:
        return [v for p in self.all_paragraphs for v in p.verses]

    @property
    def all_footnotes(self) -> list[Footnote]:
        return [fn for v in self.all_verses for fn in v.all_footnotes]

    def footnotes_by_type(self, ftype: FootnoteType) -> list[Footnote]:
        return [fn for fn in self.all_footnotes if fn.type == ftype]

    @property
    def mongo_id(self) -> str:
        return f"{self.book}_{self.chapter}_{self.version}"

    def to_doc(self) -> dict[str, Any]:
        return {
            "_id":        self.mongo_id,
            "book":       self.book,
            "chapter":    self.chapter,
            "version":    self.version,
            "title":      self.title,
            "source_url": self.source_url,
            "scraped_at": self.scraped_at,
            "sections":   [s.to_doc() for s in self.sections],
        }

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> ChapterPage:
        scraped_at = doc.get("scraped_at", datetime.now(timezone.utc))
        if isinstance(scraped_at, str):
            scraped_at = datetime.fromisoformat(scraped_at)
        cp = cls(
            book=doc["book"], chapter=doc["chapter"], version=doc["version"],
            title=doc["title"], source_url=doc["source_url"], scraped_at=scraped_at,
        )
        cp.sections = [Section.from_doc(s) for s in doc.get("sections", [])]
        return cp

    def __repr__(self) -> str:
        return (
            f"ChapterPage(_id={self.mongo_id!r}, "
            f"sections={len(self.sections)}, "
            f"verses={len(self.all_verses)}, "
            f"footnotes={len(self.all_footnotes)} "
            f"[tn={len(self.footnotes_by_type('tn'))} "
            f"sn={len(self.footnotes_by_type('sn'))} "
            f"tc={len(self.footnotes_by_type('tc'))}])"
        )


# ── Note and paragraph parsers ───────────────────────────────────────────────

def _parse_ft_span(ft_tag: Tag) -> list[Footnote]:
    """
    Parse one class="ft" span into one or more Footnote objects.

    A single span may contain multiple concatenated notes, e.g.:
      "tn Note body.sn Another note."   (glued after punctuation)
      "tn Note body. sn Another note."  (space-separated)

    A new note starts at: start-of-string OR after punctuation [.!?")]
    followed by a known 2-char prefix (tn / sn / tc) + space.
    """
    raw = re.sub(r"\s+", " ", ft_tag.get_text(" ", strip=True)).strip()
    positions = [(m.start(), m.group(1)) for m in _NOTE_BOUNDARY.finditer(raw)]

    if not positions:
        return [Footnote(type="unknown", text=raw)] if raw else []

    footnotes: list[Footnote] = []
    for idx, (pos, prefix) in enumerate(positions):
        body_start = pos + len(prefix) + 1
        body_end   = positions[idx + 1][0] if idx + 1 < len(positions) else len(raw)
        footnotes.append(Footnote(type=prefix, text=raw[body_start:body_end].strip()))  # type: ignore[arg-type]
    return footnotes


def _parse_paragraph(p_tag: Tag) -> Paragraph:
    """
    Build a Paragraph by walking the DOM children of a __p div in order.

    Children alternate between NavigableString (bible text) and
    class="ft" spans (footnotes). Walking them directly gives us the
    exact text↔footnote interleaving without any heuristic splitting:

        NavigableString  "Then the man...moving about"  → accumulate as bible text
        ft span          "tn Hitpael participle..."     → flush text as Chunk + footnotes
        NavigableString  "in the orchard at the breezy" → accumulate next bible text
        ft span          "tn The expression..."         → flush as next Chunk + footnotes
        ...

    Verse numbers embedded in bible text fragments (e.g. "...orchard. 9 But...")
    are detected and used to split into separate Verse objects.
    """
    paragraph    = Paragraph()
    current_verse: Verse | None = None
    pending_text = ""

    def new_verse(number: int) -> None:
        nonlocal current_verse
        if current_verse is not None and current_verse.chunks:
            paragraph.verses.append(current_verse)
        current_verse = Verse(number=number)

    def emit_chunk(text: str, footnotes: list[Footnote]) -> None:
        """Attach a Chunk to the current verse, creating it if needed."""
        nonlocal current_verse
        if current_verse is None:
            current_verse = Verse(number=None)
        if text or footnotes:
            current_verse.chunks.append(Chunk(text=text, footnotes=footnotes))

    def flush(footnotes: list[Footnote]) -> None:
        """
        Flush pending_text (with footnotes) into Chunk(s).
        A single pending_text fragment may span multiple verse numbers,
        e.g. "...orchard. 9 But the Lord God called to" — we split on
        embedded verse numbers so each verse gets its own Verse object.
        """
        nonlocal pending_text
        text = re.sub(r"\s+", " ", pending_text).strip()
        pending_text = ""

        # Split on embedded verse-number transitions: digits preceded by
        # whitespace and followed by a space (to avoid splitting "v.1" refs)
        # Pattern: space + digits + space, where digits stand alone
        segments = re.split(r"(?:^|(?<=\s))(\d+)(?=\s)", text)
        # segments = [pre, num, post, num, post, ...]

        if len(segments) == 1:
            # No embedded verse number
            emit_chunk(text, footnotes)
            return

        i = 0
        while i < len(segments):
            seg = segments[i].strip()
            if i + 1 < len(segments) and re.fullmatch(r"\d+", segments[i + 1]):
                # seg = text before the verse number
                if seg:
                    emit_chunk(seg, [])      # no footnotes on pre-verse text
                new_verse(int(segments[i + 1]))
                i += 2
            else:
                # Last segment: attach footnotes here
                if seg or footnotes:
                    emit_chunk(seg, footnotes)
                i += 1

    # ── Walk children ─────────────────────────────────────────────────────────
    for child in p_tag.children:
        if isinstance(child, Tag):
            if CLS_FT in child.get("class", []):
                # Footnote span: flush accumulated text + attach these footnotes
                flush(_parse_ft_span(child))
            else:
                # Verse number span or other inline tag
                inner = child.get_text(" ", strip=False)
                raw_inner = re.sub(r"\s+", " ", inner).strip()
                # If it is a bare verse number, start a new verse immediately
                if re.fullmatch(r"\d+", raw_inner):
                    flush([])
                    new_verse(int(raw_inner))
                else:
                    pending_text += inner
        elif isinstance(child, NavigableString):
            pending_text += str(child)

    # Flush any trailing text after the last footnote span
    if pending_text.strip():
        flush([])

    # Append final verse
    if current_verse is not None and current_verse.chunks:
        paragraph.verses.append(current_verse)

    return paragraph


# ── Public scrape function ────────────────────────────────────────────────────

def scrape(url: str) -> ChapterPage:
    """Fetch a bible.com chapter URL and return a ChapterPage."""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    m = re.search(r"/([A-Z0-9]+)\.(\d+)\.([A-Z0-9]+)$", url)
    book    = m.group(1) if m else "UNK"
    chapter = int(m.group(2)) if m else 0
    version = m.group(3) if m else "UNK"

    h1_tag = soup.find("h1")
    title  = h1_tag.get_text(strip=True) if h1_tag else f"{book} {chapter}"

    cp = ChapterPage(
        book=book, chapter=chapter, version=version,
        title=title, source_url=url,
        scraped_at=datetime.now(timezone.utc),
    )

    content_tags = soup.find_all(
        class_=lambda c: c and (CLS_HEADING in c or CLS_P in c)
    )
    current_section: Section | None = None

    for tag in content_tags:
        tag_classes = tag.get("class", [])
        if CLS_HEADING in tag_classes:
            current_section = Section(heading=tag.get_text(strip=True))
            cp.sections.append(current_section)
        elif CLS_P in tag_classes:
            if current_section is None:
                current_section = Section(heading=None)
                cp.sections.append(current_section)
            para = _parse_paragraph(tag)
            if para.verses:
                current_section.paragraphs.append(para)

    return cp


# ── Pretty printer ────────────────────────────────────────────────────────────

def print_structure(cp: ChapterPage, show_footnotes: bool = True) -> None:
    fn = cp.all_footnotes
    print("=" * 70)
    print(f"_id         : {cp.mongo_id}")
    print(f"title       : {cp.title}")
    print(f"book/ch/ver : {cp.book} / {cp.chapter} / {cp.version}")
    print(f"scraped_at  : {cp.scraped_at.isoformat()}")
    print(f"sections    : {len(cp.sections)}")
    print(f"verses      : {len(cp.all_verses)}")
    print(f"footnotes   : {len(fn)}  "
          f"(tn={len(cp.footnotes_by_type('tn'))}, "
          f"sn={len(cp.footnotes_by_type('sn'))}, "
          f"tc={len(cp.footnotes_by_type('tc'))})")
    print("=" * 70)
    for s_i, section in enumerate(cp.sections, 1):
        print(f"\n-- Section {s_i}: {section.heading or '(no heading)'}")
        for p_i, para in enumerate(section.paragraphs, 1):
            print(f"   Paragraph {p_i}:")
            for verse in para.verses:
                label = f"v{verse.number}" if verse.number is not None else "(line)"
                print(f"     [{label}] {verse.plain_text[:80]}"
                      f"{'...' if len(verse.plain_text) > 80 else ''}")
                if show_footnotes:
                    for fn in verse.all_footnotes:
                        print(f"             [{fn.type.upper()}] "
                              f"{fn.text[:85]}{'...' if len(fn.text) > 85 else ''}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    URL = "https://www.bible.com/bible/107/GEN.3.NET"
    print(f"Scraping {URL} ...\n")
    chapter = scrape(URL)
    print_structure(chapter, show_footnotes=True)

    doc = chapter.to_doc()
    print("\n\n-- MONGODB DOCUMENT PREVIEW (first verse only) --")
    preview = {
        "_id":        doc["_id"],
        "book":       doc["book"],
        "chapter":    doc["chapter"],
        "version":    doc["version"],
        "title":      doc["title"],
        "source_url": doc["source_url"],
        "scraped_at": doc["scraped_at"].isoformat(),
        "sections": [{
            "heading": doc["sections"][0]["heading"],
            "paragraphs": [{
                "verses": [doc["sections"][0]["paragraphs"][0]["verses"][0]]
            }]
        }]
    }
    print(json.dumps(preview, indent=2, ensure_ascii=False))

    print("\n-- ROUND-TRIP TEST (to_doc -> from_doc) --")
    restored = ChapterPage.from_doc(doc)
    v1_orig     = chapter.all_verses[0]
    v1_restored = restored.all_verses[0]
    assert v1_orig.plain_text == v1_restored.plain_text
    assert v1_orig.all_footnotes[0].type == v1_restored.all_footnotes[0].type
    assert v1_orig.all_footnotes[0].text == v1_restored.all_footnotes[0].text
    print("OK  round-trip passed")