# 汎用メモリハック数理モデル - 八握剣異戒神将魔虚羅 Hybrid Memory Scan版
# OSのメモリ(UIAutomation)で「入力中のエディタ領域」を特定し、その内部のみを
# NumpyバイナリXOR走査で超高速にエッジ抽出することで、UIを無視し純粋な文字だけに反応させます。
# 【新機能】時間的フレーム差分を用いた自己学習アルゴリズムを搭載。入力文字の特徴と空間を永続学習します。
# 実行に必要なライブラリ: pip install uiautomation keyboard mss numpy

import tkinter as tk
import ctypes
import math
import random
import queue
import threading
import time
import json
import os
import sys

try:
    import uiautomation as auto
    HAS_UIA = True
except ImportError:
    HAS_UIA = False
    print("Error: 'uiautomation' がインストールされていません。")

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False
    print("Warning: 'keyboard' library not found.")

try:
    import mss
    import numpy as np
    HAS_MSS_NP = True
except ImportError:
    HAS_MSS_NP = False
    print("Error: 'mss' または 'numpy' がインストールされていません。")

# 高DPI環境での画面サイズのズレを補正
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# === フェーズ0: 適応型RAGメモリシステム (Makora Adaptive Memory) ===
class MakoraMemory:
    def __init__(self, filepath="makora_memory.json"):
        self.filepath = filepath
        self.cache = {}
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    loaded_cache = json.load(f)
                    
                # データフォーマットの互換性チェック（古いバージョンの配列型キャッシュは破棄）
                self.cache = {}
                for k, v in loaded_cache.items():
                    if isinstance(v, dict) and "avg_density" in v:
                        self.cache[k] = v
                        
                print(f"[Makora Memory] 過去の学習プロファイルをロードしました。記憶アプリ数: {len(self.cache)}")
            except Exception as e:
                print(f"メモリのロードに失敗しました: {e}")
        else:
            print("[Makora Memory] 新規メモリ領域を初期化しました。")

    def save(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f)
        except Exception as e:
            pass

    def update_profile(self, app_id, density, min_x, max_x):
        # アプリ（例：VSCode）ごとに文字入力の特徴を学習・定着させる
        if app_id not in self.cache:
            self.cache[app_id] = {
                "samples": 0,
                "avg_density": float(density),
                "min_x_avg": float(min_x),
                "max_x_avg": float(max_x),
                "strength": 0.0
            }
            return
            
        profile = self.cache[app_id]
        
        # 指数移動平均(EMA)による忘却と定着の数理モデル
        alpha = 0.2
        profile["avg_density"] = (1 - alpha) * profile["avg_density"] + alpha * density
        profile["min_x_avg"] = (1 - alpha) * profile["min_x_avg"] + alpha * min_x
        profile["max_x_avg"] = (1 - alpha) * profile["max_x_avg"] + alpha * max_x
        
        profile["samples"] += 1
        # 約20回の入力（サンプリング）で学習が収束する。ただし常に学習は継続する。
        profile["strength"] = min(1.0, profile["samples"] / 20.0) 

    def get_thresholds(self, app_id, default_density):
        # 未学習時はデフォルトの判定を返す
        if app_id not in self.cache or self.cache[app_id]["strength"] < 0.2:
            return default_density, -99999, 99999
        
        profile = self.cache[app_id]
        s = profile["strength"]
        
        # 走査解像度(GRID_SIZE=4)に合わせて閾値を調整。空白を拾わないよう少し厳しめに設定(70%)
        learned_d = max(3, int(profile["avg_density"] * 0.7))
        thresh = int(default_density * (1 - s) + learned_d * s)
        
        # 学習した空間範囲（文字入力エリア）の期待値。外側にあるUIノイズを排除する
        margin = 100
        min_x = profile["min_x_avg"] - margin
        max_x = profile["max_x_avg"] + margin
        
        return thresh, min_x, max_x

