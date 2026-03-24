from flask import Flask, request, jsonify, render_template
import mysql.connector
from flask_cors import CORS
import requests
import json, re
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")
app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────
# 🔑 FREE GROQ API KEY
# ✅ Get yours FREE at: https://console.groq.com
# ✅ No credit card! Works in India!
# ✅ 14,400 requests per day FREE!
# ─────────────────────────────────────────
# 👈 paste your free Groq key here
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"  # FREE model — latest & smart!

# ─────────────────────────────────────────
# HELPER — Call Groq AI (FREE!)
# ─────────────────────────────────────────
def call_groq(prompt):
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type":  "application/json"
    }
    payload = {
        "model":       GROQ_MODEL,
        "messages":    [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens":  2000
    }
    response = requests.post(
        GROQ_URL,
        headers=headers,
        json=payload,
        timeout=30
    )
    data = response.json()

    # Check for errors
    if "error" in data:
        raise Exception(data["error"].get("message", "Groq API error"))

    return data["choices"][0]["message"]["content"]

# ─────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────
def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",      # 👈 your MySQL username
        password="Shankar2sep@",      # 👈 your MySQL password
        database="blogcraft_db"
    )

def row_to_dict(row):
    result = {}
    for k, v in row.items():
        if isinstance(v, datetime): result[k] = str(v)
        else: result[k] = v
    return result

# ─────────────────────────────────────────
# HOME
# ─────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

# ─────────────────────────────────────────
# GENERATE BLOG — FREE Groq AI
# ─────────────────────────────────────────
@app.route('/api/generate', methods=['POST'])
def generate_blog():
    data     = request.json
    title    = data.get('title',    '').strip()
    topic    = data.get('topic',    '').strip()
    category = data.get('category', 'Technology')
    tone     = data.get('tone',     'Professional')
    length   = data.get('length',   'Medium')
    author   = data.get('author',   'BlogCraft Author')

    if not title: return jsonify({'error': 'Title is required!'}), 400
    if not topic: return jsonify({'error': 'Topic is required!'}), 400

    word_target = {'Short': 300, 'Medium': 600, 'Long': 1000}.get(length, 600)

    # ── Build AI Prompt ──
    prompt = f"""You are an expert blog writer. Write a complete, high-quality blog post.

Title: "{title}"
Topic: {topic}
Category: {category}
Tone: {tone}
Target Word Count: approximately {word_target} words

Format your response EXACTLY like this — keep the labels:

SUBTITLE: [Write a compelling 1-2 sentence subtitle that hooks the reader]

BODY:
[Write the complete blog body here.
Use ## for main section headings.
Use ### for sub-headings.
Use **bold** for important terms.
Include one blockquote using > symbol.
Use - for bullet point lists.
Do NOT repeat the title inside the body.
Write in {tone} tone.
Aim for {word_target} words.
Make it genuinely useful and informative.]

TAGS: [5-6 comma-separated relevant tags]"""

    try:
        raw_text = call_groq(prompt)

        # ── Parse AI response ──
        subtitle = ''
        body     = raw_text
        tags     = [category, 'Blog', 'Writing']

        sub_m = re.search(r'SUBTITLE:\s*(.+?)(?=\nBODY:|\Z)', raw_text, re.IGNORECASE | re.DOTALL)
        if sub_m:
            subtitle = sub_m.group(1).strip().strip('[]').replace('\n', '')

        body_m = re.search(r'BODY:\s*([\s\S]+?)(?=\nTAGS:|\Z)', raw_text, re.IGNORECASE)
        if body_m:
            body = body_m.group(1).strip()

        tags_m = re.search(r'TAGS:\s*(.+)', raw_text, re.IGNORECASE)
        if tags_m:
            tags = [t.strip().strip('[]#') for t in tags_m.group(1).split(',') if t.strip()][:6]

        word_count = len(body.split())
        read_time  = max(1, round(word_count / 200))

        # ── Save to MySQL ──
        blog_id = _save_to_db(
            title, subtitle, body, category,
            tone, length, author, tags, word_count, read_time
        )

        return jsonify({
            'id':         blog_id,
            'title':      title,
            'subtitle':   subtitle,
            'body':       body,
            'category':   category,
            'tone':       tone,
            'length':     length,
            'author':     author,
            'tags':       tags,
            'word_count': word_count,
            'read_time':  read_time,
            'date':       datetime.now().strftime('%d-%m-%Y'),
            'time':       datetime.now().strftime('%H:%M'),
        })

    except Exception as e:
        error_msg = str(e)
        if 'invalid_api_key' in error_msg.lower() or 'authentication' in error_msg.lower():
            return jsonify({'error': '❌ Invalid Groq API key! Get free key at: console.groq.com'}), 401
        if 'rate_limit' in error_msg.lower():
            return jsonify({'error': '⏳ Too many requests! Wait 1 minute and try again.'}), 429
        return jsonify({'error': f'AI Error: {error_msg}'}), 500


