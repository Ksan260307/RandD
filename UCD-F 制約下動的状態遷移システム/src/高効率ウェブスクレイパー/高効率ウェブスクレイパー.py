import urllib.request
import urllib.error
import re
import time
import random
import json
import threading
import webbrowser
from urllib.parse import urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver

# ==========================================
# 状態圧縮管理 (Packed State Management)
# ==========================================
STATE_IDLE = 0       # 待機
STATE_RUNNING = 1    # 実行中
STATE_DONE = 2       # 完了
STATE_ERROR = 3      # エラー
STATE_PROMOTED = 4   # 動的昇格（データが大きく、詳細な解析が必要な状態）
STATE_RUINED = 5     # 破綻（リトライ上限超過により地形化）

def pack_state(priority, retry, status, ruin=0):
    return (priority & 0x3) | ((retry & 0x3) << 2) | ((status & 0x7) << 4) | ((ruin & 0x7) << 7)

def unpack_state(state):
    priority = state & 0x3
    retry = (state >> 2) & 0x3
    status = (state >> 4) & 0x7
    ruin = (state >> 7) & 0x7
    return priority, retry, status, ruin

def update_status(state, new_status):
    p, r, _, ruin = unpack_state(state)
    return pack_state(p, r, new_status, ruin)


# ==========================================
# データ並列構造・コアエンジン
# ==========================================
class ScraperSystem:
    def __init__(self):
        self.urls = []         
        self.states = []       
        self.contents = []     
        self.domain_ruin_scores = {} 
        self.logs = []
        self.exec_thread = None
        
        # 動的抽出オプション（UIからの指示で切り替わる）
        self.extract_options = {
            'title': True,
            'description': False,
            'keywords': False,
            'h1': False,
            'h2': False,
            'body_text': True,  # 本文抽出
            'links': True,
            'images': False
        }

    def log(self, msg):
        print(msg) # コンソールにも出力
        t = time.strftime("%H:%M:%S")
        self.logs.append(f"[{t}] {msg}")
        if len(self.logs) > 50:
            self.logs.pop(0)

    def add_task(self, url):
        self.urls.append(url)
        self.states.append(pack_state(0, 0, STATE_IDLE, 0))
        self.contents.append(None)
        self.log(f"[+] タスク追加: {url}")

    def _fetch_url(self, url):
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.read().decode('utf-8', errors='ignore')
        except Exception:
            return None

    def execute_batch(self):
        self.log("--- 処理開始 ---")
        
        # Stream Compaction
        active_indices = [i for i in range(len(self.urls)) if unpack_state(self.states[i])[2] == STATE_IDLE]
        
        if not active_indices:
            self.log("実行可能な待機タスクがありません。")
            self.log("--- 処理終了 ---")
            return

        for i in active_indices:
            p, r, status, ruin = unpack_state(self.states[i])
            url = self.urls[i]
            domain = urlparse(url).netloc
            
            self.states[i] = update_status(self.states[i], STATE_RUNNING)
            
            domain_penalty = self.domain_ruin_scores.get(domain, 0)
            entropy_delay = random.uniform(0.1, 0.5)
            wait_time = entropy_delay + (domain_penalty * 0.5)
            
            msg = f"実行中 [{i}]: {url[:40]}... "
            if wait_time > 0.6:
                msg += f"(環境負荷により {wait_time:.1f}秒待機)"
            self.log(msg)
            time.sleep(wait_time)
            
            content = self._fetch_url(url)
            
            if content:
                if len(content) > 50000:
                    self.states[i] = update_status(self.states[i], STATE_PROMOTED)
                    self.log(f"[{i}] 完了 (大容量データ: 詳細解析へ昇格)")
                else:
                    self.states[i] = update_status(self.states[i], STATE_DONE)
                    self.log(f"[{i}] 完了")
                
                self.contents[i] = content
                if domain in self.domain_ruin_scores and self.domain_ruin_scores[domain] > 0:
                    self.domain_ruin_scores[domain] -= 1
            else:
                if r < 3:
                    self.states[i] = pack_state(p, r + 1, STATE_IDLE, ruin + 1)
                    delay = (r + 1) * 0.5 + (ruin * 0.2)
                    self.log(f"[{i}] 失敗 (再試行予定: {delay:.1f}秒待機)")
                    time.sleep(delay)
                else:
                    self.states[i] = update_status(self.states[i], STATE_RUINED)
                    self.log(f"[{i}] 完全失敗 (アクセス困難: ドメインを地形化)")
                    self.domain_ruin_scores[domain] = self.domain_ruin_scores.get(domain, 0) + 2
                    
        self.log("--- 処理終了 ---")

    def start_execution(self):
        """バックグラウンドスレッドで実行（非同期処理）"""
        if self.exec_thread and self.exec_thread.is_alive():
            return False
        self.exec_thread = threading.Thread(target=self.execute_batch)
        self.exec_thread.daemon = True
        self.exec_thread.start()
        return True

    def get_results(self):
        """UI表示用に現在の状態をJSON変換可能な形式で返す"""
        results = []
        status_map = {
            STATE_IDLE: "待機", STATE_RUNNING: "実行中", STATE_DONE: "完了",
            STATE_ERROR: "エラー", STATE_PROMOTED: "詳細解析", STATE_RUINED: "破綻"
        }
        for i in range(len(self.urls)):
            _, _, status, _ = unpack_state(self.states[i])
            html = self.contents[i]
            size = 0
            extracted = {}
            
            if html:
                size = len(html)
                
                # オプションに基づく動的データ抽出 (遅延評価)
                if self.extract_options.get('title'):
                    match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                    extracted['title'] = match.group(1).strip() if match else "タイトルなし"
                    
                if self.extract_options.get('description'):
                    match = re.search(r'<meta[^>]*name=[\'"]?description[\'"]?[^>]*content=[\'"]?([^\'">]+)[\'"]?', html, re.IGNORECASE)
                    extracted['description'] = match.group(1).strip() if match else "説明なし"

                if self.extract_options.get('keywords'):
                    match = re.search(r'<meta[^>]*name=[\'"]?keywords[\'"]?[^>]*content=[\'"]?([^\'">]+)[\'"]?', html, re.IGNORECASE)
                    extracted['keywords'] = match.group(1).strip() if match else ""

                if self.extract_options.get('h1'):
                    match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
                    extracted['h1'] = re.sub(r'<[^>]+>', '', match.group(1)).strip() if match else "H1なし"

                if self.extract_options.get('h2'):
                    found_h2 = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.IGNORECASE | re.DOTALL)
                    extracted['h2'] = [re.sub(r'<[^>]+>', '', h).strip() for h in found_h2 if h.strip()][:3]

                if self.extract_options.get('body_text'):
                    # script/styleなど表示に不要なタグを中身ごと除去
                    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.IGNORECASE | re.DOTALL)
                    # 残りのHTMLタグ自体を除去し、区切りを改行にする
                    text = re.sub(r'<[^>]+>', '\n', text)
                    # 各行の不要な空白を削除し、空行を詰める
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    text = '\n'.join(lines)
                    # UIクラッシュを防ぐ安全装置（約1万文字上限）
                    extracted['body_text'] = text[:10000] + ('...' if len(text) > 10000 else '')

                if self.extract_options.get('links') and status in (STATE_DONE, STATE_PROMOTED):
                    found_links = re.findall(r'href=[\'"]?(https?://[^\'" >]+)', html)
                    extracted['links'] = list(set(found_links))[:5] # 負荷対策で上位5件

                if self.extract_options.get('images') and status in (STATE_DONE, STATE_PROMOTED):
                    found_images = re.findall(r'<img[^>]+src=[\'"]?(https?://[^\'" >]+)', html, re.IGNORECASE)
                    extracted['images'] = list(set(found_images))[:5]
                    
            results.append({
                'id': i, 'url': self.urls[i], 'status': status_map.get(status, "不明"),
                'statusCode': status, 'size': size, 'extracted': extracted
            })
        return results

