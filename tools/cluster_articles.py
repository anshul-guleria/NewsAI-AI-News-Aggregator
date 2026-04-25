from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# model = SentenceTransformer("all-MiniLM-L6-v2")
model = SentenceTransformer("paraphrase-MiniLM-L3-v2")

def get_embeddings(texts):
    embeddings = model.encode(texts, convert_to_numpy=True)
    return embeddings

def cluster_articles_embeddings(articles, threshold=0.7):
    if not articles:
        return []

    texts = [
        a["title"] + " " + (a.get("description") or "")
        for a in articles
    ]

    embeddings = get_embeddings(texts)

    similarity_matrix = cosine_similarity(embeddings)

    clusters = []
    visited = set()

    for i in range(len(articles)):
        if i in visited:
            continue

        cluster = [articles[i]]
        visited.add(i)

        for j in range(i + 1, len(articles)):
            if j not in visited and similarity_matrix[i][j] >= threshold:
                cluster.append(articles[j])
                visited.add(j)

        clusters.append(cluster)

    return clusters
