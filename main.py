from tools.fetch_news import fetch_news
from tools.news_scrape import process_article

from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import json
import numpy as np
from sentence_transformers import SentenceTransformer

from tools.cluster_articles import cluster_articles_embeddings

from rich import print

with open('news.json', 'r', encoding='utf-8') as file:
    news = json.load(file)

file=open("news.json","r",encoding='utf-8')

articles=json.load(file)

with ThreadPoolExecutor(max_workers=10) as executor:
    enriched_articles = list(tqdm(executor.map(process_article, articles), total=len(news)))

enriched_articles=[articles for articles in enriched_articles if articles is not None]

with open("news_updated.json", "w", encoding="utf-8") as f:
    json.dump(enriched_articles, f, indent=2)

clustered_articles=cluster_articles_embeddings(enriched_articles,threshold=0.5)

with open("cluster_articles.json",'w',encoding='utf-8') as f:
       json.dump(clustered_articles,f,indent=2)