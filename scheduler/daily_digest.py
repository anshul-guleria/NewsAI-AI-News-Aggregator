"""
daily_digest.py
───────────────
Runs the LangGraph pipeline for every subscribed topic, assembles a
personalised digest per user, and sends it via Brevo transactional email.
"""

import os
import random
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

from database.models import (
    TOPIC_EMOJIS,
    get_all_subscribed_topics,
    get_all_topic_articles,
    get_all_users_with_subscriptions,
)

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"

# Pill colours (background, text) for each topic — used in HTML email
TOPIC_COLORS: dict[str, tuple[str, str]] = {
    "artificial intelligence": ("#dbeafe", "#1e40af"),
    "technology":              ("#ede9fe", "#5b21b6"),
    "politics":                ("#fce7f3", "#9d174d"),
    "war and conflict":        ("#fee2e2", "#991b1b"),
    "entertainment":           ("#fef9c3", "#854d0e"),
    "sports":                  ("#dcfce7", "#166534"),
    "business and finance":    ("#d1fae5", "#065f46"),
    "science":                 ("#e0f2fe", "#0c4a6e"),
    "health and medicine":     ("#f0fdf4", "#14532d"),
    "climate and environment": ("#ecfdf5", "#064e3b"),
    "space exploration":       ("#f5f3ff", "#4c1d95"),
    "cybersecurity":           ("#fff7ed", "#7c2d12"),
    "education":               ("#eff6ff", "#1e3a5f"),
}


def run_pipeline_for_topics(topics: list[str]) -> dict[str, list]:
    """
    Invoke the LangGraph pipeline for every topic.
    If the 1-hour cache is still warm the pipeline node is skipped;
    either way we read the full accumulated article pool from DB.
    Returns {topic: [all_stored_clusters]}
    """
    from pipeline.graph import pipeline

    results: dict[str, list] = {}
    for topic in topics:
        print(f"  [Digest] Processing topic: '{topic}' ...")
        try:
            state = pipeline.invoke({
                "topic":             topic,
                "articles":          [],
                "enriched_articles": [],
                "clustered_articles":[],
                "final_articles":    [],
                "cache_hit":         False,
                "error":             None,
            })
            src = "cache" if state.get("cache_hit") else "fresh"
            all_articles = get_all_topic_articles(topic)
            results[topic] = all_articles
            print(f"  [Digest] '{topic}' — {len(all_articles)} cluster(s) in DB [{src}]")
        except Exception as exc:
            print(f"  [Digest] ERROR for '{topic}': {exc}")
            results[topic] = get_all_topic_articles(topic)

    return results


def assemble_digest(subscribed_topics: list[str], topic_articles: dict) -> list[dict]:
    """
    Pick up to 2 articles from each subscribed topic, shuffle, cap at 12.
    Each item has a '_topic' key injected for rendering.
    """
    pool: list[dict] = []
    for topic in subscribed_topics:
        articles = topic_articles.get(topic, [])
        if not articles:
            continue
        sample = random.sample(articles, min(2, len(articles)))
        for a in sample:
            pool.append({"_topic": topic, **a})
    random.shuffle(pool)
    return pool[:12]



