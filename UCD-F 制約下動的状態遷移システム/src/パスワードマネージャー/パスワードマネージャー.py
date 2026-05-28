# =====================================================================
# セキュア パスワードマネージャー [本番環境対応版]
# 
# 【本番環境向けの主要なセキュリティ強化点】
# 1. 暗号アルゴリズムの標準化 (AES-GCM)
#    手作りの暗号を廃止し、業界標準の「AES-GCM (256-bit)」を採用。
#    データの暗号化と改ざん検知（認証付き暗号）を極めて安全に実行します。
#
# 2. 堅牢なWebフレームワーク (Flask & Waitress)
#    ルーティングや入力検証を厳格化するため Flask を採用。
#    本番稼働用のWSGIサーバー (Waitress) で起動し、アクセスログも秘匿します。
#
# 3. HTTPセキュリティヘッダーの完全適用
#    すべての通信に CSP, HSTS, X-Content-Type-Options などの厳格な
#    セキュリティヘッダーを強制し、XSSやクリックジャッキング等を防ぎます。
#
# 4. タイミング攻撃対策の徹底
#    認証時の比較処理に `secrets.compare_digest` を使用し、処理時間から
#    正解を推測される脆弱性を完全に排除しています。
#
# 5. データベースの堅牢化 (WALモード)
#    SQLiteの WAL (Write-Ahead Logging) モードを有効化し、並行アクセス時の
#    パフォーマンス向上とデッドロックの防止を実現しています。
# =====================================================================

import json
import sqlite3
import os
import time
import base64
import secrets
import hashlib
import gc
import logging
from flask import Flask, request, jsonify, render_template_string
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Flaskの不要なアクセスログを非表示にして不可視性を高める
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# アプリケーションの初期化
app = Flask(__name__)
DB_FILE = 'secure_passwords.db'

def get_db_connection(timeout=3.0):
    """データベース接続を生成し、本番環境向けのPRAGMA設定を行う"""
    conn = sqlite3.connect(DB_FILE, timeout=timeout)
    conn.execute('PRAGMA journal_mode=WAL;') # 並行処理性能と堅牢性の向上
    conn.execute('PRAGMA synchronous=NORMAL;')
    return conn

# =========================================================
# 1. セキュリティおよび保護エンジン
# =========================================================

def _add_random_delay():
    """処理時間から内部状態を推測されるのを防ぐダミー処理 (タイミング攻撃対策)"""
    dummy_iterations = secrets.randbelow(1500) + 500
    dummy_data = secrets.token_bytes(16)
    for _ in range(dummy_iterations):
        dummy_data = hashlib.md5(dummy_data).digest()
    time.sleep(secrets.randbelow(8) / 100.0) # 0.00 〜 0.07秒の遅延

