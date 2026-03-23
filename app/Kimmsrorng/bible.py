from bs4 import BeautifulSoup
import requests

website = 'https://www.bible.com/bible/107/GEN.1.NET'
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
response = requests.get(website, headers=headers)
content = response.text
soup = BeautifulSoup(content, 'html.parser') 

title = soup.find('h1')
if title:
    print(f"TITLE: {title.get_text(strip=True)}")

# 6. Look for the DIV that holds the whole chapter
# Instead of class, we look for 'data-testid'
chapter_div = soup.find('div', attrs={'data-testid': 'chapter-content'})

print("\n--- CHAPTER TEXT ---")

if chapter_div:
    # This gets all text inside that div, including verses
    print(chapter_div.get_text(separator="\n", strip=True))
else:
    print("Could not find the chapter content. The website might be blocking us.")