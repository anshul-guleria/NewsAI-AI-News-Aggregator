from llm.groq_service import load_groq
from langchain_core.prompts import PromptTemplate

# Lazy-load so env vars are available before the client is constructed
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = load_groq()
    return _llm


prompt = PromptTemplate.from_template(
    """
    You are a professional news editor.

    Below are multiple news titles and descriptions about the same event.

    {input_text}

    Your task:
    - Create ONE clear, concise headline
    - Write ONE short description (3-4 sentences)

    Rules:
    - Combine information from all articles
    - Remove repetition
    - Focus only on key facts
    - Keep it factual and neutral
    - Do not mention "Article", "Title", or "Content"

    Input format:
    Titles: [Article Titles]
    Descriptions: [Article Descriptions]

    Output format (exactly as shown, no extra text):
    Headline: Your concise headline here
    Description: Your short description here
    """
)


def _parse_response(content: str) -> tuple[str, str]:
    """Extract Headline and Description lines from the LLM output."""
    headline, description = "", []
    capturing_desc = False
    for line in content.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("Headline:"):
            headline = stripped.replace("Headline:", "").strip()
            capturing_desc = False
        elif stripped.startswith("Description:"):
            description.append(stripped.replace("Description:", "").strip())
            capturing_desc = True
        elif capturing_desc and stripped:
            description.append(stripped)
    return headline, " ".join(description).strip()


def generate_title_description(clustered_articles: list) -> list:
    """
    Accept a list of clusters (each cluster = list of article dicts).
    Return a list of processed article dicts: headline, description, sources, urls.
    """
    results = []

    for cluster in clustered_articles:
        if not cluster:
            continue

        titles = [a.get("title") or "" for a in cluster if a.get("title")]
        descs = [a.get("description") or "" for a in cluster]
        descs = [d for d in descs if d.strip()]
        sources = list({a.get("source", "") for a in cluster if a.get("source")})
        urls = list({a.get("url", "") for a in cluster if a.get("url")})
        dates = sorted([a.get("published_at", "") for a in cluster if a.get("published_at")])

        input_text = (
            f"Titles: {', '.join(titles)}\n"
            f"Descriptions: {', '.join(descs)}"
        )

        try:
            response = _get_llm().invoke(prompt.format(input_text=input_text))
            headline, description = _parse_response(response.content)
        except Exception as e:
            print(f"[WARNING] LLM call failed: {e}")
            headline, description = "", ""

        results.append({
            "headline":     headline or (titles[0] if titles else "News Update"),
            "description":  description or (descs[0] if descs else ""),
            "sources":      sources,
            "urls":         urls,
            "published_at": dates[0] if dates else "",
            "article_count": len(cluster),
        })

    return results

