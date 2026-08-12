import sqlite3
import os
import re
import jwt
import bcrypt
import requests
import uuid
import concurrent.futures
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from bs4 import BeautifulSoup

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

GEMINI_API_KEY = "AQ.Ab8RN6L_7S7LFHbXGPYavCaVG9Ry5yWu_qk2LgMnkEeUkBza5g"
GEMINI_MODEL = "gemini-flash-latest"
GOOGLE_API_KEY = "AIzaSyAqb9g7ZolRsJckqOAjXiZL059brW5q00Q"
GOOGLE_CX = "e2feda9a33c5442fc"
YOUTUBE_API_KEY = "AIzaSyBkvTlQmeEeKsHsJtiYzpDSfJd8S1sJefo"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'users.db')
SECRET_KEY = "techhub-secret-2026"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

SOURCE_TRUST = {
    'Gemini AI': {'score': 9, 'reliability': 'Very High'},
    'Google Search': {'score': 7, 'reliability': 'Good'},
    'Stack Overflow': {'score': 9, 'reliability': 'Very High'},
    'GitHub': {'score': 8, 'reliability': 'High'},
    'Wikipedia': {'score': 8, 'reliability': 'High'},
    'Dev.to': {'score': 7, 'reliability': 'Good'},
    'Reddit': {'score': 5, 'reliability': 'Medium'},
    'YouTube': {'score': 6, 'reliability': 'Good'}
}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS search_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, query TEXT, topic TEXT, sources_used TEXT, results_count INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS saved_answers (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, query_id TEXT, source TEXT, answer TEXT, url TEXT, confidence REAL, saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        conn.close()
    except:
        pass

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def verify_password(password, password_hash):
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash)
    except:
        return False

def generate_token(user_id, email):
    payload = {'user_id': user_id, 'email': email, 'exp': datetime.utcnow() + timedelta(hours=24)}
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return {'success': True, 'user_id': payload['user_id']}
    except:
        return {'success': False}

def detect_topic(query):
    q = query.lower()
    topics = {
        'python': ['python', 'pandas', 'flask', 'django', 'pip', 'csv', 'numpy'],
        'javascript': ['javascript', 'js', 'node', 'react', 'vue', 'npm', 'dom', 'callback'],
        'java': ['java', 'spring', 'maven', 'kotlin', 'hibernate'],
        'c_cpp': ['c++', 'cpp', 'gcc', 'pointer', 'cmake'],
        'git': ['git', 'commit', 'branch', 'merge', 'rebase', 'repo', 'push', 'pull', 'clone'],
        'sql': ['sql', 'mysql', 'postgresql', 'query', 'join', 'table'],
        'docker': ['docker', 'container', 'image', 'compose'],
        'kubernetes': ['kubernetes', 'k8s', 'pod', 'deployment', 'helm'],
        'html': ['html', 'div', 'span', 'form', 'table'],
        'css': ['css', 'flexbox', 'grid', 'bootstrap', 'tailwind', 'margin'],
        'machine_learning': ['machine learning', 'ml', 'tensorflow', 'pytorch', 'model'],
        'cybersecurity': ['security', 'encryption', 'firewall', 'vpn', 'malware'],
        'linux': ['linux', 'ubuntu', 'bash', 'shell', 'terminal'],
        'blockchain': ['blockchain', 'bitcoin', 'ethereum', 'solidity', 'web3']
    }
    for topic, kws in topics.items():
        if any(kw in q for kw in kws):
            return topic
    return 'general'

def calculate_confidence(source, score=0, stars=0):
    base = {'Gemini AI': 0.90, 'Google Search': 0.60, 'Stack Overflow': 0.60, 'GitHub': 0.55, 'Wikipedia': 0.70, 'Dev.to': 0.60, 'Reddit': 0.40, 'YouTube': 0.50}
    conf = base.get(source, 0.5)
    if source == 'Stack Overflow':
        conf += min(score / 500, 0.2)
    elif source == 'GitHub':
        conf += min(stars / 10000, 0.2)
    return min(conf, 0.95)

def ask_gemini(query):
    """Uses Groq (free, fast) - shows as Gemini AI"""
    GROQ_API_KEY = "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"
    
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            'Authorization': f'Bearer {GROQ_API_KEY}',
            'Content-Type': 'application/json'
        }
        data = {
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": f"Answer this technical question clearly with code examples: {query}"}],
            "max_tokens": 500
        }
        r = requests.post(url, headers=headers, json=data, timeout=20)
        
        print(f"AI status: {r.status_code}")
        
        if r.status_code == 200:
            return r.json()['choices'][0]['message']['content']
        return None
    except Exception as e:
        print(f"AI error: {e}")
        return None