system = ScraperSystem()


# ==========================================
# フロントエンド (HTML / Tailwind CSS / JS)
# ==========================================
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>高効率ウェブスクレイパー</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        /* スクロールバーのカスタマイズ */
        .custom-scrollbar::-webkit-scrollbar {
            width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
            background: #f1f5f9;
            border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
            background: #cbd5e1;
            border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
            background: #94a3b8;
        }
    </style>
</head>
<body class="bg-slate-100 min-h-screen text-slate-800 font-sans">
    <div class="max-w-6xl mx-auto p-4 sm:p-6">
        
        <header class="flex justify-between items-center mb-6">
            <h1 class="text-2xl font-black tracking-tight text-indigo-900">🌐 Web Scraper Engine</h1>
            <div class="text-sm font-medium bg-white px-3 py-1 rounded shadow-sm border border-slate-200">
                Active Tasks: <span id="task-count" class="text-indigo-600 font-bold">0</span>
            </div>
        </header>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <!-- 左カラム：操作パネル -->
            <div class="lg:col-span-1 space-y-4">
                <div class="bg-white p-5 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="font-bold mb-3 text-slate-700">URLを追加</h2>
                    <div class="flex gap-2">
                        <input type="text" id="url-input" placeholder="https://example.com" class="flex-1 border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                        <button onclick="addTask()" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold px-4 py-2 rounded text-sm transition">追加</button>
                    </div>
                </div>

                <div class="bg-white p-5 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="font-bold mb-3 text-slate-700">システム制御</h2>
                    <button id="exec-btn" onclick="execBatch()" class="w-full bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white font-bold py-3 px-4 rounded shadow transition">
                        ▶ 一括処理を実行
                    </button>
                </div>

                <!-- 抽出オプション設定 -->
                <div class="bg-white p-5 rounded-xl shadow-sm border border-slate-200">
                    <h2 class="font-bold mb-3 text-slate-700">抽出オプション</h2>
                    <div class="grid grid-cols-2 gap-2 text-sm text-slate-600">
                        <label class="flex items-center gap-2 cursor-pointer hover:text-indigo-600">
                            <input type="checkbox" id="chk-title" checked onchange="updateConfig()" class="w-4 h-4 text-indigo-600 rounded"> タイトル
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer hover:text-indigo-600">
                            <input type="checkbox" id="chk-desc" onchange="updateConfig()" class="w-4 h-4 text-indigo-600 rounded"> 説明文
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer hover:text-indigo-600">
                            <input type="checkbox" id="chk-keywords" onchange="updateConfig()" class="w-4 h-4 text-indigo-600 rounded"> キーワード
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer hover:text-indigo-600">
                            <input type="checkbox" id="chk-h1" onchange="updateConfig()" class="w-4 h-4 text-indigo-600 rounded"> 👑 H1
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer hover:text-indigo-600">
                            <input type="checkbox" id="chk-h2" onchange="updateConfig()" class="w-4 h-4 text-indigo-600 rounded"> 📌 H2(Top 3)
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer hover:text-indigo-600">
                            <input type="checkbox" id="chk-body" checked onchange="updateConfig()" class="w-4 h-4 text-indigo-600 rounded"> 本文(全文)
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer hover:text-indigo-600">
                            <input type="checkbox" id="chk-links" checked onchange="updateConfig()" class="w-4 h-4 text-indigo-600 rounded"> リンク(Top 5)
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer hover:text-indigo-600">
                            <input type="checkbox" id="chk-images" onchange="updateConfig()" class="w-4 h-4 text-indigo-600 rounded"> 画像(Top 5)
                        </label>
                    </div>
                </div>

                <!-- 環境ペナルティ表示（地形化） -->
                <div class="bg-slate-800 text-slate-200 p-4 rounded-xl shadow-sm">
                    <h2 class="font-bold mb-2 text-sm text-slate-400">🚨 ドメイン環境ペナルティ (地形化)</h2>
                    <div id="ruin-scores" class="space-y-1"></div>
                    <p class="text-xs text-slate-500 mt-2">失敗が続いたドメインはアクセス遅延が課せられます。</p>
                </div>
            </div>

            <!-- 右カラム：タスク結果 ＆ ログ -->
            <div class="lg:col-span-2 space-y-4 flex flex-col">
                <!-- タスクカード一覧 -->
                <div class="bg-slate-50 p-5 rounded-xl shadow-inner border border-slate-200 flex-1 h-[600px] overflow-y-auto custom-scrollbar" id="tasks-container">
                    <div id="tasks" class="grid grid-cols-1 gap-4"></div>
                </div>

                <!-- システムコンソール -->
                <div class="bg-black text-green-400 p-4 rounded-xl font-mono text-xs h-40 overflow-y-auto custom-scrollbar shadow-inner" id="logs">
                    システム起動...
                </div>
            </div>
        </div>
    </div>

    <script>
        async function addTask() {
            const input = document.getElementById('url-input');
            const url = input.value.trim();
            if (!url) return;
            await fetch('/api/add', { method: 'POST', body: JSON.stringify({url}) });
            input.value = '';
            updateUI();
        }

        async function execBatch() {
            await fetch('/api/execute', { method: 'POST' });
            updateUI();
        }

        async function updateConfig() {
            const config = {
                title: document.getElementById('chk-title').checked,
                description: document.getElementById('chk-desc').checked,
                keywords: document.getElementById('chk-keywords').checked,
                h1: document.getElementById('chk-h1').checked,
                h2: document.getElementById('chk-h2').checked,
                body_text: document.getElementById('chk-body').checked,
                links: document.getElementById('chk-links').checked,
                images: document.getElementById('chk-images').checked
            };
            await fetch('/api/config', { 
                method: 'POST', 
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config) 
            });
            updateUI(); // 設定変更後すぐに再抽出して画面更新
        }

        async function updateUI() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                document.getElementById('task-count').innerText = data.tasks.length;

                // ボタン制御
                const btn = document.getElementById('exec-btn');
                if (data.is_running) {
                    btn.disabled = true;
                    btn.className = "w-full bg-slate-400 text-white font-bold py-3 px-4 rounded cursor-not-allowed";
                    btn.innerText = "⏳ 実行中...";
                } else {
                    btn.disabled = false;
                    btn.className = "w-full bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white font-bold py-3 px-4 rounded shadow transition";
                    btn.innerText = "▶ 一括処理を実行";
                }

                // タスク描画 (DOMの差分更新によるスクロール維持)
                const tasksDiv = document.getElementById('tasks');
                data.tasks.forEach(t => {
                    const cardId = `task-card-${t.id}`;
                    let cardEl = document.getElementById(cardId);
                    
                    // 状態変化を検知するためのハッシュ（ステータス、サイズ、抽出データ）
                    const stateHash = `${t.statusCode}-${t.size}-${JSON.stringify(t.extracted || {})}`;

                    // 要素がなければ新規作成
                    if (!cardEl) {
                        cardEl = document.createElement('div');
                        cardEl.id = cardId;
                        cardEl.className = "bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md transition";
                        tasksDiv.appendChild(cardEl);
                    }

                    // 状態が変わった場合のみHTMLを更新（これでテキストエリアのスクロールや選択が維持される）
                    if (cardEl.dataset.stateHash !== stateHash) {
                        cardEl.dataset.stateHash = stateHash;

                        let color = 'bg-slate-200 text-slate-600'; // 待機
                        if (t.statusCode === 1) color = 'bg-blue-100 text-blue-700 animate-pulse'; // 実行中
                        else if (t.statusCode === 2) color = 'bg-emerald-100 text-emerald-700'; // 完了
                        else if (t.statusCode === 4) color = 'bg-purple-100 text-purple-700'; // 詳細解析
                        else if (t.statusCode === 3 || t.statusCode === 5) color = 'bg-rose-100 text-rose-700'; // エラー/破綻

                        // 抽出データのHTML生成
                        let extHtml = '';
                        if (t.extracted) {
                            if (t.extracted.title !== undefined) {
                                extHtml += `<div class="text-slate-800 font-bold text-sm mb-1 line-clamp-2">📃 ${t.extracted.title}</div>`;
                            }
                            if (t.extracted.h1 !== undefined) {
                                extHtml += `<div class="text-slate-600 text-xs mb-1 truncate">👑 <span class="font-semibold">H1:</span> ${t.extracted.h1}</div>`;
                            }
                            if (t.extracted.h2 && t.extracted.h2.length > 0) {
                                extHtml += `<div class="text-slate-600 text-xs mb-1 truncate">📌 <span class="font-semibold">H2:</span> ${t.extracted.h2.join(' / ')}</div>`;
                            }
                            if (t.extracted.description !== undefined) {
                                extHtml += `<div class="text-slate-500 text-xs mb-1 line-clamp-2">📝 <span class="font-semibold">Desc:</span> ${t.extracted.description}</div>`;
                            }
                            if (t.extracted.keywords !== undefined && t.extracted.keywords !== "") {
                                extHtml += `<div class="text-slate-500 text-xs mb-2 truncate">🏷️ <span class="font-semibold">Keywords:</span> ${t.extracted.keywords}</div>`;
                            }
                            if (t.extracted.body_text !== undefined) {
                                // 本文の全文表示用スクロールコンテナ
                                extHtml += `<div class="bg-slate-50 border border-slate-200 p-3 rounded text-slate-600 text-xs mb-2 max-h-48 overflow-y-auto custom-scrollbar whitespace-pre-line leading-relaxed shadow-inner font-serif">📄 ${t.extracted.body_text}</div>`;
                            }

                            // リンクと画像を横並びレイアウトに変更
                            let gridHtml = '';
                            if (t.extracted.links && t.extracted.links.length > 0) {
                                gridHtml += `<div>
                                    <div class="font-bold text-slate-400 mb-1">🔗 リンク:</div>
                                    ${t.extracted.links.map(l => `<div class="truncate text-indigo-500 hover:underline"><a href="${l}" target="_blank">${l}</a></div>`).join('')}
                                </div>`;
                            }
                            if (t.extracted.images && t.extracted.images.length > 0) {
                                gridHtml += `<div>
                                    <div class="font-bold text-slate-400 mb-1">🖼️ 画像:</div>
                                    ${t.extracted.images.map(l => `<div class="truncate text-teal-500 hover:underline"><a href="${l}" target="_blank">${l}</a></div>`).join('')}
                                </div>`;
                            }
                            if (gridHtml) {
                                extHtml += `<div class="mt-2 pt-2 border-t border-slate-100 text-xs grid grid-cols-2 gap-2">${gridHtml}</div>`;
                            }
                        }

                        cardEl.innerHTML = `
                            <div class="flex justify-between items-start mb-3 pb-2 border-b border-slate-100">
                                <span class="truncate font-medium text-xs text-slate-500 w-2/3" title="${t.url}">${t.url}</span>
                                <div class="flex flex-col items-end gap-1">
                                    <span class="px-2 py-0.5 rounded text-[10px] font-bold ${color}">${t.status}</span>
                                    ${t.size > 0 ? `<span class="text-slate-400 text-[10px]">${(t.size/1024).toFixed(1)} KB</span>` : ''}
                                </div>
                            </div>
                            ${extHtml || '<div class="text-slate-400 text-xs italic">データ未取得</div>'}
                        `;
                    }
                });

                // ドメインペナルティ描画
                const ruinDiv = document.getElementById('ruin-scores');
                if (Object.keys(data.ruin_scores).length === 0) {
                    ruinDiv.innerHTML = '<div class="text-xs text-slate-500">現在ペナルティはありません</div>';
                } else {
                    ruinDiv.innerHTML = Object.entries(data.ruin_scores).map(([d, s]) => 
                        `<div class="flex justify-between text-xs border-b border-slate-700 pb-1">
                            <span class="truncate text-slate-300 w-3/4">${d}</span>
                            <span class="text-rose-400 font-bold">LV.${s}</span>
                        </div>`
                    ).join('');
                }

                // ログ描画
                const logsDiv = document.getElementById('logs');
                const wasScrolledToBottom = logsDiv.scrollHeight - logsDiv.clientHeight <= logsDiv.scrollTop + 1;
                logsDiv.innerHTML = data.logs.map(l => `<div>${l}</div>`).join('');
                if (wasScrolledToBottom) logsDiv.scrollTop = logsDiv.scrollHeight;

            } catch(e) { console.error(e); }
        }

        // 1秒ごとに自動更新
        setInterval(updateUI, 1000);
        updateUI();
    </script>
