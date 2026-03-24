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

# Sentence-ending punctuation used to find where a note body ends
_PUNCT = re.compile(r'[.!?"\u201c\u201d\u2018\u2019\])]')
# Sentence-ending punctuation for trailing text search (no quotes)
_SENT_END = re.compile(r'[.!?]')



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


# ── Note block parser ─────────────────────────────────────────────────────────

def _split_note_block(block: str, is_last: bool) -> tuple[list[Footnote], str]:
    """
    Parse one '#'-delimited note block into (footnotes, trailing_bible_text).

    A block looks like:
        "tn Note body.sn Another note body. trailing bible text"

    Rules:
      - A new note starts at start-of-block OR after punctuation + known prefix.
      - The note type is the first 2 characters (tn / sn / tc).
      - For non-last blocks: trailing bible text after the final note's closing
        punctuation is stripped and returned separately.
      - Last block: no trailing bible text (everything is note body).

    Bug fix: after isolating the trailing text, strip any leading punctuation
    characters (e.g. the closing '"' from '"God of gods." created' becomes
    'created' not '" created').
    """
    block = block.strip()
    positions = [(m.start(), m.group(1)) for m in _NOTE_BOUNDARY.finditer(block)]

    if not positions:
        # No known prefix — entire block is trailing bible text
        return [], block

    footnotes: list[Footnote] = []
    for idx, (pos, prefix) in enumerate(positions):
        body_start = pos + len(prefix) + 1
        body_end   = positions[idx + 1][0] if idx + 1 < len(positions) else len(block)
        body       = block[body_start:body_end].strip()
        footnotes.append(Footnote(type=prefix, text=body))  # type: ignore[arg-type]

    # Strip trailing bible text from the last footnote body.
    # Always extract if the trailing text starts with a verse number —
    # a new verse can follow even the very last note block.
    # For non-last blocks, also extract any other trailing bible text.
    # We clean leading punctuation from 'after' before checking,
    # so a closing quote like '"day"' is not mistaken for real trailing text.
    trailing = ""
    if footnotes:
        last_fn = footnotes[-1]
        for m in reversed(list(_SENT_END.finditer(last_fn.text))):
            after = last_fn.text[m.end():].strip()
            if not after:
                continue
            if re.match(r'^(tn|sn|tc) ', after):
                continue   # next note prefix — not trailing text
            # Clean leading punctuation before deciding if this is real trailing text
            after_clean = re.sub(r'^[.!?"\u201c\u201d\u2018\u2019\])\s]+', '', after).strip()
            if not after_clean:
                continue   # only punctuation after this point — keep scanning
            is_verse_start = bool(re.match(r'\d+\s', after_clean))
            if is_verse_start or not is_last:
                trailing = after_clean
                last_fn.text = last_fn.text[:m.end()].strip()
                break

    return footnotes, trailing


# ── Paragraph parser ──────────────────────────────────────────────────────────

def _parse_paragraph(p_tag: Tag) -> Paragraph:
    """
    Build a Paragraph from a __p div.

    Strategy:
      1. Collect raw text preserving '#' markers from ft spans.
      2. Split on '#' to get [bible_text_0, note_block_1, note_block_2, ...].
      3. Each note block belongs to the preceding bible text fragment.
      4. Trailing bible text inside a non-last block carries forward to the
         next chunk.
      5. Verse numbers (digits) at the start of bible text are detected and
         used to split into separate Verse objects.
    """
    # Collect raw text, marking ft spans with '#'
    raw_parts: list[str] = []
    for child in p_tag.children:
        if isinstance(child, NavigableString):
            raw_parts.append(str(child))
        elif isinstance(child, Tag):
            if CLS_FT in child.get("class", []):
                raw_parts.append("#" + child.get_text(" ", strip=False))
            else:
                raw_parts.append(child.get_text(" ", strip=False))

    raw = re.sub(r"\s+", " ", "".join(raw_parts)).strip()

    # Split on '#'
    parts      = raw.split("#")
    note_parts = parts[1:]
    chunks:    list[Chunk] = []
    pending_text = parts[0].strip()

    for i, part in enumerate(note_parts):
        is_last  = (i == len(note_parts) - 1)
        footnotes, trailing = _split_note_block(part.strip(), is_last)
        chunks.append(Chunk(text=pending_text, footnotes=footnotes))
        pending_text = trailing

    if pending_text:
        chunks.append(Chunk(text=pending_text, footnotes=[]))

    # Group chunks into Verses by detecting verse numbers.
    # A verse number can appear at the START of a chunk text or EMBEDDED
    # mid-text (e.g. "...end of v6. 7 Then the eyes...").
    # We use re.split to find ALL verse transitions within each chunk text.
    paragraph = Paragraph()
    current_verse: Verse | None = None

    def emit_chunk(text: str, footnotes: list) -> None:
        """Attach a Chunk to the current verse, creating one if needed."""
        nonlocal current_verse
        if current_verse is None:
            current_verse = Verse(number=None)
        if text or footnotes:
            current_verse.chunks.append(Chunk(text=text, footnotes=footnotes))

    def new_verse(number: int) -> None:
        """Save the current verse and start a new one."""
        nonlocal current_verse
        if current_verse is not None and current_verse.chunks:
            paragraph.verses.append(current_verse)
        current_verse = Verse(number=number)

    # Pattern: standalone digit(s) at start of string or after whitespace,
    # followed by a space — avoids splitting on "v.1", "Gen 1:1", etc.
    _VERSE_NUM = re.compile(r'(?:^|(?<=\s))(\d+)(?=\s)')

    for chunk in chunks:
        segments = _VERSE_NUM.split(chunk.text)
        # re.split with one capturing group gives:
        # [pre_text, digit, post_text, digit, post_text, ...]

        if len(segments) == 1:
            # No verse number in this chunk text
            emit_chunk(chunk.text, chunk.footnotes)
        else:
            i = 0
            while i < len(segments):
                seg = segments[i].strip()
                if i + 1 < len(segments) and re.fullmatch(r'\d+', segments[i + 1]):
                    # seg = text before a verse number
                    if seg:
                        emit_chunk(seg, [])          # no footnotes on pre-number text
                    new_verse(int(segments[i + 1]))
                    i += 2
                else:
                    # Last segment — footnotes attach here
                    emit_chunk(seg, chunk.footnotes)
                    i += 1

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
                      f"{verse.plain_text[:80]}{'...' if len(verse.plain_text) > 80 else ''}"
                    # f"{verse.plain_text}"
                      )
                for chunk in verse.chunks:
                    if chunk.footnotes:
                        print(f"       [chunk] {chunk.text[:60]}{'...' if len(chunk.text) > 60 else ''}")
                        for fn in chunk.footnotes:
                            print(f"                 [{fn.type.upper()}] "
                                    f"{fn.text[:85]}{'...' if len(fn.text) > 85 else ''}")   


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    URL = "https://www.bible.com/bible/107/GEN.3.NET"
    print(f"Scraping {URL} ...\n")
    chapter = scrape(URL)
    print_structure(chapter, show_footnotes=True)