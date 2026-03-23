from bs4 import BeautifulSoup
import requests


website = 'https://subslikescript.com/movie/Titanic-120338'
response = requests.get(website)
content = response.text

soup = BeautifulSoup(content,'lxml')
# print(soup.prettify())

box = soup.find('article', class_ = 'main-article')


title = box.find('h1').get_text()
plot = box.find('p', class_ = 'plot').get_text(strip=True, separator='\n')

transcript  = box.find('div', class_ = 'full-script').get_text(strip=True, separator='\n')

print(title)
print(plot)
print(transcript)
