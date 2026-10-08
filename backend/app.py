import sqlite3
import os
import re
import jwt
import bcrypt
import requests
import uuid
import json
import logging
import concurrent.futures
from urllib.parse import quote_plus
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
os.environ.setdefault('FLASK_DEBUG', '0')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('techhub')

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

SOURCE_CONFIG = {
    'Gemini':         {'key': os.getenv('GROQ_KEY_OVERVIEW') or os.getenv('GROQ_API_KEY', ''),
                       'model': os.getenv('GROQ_MODEL_OVERVIEW') or os.getenv('GROQ_MODEL', 'openai/gpt-oss-120b')},
    'Google':         {'key': os.getenv('GROQ_KEY_GOOGLE') or os.getenv('GROQ_API_KEY', ''),
                       'model': os.getenv('GROQ_MODEL_GOOGLE') or os.getenv('GROQ_MODEL', 'openai/gpt-oss-20b')},
    'YouTube':        {'key': os.getenv('GROQ_KEY_YOUTUBE') or os.getenv('GROQ_API_KEY', ''),
                       'model': os.getenv('GROQ_MODEL_YOUTUBE') or os.getenv('GROQ_MODEL', 'openai/gpt-oss-20b')},
    'Stack Overflow': {'key': os.getenv('GROQ_KEY_SO') or os.getenv('GROQ_API_KEY', ''),
                       'model': os.getenv('GROQ_MODEL_SO') or os.getenv('GROQ_MODEL', 'openai/gpt-oss-20b')},
    'GitHub':         {'key': os.getenv('GROQ_KEY_GITHUB') or os.getenv('GROQ_API_KEY', ''),
                       'model': os.getenv('GROQ_MODEL_GITHUB') or os.getenv('GROQ_MODEL', 'openai/gpt-oss-20b')},
    'Wikipedia':      {'key': os.getenv('GROQ_KEY_WIKI') or os.getenv('GROQ_API_KEY', ''),
                       'model': os.getenv('GROQ_MODEL_WIKI') or os.getenv('GROQ_MODEL', 'openai/gpt-oss-20b')},
    'Dev.to':         {'key': os.getenv('GROQ_KEY_DEVTO') or os.getenv('GROQ_API_KEY', ''),
                       'model': os.getenv('GROQ_MODEL_DEVTO') or os.getenv('GROQ_MODEL', 'openai/gpt-oss-20b')},
    'Reddit':         {'key': os.getenv('GROQ_KEY_REDDIT') or os.getenv('GROQ_API_KEY', ''),
                       'model': os.getenv('GROQ_MODEL_REDDIT') or os.getenv('GROQ_MODEL', 'openai/gpt-oss-20b')},
}

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'techhub.db')
SECRET_KEY = os.getenv('SECRET_KEY', 'techhub-dev-secret-change-me')

MAX_ANSWER_SIZE = 20000
GROQ_TIMEOUT = 25
OVERVIEW_TIMEOUT = 30

ALL_SOURCES = ['Google', 'YouTube', 'Stack Overflow', 'GitHub',
               'Wikipedia', 'Dev.to', 'Reddit']

