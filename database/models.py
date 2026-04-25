import json
from datetime import datetime, timedelta
from database.db import get_db

# Cache articles for 1 hour before re-running the pipeline
CACHE_TTL_HOURS = 1


def create_user(username: str, email: str, password_hash: str) -> dict:
    conn = get_db()
    try:
        created_at = datetime.utcnow().isoformat()
        cursor = conn.execute(
            "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (username, email.lower(), password_hash, created_at),
        )
        conn.commit()
        return {
            "id": cursor.lastrowid,
            "username": username,
            "email": email.lower(),
            "created_at": created_at,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Topics / Cache
# ---------------------------------------------------------------------------

def _normalize(topic: str) -> str:
    return topic.strip().lower()


def get_topic_cache(topic: str) -> list | None:
    """Return cached articles if the topic was fetched within CACHE_TTL_HOURS."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM topics WHERE topic = ?", (_normalize(topic),)
        ).fetchone()
        if not row:
            return None
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if datetime.utcnow() - fetched_at > timedelta(hours=CACHE_TTL_HOURS):
            return None  # expired
        return json.loads(row["result_json"])
    finally:
        conn.close()


def save_topic_cache(topic: str, result: list) -> int:
    """
    Merge new pipeline results into the existing topic cache instead of
    overwriting. New article clusters are appended and deduplicated by URL,
    so articles accumulate across pipeline runs rather than being replaced.
    Returns the topic row id.
    """
    conn = get_db()
    try:
        normalized = _normalize(topic)
        fetched_at = datetime.utcnow().isoformat()

        # Load whatever is already stored (ignore TTL here — we always merge)
        existing_row = conn.execute(
            "SELECT result_json FROM topics WHERE topic = ?", (normalized,)
        ).fetchone()
        existing: list = json.loads(existing_row["result_json"]) if existing_row else []

        # Build a set of all URLs already stored so we can deduplicate
        stored_urls: set[str] = set()
        for cluster in existing:
            for url in cluster.get("urls", []):
                stored_urls.add(url)

        # Only append clusters whose URLs are not already present
        new_clusters = []
        for cluster in result:
            cluster_urls = set(cluster.get("urls", []))
            if cluster_urls and cluster_urls.isdisjoint(stored_urls):
                new_clusters.append(cluster)
                stored_urls.update(cluster_urls)

        merged = existing + new_clusters

        conn.execute(
            """
            INSERT INTO topics (topic, fetched_at, result_json)
            VALUES (?, ?, ?)
            ON CONFLICT(topic) DO UPDATE SET
                fetched_at  = excluded.fetched_at,
                result_json = excluded.result_json
            """,
            (normalized, fetched_at, json.dumps(merged)),
        )
        conn.commit()

        if new_clusters:
            print(f"[Cache] '{topic}' +{len(new_clusters)} new clusters (total {len(merged)})")
        else:
            print(f"[Cache] '{topic}' no new clusters — {len(merged)} stored")

        row = conn.execute(
            "SELECT id FROM topics WHERE topic = ?", (normalized,)
        ).fetchone()
        return row["id"]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_all_topic_articles(topic: str) -> list:
    """
    Return ALL stored articles for a topic regardless of cache TTL.
    Used by the digest assembler so it always has the full article pool.
    """
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT result_json FROM topics WHERE topic = ?", (_normalize(topic),)
        ).fetchone()
        return json.loads(row["result_json"]) if row else []
    finally:
        conn.close()


def get_topic_id(topic: str) -> int | None:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM topics WHERE topic = ?", (_normalize(topic),)
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def log_user_search(user_id: int, topic_id: int):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO user_searches (user_id, topic_id, searched_at) VALUES (?, ?, ?)",
            (user_id, topic_id, datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_history(user_id: int) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT t.topic, us.searched_at
            FROM user_searches us
            JOIN topics t ON us.topic_id = t.id
            WHERE us.user_id = ?
            ORDER BY us.searched_at DESC
            LIMIT 20
            """,
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Predefined daily-digest topics
# ---------------------------------------------------------------------------

PREDEFINED_TOPICS: list[str] = [
    "artificial intelligence",
    "technology",
    "politics",
    "war and conflict",
    "entertainment",
    "sports",
    "business and finance",
    "science",
    "health and medicine",
    "climate and environment",
    "space exploration",
    "cybersecurity",
    "education",
]

# Emoji labels shown in UI / digest output
TOPIC_EMOJIS: dict[str, str] = {
    "artificial intelligence": "🤖",
    "technology":              "💻",
    "politics":                "🏛️",
    "war and conflict":        "⚔️",
    "entertainment":           "🎬",
    "sports":                  "⚽",
    "business and finance":    "📈",
    "science":                 "🔬",
    "health and medicine":     "🏥",
    "climate and environment": "🌍",
    "space exploration":       "🚀",
    "cybersecurity":           "🔒",
    "education":               "📚",
}


# ---------------------------------------------------------------------------
# User topic subscriptions
# ---------------------------------------------------------------------------

def get_user_subscriptions(user_id: int) -> list[str]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT topic FROM user_topic_subscriptions WHERE user_id = ? ORDER BY subscribed_at",
            (user_id,),
        ).fetchall()
        return [r["topic"] for r in rows]
    finally:
        conn.close()


def set_user_subscriptions(user_id: int, topics: list[str]):
    """Replace all subscriptions for a user atomically."""
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM user_topic_subscriptions WHERE user_id = ?", (user_id,)
        )
        now = datetime.utcnow().isoformat()
        for topic in topics:
            if topic in PREDEFINED_TOPICS:
                conn.execute(
                    "INSERT OR IGNORE INTO user_topic_subscriptions (user_id, topic, subscribed_at) VALUES (?, ?, ?)",
                    (user_id, topic, now),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_all_subscribed_topics() -> list[str]:
    """Return the unique set of topics at least one user is subscribed to."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT DISTINCT topic FROM user_topic_subscriptions"
        ).fetchall()
        return [r["topic"] for r in rows]
    finally:
        conn.close()


def get_all_users_with_subscriptions() -> dict[tuple, list[str]]:
    """Return {(user_id, username, email): [topics, ...]} for all subscribed users."""
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT u.id, u.username, u.email, uts.topic
            FROM user_topic_subscriptions uts
            JOIN users u ON uts.user_id = u.id
            ORDER BY u.id
            """
        ).fetchall()
        result: dict[tuple, list[str]] = {}
        for r in rows:
            key = (r["id"], r["username"], r["email"])
            result.setdefault(key, []).append(r["topic"])
        return result
    finally:
        conn.close()
