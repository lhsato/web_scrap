from playwright.sync_api import sync_playwright
import json

def scrape_via_api_intercept():
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Intercept any API/JSON responses when the tab loads
        def handle_response(response):
            if "match" in response.url.lower() or "result" in response.url.lower():
                try:
                    data = response.json()
                    captured.append({"url": response.url, "data": data})
                    print(f"Captured API: {response.url}")
                except:
                    pass

        page.on("response", handle_response)

        page.goto("https://results.first.global/", wait_until="networkidle")
        # page.click('[aria-controls="mui-p-92681-P-matches"]')
        page.get_by_role("tab", name="Matches Results").click() 
        page.wait_for_load_state("networkidle")

        browser.close()

    if captured:
        print("\n--- API Data ---")
        for item in captured:
            print(f"URL: {item['url']}")
            print(json.dumps(item['data'], indent=2))
    else:
        print("No API calls captured — data is fully SSR'd in HTML.")

    return captured

captured = scrape_via_api_intercept()

print(f"\nTotal API calls captured: {len(captured)}")       
print("Done.")