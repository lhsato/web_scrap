from bs4 import BeautifulSoup
import requests


website = 'https://subslikescript.com/movie/Titanic-120338'
response = requests.get(website)
content = response.text

soup = BeautifulSoup(content,'lxml')

box = soup.find('article', class_ = 'main-article')

title = box.find('h1').get_text()
# subtitle-cue
transcripts  = box.find_all('div', class_ = 'subtitle-cue')
# .get_text(strip=True, separator='\n')

with open(f'{title}_all.txt','w') as file:
    for transcript in transcripts:
        file.write("%s\n" % transcript)

print(transcripts[5])
