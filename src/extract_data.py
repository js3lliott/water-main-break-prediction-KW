import requests
from bs4 import BeautifulSoup
import pandas as pd

url = 'https://open-kitchenergis.opendata.arcgis.com/datasets/KitchenerGIS::water-main-breaks/about'
page = requests.get(url)
soup = BeautifulSoup(page.content, 'html.parser')

# element: <span>Download file previously generated on Dec 17, 2022, 15:40</span>
link = soup.find('span', text='Download file previously generated on Dec 17, 2022, 15:40').find_parent('a')['href']


df = pd.read_csv(link)