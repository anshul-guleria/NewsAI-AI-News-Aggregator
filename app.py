import json
import numpy as np
from rich import print
# from tools.summarize_articles import summarize_articles
from tools.title_description_generator import generate_title_description

# with open('cluster_articles.json','r',encoding='utf-8') as f:
#     clustered_articles=json.load(f)

# summarized_articles=summarize_articles(clustered_articles)

# with open("summarized_articles.json",'w',encoding='utf-8') as f:
#     json.dump(summarized_articles, f, indent=2)

with open('summarized_articles.json','r',encoding='utf-8') as f:
    summarized_articles=json.load(f)

generate_title_description(summarized_articles)
