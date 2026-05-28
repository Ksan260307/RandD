import os
import sys
import time
import threading
import urllib.parse
import shutil
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
import cmd

# ナレッジ設計書の「ベクトルバックエンド（GPUオフロード）」の
# フォールバックとして指定されているNumPyを利用し、高効率な一括演算を実現します。
try:
    import numpy as np
except ImportError:
    print("NumPyが必要です。コマンドプロンプトで 'pip install numpy' を実行してください。")
    sys.exit(1)

# システム負荷監視のためのモジュール（なければ代替機能を使用）
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ==========================================
# グローバル設定とロガー設定
# ==========================================
SHARED_DIR = os.path.abspath(os.path.join(os.getcwd(), "shared_files"))
if not os.path.exists(SHARED_DIR):
    os.makedirs(SHARED_DIR)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("FileServer")

# ==========================================
# I/O最適化: トリプル・バッファリング・キュー
# ==========================================
class TripleBufferQueue:
    """
    データ連係における同期待ち（ストール）を完全に排除するための3重リングバッファ。
    フロントエンド（Web受付）からバックエンド（状態遷移エンジン）へのログ受け渡しに使用。
    """
    def __init__(self):
        self.buffers = [[], [], []]
        self.write_idx = 0
        self.read_idx = 1
        self.lock = threading.Lock()
        
    def push(self, item):
        with self.lock:
            self.buffers[self.write_idx].append(item)
            
    def swap_and_get(self):
        with self.lock:
            self.buffers[self.read_idx].clear()
            # 書込、読取、予備バッファをローテーション
            self.read_idx, self.write_idx = self.write_idx, (self.write_idx + 1) % 3
            return list(self.buffers[self.read_idx])