</body>
</html>
"""

# ==========================================
# Webサーバー ハンドラー
# ==========================================
class ScraperAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # 不要なHTTPアクセスログを非表示

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            data = {
                'tasks': system.get_results(),
                'logs': system.logs,
                'ruin_scores': system.domain_ruin_scores,
                'is_running': system.exec_thread.is_alive() if system.exec_thread else False
            }
            self.wfile.write(json.dumps(data).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/add':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            req = json.loads(post_data.decode('utf-8'))
            url = req.get('url', '')
            if url.startswith('http'):
                system.add_task(url)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode('utf-8'))
            
        elif self.path == '/api/execute':
            system.start_execution()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'started'}).encode('utf-8'))
            
        elif self.path == '/api/config':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            req = json.loads(post_data.decode('utf-8'))
            # UIから送られた抽出設定でサーバー側を更新
            system.extract_options.update(req)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode('utf-8'))


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

def main():
    PORT = 8000
    server = ThreadedHTTPServer(('localhost', PORT), ScraperAPIHandler)
    print("=====================================")
    print(" 高効率ウェブスクレイパー UI版 起動")
    print(f" URL: http://localhost:{PORT}")
    print(" 終了するには Ctrl+C を押してください")
    print("=====================================")
    
    # ブラウザを自動で開く
    webbrowser.open(f"http://localhost:{PORT}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nシステムを終了します。")
        server.server_close()

if __name__ == "__main__":
    main()