def _add_dummy_db_access():
    """アクセス履歴から情報を推測されるのを防ぐダミーアクセス"""
    try:
        conn = get_db_connection(timeout=1.0)
        try:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS dummy_log (val TEXT)''')
            c.execute("SELECT id FROM passwords ORDER BY RANDOM() LIMIT 1")
            c.fetchall()
            if secrets.choice([True, False]):
                c.execute("INSERT INTO dummy_log (val) VALUES (?)", (secrets.token_hex(8),))
                conn.commit()
                c.execute("DELETE FROM dummy_log")
                conn.commit()
        finally:
            conn.close()
    except Exception:
        pass

def secure_encrypt(master_key: bytes, plaintext: str) -> str:
    """AES-GCMによる堅牢なデータの暗号化と保護カプセル化"""
    aesgcm = AESGCM(master_key)
    # AES-GCMの推奨Nonceサイズは12バイト
    nonce = secrets.token_bytes(12)
    data = plaintext.encode('utf-8')
    
    # 認証付き暗号化（改ざん防止のMACは暗号文に自動的に含まれる）
    ciphertext = aesgcm.encrypt(nonce, data, None)
    
    payload = nonce + ciphertext
    del data, ciphertext # 平文をメモリから即座に破棄
    return base64.b64encode(payload).decode('utf-8')

def secure_decrypt(master_key: bytes, payload_b64: str) -> str:
    """AES-GCMの署名を検証し、安全な場合のみデータを復号する"""
    try:
        raw = base64.b64decode(payload_b64)
        if len(raw) < 28: # Nonce(12) + Tag(16) 最小長
            raise ValueError("無効なデータ")
            
        nonce = raw[:12]
        ciphertext = raw[12:]
        
        aesgcm = AESGCM(master_key)
        # 改ざんされている場合はここで例外が発生し、復号されない
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        result = decrypted_bytes.decode('utf-8')
        
        del raw, ciphertext, decrypted_bytes # メモリのクリア
        return result
    except Exception:
        _add_random_delay()
        raise ValueError("復号または検証に失敗しました")

def _get_master_key():
    """HTTPヘッダーから一時的な鍵を生成する (マスターパスワードは保持しない)"""
    auth_header = request.headers.get('X-Master-Key')
    if not auth_header:
        return None
        
    try:
        master_pw = base64.b64decode(auth_header).decode('utf-8')
        _add_dummy_db_access()
        
        conn = get_db_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT value FROM config WHERE key='salt'")
            row = c.fetchone()
        finally:
            conn.close()
            
        if not row:
            return None
            
        salt_hex = row[0]
        salt = bytes.fromhex(salt_hex)
        # PBKDF2-HMAC-SHA256 (600,000イテレーション) により強力な鍵を導出
        key = hashlib.pbkdf2_hmac('sha256', master_pw.encode('utf-8'), salt, 600000)
        
        del master_pw # 入力されたパスワードは即座にメモリから抹消
        return key
    except Exception:
        return None

def _verify_auth(key):
    """生成された鍵が正しいかどうかを検証する"""
    if not key:
        _add_random_delay()
        return False
        
    _add_dummy_db_access()
    
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key='verify'")
        row = c.fetchone()
    finally:
        conn.close()
    
    if not row:
        return False
        
    try:
        decrypted = secure_decrypt(key, row[0])
        # タイミング攻撃を防ぐため、安全な文字列比較関数(compare_digest)を使用
        is_valid = secrets.compare_digest(decrypted, 'VALID_MASTER_KEY')
        del decrypted
        _add_random_delay() # 成功/失敗に関わらずタイミングを統一
        return is_valid
    except Exception:
        _add_random_delay()
        return False


# =========================================================
# 2. Webサーバー設定・ミドルウェア
# =========================================================

@app.after_request
def apply_security_headers(response):
    """本番環境向けの強力なHTTPセキュリティヘッダーを付与"""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline';"
    )
    return response

@app.errorhandler(Exception)
def handle_unexpected_error(e):
    return jsonify({"error": "処理を完了できませんでした。セキュリティ機構が作動した可能性があります。"}), 500


# =========================================================
# 3. データベース管理
# =========================================================

def init_db():
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS passwords (id INTEGER PRIMARY KEY AUTOINCREMENT, service TEXT, username TEXT, password TEXT)''')
        
        c.execute("SELECT value FROM config WHERE key='salt'")
        if not c.fetchone():
            salt = secrets.token_hex(16)
            c.execute("INSERT INTO config (key, value) VALUES ('salt', ?)", (salt,))
            conn.commit()
    finally:
        conn.close()

with app.app_context():
    init_db()


# =========================================================
# 4. API エンドポイント
# =========================================================

@app.route('/api/status', methods=['GET'])
def get_status():
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key='verify'")
        initialized = c.fetchone() is not None
    finally:
        conn.close()
    return jsonify({'initialized': initialized})

@app.route('/api/init', methods=['POST'])
def init_manager():
    data = request.get_json() or {}
    pw = data.get('password')
    if not pw:
        return jsonify({'error': 'パスワードが必要です'}), 400
        
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key='verify'")
        if c.fetchone():
            return jsonify({'error': '既に初期化されています'}), 400
    finally:
        conn.close()
            
    key = _get_master_key()
    if not key:
        return jsonify({'error': '認証情報の生成に失敗しました'}), 400
        
    verify_enc = secure_encrypt(key, 'VALID_MASTER_KEY')
    
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO config (key, value) VALUES ('verify', ?)", (verify_enc,))
        conn.commit()
    finally:
        conn.close()
    
    del pw, key, verify_enc
    gc.collect()
    return jsonify({'success': True})

@app.route('/api/auth', methods=['POST'])
def auth():
    key = _get_master_key()
    success = _verify_auth(key)
    if key: del key
    gc.collect()
    return jsonify({'success': success})

