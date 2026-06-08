import numpy as np
import time
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---------------------------------------------------------
# コアロジック (通常のappend と リスト経由のappend)
# ---------------------------------------------------------
def normal_append(data_source):
    """通常のNumpy appendを用いた追加処理"""
    buffer = np.array([], dtype=np.uint32)
    start_time = time.time()
    for item in data_source:
        buffer = np.append(buffer, item)
    return time.time() - start_time

def optimized_append(data_source):
    """リストを経由した改善版の追加処理"""
    buffer = np.array([], dtype=np.uint32)
    start_time = time.time()
    
    temp_list = buffer.tolist()
    for item in data_source:
        temp_list.append(item)
    buffer = np.asarray(temp_list, dtype=np.uint32)
    
    return time.time() - start_time

# ---------------------------------------------------------
# HTML テンプレート (フロントエンドUI)
# ---------------------------------------------------------
HTML_PAGE = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Numpy Append 高速化検証</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f3f4f6; color: #1f2937; }
        pre { background-color: #1e293b; color: #f8fafc; padding: 1rem; border-radius: 0.5rem; overflow-x: auto; font-size: 0.875rem; }
    </style>
</head>
<body class="p-6 md:p-12 max-w-5xl mx-auto">
    <h1 class="text-3xl font-bold mb-8 text-center text-blue-600">Numpy Append 高速化検証</h1>
    
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <!-- 通常手法のサンプルコード -->
        <div class="bg-white p-6 rounded-xl shadow-md border-t-4 border-red-500">
            <h2 class="text-xl font-bold mb-4 text-red-600">通常手法 (遅い)</h2>
            <p class="text-sm mb-4 text-gray-600">ループごとに Numpy 配列のメモリ再確保が発生するため、要素数が増えると急激に遅くなります。</p>
            <pre><code>buffer = np.array([], dtype=np.uint32)

for item in data_source:
    buffer = np.append(buffer, item)</code></pre>
        </div>
        
        <!-- 改善手法のサンプルコード -->
        <div class="bg-white p-6 rounded-xl shadow-md border-t-4 border-green-500">
            <h2 class="text-xl font-bold mb-4 text-green-600">改善手法 (速い)</h2>
            <p class="text-sm mb-4 text-gray-600">Pythonの可変長配列（リスト）でデータを集め、最後に一括で Numpy 配列に変換します。</p>
            <pre><code>buffer = np.array([], dtype=np.uint32)

temp_list = buffer.tolist()
for item in data_source:
    temp_list.append(item)
    
buffer = np.asarray(temp_list, dtype=np.uint32)</code></pre>
        </div>
    </div>

    <!-- コントロールパネル -->
    <div class="bg-white p-6 rounded-xl shadow-md mb-8 flex flex-col md:flex-row items-center justify-center gap-4">
        <label for="dataCount" class="font-medium text-gray-700">検証データ件数:</label>
        <input type="number" id="dataCount" value="30000" class="border border-gray-300 rounded px-4 py-2 w-48 text-center focus:ring-2 focus:ring-blue-500 outline-none">
        <button id="runBtn" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-6 rounded transition-colors shadow">
            検証を実行する
        </button>
    </div>

    <!-- コンソール出力エリア -->
    <div id="resultArea" class="hidden bg-gray-900 text-green-400 p-6 rounded-xl shadow-md font-mono text-sm leading-relaxed whitespace-pre-wrap"></div>

    <script>
        document.getElementById('runBtn').addEventListener('click', async () => {
            const btn = document.getElementById('runBtn');
            const resultArea = document.getElementById('resultArea');
            const count = document.getElementById('dataCount').value;
            
            // UIの無効化と初期メッセージ
            btn.disabled = true;
            btn.innerText = "実行中...";
            btn.classList.add("opacity-50", "cursor-not-allowed");
            resultArea.classList.remove('hidden');
            resultArea.innerText = `[System] データ件数 ${count} 件で計算エンジンを起動しました...\\n[System] バックエンドで処理中です。そのままお待ちください。`;

            try {
                // Pythonバックエンドへリクエスト送信
                const response = await fetch('/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ count: parseInt(count, 10) })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    resultArea.innerText += `\\n\\n[Error] ${data.error}`;
                } else {
                    let log = `\\n\\n=== 実行結果 ===\\n`;
                    log += `1. 通常の Numpy append : ${data.time_normal.toFixed(4)} 秒\\n`;
                    log += `2. 改善版 (リスト経由) : ${data.time_opt.toFixed(4)} 秒\\n\\n`;
                    log += `=== 結論 ===\\n`;
                    if (data.speed_up > 0) {
                        log += `改善手法は通常手法と比較して 約 ${data.speed_up.toFixed(1)} 倍 高速に処理を完了しました。`;
                    } else {
                        log += `処理が速すぎて正確な倍率が計算できませんでした。`;
                    }
                    resultArea.innerText += log;
                }
            } catch (err) {
                resultArea.innerText += `\\n\\n[Network Error] サーバーに接続できませんでした。`;
            } finally {
                // UIの復帰
                btn.disabled = false;
                btn.innerText = "検証を実行する";
                btn.classList.remove("opacity-50", "cursor-not-allowed");
            }
        });
    </script>
</body>
</html>
"""

# ---------------------------------------------------------
# Web サーバーのハンドラー
# ---------------------------------------------------------
class BenchmarkHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # ブラウザからのアクセス時にHTMLを返す
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        # UIのボタンが押されたときのAPIエンドポイント
        if self.path == '/run':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                params = json.loads(post_data.decode('utf-8'))
                count = params.get('count', 30000)
                
                # ダミーデータ生成（32bit整数）
                dummy_data = np.random.randint(0, 4294967295, size=count, dtype=np.uint32)
                
                # 速度検証の実行
                time_normal = normal_append(dummy_data)
                time_opt = optimized_append(dummy_data)
                speed_up = time_normal / time_opt if time_opt > 0 else 0
                
                # 結果をJSONでフロントへ返す
                response_data = {
                    "time_normal": time_normal,
                    "time_opt": time_opt,
                    "speed_up": speed_up
                }
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode('utf-8'))
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    # コンソール出力をシンプルに保つため、GET/POSTのアクセスログを非表示にする
    def log_message(self, format, *args):
        pass

# ---------------------------------------------------------
# メイン実行ブロック
# ---------------------------------------------------------
def main():
    port = 8000
    server_address = ('', port)
    httpd = HTTPServer(server_address, BenchmarkHandler)
    
    print("=== Numpy Append 高速化検証 Webアプリ ===")
    print(f"ローカルサーバーを起動しました。")
    print(f"ブラウザを開き、以下のURLにアクセスしてください：")
    print(f"http://localhost:{port}")
    print(f"(終了するにはこのコンソールで Ctrl+C を押してください)")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nサーバーを停止しました。")
        httpd.server_close()

if __name__ == "__main__":
    main()