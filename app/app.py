from flask import Flask, request, render_template_string
import os
import psycopg2
import psycopg2.extras

app = Flask(__name__)

# --- Config from environment ---
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "guestbook")
DB_USER = os.environ.get("DB_USER", "guest")
DB_PASS = os.environ.get("DB_PASSWORD", "guestpass")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))

HTML = """
<!doctype html>
<title>Guestbook</title>
<h2>Guestbook</h2>
<form method="post">
  <input name="content" placeholder="Write a message" required>
  <button type="submit">Save</button>
</form>
<hr>
<ul>
{% for row in rows %}
  <li><b>{{ row.created_at }}</b> — {{ row.content }}</li>
{% endfor %}
</ul>
"""

def get_conn():
    """Open a new DB connection."""
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT,
    )

def ensure_schema():
    """
    Create the notes table if it doesn't exist.
    Safe to call more than once.
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        conn.commit()

@app.route("/health")
def health():
    """
    Liveness/readiness probe.
    Returns 200 only if DB responds.
    """
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
        return "ok", 200
    except Exception as e:
        return f"not ok: {e}", 500

@app.route("/", methods=["GET", "POST"])
def index():
    # Try to make sure schema exists.
    # If DB is down right now, we won't kill the whole app.
    try:
        ensure_schema()
    except Exception:
        # We'll show an error below if we can't talk to DB
        pass

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if content:
            try:
                with get_conn() as conn, conn.cursor() as cur:
                    cur.execute("INSERT INTO notes (content) VALUES (%s);", (content,))
                    conn.commit()
            except Exception as e:
                return f"DB error while saving: {e}", 500

    # Try to fetch rows newest-first
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    "SELECT created_at, content FROM notes ORDER BY created_at DESC;"
                )
                rows = cur.fetchall()
    except Exception as e:
        # DB down? Return a degraded page instead of crashing.
        rows = []
        return (
            render_template_string(
                """
                <!doctype html>
                <title>Guestbook</title>
                <h2>Guestbook</h2>
                <p style="color:red;">Database not available yet: {{ error }}</p>
                """,
                error=str(e),
            ),
            500,
        )

    return render_template_string(HTML, rows=rows)

if __name__ == "__main__":
    # IMPORTANT: we do NOT call ensure_schema() or init_db() here,
    # and we definitely do not try to connect to Postgres here.
    # This lets the container start even if DB isn't ready yet.
    app.run(host="0.0.0.0", port=5000)
