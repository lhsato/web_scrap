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
  - Trailing bible text (e.g. "God", "created") lives at the END of a
    non-last block, after the final note's closing punctuation.

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
    """One heading + its paragraphs.
    heading_footnotes holds any footnotes attached directly to the heading
    (e.g. the psalm-intro note on Psalm 119).
    """
    heading:            str | None
    heading_footnotes:  list[Footnote] = field(default_factory=list)
    paragraphs:         list[Paragraph] = field(default_factory=list)

    def __repr__(self) -> str:
        fn = f", {len(self.heading_footnotes)} fn" if self.heading_footnotes else ""
        return f"Section(heading={self.heading!r}{fn}, paragraphs={len(self.paragraphs)})"


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


# ── Note and paragraph parsers ──────────────────────────────────────────────

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

    Children alternate between NavigableString (bible text) and ft spans
    (footnotes). Walking them directly gives exact text-footnote interleaving
    with no heuristic splitting needed:

        NavigableString  "Then the man...moving about"  -> accumulate bible text
        ft span          "tn Hitpael participle..."     -> flush as Chunk + footnotes
        NavigableString  "in the orchard at the breezy" -> accumulate next bible text
        ft span          "tn The expression..."         -> flush as next Chunk + footnotes
        ...

    Verse numbers embedded in bible text fragments (e.g. "...orchard. 9 But...")
    are detected and used to split into separate Verse objects.

    Both plain class="ft" and hashed variants like
    "ChapterContent-module__cat7xG__ft" are recognised as footnote spans.
    """
    paragraph    = Paragraph()
    current_verse: Verse | None = None
    pending_text = ""

    def _is_ft(tag: Tag) -> bool:
        classes = tag.get("class", [])
        return CLS_FT in classes or any("ft" in c for c in classes)

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

    # Pattern: standalone digit(s) at start of string or after whitespace,
    # followed by a space — avoids splitting on "v.1", "Gen 1:1", etc.
    _VERSE_NUM = re.compile(r'(?:^|(?<=\s))(\d+)(?=\s)')

    def flush(footnotes: list[Footnote]) -> None:
        """
        Flush pending_text (with footnotes) into Chunk(s), splitting on any
        embedded verse numbers so each verse gets its own Verse object.
        """
        nonlocal pending_text
        text = re.sub(r"\s+", " ", pending_text).strip()
        pending_text = ""

        segments = _VERSE_NUM.split(text)

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
                emit_chunk(seg, footnotes)       # last segment — footnotes attach here
                i += 1

    # ── Walk children ────────────────────────────────────────────────────────
    def walk(node: Tag) -> None:
        """
        Recursively walk a tag's children so that ft spans nested inside
        non-ft wrapper spans are still handled correctly.
        Non-ft, non-verse-number tags are descended into rather than
        having their full get_text() dumped into pending_text (which would
        include ft-span text and cause footnote body text to bleed into
        the bible text and be incorrectly split on verse-number digits).
        """
        nonlocal pending_text
        for child in node.children:
            if isinstance(child, Tag):
                if _is_ft(child):
                    flush(_parse_ft_span(child))
                else:
                    inner = child.get_text(" ", strip=False)
                    raw_inner = re.sub(r"\s+", " ", inner).strip()
                    if re.fullmatch(r"\d+", raw_inner):   # bare verse-number span
                        flush([])
                        new_verse(int(raw_inner))
                    elif any(_is_ft(d) for d in child.descendants if isinstance(d, Tag)):
                        # Non-ft tag that CONTAINS ft descendants — recurse
                        walk(child)
                    else:
                        # Plain inline tag with no ft descendants — safe to get_text()
                        pending_text += child.get_text(" ", strip=False)
            elif isinstance(child, NavigableString):
                pending_text += str(child)

    walk(p_tag)

    # Flush any trailing text after the last ft span
    if pending_text.strip():
        flush([])

    # Append the final verse
    if current_verse is not None and current_verse.chunks:
        paragraph.verses.append(current_verse)

    return paragraph


# ── Heading parser ───────────────────────────────────────────────────────────

def _parse_heading(tag: Tag) -> tuple[str, list[Footnote]]:
    """
    Parse a __heading div into (heading_text, footnotes).

    Most headings are plain text, e.g. "The Creation of the World".
    Some headings carry an ft span with a psalm intro note, e.g.:
        "Psalm 119<span class='ft'>sn Psalm 119. The psalmist...</span>"

    The heading content may be wrapped in a non-ft span, so we recurse
    rather than calling get_text() which would include ft descendants.
    """
    text_parts: list[str] = []
    footnotes:  list[Footnote] = []

    def _is_ft(t: Tag) -> bool:
        classes = t.get("class", [])
        return CLS_FT in classes or any("ft" in c for c in classes)

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                text_parts.append(str(child))
            elif isinstance(child, Tag):
                if _is_ft(child):
                    footnotes.extend(_parse_ft_span(child))
                elif any(_is_ft(d) for d in child.descendants if isinstance(d, Tag)):
                    walk(child)   # wrapper containing ft spans — recurse
                else:
                    text_parts.append(child.get_text(" ", strip=False))

    walk(tag)
    heading_text = re.sub(r"\s+", " ", "".join(text_parts)).strip()

    # Defensive: if the ft span was not caught by the walk (e.g. it used an
    # unrecognised class), its text leaks into heading_text as:
    #   "Psalm 119 sn The psalmist..." or "sn The psalmist..."
    # Detect a note prefix (tn/sn/tc + space) anywhere in the text and split there.
    note_start = re.search(r'(?:^|(?<=\s))(tn|sn|tc) ', heading_text)
    if note_start:
        pure_heading = heading_text[:note_start.start()].strip()
        note_block   = heading_text[note_start.start():].strip()
        positions = [(m.start(), m.group(1)) for m in _NOTE_BOUNDARY.finditer(note_block)]
        extra_fns: list[Footnote] = []
        for idx, (pos, prefix) in enumerate(positions):
            body_start = pos + len(prefix) + 1
            body_end   = positions[idx + 1][0] if idx + 1 < len(positions) else len(note_block)
            extra_fns.append(Footnote(type=prefix, text=note_block[body_start:body_end].strip()))  # type: ignore[arg-type]
        footnotes = extra_fns + footnotes
        heading_text = pure_heading

    return heading_text, footnotes


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
            heading_text, heading_fns = _parse_heading(tag)
            current_section = Section(heading=heading_text, heading_footnotes=heading_fns)
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
        heading = section.heading or '(no heading)'
        if section.heading_footnotes:
            print(f"\n-- Section {s_i}: {heading}")
            if show_footnotes:
                for fn in section.heading_footnotes:
                    print(f"   [{fn.type.upper()}] {fn.text}")
        else:
            print(f"\n-- Section {s_i}: {heading}")
        for p_i, para in enumerate(section.paragraphs, 1):
            print(f"   Paragraph {p_i}:")
            # for verse in para.verses:
            #     label = f"v{verse.number}" if verse.number is not None else "(line)"
            #     print(f"     [{label}] {verse.plain_text[:80]}"
            #           f"{'...' if len(verse.plain_text) > 80 else ''}")
            #     if show_footnotes:
            #         for chunk in verse.chunks:
            #             for fn in chunk.footnotes:
            #                 print(f"             [{fn.type.upper()}] "
            #                       f"{fn.text[:85]}{'...' if len(fn.text) > 85 else ''}")
            for verse in para.verses:
                print(f"     [v{verse.number if verse.number is not None else '(line)'}] "
                    #   f"{verse.plain_text[:80]}{'...' if len(verse.plain_text) > 80 else ''}"
                    f"{verse.plain_text}")
                for chunk in verse.chunks:
                    if chunk.footnotes:
                        print(f"       [chunk] {chunk.text[:60]}{'...' if len(chunk.text) > 60 else ''}")
                        for fn in chunk.footnotes:
                            print(f"                 [{fn.type.upper()}] "
                                    # f"{fn.text[:85]}{'...' if len(fn.text) > 85 else ''}")   
                                    f"{fn.text}")   


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    URL = "https://www.bible.com/bible/107/GEN.1.NET"
    # URL = "https://www.bible.com/bible/107/PSA.119.NET"
    with open("output.txt", "w", encoding="utf-8") as _f:
        sys.stdout = _f
        print(f"Scraping {URL} ...\n")
        chapter = scrape(URL)
        print_structure(chapter, show_footnotes=True)
        sys.stdout = sys.__stdout__
    print("Done — output written to output.txt")