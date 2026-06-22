"""
Bridge Crossing Dynamics
〜 通れれば太れる：ヤギの橋渡しシミュレーション 〜

【概要】
フロントエンド（HTML/JS）、バックエンド（Python/HTTPサーバー）、
およびゲームロジックと全網羅の動的テストコードを1ファイルに統合したアプリケーションです。
複雑な専門用語は避け、シンプルな状態遷移（決定論的ロジック）で動作します。

【操作方法】
1. このスクリプトを実行: python app.py
2. ブラウザで http://localhost:8000 にアクセス
3. 実行中のコンソールで `test` と入力してEnterを押すとユニットテストが実行されます。
"""

import http.server
import socketserver
import json
import threading
import unittest
import sys
import time

# ==========================================
# 1. フロントエンド (HTML / CSS / JS)
# ==========================================
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>通れれば太れる：ヤギの橋渡し</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        /* ヤギのサイズ変更を滑らかにするアニメーション */
        #goat {
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        .jump {
            animation: jumpAnim 0.5s ease-in-out;
        }
        @keyframes jumpAnim {
            0% { transform: translateY(0) translateX(0); }
            50% { transform: translateY(-40px) translateX(60px); }
            100% { transform: translateY(0) translateX(0); }
        }
        .shake {
            animation: shakeAnim 0.4s ease-in-out;
        }
        @keyframes shakeAnim {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-10px); }
            75% { transform: translateX(10px); }
        }
    </style>
