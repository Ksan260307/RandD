import time
import json
import threading
import webbrowser
import urllib.parse
import numpy as np
from http.server import SimpleHTTPRequestHandler, HTTPServer

PORT = 8080
DATA_SIZE = 1_000_000

# ==========================================
# 画面表示用のHTML/CSS/JavaScript (Tailwind CSS使用)
# ==========================================
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pythonループ 爆速化検証アプリ</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 text-slate-800 p-4 md:p-8 font-sans">
    <div class="max-w-6xl mx-auto">
        <header class="mb-10 text-center">
            <h1 class="text-3xl md:text-4xl font-extrabold text-slate-900 tracking-tight mb-2">🚀 Pythonループ 爆速化検証アプリ</h1>
            <p class="text-slate-600 font-medium">データ数: <span class="text-blue-600 font-bold">1,000,000</span> 件の計算を各手法で比較・検証します</p>
        </header>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            
            <!-- [1] Normal For Loop -->
            <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 flex flex-col">
                <div class="mb-4">
                    <span class="inline-block px-3 py-1 bg-red-100 text-red-700 font-bold text-sm rounded-full mb-2">[1] 通常のforループ</span>
                    <h2 class="text-lg font-bold text-slate-800 mb-1">オブジェクトの都度評価と型確認</h2>
                    <p class="text-sm text-slate-500">記事で指摘されている「すべてがオブジェクト」ゆえに解釈コストが非常に重い基準となるパターンです。</p>
                </div>
                <div class="bg-slate-900 rounded-lg p-4 mb-4 flex-grow overflow-x-auto text-sm font-mono text-slate-300">
<span class="text-pink-400">for</span> i <span class="text-pink-400">in</span> <span class="text-blue-300">range</span>(DATA_SIZE):
    vel_list[i] += int_list[i]
    <span class="text-pink-400">if</span> vel_list[i] > <span class="text-orange-300">10</span>:
        fat_list[i] += <span class="text-orange-300">1</span>
                </div>
                <div class="flex items-center justify-between mt-auto">
                    <button onclick="runTest('normal', this)" class="bg-red-600 hover:bg-red-700 text-white font-bold py-2.5 px-6 rounded-lg shadow transition duration-200">▶ 実行</button>
                    <div class="text-right">
                        <div class="text-xs text-slate-400 mb-0.5">実行時間</div>
                        <div class="text-xl font-mono font-bold text-slate-700 result-time">-.----- 秒</div>
                    </div>
                </div>
            </div>

            <!-- [2] List Comprehension -->
            <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 flex flex-col">
                <div class="mb-4">
                    <span class="inline-block px-3 py-1 bg-amber-100 text-amber-700 font-bold text-sm rounded-full mb-2">[2] 次善策: リスト内包表記</span>
                    <h2 class="text-lg font-bold text-slate-800 mb-1">組み込み関数への委譲</h2>
                    <p class="text-sm text-slate-500">Python内部のC言語による最適化の恩恵を受けることで、ループの解釈コストを削減します。</p>
                </div>
                <div class="bg-slate-900 rounded-lg p-4 mb-4 flex-grow overflow-x-auto text-sm font-mono text-slate-300">
<span class="text-slate-400"># 速度の更新を一括生成</span>
vel_list = [v + i <span class="text-pink-400">for</span> v, i <span class="text-pink-400">in</span> <span class="text-blue-300">zip</span>(vel_list, int_list)]
<span class="text-slate-400"># 疲労の更新を一括生成</span>
fat_list = [f + <span class="text-orange-300">1</span> <span class="text-pink-400">if</span> v > <span class="text-orange-300">10</span> <span class="text-pink-400">else</span> f <span class="text-pink-400">for</span> f, v <span class="text-pink-400">in</span> <span class="text-blue-300">zip</span>(fat_list, vel_list)]
                </div>
                <div class="flex items-center justify-between mt-auto">
                    <button onclick="runTest('comprehension', this)" class="bg-amber-500 hover:bg-amber-600 text-white font-bold py-2.5 px-6 rounded-lg shadow transition duration-200">▶ 実行</button>
                    <div class="text-right">
                        <div class="text-xs text-slate-400 mb-0.5">実行時間</div>
                        <div class="text-xl font-mono font-bold text-slate-700 result-time">-.----- 秒</div>
                    </div>
                </div>
            </div>

            <!-- [3] NumPy Vectorization -->
            <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 flex flex-col">
                <div class="mb-4">
                    <span class="inline-block px-3 py-1 bg-emerald-100 text-emerald-700 font-bold text-sm rounded-full mb-2">[3] 最善策: ベクトル演算</span>
                    <h2 class="text-lg font-bold text-slate-800 mb-1">配列構造化とC層への委譲</h2>
                    <p class="text-sm text-slate-500">NumPyを用いてデータを連続した配列として管理し、C言語レベルのベクトル演算で一括処理します。</p>
                </div>
                <div class="bg-slate-900 rounded-lg p-4 mb-4 flex-grow overflow-x-auto text-sm font-mono text-slate-300">
