import sqlite3
import os
import re
import jwt
import bcrypt
import requests
import uuid
import concurrent.futures
import time
import json as json_module
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from bs4 import BeautifulSoup

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# ============ CONFIG ============
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
GROQ_MODEL = os.getenv('GROQ_MODEL', 'openai/gpt-oss-20b')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', '')
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'techhub.db')
SECRET_KEY = "techhub-secret-2026"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

SOURCE_TRUST = {
    'Gemini AI': {'score': 9, 'reliability': 'Very High'},
    'Google Search': {'score': 7, 'reliability': 'Good'},
    'Stack Overflow': {'score': 9, 'reliability': 'Very High'},
    'GitHub': {'score': 8, 'reliability': 'High'},
    'Wikipedia': {'score': 8, 'reliability': 'High'},
    'Dev.to': {'score': 7, 'reliability': 'Good'},
    'Reddit': {'score': 7, 'reliability': 'Good'},
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

init_db()

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
    topic_keywords = {
        'python': ['python', 'pandas', 'numpy', 'flask', 'django', 'pip', 'conda', 'jupyter', 'matplotlib', 'scipy', 'pytest', 'sqlalchemy', 'celery', 'asyncio', 'decorator', 'lambda', 'list comprehension', 'dictionary', 'tuple', 'virtualenv', 'pydantic', 'beautifulsoup', 'scrapy', 'selenium', 'opencv', 'pygame', 'tkinter', 'pyqt', 'multiprocessing', 'threading', 'metaclass', 'dataclass', 'generator', 'coroutine'],
        'javascript': ['javascript', 'js', 'node', 'react', 'vue', 'angular', 'typescript', 'npm', 'yarn', 'dom', 'callback', 'promise', 'async', 'await', 'jsx', 'express', 'nextjs', 'nuxt', 'svelte', 'webpack', 'babel', 'jest', 'cypress', 'electron', 'redux', 'usestate', 'useeffect', 'closure', 'hoisting', 'arrow function', 'spread', 'destructuring', 'fetch', 'axios', 'websocket', 'event loop'],
        'java': ['java', 'spring', 'maven', 'gradle', 'jvm', 'kotlin', 'hibernate', 'jpa', 'servlet', 'junit', 'mockito', 'arraylist', 'hashmap', 'interface', 'abstract', 'override', 'exception', 'thread', 'synchronized', 'generics', 'enum', 'annotation', 'reflection', 'stream api'],
        'git': ['git', 'commit', 'branch', 'merge', 'rebase', 'repo', 'pull', 'push', 'clone', 'reset', 'revert', 'stash', 'checkout', 'github', 'gitlab', 'version control', 'diff', 'conflict', 'remote', 'fork', 'pull request', 'cherry-pick'],
        'sql': ['sql', 'mysql', 'postgresql', 'sqlite', 'query', 'select', 'insert', 'update', 'delete', 'join', 'inner join', 'left join', 'table', 'index', 'primary key', 'foreign key', 'trigger', 'view', 'stored procedure', 'transaction'],
        'docker': ['docker', 'dockerfile', 'container', 'image', 'volume', 'compose', 'dockerhub', 'registry', 'containerize', 'orchestration'],
        'kubernetes': ['kubernetes', 'k8s', 'kubectl', 'pod', 'deployment', 'service', 'ingress', 'helm', 'cluster', 'minikube', 'eks', 'aks', 'gke', 'istio', 'prometheus', 'grafana'],
        'html_css': ['html', 'css', 'div', 'span', 'flexbox', 'grid', 'bootstrap', 'tailwind', 'margin', 'padding', 'responsive', 'animation', 'transition', 'media query', 'center', 'layout'],
        'machine_learning': ['machine learning', 'ml', 'model', 'training', 'accuracy', 'tensorflow', 'pytorch', 'keras', 'neural network', 'deep learning', 'regression', 'classification', 'clustering', 'overfitting', 'gradient descent'],
        'cybersecurity': ['security', 'encryption', 'hashing', 'firewall', 'vpn', 'malware', 'phishing', 'ddos', 'penetration testing', 'vulnerability', 'exploit', 'cryptography', 'authentication'],
        'linux': ['linux', 'ubuntu', 'bash', 'shell', 'terminal', 'ssh', 'cron', 'chmod', 'sudo', 'apt', 'grep', 'awk', 'sed'],
        'blockchain': ['blockchain', 'bitcoin', 'ethereum', 'solidity', 'web3', 'nft', 'defi', 'token', 'wallet', 'metamask', 'smart contract'],
        'aws': ['aws', 'ec2', 's3', 'lambda', 'rds', 'dynamodb', 'cloudfront', 'cloudwatch', 'iam', 'vpc', 'serverless'],
        'android': ['android', 'apk', 'google play', 'gradle', 'manifest', 'activity', 'fragment', 'recyclerview', 'jetpack', 'compose', 'kotlin coroutine'],
        'ios': ['ios', 'swift', 'swiftui', 'xcode', 'app store', 'testflight', 'uikit', 'core data', 'autolayout'],
        'data_science': ['data science', 'data analysis', 'visualization', 'pandas', 'tableau', 'chart', 'dashboard', 'statistics', 'regression', 'hypothesis'],
        'networking': ['networking', 'tcp', 'udp', 'dns', 'dhcp', 'routing', 'switching', 'subnet', 'firewall', 'bandwidth', 'latency', 'packet'],
        'devops': ['devops', 'ci/cd', 'jenkins', 'github actions', 'pipeline', 'terraform', 'ansible', 'monitoring', 'automation', 'deployment'],
    }
    
    query_lower = query.lower()
    words = query_lower.split()
    
    scores = {}
    for topic, keywords in topic_keywords.items():
        score = 0
        for kw in keywords:
            if kw in query_lower:
                score += 2
            elif kw in words:
                score += 1
        if score > 0:
            scores[topic] = score
    
    if scores:
        best_topic = max(scores, key=scores.get)
        best_score = scores[best_topic]
        if best_score >= 3:
            return best_topic
        if best_score >= 1:
            ai_topic = detect_topic_ai(query)
            if ai_topic and ai_topic != 'general':
                return ai_topic
            return best_topic
    
    return detect_topic_ai(query)

def detect_topic_ai(query):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'}
        prompt = f"""Classify this technical question into ONE category:
python, javascript, java, c_cpp, csharp, ruby, php, go, rust, swift, kotlin, typescript, html_css, frontend, backend, fullstack, react, vue, angular, nodejs, django, flask, mysql, postgresql, sqlite, mongodb, redis, docker, kubernetes, aws, azure, gcp, terraform, ansible, devops, linux, networking, blockchain, machine_learning, deep_learning, nlp, data_science, cybersecurity, android, ios, flutter, react_native, game_dev, robotics, quantum, ar_vr, iot, embedded, operating_system, software_testing, api_development, microservices, serverless, git, bash_shell

Question: {query}
Return ONLY category name (lowercase, underscores). No explanation."""
        data = {
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 20,
            "temperature": 0.1
        }
        r = requests.post(url, headers=headers, json=data, timeout=10)
        if r.status_code == 200:
            topic = r.json()['choices'][0]['message']['content'].strip().lower()
            topic = re.sub(r'[^a-z_]', '', topic)
            return topic if topic else 'general'
        return 'general'
    except:
        return 'general'

def calculate_confidence(source, score=0, stars=0, is_answered=False, views=0, likes=0):
    if source == 'Stack Overflow':
        votes = score
        if is_answered and votes >= 100:
            return 0.95
        elif votes >= 100:
            return 0.85
        elif votes >= 50:
            return 0.75
        elif votes >= 10:
            return 0.60
        elif votes >= 5:
            return 0.50
        else:
            return 0.40
    elif source == 'GitHub':
        if stars >= 10000:
            return 0.90
        elif stars >= 1000:
            return 0.80
        elif stars >= 100:
            return 0.65
        elif stars >= 10:
            return 0.50
        else:
            return 0.35
    elif source == 'YouTube':
        like_ratio = (likes / views) if views > 0 else 0
        if views >= 1000000 and like_ratio > 0.02:
            return 0.85
        elif views >= 100000:
            return 0.70
        elif views >= 10000:
            return 0.55
        elif views >= 1000:
            return 0.45
        else:
            return 0.35
    elif source == 'Wikipedia':
        return 0.75
    elif source == 'Gemini AI':
        return 0.85
    elif source == 'Google Search':
        return 0.55
    elif source == 'Dev.to':
        return 0.55
    elif source == 'Reddit':
        if score >= 100:
            return 0.65
        elif score >= 20:
            return 0.50
        else:
            return 0.35
    return 0.50

def ask_gemini(query, topic='general'):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'}
        system_prompt = """You are TechHub, an expert technical assistant.
Rules:
1. ALWAYS answer the user's question directly - never say "I'm ready to help"
2. Include code examples when relevant
3. Be concise but complete
4. Format code in markdown blocks"""
        data = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Topic: {topic}\n\nQuestion: {query}\n\nAnswer directly:"}
            ],
            "max_tokens": 500,
            "temperature": 0.3
        }
        for attempt in range(3):
            r = requests.post(url, headers=headers, json=data, timeout=20)
            print(f"GROQ attempt {attempt+1}: status {r.status_code}")
            if r.status_code == 200:
                answer = r.json()['choices'][0]['message']['content']
                print(f"GROQ answer length: {len(answer)}")
                if len(answer) < 20 or "ready to help" in answer.lower():
                    time.sleep(2)
                    continue
                return answer
            elif r.status_code == 429:
                time.sleep(5)
                continue
            else:
                print(f"GROQ error: {r.text[:200]}")
                break
        return None
    except Exception as e:
        print(f"GROQ error: {e}")
        return None

