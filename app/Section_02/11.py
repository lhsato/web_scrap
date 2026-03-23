from bs4 import BeautifulSoup
import requests


website = 'https://subslikescript.com/movie/Titanic-120338'
#Case 1 show error 403 due to my VPN (Cloudflare), so I use a proxy to bypass it
# https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status
# shutdown VPN and try again, it works without error
response = requests.get(website)
content = response.text
soup = BeautifulSoup(content,'lxml')
#Case 2 copy content.text and save to an html file
print(soup.prettify())


#Case 3 save soup to an html file
# with open('titanic.html','w', encoding='utf-8') as file:
#     file.write(soup.prettify())