<span class="text-slate-400"># for文を一切使わず、一括演算</span>
vel_arr += int_arr
<span class="text-slate-400"># 条件絞り込みも where で一括処理</span>
fat_arr = np.where(vel_arr > <span class="text-orange-300">10</span>, fat_arr + <span class="text-orange-300">1</span>, fat_arr)
                </div>
                <div class="flex items-center justify-between mt-auto">
                    <button onclick="runTest('numpy', this)" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2.5 px-6 rounded-lg shadow transition duration-200">▶ 実行</button>
                    <div class="text-right">
                        <div class="text-xs text-slate-400 mb-0.5">実行時間</div>
                        <div class="text-xl font-mono font-bold text-slate-700 result-time">-.----- 秒</div>
                    </div>
                </div>
            </div>

            <!-- [4] Bit Packing -->
            <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 flex flex-col">
                <div class="mb-4">
                    <span class="inline-block px-3 py-1 bg-blue-100 text-blue-700 font-bold text-sm rounded-full mb-2">[4] 究極系: データ圧縮</span>
                    <h2 class="text-lg font-bold text-slate-800 mb-1">SoA構造とビットパッキング</h2>
                    <p class="text-sm text-slate-500">複数の状態を1つの32bit整数に圧縮格納し、キャッシュ効率を極限まで高めてベクトル演算を行います。</p>
                </div>
                <div class="bg-slate-900 rounded-lg p-4 mb-4 flex-grow overflow-x-auto text-sm font-mono text-slate-300">
<span class="text-slate-400"># 32bit整数からビットマスクで各値を展開</span>
v_arr = packed_arr & <span class="text-orange-300">0xFF</span>
i_arr = (packed_arr >> <span class="text-orange-300">8</span>) & <span class="text-orange-300">0xFF</span>
f_arr = (packed_arr >> <span class="text-orange-300">16</span>) & <span class="text-orange-300">0xFF</span>

v_arr += i_arr
f_arr = np.where(v_arr > <span class="text-orange-300">10</span>, f_arr + <span class="text-orange-300">1</span>, f_arr)

<span class="text-slate-400"># 演算後に再度1つの整数に圧縮</span>
packed_arr = v_arr | (i_arr << <span class="text-orange-300">8</span>) | (f_arr << <span class="text-orange-300">16</span>)
                </div>
                <div class="flex items-center justify-between mt-auto">
                    <button onclick="runTest('packed', this)" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2.5 px-6 rounded-lg shadow transition duration-200">▶ 実行</button>
                    <div class="text-right">
                        <div class="text-xs text-slate-400 mb-0.5">実行時間</div>
                        <div class="text-xl font-mono font-bold text-slate-700 result-time">-.----- 秒</div>
                    </div>
                </div>
            </div>

        </div>
    </div>

    <script>
        async function runTest(type, btn) {
            const resultDiv = btn.nextElementSibling.querySelector('.result-time');
            const originalText = btn.innerHTML;
            
            // UIを計算中状態にする
            btn.disabled = true;
            btn.classList.add('opacity-50', 'cursor-not-allowed');
            btn.innerHTML = `<svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline-block" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>計算中`;
            resultDiv.textContent = "計測中...";
            resultDiv.classList.remove('text-slate-700');
            resultDiv.classList.add('text-blue-500', 'animate-pulse');
            
            try {
                // Pythonバックエンドへ実行リクエストを送信
                const res = await fetch(`/run?type=${type}`);
                const data = await res.json();
                
                // 結果表示
                resultDiv.classList.remove('text-blue-500', 'animate-pulse');
                resultDiv.classList.add('text-slate-800');
                resultDiv.textContent = data.time.toFixed(5) + " 秒";
            } catch (e) {
                resultDiv.classList.remove('text-blue-500', 'animate-pulse');
                resultDiv.classList.add('text-red-500');
                resultDiv.textContent = "エラー発生";
            } finally {
                // UI状態を復元
                btn.disabled = false;
                btn.classList.remove('opacity-50', 'cursor-not-allowed');
                btn.innerHTML = originalText;
            }
        }
    </script>