def _article_html(index: int, article: dict) -> str:
    topic       = article.get("_topic", "")
    headline    = article.get("headline", "No headline")
    description = article.get("description", "")
    sources     = article.get("sources", []) or []
    urls        = article.get("urls", []) or []
    pub_date    = article.get("published_at", "")

    bg, fg  = TOPIC_COLORS.get(topic, ("#f3f4f6", "#374151"))
    label   = topic.title()

    # Format date
    date_str = ""
    try:
        if pub_date:
            date_str = datetime.fromisoformat(pub_date.replace("Z", "+00:00")).strftime("%B %d, %Y")
    except Exception:
        pass

    # Source line
    source_str = ", ".join(sources[:3])

    # Read-more links (max 3)
    link_parts = []
    for i, url in enumerate(urls[:3], 1):
        link_parts.append(
            f'<a href="{url}" style="color:#6c63ff;font-size:13px;font-weight:500;'
            f'text-decoration:none;margin-right:12px;">Read Article {i if len(urls) > 1 else ""}</a>'
        )
    links_html = "".join(link_parts) or '<span style="color:#9ca3af;font-size:13px;">No link available</span>'

    # Left accent colour cycles through a fixed palette
    accent_colors = ["#6c63ff", "#a855f7", "#2563eb", "#059669", "#dc2626", "#d97706"]
    accent = accent_colors[index % len(accent_colors)]

    return f"""
    <tr>
      <td style="background:#ffffff;padding:20px 40px;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="border-left:3px solid {accent};padding-left:18px;">
              <span style="display:inline-block;background:{bg};color:{fg};font-size:11px;
                font-weight:700;padding:3px 12px;border-radius:20px;text-transform:uppercase;
                letter-spacing:0.06em;margin-bottom:10px;">{label}</span>
              <h2 style="margin:0 0 8px;color:#111827;font-size:18px;font-weight:700;
                line-height:1.4;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">{headline}</h2>
              {f'<p style="margin:0 0 12px;color:#4b5563;font-size:14px;line-height:1.65;">{description}</p>' if description else ''}
              <p style="margin:0 0 10px;">
                {f'<span style="color:#9ca3af;font-size:12px;">{source_str}</span>' if source_str else ''}
                {f'<span style="color:#d1d5db;font-size:12px;margin:0 8px;">|</span><span style="color:#9ca3af;font-size:12px;">{date_str}</span>' if date_str and source_str else f'<span style="color:#9ca3af;font-size:12px;">{date_str}</span>' if date_str else ''}
              </p>
              <p style="margin:0;">{links_html}</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
    <tr>
      <td style="background:#ffffff;padding:0 40px;">
        <hr style="border:none;border-top:1px solid #f3f4f6;margin:0;">
      </td>
    </tr>"""


def build_email_html(username: str, email: str, articles: list[dict]) -> str:
    today = datetime.utcnow().strftime("%A, %B %d, %Y")
    topics_covered = sorted({a.get("_topic", "") for a in articles if a.get("_topic")})
    topic_list_str  = " · ".join(t.title() for t in topics_covered) if topics_covered else "General"
    article_count   = len(articles)

    articles_html   = "".join(_article_html(i, a) for i, a in enumerate(articles))

    no_articles_html = """
    <tr>
      <td style="background:#ffffff;padding:40px;text-align:center;">
        <p style="color:#6b7280;font-size:15px;">No news available for your subscribed topics today.</p>
      </td>
    </tr>""" if not articles else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Your Daily News Digest — NewsAI</title>
</head>
<body style="margin:0;padding:0;background:#f4f6fb;
  font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0"
  style="background:#f4f6fb;padding:40px 0;">
  <tr>
    <td align="center">
      <table width="620" cellpadding="0" cellspacing="0"
        style="max-width:620px;width:100%;">

        <!-- ── HEADER ── -->
        <tr>
          <td style="background:#1a1f3a;border-radius:14px 14px 0 0;padding:40px 44px 32px;">
            <h1 style="margin:0;color:#ffffff;font-size:30px;font-weight:800;
              letter-spacing:-0.5px;">NewsAI</h1>
            <p style="margin:6px 0 0;color:#a0a8d0;font-size:14px;">Daily Intelligence Digest</p>
            <p style="margin:20px 0 0;color:#6c74a0;font-size:13px;">{today}</p>
          </td>
        </tr>

        <!-- ── INTRO ── -->
        <tr>
          <td style="background:#ffffff;padding:28px 44px 4px;">
            <p style="margin:0 0 6px;color:#111827;font-size:16px;font-weight:600;">
              Hello, {username}
            </p>
            <p style="margin:0 0 16px;color:#4b5563;font-size:14px;line-height:1.7;">
              Here is your personalised news digest — <strong>{article_count} story
              cluster{'s' if article_count != 1 else ''}</strong> curated from your
              selected topics.
            </p>
            <p style="margin:0;padding:10px 16px;background:#f5f3ff;border-radius:8px;
              color:#5b21b6;font-size:12px;font-weight:600;text-transform:uppercase;
              letter-spacing:0.05em;">
              Topics: {topic_list_str}
            </p>
          </td>
        </tr>

        <!-- ── SPACER ── -->
        <tr>
          <td style="background:#ffffff;padding:20px 44px 0;">
            <hr style="border:none;border-top:2px solid #f3f4f6;margin:0;">
          </td>
        </tr>

        <!-- ── ARTICLES ── -->
        {articles_html}
        {no_articles_html}

        <!-- ── FOOTER ── -->
        <tr>
          <td style="background:#1a1f3a;border-radius:0 0 14px 14px;
            padding:28px 44px;">
            <p style="margin:0 0 8px;color:#a0a8d0;font-size:13px;text-align:center;
              line-height:1.7;">
              You are receiving this because you subscribed to daily digests on NewsAI.
            </p>
            <p style="margin:0;text-align:center;">
              <a href="http://localhost:5000/feed"
                style="color:#a78bfa;font-size:13px;text-decoration:none;font-weight:500;">
                Manage Subscriptions
              </a>
            </p>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>

