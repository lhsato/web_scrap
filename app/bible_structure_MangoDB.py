# """
# bible_structure.py
# ──────────────────
# Hierarchical data structure for bible.com NET Bible chapters,
# with full MongoDB document compatibility.

# PYTHON OBJECT HIERARCHY
# ═══════════════════════
# ChapterPage
#  ├── metadata             (book, chapter, version, url, scraped_at)
#  └── sections[]
#       ├── heading         (str | None)
#       └── paragraphs[]
#            └── verses[]
#                 ├── number     (int | None)
#                 └── chunks[]
#                      ├── text          (str — Bible text fragment)
#                      └── footnotes[]
#                           ├── type    ("tn" | "sn" | "tc" | "unknown")
#                           └── text    (str — full note body)

# MONGODB DOCUMENT SHAPE  (collection: "chapters")
# ════════════════════════════════════════════════
# {
#   "_id":        "GEN_1_NET",          <- book_chapter_version  (unique)
#   "book":       "GEN",                <- USFM book code
#   "chapter":    1,                    <- int
#   "version":    "NET",                <- Bible version code
#   "title":      "Genesis 1",          <- <h1>
#   "source_url": "https://...",
#   "scraped_at": "2026-01-01T00:00:00Z",
#   "sections": [
#     {
#       "heading": "The Creation of the World",   <- null if absent
#       "paragraphs": [
#         {
#           "verses": [
#             {
#               "number": 1,                       <- null for unnumbered lines
#               "plain_text": "In the beginning",  <- denormalised for full-text search
#               "chunks": [
#                 {
#                   "text": "In the beginning",
#                   "footnotes": [
#                     { "type": "tn", "text": "The translation assumes..." },
#                     { "type": "sn", "text": "In the beginning..."       }
#                   ]
#                 },
#                 ...
#               ]
#             }
#           ]
#         }
#       ]
#     }
#   ]
# }

# FOOTNOTE TYPES  (all scraped from class="ft" spans)
# ===================================================
#   tn  Translator's Note   -- translation choices, Hebrew/Greek word meanings
#   sn  Study Note          -- biblical, historical, theological context
#   tc  Textual Criticism   -- manuscript variants and textual traditions

# RECOMMENDED MONGODB INDEXES
# ============================
#   db.chapters.create_index([("book",1),("chapter",1),("version",1)], unique=True)
#   db.chapters.create_index("version")
#   db.chapters.create_index([("sections.paragraphs.verses.plain_text", "text")])
# """

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

# CSS class names (hashed identifiers used by bible.com)
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


# ── Data classes -- bottom-up ─────────────────────────────────────────────────