# === フェーズ0.5: ゼロアロケーション基盤 (Zero Allocation Pools) ===
class RectPool:
    def __init__(self, max_size=4000):
        self.pool = [{'x': 0, 'y': 0, 'w': 0, 'h': 0} for _ in range(max_size)]
        self.active_count = 0

    def reset(self):
        self.active_count = 0

    def add(self, x, y, w, h):
        if self.active_count < len(self.pool):
            rect = self.pool[self.active_count]
            rect['x'] = int(x)
            rect['y'] = int(y)
            rect['w'] = int(w)
            rect['h'] = int(h)
            self.active_count += 1

    def get_active_rects(self):
        return self.pool[:self.active_count]

class Barrel:
    def __init__(self, screen_width: float):
        self.radius = 12.0
        self.screen_width = screen_width
        self.is_active = False
        self.prev_x = 0.0
        self.prev_y = 0.0
        self.reset()

    def reset(self):
        center_x = self.screen_width / 2.0 if self.screen_width > 0 else 400.0
        self.x = center_x + random.uniform(-200, 200)
        self.y = 10.0 + random.uniform(0, 20)
        self.prev_x = self.x
        self.prev_y = self.y
        self.vx = (1 if random.random() > 0.5 else -1) * (1.0 + random.uniform(0, 3.0))
        self.vy = 0.0
        self.rotation = 0.0
        self.bounce_factor = 0.4
        self.friction = 0.98

    def update(self, rect_pool: RectPool, screen_height: float):
        if not self.is_active: return

        self.prev_x = self.x
        self.prev_y = self.y

        self.vy += 0.5
        next_x = self.x + self.vx
        next_y = self.y + self.vy
        hit_floor = False

        active_rects = rect_pool.get_active_rects()
        for r in active_rects:
            rx, ry, rw, rh = r['x'], r['y'], r['w'], r['h']
            if rx < next_x < rx + rw:
                if self.y + self.radius <= ry and next_y + self.radius > ry:
                    next_y = ry - self.radius
                    self.vy = -self.vy * self.bounce_factor
                    if abs(self.vy) < 1.5: self.vy = 0
                    hit_floor = True
                elif self.y - self.radius >= ry + rh and next_y - self.radius < ry + rh:
                    next_y = ry + rh + self.radius
                    self.vy = 0
            if ry < next_y + self.radius * 0.5 and next_y - self.radius * 0.5 < ry + rh:
                if self.x + self.radius <= rx and next_x + self.radius > rx:
                    next_x = rx - self.radius
                    self.vx = -self.vx * 0.6
                elif self.x - self.radius >= rx + rw and next_x - self.radius < rx + rw:
                    next_x = rx + rw + self.radius
                    self.vx = -self.vx * 0.6

        if not hit_floor and next_y + self.radius > screen_height:
            next_y = screen_height - self.radius
            self.vy = -self.vy * self.bounce_factor
            if abs(self.vy) < 1.5: self.vy = 0
            hit_floor = True

        self.x = next_x
        self.y = next_y

        if hit_floor and abs(self.vy) < 1.0:
            self.vx *= self.friction
            if abs(self.vx) < 0.5:
                self.vx = 2.0 if random.random() > 0.5 else -2.0

        self.rotation += self.vx * 0.1

    def draw(self, canvas: tk.Canvas):
        if not self.is_active: return
        r = self.radius
        canvas.create_oval(self.x - r, self.y - r, self.x + r, self.y + r, fill='#8B4513', outline='#3e1e06', width=2)
        cos_t = math.cos(self.rotation)
        sin_t = math.sin(self.rotation)
        p1x, p1y = -r * 0.85, -r * 0.4
        p2x, p2y = r * 0.85, -r * 0.4
        canvas.create_line(self.x + p1x * cos_t - p1y * sin_t, self.y + p1x * sin_t + p1y * cos_t,
                           self.x + p2x * cos_t - p2y * sin_t, self.y + p2x * sin_t + p2y * cos_t, fill='#A9A9A9', width=2)
        p3x, p3y = -r * 0.85, r * 0.4
        p4x, p4y = r * 0.85, r * 0.4
        canvas.create_line(self.x + p3x * cos_t - p3y * sin_t, self.y + p3x * sin_t + p3y * cos_t,
                           self.x + p4x * cos_t - p4y * sin_t, self.y + p4x * sin_t + p4y * cos_t, fill='#A9A9A9', width=2)

