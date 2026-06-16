# 汎用メモリハック数理モデル - 八握剣異戒神将魔虚羅 Pixel-Perfect Terrain版
# 画面全域のエッジピクセルを直接物理的な地形として扱い、あらゆる形状に衝突させます。
# 学習した地形データは zlib で高圧縮され、JSONに永続化されます。
# 実行に必要なライブラリ: pip install mss numpy keyboard

import tkinter as tk
import ctypes
import math
import random
import queue
import threading
import time
import json
import os
import zlib
import base64

try:
    import mss
    import numpy as np
    HAS_MSS = True
except ImportError:
    HAS_MSS = False
    print("Error: mss, numpy がインストールされていません。")

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

# === フェーズ0: 魔虚羅 適応型メモリシステム ===
class MakoraMemory:
    def __init__(self, filepath="makora_memory.json"):
        self.filepath = filepath
        self.cache = {}
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                
                # 圧縮された地形データ（エッジマップ）の解凍と展開
                for k, v in loaded_data.items():
                    if "edge_map_b64" in v:
                        compressed = base64.b64decode(v["edge_map_b64"].encode('ascii'))
                        unpacked = np.unpackbits(np.frombuffer(zlib.decompress(compressed), dtype=np.uint8))
                        shape = tuple(v["shape"])
                        # 解凍して元の2D boolean配列に戻す
                        edge_map = unpacked[:shape[0]*shape[1]].reshape(shape).astype(bool)
                        self.cache[k] = {"strength": v["strength"], "edge_map": edge_map}
                    else:
                        self.cache[k] = {"strength": v["strength"], "edge_map": None}
                
                print(f"[Makora Memory] 過去の適応記憶をロードしました。記憶数: {len(self.cache)}")
            except Exception as e:
                print(f"メモリのロードに失敗しました: {e}")
        else:
            print("[Makora Memory] 新規メモリ領域を初期化しました。")

    def save(self):
        try:
            save_data = {}
            for k, v in self.cache.items():
                # 巨大な boolean 配列をビットパックして高圧縮(zlib)保存する
                if "edge_map" in v and v["edge_map"] is not None:
                    packed = np.packbits(v["edge_map"]).tobytes()
                    compressed = base64.b64encode(zlib.compress(packed)).decode('ascii')
                    shape = v["edge_map"].shape
                    save_data[k] = {"strength": v["strength"], "edge_map_b64": compressed, "shape": shape}
                else:
                    save_data[k] = {"strength": v["strength"]}
            
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f)
        except Exception as e:
            pass

    # 高速な疑似ハッシュ（画面のダウンサンプリングによるシグネチャ）
    @staticmethod
    def compute_fast_hash(packed_2d):
        h, w = packed_2d.shape
        samples = packed_2d[h//4:3*h//4:50, w//4:3*w//4:50].flatten()
        return str(hash(samples.tobytes()))

# === フェーズ1: ピクセルパーフェクト物理演算エンジン ===
class Barrel:
    def __init__(self, screen_width: float):
        self.radius = 12.0
        center_x = screen_width / 2.0 if screen_width > 0 else 400.0
        self.x = center_x + random.uniform(-200, 200)
        self.y = 10.0 + random.uniform(0, 20)
        self.vx = (1 if random.random() > 0.5 else -1) * (1.0 + random.uniform(0, 3.0))
        self.vy = 0.0
        self.rotation = 0.0
        self.bounce_factor = 0.4
        self.friction = 0.98

    def update(self, edge_map, screen_width, screen_height):
        self.vy += 0.5
        next_x = self.x + self.vx
        next_y = self.y + self.vy
        hit_floor = False

        # --- ピクセルパーフェクト地形衝突判定 ---
        if edge_map is not None:
            # 樽の周囲（バウンディングボックス）を計算
            min_x = int(max(0, next_x - self.radius))
            max_x = int(min(screen_width, next_x + self.radius))
            min_y = int(max(0, next_y - self.radius))
            max_y = int(min(screen_height, next_y + self.radius))
            
            if max_x > min_x and max_y > min_y:
                # エッジマップの該当領域だけを高速にスライス
                region = edge_map[min_y:max_y, min_x:max_x]
                
                if np.any(region):
                    hit_y, hit_x = np.where(region)
                    # 切り出した領域のローカル座標を画面のグローバル座標に変換
                    hit_y_global = hit_y + min_y
                    hit_x_global = hit_x + min_x
                    
                    # 樽の「円の範囲内」に食い込んでいるピクセルだけを抽出
                    dx_arr = hit_x_global - next_x
                    dy_arr = hit_y_global - next_y
                    distances = np.hypot(dx_arr, dy_arr)
                    valid_mask = distances <= self.radius
                    
                    if np.any(valid_mask):
                        # 衝突したピクセル群の「重心」を計算
                        cx = np.mean(hit_x_global[valid_mask])
                        cy = np.mean(hit_y_global[valid_mask])
                        
                        dx = cx - next_x
                        dy = cy - next_y
                        dist = math.hypot(dx, dy)
                        
                        if dist > 0:
                            # 押し出しの法線ベクトル（反発方向）
                            nx = dx / dist
                            ny = dy / dist
                            
                            # 食い込んだ分だけ位置を押し戻す
                            overlap = self.radius - dist
                            next_x -= nx * overlap
                            next_y -= ny * overlap
                            
                            # 速度の反射（ベクトルの反射公式）
                            v_dot_n = self.vx * nx + self.vy * ny
                            if v_dot_n > 0: # 面に向かっている場合のみ反射
                                self.vx -= (1 + self.bounce_factor) * v_dot_n * nx
                                self.vy -= (1 + self.bounce_factor) * v_dot_n * ny
                                
                            # 下からの反発が強い場合、床に着地したとみなす
                            if ny > 0.5:
                                hit_floor = True

        # 画面の一番下（絶対的な床）の処理
        if not hit_floor and next_y + self.radius > screen_height:
            next_y = screen_height - self.radius
            self.vy = -self.vy * self.bounce_factor
            if abs(self.vy) < 1.5: self.vy = 0
            hit_floor = True

        self.x = next_x
        self.y = next_y

        # 着地時の摩擦と転がり処理
        if hit_floor and abs(self.vy) < 1.0:
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


# === フェーズ2: デスクトップオーバーレイ ===
class OverlayApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PixelPerfectMemoryHack")
        
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
        self.current_edge_map = None # スレッド間で共有する地形マップ
        self.event_queue = queue.Queue()
        self.is_running = True
        
        self.memory_sys = MakoraMemory()
        self.current_adaptation_status = "画面全域走査中 (解析初期化)"

        if HAS_KEYBOARD:
            try: keyboard.on_press(self.on_key)
            except Exception as e: print(f"Key hook error: {e}")

        if HAS_MSS:
            self.vision_thread = threading.Thread(target=self.pixel_perfect_scan_loop, daemon=True)
            self.vision_thread.start()

        self.update_physics()
        self.check_events()
        self.auto_inject()
        
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
        while len(self.barrels) > 40: self.barrels.pop(0)

    # === 画像のブロック化を廃止し、ピクセルのエッジをそのまま地形にする ===
    def pixel_perfect_scan_loop(self):
        last_env_hash = None
        adaptation_threshold = 1.0

        with mss.mss() as sct:
            monitor = {"top": 0, "left": 0, "width": self.screen_width, "height": self.screen_height}
            
            while self.is_running:
                try:
                    raw_sct = sct.grab(monitor)
                    
                    # 1ピクセル(BGRA)を1つの32bit unsigned intとしてキャスト
                    packed_data = np.frombuffer(raw_sct.bgra, dtype=np.uint32)
                    packed_2d = packed_data.reshape((self.screen_height, self.screen_width))
                    
                    current_hash = self.memory_sys.compute_fast_hash(packed_2d)
                    if last_env_hash != current_hash:
                        last_env_hash = current_hash
                        if current_hash not in self.memory_sys.cache:
                            self.memory_sys.cache[current_hash] = {"strength": 0.0, "edge_map": None}
                            self.current_adaptation_status = "未知の画面全域を学習開始"
                        else:
                            self.current_adaptation_status = "既知の地形（記憶の呼び出し中）"

                    env_data = self.memory_sys.cache[current_hash]
                    
                    if env_data["strength"] >= adaptation_threshold:
                        self.current_edge_map = env_data["edge_map"]
                        self.current_adaptation_status = "完全適応済み (地形固定・コスト0)"
                        time.sleep(0.5)
                        continue

                    # 矩形(ブロック)処理を廃止。全ピクセルのXORを取り、地形マップを作る
                    shifted_right = np.roll(packed_2d, shift=1, axis=1)
                    shifted_down = np.roll(packed_2d, shift=1, axis=0)
                    
                    edge_mask_x = np.bitwise_xor(packed_2d, shifted_right)
                    edge_mask_y = np.bitwise_xor(packed_2d, shifted_down)
                    
                    # 画面全域の「色の境界線」がTrueになる boolean配列
                    edges = (edge_mask_x > 0) | (edge_mask_y > 0)

                    env_data["edge_map"] = edges
                    env_data["strength"] += 0.34 # 約3回で適応完了
                    self.current_edge_map = edges
                    
                    if env_data["strength"] >= adaptation_threshold:
                        print(f"全域走査完了。環境ハッシュ [{current_hash}] の地形化が完了。")
                    else:
                        self.current_adaptation_status = f"適応進行中 (地形生成... {int(env_data['strength']*100)}%)"

                except Exception as e:
                    print(f"Binary Scan error: {e}")
                
                time.sleep(0.3)

    def update_physics(self):
        self.canvas.delete("all")
        
        status_color = "#00FF00" if "完全適応" in self.current_adaptation_status else "#FFD700"
        self.canvas.create_text(20, 20, anchor="nw", text=f"System Status: {self.current_adaptation_status}", 
                                fill=status_color, font=("Consolas", 14, "bold"))
        
        # ※地形は全ピクセルに及ぶため、Tkinterで描画するとフリーズします。
        # 代わりに、見えない実際の地形に沿って樽が転がる視覚効果をお楽しみください。
        
        for b in self.barrels[:]:
            b.update(self.current_edge_map, self.screen_width, self.screen_height)
            b.draw(self.canvas)
            if b.x < -100 or b.x > self.screen_width + 100:
                self.barrels.remove(b)

        self.root.after(16, self.update_physics)

if __name__ == "__main__":
    print("Starting Pixel-Perfect Terrain Memory Hack...")
    print("画面上のありとあらゆる形（文字、アイコン、イラストの境界線）が物理的な地形になります。")
    print("終了するには、このターミナルで Ctrl+C を押してください。")
    
    root = tk.Tk()
    app = OverlayApp(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.is_running = False
        app.memory_sys.save()
        print("\n適応記憶を保存して終了しました。")