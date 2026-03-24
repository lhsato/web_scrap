"""
bible_structure.py
──────────────────
Hierarchical data structure for bible.com NET Bible chapters.

PYTHON OBJECT HIERARCHY
═══════════════════════
ChapterPage
 ├── book, chapter, version, title, source_url
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

FOOTNOTE TYPES
══════════════
  tn  Translator's Note   -- translation choices, Hebrew/Greek word meanings
  sn  Study Note          -- biblical, historical, theological context
  tc  Textual Criticism   -- manuscript variants and textual traditions
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

import requests
from bs4 import BeautifulSoup, NavigableString, Tag


# ── Constants ─────────────────────────────────────────────────────────────────

FootnoteType = Literal["tn", "sn", "tc", "unknown"]

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

    def __repr__(self) -> str:
        return f"Paragraph(verses={len(self.verses)})"


@dataclass
class Section:
    """One heading + its paragraphs."""
    heading: str | None
    paragraphs: list[Paragraph] = field(default_factory=list)

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

    def __repr__(self) -> str:
        return (
            f"ChapterPage(book={self.book!r}, chapter={self.chapter}, "
            f"version={self.version!r}, "
            f"sections={len(self.sections)}, "
            f"verses={len(self.all_verses)}, "
            f"footnotes={len(self.all_footnotes)} "
            f"[tn={len(self.footnotes_by_type('tn'))} "
            f"sn={len(self.footnotes_by_type('sn'))} "
            f"tc={len(self.footnotes_by_type('tc'))}])"
        )


# ── Note and paragraph parsers ────────────────────────────────────────────────

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
    exact text-footnote interleaving without any heuristic splitting:

        NavigableString  "Then the man...moving about"   -> accumulate as bible text
        ft span          "tn Hitpael participle..."      -> flush text as Chunk + footnotes
        NavigableString  "in the orchard at the breezy"  -> accumulate next bible text
        ft span          "tn The expression..."          -> flush as next Chunk + footnotes
        ...

    Verse numbers embedded in bible text fragments (e.g. "...orchard. 9 But...")
    are detected and used to split into separate Verse objects.
    """
    paragraph     = Paragraph()
    current_verse: Verse | None = None
    pending_text  = ""

    def new_verse(number: int) -> None:
        nonlocal current_verse
        if current_verse is not None and current_verse.chunks:
            paragraph.verses.append(current_verse)
        current_verse = Verse(number=number)

    def emit_chunk(text: str, footnotes: list[Footnote]) -> None:
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

        # Split on verse-number transitions: digits at start or after whitespace,
        # followed by a space (avoids splitting on "v.1" or "(Gen 1:1)" refs)
        segments = re.split(r"(?:^|(?<=\s))(\d+)(?=\s)", text)

        if len(segments) == 1:
            emit_chunk(text, footnotes)
            return

        i = 0
        while i < len(segments):
            seg = segments[i].strip()
            if i + 1 < len(segments) and re.fullmatch(r"\d+", segments[i + 1]):
                if seg:
                    emit_chunk(seg, [])          # text before a verse number — no footnotes
                new_verse(int(segments[i + 1]))
                i += 2
            else:
                if seg or footnotes:
                    emit_chunk(seg, footnotes)   # last segment — footnotes attach here
                i += 1

    # ── Walk children ─────────────────────────────────────────────────────────
    for child in p_tag.children:
        if isinstance(child, Tag):
            if CLS_FT in child.get("class", []):
                flush(_parse_ft_span(child))
            else:
                inner = child.get_text(" ", strip=False)
                raw_inner = re.sub(r"\s+", " ", inner).strip()
                if re.fullmatch(r"\d+", raw_inner):   # bare verse-number span
                    flush([])
                    new_verse(int(raw_inner))
                else:
                    pending_text += inner
        elif isinstance(child, NavigableString):
            pending_text += str(child)

    if pending_text.strip():
        flush([])

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
    print(f"title       : {cp.title}")
    print(f"book/ch/ver : {cp.book} / {cp.chapter} / {cp.version}")
    print(f"url         : {cp.source_url}")
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
                    #   f"{'...' if len(verse.plain_text) > 80 else ''}")
                    f"{verse.plain_text}")
                if show_footnotes:
                    for fn in verse.all_footnotes:
                        print(f"             [{fn.type.upper()}] "
                              f"{fn.text[:85]}{'...' if len(fn.text) > 85 else ''}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    URL = "https://www.bible.com/bible/107/GEN.1.NET"
    print(f"Scraping {URL} ...\n")
    chapter = scrape(URL)
    print_structure(chapter, show_footnotes=True)