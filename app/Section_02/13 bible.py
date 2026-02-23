from bs4 import BeautifulSoup
import requests


website = 'https://www.bible.com/bible/1270/GEN.1.%2525E1%25259E%252596%2525E1%25259E%252582%2525E1%25259E%252594'
response = requests.get(website)
content = response.text

soup = BeautifulSoup(content,'lxml')

box = soup.find("div", {"data-testid": "chapter-content"})

title = box.find('h1').get_text()
# transcript  = soup.find('div', class_ = 'full-script').get_text(strip=True, separator='\n')

# with open(f'{title}.txt','w') as file:
#     file.write(transcript)

print(title)