def _save_to_db(title, subtitle, body, category, tone, length, author, tags, word_count, read_time):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO blogs
              (title, subtitle, body, category, tone, length,
               author, tags, word_count, read_time)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (title, subtitle, body, category, tone, length,
              author, json.dumps(tags), word_count, read_time))
        db.commit()
        new_id = cursor.lastrowid
        db.close()
        return new_id
    except Exception as e:
        print(f"DB save error: {e}")
        return None

# ─────────────────────────────────────────
# GET ALL BLOGS
# ─────────────────────────────────────────
@app.route('/api/blogs', methods=['GET'])
def get_blogs():
    search   = request.args.get('search',   '')
    category = request.args.get('category', '')
    db       = get_db()
    cursor   = db.cursor(dictionary=True)
    q        = "SELECT * FROM blogs WHERE 1=1"
    params   = []
    if search:
        q += " AND title LIKE %s"
        params.append(f'%{search}%')
    if category:
        q += " AND category = %s"
        params.append(category)
    q += " ORDER BY created_at DESC"
    cursor.execute(q, params)
    rows = cursor.fetchall()
    db.close()
    result = []
    for r in rows:
        d = row_to_dict(r)
        d['tags'] = json.loads(d.get('tags') or '[]')
        result.append(d)
    return jsonify(result)

# ─────────────────────────────────────────
# GET SINGLE BLOG
# ─────────────────────────────────────────
@app.route('/api/blogs/<int:id>', methods=['GET'])
def get_blog(id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM blogs WHERE id=%s", (id,))
    row = cursor.fetchone()
    db.close()
    if not row:
        return jsonify({'error': 'Blog not found'}), 404
    d = row_to_dict(row)
    d['tags'] = json.loads(d.get('tags') or '[]')
    return jsonify(d)

# ─────────────────────────────────────────
# DELETE BLOG
# ─────────────────────────────────────────
@app.route('/api/blogs/<int:id>', methods=['DELETE'])
def delete_blog(id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM blogs WHERE id=%s", (id,))
    db.commit()
    db.close()
    return jsonify({'message': 'Blog deleted!'})

# ─────────────────────────────────────────
# STATS
# ─────────────────────────────────────────
@app.route('/api/stats', methods=['GET'])
def get_stats():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT COUNT(*)          as total,
               SUM(word_count)   as total_words,
               AVG(word_count)   as avg_words,
               SUM(read_time)    as total_read
        FROM blogs
    """)
    row = cursor.fetchone()
    cursor.execute("SELECT COUNT(DISTINCT category) as cats FROM blogs")
    cats = cursor.fetchone()['cats']
    db.close()
    return jsonify({
        'total_blogs':  row['total']       or 0,
        'total_words':  int(row['total_words'] or 0),
        'avg_words':    round(float(row['avg_words'] or 0), 1),
        'total_read':   int(row['total_read']  or 0),
        'categories':   cats
    })

# ─────────────────────────────────────────
# IMPROVE TEXT — Groq rewrites a section
# ─────────────────────────────────────────
@app.route('/api/improve', methods=['POST'])
def improve_text():
    data        = request.json
    text        = data.get('text', '').strip()
    instruction = data.get('instruction', 'improve the writing quality and clarity')
    if not text:
        return jsonify({'error': 'Text is required'}), 400
    try:
        improved = call_groq(
            f"Please {instruction}. Return ONLY the improved text, no explanations:\n\n{text}"
        )
        return jsonify({'improved': improved})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─────────────────────────────────────────
# SUGGEST TITLES — Groq suggests 5 titles
# ─────────────────────────────────────────
@app.route('/api/suggest-titles', methods=['POST'])
def suggest_titles():
    data  = request.json
    topic = data.get('topic', '').strip()
    if not topic:
        return jsonify({'error': 'Topic required'}), 400
    try:
        raw = call_groq(
            f"Suggest 5 compelling, click-worthy blog titles for this topic: {topic}\n\nReturn ONLY a numbered list of 5 titles, nothing else."
        )
        titles = [
            re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            for line in raw.strip().split('\n')
            if line.strip()
        ][:5]
        return jsonify({'titles': titles})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)

# Flask → your backend framework
# flask-cors → connect frontend (JS) with backend
# mysql-connector-python → MySQL database connection
# requests → calling Groq API
# python-dotenv → load .env file (for API key)
# gunicorn → needed for deployment (PythonAnywhere / production)