from bs4 import BeautifulSoup
import requests

website = 'https://www.bible.com/bible/107/GEN.1.NET'

response = requests.get(website)
content = response.text
soup = BeautifulSoup(content, 'lxml')

box = soup.find('div', class_ = 'ChapterContent-module__cat7xG__yv-bible-text')

title = box.find('h1').get_text()
texts = box.find_all('span', class_ = 'ChapterContent-module__cat7xG__content') 
notes = box.find_all('span', class_='ft')

with open(f'{title}.txt', 'w', encoding='utf-8') as file:
    for text, note in zip(texts, notes):
        txt = text.get_text(strip=True)
        nt = note.get_text(strip=True)
        if txt:
            file.write(txt + f' [{nt}]\n')