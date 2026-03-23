import requests
from bs4 import BeautifulSoup

url = "https://results.first.global/"
headers = {"User-Agent": "Mozilla/5.0"}

soup = BeautifulSoup(requests.get(url, headers=headers).text, "html.parser")

# Find all text nodes and reconstruct rows
# The rankings tab content is server-rendered, so it's in the raw HTML
# Each ranking entry contains: rank number, alliance name, score, played count, team codes

# Get all text, split into lines, filter ranking rows
lines = [line.strip() for line in soup.get_text("\n").split("\n") if line.strip()]

rankings = []
i = 0
while i < len(lines):
    line = lines[i]
    # Rank rows start with a number followed by "Alliance X"
    if line.isdigit() and i + 1 < len(lines) and lines[i+1].startswith("Alliance"):
        try:
            rank       = line
            alliance   = lines[i+1]
            rank_score = lines[i+2]
            played     = lines[i+3]
            teams      = [lines[i+4], lines[i+5], lines[i+6], lines[i+7]]
            rankings.append({
                "Rank": rank,
                "Alliance": alliance,
                "Rank Score": rank_score,
                "Played": played,
                "Teams": ", ".join(teams)
            })
            i += 8
            continue
        except IndexError:
            pass
    i += 1

for r in rankings:
    print(r)