def search_google(query, limit=5):
    """Uses Bing search (scraping) - more reliable than DuckDuckGo"""
    results = []
    seen_urls = set()
    
    # Try Bing first
    try:
        url = f"https://www.bing.com/search?q={query}&count={limit*2}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Try multiple Bing result selectors
            for item in soup.find_all('li', class_='b_algo')[:limit]:
                title_elem = item.find('h2')
                link_elem = item.find('a')
                snippet_elem = item.find('div', class_='b_caption') or item.find('p')
                
                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    link = link_elem.get('href', '')
                    body = snippet_elem.get_text(strip=True)[:250] if snippet_elem else ''
                    
                    if link and link not in seen_urls:
                        seen_urls.add(link)
                        results.append({
                            'source': 'Google Search',
                            'title': title,
                            'body': body,
                            'url': link,
                            'confidence': 0.65,
                            'trust_score': 7,
                            'reliability': 'Good',
                            'date': ''
                        })
        else:
            print(f"Bing status: {r.status_code}")
    except Exception as e:
        print(f"Bing error: {e}")
    
    # Fallback to DuckDuckGo
    if not results:
        try:
            url = "https://api.duckduckgo.com/"
            params = {'q': query, 'format': 'json', 'no_html': 1, 'no_redirect': 1, 'skip_disambig': 1}
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                
                if data.get('AbstractText') and len(data.get('AbstractText', '')) > 50:
                    results.append({
                        'source': 'Google Search',
                        'title': data.get('Heading', query),
                        'body': data.get('AbstractText', '')[:250],
                        'url': data.get('AbstractURL', ''),
                        'confidence': 0.75,
                        'trust_score': 7,
                        'reliability': 'High',
                        'date': ''
                    })
                
                for topic in data.get('RelatedTopics', []):
                    if isinstance(topic, dict) and 'Text' in topic:
                        topic_url = topic.get('FirstURL', '')
                        if topic_url and topic_url not in seen_urls:
                            seen_urls.add(topic_url)
                            results.append({
                                'source': 'Google Search',
                                'title': topic.get('Text', '')[:100],
                                'body': topic.get('Text', '')[:250],
                                'url': topic_url,
                                'confidence': 0.60,
                                'trust_score': 6,
                                'reliability': 'Good',
                                'date': ''
                            })
                        if len(results) >= limit:
                            break
        except:
            pass
    
    # Remove duplicates
    final_results = []
    seen_titles = set()
    for r in results:
        title_key = r['title'][:60].lower()
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            final_results.append(r)
    
    return final_results[:limit]
