import os
import sys
import re
import concurrent.futures
import fnmatch
import shutil
import threading
import webbrowser
from pathlib import Path

# Webサーバー・API用ライブラリ
try:
    from flask import Flask, request, jsonify, render_template_string
except ImportError:
    print("エラー: Flaskライブラリがインストールされていません。")
    print("以下のコマンドを実行してインストールしてください:")
    print("pip install flask")
    sys.exit(1)

# 文字コード判定のフォールバック用ライブラリ
try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False

# ベースとなる除外ディレクトリ群
BASE_EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode", "build", "dist"}

app = Flask(__name__)

# ==========================================
# Core Logic (バックエンドの高速検索/置換処理)
# ==========================================

def detect_encoding(raw_bytes: bytes) -> str:
    """バイト列から最適なエンコーディングを推論する"""
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff"):
        return "utf-16"

    try:
        raw_bytes.decode("utf-8", errors="strict")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    if HAS_CHARDET:
        result = chardet.detect(raw_bytes[:4096])
        if result and result["encoding"]:
            enc = result["encoding"].lower()
            if enc in ("shift_jis", "shift-jis", "sjis"):
                return "cp932" 
            return enc

    for enc in ("cp932", "euc-jp", "iso-2022-jp", "latin-1"):
        try:
            raw_bytes[:4096].decode(enc, errors="strict")
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
            
    return "utf-8"

def execute_replace_single(file_path_str: str, pattern_str: str, flags: int, replace_str: str, encoding: str, make_backup: bool) -> dict:
    """単一ファイルに対する置換の実行"""
    file_path = Path(file_path_str)
    try:
        pattern = re.compile(pattern_str, flags)
        with open(file_path, "r", encoding=encoding, errors="surrogateescape") as f:
            content = f.read()
            
        new_content, count = pattern.subn(replace_str, content)
        
        if count > 0:
            if make_backup:
                backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                shutil.copy2(file_path, backup_path)
                
            with open(file_path, "w", encoding=encoding, errors="surrogateescape") as f:
                f.write(new_content)
            return {"file": file_path.name, "count": count, "status": "success"}
        return {"file": file_path.name, "count": 0, "status": "no_match"}
    except Exception as e:
        return {"file": file_path.name, "count": 0, "status": "error", "message": str(e)}

def process_file_worker(file_path_str: str, pattern_str: str, flags: int, base_dir_str: str, 
                 files_with_matches: bool, only_matching: bool, force_encoding: str) -> dict:
    """並列ワーカーから呼び出される単一ファイルの検索タスク"""
    file_path = Path(file_path_str)
    base_dir = Path(base_dir_str)
    pattern = re.compile(pattern_str, flags)
    
    results = []
    encoding = force_encoding if force_encoding else "utf-8"
    try:
        with open(file_path, "rb") as f:
            sample_bytes = f.read(8192)
            if not sample_bytes:
                return None
            if b"\x00" in sample_bytes and not (sample_bytes.startswith(b"\xff\xfe") or sample_bytes.startswith(b"\xfe\xff")):
                 return None

            if not force_encoding:
                encoding = detect_encoding(sample_bytes)

        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            if files_with_matches:
                for line in f:
                    if pattern.search(line):
                        results.append({"line_num": None, "text": None})
                        break
            else:
                for line_num, line in enumerate(f, 1):
                    if only_matching:
                        for match in pattern.finditer(line):
                            results.append({"line_num": line_num, "text": match.group(0)})
                    else:
                        if pattern.search(line):
                            results.append({"line_num": line_num, "text": line.rstrip()})
                            
    except Exception:
        return None
        
    if not results:
        return None
        
    return {
        "full_path": str(file_path),
        "rel_path": str(file_path.relative_to(base_dir)).replace("\\", "/"),
        "encoding": encoding,
        "matches": results
    }

def build_file_list(target_dir: Path, include_patterns: list, exclude_patterns: list, exclude_dirs: set) -> list:
    """探索ツリーの枝刈りを行い、対象ファイルのリストを構築する"""
    file_list = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
        for file in files:
            if file.startswith('.'): continue
            file_path = Path(root) / file
            rel_path_str = str(file_path.relative_to(target_dir)).replace("\\", "/")
            
            if exclude_patterns and any(fnmatch.fnmatch(rel_path_str, p) or fnmatch.fnmatch(file, p) for p in exclude_patterns):
                continue
            if include_patterns and not any(fnmatch.fnmatch(rel_path_str, p) or fnmatch.fnmatch(file, p) for p in include_patterns):
                continue
            file_list.append(str(file_path))
    return file_list

