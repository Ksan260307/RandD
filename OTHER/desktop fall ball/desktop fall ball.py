# 汎用メモリハック数理モデル - 八握剣異戒神将魔虚羅 適応型オーバーレイ (Makora-Adaptive Vision版)
# 画面状態を学習し、完全に適応した画面では重い画像処理をスキップしてコストをゼロ化します。
# 実行に必要なライブラリ: pip install mss opencv-python numpy keyboard

import tkinter as tk
import ctypes
import math
import random
import queue
import threading
import time
import json
import os

try:
    import mss
    import cv2
    import numpy as np
    HAS_CV = True
except ImportError:
    HAS_CV = False
    print("Error: mss, cv2, numpy がインストールされていません。")

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False
    print("Warning: 'keyboard' library not found.")

# 高DPI環境での画面サイズのズレを補正
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


# === フェーズ0: 魔虚羅 適応型メモリシステム (Adaptive Vision Memory) ===
# 論文における「適応型RAGメモリ（ARM）」と「忘却と定着の数理」を実装
class MakoraMemory:
    def __init__(self, filepath="makora_memory.json"):
        self.filepath = filepath
        self.cache = {}
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
                print(f"[Makora Memory] 過去の適応記憶をロードしました。記憶数: {len(self.cache)}")
            except Exception as e:
                print(f"メモリのロードに失敗しました: {e}")
        else:
            print("[Makora Memory] 新規メモリ領域を初期化しました。")

    def save(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f)
        except Exception as e:
            print(f"メモリの保存に失敗しました: {e}")

    # Average Hash (aHash) による画面の環境シグネチャの計算
    @staticmethod
    def compute_ahash(gray_img):
        resized = cv2.resize(gray_img, (8, 8))
        mean_val = np.mean(resized)
        hash_val = 0
        for idx, val in enumerate(resized.flatten()):
            if val > mean_val:
                hash_val |= (1 << idx)
        return str(hash_val)

    # 中華料理店過程（CRP）的アプローチ: 未知の環境か既存の環境かをハミング距離で判定
    @staticmethod
    def hamming_distance(h1_str, h2_str):
        h1, h2 = int(h1_str), int(h2_str)
        return bin(h1 ^ h2).count('1')


# === フェーズ1: 物理演算エンジン ===
class Barrel:
    def __init__(self, screen_width: float):
        self.radius = 12.0
        center_x = screen_width / 2.0 if screen_width > 0 else 400.0
        self.x = center_x + random.uniform(-150, 150)
        self.y = 10.0 + random.uniform(0, 20)
        self.vx = (1 if random.random() > 0.5 else -1) * (1.0 + random.uniform(0, 3.0))
        self.vy = 0.0
        self.rotation = 0.0
        self.bounce_factor = 0.4
        self.friction = 0.98

    def update(self, rects: list, screen_height: float):
        self.vy += 0.5
        next_x = self.x + self.vx
        next_y = self.y + self.vy
        hit_floor = False

        for r in rects:
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

        if hit_floor and self.vy == 0:
            self.vx *= self.friction
            if abs(self.vx) < 0.5:
                self.vx = 2.0 if random.random() > 0.5 else -2.0

        self.rotation += self.vx * 0.1

    def draw(self, canvas: tk.Canvas):
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