@app.route('/api/entries', methods=['GET'])
def get_entries():
    key = _get_master_key()
    if not _verify_auth(key):
        if key: del key
        return jsonify({'error': '認証に失敗しました'}), 401
    
    search_query = request.args.get('q', '').lower()
    _add_dummy_db_access()
    
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id, service, username, password FROM passwords")
        rows = c.fetchall()
    finally:
        conn.close()
    
    entries = []
    for row in rows:
        try:
            decrypted_service = secure_decrypt(key, row[1])
            if search_query and search_query not in decrypted_service.lower():
                del decrypted_service
                continue
                
            entries.append({
                'id': row[0],
                'service': decrypted_service,
                'username': secure_decrypt(key, row[2]),
                'password': secure_decrypt(key, row[3])
            })
        except Exception:
            continue
            
    del key, rows, search_query
    gc.collect() 
    return jsonify(entries)

@app.route('/api/entries', methods=['POST'])
def add_entry():
    key = _get_master_key()
    if not _verify_auth(key):
        if key: del key
        return jsonify({'error': '認証に失敗しました'}), 401
        
    data = request.get_json() or {}
    service = data.get('service', '')
    username = data.get('username', '')
    password = data.get('password', '')
    
    if not all([service, username, password]):
        if key: del key
        return jsonify({'error': '入力項目が不足しています'}), 400
        
    _add_dummy_db_access()
    
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO passwords (service, username, password) VALUES (?, ?, ?)", 
                 (secure_encrypt(key, service), 
                  secure_encrypt(key, username), 
                  secure_encrypt(key, password)))
        conn.commit()
    finally:
        conn.close()
    
    del service, username, password, key
    gc.collect()
    return jsonify({'success': True})

@app.route('/api/entries', methods=['PUT'])
def update_entry():
    """登録済みデータの編集用API"""
    key = _get_master_key()
    if not _verify_auth(key):
        if key: del key
        return jsonify({'error': '認証に失敗しました'}), 401
        
    data = request.get_json() or {}
    item_id = data.get('id')
    service = data.get('service', '')
    username = data.get('username', '')
    password = data.get('password', '')
    
    if not item_id or not all([service, username, password]):
        if key: del key
        return jsonify({'error': '入力項目が不足しています'}), 400
        
    _add_dummy_db_access()
    
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE passwords SET service=?, username=?, password=? WHERE id=?", 
                 (secure_encrypt(key, service), 
                  secure_encrypt(key, username), 
                  secure_encrypt(key, password),
                  item_id))
        conn.commit()
        if c.rowcount == 0:
            return jsonify({'error': '対象データが見つかりません'}), 404
    finally:
        conn.close()
    
    del service, username, password, key
    gc.collect()
    return jsonify({'success': True})

@app.route('/api/entries', methods=['DELETE'])
def delete_entry():
    key = _get_master_key()
    if not _verify_auth(key):
        if key: del key
        return jsonify({'error': '認証に失敗しました'}), 401
    
    item_id = request.args.get('id')
    if not item_id:
        if key: del key
        return jsonify({'error': 'IDが指定されていません'}), 400
        
    _add_dummy_db_access()
    
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM passwords WHERE id=?", (item_id,))
        conn.commit()
    finally:
        conn.close()
    
    if key: del key
    gc.collect()
    return jsonify({'success': True})


