from bs4 import BeautifulSoup
import requests


website = 'https://www.bible.com/bible/107/GEN.1.NET'
# Case 1 show error 403 due to my VPN (Cloudflare), so I use a proxy to bypass it
# https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status
# shutdown VPN and try again, it works without error
response = requests.get(website)
response.encoding = 'utf-8'  # Ensure the correct encoding for Khmer characters
content = response.text

soup = BeautifulSoup(content,'lxml')

paragraphs = soup.find('div', class_ = 'ChapterContent-module__cat7xG__bible-reader')

title = paragraphs.find('h1').get_text()
title2 = paragraphs.find('span', class_ = 'ChapterContent-module__cat7xG__heading').get_text()
transcripts  = paragraphs.find_all('span', class_ = 'ChapterContent-module__cat7xG__verse') # subtitle-cue # .get_text(strip=True, separator='\n')


with open(f'utils/Bible.txt', 'w', encoding='utf-8') as file:
    file.write("%s\n" % title)  # Write the title to the file
    file.write("%s\n" % title2)  # Write the title to the file
    for transcript in transcripts:
        # Added .get_text() so you get the words, not the HTML code
        file.write("%s\n" % transcript.get_text()) 

print("File created successfully!")
print("End of the program")

print(title)
# print(plot)  
print(transcript)