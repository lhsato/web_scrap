from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def scrape_matches():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=False so you can SEE what's happening
        page = browser.new_page()

        page.goto("https://results.first.global/", wait_until="networkidle")

        # Click the tab
        page.get_by_role("tab", name="Matches Results").click()
        page.wait_for_timeout(5000)  # wait 5 seconds for content to render

        # Dump the full HTML to a file so we can inspect it
        html = page.content()
        with open("page_dump.html", "w", encoding="utf-8") as f:
            f.write(html)

        print("✅ HTML saved to page_dump.html")
        print(f"HTML size: {len(html)} characters")

        browser.close()

scrape_matches()