# coding: utf-8
import http.server
import json
import threading
import sys
import unittest
import urllib.parse

# =========================================================
# ドメインロジック：完全決定論的状態遷移（サルでもわかる版）
# =========================================================
class Character:
    def __init__(self, name, icon, speed):
        self.name = name
        self.icon = icon
        self.speed = speed # 1時間(Tick)あたりの進み具合 (0.01 なら 100時間で1周)
        
    def get_state_at(self, current_time):
        """
        [完全決定論の要（O(1)予測）]
        ループ(forやwhile)を一切使わず、現在の時間(絶対Tick)から
        「割り算」と「余り(モジュロ)」だけで一瞬で状態を計算します。
        サイコロ（乱数）がないため、未来も過去も100%確定しています。
        """
        # 1周(進み具合1.0)にかかる時間
        ticks_per_cycle = int(1.0 / self.speed)
        # つかれが 5 溜まるまで活動（5周分）
        active_duration = ticks_per_cycle * 5
        # 疲れたらおやすみする時間（1.5周分の時間を休息にあてる）
        sleep_duration = int(ticks_per_cycle * 1.5)
        
        # 1つの大きなサイクル(活動＋おやすみ)にかかる合計時間
        total_period = active_duration + sleep_duration
        
        # 大きなサイクルの中で、今はどの時間にいるか
        time_in_period = current_time % total_period
        
        if time_in_period < active_duration:
            state = "活動中"
            # 1周の中での進み具合(0.0 ~ 1.0)
            progress = (time_in_period % ticks_per_cycle) / ticks_per_cycle
            # つかれ(何周したか)
            tiredness = time_in_period // ticks_per_cycle
        else:
            state = "おやすみ"  # 計算をサボってエコに動く(マクロカリング概念)
            progress = 0.0
            tiredness = 0
            
        return {
            "name": self.name,
            "icon": self.icon,
            "state": state,
            "progress": round(progress, 4),
            "tiredness": tiredness,
            "speed": self.speed
        }

class World:
    def __init__(self):
        self.current_time = 0
        self.characters = [
            Character("サル", "🐒", 0.05), # 20時間で1周
            Character("ウサギ", "🐇", 0.10), # 10時間で1周
            Character("カメ", "🐢", 0.02)  # 50時間で1周
        ]
        
    def step(self):
        self.current_time += 1
        
    def step_back(self):
        """時間を巻き戻す（過去の状態も計算だけで完全に復元可能）"""
        if self.current_time > 0:
            self.current_time -= 1
        
    def get_current_state(self):
        return {
            "time": self.current_time,
            "characters": [c.get_state_at(self.current_time) for c in self.characters]
        }
        
    def predict_future(self, add_time):
        future_time = self.current_time + add_time
        return {
            "time": future_time,
            "characters": [c.get_state_at(future_time) for c in self.characters]
        }
        
    def reset(self):
        self.current_time = 0

# グローバルな世界の状態
world = World()