def search_google(query, limit=5):
    """Uses DuckDuckGo + Bing - removes duplicates"""
    results = []
    seen_urls = set()
    
    # Try DuckDuckGo first
    try:
        url = "https://api.duckduckgo.com/"
        params = {'q': query, 'format': 'json', 'no_html': 1}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get('AbstractText'):
                abstract_url = data.get('AbstractURL', '')
                if abstract_url not in seen_urls:
                    seen_urls.add(abstract_url)
                    results.append({
                        'source': 'Google Search',
                        'title': data.get('Heading', query),
                        'body': data.get('AbstractText', '')[:200],
                        'url': abstract_url,
                        'confidence': 0.70,
                        'trust_score': 7,
                        'reliability': 'High',
                        'date': ''
                    })
            for topic in data.get('RelatedTopics', []):
                if isinstance(topic, dict) and 'Text' in topic:
                    topic_url = topic.get('FirstURL', '')
                    if topic_url not in seen_urls:
                        seen_urls.add(topic_url)
                        results.append({
                            'source': 'Google Search',
                            'title': topic.get('Text', '')[:100],
                            'body': topic.get('Text', '')[:200],
                            'url': topic_url,
                            'confidence': 0.55,
                            'trust_score': 6,
                            'reliability': 'Good',
                            'date': ''
                        })
                if len(results) >= limit:
                    break
    except:
        pass
    
    # Try Bing if DuckDuckGo returns nothing
    if not results:
        try:
            url = f"https://www.bing.com/search?q={query}"
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                for item in soup.find_all('li', class_='b_algo'):
                    title_elem = item.find('h2')
                    link_elem = item.find('a')
                    snippet = item.find('p')
                    if title_elem and link_elem:
                        link = link_elem.get('href', '')
                        if link not in seen_urls:
                            seen_urls.add(link)
                            results.append({
                                'source': 'Google Search',
                                'title': title_elem.get_text(strip=True),
                                'body': snippet.get_text(strip=True)[:200] if snippet else '',
                                'url': link,
                                'confidence': 0.65,
                                'trust_score': 7,
                                'reliability': 'Good',
                                'date': ''
                            })
                    if len(results) >= limit:
                        break
        except:
            pass
    
    return results[:limit]
def search_youtube(query, limit=3):
    try:
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {'q': query, 'key': YOUTUBE_API_KEY, 'part': 'snippet', 'type': 'video', 'maxResults': limit}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            results = []
            for i in r.json().get('items', []):
                vid = i.get('id', {}).get('videoId', '')
                results.append({'source': 'YouTube', 'title': i.get('snippet',{}).get('title',''), 'body': i.get('snippet',{}).get('description','')[:150], 'url': f'https://youtube.com/watch?v={vid}', 'confidence': 0.50, 'trust_score': 6, 'reliability': 'Good', 'date': i.get('snippet',{}).get('publishedAt','')[:10]})
            return results
    except Exception as e:
        print(f"YouTube: {e}")
    return []

def search_stackoverflow(query, limit=5):
    try:
        url = "https://api.stackexchange.com/2.3/search/advanced"
        params = {'q': query, 'site': 'stackoverflow', 'pagesize': limit, 'order': 'desc', 'sort': 'relevance', 'filter': 'withbody', 'answers': 1}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            results = []
            seen = set()
            for i in r.json().get('items', []):
                link = i.get('link', '')
                if link in seen:
                    continue
                seen.add(link)
                score = i.get('score', 0)
                results.append({
                    'source': 'Stack Overflow',
                    'title': i.get('title', ''),
                    'body': re.sub(r'<[^>]+>', '', i.get('body', ''))[:200],
                    'url': link,
                    'score': score,
                    'confidence': calculate_confidence('Stack Overflow', score=score),
                    'trust_score': 9,
                    'reliability': 'Very High',
                    'date': datetime.fromtimestamp(i.get('creation_date', 0)).strftime('%Y-%m-%d')
                })
            return results
    except Exception as e:
        print(f"SO: {e}")
    return []
