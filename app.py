from flask import Flask, request, jsonify, render_template
import sqlite3
from flask_cors import CORS
import requests
import json, re
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────
# GROQ CONFIG
# ─────────────────────────────────────────
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

# ─────────────────────────────────────────
# HELPER — Call Groq AI
# ─────────────────────────────────────────
def call_groq(prompt):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 2000
    }

    response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
    data = response.json()

    if "error" in data:
        raise Exception(data["error"].get("message", "Groq API error"))

    return data["choices"][0]["message"]["content"]

# ─────────────────────────────────────────
# DATABASE (SQLite)
# ─────────────────────────────────────────
def get_db():
    conn = sqlite3.connect("blog.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            subtitle TEXT,
            body TEXT,
            category TEXT,
            tone TEXT,
            length TEXT,
            author TEXT,
            tags TEXT,
            word_count INTEGER,
            read_time INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    db.commit()
    db.close()

init_db()

def row_to_dict(row):
    result = {}
    for k in row.keys():
        v = row[k]
        if isinstance(v, datetime):
            result[k] = str(v)
        else:
            result[k] = v
    return result

# ─────────────────────────────────────────
# HOME
# ─────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

# ─────────────────────────────────────────
# GENERATE BLOG
# ─────────────────────────────────────────
@app.route('/api/generate', methods=['POST'])
def generate_blog():
    data     = request.json
    title    = data.get('title', '').strip()
    topic    = data.get('topic', '').strip()
    category = data.get('category', 'Technology')
    tone     = data.get('tone', 'Professional')
    length   = data.get('length', 'Medium')
    author   = data.get('author', 'BlogCraft Author')

    if not title:
        return jsonify({'error': 'Title is required!'}), 400
    if not topic:
        return jsonify({'error': 'Topic is required!'}), 400

    word_target = {'Short': 300, 'Medium': 600, 'Long': 1000}.get(length, 600)

    prompt = f"""You are an expert blog writer. Write a complete, high-quality blog post.

Title: "{title}"
Topic: {topic}
Category: {category}
Tone: {tone}
Target Word Count: approximately {word_target} words

Format your response EXACTLY like this — keep the labels:

SUBTITLE: [Write a compelling subtitle]

BODY:
[Write blog body using markdown]

TAGS: [5-6 comma-separated tags]"""

    try:
        raw_text = call_groq(prompt)

        subtitle = ''
        body     = raw_text
        tags     = [category, 'Blog', 'Writing']

        sub_m = re.search(r'SUBTITLE:\s*(.+?)(?=\nBODY:|\Z)', raw_text, re.DOTALL)
        if sub_m:
            subtitle = sub_m.group(1).strip().strip('[]')

        body_m = re.search(r'BODY:\s*([\s\S]+?)(?=\nTAGS:|\Z)', raw_text)
        if body_m:
            body = body_m.group(1).strip()

        tags_m = re.search(r'TAGS:\s*(.+)', raw_text)
        if tags_m:
            tags = [t.strip() for t in tags_m.group(1).split(',')][:6]

        word_count = len(body.split())
        read_time  = max(1, round(word_count / 200))

        blog_id = _save_to_db(
            title, subtitle, body, category,
            tone, length, author, tags, word_count, read_time
        )

        return jsonify({
            'id': blog_id,
            'title': title,
            'subtitle': subtitle,
            'body': body,
            'category': category,
            'tone': tone,
            'length': length,
            'author': author,
            'tags': tags,
            'word_count': word_count,
            'read_time': read_time
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─────────────────────────────────────────
# SAVE TO DB
# ─────────────────────────────────────────
def _save_to_db(title, subtitle, body, category, tone, length, author, tags, word_count, read_time):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO blogs
        (title, subtitle, body, category, tone, length,
         author, tags, word_count, read_time)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (title, subtitle, body, category, tone, length,
          author, json.dumps(tags), word_count, read_time))
    db.commit()
    new_id = cursor.lastrowid
    db.close()
    return new_id

# ─────────────────────────────────────────
# GET BLOGS
# ─────────────────────────────────────────
@app.route('/api/blogs', methods=['GET'])
def get_blogs():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM blogs ORDER BY created_at DESC")
    rows = cursor.fetchall()
    db.close()

    result = []
    for r in rows:
        d = row_to_dict(r)
        d['tags'] = json.loads(d.get('tags') or '[]')
        result.append(d)

    return jsonify(result)

# ─────────────────────────────────────────
# DELETE BLOG
# ─────────────────────────────────────────
@app.route('/api/blogs/<int:id>', methods=['DELETE'])
def delete_blog(id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM blogs WHERE id=?", (id,))
    db.commit()
    db.close()
    return jsonify({'message': 'Deleted'})

# ─────────────────────────────────────────
# RUN
# ─────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)