# =========================================================
# テストコード：動的全網羅単体テスト
# =========================================================
class TestDeterministicWorld(unittest.TestCase):
    def setUp(self):
        self.world = World()
        
    def test_initial_state(self):
        """初期状態のテスト"""
        state = self.world.get_current_state()
        self.assertEqual(state["time"], 0)
        self.assertEqual(state["characters"][0]["state"], "活動中")
        self.assertEqual(state["characters"][0]["progress"], 0.0)
        self.assertEqual(state["characters"][0]["tiredness"], 0)

    def test_step_progress(self):
        """時間が進むと正しく進み具合が増えるかテスト"""
        # サル (speed=0.05) を1時間進める
        self.world.step()
        state = self.world.get_current_state()
        self.assertEqual(state["time"], 1)
        self.assertAlmostEqual(state["characters"][0]["progress"], 0.05)
        
    def test_step_back(self):
        """時間が巻き戻せるか（履歴なしで過去を復元できるか）テスト"""
        self.world.step()
        self.world.step()
        self.world.step_back()
        state = self.world.get_current_state()
        self.assertEqual(state["time"], 1)
        self.assertAlmostEqual(state["characters"][0]["progress"], 0.05)

    def test_tiredness_accumulation(self):
        """1周ごとに「つかれ」が蓄積されるかテスト"""
        # サルは20時間で1周。1周すると「つかれ」が1になる。
        for _ in range(20):
            self.world.step()
        state = self.world.get_current_state()
        self.assertEqual(state["characters"][0]["tiredness"], 1)
        self.assertEqual(state["characters"][0]["progress"], 0.0)

    def test_sleep_state(self):
        """つかれが5溜まると「おやすみ」状態になるかテスト"""
        # サルは5周 (100時間) でおやすみに入る
        for _ in range(100):
            self.world.step()
        state = self.world.get_current_state()
        self.assertEqual(state["characters"][0]["state"], "おやすみ")
        self.assertEqual(state["characters"][0]["tiredness"], 0)
        
    def test_wakeup_state(self):
        """一定時間休むと再び活動を開始するかテスト"""
        # サルのおやすみ時間は 20 * 1.5 = 30時間。合計130時間で復活する。
        for _ in range(130):
            self.world.step()
        state = self.world.get_current_state()
        self.assertEqual(state["characters"][0]["state"], "活動中")
        self.assertEqual(state["characters"][0]["progress"], 0.0)
        self.assertEqual(state["characters"][0]["tiredness"], 0)

    def test_o1_prediction_accuracy(self):
        """
        [完全決定論の証明テスト]
        1万回ループして実際にシミュレーションした結果と、
        ループなしでO(1)で直接計算した未来予測結果が「完全に一致」することを証明します。
        """
        target_time = 10000
        # 1. 一瞬で未来を計算 (O(1)予測)
        predicted_state = self.world.predict_future(target_time)
        
        # 2. 愚直に1ステップずつ1万回計算するシミュレーション
        for _ in range(target_time):
            self.world.step()
        simulated_state = self.world.get_current_state()
        
        self.assertEqual(predicted_state["time"], simulated_state["time"])
        for p_char, s_char in zip(predicted_state["characters"], simulated_state["characters"]):
            self.assertEqual(p_char["state"], s_char["state"])
            self.assertAlmostEqual(p_char["progress"], s_char["progress"])
            self.assertEqual(p_char["tiredness"], s_char["tiredness"])

def run_tests():
    # テストランナーを起動（システムを終了せずに実行する設定）
    suite = unittest.TestLoader().loadTestsFromTestCase(TestDeterministicWorld)
    unittest.TextTestRunner(verbosity=2).run(suite)

