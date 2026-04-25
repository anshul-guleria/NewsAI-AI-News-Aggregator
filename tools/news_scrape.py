from newspaper import Article
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm


def extract_article_content(url):
    try:
        article = Article(url)
        article.download()
        article.parse()

        return {
            "text": article.text,
            "publish_date": str(article.publish_date),
            "top_image": article.top_image
        }

    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None
    

def process_article(article):
    content = extract_article_content(article["url"])
    if content:
        article["content"] = content["text"]
    else:
        article["content"] = "-1"
        return
    return article
