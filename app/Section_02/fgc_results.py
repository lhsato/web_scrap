from bs4 import BeautifulSoup
import requests


website = 'https://results.first'
response = requests.get(website)
content = response.text

soup = BeautifulSoup(content,'lxml')

box = soup.find('article', class_ = 'main-article')

title = box.find('h1').get_text()
# transcripts  = box.find_all('p', class_ = 'cue-line') # subtitle-cue # .get_text(strip=True, separator='\n')

sentences  = box.find_all('p', class_ = 'cue-line')

with open(f'..\..\{title}_all.txt','w+') as file:
    for sentence in sentences:
        file.write("%s\n" % sentence.contents[0]) #<p class="cue-line" data-cue-idx="0" data-line-idx="0">13 meters. You should see it.</p>
        # file.write("%s\n" % transcript.contents[0]) # 13 meters. You should see it.

print("End of the program")