# ==========================================
# Web Frontend (HTML/CSS/JS)
# ==========================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FastGrep Web</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .loader {
            border-top-color: #4f46e5;
            -webkit-animation: spinner 1.5s linear infinite;
            animation: spinner 1.5s linear infinite;
        }
        @keyframes spinner {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        /* スクロールバーのカスタマイズ */
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: #f1f1f1; }
        ::-webkit-scrollbar-thumb { background: #c1c1c1; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #a8a8a8; }
    </style>
</head>
<body class="bg-gray-100 h-screen flex flex-col font-sans text-gray-800">
    <!-- Header -->
    <header class="bg-indigo-600 text-white p-4 shadow-md flex justify-between items-center z-10 relative">
        <div class="flex items-center space-x-2">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
            <h1 class="text-xl font-bold tracking-wider">FastGrep Web</h1>
        </div>
        <div class="text-sm bg-indigo-700 px-3 py-1 rounded-full border border-indigo-500">Python + Flask Engine</div>
    </header>

    <!-- Main Content -->
    <div class="flex flex-1 overflow-hidden">
        
        <!-- Left Sidebar (Controls) -->
        <aside class="w-96 bg-white border-r border-gray-200 overflow-y-auto flex flex-col">
            <div class="p-5 space-y-5">
                
                <!-- Search Target -->
                <section>
                    <h2 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Target</h2>
                    <div class="space-y-3">
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">ディレクトリパス (必須)</label>
                            <input type="text" id="target_path" placeholder="C:\\Projects\\MyApp" class="w-full text-sm border-gray-300 border rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500 shadow-sm">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">検索文字列 (必須)</label>
                            <input type="text" id="pattern" placeholder="Search string..." class="w-full text-sm border-gray-300 border rounded-md px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500 shadow-sm">
                        </div>
                    </div>
                </section>

                <hr class="border-gray-200">

                <!-- Search Options -->
                <section>
                    <h2 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Options</h2>
                    <div class="space-y-2 text-sm">
                        <label class="flex items-center space-x-2 cursor-pointer">
                            <input type="checkbox" id="opt_ignore_case" class="rounded text-indigo-600 focus:ring-indigo-500">
                            <span>大文字小文字を区別しない (i)</span>
                        </label>
                        <label class="flex items-center space-x-2 cursor-pointer">
                            <input type="checkbox" id="opt_word" class="rounded text-indigo-600 focus:ring-indigo-500">
                            <span>単語単位で検索 (w)</span>
                        </label>
                        <label class="flex items-center space-x-2 cursor-pointer">
                            <input type="checkbox" id="opt_fixed" class="rounded text-indigo-600 focus:ring-indigo-500">
                            <span>リテラル検索 (正規表現無効) (F)</span>
                        </label>
                        <label class="flex items-center space-x-2 cursor-pointer">
                            <input type="checkbox" id="opt_filename_only" class="rounded text-indigo-600 focus:ring-indigo-500">
                            <span>ファイル名のみ検索</span>
                        </label>
                        <label class="flex items-center space-x-2 cursor-pointer">
                            <input type="checkbox" id="opt_files_with_matches" class="rounded text-indigo-600 focus:ring-indigo-500">
                            <span>マッチしたファイル名のみ出力 (l)</span>
                        </label>
                        <label class="flex items-center space-x-2 cursor-pointer">
                            <input type="checkbox" id="opt_only_matching" class="rounded text-indigo-600 focus:ring-indigo-500">
                            <span>マッチ部分のみ抽出 (o)</span>
                        </label>
                    </div>
                </section>

                <hr class="border-gray-200">

                <!-- Filters -->
                <section>
                    <h2 class="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">Filters</h2>
                    <div class="space-y-3">
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">含めるファイル (*.py, src/*)</label>
                            <input type="text" id="include" placeholder="空なら全て" class="w-full text-sm border-gray-300 border rounded-md px-3 py-2">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">除外するファイル (*.test.js)</label>
                            <input type="text" id="exclude" placeholder="" class="w-full text-sm border-gray-300 border rounded-md px-3 py-2">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">追加除外ディレクトリ (logs, tmp)</label>
                            <input type="text" id="exclude_dir" placeholder="" class="w-full text-sm border-gray-300 border rounded-md px-3 py-2">
                        </div>
                    </div>
                </section>

            </div>

            <!-- Action Buttons (Sticky Bottom) -->
            <div class="p-4 bg-gray-50 border-t border-gray-200 mt-auto">
                <button id="btn_search" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2.5 px-4 rounded shadow transition-colors flex justify-center items-center">
                    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                    検索を実行
                </button>
            </div>
        </aside>

        <!-- Right Content (Results & Replace) -->
        <main class="flex-1 flex flex-col bg-gray-100 overflow-hidden relative">
            
            <!-- Replace Action Bar (Hidden by default) -->
            <div id="replace_bar" class="bg-white border-b border-gray-200 p-4 shadow-sm hidden items-end space-x-4">
                <div class="flex-1">
                    <label class="block text-xs font-bold text-red-600 mb-1 uppercase tracking-wider">Replace String (置換文字列)</label>
                    <input type="text" id="replace_str" placeholder="New string..." class="w-full text-sm border-gray-300 border rounded-md px-3 py-2 focus:ring-red-500 focus:border-red-500">
                </div>
                <div class="pb-2">
                    <label class="flex items-center space-x-2 cursor-pointer text-sm font-medium">
                        <input type="checkbox" id="opt_backup" checked class="rounded text-red-600 focus:ring-red-500">
                        <span>実行前に.bakを作成</span>
                    </label>
                </div>
                <button id="btn_replace" class="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-6 rounded shadow transition-colors h-10">
                    選択したファイルを置換
                </button>
            </div>

            <!-- Status & Stats -->
            <div class="px-6 py-3 bg-gray-50 border-b border-gray-200 flex justify-between items-center text-sm">
                <div id="status_text" class="text-gray-600 font-medium">準備完了 - 検索パスと文字列を入力してください</div>
                <div id="stats_text" class="text-indigo-600 font-bold hidden"></div>
            </div>

            <!-- Loading Overlay -->
            <div id="loading_overlay" class="absolute inset-0 bg-white/70 backdrop-blur-sm z-20 flex flex-col justify-center items-center hidden">
                <div class="loader ease-linear rounded-full border-4 border-t-4 border-gray-200 h-12 w-12 mb-4"></div>
                <p class="text-gray-600 font-semibold text-lg animate-pulse" id="loading_message">検索中...</p>
            </div>

            <!-- Results Area -->
            <div id="results_area" class="flex-1 overflow-y-auto p-6">
                <!-- Search results will be injected here -->
                <div class="h-full flex flex-col items-center justify-center text-gray-400 space-y-4 opacity-50">
                    <svg class="w-20 h-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                    <p class="text-lg">No results yet.</p>
                </div>
            </div>
        </main>
    </div>

    <!-- JavaScript Application Logic -->
    <script>
        let currentResults = [];

        // DOM Elements
        const el = {
            targetPath: document.getElementById('target_path'),
            pattern: document.getElementById('pattern'),
            replaceStr: document.getElementById('replace_str'),
            btnSearch: document.getElementById('btn_search'),
            btnReplace: document.getElementById('btn_replace'),
            resultsArea: document.getElementById('results_area'),
            loadingOverlay: document.getElementById('loading_overlay'),
            loadingMessage: document.getElementById('loading_message'),
            statusText: document.getElementById('status_text'),
            statsText: document.getElementById('stats_text'),
            replaceBar: document.getElementById('replace_bar')
        };

        // Utility: HTML Escape
        function escapeHTML(str) {
            if (!str) return "";
            return str.replace(/[&<>'"]/g, tag => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
            }[tag] || tag));
        }

        // Search Action
        el.btnSearch.addEventListener('click', async () => {
            const targetPath = el.targetPath.value.trim();
            const pattern = el.pattern.value;

            if (!targetPath || (!pattern && !document.getElementById('opt_filename_only').checked)) {
                alert("ディレクトリパスと検索文字列を入力してください。");
                return;
            }

            const payload = {
                target_path: targetPath,
                pattern: pattern,
                ignore_case: document.getElementById('opt_ignore_case').checked,
                word: document.getElementById('opt_word').checked,
                fixed_strings: document.getElementById('opt_fixed').checked,
                filename_only: document.getElementById('opt_filename_only').checked,
                files_with_matches: document.getElementById('opt_files_with_matches').checked,
                only_matching: document.getElementById('opt_only_matching').checked,
                include: document.getElementById('include').value,
                exclude: document.getElementById('exclude').value,
                exclude_dir: document.getElementById('exclude_dir').value
            };

            el.loadingMessage.innerText = "検索・解析中...";
            el.loadingOverlay.classList.remove('hidden');
            el.resultsArea.innerHTML = '';
            el.replaceBar.classList.add('hidden');
            el.statsText.classList.add('hidden');
            currentResults = [];

            try {
                const response = await fetch('/api/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || "サーバーエラーが発生しました");
                }

                currentResults = data.results;
                renderResults(data);
                
                // Show replace bar if we have valid textual matches (not filename only)
                if (currentResults.length > 0 && !payload.filename_only && !payload.files_with_matches && !payload.only_matching) {
                    el.replaceBar.classList.remove('hidden');
                }

            } catch (err) {
                el.statusText.innerHTML = `<span class="text-red-600 font-bold">エラー: ${escapeHTML(err.message)}</span>`;
            } finally {
                el.loadingOverlay.classList.add('hidden');
            }
        });

        // Replace Action
        el.btnReplace.addEventListener('click', async () => {
            const replaceStr = el.replaceStr.value;
            const makeBackup = document.getElementById('opt_backup').checked;
            
            // Collect checked files
            const checkboxes = document.querySelectorAll('.file-checkbox:checked');
            const filesToReplace = Array.from(checkboxes).map(cb => {
                const index = parseInt(cb.dataset.index);
                return currentResults[index];
            });

            if (filesToReplace.length === 0) {
                alert("置換対象のファイルが選択されていません。");
                return;
            }

            if (!confirm(`${filesToReplace.length} 個のファイルに対して置換を実行します。よろしいですか？`)) {
                return;
            }

            const payload = {
                pattern: el.pattern.value,
                replace: replaceStr,
                ignore_case: document.getElementById('opt_ignore_case').checked,
                word: document.getElementById('opt_word').checked,
                fixed_strings: document.getElementById('opt_fixed').checked,
                make_backup: makeBackup,
                files: filesToReplace.map(f => ({ full_path: f.full_path, encoding: f.encoding }))
            };

            el.loadingMessage.innerText = "置換を実行中...";
            el.loadingOverlay.classList.remove('hidden');

            try {
                const response = await fetch('/api/replace', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || "置換に失敗しました");

                let totalReplaced = 0;
                let errorCount = 0;
                data.results.forEach(r => {
                    if (r.status === 'success') totalReplaced += r.count;
                    if (r.status === 'error') errorCount++;
                });

                alert(`置換完了: ${totalReplaced} 箇所\\n(エラー: ${errorCount} 件)`);
                el.replaceStr.value = '';
                // 再検索して画面を更新
                el.btnSearch.click();

            } catch (err) {
                alert(`エラー: ${err.message}`);
            } finally {
                el.loadingOverlay.classList.add('hidden');
            }
        });

        // Render Results HTML
        function renderResults(data) {
            el.statusText.innerHTML = `スキャン完了: <span class="font-bold text-gray-800">${data.total_files}</span> files scanned.`;
            
            if (data.results.length === 0) {
                el.resultsArea.innerHTML = `
                    <div class="h-full flex flex-col items-center justify-center text-gray-400 space-y-4">
                        <svg class="w-16 h-16 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                        <p class="text-lg font-medium">一致する文字列は見つかりませんでした。</p>
                    </div>`;
                return;
            }

            let totalMatches = 0;
            let html = '<div class="space-y-4 pb-10">';

            data.results.forEach((fileRes, index) => {
                totalMatches += fileRes.matches ? fileRes.matches.length : 1;
                
                html += `
                <div class="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden hover:shadow-md transition-shadow">
                    <div class="bg-gray-50 border-b border-gray-200 px-4 py-2 flex items-center justify-between sticky top-0">
                        <div class="flex items-center space-x-3 truncate">
                            <input type="checkbox" class="file-checkbox rounded text-indigo-600 focus:ring-indigo-500 cursor-pointer" checked data-index="${index}">
                            <svg class="w-5 h-5 text-gray-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z"></path></svg>
                            <span class="font-semibold text-indigo-800 text-sm truncate" title="${escapeHTML(fileRes.rel_path)}">${escapeHTML(fileRes.rel_path)}</span>
                        </div>
                        <span class="text-xs bg-gray-200 text-gray-600 px-2 py-1 rounded border border-gray-300">${escapeHTML(fileRes.encoding)}</span>
                    </div>
                    <div class="p-0 bg-gray-900 text-gray-100 font-mono text-xs overflow-x-auto">
                `;

                if (fileRes.matches && fileRes.matches.length > 0) {
                    html += `<table class="w-full whitespace-pre"><tbody>`;
                    fileRes.matches.forEach(m => {
                        if (m.line_num !== null && m.text !== null) {
                            html += `
                            <tr class="hover:bg-gray-800 transition-colors">
                                <td class="px-3 py-1 text-right text-gray-500 border-r border-gray-700 w-12 select-none">${m.line_num}</td>
                                <td class="px-3 py-1 text-green-400 break-all">${escapeHTML(m.text)}</td>
                            </tr>`;
                        } else {
                            html += `<tr><td class="px-4 py-2 text-green-400 italic">Match found.</td></tr>`;
                        }
                    });
                    html += `</tbody></table>`;
                }
                
                html += `</div></div>`;
            });

            html += '</div>';
            el.resultsArea.innerHTML = html;

            el.statsText.innerText = `${data.results.length} files / ${totalMatches} hits`;
            el.statsText.classList.remove('hidden');
        }
    </script>
</body>
</html>
"""

# ==========================================
# Flask API Endpoints
# ==========================================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/search', methods=['POST'])
def api_search():
    data = request.json
    target_path = data.get('target_path', '').strip()
    pattern_str = data.get('pattern', '')
    
    ignore_case = data.get('ignore_case', False)
    word = data.get('word', False)
    fixed_strings = data.get('fixed_strings', False)
    filename_only = data.get('filename_only', False)
    files_with_matches = data.get('files_with_matches', False)
    only_matching = data.get('only_matching', False)
    
    target_dir = Path(target_path).resolve()
    if not target_dir.is_dir():
        return jsonify({"error": "指定されたパスが存在しないか、ディレクトリではありません"}), 400

    if filename_only and only_matching:
        return jsonify({"error": "ファイル名のみ検索とマッチ部分抽出は同時に指定できません"}), 400

    if fixed_strings:
        pattern_str = re.escape(pattern_str)
    if word:
        pattern_str = rf"\b{pattern_str}\b"

    flags = re.IGNORECASE if ignore_case else 0
    
    try:
        compiled_pattern = re.compile(pattern_str, flags)
    except re.error as e:
        return jsonify({"error": f"正規表現エラー: {e}"}), 400

    include_patterns = [p.strip() for p in data.get('include', '').split(",")] if data.get('include') else []
    exclude_patterns = [p.strip() for p in data.get('exclude', '').split(",")] if data.get('exclude') else []
    
    active_exclude_dirs = set(BASE_EXCLUDE_DIRS)
    if data.get('exclude_dir'):
        active_exclude_dirs.update({d.strip() for d in data.get('exclude_dir').split(",")})

    files = build_file_list(target_dir, include_patterns, exclude_patterns, active_exclude_dirs)
    
    results = []
    
    if filename_only:
        for f_path_str in files:
            rel_path = str(Path(f_path_str).relative_to(target_dir)).replace("\\", "/")
            if compiled_pattern.search(rel_path):
                results.append({
                    "full_path": f_path_str,
                    "rel_path": rel_path,
                    "encoding": "N/A",
                    "matches": []
                })
    else:
        workers = os.cpu_count() or 4
        if workers > 1 and len(files) > 50:
            with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        process_file_worker, f, pattern_str, flags, str(target_dir), 
                        files_with_matches, only_matching, None
                    ): f for f in files
                }
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    if res: results.append(res)
        else:
            for f in files:
                res = process_file_worker(f, pattern_str, flags, str(target_dir), files_with_matches, only_matching, None)
                if res: results.append(res)

    results.sort(key=lambda x: x["rel_path"])

    return jsonify({
        "total_files": len(files),
        "results": results
    })

@app.route('/api/replace', methods=['POST'])
def api_replace():
    data = request.json
    pattern_str = data.get('pattern', '')
    replace_str = data.get('replace', '')
    files = data.get('files', [])
    
    ignore_case = data.get('ignore_case', False)
    word = data.get('word', False)
    fixed_strings = data.get('fixed_strings', False)
    make_backup = data.get('make_backup', True)

    if fixed_strings:
        pattern_str = re.escape(pattern_str)
    if word:
        pattern_str = rf"\b{pattern_str}\b"

    flags = re.IGNORECASE if ignore_case else 0
    
    results = []
    for f_info in files:
        res = execute_replace_single(f_info['full_path'], pattern_str, flags, replace_str, f_info['encoding'], make_backup)
        results.append(res)

    return jsonify({"results": results})


def open_browser():
    webbrowser.open_new('http://127.0.0.1:5000/')

if __name__ == "__main__":
    print("🚀 FastGrep Web Server を起動しています...")
    print("🌐 ブラウザが自動的に開きます (http://127.0.0.1:5000/)")
    # サーバー起動から少し遅延させてブラウザを開く
    threading.Timer(1.25, open_browser).start()
    app.run(host='127.0.0.1', port=5000, debug=False)