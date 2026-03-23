"""
bible_structure.py
──────────────────
Hierarchical data structure for bible.com NET Bible chapters.

PAGE HIERARCHY
==============
ChapterPage
 └── title                  (h1)
 └── chapter_number         (class __chapter)
 └── sections[]             (grouped by heading)
      └── heading           (class __heading)  ← may be None
      └── paragraphs[]      (class __p)
           └── verses[]
                └── verse_number   (int | None for un-numbered lines)
                └── chunks[]
                     └── text          (str — the actual Bible text)
                     └── footnotes[]
                          └── type    ("tn" | "sn" | "tc" | "unknown")
                          └── text    (str — full footnote body)

FOOTNOTE TYPES (all live inside class="ft" spans)
══════════════════════════════════════════════════
  tn  Translator's Note   — translation choices, Hebrew/Greek word meanings
  sn  Study Note          — biblical, historical, theological context
  tc  Textual Criticism   — manuscript variants and textual traditions
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

import re
import requests
from bs4 import BeautifulSoup, Tag, NavigableString


# ── Types ─────────────────────────────────────────────────────────────────────

FootnoteType = Literal["tn", "sn", "tc", "unknown"]

KNOWN_PREFIXES = {"tn", "sn", "tc"}

# CSS class shortcuts (hashed class names from the site)
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


# ── Data classes (bottom-up) ──────────────────────────────────────────────────

@dataclass
class Footnote:
    """A single tn / sn / tc note attached to a text chunk."""
    type: FootnoteType   # "tn" | "sn" | "tc" | "unknown"
    text: str            # full body of the note

    def __repr__(self):
        return f"Footnote(type={self.type!r}, text={self.text[:60]!r}...)"


@dataclass
class Chunk:
    """
    A piece of verse text followed by zero or more footnotes.

    Example — verse 1:
      "In the beginning"  → footnotes: [tn(...), sn(...)]
      "God"               → footnotes: [sn(...)]
      "created"           → footnotes: [tn(...)]
      "the heavens and the earth." → footnotes: [tn(...)]
    """
    text: str                          # Bible text fragment
    footnotes: list[Footnote] = field(default_factory=list)

    def __repr__(self):
        fn = f", {len(self.footnotes)} fn" if self.footnotes else ""
        return f"Chunk({self.text[:50]!r}{fn})"


@dataclass
class Verse:
    """
    One verse (or un-numbered poetic line) inside a paragraph.
    Contains one or more Chunks preserving original inline order.
    """
    number: int | None          # verse number; None for continuation lines
    chunks: list[Chunk] = field(default_factory=list)

    @property
    def plain_text(self) -> str:
        """Bible text only, no footnotes."""
        return " ".join(c.text for c in self.chunks).strip()

    @property
    def all_footnotes(self) -> list[Footnote]:
        """All footnotes across all chunks, in order of appearance."""
        return [fn for chunk in self.chunks for fn in chunk.footnotes]

    def __repr__(self):
        return f"Verse(v={self.number}, chunks={len(self.chunks)}, fns={len(self.all_footnotes)})"


@dataclass
class Paragraph:
    """
    One <div class='__p'> block — a group of verses forming a paragraph.
    """
    verses: list[Verse] = field(default_factory=list)

    @property
    def plain_text(self) -> str:
        return " ".join(v.plain_text for v in self.verses).strip()

    def __repr__(self):
        return f"Paragraph(verses={len(self.verses)})"


@dataclass
class Section:
    """
    A titled section — one __heading followed by one or more paragraphs.
    The first section may have no heading (e.g. chapter number block).
    """
    heading: str | None             # e.g. "The Creation of the World"
    paragraphs: list[Paragraph] = field(default_factory=list)

    def __repr__(self):
        return f"Section(heading={self.heading!r}, paragraphs={len(self.paragraphs)})"


@dataclass
class ChapterPage:
    """
    Root object — the full scraped chapter page.
    """
    title: str                      # <h1>  e.g. "Genesis 1"
    chapter_number: str | None      # class __chapter  e.g. "1"
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

    def __repr__(self):
        return (
            f"ChapterPage(title={self.title!r}, "
            f"sections={len(self.sections)}, "
            f"verses={len(self.all_verses)}, "
            f"footnotes={len(self.all_footnotes)})"
        )


# ── Parser ────────────────────────────────────────────────────────────────────

def _parse_footnote_span(ft_tag: Tag) -> list[Footnote]:
    """
    Parse one class="ft" span into one or more Footnote objects.

    A single span can contain multiple notes concatenated, e.g.:
      "tn Some translation note. sn Some study note."
    We split on the known prefixes to separate them.
    """
    raw = ft_tag.get_text(" ", strip=True)
    raw = re.sub(r"\s+", " ", raw).strip()

    # Split on boundaries like " tn ", " sn ", " tc " that appear mid-string
    # Also handle if it starts directly with a prefix
    pattern = r"(?<!\w)(tn|sn|tc)\s"
    parts = re.split(pattern, raw)

    footnotes: list[Footnote] = []
    i = 0
    # parts alternates: [possible_pre_text, prefix, text, prefix, text, ...]
    while i < len(parts):
        part = parts[i].strip()
        if part in KNOWN_PREFIXES:
            ftype: FootnoteType = part  # type: ignore
            body = parts[i + 1].strip() if i + 1 < len(parts) else ""
            if body:
                footnotes.append(Footnote(type=ftype, text=body))
            i += 2
        elif part:
            # text before first prefix — try to detect prefix at its start
            m = re.match(r"^(tn|sn|tc)\s+(.*)", part, re.DOTALL)
            if m:
                footnotes.append(Footnote(type=m.group(1), text=m.group(2).strip()))  # type: ignore
            else:
                footnotes.append(Footnote(type="unknown", text=part))
            i += 1
        else:
            i += 1

    return footnotes


def _parse_paragraph(p_tag: Tag) -> Paragraph:
    """
    Walk the children of a __p div and build a Paragraph with Verses and Chunks.

    Structure in the DOM (simplified):
      <div class="__p">
        <span class="verse-num">1</span>
        text node "In the beginning"
        <span class="ft">tn ...sn ...</span>
        text node "God"
        <span class="ft">sn ...</span>
        ...
        <span class="verse-num">2</span>
        ...
      </div>
    """
    paragraph = Paragraph()
    current_verse: Verse | None = None
    current_chunk_text: str = ""
    current_footnotes: list[Footnote] = []

    def flush_chunk():
        """Save accumulated text+footnotes as a Chunk onto current_verse."""
        nonlocal current_chunk_text, current_footnotes
        text = re.sub(r"\s+", " ", current_chunk_text).strip()
        if text or current_footnotes:
            if current_verse is not None:
                current_verse.chunks.append(Chunk(text=text, footnotes=current_footnotes))
        current_chunk_text = ""
        current_footnotes = []

    def flush_verse():
        """Save current_verse onto paragraph."""
        nonlocal current_verse
        if current_verse is not None:
            flush_chunk()
            if current_verse.chunks:
                paragraph.verses.append(current_verse)
        current_verse = None

    for child in p_tag.children:
        # ── Verse number span ────────────────────────────────────────────────
        if isinstance(child, Tag):
            classes = child.get("class", [])

            # Detect verse number — common class patterns on bible.com
            is_verse_num = any(
                "verse" in c.lower() and ("num" in c.lower() or "label" in c.lower() or "usfm" in c.lower())
                for c in classes
            ) or child.name in ("sup",)

            # Also catch plain digits as verse numbers via aria-label or data attrs
            aria = child.get("aria-label", "")
            data_usfm = child.get("data-usfm", "")

            if is_verse_num or re.fullmatch(r"\d+", child.get_text(strip=True)):
                raw_num = child.get_text(strip=True)
                if re.fullmatch(r"\d+", raw_num):
                    flush_verse()
                    current_verse = Verse(number=int(raw_num))
                    continue

            # ── Footnote span ────────────────────────────────────────────────
            if CLS_FT in classes:
                fns = _parse_footnote_span(child)
                if fns:
                    # These footnotes belong to the text accumulated so far
                    flush_chunk()
                    # Re-open chunk so next text starts fresh
                    current_footnotes = fns
                    flush_chunk()
                continue

            # ── Any other inline tag (spans wrapping text, etc.) ─────────────
            inner_text = child.get_text(" ", strip=True)
            if inner_text:
                current_chunk_text += " " + inner_text

        # ── Plain text node ──────────────────────────────────────────────────
        elif isinstance(child, NavigableString):
            text = str(child)
            if text.strip():
                current_chunk_text += " " + text

    # Flush whatever is left
    if current_verse is None and current_chunk_text.strip():
        # Paragraph with no verse number (e.g. poetic line)
        current_verse = Verse(number=None)
    flush_verse()

    return paragraph


def scrape(url: str) -> ChapterPage:
    """Fetch a bible.com chapter URL and return a ChapterPage."""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # ── h1 ───────────────────────────────────────────────────────────────────
    h1_tag = soup.find("h1")
    title = h1_tag.get_text(strip=True) if h1_tag else "Unknown"

    # ── chapter number ───────────────────────────────────────────────────────
    ch_tag = soup.find(class_=CLS_CHAPTER)
    chapter_number = ch_tag.get_text(strip=True) if ch_tag else None

    # ── walk headings + paragraphs in document order ─────────────────────────
    # Collect all __heading and __p tags in order, then group them
    content_tags = soup.find_all(class_=lambda c: c and (
        CLS_HEADING in c or CLS_P in c
    ))

    chapter = ChapterPage(title=title, chapter_number=chapter_number)
    current_section: Section | None = None

    for tag in content_tags:
        tag_classes = tag.get("class", [])

        if CLS_HEADING in tag_classes:
            # Start a new section
            current_section = Section(heading=tag.get_text(strip=True))
            chapter.sections.append(current_section)

        elif CLS_P in tag_classes:
            # Ensure there's a section to attach to
            if current_section is None:
                current_section = Section(heading=None)
                chapter.sections.append(current_section)
            para = _parse_paragraph(tag)
            if para.verses:
                current_section.paragraphs.append(para)

    return chapter


# ── Pretty printer ────────────────────────────────────────────────────────────

def print_structure(chapter: ChapterPage, show_footnotes: bool = True):
    print("=" * 70)
    print(f"TITLE          : {chapter.title}")
    print(f"CHAPTER NUMBER : {chapter.chapter_number}")
    print(f"SECTIONS       : {len(chapter.sections)}")
    print(f"TOTAL VERSES   : {len(chapter.all_verses)}")
    fn_all = chapter.all_footnotes
    tn = chapter.footnotes_by_type("tn")
    sn = chapter.footnotes_by_type("sn")
    tc = chapter.footnotes_by_type("tc")
    uk = chapter.footnotes_by_type("unknown")
    print(f"TOTAL FOOTNOTES: {len(fn_all)}  (tn={len(tn)}, sn={len(sn)}, tc={len(tc)}, unknown={len(uk)})")
    print("=" * 70)

    for s_idx, section in enumerate(chapter.sections, 1):
        print(f"\n{'─'*60}")
        print(f"SECTION {s_idx}: {section.heading or '(no heading)'}")
        print(f"{'─'*60}")

        for p_idx, para in enumerate(section.paragraphs, 1):
            print(f"\n  Paragraph {p_idx}:")
            for verse in para.verses:
                v_label = f"v{verse.number}" if verse.number else "  (line)"
                print(f"    [{v_label}] {verse.plain_text[:80]}{'...' if len(verse.plain_text) > 80 else ''}")
                if show_footnotes:
                    for fn in verse.all_footnotes:
                        print(f"           [{fn.type.upper()}] {fn.text[:90]}{'...' if len(fn.text) > 90 else ''}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    URL = "https://www.bible.com/bible/107/GEN.1.NET"
    print(f"Scraping {URL} ...\n")
    chapter = scrape(URL)
    print_structure(chapter, show_footnotes=True)

    # Example: access specific data
    print("\n\n── EXAMPLE ACCESS ──────────────────────────────────────────────")
    print(f"chapter.title               → {chapter.title!r}")
    print(f"chapter.sections[0].heading → {chapter.sections[0].heading!r}")
    v1 = chapter.all_verses[0]
    print(f"chapter.all_verses[0]       → {v1}")
    print(f"  .plain_text               → {v1.plain_text[:60]!r}")
    print(f"  .all_footnotes[0]         → {v1.all_footnotes[0]}")
    print(f"  .all_footnotes[0].type    → {v1.all_footnotes[0].type!r}")
