from bs4 import BeautifulSoup
import requests


website = 'https://www.bible.com/bible/1270/GEN.1.%2525E1%25259E%252596%2525E1%25259E%252582%2525E1%25259E%252594'
response = requests.get(website)
content = response.text

soup = BeautifulSoup(content)
# soup = BeautifulSoup(content,'lxml')
# why do we need a parser
# https://www.geeksforgeeks.org/python/html5lib-and-lxml-parsers-in-python/
# what is a BLOB
# https://www.geeksforgeeks.org/dbms/blob-full-form/
# https://www.tutorialspoint.com/article/html5lib-and-lxml-parsers-in-python
# https://scrapeops.io/python-web-scraping-playbook/best-python-html-parsing-libraries/

box = soup.find("div", {"data-testid": "chapter-content"})

title = box.find('h1').get_text()
# transcript  = soup.find('div', class_ = 'full-script').get_text(strip=True, separator='\n')

# with open(f'{title}.txt','w') as file:
#     file.write(transcript)

print(title)