def search_github(query, limit=3):
    try:
        url = "https://api.github.com/search/repositories"
        params = {'q': query, 'sort': 'stars', 'per_page': 10}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            results = []
            qwords = [w.lower() for w in query.split() if len(w) > 3]
            for i in r.json().get('items', []):
                stars = i.get('stargazers_count', 0)
                desc = (i.get('description') or '').lower()
                name = (i.get('full_name') or '').lower()
                combined = name + ' ' + desc
                matches = sum(1 for w in qwords if w in combined)
                if matches >= 2 and stars > 100:
                    results.append({'source': 'GitHub', 'title': i.get('full_name',''), 'body': (i.get('description') or 'No description')[:200], 'url': i.get('html_url',''), 'stars': stars, 'confidence': calculate_confidence('GitHub', stars=stars), 'trust_score': 8, 'reliability': 'High', 'date': i.get('updated_at','')[:10]})
                if len(results) >= limit:
                    break
            return results
    except Exception as e:
        print(f"GH: {e}")
    return []
def search_wikipedia(query, limit=3):
    try:
        term = query.split()[0] if query.split() else query
        
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            'action': 'query',
            'list': 'search',
            'srsearch': term,
            'format': 'json',
            'srlimit': limit
        }
        
        # Add proper User-Agent - Wikipedia requires this
        wiki_headers = {
            'User-Agent': 'TechHub/1.0 (https://techhub.example.com; contact@techhub.example.com)'
        }
        
        r = requests.get(url, params=params, headers=wiki_headers, timeout=15)
        
        print(f"Wikipedia status: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            search_results = data.get('query', {}).get('search', [])
            print(f"Wikipedia found: {len(search_results)} results")
            
            results = []
            for item in search_results:
                title = item.get('title', '')
                snippet = item.get('snippet', '')
                clean_snippet = re.sub(r'<[^>]+>', '', snippet)
                timestamp = item.get('timestamp', '')
                
                results.append({
                    'source': 'Wikipedia',
                    'title': title,
                    'body': clean_snippet[:200],
                    'url': f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    'confidence': 0.70,
                    'trust_score': 8,
                    'reliability': 'High',
                    'date': timestamp[:10]
                })
            
            return results
        
        return []
    except Exception as e:
        print(f"Wiki error: {e}")
        return []
def search_devto(query, limit=3):
    try:
        topic = detect_topic(query)
        tag = topic if topic != 'general' else 'programming'
        
        # Search by tag
        url = f"https://dev.to/api/articles?tag={tag}&per_page={limit}"
        r = requests.get(url, timeout=10)
        
        if r.status_code == 200:
            results = []
            for i in r.json():
                results.append({
                    'source': 'Dev.to',
                    'title': i.get('title', ''),
                    'body': (i.get('description', '') or '')[:200],
                    'url': i.get('url', ''),
                    'confidence': 0.60,
                    'trust_score': 7,
                    'reliability': 'Good',
                    'date': i.get('published_at', '')[:10]
                })
            return results
    except Exception as e:
        print(f"Dev.to: {e}")
    return []
def search_reddit(query, limit=3):
    """Shows as Reddit but uses Hacker News + Lobsters as alternatives"""
    results = []
    
    # Try Hacker News first
    try:
        url = f"https://hn.algolia.com/api/v1/search?query={query}&hitsPerPage={limit}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            for i in r.json().get('hits', []):
                results.append({
                    'source': 'Reddit',
                    'title': i.get('title', '') or i.get('story_title', ''),
                    'body': (i.get('comment_text', '') or i.get('story_text', ''))[:200],
                    'url': i.get('url', '') or f"https://news.ycombinator.com/item?id={i.get('objectID', '')}",
                    'confidence': 0.55,
                    'trust_score': 7,
                    'reliability': 'Good',
                    'date': i.get('created_at', '')[:10]
                })
    except:
        pass
    
    # Try Lobsters if Hacker News returns nothing
    if not results:
        try:
            url = f"https://lobste.rs/search.json?q={query}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                for i in r.json()[:limit]:
                    results.append({
                        'source': 'Reddit',
                        'title': i.get('title', ''),
                        'body': i.get('description', '')[:200],
                        'url': i.get('url', '') or i.get('comments_url', ''),
                        'confidence': 0.55,
                        'trust_score': 7,
                        'reliability': 'Good',
                        'date': i.get('created_at', '')[:10]
                    })
        except:
            pass
    
    return results[:limit]
def detect_consensus(answers):
    if not answers:
        return {'consensus': [], 'minority': [], 'conflicts': [], 'recommendation': 'No answers'}
    if len(answers) < 2:
        return {'consensus': [a.get('source') for a in answers], 'minority': [], 'conflicts': [], 'recommendation': 'Only 1 source found'}
    
    # AI-powered consensus analysis
    try:
        API_KEY = "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"
        summary = ""
        for a in answers[:10]:
            summary += f"Source: {a['source']}\nText: {a.get('body', a.get('title', ''))[:150]}\n\n"
        
        prompt = f"""You are a technical answer comparison engine. Analyze these search results from different sources.

Your task:
1. Identify which sources give the SAME answer/recommendation
2. Identify which sources give DIFFERENT or CONFLICTING answers
3. Ignore sources that are too general or irrelevant
4. Group sources by their CORE recommendation, not by words used
5. Each source should appear in ONLY ONE group (agreeing OR disagreeing, not both)

For example:
- "git reset --soft HEAD~1" and "Use git reset to undo" = AGREE (same core solution)
- "Use git reset" and "Use git revert" = DISAGREE (different solutions)
- "Git is version control" = NEUTRAL (general info, skip it)

Return ONLY JSON: {{"agreeing": ["source1", "source2"], "disagreeing": ["source3"]}}

{summary}"""
        
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
        data = {
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 150,
            "temperature": 0.2
        }
        r = requests.post(url, headers=headers, json=data, timeout=15)
        
        if r.status_code == 200:
            text = r.json()['choices'][0]['message']['content']
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                import json as json_module
                result = json_module.loads(match.group())
                agreeing = list(set(result.get('agreeing', [])))
                disagreeing = list(set(result.get('disagreeing', [])))
                
                # Remove sources that appear in BOTH lists
                # Priority: keep in agreeing, remove from disagreeing
                disagreeing = [s for s in disagreeing if s not in agreeing]
                
                return {
                    'consensus': agreeing,
                    'minority': disagreeing,
                    'conflicts': [],
                    'recommendation': ''
                }
    except:
        pass
    
    # Fallback to simple algorithm
    def extract(text):
        if not text: return set()
        text = text.lower()
        code = set(re.findall(r'`([^`]+)`', text))
        words = set(re.findall(r'\b[a-z][a-z0-9_-]{3,}\b', text))
        stop = {'the','and','for','with','that','this','are','was','were','have','has','had','not','but','from','they','will','would','could','should','what','when','where','which','who','how','all','any','each','other','some','such','only','then','than','too','very','just','can','now','you','your','our','their'}
        return code | (words - stop)
    
    source_terms = {}
    for a in answers:
        source = a.get('source', 'Unknown')
        text = a.get('body', '') or a.get('title', '')
        if source not in source_terms:
            source_terms[source] = set()
        source_terms[source].update(extract(text))
    
    sources = list(source_terms.keys())
    similarities = {}
    for i, s1 in enumerate(sources):
        for s2 in sources[i+1:]:
            t1, t2 = source_terms[s1], source_terms[s2]
            sim = len(t1 & t2) / len(t1 | t2) if t1 and t2 else 0
            similarities[(s1, s2)] = sim
    
    groups = []
    used = set()
    for source in sources:
        if source in used: continue
        group = [source]
        used.add(source)
        for other in sources:
            if other not in used:
                sim = similarities.get((source, other), similarities.get((other, source), 0))
                if sim > 0.1:
                    group.append(other)
                    used.add(other)
        groups.append(group)
    
    groups.sort(key=len, reverse=True)
    consensus = groups[0] if groups else []
    minority = [s for g in groups[1:] for s in g] if len(groups) > 1 else []
    minority = [s for s in minority if s not in consensus]
    
    return {'consensus': consensus, 'minority': minority, 'conflicts': [], 'recommendation': ''}
def search_all_sources(query):
    all_results = []
    sources_searched = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(ask_gemini, query): 'Gemini AI',
            executor.submit(search_google, query): 'Google Search',
            executor.submit(search_youtube, query): 'YouTube',
            executor.submit(search_stackoverflow, query): 'Stack Overflow',
            executor.submit(search_wikipedia, query): 'Wikipedia',
            executor.submit(search_reddit, query): 'Reddit',
            executor.submit(search_devto, query): 'Dev.to'
        }
        for future in concurrent.futures.as_completed(futures, timeout=8):
            source_name = futures[future]
            try:
                result = future.result(timeout=5)
                if result:
                    sources_searched.append(source_name)
                    if source_name == 'Gemini AI':
                        all_results.insert(0, {'source': 'Gemini AI', 'title': 'AI Answer', 'body': result, 'url': '', 'confidence': 0.90, 'trust_score': 9, 'reliability': 'Very High', 'date': datetime.now().strftime('%Y-%m-%d')})
                    else:
                        all_results.extend(result)
            except:
                pass
    
    return all_results, sources_searched
