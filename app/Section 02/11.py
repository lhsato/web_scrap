from bs4 import BeautifulSoup
import requests


website = 'https://subslikescript.com/movie/Titanic-120338'
response = requests.get(website)
content = response.text

soup = BeautifulSoup(content,'lxml')
print(soup.prettify())