# ==========================================
# 状態遷移エンジン (コアシステム)
# ==========================================
class FileStateEngine:
    """
    制約下動的状態遷移システムの設計思想に基づき、
    ファイル群の状態を32bit整数にパッキングし、NumPyのSoA(Structure of Arrays)
    を用いて高効率に一括状態遷移を行うエンジン。
    """
    def __init__(self, max_items=1000):
        self.max_items = max_items
        self.item_count = 0
        self.filenames = [""] * max_items
        self.name_to_index = {}
        
        # --- 32bitビットパッキング状態配列 (SoAベース) ---
        # [0-1] アクセス権限 (0: 読書, 1: 読取専用)
        # [2-3] ロック状態 (0: 解放, 1: ロック中)
        # [4-5] アクセス頻度 (Velocity相当)
        # [6-11] 転送変化量 (Intensity相当)
        # [24-26] アクティブ状態フラグ (0: 圧縮/相転移, 1: 展開中, 2: 破綻地形化)
        # [27-29] エラー蓄積値 (Fatigue相当)
        self.packed_states = np.zeros(max_items, dtype=np.uint32)
        
        # 物理座標の代わりとなる固定小数点バッファの代替（ファイルサイズ）
        self.file_sizes = np.zeros(max_items, dtype=np.int64)
        
        self.action_queue = TripleBufferQueue()
        self.is_running = False
        self.worker_thread = None
        self.entropy_thread = None
        self.current_system_load = 0.0 # 現実エントロピー（システム負荷 0.0~1.0）

    def _pack_value(self, array, index, shift, mask, value):
        array[index] = (array[index] & ~(mask << shift)) | ((value & mask) << shift)

    def _unpack_value(self, array, index, shift, mask):
        return (array[index] >> shift) & mask

    def register_file(self, filename, size):
        if filename in self.name_to_index:
            return
        if self.item_count >= self.max_items:
            logger.warning("管理上限に達しました。密度限界です。")
            return
            
        idx = self.item_count
        self.filenames[idx] = filename
        self.name_to_index[filename] = idx
        self.file_sizes[idx] = size
        
        # 初期状態: 展開中(1)として登録
        self._pack_value(self.packed_states, idx, 24, 0x7, 1)
        self.item_count += 1

    def push_action(self, action_type, filename):
        """アクセスログ（アクション）を記録。遅延評価グラフの入力要素として扱う。"""
        self.action_queue.push({"type": action_type, "target": filename, "time": time.time()})

    def trigger_observation(self):
        """観測者効果: 管理者による観測時、圧縮状態の対象を強制的に展開状態へ復帰させる"""
        if self.item_count > 0:
            active_mask = (self.packed_states[:self.item_count] >> 24) & 0x7
            # 圧縮中(0)のものを展開中(1)へ一括変更。ただし破綻(2)はそのまま。
            to_deploy = (active_mask == 0)
            new_states = np.where(
                to_deploy,
                (self.packed_states[:self.item_count] & ~(0x7 << 24)) | (1 << 24),
                self.packed_states[:self.item_count]
            )
            self.packed_states[:self.item_count] = new_states
            logger.info("観測者効果が発動しました。圧縮状態のファイルが実体化（展開）しました。")

    def start(self):
        if self.is_running: return
        self.is_running = True
        
        # 状態更新スレッド
        self.worker_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.worker_thread.start()
        
        # システム負荷監視スレッド（エントロピー収穫デーモン）
        self.entropy_thread = threading.Thread(target=self._entropy_harvester_loop, daemon=True)
        self.entropy_thread.start()
        
        logger.info("状態遷移エンジン（バックエンド）が起動しました。")

    def stop(self):
        self.is_running = False
        if self.worker_thread:
            self.worker_thread.join()
        if self.entropy_thread:
            self.entropy_thread.join()
        logger.info("状態遷移エンジンが停止しました。")

    def _entropy_harvester_loop(self):
        """現実のシステム負荷を収穫し、状態遷移エンジン用のエントロピーとして権威化する"""
        while self.is_running:
            if HAS_PSUTIL:
                load = psutil.cpu_percent(interval=1.0) / 100.0
            else:
                # psutilがない環境向けの擬似的な負荷計算（アクセス数などから推測可能だがここではランダム揺らぎ）
                load = (int(time.time()) % 10) / 10.0
            
            self.current_system_load = load
            time.sleep(2.0)

    def _process_loop(self):
        """
        決定論的ロックステップに基づく状態の更新ループ。
        現実世界のノイズ（エントロピー）を取り込み、ベクトル演算で一括処理する。
        """
        cycle = 0
        while self.is_running:
            # 外部エントロピーの適用
            system_load = self.current_system_load
            
            actions = self.action_queue.swap_and_get()
            
            # 影響円錐（Cone of Influence）の抽出：変更対象のインデックス特定
            affected_indices = set()
            for act in actions:
                idx = self.name_to_index.get(act["target"])
                if idx is not None:
                    affected_indices.add(idx)
                    
                    if act["type"] == "ERROR":
                        # 不正アクセスやエラー時、エラー蓄積値（Fatigue）を加算
                        err = min(7, self._unpack_value(self.packed_states, idx, 27, 0x7) + 1)
                        self._pack_value(self.packed_states, idx, 27, 0x7, err)
                        if err >= 7:
                            # 限界突破で破綻状態（地形化）へ
                            self._pack_value(self.packed_states, idx, 24, 0x7, 2)
                            logger.warning(f"ファイル [{act['target']}] がエラー蓄積MAXとなり、アクセス拒否状態に固定化されました。")
                    else:
                        # 正常アクセス: アクセス頻度と転送量の増加、及び観測者効果による復帰
                        self._pack_value(self.packed_states, idx, 24, 0x7, 1) # 展開中へ
                        freq = min(3, self._unpack_value(self.packed_states, idx, 4, 0x3) + 1)
                        intensity = min(63, self._unpack_value(self.packed_states, idx, 6, 0x3F) + 10)
                        self._pack_value(self.packed_states, idx, 4, 0x3, freq)
                        self._pack_value(self.packed_states, idx, 6, 0x3F, intensity)
            
            # 定期的な相転移（圧縮モードへの移行）と局所時間拡張の適用
            if cycle % 10 == 0 and self.item_count > 0:
                # アクセス頻度が低いファイル群をベクトル演算で抽出
                freq_mask = (self.packed_states[:self.item_count] >> 4) & 0x3
                active_mask = (self.packed_states[:self.item_count] >> 24) & 0x7
                
                # システム負荷(エントロピー)が高いほど、圧縮されやすくなる（閾値変動）
                freq_threshold = 1 if system_load > 0.7 else 0
                
                # アクセス頻度が閾値以下、かつ現在展開中(1)のものを圧縮(0)へ相転移
                to_compress = (freq_mask <= freq_threshold) & (active_mask == 1)
                
                # NumPyを用いた一括ビット操作
                new_states = np.where(
                    to_compress,
                    self.packed_states[:self.item_count] & ~(0x7 << 24), # 0クリア(圧縮状態)
                    self.packed_states[:self.item_count]
                )
                self.packed_states[:self.item_count] = new_states
                
                # 毎ループ頻度を自然減衰（Stream Compaction的最適化の準備）
                dec_freq_states = np.where(
                    freq_mask > 0,
                    (self.packed_states[:self.item_count] & ~(0x3 << 4)) | (((freq_mask - 1) & 0x3) << 4),
                    self.packed_states[:self.item_count]
                )
                self.packed_states[:self.item_count] = dec_freq_states

            cycle += 1
            time.sleep(1.0) # 決定論的ティック間隔

    def get_status_report(self):
        """現在のSoA状態をデコードして人間に読める形にする"""
        report = []
        for i in range(self.item_count):
            state = self.packed_states[i]
            freq = (state >> 4) & 0x3
            active = (state >> 24) & 0x7
            err = (state >> 27) & 0x7
            
            status_str = "展開中 (高精度)" if active == 1 else ("圧縮中 (確率雲)" if active == 0 else "破綻 (アクセス不可)")
            report.append(f"[{i:03d}] {self.filenames[i]:<20} | サイズ: {self.file_sizes[i]:<8} | 状態: {status_str} | アクセス頻度: {freq} | エラー累積: {err}")
        return report

