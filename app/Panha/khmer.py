from bs4 import BeautifulSoup
import requests

website = 'https://www.bible.com/bible/1270/GEN.1.%25E1%259E%2596%25E1%259E%2582%25E1%259E%2594'

response = requests.get(website)
content = response.text
soup = BeautifulSoup(content, 'lxml')

box = soup.find('div' , class_ = 'ChapterContent-module__cat7xG__yv-bible-text')

title = box.find('h1').get_text()
texts = box.find_all('span' , class_ = 'ChapterContent-module__cat7xG__content')

count = 1
bold_next = False

with open(f'{title}.txt', 'w', encoding = 'utf-8') as file: 
    for text in texts:
        txt = text.get_text(strip = True)
        if txt == '':
            bold_next = True
            continue
        if bold_next: 
            file.write(f'**{count}**. {txt}\n')
            bold_next = False
        else: 
            file.write(f'{count}. {txt}\n')
        count += 1
    