import requests
from bs4 import BeautifulSoup

URL = "https://www.bible.com/bible/107/GEN.1.NET"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Class name shortcuts ──────────────────────────────────────────────────────
CLS_HEADING  = "ChapterContent-module__cat7xG__heading"
CLS_CHAPTER  = "ChapterContent-module__cat7xG__chapter"
CLS_P        = "ChapterContent-module__cat7xG__p"
CLS_FT       = "ft"


def get_text(tag):
    """Return stripped inner text of a tag, collapsing whitespace."""
    return " ".join(tag.get_text(" ", strip=True).split())


def scrape_bible_chapter(url: str) -> dict:
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # 1) <h1> content
    h1_tag = soup.find("h1")
    h1_text = get_text(h1_tag) if h1_tag else None

    # 2) Heading
    heading_tag = soup.find(class_=CLS_HEADING)
    heading_text = get_text(heading_tag) if heading_tag else None

    # 3) Chapter number/label
    chapter_tag = soup.find(class_=CLS_CHAPTER)
    chapter_text = get_text(chapter_tag) if chapter_tag else None

    # 4 & 5) All <p> blocks — preserve order, include nested .ft footnotes
    paragraphs = []
    for p_tag in soup.find_all(class_=CLS_P):
        # Collect every text node AND .ft spans in document order
        parts = []
        for element in p_tag.descendants:
            # Capture .ft footnote text inline
            if hasattr(element, "get") and CLS_FT in element.get("class", []):
                ft_text = get_text(element)
                if ft_text:
                    parts.append(f"[FOOTNOTE: {ft_text}]")
            # Capture plain NavigableString (direct text nodes only, skip nested tags' text)
            elif element.parent == p_tag or (
                hasattr(element, "name") is False  # NavigableString
                and not any(
                    CLS_FT in (getattr(a, "get", lambda *_: [])(  # noqa
                        "class", [])) for a in element.parents
                )
            ):
                pass  # handled by get_text below for simplicity

        # Simpler, robust approach: get full text then append footnotes separately
        # Full paragraph text (strips footnotes' raw text too — we re-add them labeled)
        full_text = get_text(p_tag)

        # Collect footnotes within this paragraph
        footnotes = [get_text(ft) for ft in p_tag.find_all(class_=CLS_FT) if get_text(ft)]

        paragraphs.append({
            "text": full_text,
            "footnotes": footnotes,
        })

    return {
        "h1": h1_text,
        "heading": heading_text,
        "chapter": chapter_text,
        "paragraphs": paragraphs,
    }


def print_results(data: dict):
    print("=" * 70)
    print(f"H1          : {data['h1']}")
    print(f"Heading     : {data['heading']}")
    print(f"Chapter     : {data['chapter']}")
    print("=" * 70)
    print(f"Paragraphs  : {len(data['paragraphs'])} found\n")

    for i, para in enumerate(data["paragraphs"], 1):
        print(f"--- Paragraph {i} ---")
        print(f"Text      : {para['text'][:120]}{'...' if len(para['text']) > 120 else ''}")
        if para["footnotes"]:
            print(f"Footnotes ({len(para['footnotes'])}):")
            for fn in para["footnotes"]:
                print(f"  • {fn[:100]}{'...' if len(fn) > 100 else ''}")
        print()


if __name__ == "__main__":
    print(f"Scraping: {URL}\n")
    result = scrape_bible_chapter(URL)
    print_results(result)