# グローバルエンジンインスタンス
engine = FileStateEngine()

# ==========================================
# 描画/通信アダプタ (Webサーバー層)
# ==========================================
class FileServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # サーバーログをPython標準のloggingにリダイレクト
        logger.info("%s - %s" % (self.address_string(), format%args))

    def send_index_html(self):
        """Webブラウザ用のダッシュボードとアップロード画面を動的生成する"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        
        # 状態エンジンのSoAバッファから最新状態を構築
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Py_UCD-F_ABC ファイルサーバー</title>
            <style>
                body { font-family: sans-serif; margin: 20px; color: #333; }
                table { border-collapse: collapse; width: 100%; max-width: 800px; margin-top: 10px; }
                th, td { border: 1px solid #ccc; padding: 10px; text-align: left; }
                th { background-color: #f4f4f4; }
                .upload-area { margin-bottom: 30px; padding: 20px; background: #eef7ff; border-radius: 8px; border: 1px solid #cce; max-width: 758px; }
                button { padding: 8px 16px; cursor: pointer; }
                .status-msg { margin-top: 10px; font-weight: bold; color: #0056b3; }
                .state-deploy { color: green; font-weight: bold; }
                .state-compress { color: gray; }
                .state-ruin { color: red; font-weight: bold; text-decoration: line-through; }
            </style>
        </head>
        <body>
            <h2>高効率状態遷移ファイルサーバー (Web UI)</h2>
            
            <div class="upload-area">
                <h3>ファイルのアップロード</h3>
                <p>※サーバーのCPU負荷を避けるため、ブラウザ側からダイレクト通信(PUT)を行います。</p>
                <input type="file" id="fileInput">
                <button onclick="uploadFile()">アップロード実行</button>
                <div id="uploadStatus" class="status-msg"></div>
            </div>

            <h3>共有ファイル一覧</h3>
            <table>
                <tr><th>ファイル名</th><th>サイズ (Bytes)</th><th>動的状態</th><th>操作</th></tr>
        """
        
        # SoA配列から状態を抽出して行を生成
        for i in range(engine.item_count):
            state = engine.packed_states[i]
            active = (state >> 24) & 0x7
            err = (state >> 27) & 0x7
            fname = engine.filenames[i]
            fsize = engine.file_sizes[i]
            
            if active == 1:
                status_html = "<span class='state-deploy'>展開中 (Hot)</span>"
                dl_link = f"<a href='/{urllib.parse.quote(fname)}'>ダウンロード</a>"
            elif active == 0:
                status_html = "<span class='state-compress'>圧縮中 (Cold)</span>"
                dl_link = f"<a href='/{urllib.parse.quote(fname)}'>ダウンロード</a>"
            else:
                status_html = f"<span class='state-ruin'>破綻 (Err:{err})</span>"
                dl_link = "<span style='color:red;'>アクセス拒否</span>"
            
            html += f"<tr><td>{fname}</td><td>{fsize:,}</td><td>{status_html}</td><td>{dl_link}</td></tr>"

        html += """
            </table>
            
            <script>
                function uploadFile() {
                    const fileInput = document.getElementById('fileInput');
                    const statusDiv = document.getElementById('uploadStatus');
                    const file = fileInput.files[0];
                    
                    if (!file) {
                        statusDiv.innerText = "エラー: ファイルを選択してください。";
                        return;
                    }
                    
                    statusDiv.innerText = "アップロード中... (通信エンジンへ送信中)";
                    
                    // Python側に複雑なパースをさせないため、fetch APIで直接PUT送信
                    fetch('/' + encodeURIComponent(file.name), {
                        method: 'PUT',
                        body: file
                    }).then(response => {
                        if (response.ok) {
                            statusDiv.innerText = "アップロード完了！ 画面を更新します...";
                            setTimeout(() => location.reload(), 1000);
                        } else {
                            statusDiv.innerText = "エラーが発生しました: サーバーが拒否しました (HTTP " + response.status + ")";
                        }
                    }).catch(err => {
                        statusDiv.innerText = "通信エラー: " + err;
                    });
                }
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

    def do_GET(self):
        filename = urllib.parse.unquote(self.path.lstrip("/"))
        
        # ルートアクセス、または index.html へのアクセス時はWeb UIを返す
        if not filename or filename == "index.html":
            self.send_index_html()
            return

        file_path = os.path.join(SHARED_DIR, filename)
        
        # 状態エンジンにアクセスログ（アクション）を投入
        if filename in engine.name_to_index:
            # 破綻地形（エラー蓄積MAX）判定。判定はO(1)で即座に行う
            idx = engine.name_to_index[filename]
            if (engine.packed_states[idx] >> 24) & 0x7 == 2:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Error: File is in Ruined State (Access Denied).")
                engine.push_action("ERROR", filename) # さらにエラーとして記録
                return

            engine.push_action("READ", filename)

        if os.path.exists(file_path) and os.path.isfile(file_path):
            with open(file_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            # 存在しないファイルへのアクセスは、対象が登録されていればエラーアクションとする
            if filename in engine.name_to_index:
                engine.push_action("ERROR", filename)
                
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_PUT(self):
        """ファイルのアップロード（配置）処理"""
        filename = urllib.parse.unquote(self.path.lstrip("/"))
        file_path = os.path.join(SHARED_DIR, filename)
        
        length = int(self.headers.get('Content-Length', 0))
        with open(file_path, 'wb') as f:
            f.write(self.rfile.read(length))
            
        engine.register_file(filename, length)
        engine.push_action("WRITE", filename)
        
        self.send_response(201)
        self.end_headers()
        self.wfile.write(b"Created/Updated successfully.")

# ==========================================
# コンソール操作インターフェース
# ==========================================
class FileServerConsole(cmd.Cmd):
    intro = "\n=======================================================\n" \
            " 古いPC向け 高効率状態遷移ファイルサーバーへようこそ。\n" \
            " 'help' または '?' を入力するとコマンド一覧を表示します。\n" \
            "=======================================================\n"
    prompt = "(server) "

    def __init__(self):
        super().__init__()
        self.httpd = None
        self.server_thread = None
        self.port = 8080

    def do_start(self, arg):
        """start [port] : ファイルサーバーと状態遷移エンジンを起動します"""
        if self.httpd:
            print("サーバーは既に起動しています。")
            return
            
        if arg.isdigit():
            self.port = int(arg)
            
        engine.start()
        
        # ディレクトリの初期スキャン
        for f in os.listdir(SHARED_DIR):
            fpath = os.path.join(SHARED_DIR, f)
            if os.path.isfile(fpath):
                engine.register_file(f, os.path.getsize(fpath))
                
        try:
            self.httpd = HTTPServer(('', self.port), FileServerHandler)
            self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.server_thread.start()
            print(f"サーバーをポート {self.port} で起動しました。")
            print(f"共有ディレクトリ: {SHARED_DIR}")
        except Exception as e:
            print(f"起動エラー: {e}")

    def do_stop(self, arg):
        """stop : ファイルサーバーと状態遷移エンジンを停止します"""
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
            self.server_thread = None
            print("HTTPサーバーを停止しました。")
        engine.stop()

    def do_status(self, arg):
        """status : 管理対象ファイル群のビットパッキング状態レポートを表示します"""
        if not engine.is_running:
            print("エンジンが起動していません。'start' を実行してください。")
            return
            
        # 観測者効果の発動
        engine.trigger_observation()
        
        report = engine.get_status_report()
        if not report:
            print("管理対象のファイルがありません。")
        else:
            print(f"\n--- システム負荷（エントロピー）: {engine.current_system_load:.1%} ---")
            print("--- ファイル状態レポート ---")
    def do_scan(self, arg):
        """scan : 共有ディレクトリを再スキャンし、新たなファイルをエンジンに登録します"""
        count = 0
        for f in os.listdir(SHARED_DIR):
            fpath = os.path.join(SHARED_DIR, f)
            if os.path.isfile(fpath) and f not in engine.name_to_index:
                engine.register_file(f, os.path.getsize(fpath))
                count += 1
        print(f"{count} 件の新規ファイルを状態ベクトルに登録しました。")

    def do_exit(self, arg):
        """exit : アプリケーションを終了します"""
        print("終了処理を実行中...")
        self.do_stop("")
        return True

if __name__ == '__main__':
    # アプリケーション開始
    try:
        FileServerConsole().cmdloop()
    except KeyboardInterrupt:
        print("\n強制終了シグナルを受信しました。終了します。")
        engine.stop()
        sys.exit(0)