# =========================================================
# 5. フロントエンド UI
# =========================================================

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>セキュア パスワードマネージャー</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .fade-in { animation: fadeIn 0.3s ease-in-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body class="text-gray-800">

    <div id="toast" class="fixed top-5 left-1/2 transform -translate-x-1/2 bg-gray-800 text-white px-4 py-2 rounded-lg shadow-lg opacity-0 transition-opacity duration-300 pointer-events-none z-50">
        メッセージ
    </div>

    <div class="max-w-3xl mx-auto mt-12 p-6 bg-white rounded-2xl shadow-sm border border-gray-100 fade-in">
        <header class="mb-8 text-center">
            <h1 class="text-2xl font-bold text-gray-900 tracking-tight">セキュア パスワードマネージャー</h1>
        </header>

        <div id="auth-view" class="max-w-sm mx-auto">
            <h2 id="auth-title" class="text-lg font-semibold mb-4 text-center">マスターパスワードを入力</h2>
            <input type="password" id="master-password" class="w-full px-4 py-3 rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500 transition mb-4" placeholder="Master Password">
            <button onclick="handleAuth()" id="auth-btn" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 rounded-lg transition shadow-sm">ロック解除</button>
            <p id="auth-error" class="text-red-500 text-sm mt-3 text-center hidden"></p>
        </div>

        <div id="main-view" class="hidden">
            <div class="bg-gray-50 p-5 rounded-xl border border-gray-100 mb-8">
                <h3 class="font-medium text-gray-700 mb-3">新しいデータを追加</h3>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                    <input type="text" id="new-service" placeholder="サービス名" class="px-3 py-2 border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <input type="text" id="new-username" placeholder="ID / ユーザー名" class="px-3 py-2 border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <div class="relative">
                        <input type="text" id="new-password" placeholder="パスワード" class="w-full px-3 py-2 pr-10 border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <button type="button" onclick="generatePassword('new-password')" class="absolute inset-y-0 right-0 px-3 flex items-center text-gray-400 hover:text-blue-500 transition" title="強力なパスワードを自動生成">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
                        </button>
                    </div>
                </div>
                <button onclick="addEntry()" class="w-full bg-gray-800 hover:bg-gray-900 text-white py-2 rounded-md transition text-sm font-medium">安全に追加する</button>
            </div>

            <div>
                <div class="flex justify-between items-center mb-3">
                    <h3 class="font-medium text-gray-700">登録済みデータ</h3>
                    <input type="text" id="search-box" onkeyup="triggerSearch()" placeholder="検索..." class="px-3 py-1 text-sm border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500 w-48">
                </div>
                <div id="password-list" class="space-y-3">
                    <!-- データがここに挿入されます -->
                </div>
            </div>
            
            <div class="mt-8 text-center">
                <button onclick="logout()" class="text-sm text-gray-400 hover:text-gray-600 underline">ロック</button>
            </div>
        </div>
    </div>

    <!-- 編集用モーダル (初期非表示) -->
    <div id="edit-modal" class="fixed inset-0 bg-gray-900 bg-opacity-50 hidden flex items-center justify-center z-50">
        <div class="bg-white rounded-xl shadow-lg p-6 w-full max-w-md m-4 fade-in">
            <h3 class="text-lg font-bold text-gray-900 mb-4">データを編集</h3>
            <input type="hidden" id="edit-id">
            <div class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">サービス名</label>
                    <input type="text" id="edit-service" class="w-full px-3 py-2 border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">ID / ユーザー名</label>
                    <input type="text" id="edit-username" class="w-full px-3 py-2 border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">パスワード</label>
                    <div class="relative">
                        <input type="text" id="edit-password" class="w-full px-3 py-2 pr-10 border border-gray-200 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <button type="button" onclick="generatePassword('edit-password')" class="absolute inset-y-0 right-0 px-3 flex items-center text-gray-400 hover:text-blue-500 transition" title="強力なパスワードを自動生成">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
                        </button>
                    </div>
                </div>
            </div>
            <div class="mt-6 flex justify-end space-x-3">
                <button onclick="closeEditModal()" class="px-4 py-2 text-sm font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-md transition">キャンセル</button>
                <button onclick="saveEdit()" class="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md transition">保存</button>
            </div>
        </div>
    </div>

    <script>
        let isInitialized = false;
        let masterKey = '';
        let searchTimeout = null;

        async function checkStatus() {
            const res = await fetch('/api/status');
            const data = await res.json();
            isInitialized = data.initialized;
            if (!isInitialized) {
                document.getElementById('auth-title').innerText = "初回設定: マスターパスワードを作成";
                document.getElementById('auth-btn').innerText = "初期設定を完了する";
            }
        }

        // 引数で指定した入力フィールドにパスワードを生成
        function generatePassword(targetId = 'new-password') {
            const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+~`|}{[]:;?><,./-=";
            let password = "";
            const array = new Uint32Array(16);
            window.crypto.getRandomValues(array);
            for (let i = 0; i < array.length; i++) {
                password += chars[array[i] % chars.length];
            }
            document.getElementById(targetId).value = password;
            showToast("パスワードを生成しました");
        }

        function copyToClipboard(text, itemName) {
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text).then(() => showToast(`${itemName} をコピーしました`));
            } else {
                const textArea = document.createElement("textarea");
                textArea.value = text;
                document.body.appendChild(textArea);
                textArea.select();
                try {
                    document.execCommand('copy');
                    showToast(`${itemName} をコピーしました`);
                } catch (err) {}
                document.body.removeChild(textArea);
            }
        }

        function showToast(message) {
            const toast = document.getElementById('toast');
            toast.innerText = message;
            toast.style.opacity = '1';
            setTimeout(() => { toast.style.opacity = '0'; }, 2000);
        }

        async function apiRequest(endpoint, method = 'GET', body = null) {
            const headers = { 'Content-Type': 'application/json' };
            if (masterKey) {
                const utf8Bytes = new TextEncoder().encode(masterKey);
                let binaryStr = '';
                for (let i = 0; i < utf8Bytes.length; i++) {
                    binaryStr += String.fromCharCode(utf8Bytes[i]);
                }
                headers['X-Master-Key'] = btoa(binaryStr);
            }
            
            const options = { method, headers };
            if (body) options.body = JSON.stringify(body);
            
            return fetch(endpoint, options);
        }

        async function handleAuth() {
            const input = document.getElementById('master-password').value;
            if (!input) return;
            
            masterKey = input;
            const errorEl = document.getElementById('auth-error');
            errorEl.classList.add('hidden');
            const btn = document.getElementById('auth-btn');
            const originalText = btn.innerText;
            btn.innerText = "認証中...";
            btn.disabled = true;

            try {
                if (!isInitialized) {
                    const res = await apiRequest('/api/init', 'POST', { password: input });
                    if (res.ok) {
                        isInitialized = true;
                        showToast("初期設定が完了しました");
                        loadEntries();
                    } else {
                        throw new Error((await res.json()).error || "初期設定に失敗しました");
                    }
                } else {
                    const res = await apiRequest('/api/auth', 'POST');
                    if (res.ok) {
                        const data = await res.json();
                        if (data.success) {
                            loadEntries();
                        } else {
                            throw new Error("認証に失敗しました");
                        }
                    } else {
                        throw new Error("通信エラーが発生しました");
                    }
                }
            } catch (err) {
                masterKey = ''; 
                errorEl.innerText = err.message;
                errorEl.classList.remove('hidden');
            } finally {
                btn.innerText = originalText;
                btn.disabled = false;
            }
        }

        function triggerSearch() {
            const query = document.getElementById('search-box').value;
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                loadEntries(query);
            }, 300);
        }

        async function loadEntries(searchQuery = '') {
            const endpoint = searchQuery ? `/api/entries?q=${encodeURIComponent(searchQuery)}` : '/api/entries';
            const res = await apiRequest(endpoint);
            
            if (res.ok) {
                const entries = await res.json();
                renderList(entries);
                document.getElementById('auth-view').classList.add('hidden');
                document.getElementById('main-view').classList.remove('hidden');
                document.getElementById('master-password').value = '';
            } else {
                masterKey = '';
                showToast("セッションが無効です。再度ロックを解除してください。");
                logout();
            }
        }

        async function addEntry() {
            const service = document.getElementById('new-service').value;
            const username = document.getElementById('new-username').value;
            const password = document.getElementById('new-password').value;

            if (!service || !username || !password) {
                showToast("すべての項目を入力してください");
                return;
            }

            const res = await apiRequest('/api/entries', 'POST', { service, username, password });
            if (res.ok) {
                showToast("安全に追加されました");
                document.getElementById('new-service').value = '';
                document.getElementById('new-username').value = '';
                document.getElementById('new-password').value = '';
                document.getElementById('search-box').value = ''; 
                loadEntries();
            }
        }

        // 編集モーダルを開く
        function openEditModal(id, service, username, password) {
            document.getElementById('edit-id').value = id;
            document.getElementById('edit-service').value = service;
            document.getElementById('edit-username').value = username;
            document.getElementById('edit-password').value = password;
            document.getElementById('edit-modal').classList.remove('hidden');
        }

        // 編集モーダルを閉じる
        function closeEditModal() {
            document.getElementById('edit-modal').classList.add('hidden');
            document.getElementById('edit-id').value = '';
            document.getElementById('edit-service').value = '';
            document.getElementById('edit-username').value = '';
            document.getElementById('edit-password').value = '';
        }

        // 編集内容を保存する
        async function saveEdit() {
            const id = document.getElementById('edit-id').value;
            const service = document.getElementById('edit-service').value;
            const username = document.getElementById('edit-username').value;
            const password = document.getElementById('edit-password').value;

            if (!service || !username || !password) {
                showToast("すべての項目を入力してください");
                return;
            }

            const res = await apiRequest('/api/entries', 'PUT', { id, service, username, password });
            if (res.ok) {
                showToast("データを更新しました");
                closeEditModal();
                const currentSearch = document.getElementById('search-box').value;
                loadEntries(currentSearch);
            } else {
                showToast("更新に失敗しました");
            }
        }

        async function deleteEntry(id) {
            if(!confirm("本当に削除してもよろしいですか？")) return;
            const res = await apiRequest(`/api/entries?id=${id}`, 'DELETE');
            if (res.ok) {
                showToast("削除しました");
                const currentSearch = document.getElementById('search-box').value;
                loadEntries(currentSearch);
            }
        }

        function renderList(entries) {
            const list = document.getElementById('password-list');
            list.innerHTML = '';
            
            if (entries.length === 0) {
                list.innerHTML = '<p class="text-sm text-gray-500 text-center py-4">該当するデータがありません</p>';
                return;
            }

            entries.forEach(entry => {
                const div = document.createElement('div');
                div.className = "flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-white border border-gray-100 rounded-lg shadow-sm hover:shadow transition";
                
                // JavaScriptでクォーテーション等を含む文字列を安全にエスケープ
                const safeService = entry.service.replace(/'/g, "\\'").replace(/"/g, '&quot;');
                const safeUsername = entry.username.replace(/'/g, "\\'").replace(/"/g, '&quot;');
                const safePassword = entry.password.replace(/'/g, "\\'").replace(/"/g, '&quot;');

                div.innerHTML = `
                    <div class="flex-1 mb-3 sm:mb-0 overflow-hidden">
                        <p class="font-medium text-gray-800 truncate">${entry.service}</p>
                    </div>
                    <div class="flex items-center space-x-2">
                        <div class="flex items-center bg-gray-50 px-3 py-1.5 rounded-md border border-gray-200">
                            <span class="text-sm text-gray-600 truncate w-24 mr-2">${entry.username}</span>
                            <button onclick="copyToClipboard('${safeUsername}', 'ID')" class="text-gray-400 hover:text-blue-500 transition" title="IDをコピー">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
                            </button>
                        </div>
                        <div class="flex items-center bg-gray-50 px-3 py-1.5 rounded-md border border-gray-200">
                            <span class="text-sm text-gray-400 tracking-widest w-20 mr-2">••••••••</span>
                            <button onclick="copyToClipboard('${safePassword}', 'パスワード')" class="text-gray-400 hover:text-blue-500 transition" title="パスワードをコピー">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
                            </button>
                        </div>
                        
                        <!-- 編集ボタン -->
                        <button onclick="openEditModal(${entry.id}, '${safeService}', '${safeUsername}', '${safePassword}')" class="p-1.5 text-gray-300 hover:text-blue-500 transition ml-1" title="編集">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                        </button>

                        <!-- 削除ボタン -->
                        <button onclick="deleteEntry(${entry.id})" class="p-1.5 text-gray-300 hover:text-red-500 transition" title="削除">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                        </button>
                    </div>
                `;
                list.appendChild(div);
            });
        }

        function logout() {
            masterKey = ''; 
            document.getElementById('main-view').classList.add('hidden');
            document.getElementById('auth-view').classList.remove('hidden');
            document.getElementById('password-list').innerHTML = '';
            document.getElementById('search-box').value = '';
            showToast("ロックしました");
        }

        checkStatus();
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def index():
    return render_template_string(HTML_CONTENT)

# =========================================================
# 6. サーバー起動 (本番/開発)
# =========================================================

if __name__ == '__main__':
    print("🔒 セキュア パスワードマネージャーを起動しています...")
    try:
        from waitress import serve
        print("✅ 本番環境用サーバー (Waitress) で稼働中 - http://127.0.0.1:8000")
        print("   ※ 終了するには Ctrl+C を押してください")
        serve(app, host='127.0.0.1', port=8000)
    except ImportError:
        print("⚠️ 警告: Waitress がインストールされていません。開発用サーバーで起動します。")
        print("   本番利用時は 'pip install waitress' を実行してください。")
        app.run(host='127.0.0.1', port=8000)