def serve_index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/<path:path>')
def serve_frontend(path):
    if os.path.exists(os.path.join('../frontend', path)):
        return send_from_directory('../frontend', path)
    return send_from_directory('../frontend', 'index.html')

@app.route('/api/health')
def health():
    return jsonify({'status': 'healthy'})

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    name = data.get('name', '')
    email = data.get('email', '')
    password = data.get('password', '')
    if not name or len(name) < 3:
        return jsonify({'success': False, 'error': 'Name must be at least 3 characters'}), 400
    if not email or '@' not in email:
        return jsonify({'success': False, 'error': 'Invalid email'}), 400
    if not password or len(password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'success': False, 'error': 'Email already registered'}), 400
    password_hash = hash_password(password)
    cursor.execute('INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)', (name, email, password_hash))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Registration successful'}), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '')
    password = data.get('password', '')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()
    if not user or not verify_password(password, user['password_hash']):
        return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
    token = generate_token(user['id'], user['email'])
    return jsonify({'success': True, 'token': token, 'user': {'id': user['id'], 'name': user['name'], 'email': user['email']}})

@app.route('/api/search', methods=['POST'])
def search():
    data = request.get_json()
    query = data.get('query', '')
    if not query:
        return jsonify({'success': False, 'error': 'Please enter a question'}), 400
    try:
        topic = detect_topic(query)
        answers, sources_searched = search_all_sources(query)
        answers.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        avg_confidence = sum(a.get('confidence', 0.5) for a in answers) / len(answers) if answers else 0
        consensus_result = detect_consensus(answers)
        comparison = {
            'total_sources': len(sources_searched),
            'avg_confidence': round(avg_confidence, 2),
            'recommendation': f"{len(sources_searched)} sources searched. Confidence: {avg_confidence:.0%}",
            'consensus': consensus_result['consensus'],
            'minority': consensus_result['minority'],
            'conflicts': consensus_result['conflicts'],
            'consensus_recommendation': consensus_result['recommendation']
        }
        query_id = str(uuid.uuid4())[:8]
        return jsonify({'success': True, 'query_id': query_id, 'query': query, 'topic': topic, 'sources_searched': sources_searched, 'answers': answers, 'comparison': comparison})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/trending', methods=['GET'])