</body>
</html>"""

def send_email_brevo(to_email: str, to_name: str, subject: str, html: str) -> bool:
    """
    POST to Brevo transactional email API.
    Returns True on success, False on failure.
    """
    # Read fresh on every call so .env changes are picked up after restart
    api_key      = os.getenv("BREVO_API_KEY", "")
    # print(api_key)
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "")
    # print(sender_email)
    sender_name  = os.getenv("BREVO_SENDER_NAME", "NewsAI Digest")

    if not api_key or not sender_email:
        print(f"  [Email] BREVO_API_KEY or BREVO_SENDER_EMAIL not set — skipping send to {to_email}")
        return False

    payload = {
        "sender":      {"name": sender_name, "email": sender_email},
        "to":          [{"email": to_email, "name": to_name}],
        "subject":     subject,
        "htmlContent": html,
    }

    try:
        resp = requests.post(
            BREVO_ENDPOINT,
            json=payload,
            headers={
                "api-key":      api_key,
                "Content-Type": "application/json",
                "accept":       "application/json",
            },
            timeout=15,
        )
        if resp.status_code in (200, 201):
            print(f"  [Email] Sent to {to_email} (Brevo messageId: {resp.json().get('messageId', '?')})")
            return True
        else:
            print(f"  [Email] Brevo error {resp.status_code}: {resp.text}")
            return False
    except Exception as exc:
        print(f"  [Email] Request failed for {to_email}: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point (called by scheduler or /daily/run)
# ─────────────────────────────────────────────────────────────────────────────

def run_daily_digest():
    today = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n[Digest] === Daily Digest Pipeline Starting — {today} ===")

    # 1. Get all unique subscribed topics
    topics = get_all_subscribed_topics()
    if not topics:
        print("[Digest] No subscriptions found — nothing to do.")
        return

    print(f"[Digest] {len(topics)} unique topic(s): {', '.join(topics)}")

    # 2. Run pipeline per topic (accumulates into DB)
    topic_articles = run_pipeline_for_topics(topics)

    # 3. Generate and email each user's digest
    users_map = get_all_users_with_subscriptions()
    if not users_map:
        print("[Digest] No subscribed users found.")
        return

    print(f"\n[Digest] Sending digests to {len(users_map)} user(s)...")
    sent = failed = 0

    for (user_id, username, email), user_topics in users_map.items():
        articles = assemble_digest(user_topics, topic_articles)

        subject      = f"Your Daily News Digest — {datetime.utcnow().strftime('%B %d, %Y')}"
        html_content = build_email_html(username, email, articles)

        ok = send_email_brevo(email, username, subject, html_content)
        if ok:
            sent += 1
        else:
            failed += 1

    print(f"\n[Digest] Complete — {sent} sent, {failed} failed.\n")
