from bs4 import BeautifulSoup
import requests


# website = 'https://subslikescript.com/movie/Titanic-120338'
website = 'https://www.bible.com/bible/1270/GEN.1.%2525E1%25259E%252596%2525E1%25259E%252582%2525E1%25259E%252594'
response = requests.get(website)
content = response.text

soup = BeautifulSoup(content,'lxml')
# print(soup.prettify())

# box = soup.find('article', class_ = 'main-article')
box = soup.find("div", {"data-testid": "chapter-content"})

# soup.find('h1').get_text()
title = box.find('h1').get_text()
# transcript  = box.find('div', class_ = 'full-script').get_text(strip=True, separator=' ')

# with open(f'{title}.txt','w') as file:
#     file.write(transcript)

print(title)