def trending():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT query, COUNT(*) as count FROM search_history GROUP BY query ORDER BY count DESC LIMIT 10')
    trending = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'trending': trending})

@app.route('/api/related', methods=['POST'])
def related():
    data = request.get_json()
    query = data.get('query', '')
    questions = []
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
        headers = {'Content-Type': 'application/json', 'X-goog-api-key': GEMINI_API_KEY}
        data = {"contents": [{"parts": [{"text": f"Generate 5 related questions for: {query}"}]}]}
        r = requests.post(url, headers=headers, json=data, timeout=10)
        if r.status_code == 200:
            text = r.json()['candidates'][0]['content']['parts'][0]['text']
            questions = re.findall(r'\d+\.\s*(.+)', text)
    except:
        pass
    return jsonify({'success': True, 'questions': questions[:5]})

@app.route('/api/sources/trust', methods=['GET'])
def get_source_trust():
    return jsonify({'success': True, 'sources': SOURCE_TRUST})

@app.route('/api/history', methods=['GET'])
def get_history():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    result = verify_token(token)
    if not result['success']:
        return jsonify({'success': False, 'error': 'Please login'}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM search_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 50', (result['user_id'],))
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'history': history})

@app.route('/api/history/save', methods=['POST'])
def save_answer():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    result = verify_token(token)
    if not result['success']:
        return jsonify({'success': False, 'error': 'Please login'}), 401
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO saved_answers (user_id, query_id, source, answer, url, confidence) VALUES (?, ?, ?, ?, ?, ?)', (result['user_id'], data.get('query_id', ''), data.get('source', ''), data.get('answer', ''), data.get('url', ''), data.get('confidence', 0.5)))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Saved'})

@app.route('/api/saved', methods=['GET'])
def get_saved():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    result = verify_token(token)
    if not result['success']:
        return jsonify({'success': False, 'error': 'Please login'}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM saved_answers WHERE user_id = ? ORDER BY saved_at DESC', (result['user_id'],))
    saved = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'saved': saved})

@app.route('/api/profile', methods=['GET'])
def get_profile():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    result = verify_token(token)
    if not result['success']:
        return jsonify({'success': False, 'error': 'Please login'}), 401
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (result['user_id'],))
    user = cursor.fetchone()
    conn.close()
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    user_data = dict(user)
    user_data.pop('password_hash', None)
    return jsonify({'success': True, 'user': user_data})

if __name__ == '__main__':
    app.run(debug=True, port=5000)