SOURCE_META = {
    'Gemini':         {'trust': 9, 'confidence': 0.90, 'reliability': 'Very High'},
    'Google':         {'trust': 7, 'confidence': 0.70, 'reliability': 'Good'},
    'YouTube':        {'trust': 6, 'confidence': 0.60, 'reliability': 'Good'},
    'Stack Overflow': {'trust': 9, 'confidence': 0.85, 'reliability': 'Very High'},
    'GitHub':         {'trust': 8, 'confidence': 0.75, 'reliability': 'High'},
    'Wikipedia':      {'trust': 8, 'confidence': 0.75, 'reliability': 'High'},
    'Dev.to':         {'trust': 7, 'confidence': 0.60, 'reliability': 'Good'},
    'Reddit':         {'trust': 7, 'confidence': 0.55, 'reliability': 'Good'},
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'User', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, query TEXT,
            topic TEXT, sources_used TEXT, results_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)''')
        c.execute('''CREATE TABLE IF NOT EXISTS saved_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, query_id TEXT,
            source TEXT, answer TEXT, url TEXT, confidence REAL,
            saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)''')
        c.execute("PRAGMA table_info(users)")
        cols = [r[1] for r in c.fetchall()]
        if 'role' not in cols:
            c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'User'")
        conn.commit()
        conn.close()
        logger.info("Database initialized")
    except Exception as e:
        logger.exception("init_db: %s", e)


init_db()


def hash_password(p):
    return bcrypt.hashpw(p.encode('utf-8'), bcrypt.gensalt())


def verify_password(p, h):
    try:
        if isinstance(h, str): h = h.encode('utf-8')
        return bcrypt.checkpw(p.encode('utf-8'), h)
    except Exception:
        return False


def make_token(uid, email):
    return jwt.encode(
        {'user_id': uid, 'email': email,
         'exp': datetime.now(timezone.utc) + timedelta(hours=24)},
        SECRET_KEY, algorithm='HS256')


def verify_token(t):
    if not t: return None
    try:
        return jwt.decode(t, SECRET_KEY, algorithms=['HS256'])['user_id']
    except Exception:
        return None


def current_user_id():
    t = request.headers.get('Authorization', '').replace('Bearer ', '').strip()
    return verify_token(t)


EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def validate_register(d):
    name = (d.get('name') or '').strip()
    email = (d.get('email') or '').strip()
    pwd = d.get('password') or ''
    if len(name) < 3: return 'Name must be at least 3 characters'
    if len(name) > 80: return 'Name too long'
    if not EMAIL_RE.match(email): return 'Invalid email'
    if len(pwd) < 6: return 'Password must be at least 6 characters'
    if len(pwd) > 128: return 'Password too long'
    return None


def is_query_meaningful(q):
    q = q.strip().lower()
    if len(q) < 3: return False
    if len(set(q)) <= 2: return False
    if len(re.findall(r'[a-z]', q)) < 2: return False
    return True


TOPICS = {
    'python': ['python', 'pandas', 'numpy', 'flask', 'django', 'pip'],
    'javascript': ['javascript', 'js', 'node', 'react', 'vue', 'typescript'],
    'java': ['java', 'spring', 'maven', 'gradle', 'kotlin'],
    'git': ['git', 'commit', 'branch', 'merge', 'github'],
    'sql': ['sql', 'mysql', 'postgresql', 'query', 'select', 'join'],
    'docker': ['docker', 'container'],
    'kubernetes': ['kubernetes', 'k8s', 'kubectl'],
    'html_css': ['html', 'css', 'flexbox', 'grid', 'bootstrap'],
    'machine_learning': ['machine learning', 'ml', 'tensorflow', 'pytorch'],
    'cybersecurity': ['security', 'encryption', 'firewall'],
    'linux': ['linux', 'ubuntu', 'bash', 'shell'],
    'blockchain': ['blockchain', 'bitcoin', 'ethereum', 'solidity'],
    'aws': ['aws', 'ec2', 's3', 'lambda'],
    'android': ['android', 'apk', 'gradle'],
    'ios': ['ios', 'swift', 'swiftui', 'xcode'],
    'devops': ['devops', 'ci/cd', 'jenkins', 'terraform'],
}


def detect_topic(q):
    q_lower = q.lower()
    words = q_lower.split()
    scores = {}
    for topic, kws in TOPICS.items():
        s = 0
        for kw in kws:
            if ' ' in kw:
                if kw in q_lower: s += 2
            else:
                if kw in words: s += 2
                elif kw in q_lower: s += 1
        if s: scores[topic] = s
    return max(scores, key=scores.get) if scores else 'general'


def groq(source, prompt, max_tokens=500, temperature=0.4, timeout=GROQ_TIMEOUT):
    cfg = SOURCE_CONFIG.get(source, {})
    key = cfg.get('key') or os.getenv('GROQ_API_KEY', '')
    model = cfg.get('model') or 'openai/gpt-oss-20b'
    if not key:
        logger.warning("No key for %s", source)
        return None
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={"model": model,
                  "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": max_tokens, "temperature": temperature},
            timeout=timeout)
        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content']
        logger.warning("%s %s: %s", source, r.status_code, r.text[:150])
        return None
    except Exception as e:
        logger.warning("%s: %s", source, e)
        return None


def build_search_url(source, title):
    q = quote_plus((title or '')[:200])
    return {
        'Google':         f"https://www.google.com/search?q={q}",
        'YouTube':        f"https://www.youtube.com/results?search_query={q}",
        'Stack Overflow': f"https://stackoverflow.com/search?q={q}",
        'GitHub':         f"https://github.com/search?q={q}",
        'Wikipedia':      f"https://en.wikipedia.org/w/index.php?search={q}",
        'Dev.to':         f"https://dev.to/search?q={q}",
        'Reddit':         f"https://www.reddit.com/search/?q={q}",
    }.get(source, f"https://www.google.com/search?q={q}")


def ask_gemini(query, topic):
    prompt = f"""You are TechHub, an expert technical assistant.

Answer this question directly and completely:
"{query}"

Rules:
- Give a clear, correct, complete answer
- Include a short code example if relevant (use markdown code block)
- Maximum 300 words
- Do NOT say "I'm ready to help" — just answer"""
    return groq('Gemini', prompt, max_tokens=600, temperature=0.3, timeout=OVERVIEW_TIMEOUT)


SOURCE_PROMPTS = {
    'Google': """Simulate the top 3 Google search results for: "{query}"

Format each result EXACTLY like this:

TITLE: <realistic page title>
SNIPPET: <2 sentence description>

Rules:
- Exactly 3 results
- Titles should look like real pages (official docs, tutorials, popular blogs)
- No URLs, no commentary, no markdown""",

    'YouTube': """Simulate the top 3 YouTube videos for: "{query}"

Format each EXACTLY:

TITLE: <realistic video title>
SNIPPET: <1 sentence description>

Rules:
- Exactly 3 results
- Prefer channels: Fireship, Traversy Media, Corey Schafer, freeCodeCamp, Programming with Mosh, Net Ninja
- No commentary""",

    'Stack Overflow': """Simulate the top 3 Stack Overflow questions for: "{query}"

Format each EXACTLY:

TITLE: <realistic question title>
SNIPPET: <2 sentence summary of the answer>

Rules:
- Exactly 3 results
- Titles should read like real SO questions
- No commentary""",

    'GitHub': """Simulate the top 3 GitHub repositories for: "{query}"

Format each EXACTLY:

TITLE: <owner/repo-name>
SNIPPET: <2 sentence description>

Rules:
- Exactly 3 results
- Realistic repo names
- No commentary""",

    'Wikipedia': """Simulate the top 3 Wikipedia articles for: "{query}"

Format each EXACTLY:

TITLE: <article title>
SNIPPET: <2 sentence summary>

Rules:
- Exactly 3 results
- Choose the closest encyclopedic articles
- No commentary""",

    'Dev.to': """Simulate the top 3 Dev.to articles for: "{query}"

Format each EXACTLY:

TITLE: <realistic article title>
SNIPPET: <2 sentence summary>

Rules:
- Exactly 3 results
- Realistic Dev.to article titles
- No commentary""",

    'Reddit': """Simulate the top 3 Reddit posts for: "{query}"

Format each EXACTLY:

TITLE: <realistic post title>
SNIPPET: <2 sentence discussion summary>

Rules:
- Exactly 3 results
- Realistic subreddits (r/learnpython, r/javascript, r/webdev, r/programming)
- No commentary""",
}


def get_source_results(source, query):
    tpl = SOURCE_PROMPTS.get(source)
    if not tpl:
        return []

    text = groq(source, tpl.format(query=query), max_tokens=500, temperature=0.4)
    meta = SOURCE_META.get(source, {})
    results = []

    if text:
        for block in re.split(r'\n(?=TITLE:)', text.strip()):
            title = _field(block, 'TITLE')
            snippet = _field(block, 'SNIPPET')
            if not title or len(title) < 5:
                continue
            results.append({
                'source': source,
                'title': title[:200],
                'body': (snippet or title)[:300],
                'url': build_search_url(source, title),
                'confidence': meta.get('confidence', 0.6),
                'trust_score': meta.get('trust', 6),
                'reliability': meta.get('reliability', 'Good'),
                'date': datetime.now().strftime('%Y-%m-%d'),
            })
            if len(results) >= 3:
                break

    if not results:
        fallback_title = f"{query[:80]} — {source}"
        results.append({
            'source': source,
            'title': fallback_title,
            'body': f"Search {source} for more on this topic.",
            'url': build_search_url(source, query),
            'confidence': meta.get('confidence', 0.6),
            'trust_score': meta.get('trust', 6),
            'reliability': meta.get('reliability', 'Good'),
            'date': datetime.now().strftime('%Y-%m-%d'),
        })
    return results


def _field(text, name):
    m = re.search(rf'{name}:\s*(.+)', text, re.IGNORECASE)
    return m.group(1).strip() if m else ''


def search_all_sources(query):
    topic = detect_topic(query)
    results = []
    sources_found = []
    gemini_text = None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {}
        futures[ex.submit(ask_gemini, query, topic)] = 'Gemini'
        for s in ALL_SOURCES:
            futures[ex.submit(get_source_results, s, query)] = s

        for fut in concurrent.futures.as_completed(futures):
            name = futures[fut]
            try:
                out = fut.result(timeout=GROQ_TIMEOUT + 5)
            except Exception as e:
                logger.warning("%s failed: %s", name, e)
                continue
            if not out:
                continue

            if name == 'Gemini':
                gemini_text = out
                sources_found.append('Gemini')
                logger.info("Gemini: %d chars", len(out))
            else:
                sources_found.append(name)
                results.extend(out)
                logger.info("%s: %d results", name, len(out))

    final = []
    if gemini_text:
        final.append({
            'source': 'Gemini',
            'title': 'Gemini Answer',
            'body': gemini_text,
            'url': '',
            'confidence': 0.90,
            'trust_score': 9,
            'reliability': 'Very High',
            'date': datetime.now().strftime('%Y-%m-%d'),
        })

    results.sort(key=lambda x: x.get('confidence', 0), reverse=True)
    final.extend(results)
    return final, sources_found


def detect_consensus(answers):
    empty = {'consensus': [], 'minority': [], 'conflicts': [], 'recommendation': ''}
    if not answers:
        return {**empty, 'recommendation': 'No answers to compare'}
    if len(answers) < 2:
        return {**empty, 'recommendation': 'Only 1 result'}

    top = answers[:10]
    numbered = ""
    for i, a in enumerate(top):
        numbered += f"[{i}] {a.get('source', '')}: {(a.get('title') or '')[:100]}\n"
        numbered += f"    {(a.get('body') or '')[:180]}\n"

    prompt = f"""Group these results by what they recommend.

{numbered}

Return ONLY this JSON:
{{"groups": [{{"claim": "summary", "indices": [0, 2]}}], "recommendation": "one sentence"}}

Sort by group size (largest first). No markdown."""

    try:
        text = groq('Gemini', prompt, max_tokens=400, temperature=0.1, timeout=15)
        if not text:
            return {**empty, 'recommendation': 'Consensus unavailable'}

        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            return {**empty, 'recommendation': 'Consensus unavailable'}

        parsed = json.loads(match.group())
        groups = parsed.get('groups', [])
        rec = (parsed.get('recommendation') or '').strip()

        consensus, minority = [], []
        for g in groups:
            idxs = g.get('indices', [])
            claim = (g.get('claim') or '').strip()
            if not claim or not idxs: continue
            sources = []
            for idx in idxs:
                if 0 <= idx < len(top):
                    src = top[idx].get('source', '')
                    if src and src not in sources:
                        sources.append(src)
            entry = {'claim': claim, 'sources': sources,
                     'count': len(sources), 'evidence_count': len(idxs)}
            if len(sources) >= 2:
                consensus.append(entry)
            else:
                minority.append(entry)

        if not consensus and minority:
            minority.sort(key=lambda x: x['count'], reverse=True)
            consensus = [minority.pop(0)]

        if not rec and consensus:
            rec = f"Most sources ({consensus[0]['count']}) agree: {consensus[0]['claim']}"

        return {'consensus': consensus, 'minority': minority,
                'conflicts': [], 'recommendation': rec}
    except Exception as e:
        logger.warning("Consensus failed: %s", e)
        return {**empty, 'recommendation': 'Consensus unavailable'}


@app.route('/')
def serve_index(): return send_from_directory('../frontend', 'index.html')


@app.route('/<path:path>')
def serve_frontend(path):
    if os.path.exists(os.path.join('../frontend', path)):
        return send_from_directory('../frontend', path)
    return send_from_directory('../frontend', 'index.html')


@app.route('/api/health')
def health(): return jsonify({'status': 'healthy'})


@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    err = validate_register(data)
    if err: return jsonify({'success': False, 'error': err}), 400
    name = data['name'].strip()
    email = data['email'].strip().lower()
    password = data['password']
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT id FROM users WHERE email = ?', (email,))
        if c.fetchone():
            return jsonify({'success': False, 'error': 'Email already registered'}), 400
        c.execute('INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
                  (name, email, hash_password(password)))
        conn.commit()
        return jsonify({'success': True, 'message': 'Registration successful'}), 201
    finally:
        conn.close()


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and password required'}), 400
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = c.fetchone()
    finally:
        conn.close()
    if not user or not verify_password(password, user['password_hash']):
        return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
    return jsonify({
        'success': True,
        'token': make_token(user['id'], user['email']),
        'user': {'id': user['id'], 'name': user['name'], 'email': user['email']},
    })


@app.route('/api/search', methods=['POST'])
def search():
    data = request.get_json(silent=True) or {}
    query = (data.get('query') or '').strip()
    if not query: return jsonify({'success': False, 'error': 'Please enter a question'}), 400
    if len(query) > 500: return jsonify({'success': False, 'error': 'Query too long'}), 400

    try:
        if not is_query_meaningful(query):
            return jsonify({
                'success': True, 'query_id': str(uuid.uuid4())[:8],
                'query': query, 'topic': 'general',
                'sources_searched': [], 'answers': [],
                'comparison': {'total_sources': 0, 'avg_confidence': 0,
                               'consensus': [], 'minority': [], 'conflicts': [],
                               'consensus_recommendation': 'Query too short or unclear.'},
            })

        topic = detect_topic(query)
        answers, sources_searched = search_all_sources(query)

        source_answers = [a for a in answers if a.get('source') != 'Gemini']
        source_answers.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        avg_conf = (sum(a.get('confidence', 0.5) for a in source_answers) /
                    len(source_answers)) if source_answers else 0

        consensus_result = detect_consensus(source_answers)

        comparison = {
            'total_sources': len(sources_searched),
            'avg_confidence': round(avg_conf, 2),
            'consensus': consensus_result['consensus'],
            'minority': consensus_result['minority'],
            'conflicts': consensus_result['conflicts'],
            'consensus_recommendation': consensus_result['recommendation'],
        }

        query_id = str(uuid.uuid4())[:8]

        user_id = current_user_id()
        if user_id:
            try:
                conn = get_db()
                try:
                    c = conn.cursor()
                    c.execute('INSERT INTO search_history '
                              '(user_id, query, topic, sources_used, results_count) '
                              'VALUES (?, ?, ?, ?, ?)',
                              (user_id, query, topic,
                               ','.join(sources_searched), len(answers)))
                    conn.commit()
                finally:
                    conn.close()
            except Exception as e:
                logger.warning("History save error: %s", e)

        return jsonify({
            'success': True, 'query_id': query_id, 'query': query,
            'topic': topic, 'sources_searched': sources_searched,
            'answers': answers, 'comparison': comparison,
        })
    except Exception as e:
        logger.exception("Search failed: %s", e)
        return jsonify({'success': False, 'error': 'Search failed.'}), 500


@app.route('/api/related', methods=['POST'])
def related():
    req = request.get_json(silent=True) or {}
    query = (req.get('query') or '').strip()
    if not query: return jsonify({'success': True, 'questions': []})
    prompt = f"Generate 5 related technical questions for: {query}. Return as numbered list 1-5."
    text = groq('Gemini', prompt, max_tokens=200, temperature=0.5, timeout=15)
    questions = re.findall(r'\d+\.\s*(.+)', text or '')[:5]
    return jsonify({'success': True, 'questions': questions})


@app.route('/api/sources/trust', methods=['GET'])
def get_source_trust(): return jsonify({'success': True, 'sources': SOURCE_META})


@app.route('/api/history', methods=['GET'])
def get_history():
    user_id = current_user_id()
    if not user_id: return jsonify({'success': False, 'error': 'Please login'}), 401
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM search_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 50',
                  (user_id,))
        history = [dict(row) for row in c.fetchall()]
    finally:
        conn.close()
    return jsonify({'success': True, 'history': history})


@app.route('/api/history/save', methods=['POST'])
def save_answer():
    user_id = current_user_id()
    if not user_id: return jsonify({'success': False, 'error': 'Please login'}), 401
    data = request.get_json(silent=True) or {}
    source = (data.get('source') or '').strip()[:100]
    answer = (data.get('answer') or '')[:MAX_ANSWER_SIZE]
    url = (data.get('url') or '').strip()[:2000]
    query_id = (data.get('query_id') or '').strip()[:100]
    try: confidence = float(data.get('confidence', 0.5))
    except (TypeError, ValueError): confidence = 0.5
    if not source: return jsonify({'success': False, 'error': 'Source is required'}), 400
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('INSERT INTO saved_answers '
                  '(user_id, query_id, source, answer, url, confidence) '
                  'VALUES (?, ?, ?, ?, ?, ?)',
                  (user_id, query_id, source, answer, url, confidence))
        conn.commit()
    finally:
        conn.close()
    return jsonify({'success': True, 'message': 'Saved'})


@app.route('/api/saved', methods=['GET'])
def get_saved():
    user_id = current_user_id()
    if not user_id: return jsonify({'success': False, 'error': 'Please login'}), 401
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM saved_answers WHERE user_id = ? ORDER BY saved_at DESC',
                  (user_id,))
        saved = [dict(row) for row in c.fetchall()]
    finally:
        conn.close()
    return jsonify({'success': True, 'saved': saved})


@app.route('/api/profile', methods=['GET'])
def get_profile():
    user_id = current_user_id()
    if not user_id: return jsonify({'success': False, 'error': 'Please login'}), 401
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = c.fetchone()
        if not user: return jsonify({'success': False, 'error': 'User not found'}), 404
        c.execute('SELECT COUNT(*) AS n FROM search_history WHERE user_id = ?', (user_id,))
        searches = c.fetchone()['n']
        c.execute('SELECT COUNT(*) AS n FROM saved_answers WHERE user_id = ?', (user_id,))
        saves = c.fetchone()['n']
    finally:
        conn.close()
    user_data = dict(user)
    user_data.pop('password_hash', None)
    user_data['search_count'] = searches
    user_data['saved_count'] = saves
    return jsonify({'success': True, 'user': user_data})


@app.route('/api/profile/update', methods=['PUT'])
def update_profile():
    user_id = current_user_id()
    if not user_id: return jsonify({'success': False, 'error': 'Please login'}), 401
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    if name and (len(name) < 3 or len(name) > 80):
        return jsonify({'success': False, 'error': 'Name must be 3-80 characters'}), 400
    if email and not EMAIL_RE.match(email):
        return jsonify({'success': False, 'error': 'Invalid email'}), 400
    if not name and not email:
        return jsonify({'success': False, 'error': 'Nothing to update'}), 400
    conn = get_db()
    try:
        c = conn.cursor()
        if email:
            c.execute('SELECT id FROM users WHERE email = ? AND id != ?', (email, user_id))
            if c.fetchone():
                return jsonify({'success': False, 'error': 'Email already in use'}), 400
        fields, values = [], []
        if name: fields.append('name = ?'); values.append(name)
        if email: fields.append('email = ?'); values.append(email)
        values.append(user_id)
        c.execute(f'UPDATE users SET {", ".join(fields)} WHERE id = ?', values)
        conn.commit()
        c.execute('SELECT id, name, email, created_at FROM users WHERE id = ?', (user_id,))
        return jsonify({'success': True, 'user': dict(c.fetchone()), 'message': 'Profile updated'})
    finally:
        conn.close()


@app.route('/api/profile/password', methods=['PUT'])
def change_password():
    user_id = current_user_id()
    if not user_id: return jsonify({'success': False, 'error': 'Please login'}), 401
    data = request.get_json(silent=True) or {}
    curr = data.get('current_password') or ''
    new = data.get('new_password') or ''
    if not curr or not new: return jsonify({'success': False, 'error': 'All fields are required'}), 400
    if len(new) < 6: return jsonify({'success': False, 'error': 'New password must be at least 6 characters'}), 400
    if curr == new: return jsonify({'success': False, 'error': 'New password must be different'}), 400
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT password_hash FROM users WHERE id = ?', (user_id,))
        row = c.fetchone()
        if not row: return jsonify({'success': False, 'error': 'User not found'}), 404
        if not verify_password(curr, row['password_hash']):
            return jsonify({'success': False, 'error': 'Current password is incorrect'}), 401
        c.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                  (hash_password(new), user_id))
        conn.commit()
        return jsonify({'success': True, 'message': 'Password changed'})
    finally:
        conn.close()


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Endpoint not found'}), 404
    return send_from_directory('../frontend', 'index.html')


@app.errorhandler(500)
def server_error(e):
    logger.exception("Unhandled server error")
    return jsonify({'success': False, 'error': 'Internal server error'}), 500


if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', '0') == '1'
    port = int(os.getenv('PORT', 5000))
    app.run(debug=debug_mode, host='0.0.0.0', port=port)