def search_youtube(query, limit=3):
    try:
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {'q': query, 'key': YOUTUBE_API_KEY, 'part': 'snippet', 'type': 'video', 'maxResults': limit, 'order': 'relevance', 'videoEmbeddable': 'true'}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            items = r.json().get('items', [])
            if not items:
                return []
            video_ids = [i['id']['videoId'] for i in items]
            stats_url = "https://www.googleapis.com/youtube/v3/videos"
            stats_params = {'id': ','.join(video_ids), 'key': YOUTUBE_API_KEY, 'part': 'statistics'}
            stats_r = requests.get(stats_url, params=stats_params, timeout=10)
            stats_data = {}
            if stats_r.status_code == 200:
                for item in stats_r.json().get('items', []):
                    stats_data[item['id']] = item.get('statistics', {})
            results = []
            for item in items:
                vid = item['id']['videoId']
                snippet = item.get('snippet', {})
                stats = stats_data.get(vid, {})
                views = int(stats.get('viewCount', 0))
                likes = int(stats.get('likeCount', 0))
                results.append({'source': 'YouTube', 'title': snippet.get('title', ''), 'body': snippet.get('description', '')[:200], 'url': f'https://youtube.com/watch?v={vid}', 'views': views, 'likes': likes, 'channel': snippet.get('channelTitle', ''), 'confidence': calculate_confidence('YouTube', views=views, likes=likes), 'trust_score': 6, 'reliability': 'Good', 'date': snippet.get('publishedAt', '')[:10]})
            return results
    except Exception as e:
        print(f"YouTube: {e}")
    return []