# === フェーズ2: デスクトップオーバーレイと Makora-Adaptive Workflow ===
class OverlayApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MakoraAdaptiveMemoryHack")
        
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

        self.barrels = []
        self.text_rects = []
        self.event_queue = queue.Queue()
        self.is_running = True
        
        # 記憶管理システムの初期化
        self.memory_sys = MakoraMemory()
        self.current_adaptation_status = "検索中 (解析初期化)"

        if HAS_KEYBOARD:
            try: keyboard.on_press(self.on_key)
            except Exception as e: print(f"Key hook error: {e}")

        if HAS_CV:
            self.vision_thread = threading.Thread(target=self.makora_adaptive_vision_loop, daemon=True)
            self.vision_thread.start()

        self.update_physics()
        self.check_events()
        self.auto_inject()
        
        # 30秒に1回、メモリをファイルに永続化保存
        self.save_memory_loop()

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
        for _ in range(count): self.barrels.append(Barrel(self.screen_width))
        while len(self.barrels) > 60: self.barrels.pop(0)

    # === 画像処理エンジン（魔虚羅の適応アルゴリズム完全実装） ===
    def makora_adaptive_vision_loop(self):
        background_accumulator = None
        learning_rate = 0.3
        
        last_env_hash = None
        adaptation_threshold = 1.0  # 完全適応（固定化）に必要な強度

        with mss.mss() as sct:
            monitor = {"top": 0, "left": 0, "width": self.screen_width, "height": self.screen_height}
            while self.is_running:
                try:
                    img = np.array(sct.grab(monitor))
                    gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                    
                    # 1. 環境シグネチャの取得と被弾検知
                    current_hash = self.memory_sys.compute_ahash(gray)
                    
                    # 画面が動いた（環境変化/ドメインシフト）かの判定
                    is_environment_changed = True
                    if last_env_hash is not None:
                        dist = self.memory_sys.hamming_distance(current_hash, last_env_hash)
                        if dist <= 2:  # わずかなピクセル変化は同じ環境とみなす
                            is_environment_changed = False
                            current_hash = last_env_hash # 安定化のためハッシュを維持
                    
                    if is_environment_changed:
                        # 画面が動いた場合、学習をリセット（法陣の回転開始）
                        background_accumulator = None
                        last_env_hash = current_hash
                        if current_hash not in self.memory_sys.cache:
                            self.memory_sys.cache[current_hash] = {"strength": 0.0, "rects": []}
                            self.current_adaptation_status = "未知の事象（学習開始）"
                        else:
                            self.current_adaptation_status = "既知の事象（記憶の呼び出し中）"

                    # 2. 完全適応の確認 (Check Full Adaptation) - コストゼロ化プロセス
                    env_data = self.memory_sys.cache[current_hash]
                    
                    if env_data["strength"] >= adaptation_threshold:
                        # 【適応完了・無効化】重い画像処理を完全にスキップし、判定を固定
                        self.text_rects = env_data["rects"]
                        self.current_adaptation_status = "完全適応済み (画像処理バイパス・コスト0)"
                        time.sleep(0.5)
                        continue

                    # 3. 継続的学習と定着 (法陣の回転)
                    # 画面が静止している間、移動平均を用いて安定したテキストブロックを抽出する
                    if background_accumulator is None:
                        background_accumulator = np.float32(gray)
                    else:
                        cv2.accumulateWeighted(gray, background_accumulator, learning_rate)
                    
                    learned_background = cv2.convertScaleAbs(background_accumulator)
                    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
                    enhanced_gray = clahe.apply(learned_background)
                    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                    grad = cv2.morphologyEx(enhanced_gray, cv2.MORPH_GRADIENT, kernel)
                    _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 4))
                    connected = cv2.dilate(bw, kernel_dilate, iterations=1)
                    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    
                    new_rects = []
                    for c in contours:
                        x, y, w, h = cv2.boundingRect(c)
                        aspect_ratio = float(w) / h if h > 0 else 0
                        if 10 < h < 100 and w > 15 and aspect_ratio > 0.8:
                            new_rects.append({'x': x, 'y': y, 'w': w, 'h': h})
                    
                    # 学習結果をメモリに反映し、適応度（強度）を上昇させる
                    env_data["rects"] = new_rects
                    env_data["strength"] += 0.25 # 約4回の反復（約2秒）で完全適応に達する
                    self.text_rects = new_rects
                    
                    if env_data["strength"] >= adaptation_threshold:
                        print(f"法陣が回転しました。環境ハッシュ [{current_hash}] への適応が完了。以後の計算コストを無効化します。")
                    else:
                        self.current_adaptation_status = f"適応進行中 (法陣の回転... {int(env_data['strength']*100)}%)"

                except Exception as e:
                    print(f"Vision loop error: {e}")
                
                time.sleep(0.5)

    def update_physics(self):
        self.canvas.delete("all")
        
        # 状態表示用テキスト (左上にシステムの適応状態を表示)
        status_color = "#00FF00" if "完全適応" in self.current_adaptation_status else "#FFD700"
        self.canvas.create_text(20, 20, anchor="nw", text=f"System Status: {self.current_adaptation_status}", 
                                fill=status_color, font=("Consolas", 14, "bold"))
        
        for r in self.text_rects:
            color = '#00FF00' if "完全適応" in self.current_adaptation_status else '#FFA500'
            self.canvas.create_rectangle(r['x'], r['y'], r['x']+r['w'], r['y']+r['h'], outline=color, stipple='gray25')
        
        for b in self.barrels[:]:
            b.update(self.text_rects, self.screen_height)
            b.draw(self.canvas)
            if b.x < -100 or b.x > self.screen_width + 100:
                self.barrels.remove(b)

        self.root.after(16, self.update_physics)

if __name__ == "__main__":
    print("Starting Makora-Adaptive Vision Hack (適応型学習モデル)...")
    print("---------------------------------------------------------")
    print("【特性】")
    print("1. 画面が静止すると学習（法陣の回転）が進行します。")
    print("2. 学習が完了（完全適応）すると、画像処理を完全に停止して判定を固定化し、PCの負荷をゼロにします。")
    print("3. 画面が動く（スクロール等）と検知し、再度新しい画面の学習を開始します。")
    print("4. 学習した画面情報は makora_memory.json に保存され、次回起動時に再利用されます。")
    print("---------------------------------------------------------")
    print("終了するには、このターミナルで Ctrl+C を押してください。")
    
    root = tk.Tk()
    app = OverlayApp(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.is_running = False
        app.memory_sys.save() # 終了時に確実に記憶を保存
        print("\n適応記憶を保存して終了しました。")