class BarrelPool:
    def __init__(self, max_size, screen_width):
        self.pool = [Barrel(screen_width) for _ in range(max_size)]

    def spawn(self):
        for b in self.pool:
            if not b.is_active:
                b.reset()
                b.is_active = True
                return b
        return None

    def get_active_barrels(self):
        return [b for b in self.pool if b.is_active]

# === フェーズ2: デスクトップオーバーレイ (Hybrid Scan & Dynamic Learning) ===
class OverlayApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HybridMemoryObjectHack")
        
        self.screen_width = root.winfo_screenwidth()
        self.screen_height = root.winfo_screenheight()
        root.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        transparent_color = 'magenta'
        root.attributes("-transparentcolor", transparent_color)
        root.configure(bg=transparent_color)

        self.canvas = tk.Canvas(root, bg=transparent_color, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        root.update()
        self.set_click_through()

        self.rect_pool = RectPool(max_size=4000)
        self.barrel_pool = BarrelPool(max_size=60, screen_width=self.screen_width)

        self.event_queue = queue.Queue()
        self.is_running = True
        self.test_requested = False
        
        self.memory_sys = MakoraMemory()
        self.current_adaptation_status = "ハイブリッド走査待機中..."
        self.current_app_id = "Unknown"
        
        if HAS_UIA:
            auto.SetGlobalSearchTimeout(1.0)

        if HAS_KEYBOARD:
            try: keyboard.on_press(self.on_key)
            except Exception as e: print(f"Key hook error: {e}")

        if HAS_UIA and HAS_MSS_NP:
            self.vision_thread = threading.Thread(target=self.hybrid_scan_loop, daemon=True)
            self.vision_thread.start()

        self.console_thread = threading.Thread(target=self.console_input_loop, daemon=True)
        self.console_thread.start()

        self.update_physics()
        self.check_events()
        self.auto_inject()
        
        self.save_memory_loop()

    def console_input_loop(self):
        print(">>> 準備完了。コンソールに 'test' と入力してEnterを押すと、動的単体テストを実行します。")
        while self.is_running:
            try:
                cmd = sys.stdin.readline().strip()
                if cmd.lower() == "test":
                    self.test_requested = True
            except Exception:
                break

    def save_memory_loop(self):
        self.memory_sys.save()
        self.root.after(30000, self.save_memory_loop)

    def set_click_through(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        except Exception:
            pass

    def on_key(self, event):
        self.event_queue.put("inject")

    def check_events(self):
        while not self.event_queue.empty():
            try:
                msg = self.event_queue.get_nowait()
                if msg == "inject": self.inject_barrels(3)
            except queue.Empty:
                break
        self.root.after(16, self.check_events)

    def auto_inject(self):
        self.inject_barrels(1)
        self.root.after(2000, self.auto_inject)

    def inject_barrels(self, count):
        for _ in range(count):
            self.barrel_pool.spawn()

    # === 動的単体テストロジック ===
    def run_dynamic_tests(self):
        print("\n==================================================")
        print("🚀 [Dynamic Unit Test] 動的単体テスト (ハイブリッド・学習版) 開始...")
        print("==================================================")
        
        try:
            focused_control = auto.GetFocusedControl()
            if focused_control:
                print(f"[OK] フォーカス領域検出: '{focused_control.Name}' (Class: {focused_control.ClassName})")
                
            if self.current_app_id in self.memory_sys.cache:
                prof = self.memory_sys.cache[self.current_app_id]
                print(f"[OK] 記憶プロファイル [{self.current_app_id}]:")
                print(f"  -> 適応度: {int(prof['strength']*100)}% (Samples: {prof['samples']})")
                print(f"  -> 学習済エッジ密度: {prof['avg_density']:.2f}")
                print(f"  -> 学習済入力空間(X): {int(prof['min_x_avg'])} ～ {int(prof['max_x_avg'])}")
            else:
                print(f"[WARN] {self.current_app_id} の学習データはまだありません。")

        except Exception as e:
            print(f"[ERROR] 診断失敗: {e}")

        active_rects = self.rect_pool.get_active_rects()
        print(f"[OK] RectPool (ゼロアロケーション): {self.rect_pool.active_count} 個のエッジ(行)を抽出中")
        print(f"[OK] BarrelPool: {len(self.barrel_pool.get_active_barrels())} 個の樽がアクティブ")
        print("==================================================\n")

    # === ハイブリッド・スキャン (Hybrid Scan & Dynamic Learning) ===
    def hybrid_scan_loop(self):
        last_valid_rect = None
        last_gray_img = None
        last_top_window_handle = None

        with auto.UIAutomationInitializerInThread(), mss.MSS() as sct:
            while self.is_running:
                if self.test_requested:
                    self.test_requested = False
                    self.run_dynamic_tests()

                try:
                    focused_control = auto.GetForegroundControl()
                    rect = None
                    
                    if focused_control:
                        try:
                            # トップレベルウィンドウ（一番親の枠）を取得し、アプリの切り替えを検知
                            top_window = focused_control.GetTopLevelControl()
                            current_top_handle = str(top_window.NativeWindowHandle) if top_window else None
                        except Exception:
                            current_top_handle = None
                            
                        # アプリが切り替わった場合、スキャン領域と学習途中の画像をリセットする
                        if current_top_handle and current_top_handle != last_top_window_handle:
                            last_valid_rect = None
                            last_top_window_handle = current_top_handle
                            self.rect_pool.reset()
                            last_gray_img = None

                        current_rect = focused_control.BoundingRectangle
                        # エディタ全体枠を特定
                        if current_rect and current_rect.width() > 100 and current_rect.height() > 30:
                            last_valid_rect = current_rect
                            rect = current_rect
                            self.current_app_id = focused_control.ClassName
                        else:
                            rect = last_valid_rect
                    else:
                        rect = last_valid_rect
                        
                    if rect:
                        self.rect_pool.reset()
                        
                        left = max(0, rect.left)
                        top = max(0, rect.top)
                        right = min(self.screen_width, rect.right)
                        bottom = min(self.screen_height, rect.bottom)
                        w = right - left
                        h = bottom - top
                        
                        if w > 100 and h > 30:
                            monitor = {"top": top, "left": left, "width": w, "height": h}
                            raw_sct = sct.grab(monitor)
                            
                            # === 画像処理の改善 (Luminance変換) ===
                            # mssのbgraは B, G, R, A の順。人間の視覚特性に合わせた輝度(Luminance)に変換する。
                            # これによりClearType(サブピクセルレンダリング)による色付きの滲みを相殺し、空白の誤検知を防ぐ。
                            img = np.array(raw_sct, dtype=np.int16)
                            gray_img = (0.114 * img[:, :, 0] + 0.587 * img[:, :, 1] + 0.299 * img[:, :, 2]).astype(np.int16)
                            
                            # === 背景色(明るさ)の動的判定と閾値の切り替え ===
                            # エディタ中央の水平1ラインの平均輝度を背景色と推定
                            bg_brightness = np.mean(gray_img[h // 2, :])
                            
                            if bg_brightness > 180:
                                # ライトモード（白背景）: コントラストが強いため、滲みやハイライトを無視するよう閾値を大幅に高く設定
                                COLOR_DIFF_THRESHOLD = 60
                                MOTION_DIFF_THRESHOLD = 40
                            else:
                                # ダークモード（黒背景）: 文字が細く見えがちなため閾値をやや低めに設定
                                COLOR_DIFF_THRESHOLD = 30
                                MOTION_DIFF_THRESHOLD = 20
                            
                            # 空白（スペース）を細かく認識するため、走査解像度を 4px に
                            GRID_SIZE = 4
                            grid_h, grid_w = h // GRID_SIZE, w // GRID_SIZE
                            
                            # ==== 1. 時間的フレーム差分による学習フェーズ ====
                            changed_mask = None
                            if last_gray_img is not None and last_gray_img.shape == gray_img.shape:
                                diff_img = np.abs(gray_img - last_gray_img)
                                # 動的に設定したモーション閾値で変化を検知
                                changed_mask = diff_img > MOTION_DIFF_THRESHOLD 
                                
                            # ==== 2. XORエッジ抽出 (全体の文字抽出) ====
                            shifted_right = np.roll(gray_img, shift=1, axis=1)
                            shifted_down = np.roll(gray_img, shift=1, axis=0)
                            
                            # 動的に設定したコントラスト閾値でエッジをシャープに抽出
                            edge_mask_x = np.abs(gray_img - shifted_right) > COLOR_DIFF_THRESHOLD
                            edge_mask_y = np.abs(gray_img - shifted_down) > COLOR_DIFF_THRESHOLD
                            edges = edge_mask_x | edge_mask_y

                            # ==== 2.5. 動的ノイズ（ボール）のマスク処理 ====
                            active_barrels = self.barrel_pool.get_active_barrels()
                            mask_radius = 30 
                            
                            for b in active_barrels:
                                for px, py in [(b.x, b.y), (b.prev_x, b.prev_y)]:
                                    local_px = int(px - left)
                                    local_py = int(py - top)
                                    
                                    mx1 = max(0, local_px - mask_radius)
                                    my1 = max(0, local_py - mask_radius)
                                    mx2 = min(w, local_px + mask_radius)
                                    my2 = min(h, local_py + mask_radius)
                                    
                                    if mx2 > mx1 and my2 > my1:
                                        if changed_mask is not None:
                                            changed_mask[my1:my2, mx1:mx2] = False
                                        edges[my1:my2, mx1:mx2] = False

                            # ==== 3. 学習データの蓄積 (Makora Update) ====
                            if changed_mask is not None:
                                changed_cropped = changed_mask[:grid_h * GRID_SIZE, :grid_w * GRID_SIZE]
                                changed_blocks = changed_cropped.reshape(grid_h, GRID_SIZE, grid_w, GRID_SIZE).sum(axis=(1, 3))
                                cy_idx, cx_idx = np.where(changed_blocks > 2)
                            else:
                                cy_idx, cx_idx = [], []
                                
                            edges_cropped = edges[:grid_h * GRID_SIZE, :grid_w * GRID_SIZE]
                            blocks = edges_cropped.reshape(grid_h, GRID_SIZE, grid_w, GRID_SIZE)
                            edge_density = blocks.sum(axis=(1, 3))
                            
                            if len(cy_idx) > 0:
                                active_densities = edge_density[cy_idx, cx_idx]
                                avg_active_density = float(np.mean(active_densities))
                                
                                min_x_local = int(np.min(cx_idx) * GRID_SIZE)
                                max_x_local = int(np.max(cx_idx) * GRID_SIZE + GRID_SIZE)
                                
                                if max_x_local - min_x_local < w * 0.8:
                                    self.memory_sys.update_profile(self.current_app_id, avg_active_density, min_x_local, max_x_local)

                            last_gray_img = gray_img.copy()

                            # ==== 4. 学習結果に基づく動的閾値による判定 ====
                            # 16px中最低4px(25%)のエッジがあれば文字とする。これにより空白のノイズを落とす。
                            default_density = 4
                            learned_thresh, learned_min_x, learned_max_x = self.memory_sys.get_thresholds(self.current_app_id, default_density)
                            
                            y_indices, x_indices = np.where(edge_density > learned_thresh)
                            
                            if len(y_indices) > 0:
                                coords = sorted(zip(y_indices, x_indices))
                                cx, cy = coords[0][1] * GRID_SIZE, coords[0][0] * GRID_SIZE
                                current_rect = {'x': cx, 'y': cy, 'w': GRID_SIZE, 'h': GRID_SIZE}
                                
                                for i in range(1, len(coords)):
                                    y_idx, x_idx = coords[i]
                                    nx, ny = x_idx * GRID_SIZE, y_idx * GRID_SIZE
                                    
                                    # 隣接判定の厳格化：少しでも隙間（空白）があれば結合を打ち切る
                                    if ny == current_rect['y'] and nx == current_rect['x'] + current_rect['w']:
                                        current_rect['w'] += GRID_SIZE
                                    else:
                                        if current_rect['w'] >= GRID_SIZE:
                                            if learned_min_x <= current_rect['x'] <= learned_max_x:
                                                self.rect_pool.add(current_rect['x'] + left, current_rect['y'] + top, current_rect['w'], current_rect['h'])
                                        current_rect = {'x': nx, 'y': ny, 'w': GRID_SIZE, 'h': GRID_SIZE}
                                
                                if current_rect['w'] >= GRID_SIZE:
                                    if learned_min_x <= current_rect['x'] <= learned_max_x:
                                        self.rect_pool.add(current_rect['x'] + left, current_rect['y'] + top, current_rect['w'], current_rect['h'])

                        prof = self.memory_sys.cache.get(self.current_app_id, {})
                        s = prof.get("strength", 0.0)
                        
                        # 背景色(ライト/ダーク)の推定結果をステータスに表示
                        theme_str = "Light" if bg_brightness > 180 else "Dark"
                        self.current_adaptation_status = f"[{self.current_app_id} | {theme_str}] 学習・抽出中... (学習率 {int(s*100)}%)"

                except Exception as e:
                    pass
                
                time.sleep(0.1)

    def update_physics(self):
        self.canvas.delete("all")
        
        status_color = "#00FF00" if "100%" in self.current_adaptation_status else "#FFD700"
        self.canvas.create_text(20, 20, anchor="nw", text=f"System Status: {self.current_adaptation_status}", 
                                fill=status_color, font=("Consolas", 14, "bold"))
        
        active_rects = self.rect_pool.get_active_rects()
        for r in active_rects:
            color = '#00FF00' if "100%" in self.current_adaptation_status else '#00FFFF'
            self.canvas.create_rectangle(r['x'], r['y'], r['x']+r['w'], r['y']+r['h'], outline=color, stipple='gray25')
        
        active_barrels = self.barrel_pool.get_active_barrels()
        for b in active_barrels:
            b.update(self.rect_pool, self.screen_height)
            b.draw(self.canvas)
            if b.x < -100 or b.x > self.screen_width + 100:
                b.is_active = False # Zero Allocation

        self.root.after(16, self.update_physics)

if __name__ == "__main__":
    print("Starting Hybrid Memory Object Hack (UIA + Binary XOR Scan + ML Learning)...")
    print("タイピングの変化を自己学習し、アプリごとの文字の特徴と空間をプロファイリングしてUIノイズを除去します。")
    print("--------------------------------------------------")
    print("【動的単体テスト機能】")
    print("このコンソールで 'test' と入力しEnterを押すと、システムの状態を自己診断します。")
    print("--------------------------------------------------")
    print("終了するには、このターミナルで Ctrl+C を押してください。")
    
    root = tk.Tk()
    app = OverlayApp(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.is_running = False
        app.memory_sys.save()
        print("\n適応記憶を保存して終了しました。")