@dataclass
class Footnote:
    # """
    # A single annotation attached to a text chunk.
    # type: "tn" (Translator) | "sn" (Study) | "tc" (Textual Criticism) | "unknown"
    # """
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
    # """
    # An atomic piece of Bible text paired with its immediately following footnotes.
    # Preserves inline order: text -> [fn, fn, ...] -> next text -> [fn] -> ...
    # """
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
    # """
    # One verse (or unnumbered poetic line) composed of ordered Chunks.
    # number=None means the line has no verse number (continuation / poetry).
    # """
    number: int | None
    chunks: list[Chunk] = field(default_factory=list)

    @property
    def plain_text(self) -> str:
        # """Full Bible text of the verse with no footnote content."""
        return " ".join(c.text for c in self.chunks if c.text).strip()

    @property
    def all_footnotes(self) -> list[Footnote]:
        # """All footnotes across all chunks, in document order."""
        return [fn for chunk in self.chunks for fn in chunk.footnotes]

    def footnotes_by_type(self, ftype: FootnoteType) -> list[Footnote]:
        return [fn for fn in self.all_footnotes if fn.type == ftype]

    def to_doc(self) -> dict[str, Any]:
        return {
            "number":     self.number,
            "plain_text": self.plain_text,   # denormalised -- useful for $text search
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
    # """One <div class='__p'> block -- a group of consecutive verses."""
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
    # """
    # A titled section: one optional heading followed by one or more paragraphs.
    # Sections are delimited by <div class='__heading'> tags in the source HTML.
    # """
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
    # """
    # Root object representing one scraped Bible chapter page.
    # Call .to_doc() to get a MongoDB-ready dict.
    # Call ChapterPage.from_doc(doc) to reconstruct from MongoDB.
    # """
    book:       str       # USFM book code e.g. "GEN"
    chapter:    int       # chapter number  e.g. 1
    version:    str       # Bible version   e.g. "NET"
    title:      str       # <h1> text       e.g. "Genesis 1"
    source_url: str       # original URL scraped
    scraped_at: datetime  # UTC timestamp

    sections: list[Section] = field(default_factory=list)

    # ── Convenience accessors ─────────────────────────────────────────────────

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

    # ── MongoDB ───────────────────────────────────────────────────────────────

    @property
    def mongo_id(self) -> str:
        # """
        # Human-readable unique _id: "GEN_1_NET".
        # Makes upserts and direct lookups trivial without ObjectId.
        # """
        return f"{self.book}_{self.chapter}_{self.version}"

    def to_doc(self) -> dict[str, Any]:
        # """
        # Return a MongoDB-ready document dict.

        # Usage:
        #     doc = chapter.to_doc()
        #     collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        # """
        return {
            "_id":        self.mongo_id,
            "book":       self.book,
            "chapter":    self.chapter,
            "version":    self.version,
            "title":      self.title,
            "source_url": self.source_url,
            "scraped_at": self.scraped_at,      # pymongo serialises datetime -> BSON Date
            "sections":   [s.to_doc() for s in self.sections],
        }

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> ChapterPage:
        """Reconstruct a ChapterPage from a raw MongoDB document dict."""
        scraped_at = doc.get("scraped_at", datetime.now(timezone.utc))
        if isinstance(scraped_at, str):             # came from JSON, not pymongo
            scraped_at = datetime.fromisoformat(scraped_at)

        cp = cls(
            book=doc["book"],
            chapter=doc["chapter"],
            version=doc["version"],
            title=doc["title"],
            source_url=doc["source_url"],
            scraped_at=scraped_at,
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


# ── Internal parser helpers ───────────────────────────────────────────────────

def _parse_footnote_span(ft_tag: Tag) -> list[Footnote]:
    # """
    # Split one class="ft" span into one or more Footnote objects.
    # A single span may contain multiple concatenated notes, e.g.:
    #   "tn Some translation note. sn Some study note."
    # """
    raw = re.sub(r"\s+", " ", ft_tag.get_text(" ", strip=True)).strip()
    parts = re.split(r"(?<!\w)(tn|sn|tc)\s", raw)

    footnotes: list[Footnote] = []
    i = 0
    while i < len(parts):
        part = parts[i].strip()
        if part in KNOWN_PREFIXES:
            body = parts[i + 1].strip() if i + 1 < len(parts) else ""
            if body:
                footnotes.append(Footnote(type=part, text=body))  # type: ignore[arg-type]
            i += 2
        elif part:
            m = re.match(r"^(tn|sn|tc)\s+(.*)", part, re.DOTALL)
            if m:
                footnotes.append(Footnote(type=m.group(1), text=m.group(2).strip()))  # type: ignore[arg-type]
            else:
                footnotes.append(Footnote(type="unknown", text=part))
            i += 1
        else:
            i += 1
    return footnotes


def _parse_paragraph(p_tag: Tag) -> Paragraph:
    # """
    # Walk the children of a __p div and build a Paragraph.
    # Verse number spans start a new Verse; .ft spans close the current text
    # accumulator and attach footnotes to that Chunk.
    # """
    paragraph = Paragraph()
    current_verse: Verse | None = None
    current_text: str = ""

    def flush_chunk(footnotes: list[Footnote] | None = None) -> None:
        nonlocal current_text
        text = re.sub(r"\s+", " ", current_text).strip()
        if text or footnotes:
            if current_verse is not None:
                current_verse.chunks.append(Chunk(text=text, footnotes=footnotes or []))
        current_text = ""

    def flush_verse() -> None:
        nonlocal current_verse
        if current_verse is not None:
            flush_chunk()
            if current_verse.chunks:
                paragraph.verses.append(current_verse)
        current_verse = None

    for child in p_tag.children:

        if isinstance(child, Tag):
            classes = child.get("class", [])
            raw = child.get_text(strip=True)

            # Verse number: pure digit, not a footnote span
            if re.fullmatch(r"\d+", raw) and CLS_FT not in classes:
                flush_verse()
                current_verse = Verse(number=int(raw))
                continue

            # Footnote: close current text chunk and attach notes to it
            if CLS_FT in classes:
                fns = _parse_footnote_span(child)
                if fns:
                    flush_chunk(footnotes=fns)
                continue

            # Any other inline tag
            inner = child.get_text(" ", strip=True)
            if inner:
                current_text += " " + inner

        elif isinstance(child, NavigableString):
            t = str(child)
            if t.strip():
                current_text += " " + t

    # Flush trailing content
    if current_verse is None and current_text.strip():
        current_verse = Verse(number=None)
    flush_verse()

    return paragraph


# ── Public scrape function ────────────────────────────────────────────────────

def scrape(url: str) -> ChapterPage:
    # """
    # Fetch a bible.com chapter URL and return a ChapterPage.

    # URL format:  https://www.bible.com/bible/107/GEN.1.NET
    #                                               ^^^ ^ ^^^
    #                                              book | version
    #                                                   chapter
    # """
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    # Parse metadata from URL
    m = re.search(r"/([A-Z0-9]+)\.(\d+)\.([A-Z0-9]+)$", url)
    book    = m.group(1) if m else "UNK"
    chapter = int(m.group(2)) if m else 0
    version = m.group(3) if m else "UNK"

    h1_tag = soup.find("h1")
    title  = h1_tag.get_text(strip=True) if h1_tag else f"{book} {chapter}"

    cp = ChapterPage(
        book=book,
        chapter=chapter,
        version=version,
        title=title,
        source_url=url,
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
    print("=" * 70)
    print(f"_id         : {cp.mongo_id}")
    print(f"title       : {cp.title}")
    print(f"book/ch/ver : {cp.book} / {cp.chapter} / {cp.version}")
    print(f"scraped_at  : {cp.scraped_at.isoformat()}")
    print(f"sections    : {len(cp.sections)}")
    print(f"verses      : {len(cp.all_verses)}")
    fn = cp.all_footnotes
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

    URL = "https://www.bible.com/bible/107/GEN.1.NET"
    print(f"Scraping {URL} ...\n")
    chapter = scrape(URL)
    print_structure(chapter, show_footnotes=True)

    # MongoDB document preview
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

    # Round-trip test
    print("\n-- ROUND-TRIP TEST (to_doc -> from_doc) --")
    restored = ChapterPage.from_doc(doc)
    v1_orig     = chapter.all_verses[0]
    v1_restored = restored.all_verses[0]
    assert v1_orig.plain_text == v1_restored.plain_text
    assert v1_orig.all_footnotes[0].type == v1_restored.all_footnotes[0].type
    assert v1_orig.all_footnotes[0].text == v1_restored.all_footnotes[0].text
    print("OK  to_doc() -> from_doc() round-trip passed")

    # Usage reminder
    print("""
-- HOW TO INSERT INTO MONGODB --
from pymongo import MongoClient
from bible_structure import scrape, ChapterPage

client     = MongoClient("mongodb://localhost:27017")
collection = client["bible"]["chapters"]

# Create indexes once
collection.create_index([("book",1),("chapter",1),("version",1)], unique=True)
collection.create_index("version")
collection.create_index([("sections.paragraphs.verses.plain_text","text")])

# Scrape and upsert (safe to re-run)
chapter = scrape("https://www.bible.com/bible/107/GEN.1.NET")
doc     = chapter.to_doc()
collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)

# Restore from MongoDB
doc     = collection.find_one({"_id": "GEN_1_NET"})
chapter = ChapterPage.from_doc(doc)

# Full-text search across all verse text
results = collection.find({"$text": {"$search": "created heavens"}})
""")