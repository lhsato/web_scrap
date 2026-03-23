from bs4 import BeautifulSoup
import requests


website = 'https://subslikescript.com/movie/Titanic-120338'
# Case 1 show error 403 due to my VPN (Cloudflare), so I use a proxy to bypass it
# https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status
# shutdown VPN and try again, it works without error
response = requests.get(website)
content = response.text
soup = BeautifulSoup(content,'lxml')
#Case 2 copy content.text and save to an html file
print(soup.prettify())
  
box = soup.find('article', class_ = 'main-article')

   
title = box.find('h1').get_text()
plot = box.find('p', class_ = 'plot').get_text(strip=True, separator='\n')

transcript  = box.find('div', class_ = 'full-script').get_text(strip=True, separator='\n')

print(title)
print(plot)  
print(transcript)