def search_stackoverflow(query, limit=5):
    try:
        url = "https://api.stackexchange.com/2.3/search/advanced"
        params = {'q': query, 'site': 'stackoverflow', 'pagesize': limit * 2, 'order': 'desc', 'sort': 'votes', 'filter': 'withbody', 'answers': 1, 'closed': 'False'}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            results = []
            seen = set()
            for i in r.json().get('items', []):
                link = i.get('link', '')
                if link in seen:
                    continue
                score = i.get('score', 0)
                if score < 5:
                    continue
                seen.add(link)
                results.append({'source': 'Stack Overflow', 'title': i.get('title', ''), 'body': re.sub(r'<[^>]+>', '', i.get('body', ''))[:300], 'url': link, 'score': score, 'is_answered': i.get('is_answered', False), 'tags': i.get('tags', [])[:3], 'confidence': calculate_confidence('Stack Overflow', score=score, is_answered=i.get('is_answered', False)), 'reliability': 'Very High', 'date': datetime.fromtimestamp(i.get('creation_date', 0)).strftime('%Y-%m-%d')})
                if len(results) >= limit:
                    break
            return results
    except Exception as e:
        print(f"SO: {e}")
    return []

def search_github(query, limit=3):
    try:
        topic = detect_topic(query)
        
        topic_language = {'python': 'python', 'javascript': 'javascript', 'java': 'java', 'c_cpp': 'c++', 'csharp': 'c#', 'ruby': 'ruby', 'php': 'php', 'go': 'go', 'rust': 'rust', 'swift': 'swift', 'kotlin': 'kotlin', 'typescript': 'typescript', 'git': 'git'}
        
        language = topic_language.get(topic, '')
        url = "https://api.github.com/search/repositories"
        search_query = query
        if language:
            search_query = f"{query} language:{language}"
        
        params = {'q': search_query, 'sort': 'stars', 'per_page': limit * 3}
        r = requests.get(url, params=params, timeout=10)
        
        if r.status_code == 200:
            results = []
            query_words = [w.lower() for w in query.split() if len(w) > 3]
            
            for i in r.json().get('items', []):
                stars = i.get('stargazers_count', 0)
                description = (i.get('description', '') or '').lower()
                name = (i.get('full_name', '') or '').lower()
                combined = name + ' ' + description
                
                # Require at least 2 query words in name/description
                matches = sum(1 for w in query_words if w in combined)
                
                if matches >= 2 and stars > 50:
                    results.append({
                        'source': 'GitHub',
                        'title': i.get('full_name', ''),
                        'body': (i.get('description', '') or 'No description')[:250],
                        'url': i.get('html_url', ''),
                        'stars': stars,
                        'language': i.get('language', ''),
                        'topics': i.get('topics', [])[:5],
                        'confidence': calculate_confidence('GitHub', stars=stars),
                        'trust_score': 8,
                        'reliability': 'High',
                        'date': i.get('updated_at', '')[:10]
                    })
                
                if len(results) >= limit:
                    break
            
            return results
    except Exception as e:
        print(f"GH: {e}")
    return []
