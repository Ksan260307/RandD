import os
import json
import asyncio
import hashlib
import re
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
import uvicorn
from plyer import notification
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# 実行ファイル（app.py）のディレクトリを基準にする
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
BROWSER_STATE_FILE = os.path.join(BASE_DIR, "browser_state.json")

# ==========================================
# フロントエンド HTML (Pythonコード内に統合)
# ==========================================
# ※エスケープ文字の影響を防ぐため raw 文字列(r)を使用
HTML_CONTENT = r"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIスマートメールモニター (自動ブラウザ版)</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
        ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
        .glass-panel {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        }
    </style>
</head>
<body class="bg-slate-100 h-screen font-sans text-slate-800 overflow-hidden flex flex-col">

    <header class="bg-indigo-600 text-white p-4 shadow-md z-10 flex justify-between items-center">
        <h1 class="text-xl font-bold flex items-center gap-2">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
            AIスマートモニター (自律ブラウザ・エンジン)
        </h1>
        <div class="text-sm opacity-80" id="status-indicator">システム稼働中...</div>
    </header>

    <div class="flex flex-1 overflow-hidden">
        <aside class="w-[420px] shrink-0 border-r border-slate-200 flex flex-col bg-white overflow-y-auto">
            <form id="settings-form">
                <div class="p-4 border-b border-slate-100 bg-slate-50">
                    <h2 class="text-sm font-bold text-slate-500 mb-3 uppercase tracking-wider flex items-center gap-2">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                        自動取得設定
                    </h2>
                    <div class="space-y-4">
                        
                        <!-- 複数フォルダ（URL）設定エリア -->
                        <div>
                            <label class="text-xs text-slate-500 mb-2 flex justify-between items-center">
                                <span>監視するWebページ(OWA)のURL</span>
                                <button type="button" onclick="addFolderInput()" class="text-indigo-600 hover:text-indigo-800 font-bold bg-indigo-50 px-2 py-1 rounded transition">+ 追加</button>
                            </label>
                            <div id="folder-list" class="space-y-2 max-h-48 overflow-y-auto p-1">
                                <!-- JSで動的に追加 -->
                            </div>
                        </div>

                        <!-- ログイン補助アクション -->
                        <div class="bg-indigo-50 p-3 rounded border border-indigo-100 flex flex-col gap-2">
                            <span class="text-xs text-indigo-800 font-bold">⚠️ Outlook等のログインが必要な場合</span>
                            <span class="text-[10px] text-indigo-600">下のボタンを押すと認証用ブラウザが立ち上がります。ログインが完了すると状態が自動保存され、以降は裏側で自動取得されます。</span>
                            <button type="button" onclick="triggerBrowserLogin()" class="bg-white border border-indigo-300 text-indigo-700 hover:bg-indigo-100 px-3 py-1.5 rounded text-xs font-bold transition shadow-sm">
                                1番目のURLでログイン状態を構築する
                            </button>
                        </div>

                        <hr class="border-slate-200">

                        <div>
                            <label class="block text-xs text-slate-500 mb-1">重要ワード (カンマ区切り)</label>
                            <input type="text" id="alert_words" class="w-full px-3 py-2 text-sm border border-slate-300 rounded focus:outline-none focus:border-rose-500" placeholder="例: 重要,更新,エラー">
                        </div>
                        <div>
                            <label class="block text-xs text-slate-500 mb-1">自動確認間隔 (秒) ※ブラウザ起動負荷を考慮し長め推奨</label>
                            <input type="number" id="polling_interval" min="30" class="w-full px-3 py-2 text-sm border border-slate-300 rounded focus:outline-none focus:border-indigo-500">
                        </div>
                        <button type="submit" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded text-sm transition mt-2 font-bold shadow-sm flex justify-center items-center gap-2">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"></path></svg>
                            設定を保存
                        </button>
                    </div>
                </div>
            </form>

            <div class="p-2 border-b border-slate-200 bg-slate-50 flex justify-between items-center">
                <span class="text-xs font-bold text-slate-500 ml-2 uppercase">新着情報 (疑似メール)</span>
                <button onclick="fetchMails()" class="text-xs text-indigo-600 border border-indigo-200 bg-indigo-50 hover:bg-indigo-100 px-3 py-1 rounded transition">
                    手動更新
                </button>
            </div>

            <div class="flex-1 overflow-y-auto p-2 min-h-[300px]" id="mail-list">
                <div class="p-4 text-center text-slate-400 text-sm">情報を読み込み中...</div>
            </div>
        </aside>

        <main class="flex-1 bg-slate-50 p-6 overflow-y-auto relative" id="main-content">
            <div class="absolute inset-0 flex items-center justify-center text-slate-400" id="empty-state">
                <div class="text-center">
                    <svg class="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                    <p>左のリストから項目を選択すると、<br>ここに詳細が表示されます。</p>
                </div>
            </div>

            <div id="detail-view" class="hidden h-full flex-col max-w-4xl mx-auto space-y-4">
                <div class="glass-panel p-6 rounded-xl">
                    <h2 class="text-2xl font-bold text-slate-800 mb-2 flex items-center gap-2" id="detail-subject">件名</h2>
                    <div class="flex justify-between items-center text-sm text-slate-500 border-t border-slate-100 pt-3 mt-3">
                        <span id="detail-sender" class="font-medium text-indigo-600 break-all">送信者 (URL)</span>
                        <span id="detail-time" class="shrink-0 ml-4">日時</span>
                    </div>
                </div>

                <div class="glass-panel p-6 rounded-xl flex-1 overflow-y-auto">
                    <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">取得テキスト (最大10000文字)</h3>
                    <div id="detail-body" class="text-slate-600 text-sm whitespace-pre-wrap leading-relaxed font-mono">
                        読込中...
                    </div>
                </div>
            </div>
        </main>
    </div>

    <script>
        const API_BASE = '/api';

        // 実行環境（iframe等）でブロックされる alert() の代替となるカスタム通知UI
        function showMessage(msg, isError = false) {
            let container = document.getElementById('toast-container');
            if (!container) {
                container = document.createElement('div');
                container.id = 'toast-container';
                container.className = 'fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none';
                document.body.appendChild(container);
            }
            const toast = document.createElement('div');
            toast.className = `${isError ? 'bg-rose-500' : 'bg-indigo-600'} text-white px-4 py-3 rounded shadow-lg transition-opacity duration-300 opacity-0 pointer-events-auto text-sm max-w-sm whitespace-pre-wrap`;
            toast.innerText = msg;
            container.appendChild(toast);
            
            setTimeout(() => toast.classList.remove('opacity-0'), 10);
            setTimeout(() => {
                toast.classList.add('opacity-0');
                setTimeout(() => toast.remove(), 300);
            }, 5000);
        }

        // HTML（DOM）の読み込みが完全に終わってからイベントリスナーを登録する
        document.addEventListener('DOMContentLoaded', async () => {
            const form = document.getElementById('settings-form');
            if (form) {
                form.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const folders = [];
                    document.querySelectorAll('.folder-row').forEach(row => {
                        const name = row.querySelector('.folder-name').value.trim();
                        const url = row.querySelector('.folder-url').value.trim();
                        if (url) folders.push({ name: name || '名称未設定', url: url });
                    });

                    const payload = {
                        folders: folders,
                        polling_interval: parseInt(document.getElementById('polling_interval').value, 10),
                        alert_words: document.getElementById('alert_words').value
                    };

                    try {
                        const res = await fetch(`${API_BASE}/settings`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload)
                        });
                        const result = await res.json();
                        showMessage(result.message);
                        fetchMails();
                    } catch (e) {
                        showMessage('設定の保存に失敗しました。', true);
                    }
                });
            }

            await fetchSettings();
            fetchMails();
            setInterval(fetchMails, 30000); 
        });

        function renderFolderInputs(folders) {
            const list = document.getElementById('folder-list');
            list.innerHTML = '';
            if(!folders || folders.length === 0) {
                addFolderInput('メイン', 'https://outlook.cloud.microsoft/mail/');
                return;
            }
            folders.forEach(f => addFolderInput(f.name, f.url));
        }

        function addFolderInput(name = '', url = '') {
            const list = document.getElementById('folder-list');
            const div = document.createElement('div');
            div.className = "flex gap-2 items-center folder-row group";
            div.innerHTML = `
                <input type="text" placeholder="名前" value="${name}" class="w-1/4 px-2 py-1 text-sm border border-slate-300 rounded focus:outline-none focus:border-indigo-500 folder-name">
                <input type="text" placeholder="https://..." value="${url}" class="flex-1 px-2 py-1 text-sm border border-slate-300 rounded focus:outline-none focus:border-indigo-500 folder-url">
                <button type="button" onclick="this.parentElement.remove()" class="text-slate-300 hover:text-red-500 transition px-1" title="削除">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                </button>
            `;
            list.appendChild(div);
        }

        async function fetchSettings() {
            try {
                const res = await fetch(`${API_BASE}/settings`);
                const data = await res.json();
                renderFolderInputs(data.folders);
                document.getElementById('polling_interval').value = data.polling_interval || 60;
                document.getElementById('alert_words').value = data.alert_words || '';
            } catch (e) {
                renderFolderInputs([]);
            }
        }

        // UIアクション：ブラウザ自動保存プロセスの起動
        async function triggerBrowserLogin() {
            const firstUrlInput = document.querySelector('.folder-url');
            const url = firstUrlInput ? firstUrlInput.value : 'https://outlook.cloud.microsoft/mail/';
            
            if (!url) {
                showMessage("URLを入力してください。", true);
                return;
            }

            showMessage("専用のブラウザを起動します。画面が立ち上がったらログインを完了させてください。\nログイン成功（またはメール一覧が表示）されると、ブラウザは自動的に閉じ、状態が保存されます。");
            
            try {
                const res = await fetch(`${API_BASE}/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url })
                });
                const result = await res.json();
                if(result.status !== 'success'){
                    showMessage("起動に失敗しました: " + result.message, true);
                }
            } catch (e) {
                showMessage("通信エラーが発生しました。", true);
            }
        }

        async function fetchMails() {
            try {
                const res = await fetch(`${API_BASE}/mails`);
                const data = await res.json();
                renderMailList(data.mails);
                const timeStr = new Date().toLocaleTimeString('ja-JP', { hour: '2-digit', minute:'2-digit', second:'2-digit' });
                document.getElementById('status-indicator').innerText = `最終確認: ${timeStr}`;
            } catch (e) {
                document.getElementById('mail-list').innerHTML = `<div class="p-4 text-center text-red-500 text-sm">通信エラー</div>`;
            }
        }

        function renderMailList(mails) {
            const container = document.getElementById('mail-list');
            container.innerHTML = '';

            if (!mails || mails.length === 0) {
                container.innerHTML = `<div class="p-4 text-center text-slate-400 text-sm">表示する情報がありません<br>(ワーカーの自動取得を待機中...)</div>`;
                return;
            }

            mails.forEach(mail => {
                const isUnread = mail.unread;
                const isAlert = mail.is_alert;
                
                let borderClass = 'border-l-4 border-transparent bg-slate-50 opacity-70';
                let fontClass = 'font-normal text-slate-600';
                let iconHtml = '';

                if (isAlert) {
                    borderClass = 'border-l-4 border-rose-500 bg-rose-50';
                    fontClass = 'font-bold text-rose-800';
                    iconHtml = '<span class="text-rose-600 mr-1 animate-pulse" title="重要ワード検出">❗</span>';
                } else if (isUnread) {
                    borderClass = 'border-l-4 border-indigo-500 bg-white shadow-sm';
                    fontClass = 'font-bold text-slate-800';
                }

                const div = document.createElement('div');
                div.className = `p-3 mb-2 rounded cursor-pointer hover:bg-indigo-50 hover:opacity-100 transition-all ${borderClass}`;
                div.onclick = () => loadMailDetail(mail.id, mail.subject, mail.sender, mail.time, isAlert);
                
                div.innerHTML = `
                    <div class="text-xs text-slate-500 flex justify-between mb-1">
                        <span class="truncate pr-2 font-medium text-indigo-500">${mail.sender}</span>
                        <span class="shrink-0">${mail.time.split(' ')[1] || mail.time}</span>
                    </div>
                    <div class="text-sm truncate ${fontClass}">
                        ${iconHtml}${mail.subject || '(件名なし)'}
                    </div>
                `;
                container.appendChild(div);
            });
        }

        async function loadMailDetail(id, subject, sender, time, isAlert = false) {
            document.getElementById('empty-state').classList.add('hidden');
            document.getElementById('detail-view').classList.remove('hidden');
            document.getElementById('detail-view').classList.add('flex');

            const iconHtml = isAlert ? '<span class="text-rose-600">❗</span>' : '';
            document.getElementById('detail-subject').innerHTML = `${iconHtml} ${subject || '(情報なし)'}`;
            
            document.getElementById('detail-sender').innerHTML = sender.startsWith('http') 
                ? `<a href="${sender}" target="_blank" class="hover:underline flex items-center gap-1">${sender} <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg></a>` 
                : sender;
                
            document.getElementById('detail-time').innerText = time;
            document.getElementById('detail-body').innerText = '読み込み中...';

            try {
                const res = await fetch(`${API_BASE}/detail`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ entry_id: id })
                });
                const data = await res.json();

                if (data.status === 'success') {
                    document.getElementById('detail-body').innerText = data.body;
                    setTimeout(fetchMails, 1000); 
                } else {
                    document.getElementById('detail-body').innerText = data.message || '本文の取得に失敗しました。';
                }
            } catch (e) {
                document.getElementById('detail-body').innerText = '通信エラーが発生しました。';
            }
        }
    </script>
</body>
</html>
"""

# ==========================================
# 高効率状態管理エンジン (設計書思想の実装)
# ==========================================
class SystemState:
    def __init__(self):
        self.active_ids = []           # 監視対象のIDリスト (SoA)
        self.statuses = {}             # 0: 未読, 1: 既読, 2: アーカイブ済（静的履歴）
        self.mail_store = {}           # 収穫されたエントロピー(データ)をメモリ内に保持
        self.folders = []              # [{"name": "メイン", "url": "https://..."}]
        self.base_interval = 60        # 局所時間制御（ポーリング間隔）
        self.alert_words = []          # 変動強度（Δ）を高めるトリガーワード
        self.is_running = True
        
        # タイムゾーンと最終確認時刻の初期化
        self.jst = timezone(timedelta(hours=9))
        self.last_check_time = datetime.now(self.jst)
        self.load_settings()

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.folders = data.get("folders", [])
                    self.base_interval = data.get("polling_interval", 60)
                    self.alert_words = data.get("alert_words", [])
            except Exception as e:
                print(f"設定読込エラー: {e}")

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "folders": self.folders,
                    "polling_interval": self.base_interval,
                    "alert_words": self.alert_words,
                }, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"設定保存エラー: {e}")

state = SystemState()
app = FastAPI()

# ==========================================
# データモデル
# ==========================================
class FolderModel(BaseModel):
    name: str
    url: str

class SettingsModel(BaseModel):
    folders: List[FolderModel]
    polling_interval: int
    alert_words: str

class MailDetailRequest(BaseModel):
    entry_id: str

class LoginRequest(BaseModel):
    url: str

# ==========================================
# DOM解析エンジン (OWA対応)
# ==========================================
def parse_owa_time(time_str: str, jst: timezone) -> datetime:
    """ "2026/05/28 (木) 16:46" などの文字列から datetime を生成する """
    if not time_str:
        return datetime.now(jst)
    
    # 正規表現で YYYY/MM/DD と HH:MM を抽出
    match = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2}).*?(\d{1,2}):(\d{2})', time_str)
    if match:
        try:
            year, month, day, hour, minute = map(int, match.groups())
            return datetime(year, month, day, hour, minute, tzinfo=jst)
        except ValueError:
            pass
    return datetime.now(jst)


def process_scraped_html(html_content: str, name: str, url: str) -> tuple:
    """取得したHTML(JSレンダリング後)をパースしてシステム状態へ統合する"""
    soup = BeautifulSoup(html_content, "html.parser")
    new_mail_count = 0
    alert_mail_count = 0
    latest_subject = ""
    
    # 1. Office 365 (OWA) の特殊なHTML構造の解析
    owa_elements = soup.find_all('div', role='option')
    
    if owa_elements:
        for el in owa_elements[:15]:
            aria_label = el.get('aria-label', '')
            
            subj_el = el.find('span', class_='TtcXM')
            subject = subj_el.get_text(strip=True) if subj_el else ""
            
            sender_el = el.find('span', title=lambda x: x and '@' in x)
            if not sender_el: sender_el = el.find('span', class_=lambda c: c and 'ESO13' in c)
            sender = sender_el.get_text(strip=True) if sender_el else "Unknown"
            
            body_el = el.find('span', class_='FqgPc')
            body = body_el.get_text(strip=True) if body_el else ""
            
            time_el = el.find('span', class_='_rWRU')
            time_str = time_el.get('title') if time_el else datetime.now(state.jst).strftime("%Y-%m-%d %H:%M")
            
            # 【日時の比較】最終確認時刻の10分前より古いものは抽出しない（時刻の丸めによる漏れ防止）
            mail_dt = parse_owa_time(time_str, state.jst)
            if mail_dt < state.last_check_time - timedelta(minutes=10):
                continue
            
            if not subject and aria_label:
                subject = aria_label[:40] + "..."
                body = aria_label
                
            if not subject: continue
                
            # 一意なIDの生成（URL＋件名＋送信者＋日時）で重複を確実に排除
            entry_id = hashlib.md5(f"{url}_{subject}_{sender}_{time_str}".encode('utf-8')).hexdigest()
            
            if entry_id not in state.active_ids and entry_id not in state.statuses:
                state.active_ids.insert(0, entry_id)
                state.statuses[entry_id] = 0
                state.mail_store[entry_id] = {"subject": f"[{name}] {subject}", "sender": sender, "time": time_str, "body": body}
                new_mail_count += 1
                latest_subject = subject
                if any(word.lower() in subject.lower() for word in state.alert_words):
                    alert_mail_count += 1

    # 2. 汎用的なWebサイトの解析 (フォールバック)
    else:
        elements = soup.find_all(['h1', 'h2', 'h3'])
        if not elements: elements = [a for a in soup.find_all('a') if len(a.get_text(strip=True)) > 15]

        for el in elements[:5]:
            subject = el.get_text(strip=True)
            if not subject or len(subject) < 5: continue
                
            entry_id = hashlib.md5(f"{url}_{subject}".encode('utf-8')).hexdigest()
            if entry_id not in state.active_ids and entry_id not in state.statuses:
                state.active_ids.insert(0, entry_id)
                state.statuses[entry_id] = 0
                parent = el.find_parent()
                body = parent.get_text(separator="\n", strip=True) if parent else subject
                state.mail_store[entry_id] = {"subject": f"[{name}] {subject}", "sender": url, "time": datetime.now(state.jst).strftime("%Y-%m-%d %H:%M"), "body": body}
                new_mail_count += 1
                latest_subject = subject
                if any(word.lower() in subject.lower() for word in state.alert_words):
                    alert_mail_count += 1

    return new_mail_count, alert_mail_count, latest_subject

# ==========================================
# ブラウザ自動操作ワーカー (Playwright)
# ==========================================
async def auto_scraping_worker():
    """
    バックグラウンドで不可視のブラウザを起動し、定期的にJSレンダリング後の完全なDOMを取得する
    """
    try:
        async with async_playwright() as p:
            # ヘッドレス（不可視）モードで起動
            browser = await p.chromium.launch(headless=True)
            
            while state.is_running:
                try:
                    # ログインCookie（状態）が存在すれば読み込んでコンテキストを作成
                    if os.path.exists(BROWSER_STATE_FILE):
                        context = await browser.new_context(storage_state=BROWSER_STATE_FILE)
                    else:
                        context = await browser.new_context()
                    
                    total_new = 0
                    total_alert = 0
                    last_subj = ""
                    
                    # 今回のポーリング開始時刻を記録
                    current_check_time = datetime.now(state.jst)

                    for folder in state.folders:
                        name = folder.get("name", "Unknown")
                        url = folder.get("url", "")
                        if not url.startswith("http"): continue
                        
                        try:
                            page = await context.new_page()
                            # タイムアウトを設けてアクセス
                            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            
                            # OWAの場合はメールリストの描画完了を待つ
                            try:
                                await page.wait_for_selector('div[role="option"]', timeout=10000)
                            except:
                                pass # OWA以外の汎用サイトの場合はそのまま進む
                            
                            html_content = await page.content()
                            await page.close()
                            
                            # パース処理へ投げる
                            n_count, a_count, l_subj = process_scraped_html(html_content, name, url)
                            total_new += n_count
                            total_alert += a_count
                            if l_subj: last_subj = l_subj

                        except Exception as e:
                            print(f"Scraping Fetch Error [{name}]: {e}")
                            try:
                                await page.close()
                            except: pass

                    await context.close()

                    # 通知ロジック
                    if total_new > 0:
                        title = f"🚨 監視先更新アラート ({total_alert}件 / 全{total_new}件)" if total_alert > 0 else f"新着情報の取得: {total_new}件"
                        notification.notify(title=title, message=f"最新: {last_subj}", app_name="Web監視チェッカー", timeout=5)
                        print(f"新着情報: {total_new}件")

                    # 最終確認時刻を更新（取得漏れを防ぐため、1分のマージンを持たせて更新）
                    state.last_check_time = current_check_time - timedelta(minutes=1)

                except Exception as e:
                    print(f"Worker Loop Error: {e}")
                
                # 局所時間制御（待機）
                await asyncio.sleep(state.base_interval)
                
    except Exception as e:
        print(f"Playwright Fatal Error: {e}")

# ==========================================
# ログイン状態構築用タスク (UIアクション用)
# ==========================================
async def run_browser_login_task(url: str):
    """
    可視状態のブラウザを起動し、ユーザーのログイン完了を待って状態(Cookie等)を保存する
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False) # ユーザーに見えるように起動
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url)
            
            print("ブラウザを起動しました。ログインを完了させてください。")
            
            # OWA特有のメールリストか、検索バーが表示されるまで待機（最長2分）
            try:
                await page.wait_for_selector('div[role="option"], input[placeholder="検索"]', timeout=120000)
                print("ログイン状態の検知に成功しました。Cookieを保存します。")
                await context.storage_state(path=BROWSER_STATE_FILE)
            except Exception as e:
                print(f"要素待機タイムアウトまたは手動クローズ: {e}")
            
            await browser.close()
    except Exception as e:
        print(f"Login task error: {e}")

# ==========================================
# FastAPI エンドポイント
# ==========================================
@app.on_event("startup")
async def startup_event():
    # FastAPIのイベントループ上でスクレイピングワーカーを並行起動
    asyncio.create_task(auto_scraping_worker())

@app.on_event("shutdown")
def shutdown_event():
    state.is_running = False

@app.get("/")
def serve_frontend():
    return HTMLResponse(content=HTML_CONTENT)

@app.get("/api/settings")
def get_settings():
    return {"folders": state.folders, "polling_interval": state.base_interval, "alert_words": ",".join(state.alert_words)}

@app.post("/api/settings")
def update_settings(settings: SettingsModel):
    state.folders = [{"name": f.name, "url": f.url} for f in settings.folders]
    state.base_interval = settings.polling_interval
    state.alert_words = [w.strip() for w in settings.alert_words.split(",") if w.strip()]
    state.save_settings()
    return {"status": "success", "message": "監視設定を保存しました。"}

@app.post("/api/login")
async def trigger_login(req: LoginRequest):
    """設定画面のボタンから呼ばれ、バックグラウンドでブラウザ起動タスクを生成する"""
    asyncio.create_task(run_browser_login_task(req.url))
    return {"status": "success", "message": "ログインブラウザを起動中..."}

@app.get("/api/mails")
def get_mails():
    mail_list = []
    for entry_id in state.active_ids[:15]:
        data = state.mail_store.get(entry_id)
        if not data: continue
        subject, sender = data["subject"], data["sender"]
        
        is_alert = False
        if state.alert_words:
            search_text = f"{subject} {sender}".lower()
            is_alert = any(w.lower() in search_text for w in state.alert_words)
        
        mail_list.append({
            "id": entry_id, "subject": subject, "sender": sender,
            "time": data["time"], "unread": state.statuses.get(entry_id) == 0, "is_alert": is_alert
        })
    return {"mails": mail_list}

@app.post("/api/detail")
def get_mail_detail(req: MailDetailRequest):
    if req.entry_id not in state.mail_store: return {"status": "error", "message": "データが見つかりません。"}
        
    data = state.mail_store[req.entry_id]
    body = data["body"]
    
    if req.entry_id in state.active_ids and state.statuses.get(req.entry_id) == 0:
        state.statuses[req.entry_id] = 1 # 既読化
        
    return {
        "status": "success", "subject": data["subject"],
        "body": body[:10000] + ("\n...[続きは省略]..." if len(body) > 10000 else "")
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)