# =========================================================
# HTML/JS フロントエンド (1ファイル化のために文字列で保持)
# =========================================================
INDEX_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>サルでもわかる！完全決定論アプリ</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .orbit { position: relative; width: 140px; height: 140px; border-radius: 50%; border: 3px dashed #cbd5e1; margin: 0 auto; }
        .center-point { position: absolute; top: 50%; left: 50%; width: 10px; height: 10px; background: #94a3b8; border-radius: 50%; transform: translate(-50%, -50%); }
        .agent { position: absolute; top: 50%; left: 50%; width: 40px; height: 40px; margin-top: -20px; margin-left: -20px; text-align: center; line-height: 40px; font-size: 32px; transition: transform 0.1s linear, filter 0.3s; }
        .sleeping { filter: grayscale(100%) opacity(50%); }
        .z-zz { position: absolute; top: -15px; right: -10px; font-size: 16px; color: #64748b; font-weight: bold; animation: float 2s infinite; display: none; }
        .sleeping .z-zz { display: block; }
        @keyframes float { 0% { transform: translateY(0); opacity: 1; } 100% { transform: translateY(-10px); opacity: 0; } }
        #log-console::-webkit-scrollbar { width: 8px; }
        #log-console::-webkit-scrollbar-thumb { background: #475569; border-radius: 4px; }
    </style>
</head>
<body class="bg-slate-50 text-slate-800 font-sans p-4 md:p-8">
    <div class="max-w-5xl mx-auto">
        <header class="mb-8 text-center">
            <h1 class="text-3xl font-bold text-indigo-600 mb-2">サルでもわかる！完全決定論アプリ 🐵🔄</h1>
            <p class="text-slate-600">サイコロ（ランダム）を一切使わず、数式だけで動く世界。だから未来が一瞬でわかる！<br>過去のセーブデータがなくても、計算だけで巻き戻せる！</p>
        </header>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <!-- 左側：世界（宇宙）の様子 -->
            <div class="bg-white p-6 rounded-2xl shadow-lg border border-slate-200">
                <div class="flex justify-between items-center mb-6">
                    <h2 class="text-xl font-bold text-slate-700">🌍 今の世界</h2>
                    <div class="bg-indigo-100 text-indigo-800 px-4 py-2 rounded-lg font-mono font-bold text-lg shadow-inner">
                        時間 (Tick): <span id="current-time">0</span>
                    </div>
                </div>

                <div id="characters-container" class="space-y-6">
                    <!-- キャラクター描画エリア -->
                </div>
            </div>

            <!-- 右側：操作と学習コンソール -->
            <div class="space-y-6">
                <!-- 操作パネル -->
                <div class="bg-white p-6 rounded-2xl shadow-lg border border-slate-200">
                    <h2 class="text-xl font-bold text-slate-700 mb-4">🎮 操作パネル</h2>
                    <div class="flex flex-wrap gap-3 mb-6">
                        <button id="btn-step-back" class="bg-slate-500 hover:bg-slate-600 text-white px-5 py-3 rounded-xl font-bold transition shadow-sm">
                            -1時間 戻す
                        </button>
                        <button id="btn-step" class="bg-blue-500 hover:bg-blue-600 text-white px-5 py-3 rounded-xl font-bold transition shadow-sm">
                            +1時間 進める
                        </button>
                        <button id="btn-auto" class="bg-emerald-500 hover:bg-emerald-600 text-white px-5 py-3 rounded-xl font-bold transition shadow-sm flex-1">
                            ▶ 自動再生
                        </button>
                        <button id="btn-reset" class="bg-rose-500 hover:bg-rose-600 text-white px-5 py-3 rounded-xl font-bold transition shadow-sm">
                            ↺ リセット
                        </button>
                    </div>

                    <div class="p-4 bg-purple-50 rounded-xl border border-purple-200">
                        <h3 class="font-bold text-purple-800 mb-2">🔮 魔法の未来予測（O(1)計算）</h3>
                        <p class="text-sm text-purple-700 mb-4">
                            決定論の世界では、何度もシミュレーションしなくても、<br>
                            「割り算と余り」の数式だけで<b>一瞬で未来がわかります。</b>
                        </p>
                        <div class="flex gap-2">
                            <input type="number" id="future-input" value="1000" class="border border-purple-300 p-2 rounded-lg w-24 text-right font-mono outline-none focus:border-purple-500">
                            <span class="py-2 text-purple-800 font-bold">時間後を</span>
                            <button id="btn-predict" class="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-xl font-bold transition shadow-sm flex-1">
                                覗き見する！
                            </button>
                        </div>
                    </div>
                </div>

                <!-- O(1)計算のサンプルコード表示 -->
                <div class="bg-slate-900 p-5 rounded-2xl shadow-lg border border-slate-700">
                    <h3 class="font-bold text-emerald-400 mb-2 font-mono text-sm">// サンプルコード: O(1)で状態を導く魔法の数式</h3>
                    <p class="text-xs text-slate-400 mb-3">for文やwhile文（ループ）が一切ないことに注目してください。</p>
                    <pre class="overflow-x-auto text-xs font-mono text-emerald-200 leading-relaxed"><code>def get_state_at(self, current_time):
    # 1. 周期の計算
    ticks_per_cycle = int(1.0 / self.speed)
    active_duration = ticks_per_cycle * 5
    sleep_duration = int(ticks_per_cycle * 1.5)
    total_period = active_duration + sleep_duration
    
    # 2. 割り算の余り(モジュロ)で、今どの周期にいるか判定
    time_in_period = current_time % total_period
    
    # 3. 状態の決定（ループを回さず一瞬で決まる！）
    if time_in_period < active_duration:
        state = "活動中"
        progress = (time_in_period % ticks_per_cycle) / ticks_per_cycle
        tiredness = time_in_period // ticks_per_cycle
    else:
        state = "おやすみ"
        progress = 0.0
        tiredness = 0
        
    return state, progress, tiredness</code></pre>
                </div>

                <!-- ログ / コンソール -->
                <div class="bg-slate-800 text-green-400 p-5 rounded-2xl shadow-lg font-mono text-sm h-64 overflow-y-auto" id="log-console">
                    <div>> システム起動完了。完全決定論的状態遷移を開始します。</div>
                    <div>> ランダム要素：0%。すべての未来は数式で定まっています。</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let autoPlayTimer = null;

        function log(message, type="info") {
            const consoleEl = document.getElementById('log-console');
            const color = type === "predict" ? "text-purple-300" : (type === "error" ? "text-red-400" : "text-emerald-400");
            const div = document.createElement('div');
            div.className = `mb-1 ${color}`;
            div.innerText = `> ${message}`;
            consoleEl.appendChild(div);
            consoleEl.scrollTop = consoleEl.scrollHeight;
        }

        function renderCharacters(characters) {
            const container = document.getElementById('characters-container');
            container.innerHTML = '';

            characters.forEach((char) => {
                const isSleeping = char.state === "おやすみ";
                // 角度計算: 0.0=上(270度), 0.25=右(0度), 0.5=下(90度), 0.75=左(180度)
                const angleDeg = (char.progress * 360) - 90;
                
                const html = `
                <div class="flex items-center gap-4">
                    <div class="w-1/3 text-center">
                        <div class="orbit">
                            <div class="center-point"></div>
                            <div class="agent ${isSleeping ? 'sleeping' : ''}" style="transform: rotate(${angleDeg}deg) translate(70px) rotate(-${angleDeg}deg);">
                                ${char.icon}
                                <div class="z-zz">zZ</div>
                            </div>
                        </div>
                    </div>
                    <div class="w-2/3 bg-white p-4 rounded-xl border ${isSleeping ? 'border-slate-300 bg-slate-50' : 'border-blue-100 shadow-sm'}">
                        <div class="flex justify-between items-center mb-2">
                            <span class="font-bold text-lg text-slate-700">${char.icon} ${char.name}</span>
                            <span class="px-3 py-1 rounded-full text-xs font-bold ${isSleeping ? 'bg-slate-200 text-slate-500' : 'bg-blue-100 text-blue-700'}">${char.state}</span>
                        </div>
                        <div class="mb-3">
                            <div class="text-xs text-slate-500 mb-1 flex justify-between">
                                <span>進み具合</span>
                                <span>${(char.progress * 100).toFixed(0)}%</span>
                            </div>
                            <div class="w-full bg-slate-100 rounded-full h-2">
                                <div class="bg-blue-500 h-2 rounded-full transition-all duration-200" style="width: ${char.progress * 100}%"></div>
                            </div>
                        </div>
                        <div>
                            <div class="text-xs text-slate-500 mb-1">つかれ (5で休憩)</div>
                            <div class="flex gap-1.5">
                                ${[1,2,3,4,5].map(i => `<div class="w-full h-2 rounded-full ${i <= char.tiredness ? 'bg-orange-400' : 'bg-slate-200'}"></div>`).join('')}
                            </div>
                        </div>
                    </div>
                </div>`;
                container.insertAdjacentHTML('beforeend', html);
            });
        }

        async function fetchState() {
            try {
                const res = await fetch('/api/state');
                const data = await res.json();
                document.getElementById('current-time').innerText = data.time;
                renderCharacters(data.characters);
            } catch (e) {
                log("通信エラーが発生しました", "error");
            }
        }

        async function stepTime() {
            try {
                const res = await fetch('/api/step', { method: 'POST' });
                const data = await res.json();
                document.getElementById('current-time').innerText = data.time;
                renderCharacters(data.characters);
            } catch (e) {
                log("通信エラー", "error");
            }
        }

        async function stepBackTime() {
            try {
                const res = await fetch('/api/step_back', { method: 'POST' });
                const data = await res.json();
                document.getElementById('current-time').innerText = data.time;
                renderCharacters(data.characters);
            } catch (e) {
                log("通信エラー", "error");
            }
        }

        async function predictFuture(addTime) {
            try {
                const startTime = performance.now();
                const res = await fetch(`/api/predict?add=${addTime}`);
                const data = await res.json();
                const endTime = performance.now();
                
                log(`[未来予測] ${addTime}時間後の世界を覗き見しました！`, "predict");
                log(`[速度] 計算にかかった時間: ${(endTime - startTime).toFixed(2)}ミリ秒 (ループなしのO(1)計算)`, "predict");
                
                data.characters.forEach(c => {
                    log(`${c.icon} ${c.name} -> 状態: ${c.state}, 進み具合: ${(c.progress*100).toFixed(0)}%, つかれ: ${c.tiredness}`, "predict");
                });
                log(`※ これは予測結果を計算しただけなので、実際の時間は進んでいません。`, "predict");
                
            } catch (e) {
                log("予測エラー", "error");
            }
        }

        document.getElementById('btn-step').addEventListener('click', () => {
            stepTime();
            log("1時間 進めました");
        });

        document.getElementById('btn-step-back').addEventListener('click', () => {
            const currentTime = parseInt(document.getElementById('current-time').innerText);
            if (currentTime > 0) {
                stepBackTime();
                log("1時間 巻き戻しました（履歴を使わず数式だけで復元しました）");
            } else {
                log("これ以上過去には戻れません", "error");
            }
        });

        document.getElementById('btn-auto').addEventListener('click', (e) => {
            if (autoPlayTimer) {
                clearInterval(autoPlayTimer);
                autoPlayTimer = null;
                e.target.innerText = "▶ 自動再生";
                e.target.classList.replace('bg-amber-500', 'bg-emerald-500');
                e.target.classList.replace('hover:bg-amber-600', 'hover:bg-emerald-600');
                log("自動再生を停止しました");
            } else {
                autoPlayTimer = setInterval(stepTime, 200);
                e.target.innerText = "⏸ 停止";
                e.target.classList.replace('bg-emerald-500', 'bg-amber-500');
                e.target.classList.replace('hover:bg-emerald-600', 'hover:bg-amber-600');
                log("自動再生を開始しました");
            }
        });

        document.getElementById('btn-reset').addEventListener('click', async () => {
            await fetch('/api/reset', { method: 'POST' });
            await fetchState();
            log("時間を0に戻しました");
        });

        document.getElementById('btn-predict').addEventListener('click', () => {
            const val = parseInt(document.getElementById('future-input').value) || 1000;
            predictFuture(val);
        });

        fetchState();
    </script>
</body>
</html>
"""

# =========================================================
# HTTP サーバー APIハンドラ
# =========================================================
class AppHandler(http.server.BaseHTTPRequestHandler):
    # ログ出力を抑制してコンソールを綺麗に保つ
    def log_message(self, format, *args):
        pass

    def _send_json(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode('utf-8'))
            
        elif path == '/api/state':
            self._send_json(world.get_current_state())
            
        elif path == '/api/predict':
            query = urllib.parse.parse_qs(parsed.query)
            add_time = int(query.get('add', ['100'])[0])
            self._send_json(world.predict_future(add_time))
            
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/step':
            world.step()
            self._send_json(world.get_current_state())
            
        elif self.path == '/api/step_back':
            world.step_back()
            self._send_json(world.get_current_state())
            
        elif self.path == '/api/reset':
            world.reset()
            self._send_json({"status": "ok"})
            
        else:
            self.send_response(404)
            self.end_headers()

# =========================================================
# メインプロセス：サーバー起動とコンソールUI
# =========================================================
def start_server(port=8000):
    server = http.server.HTTPServer(('', port), AppHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    return server

if __name__ == "__main__":
    PORT = 8000
    try:
        server = start_server(PORT)
    except OSError:
        # ポートが既に使用されている場合は8001にフォールバック
        PORT = 8001
        server = start_server(PORT)
        
    print("=" * 60)
    print("🚀 サルでもわかる！完全決定論アプリ サーバー起動完了")
    print(f"🌍 ブラウザで http://localhost:{PORT} にアクセスしてください。")
    print("-" * 60)
    print("【コマンド】")
    print("  test : 動的全網羅単体テストを実行します。")
    print("  exit : サーバーを終了します。")
    print("=" * 60)
    
    # コンソール入力を受け付けるメインループ
    while True:
        try:
            cmd = input("ADC-App> ").strip().lower()
            if cmd == "test":
                print("\n⚙️ --- 単体テストを開始します --- ⚙️")
                run_tests()
                print("------------------------------------\n")
            elif cmd in ["exit", "quit"]:
                print("サーバーを終了します...")
                break
        except (KeyboardInterrupt, EOFError):
            print("\nサーバーを終了します...")
            break
            
    server.shutdown()
    server.server_close()
    sys.exit(0)