</body>
</html>
"""

# ==========================================
# API及び静的ファイル配信を処理するバックエンドサーバー
# ==========================================
class BenchmarkAPIHandler(SimpleHTTPRequestHandler):
    
    # 標準のアクセスログを無効化（コンソールをシンプルに保つため）
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        # 1. HTMLUIの配信
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
            
        # 2. ベンチマーク実行APIの処理
        elif self.path.startswith('/run?type='):
            parsed_path = urllib.parse.urlparse(self.path)
            req_type = urllib.parse.parse_qs(parsed_path.query).get('type', [''])[0]
            
            vel_init, int_init, fat_init = 1, 2, 0
            result_time = 0.0
            
            # --- ここから各ループのベンチマーク実行処理 ---
            if req_type == 'normal':
                print(f"[UI要求] 通常のforループを実行中...", end="", flush=True)
                vel_list = [vel_init] * DATA_SIZE
                int_list = [int_init] * DATA_SIZE
                fat_list = [fat_init] * DATA_SIZE
                
                start = time.perf_counter()
                for i in range(DATA_SIZE):
                    vel_list[i] += int_list[i]
                    if vel_list[i] > 10:
                        fat_list[i] += 1
                result_time = time.perf_counter() - start
                print(f" 完了 -> {result_time:.5f} 秒")

            elif req_type == 'comprehension':
                print(f"[UI要求] リスト内包表記を実行中...", end="", flush=True)
                vel_list = [vel_init] * DATA_SIZE
                int_list = [int_init] * DATA_SIZE
                fat_list = [fat_init] * DATA_SIZE
                
                start = time.perf_counter()
                vel_list = [v + i for v, i in zip(vel_list, int_list)]
                fat_list = [f + 1 if v > 10 else f for f, v in zip(fat_list, vel_list)]
                result_time = time.perf_counter() - start
                print(f" 完了 -> {result_time:.5f} 秒")

            elif req_type == 'numpy':
                print(f"[UI要求] NumPyベクトル演算を実行中...", end="", flush=True)
                vel_arr = np.full(DATA_SIZE, vel_init, dtype=np.int32)
                int_arr = np.full(DATA_SIZE, int_init, dtype=np.int32)
                fat_arr = np.full(DATA_SIZE, fat_init, dtype=np.int32)
                
                start = time.perf_counter()
                vel_arr += int_arr
                fat_arr = np.where(vel_arr > 10, fat_arr + 1, fat_arr)
                result_time = time.perf_counter() - start
                print(f" 完了 -> {result_time:.5f} 秒")

            elif req_type == 'packed':
                print(f"[UI要求] データ圧縮・一括演算を実行中...", end="", flush=True)
                packed_val = vel_init | (int_init << 8) | (fat_init << 16)
                packed_arr = np.full(DATA_SIZE, packed_val, dtype=np.uint32)
                
                start = time.perf_counter()
                v_arr = packed_arr & 0xFF
                i_arr = (packed_arr >> 8) & 0xFF
                f_arr = (packed_arr >> 16) & 0xFF
                v_arr += i_arr
                f_arr = np.where(v_arr > 10, f_arr + 1, f_arr)
                packed_arr = v_arr | (i_arr << 8) | (f_arr << 16)
                result_time = time.perf_counter() - start
                print(f" 完了 -> {result_time:.5f} 秒")

            # 実行結果(秒数)をJSONでフロントに返す
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'time': result_time}).encode('utf-8'))
            
        else:
            self.send_response(404)
            self.end_headers()

def start_server():
    server = HTTPServer(('localhost', PORT), BenchmarkAPIHandler)
    print("=" * 60)
    print(" 🚀 Pythonループ 爆速化検証 Webアプリケーション起動")
    print(f" ブラウザで自動的に http://localhost:{PORT} を開きます。")
    print(" 終了する場合はターミナルで [Ctrl+C] を押してください。")
    print("=" * 60)
    server.serve_forever()

if __name__ == "__main__":
    # バックグラウンドでサーバーを起動
    threading.Thread(target=start_server, daemon=True).start()
    
    # サーバー立ち上げの猶予を取り、ブラウザを自動で開く
    time.sleep(1)
    webbrowser.open(f"http://localhost:{PORT}")
    
    # メインスレッドはCtrl+Cを待機
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nサーバーを停止しました。")