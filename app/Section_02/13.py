from bs4 import BeautifulSoup
import requests


website = 'https://subslikescript.com/movie/Titanic-120338'
response = requests.get(website)
content = response.text

soup = BeautifulSoup(content,'lxml')

box = soup.find('article', class_ = 'main-article')

title = box.find('h1').get_text()
transcript  = box.find('div', class_ = 'full-script').get_text(strip=True, separator='\n')

with open(f'..\..\{title}.txt','w') as file:
    file.write(transcript)

print("End of the program")