def search_wikipedia(query, limit=3):
    try:
        stop_words = {'how', 'to', 'what', 'is', 'the', 'a', 'an', 'in', 'of', 'for', 'and', 'or', 'but', 'can', 'you', 'i', 'me', 'my', 'do', 'does', 'did', 'why', 'when', 'where', 'which', 'who', 'use', 'using', 'with', 'without', 'from', 'this', 'that', 'these', 'those', 'it', 'on', 'at', 'by'}
        words = query.lower().split()
        meaningful = [w for w in words if w not in stop_words]
        search_term = ' '.join(meaningful) if meaningful else query
        wiki_headers = {'User-Agent': 'TechHub/1.0 (contact@techhub.example.com)'}
        url = "https://en.wikipedia.org/w/api.php"
        params = {'action': 'query', 'list': 'search', 'srsearch': search_term, 'format': 'json', 'srlimit': 10}
        r = requests.get(url, params=params, headers=wiki_headers, timeout=15)
        if r.status_code == 200:
            search_results = r.json().get('query', {}).get('search', [])
            results = []
            for item in search_results:
                title = item.get('title', '')
                snippet = item.get('snippet', '')
                clean_snippet = re.sub(r'<[^>]+>', '', snippet)
                timestamp = item.get('timestamp', '')
                title_lower = title.lower()
                if 'disambiguation' in title_lower:
                    continue
                query_words = [w for w in meaningful if len(w) > 2]
                if query_words:
                    if not any(w in title_lower for w in query_words):
                        continue
                results.append({'source': 'Wikipedia', 'title': title, 'body': clean_snippet[:250], 'url': f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}", 'confidence': 0.85, 'trust_score': 8, 'reliability': 'High', 'date': timestamp[:10]})
                if len(results) >= limit:
                    break
            if results:
                return results
        params = {'action': 'query', 'list': 'search', 'srsearch': search_term, 'format': 'json', 'srlimit': limit}
        r = requests.get(url, params=params, headers=wiki_headers, timeout=15)
        if r.status_code == 200:
            search_results = r.json().get('query', {}).get('search', [])
            results = []
            for item in search_results:
                title = item.get('title', '')
                if 'disambiguation' in title.lower():
                    continue
                results.append({'source': 'Wikipedia', 'title': title, 'body': re.sub(r'<[^>]+>', '', item.get('snippet', ''))[:250], 'url': f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}", 'confidence': 0.70, 'trust_score': 8, 'reliability': 'High', 'date': item.get('timestamp', '')[:10]})
                if len(results) >= limit:
                    break
            return results
        return []
    except Exception as e:
        print(f"Wiki: {e}")
    return []

def search_devto(query, limit=3):
    try:
        topic = detect_topic(query)
        tag = topic if topic != 'general' else 'programming'
        url = f"https://dev.to/api/articles?tag={tag}&per_page={limit * 2}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            results = []
            for i in r.json():
                title = (i.get('title', '') or '').lower()
                query_words = [w.lower() for w in query.split() if len(w) > 3]
                matches = sum(1 for w in query_words if w in title)
                if matches >= 1 or tag == topic:
                    results.append({'source': 'Dev.to', 'title': i.get('title', ''), 'body': (i.get('description', '') or '')[:250], 'url': i.get('url', ''), 'tags': i.get('tags', [])[:3], 'confidence': 0.60 if matches >= 1 else 0.50, 'trust_score': 7, 'reliability': 'Good', 'date': i.get('published_at', '')[:10]})
                if len(results) >= limit:
                    break
            return results if results else []
    except Exception as e:
        print(f"Dev.to: {e}")
    return []

def search_reddit(query, limit=3):
    results = []
    try:
        url = f"https://hn.algolia.com/api/v1/search?query={query}&hitsPerPage=10"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            for i in r.json().get('hits', []):
                points = i.get('points', 0) or 0
                created = i.get('created_at', '')
                try:
                    post_date = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    if post_date < datetime.now() - timedelta(days=365*5):
                        continue
                except:
                    pass
                if points < 5:
                    continue
                results.append({'source': 'Reddit', 'title': i.get('title', '') or i.get('story_title', ''), 'body': (i.get('comment_text', '') or i.get('story_text', ''))[:200], 'url': i.get('url', '') or f"https://news.ycombinator.com/item?id={i.get('objectID', '')}", 'score': points, 'confidence': calculate_confidence('Reddit', score=points), 'trust_score': 7, 'reliability': 'Good', 'date': created[:10]})
                if len(results) >= limit:
                    break
    except Exception as e:
        print(f"Reddit: {e}")
    return results

def detect_consensus(answers):
    if not answers:
        return {'consensus': [], 'minority': [], 'conflicts': [], 'recommendation': 'No answers'}
    if len(answers) < 2:
        return {'consensus': [a.get('source') for a in answers], 'minority': [], 'conflicts': [], 'recommendation': 'Only 1 source found'}
    try:
        summary = ""
        for a in answers[:10]:
            summary += f"Source: {a['source']}\nText: {a.get('body', a.get('title', ''))[:150]}\n\n"
        prompt = f"""Analyze these search results. 

CRITICAL RULES:
- Each source must appear in ONLY ONE list (agreeing OR disagreeing)
- NEVER put the same source in both lists
- Remove any source that is too general or irrelevant
- Group by CORE recommendation, not wording

Return JSON with these EXACT keys:
{{"agreeing": [], "disagreeing": []}}

{summary}"""
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'}
        data = {"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 150, "temperature": 0.1}
        r = requests.post(url, headers=headers, json=data, timeout=15)
        if r.status_code == 200:
            text = r.json()['choices'][0]['message']['content']
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                result = json_module.loads(match.group())
                raw_agreeing = result.get('agreeing', [])
                raw_disagreeing = result.get('disagreeing', [])
                def clean_list(items):
                    cleaned = []
                    seen = set()
                    for item in items:
                        key = item.lower().strip()
                        if key not in seen:
                            seen.add(key)
                            cleaned.append(item)
                    return cleaned
                agreeing = clean_list(raw_agreeing)
                disagreeing = clean_list(raw_disagreeing)
                agreeing_keys = {a.lower().strip() for a in agreeing}
                disagreeing = [d for d in disagreeing if d.lower().strip() not in agreeing_keys]
                return {'consensus': agreeing, 'minority': disagreeing, 'conflicts': [], 'recommendation': ''}
    except:
        pass
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
    consensus = list(dict.fromkeys(consensus))
    minority = list(dict.fromkeys(minority))
    minority = [s for s in minority if s not in consensus]
    return {'consensus': consensus, 'minority': minority, 'conflicts': [], 'recommendation': ''}

def search_all_sources(query):
    all_results = []
    sources_searched = []
    topic = detect_topic(query)
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futures = {
            executor.submit(ask_gemini, query, topic): 'Gemini AI',
            executor.submit(search_google, query): 'Google Search',
            executor.submit(search_youtube, query): 'YouTube',
            executor.submit(search_stackoverflow, query): 'Stack Overflow',
            executor.submit(search_github, query): 'GitHub',
            executor.submit(search_wikipedia, query): 'Wikipedia',
            executor.submit(search_devto, query): 'Dev.to',
            executor.submit(search_reddit, query): 'Reddit'
        }
        for future in concurrent.futures.as_completed(futures, timeout=10):
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

@app.route('/')
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

@app.route('/api/related', methods=['POST'])
def related():
    data = request.get_json()
    query = data.get('query', '')
    questions = []
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'}
        data = {"model": GROQ_MODEL, "messages": [{"role": "user", "content": f"Generate 5 related technical questions for: {query}. Return as numbered list."}], "max_tokens": 150, "temperature": 0.5}
        r = requests.post(url, headers=headers, json=data, timeout=10)
        if r.status_code == 200:
            text = r.json()['choices'][0]['message']['content']
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