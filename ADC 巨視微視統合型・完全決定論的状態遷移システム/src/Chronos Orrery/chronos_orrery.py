import os
import sys
import math
import random
import webview
import unittest

# --- フロントエンド（HTML/CSS/JavaScript） ---
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>Chronos Orrery v2 - Complete Determinism Model</title>
    <style>
        :root {
            --bg-color: #030308;
            --panel-bg: rgba(10, 15, 30, 0.6);
            --border-color: rgba(100, 200, 255, 0.2);
            --accent-color: #60a5fa;
            --text-main: #e2e8f0;
            --text-sub: #94a3b8;
            --monitor-green: #34d399;
            --monitor-red: #f87171;
            --monitor-blue: #60a5fa;
        }

        body {
            margin: 0;
            background-color: var(--bg-color);
            background-image: radial-gradient(circle at 50% 50%, #0a0f1a 0%, #020205 100%);
            color: var(--text-main);
            font-family: 'Consolas', 'Courier New', monospace;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            overflow: hidden;
            gap: 20px;
            padding: 20px;
            box-sizing: border-box;
        }

        /* 左側：HUDモニター */
        #hud-monitor {
            width: 280px;
            height: 620px;
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 20px;
            box-sizing: border-box;
            box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.8), 0 0 15px rgba(100, 200, 255, 0.05);
            display: flex;
            flex-direction: column;
            backdrop-filter: blur(10px);
        }

        .hud-header {
            font-size: 18px;
            font-weight: bold;
            color: var(--accent-color);
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 10px;
            margin-bottom: 15px;
            letter-spacing: 2px;
            text-shadow: 0 0 5px var(--accent-color);
        }

        .hud-section {
            margin-bottom: 20px;
        }

        .hud-label {
            font-size: 11px;
            color: var(--text-sub);
            margin-bottom: 4px;
            letter-spacing: 1px;
        }

        .hud-value {
            font-size: 20px;
            color: var(--monitor-green);
            text-shadow: 0 0 5px rgba(52, 211, 153, 0.5);
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .hud-value.blue { color: var(--monitor-blue); text-shadow: 0 0 5px rgba(96, 165, 250, 0.5); }
        .hud-value.red { color: var(--monitor-red); text-shadow: 0 0 5px rgba(248, 113, 113, 0.5); }
        .hud-value.purple { color: #c7d2fe; text-shadow: 0 0 5px rgba(199, 210, 254, 0.5); }

        /* プログレスバー風の装飾 */
        .bar-container {
            width: 100%;
            height: 4px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 2px;
            margin-bottom: 15px;
            overflow: hidden;
        }
        .bar-fill {
            height: 100%;
            background: var(--monitor-green);
            transition: width 0.1s linear, background-color 0.3s;
        }

        /* 中央：天球儀キャンバス */
        #canvas-wrapper {
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        #canvas-container {
            position: relative;
            box-shadow: 0 0 50px rgba(100, 200, 255, 0.05);
            border-radius: 50%;
            overflow: hidden;
            background: #020205;
            border: 1px solid rgba(255, 255, 255, 0.1);
            width: 600px;
            height: 600px;
        }

        canvas {
            display: block;
        }

        .title {
            margin: 0 0 15px 0;
            font-weight: 300;
            letter-spacing: 6px;
            color: #c7d2fe;
            font-family: 'Helvetica Neue', sans-serif;
            text-shadow: 0 0 10px rgba(199, 210, 254, 0.5);
        }

        /* 右側：コントロールパネル */
        #control-panel {
            width: 280px;
            height: 620px;
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 20px;
            box-sizing: border-box;
            box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.8), 0 0 15px rgba(100, 200, 255, 0.05);
            display: flex;
            flex-direction: column;
            gap: 20px;
            backdrop-filter: blur(10px);
        }

        .control-group {
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 6px;
            padding: 15px;
        }

        .control-group-title {
            font-size: 12px;
            color: var(--accent-color);
            margin-bottom: 15px;
            letter-spacing: 1px;
            border-bottom: 1px dashed rgba(255, 255, 255, 0.1);
            padding-bottom: 5px;
        }

        /* 時間操作ボタン */
        .time-buttons {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }
        .time-buttons button.full-width {
            grid-column: span 2;
        }

        button {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: white;
            padding: 10px 15px;
            border-radius: 4px;
            font-size: 13px;
            font-family: inherit;
            cursor: pointer;
            transition: all 0.2s ease;
            letter-spacing: 1px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }

        button:hover {
            background: rgba(255, 255, 255, 0.15);
            border-color: rgba(255, 255, 255, 0.3);
        }

        button.active {
            background: rgba(96, 165, 250, 0.2);
            border-color: var(--accent-color);
            color: var(--accent-color);
            box-shadow: 0 0 15px rgba(96, 165, 250, 0.3);
        }

        /* 光の追加コントロール */
        .input-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
        }

        .input-row label {
            font-size: 12px;
            color: var(--text-sub);
        }

        input[type="color"] {
            -webkit-appearance: none;
            border: none;
            width: 40px;
            height: 24px;
            border-radius: 4px;
            cursor: pointer;
            background: none;
        }
        input[type="color"]::-webkit-color-swatch-wrapper { padding: 0; }
        input[type="color"]::-webkit-color-swatch { border: 1px solid rgba(255,255,255,0.2); border-radius: 4px; }

        input[type="range"] {
            width: 100px;
            accent-color: var(--accent-color);
        }

        .action-button {
            width: 100%;
            margin-bottom: 8px;
        }
        .action-button.add { border-color: rgba(52, 211, 153, 0.4); color: #a7f3d0; }
        .action-button.add:hover { background: rgba(52, 211, 153, 0.15); }
        
        .action-button.remove { border-color: rgba(248, 113, 113, 0.4); color: #fecaca; }
        .action-button.remove:hover { background: rgba(248, 113, 113, 0.15); }

    </style>
</head>
<body>

    <!-- 左側：HUDモニター -->
    <div id="hud-monitor">
        <div class="hud-header">ORRERY STATUS</div>
        
        <div class="hud-section">
            <div class="hud-label">GLOBAL TIME (絶対時間)</div>
            <div class="hud-value purple" id="val-global-time">0.00</div>
        </div>

        <div class="hud-section">
            <div class="hud-label">CURRENT TIME SCALE</div>
            <div class="hud-value" id="val-time-scale">1.00x</div>
            <div class="bar-container">
                <div class="bar-fill" id="bar-time-scale" style="width: 50%;"></div>
            </div>
            
            <div class="hud-label">TARGET TIME SCALE</div>
            <div class="hud-value blue" id="val-target-scale">1.00x</div>
        </div>

        <div class="hud-section">
            <div class="hud-label">ACTIVE ENTITIES (現在の光の数)</div>
            <div class="hud-value" id="val-entities">200</div>
            <div class="bar-container">
                <div class="bar-fill" id="bar-entities" style="width: 40%; background: var(--monitor-blue);"></div>
            </div>
        </div>

        <div class="hud-section">
            <div class="hud-label">SYSTEM ENTROPY (角速度の総和)</div>
            <div class="hud-value red" id="val-entropy">0.000</div>
        </div>
        
        <div class="hud-section" style="margin-top: auto;">
            <div class="hud-label">SYSTEM LOG</div>
            <div id="sys-log" style="font-size: 10px; color: #64748b; line-height: 1.4; word-wrap: break-word;">
                > ORRERY INITIALIZED.<br>
                > AWAITING COMMAND...
            </div>
        </div>
    </div>

    <!-- 中央：天球儀 -->
    <div id="canvas-wrapper">
        <h2 class="title">CHRONOS ORRERY</h2>
        <div id="canvas-container">
            <canvas id="gardenCanvas" width="600" height="600"></canvas>
        </div>
    </div>

    <!-- 右側：コントロールパネル -->
    <div id="control-panel">
        
        <!-- 時間操作 -->
        <div class="control-group">
            <div class="control-group-title">TIME CONTROL (時間操作)</div>
            <div class="time-buttons">
                <button id="btn-rewind" onclick="setTimeMode('REWIND')">⏪ 遡行</button>
                <button id="btn-slow" onclick="setTimeMode('SLOW')">🐢 減速</button>
                <button id="btn-play" class="active full-width" onclick="setTimeMode('PLAY')">▶️ 標準時間</button>
                <button id="btn-stop" onclick="setTimeMode('STOP')">⏸️ 停止</button>
                <button id="btn-fast" onclick="setTimeMode('FAST')">⏩ 加速</button>
            </div>
        </div>

        <!-- エンティティ操作 -->
        <div class="control-group">
            <div class="control-group-title">ENTITY CONTROL (光の操作)</div>
            
            <div class="input-row">
                <label>COLOR (色)</label>
                <input type="color" id="light-color" value="#a78bfa">
            </div>
            
            <div class="input-row">
                <label>SIZE (大きさ)</label>
                <input type="range" id="light-size" min="1" max="6" step="0.5" value="2.5">
                <span id="size-val" style="font-size:12px; width:20px; text-align:right;">2.5</span>
            </div>

            <button class="action-button add" onclick="addEntity()">✨ 光を追加する</button>
            <button class="action-button remove" onclick="removeEntity()">🗑️ 古い光を消す</button>
        </div>
        
    </div>

<script>
const canvas = document.getElementById('gardenCanvas');
const ctx = canvas.getContext('2d');

// HUDのDOM要素
const elGlobalTime = document.getElementById('val-global-time');
const elTimeScale = document.getElementById('val-time-scale');
const barTimeScale = document.getElementById('bar-time-scale');
const elTargetScale = document.getElementById('val-target-scale');
const elEntities = document.getElementById('val-entities');
const barEntities = document.getElementById('bar-entities');
const elEntropy = document.getElementById('val-entropy');
const sysLog = document.getElementById('sys-log');

let rawData = null;

// サイズスライダーの表示連動
document.getElementById('light-size').addEventListener('input', function(e) {
    document.getElementById('size-val').innerText = e.target.value;
});

function logMessage(msg) {
    const lines = sysLog.innerHTML.split('<br>');
    if (lines.length > 4) lines.shift(); // ログの表示行数を調整
    lines.push(`> ${msg}`);
    sysLog.innerHTML = lines.join('<br>');
}

// 描画関数
function drawOrrery() {
    if (!rawData) return;

    // 現在の時間スケールに応じた残像の長さを計算（速いほどブレる）
    const tScale = Math.abs(rawData.time_scale);
    const alpha = Math.max(0.05, Math.min(0.3, 0.2 - (tScale * 0.02)));
    
    // 残像効果
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = `rgba(2, 2, 5, ${alpha})`; 
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.globalCompositeOperation = 'lighter';

    const entities = rawData.entities;
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;

    // 中心太陽
    ctx.beginPath();
    ctx.arc(cx, cy, 10, 0, Math.PI * 2);
    ctx.fillStyle = '#ffffff';
    ctx.shadowBlur = 30;
    ctx.shadowColor = '#e0e7ff';
    ctx.fill();

    // エンティティ（光の点）
    for (let i = 0; i < entities.length; i++) {
        const e = entities[i];
        
        ctx.beginPath();
        ctx.arc(e.x, e.y, e.size, 0, Math.PI * 2);
        
        ctx.fillStyle = e.color;
        ctx.shadowBlur = e.size * 3;
        ctx.shadowColor = e.color;
        
        ctx.fill();
        ctx.shadowBlur = 0;
    }

    // --- HUDモニターの更新 ---
    elGlobalTime.innerText = rawData.global_time.toFixed(2);

    const scale = rawData.time_scale;
    elTimeScale.innerText = scale.toFixed(2) + 'x';
    
    // バーの計算：-5x 〜 5x を 0% 〜 100% にマッピング
    const scalePercent = ((scale + 5) / 10) * 100;
    barTimeScale.style.width = `${Math.max(0, Math.min(100, scalePercent))}%`;
    
    // 色の変更（マイナスなら赤、プラスなら緑）
    if (scale < -0.1) {
        elTimeScale.className = 'hud-value red';
        barTimeScale.style.background = 'var(--monitor-red)';
    } else if (scale > 0.1) {
        elTimeScale.className = 'hud-value';
        barTimeScale.style.background = 'var(--monitor-green)';
    } else {
        elTimeScale.className = 'hud-value blue';
        barTimeScale.style.background = 'var(--monitor-blue)';
    }

    elTargetScale.innerText = rawData.target_scale.toFixed(2) + 'x';
    
    const count = entities.length;
    elEntities.innerText = count;
    barEntities.style.width = `${Math.min(100, (count / 500) * 100)}%`; 
    
    elEntropy.innerText = rawData.entropy.toFixed(4);
}

// バックエンド通信ループ
function updateLoop() {
    pywebview.api.update_simulation().then(data => {
        rawData = data;
        drawOrrery();
        requestAnimationFrame(updateLoop);
    });
}

// 時間操作
function setTimeMode(mode) {
    document.querySelectorAll('.time-buttons button').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`btn-${mode.toLowerCase()}`).classList.add('active');
    pywebview.api.set_time_mode(mode);
    logMessage(`TIME MODE SET: ${mode}`);
}

// 光の追加
function addEntity() {
    const color = document.getElementById('light-color').value;
    const size = parseFloat(document.getElementById('light-size').value);
    pywebview.api.add_entity(size, color).then(res => {
        if(res) logMessage(`ENTITY ADDED [${color}]`);
    });
}

// 光の削除
function removeEntity() {
    pywebview.api.remove_entity().then(res => {
        if(res) logMessage(`OLDEST ENTITY REMOVED`);
        else logMessage(`ERR: NO ACTIVE ENTITIES`);
    });
}

// 起動
window.addEventListener('pywebviewready', () => {
    updateLoop();
    logMessage('SYSTEM READY.');
});
</script>
</body>
</html>
"""

# --- バックエンド（Python：時間管理と完全決定論的位相力学） ---
class ChronosOrrery:
    def __init__(self):
        self.width = 600
        self.height = 600
        self.cx = self.width / 2
        self.cy = self.height / 2
        
        # --- 時間管理 (ADC Absolute Tick Management) ---
        self.global_time = 0.0        # システムの絶対時間（過去未来の座標軸）
        self.target_time_scale = 1.0  
        self.current_time_scale = 1.0 
        self.morph_speed = 0.05       # 慣性係数
        
        # --- エンティティの履歴と状態 (SoA構造) ---
        self.radii = []           # 中心からの距離
        self.initial_phases = []  # 初期位相 (t=0のときの角度)
        self.angular_vels = []    # 回転速度（角速度）
        self.sizes = []           # 大きさ
        self.colors = []          # 色
        
        # 決定論的ロールバックのための「誕生」と「消滅」のタイムスタンプ
        self.birth_times = []     
        self.death_times = []     
        
        # 初期生成（200個：ビッグバン以前から存在するものとして扱う）
        for _ in range(200):
            self._generate_random_entity(birth_time=-math.inf)

    def _generate_random_entity(self, birth_time):
        """ランダムな軌道・色・速度のエンティティを生成して追加する内部関数"""
        colors_palette = [
            'rgba(199, 210, 254, 0.8)', # 薄いインディゴ
            'rgba(165, 180, 252, 0.8)',
            'rgba(129, 140, 248, 0.8)',
            'rgba(244, 114, 182, 0.7)', # 薄いピンク
            'rgba(45, 212, 191, 0.7)',  # ティール
        ]
        layer = random.randint(1, 10)
        radius = layer * 25 + random.uniform(-2, 2)
        base_speed = (11 - layer) * 0.002
        
        if layer % 2 == 0:
            base_speed *= -0.8
            color = colors_palette[4]
        else:
            color = random.choice(colors_palette[:4])
            
        speed = base_speed + random.uniform(-0.0005, 0.0005)
        size = random.uniform(1.0, 3.5)
        
        # 絶対時間に基づくO(1)計算のため、現在の位相をそのまま初期位相とする
        self._append_data(radius, random.uniform(0, math.pi * 2), speed, size, color, birth_time)

    def _append_data(self, radius, initial_phase, speed, size, color, birth_time):
        """SoAの配列にデータを追加。death_timeは未定（None）"""
        self.radii.append(radius)
        self.initial_phases.append(initial_phase)
        self.angular_vels.append(speed)
        self.sizes.append(size)
        self.colors.append(color)
        self.birth_times.append(birth_time)
        self.death_times.append(None)

    def set_time_mode(self, mode):
        """UIからの時間操作コマンドを受け取る"""
        if mode == 'STOP':
            self.target_time_scale = 0.0
        elif mode == 'PLAY':
            self.target_time_scale = 1.0
        elif mode == 'SLOW':
            self.target_time_scale = 0.2
        elif mode == 'FAST':
            self.target_time_scale = 5.0
        elif mode == 'REWIND':
            self.target_time_scale = -2.0

    def add_entity(self, size, hex_color):
        """UIから新しい光を追加する。追加した「絶対時間」を記録する"""
        layer = random.randint(1, 10)
        radius = layer * 25 + random.uniform(-2, 2)
        
        direction = 1 if random.random() > 0.5 else -0.8
        base_speed = (11 - layer) * 0.002 * direction
        speed = base_speed + random.uniform(-0.0005, 0.0005)
        
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        rgba_color = f"rgba({r}, {g}, {b}, 0.8)"
        
        # 逆算して、現在のglobal_timeでの見た目が合致するようにinitial_phaseを決定
        current_angle = random.uniform(0, math.pi * 2)
        initial_phase = current_angle - (speed * self.global_time)
        
        # 現在の絶対時間(global_time)を誕生時刻として記録
        self._append_data(radius, initial_phase, speed, float(size), rgba_color, self.global_time)
        return True

    def remove_entity(self):
        """現在の絶対時間においてアクティブな光のうち、最も古いものを削除としてマーキングする"""
        active_indices = []
        for i in range(len(self.radii)):
            if self.birth_times[i] <= self.global_time and (self.death_times[i] is None or self.global_time < self.death_times[i]):
                active_indices.append(i)
        
        if active_indices:
            # 現在表示されているものの中で、最も誕生が古いものを探す
            oldest_idx = min(active_indices, key=lambda i: self.birth_times[i])
            # データを消去せず、現在の絶対時間を「死亡時刻」として記録する
            self.death_times[oldest_idx] = self.global_time
            return True
        return False

    def update_simulation(self):
        """絶対時間に基づく O(1) 完全決定論予測"""
        
        # 1. 時間スケールの滑らかな遷移と絶対時間（Global Time）の更新
        self.current_time_scale += (self.target_time_scale - self.current_time_scale) * self.morph_speed
        self.global_time += self.current_time_scale
        
        active_entities = []
        total_entropy = 0.0
        
        # 2. 全エンティティの履歴照合と位相算出
        for i in range(len(self.radii)):
            # 【履歴照合】誕生時刻を過ぎており、かつ死亡時刻に達していないものだけを描画
            if self.birth_times[i] <= self.global_time and (self.death_times[i] is None or self.global_time < self.death_times[i]):
                
                # 【O(1) 予測】前フレームの角度に足し算するのではなく、絶対時間から一意に角度を計算する
                # これにより、どれだけ時間を巻き戻してもズレが一切生じない
                phase = self.initial_phases[i] + self.angular_vels[i] * self.global_time
                
                total_entropy += abs(self.angular_vels[i] * self.current_time_scale)
                
                x = self.cx + math.cos(phase) * self.radii[i]
                y = self.cy + math.sin(phase) * self.radii[i]
                
                active_entities.append({
                    "x": x,
                    "y": y,
                    "size": self.sizes[i],
                    "color": self.colors[i]
                })

        return {
            "global_time": self.global_time,
            "time_scale": self.current_time_scale,
            "target_scale": self.target_time_scale,
            "entropy": total_entropy,
            "entities": active_entities
        }

# --- 動的単体テスト（ADC 完全決定論の検証スイート） ---
class TestChronosOrrery(unittest.TestCase):
    
    def setUp(self):
        """テスト前の初期化。ランダムシードを固定し、決定論的挙動を担保する"""
        random.seed(42)
        self.orrery = ChronosOrrery()

    def test_01_soa_structure_integrity(self):
        """SoA (Structure of Arrays) データ構造の整合性テスト"""
        o = self.orrery
        # 全ての内部配列が初期設定数(200)で一致しているか
        self.assertEqual(len(o.radii), 200)
        self.assertEqual(len(o.initial_phases), 200)
        self.assertEqual(len(o.angular_vels), 200)
        self.assertEqual(len(o.sizes), 200)
        self.assertEqual(len(o.colors), 200)
        self.assertEqual(len(o.birth_times), 200)
        self.assertEqual(len(o.death_times), 200)

    def test_02_time_mode_setting(self):
        """時間モード（CVD: Time Manager）の設定と目標値の検証"""
        modes_expected = {
            'STOP': 0.0,
            'PLAY': 1.0,
            'SLOW': 0.2,
            'FAST': 5.0,
            'REWIND': -2.0
        }
        for mode, expected in modes_expected.items():
            self.orrery.set_time_mode(mode)
            self.assertEqual(self.orrery.target_time_scale, expected)

    def test_03_morphing_dynamics(self):
        """時間スケールの滑らかな遷移（慣性）の検証"""
        self.orrery.set_time_mode('FAST')  # target = 5.0
        self.orrery.current_time_scale = 1.0
        self.orrery.update_simulation()
        
        # 1.0 から 5.0 に向かって morph_speed (0.05) 分だけ近づくか
        expected_scale = 1.0 + (5.0 - 1.0) * 0.05
        self.assertAlmostEqual(self.orrery.current_time_scale, expected_scale)

    def test_04_add_entity(self):
        """光の追加と絶対時間（Global Time）の記録テスト"""
        # 時を100.0まで進める
        self.orrery.global_time = 100.0
        
        # 光を追加
        self.orrery.add_entity(3.0, "#ff0000")
        
        # 要素数が1つ増え、誕生時刻が100.0で記録されているか
        self.assertEqual(len(self.orrery.radii), 201)
        self.assertEqual(self.orrery.birth_times[-1], 100.0)
        self.assertIsNone(self.orrery.death_times[-1])

    def test_05_remove_entity(self):
        """光の消去（論理削除）と死亡時刻の記録テスト"""
        self.orrery.global_time = 50.0
        
        # 初期状態で画面に表示される数を確認
        res_before = self.orrery.update_simulation()
        active_before = len(res_before['entities'])
        
        # 光を1つ消去
        success = self.orrery.remove_entity()
        self.assertTrue(success)
        
        # 論理削除として、最も古い要素(インデックス0)のdeath_timeに時刻が記録される
        self.assertEqual(self.orrery.death_times[0], self.orrery.global_time)
        
        # 次フレームで画面上の表示数が1つ減っているか
        res_after = self.orrery.update_simulation()
        active_after = len(res_after['entities'])
        self.assertEqual(active_after, active_before - 1)

    def test_06_absolute_determinism_rollback(self):
        """【コア機能検証】完全決定論的ロールバックの統合テスト"""
        
        # --- [フェーズ1: 初期状態の記録] ---
        self.orrery.global_time = 0.0
        self.orrery.current_time_scale = 1.0
        self.orrery.target_time_scale = 1.0
        
        res_initial = self.orrery.update_simulation()
        initial_count = len(res_initial['entities'])
        initial_first_x = res_initial['entities'][0]['x']
        initial_first_y = res_initial['entities'][0]['y']

        # 10フレーム進める
        for _ in range(10): self.orrery.update_simulation()

        # --- [フェーズ2: 未来での操作] ---
        # 1. 光を追加
        self.orrery.add_entity(2.5, "#00ff00")
        time_added = self.orrery.global_time
        
        for _ in range(10): self.orrery.update_simulation()
            
        # 2. 光を消去
        self.orrery.remove_entity()
        time_removed = self.orrery.global_time

        for _ in range(10): self.orrery.update_simulation()
            
        # --- [フェーズ3: 過去への遡行 (REWIND) と状態復元チェック] ---
        
        # 巻き戻しを完全にコントロールするため、強制的にスケールをマイナスに固定
        self.orrery.target_time_scale = -1.0
        self.orrery.current_time_scale = -1.0
        
        # 「光を消去した直前」まで時間を戻す
        while self.orrery.global_time >= time_removed:
            self.orrery.update_simulation()
            
        # 【検証】消去した光が復活し、個数が(初期値+1)になっているか
        res_revived = self.orrery.update_simulation()
        self.assertEqual(len(res_revived['entities']), initial_count + 1)
        
        # 「光を追加した直前」まで時間を戻す
        while self.orrery.global_time >= time_added:
            self.orrery.update_simulation()
            
        # 【検証】追加した光が「まだ存在しない状態」に戻り、個数が初期値に戻っているか
        res_pre_add = self.orrery.update_simulation()
        self.assertEqual(len(res_pre_add['entities']), initial_count)

        # 初期状態付近まで巻き戻す
        while self.orrery.global_time > res_initial['global_time']:
            self.orrery.update_simulation()
            
        # O(1)位相跳躍の完全性を証明するため、絶対時間を「初期状態と同じ時刻」に指定して再計算する
        # (update_simulation() は内部で global_time に current_time_scale を足すため、事前に引いておく)
        self.orrery.global_time = res_initial['global_time'] - self.orrery.current_time_scale 
        res_final = self.orrery.update_simulation()
        
        final_first_x = res_final['entities'][0]['x']
        final_first_y = res_final['entities'][0]['y']
        
        # 【検証】座標が浮動小数点誤差の範囲内で「完全に」初期位置と一致するか
        self.assertAlmostEqual(initial_first_x, final_first_x, places=5, msg="X座標の完全復元に失敗")
        self.assertAlmostEqual(initial_first_y, final_first_y, places=5, msg="Y座標の完全復元に失敗")


# --- アプリケーション起動 / テスト実行ルーチン ---
if __name__ == '__main__':
    # ターミナルから `python chronos_orrery.py test` と実行された場合はテストスイートを起動する
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        print("=== CHRONOS ORRERY: ADC 完全決定論テストシーケンスを開始します ===")
        # unittestモジュールが誤動作しないように引数 'test' を削除
        sys.argv.pop(1)
        # 詳細なテスト結果を出力するために verbosity=2 を設定
        unittest.main(verbosity=2)
    else:
        # 引数なしの場合は通常のGUIモードとして起動
        bridge = ChronosOrrery()
        
        window = webview.create_window(
            title='Chronos Orrery v2.0', 
            html=HTML_CONTENT, 
            js_api=bridge,
            width=1240,
            height=720,
            resizable=False
        )
        
        webview.start()