</head>
<body class="bg-sky-50 h-screen flex flex-col items-center justify-center p-4">
    <h1 class="text-3xl font-bold text-gray-800 mb-2">通れれば太れる</h1>
    <p class="text-gray-500 mb-6 font-medium">丁度いい力で橋を渡り、ヤギを太らせよう</p>
    
    <div class="bg-white rounded-2xl shadow-xl p-8 w-full max-w-md text-center">
        
        <!-- 橋とヤギの描画エリア -->
        <div class="mb-8 relative h-48 flex flex-col items-center justify-end border-b-8 border-amber-700 pb-2 overflow-hidden">
            <!-- 障害物（失敗したヤギの跡）の表示 -->
            <div id="obstacle-container" class="absolute bottom-0 left-0 w-full flex justify-center gap-1 opacity-50 z-0">
                <!-- JSで障害物が追加されます -->
            </div>
            
            <!-- メインのヤギ -->
            <div id="goat" class="bg-white border-4 border-gray-400 rounded-full flex items-center justify-center font-bold shadow-md z-10" style="width: 40px; height: 40px;">
                <span id="goat-emoji" class="text-xl">🐐</span>
            </div>
        </div>

        <!-- ステータス表示 -->
        <div class="flex justify-between mb-4 bg-gray-50 p-4 rounded-lg border border-gray-100">
            <div class="text-center">
                <div class="text-xs text-gray-500 font-bold">ヤギの太さ</div>
                <div id="goat-size" class="text-blue-600 text-2xl font-black mt-1">1</div>
            </div>
            <div class="text-center">
                <div class="text-xs text-gray-500 font-bold">必要な力</div>
                <div id="req-power" class="text-green-600 text-2xl font-black mt-1">-</div>
            </div>
            <div class="text-center">
                <div class="text-xs text-gray-500 font-bold">橋の障害物</div>
                <div id="obstacles" class="text-red-600 text-2xl font-black mt-1">0</div>
            </div>
        </div>

        <!-- メッセージエリア -->
        <div class="h-14 flex items-center justify-center mb-4">
            <p id="message" class="text-gray-700 font-medium">スライダーで「渡る力」を決めてください。</p>
        </div>

        <!-- 入力エリア -->
        <div class="mb-8">
            <div class="flex justify-between text-xs text-gray-400 font-bold mb-1">
                <span>弱 (1)</span>
                <span>強 (20)</span>
            </div>
            <input type="range" id="power-slider" min="1" max="20" value="1" class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-500">
            <div class="text-center mt-3 font-black text-3xl text-gray-700" id="power-display">1</div>
        </div>

        <button id="cross-btn" class="w-full bg-blue-500 hover:bg-blue-600 active:bg-blue-700 text-white font-bold py-4 px-4 rounded-xl shadow-lg transition-all transform hover:-translate-y-1">
            橋を渡る
        </button>
    </div>

    <script>
        // DOM要素の取得
        const goatEl = document.getElementById('goat');
        const emojiEl = document.getElementById('goat-emoji');
        const sizeEl = document.getElementById('goat-size');
        const obstaclesEl = document.getElementById('obstacles');
        const reqPowerEl = document.getElementById('req-power');
        const messageEl = document.getElementById('message');
        const slider = document.getElementById('power-slider');
        const powerDisplay = document.getElementById('power-display');
        const crossBtn = document.getElementById('cross-btn');
        const obstacleContainer = document.getElementById('obstacle-container');

        // スライダーの連動
        slider.addEventListener('input', (e) => {
            powerDisplay.textContent = e.target.value;
        });

        // 状態を取得してUIを更新
        async function fetchState() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                updateUI(data);
            } catch (e) {
                console.error("サーバーとの通信に失敗しました", e);
            }
        }

        // UI描画ロジック
        function updateUI(state) {
            sizeEl.textContent = state.goat_size;
            obstaclesEl.textContent = state.bridge_obstacles;
            
            // ヒントとして必要な力の範囲を表示（ゲームを遊びやすくするため）
            reqPowerEl.textContent = `${state.required_power}〜${state.required_power + 2}`;
            
            // 太さに応じた見た目の変化 (ベース40px + (サイズ-1)*15px)
            const newSize = Math.min(40 + (state.goat_size - 1) * 15, 140);
            goatEl.style.width = `${newSize}px`;
            goatEl.style.height = `${newSize}px`;
            
            // 絵文字のサイズ調整
            const emjSize = Math.min(20 + (state.goat_size - 1) * 5, 80);
            emojiEl.style.fontSize = `${emjSize}px`;

            // 障害物の描画
            obstacleContainer.innerHTML = '';
            for (let i = 0; i < state.bridge_obstacles; i++) {
                const block = document.createElement('div');
                block.className = 'bg-gray-800 w-6 h-6 rounded flex items-center justify-center text-xs text-white shadow-inner';
                block.textContent = '💀';
                obstacleContainer.appendChild(block);
            }
        }

        // 橋を渡るアクション
        crossBtn.addEventListener('click', async () => {
            // 連打防止
            if (crossBtn.disabled) return;
            crossBtn.disabled = true;
            
            // アニメーション開始
            goatEl.classList.remove('jump', 'shake');
            void goatEl.offsetWidth; // リフロー強制
            goatEl.classList.add('jump');
            
            // アニメーションの途中でAPIを叩く
            setTimeout(async () => {
                try {
                    const power = parseInt(slider.value, 10);
                    const res = await fetch('/api/cross', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ power: power })
                    });
                    const result = await res.json();
                    
                    // 結果のメッセージ表示
                    messageEl.textContent = result.message;
                    if (result.success) {
                        messageEl.className = "text-green-600 font-bold text-lg";
                        // 成功時はスライダーの値を次に必要な値の近くにリセット
                        slider.value = result.state.required_power;
                        powerDisplay.textContent = slider.value;
                    } else {
                        messageEl.className = "text-red-600 font-bold text-lg";
                        document.querySelector('.bg-white').classList.add('shake');
                        setTimeout(() => document.querySelector('.bg-white').classList.remove('shake'), 400);
                        slider.value = 1;
                        powerDisplay.textContent = 1;
                    }
                    
                    // UIの更新
                    updateUI(result.state);
                } catch (e) {
                    messageEl.textContent = "エラーが発生しました。";
                    messageEl.className = "text-red-500 font-bold";
                } finally {
                    crossBtn.disabled = false;
                    goatEl.classList.remove('jump');
                }
            }, 250); // アニメーションの頂点あたりで判定を反映
        });

        // 起動時の初期化
        fetchState();
    </script>
