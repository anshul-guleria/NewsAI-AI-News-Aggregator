import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

load_dotenv()

# Make sure project root is on the path when running this module directly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.models import get_topic_cache, save_topic_cache
from tools.cluster_articles import cluster_articles_embeddings
from tools.fetch_news import fetch_news_articles
from tools.news_scrape import process_article
from tools.title_description_generator import generate_title_description

API_KEY = os.getenv("NEWS_API_KEY")


class PipelineState(TypedDict):
    topic: str
    articles: List[dict]
    enriched_articles: List[dict]
    clustered_articles: List[List[dict]]
    final_articles: List[dict]
    cache_hit: bool
    error: Optional[str]


def check_cache_node(state: PipelineState) -> PipelineState:
    """Return cached result if fresh (< 1 h). Sets cache_hit flag."""
    cached = get_topic_cache(state["topic"])
    if cached is not None:
        print(f"[Pipeline] Cache HIT for '{state['topic']}'")
        return {**state, "final_articles": cached, "cache_hit": True}
    print(f"[Pipeline] Cache MISS for '{state['topic']}' — running full pipeline")
    return {**state, "cache_hit": False}


def fetch_news_node(state: PipelineState) -> PipelineState:
    """Fetch raw articles from NewsAPI."""
    try:
        articles = fetch_news_articles(
            query=state["topic"],
            language="en",
            sortBy="publishedAt",
            pageSize=20,
            apiKey=API_KEY,
        )
        print(f"[Pipeline] Fetched {len(articles)} articles")
        return {**state, "articles": articles}
    except Exception as exc:
        print(f"[Pipeline] fetch_news_node error: {exc}")
        return {**state, "articles": [], "error": str(exc)}


def scrape_node(state: PipelineState) -> PipelineState:
    """Enrich articles with full text via newspaper3k (parallel)."""
    articles = state.get("articles", [])
    if not articles:
        return {**state, "enriched_articles": []}
    with ThreadPoolExecutor(max_workers=10) as executor:
        enriched = list(executor.map(process_article, articles))
    enriched = [a for a in enriched if a is not None]
    print(f"[Pipeline] Scraped {len(enriched)} articles")
    return {**state, "enriched_articles": enriched}


def cluster_node(state: PipelineState) -> PipelineState:
    """Cluster articles by semantic similarity."""
    enriched = state.get("enriched_articles", [])
    if not enriched:
        return {**state, "clustered_articles": []}
    clustered = cluster_articles_embeddings(enriched, threshold=0.5)
    print(f"[Pipeline] Formed {len(clustered)} clusters")
    return {**state, "clustered_articles": clustered}


def title_node(state: PipelineState) -> PipelineState:
    """Generate a headline + description for every cluster via Groq."""
    clustered = state.get("clustered_articles", [])
    if not clustered:
        return {**state, "final_articles": []}
    final = generate_title_description(clustered)
    print(f"[Pipeline] Generated titles for {len(final)} clusters")
    return {**state, "final_articles": final}


def save_to_db_node(state: PipelineState) -> PipelineState:
    """Persist results to the topics cache table."""
    if not state.get("error") and state.get("final_articles"):
        save_topic_cache(state["topic"], state["final_articles"])
        print(f"[Pipeline] Saved to DB for '{state['topic']}'")
    return state


def _route_after_cache(state: PipelineState) -> str:
    return "end" if state["cache_hit"] else "fetch_news"


def build_pipeline():
    graph = StateGraph(PipelineState)

    graph.add_node("check_cache",     check_cache_node)
    graph.add_node("fetch_news",      fetch_news_node)
    graph.add_node("scrape",          scrape_node)
    graph.add_node("cluster",         cluster_node)
    graph.add_node("generate_titles", title_node)
    graph.add_node("save_to_db",      save_to_db_node)

    graph.set_entry_point("check_cache")

    graph.add_conditional_edges(
        "check_cache",
        _route_after_cache,
        {"end": END, "fetch_news": "fetch_news"},
    )

    graph.add_edge("fetch_news",      "scrape")
    graph.add_edge("scrape",          "cluster")
    graph.add_edge("cluster",         "generate_titles")
    graph.add_edge("generate_titles", "save_to_db")
    graph.add_edge("save_to_db",      END)

    return graph.compile()


pipeline = build_pipeline()
