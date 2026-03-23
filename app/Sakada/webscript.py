import requests
from bs4 import BeautifulSoup

url = "https://www.bible.com/bible/107/GEN.1.NET"
response = requests.get(url)
content = response.text

soup = BeautifulSoup(content,'lxml')

all_text = soup.find('div', class_='ChapterContent-module__cat7xG__chapter')

head = all_text.find('span', class_='ChapterContent-module__cat7xG__heading').get_text()

transcript_indiv = all_text.find_all('div', class_='ChapterContent-module__cat7xG__p')

print(head)

for transcript in transcript_indiv:
    print(transcript.get_text())
    
    
with open(f'{head}_all.txt','w+', encoding='utf-8') as file:
    for transcript in transcript_indiv:
        file.write("%s\n" % transcript.get_text())

 