</body>
</html>
"""

# ==========================================
# 2. バックエンドゲームロジック (決定論的状態遷移)
# ==========================================
class GoatGameLogic:
    """
    ヤギの成長と環境（橋）の状態を管理するクラス。
    乱数は一切使用せず、現在の状態と入力値（power）のみで次状態が完全に決定される
    決定論的アルゴリズムを採用しています。
    """
    def __init__(self):
        # 状態の初期化
        self.reset()

    def reset(self):
        """初期状態に戻す"""
        self.goat_size = 1        # 個体の初期サイズ（太さ）
        self.bridge_obstacles = 0 # 橋に残された過去の死骸（環境の複雑さ）

    def get_state(self):
        """現在の完全な状態を取得する"""
        return {
            "goat_size": self.goat_size,
            "bridge_obstacles": self.bridge_obstacles,
            "required_power": self.calculate_required_power()
        }

    def calculate_required_power(self):
        """
        橋を渡るために必要な基本の力を計算する。
        - 障害物が多いほど高い力が必要。
        - ヤギが太い（サイズが大きい）ほど、体を動かすための基本力も上がる。
        """
        return (self.bridge_obstacles * 2) + self.goat_size

    def cross(self, power: int):
        """
        橋を渡るアクションを処理する状態遷移関数。
        
        Args:
            power (int): プレイヤーが入力した力
            
        Returns:
            dict: 成功可否、メッセージ、遷移後の状態を含む辞書
        """
        req_power = self.calculate_required_power()
        
        # 決定論的判定ルール：
        # 力が弱すぎてもダメ、強すぎても橋が壊れて（あるいは足場を踏み外して）失敗する。
        # 必要な力 〜 必要な力+2 の間に収まっていれば成功。
        is_success = (req_power <= power <= req_power + 2)
        
        if is_success:
            # 成功時：個体の成長（サイズアップ）
            self.goat_size += 1
            msg = f"見事！丁度いい力で渡りきり、ヤギは太さ {self.goat_size} に成長した！"
        else:
            # 失敗時：個体は死亡し環境の一部（障害物）となる。新たな個体が誕生する。
            self.bridge_obstacles += 1
            self.goat_size = 1
            if power < req_power:
                msg = "力が足りずトロルに捕まった...ヤギは障害物となり、新しいヤギが来た。"
            else:
                msg = "力が強すぎて勢い余って落ちた...ヤギは障害物となり、新しいヤギが来た。"
                
        return {
            "success": is_success,
            "message": msg,
            "state": self.get_state()
        }


# シングルトンとしてゲームインスタンスを保持
game_instance = GoatGameLogic()


# ==========================================
# 3. HTTP サーバー (API & 静的ファイル配信)
# ==========================================
class SimpleGameHandler(http.server.BaseHTTPRequestHandler):
    """
    外部ライブラリ不要の標準HTTPサーバー。
    GETでHTMLを返し、POSTでAPIロジックを処理する。
    """
    
    def _send_response(self, content: str, content_type: str = 'text/html'):
        self.send_response(200)
        self.send_header('Content-type', f'{content_type}; charset=utf-8')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def do_GET(self):
        if self.path == '/':
            # フロントエンドのHTMLを配信
            self._send_response(HTML_CONTENT, 'text/html')
        elif self.path == '/api/state':
            # 現在の状態をJSONで配信
            state_json = json.dumps(game_instance.get_state())
            self._send_response(state_json, 'application/json')
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == '/api/cross':
            try:
                # リクエストボディの読み取り
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data)
                
                # 入力値の取得とバリデーション
                power = int(data.get('power', 1))
                
                # ロジックの実行
                result = game_instance.cross(power)
                
                # 結果をJSONで返却
                self._send_response(json.dumps(result), 'application/json')
            except Exception as e:
                self.send_error(400, f"Bad Request: {str(e)}")
        else:
            self.send_error(404, "Not Found")

    # コンソール出力を綺麗に保つため、デフォルトのアクセスログ出力を無効化
    def log_message(self, format, *args):
        pass


def start_server(port=8000):
    """サーバーを別スレッドで起動するための関数"""
    handler = SimpleGameHandler
    # アドレス再利用を設定し、再起動時のエラーを防ぐ
    socketserver.TCPServer.allow_reuse_address = True 
    httpd = socketserver.TCPServer(("", port), handler)
    print(f"\n🚀 サーバーが起動しました: http://localhost:{port}")
    print("--------------------------------------------------")
    print("💻 コンソールコマンド:")
    print("  'test' と入力してEnter: ユニットテストを実行します")
    print("  'exit' と入力してEnter: サーバーを終了します")
    print("--------------------------------------------------\n")
    httpd.serve_forever()


# ==========================================
# 4. 全網羅 動的テストコード (unittest)
# ==========================================
class TestGoatGameLogic(unittest.TestCase):
    """
    ゲームロジックの完全な状態遷移を検証するテストスイート。
    境界値分析および同値分割に基づき、全てのロジックパスを網羅。
    """

    def setUp(self):
        """各テストの前に新しい独立したゲームインスタンスを用意する"""
        self.game = GoatGameLogic()

    def test_01_initial_state(self):
        """【テスト1】初期状態の検証"""
        state = self.game.get_state()
        self.assertEqual(state['goat_size'], 1, "初期のヤギサイズは1であるべき")
        self.assertEqual(state['bridge_obstacles'], 0, "初期の障害物は0であるべき")
        self.assertEqual(state['required_power'], 1, "初期の必要力は (0*2)+1 = 1 であるべき")

    def test_02_cross_success_exact_power(self):
        """【テスト2】ピッタリの力で渡る（成功）"""
        # 初期状態(req=1)で力1を入力
        result = self.game.cross(1)
        self.assertTrue(result['success'], "ピッタリの力なら成功するべき")
        self.assertEqual(self.game.goat_size, 2, "成功時、ヤギサイズが+1されるべき")
        self.assertEqual(self.game.bridge_obstacles, 0, "成功時、障害物は増えないべき")

    def test_03_cross_success_upper_boundary(self):
        """【テスト3】許容される最大の力で渡る（成功・境界値）"""
        # 初期状態(req=1)で力3 (1+2) を入力
        result = self.game.cross(3)
        self.assertTrue(result['success'], "許容範囲内の力なら成功するべき")
        self.assertEqual(self.game.goat_size, 2)

    def test_04_cross_fail_insufficient_power(self):
        """【テスト4】力が足りずに渡る（失敗）"""
        self.game.goat_size = 2 # 状態を強制変更 (req=2)
        result = self.game.cross(1) # req=2に対して1を入力
        self.assertFalse(result['success'], "力が足りなければ失敗するべき")
        self.assertEqual(self.game.goat_size, 1, "失敗時、新しいヤギ(サイズ1)になるべき")
        self.assertEqual(self.game.bridge_obstacles, 1, "失敗時、障害物が+1されるべき")
        self.assertIn("力が足りず", result['message'])

    def test_05_cross_fail_excessive_power(self):
        """【テスト5】力が強すぎて渡る（失敗・境界値外）"""
        # 初期状態(req=1)に対して許容範囲外の4を入力
        result = self.game.cross(4)
        self.assertFalse(result['success'], "力が強すぎると失敗するべき")
        self.assertEqual(self.game.goat_size, 1, "失敗時、新しいヤギになるべき")
        self.assertEqual(self.game.bridge_obstacles, 1, "失敗時、障害物が+1されるべき")
        self.assertIn("強すぎて", result['message'])

    def test_06_complex_state_transition(self):
        """【テスト6】複数回の遷移（成功→成功→失敗→成功）のシナリオテスト"""
        # 1. 成功 (req: 1 -> 力2を入力)
        self.game.cross(2)
        self.assertEqual(self.game.goat_size, 2)
        
        # 2. 成功 (req: (0*2)+2 = 2 -> 力4を入力)
        self.game.cross(4)
        self.assertEqual(self.game.goat_size, 3)
        self.assertEqual(self.game.bridge_obstacles, 0)
        
        # 3. 失敗 (req: (0*2)+3 = 3 -> 力1を入力してわざと失敗)
        self.game.cross(1)
        self.assertEqual(self.game.goat_size, 1, "失敗でリセット")
        self.assertEqual(self.game.bridge_obstacles, 1, "障害物発生")
        
        # 4. 障害物ありでの成功 (req: (1*2)+1 = 3 -> 力4を入力)
        self.game.cross(4)
        self.assertEqual(self.game.goat_size, 2, "復活後の成功")
        self.assertEqual(self.game.bridge_obstacles, 1, "過去の障害物は残る")


def run_tests():
    """コンソールから呼び出されるテスト実行関数"""
    print("\n" + "="*50)
    print("🔍 自動テストスイートを実行中...")
    print("="*50)
    
    # テストスイートの作成と実行
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestGoatGameLogic)
    
    # TextTestRunnerで詳細（verbosity=2）に出力
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("="*50)
    if result.wasSuccessful():
        print("✅ 全てのテストが正常に通過しました！ (ロジックは完璧です)")
    else:
        print(f"❌ {len(result.failures) + len(result.errors)} 個のテストが失敗しました。")
    print("="*50 + "\n")
    print("コマンド待機中 ('test' で再実行, 'exit' で終了): ", end="", flush=True)


# ==========================================
# 5. メインプロセス (サーバー起動＆コンソール監視)
# ==========================================
if __name__ == '__main__':
    # サーバーを別スレッド（デーモン）で起動
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # メインスレッドでは標準入力を監視（動的テスト用インターフェース）
    # time.sleepを入れてサーバー起動メッセージの表示を待つ
    time.sleep(0.5) 
    print("コマンド待機中 ('test' または 'exit'): ", end="", flush=True)
    
    while True:
        try:
            # 標準入力から行を読み取る
            user_input = sys.stdin.readline()
            
            # EOF (Ctrl+D等) の場合は終了
            if not user_input:
                break
                
            command = user_input.strip().lower()
            
            if command == 'test':
                run_tests()
            elif command == 'exit':
                print("👋 サーバーを終了します...")
                sys.exit(0)
            elif command != '':
                print(f"不明なコマンド: '{command}'。 'test' か 'exit' を入力してください。")
                print("コマンド待機中: ", end="", flush=True)
                
        except KeyboardInterrupt:
            # Ctrl+Cでの安全な終了
            print("\n👋 サーバーを終了します...")
            sys.exit(0)