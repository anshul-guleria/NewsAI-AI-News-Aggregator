import os
import requests
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

API_KEY = os.getenv("NEWS_API_KEY")
BASE_URL = "https://newsapi.org/v2/everything"


def fetch_news_articles(query, language, sortBy, pageSize, apiKey) -> list[dict]:
    """Fetch articles from NewsAPI and return a cleaned list. No file I/O."""
    params = {
        "q": query,
        "language": language,
        "sortBy": sortBy,
        "pageSize": pageSize,
        "apiKey": apiKey,
    }

    response = requests.get(BASE_URL, params=params)

    if response.status_code != 200:
        raise Exception(
            f"Error fetching news: {response.status_code} — {response.text}"
        )

    data = response.json()
    articles = data.get("articles", [])

    cleaned_articles = []
    for article in articles:
        cleaned = {
            "title": article.get("title"),
            "description": article.get("description"),
            "url": article.get("url"),
            "source": article.get("source", {}).get("name"),
            "published_at": article.get("publishedAt"),
            "fetched_at": datetime.utcnow().isoformat(),
        }
        if cleaned["title"] and cleaned["url"]:
            cleaned_articles.append(cleaned)

    return cleaned_articles


def fetch_news(topic: str) -> list[dict]:
    articles = fetch_news_articles(
        query=topic,
        language="en",
        sortBy="publishedAt",
        pageSize=20,
        apiKey=API_KEY,
    )
    print(f"Fetched {len(articles)} articles")
    return articles


if __name__ == "__main__":
    fetch_news("WAR")

