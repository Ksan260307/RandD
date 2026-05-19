import os
import sys
import time
import math
import random
import threading
from typing import List, Tuple, Dict, Any, Optional

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import pyautogui
    # マウスを画面の四隅に押し当てると強制終了できるセーフティを有効化
    pyautogui.FAILSAFE = True
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

IS_WINDOWS = sys.platform.startswith('win')
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

def is_esc_pressed() -> bool:
    """Escキーが押されているかを判定します"""
    if IS_WINDOWS:
        # Windowsの直通API（VK_ESCAPE = 0x1B）を利用して非同期にキー状態を取得します
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)
    else:
        # Windows以外のOS向けにkeyboardライブラリの利用を試みます
        try:
            import keyboard
            return keyboard.is_pressed('esc')
        except ImportError:
            return False

class PreciseMath:
    """
    OSやCPUによる計算誤差を防ぐため、すべての数値を整数（固定小数点）に変換して
    ズレを完全に防ぐための精密計算クラスです。
    """
    SHIFT = 16
    ONE = 1 << SHIFT
    MASK = (1 << 32) - 1

    @classmethod
    def from_float(cls, val: float) -> int:
        """普通の小数をシステム用の精密整数に変換します"""
        return int(val * cls.ONE) & cls.MASK

    @classmethod
    def to_float(cls, val: int) -> float:
        """システム用の精密整数を普通の小数に戻します"""
        signed_val = val if val < (1 << 31) else val - (1 << 32)
        return signed_val / cls.ONE

    @classmethod
    def multiply(cls, a: int, b: int) -> int:
        """精密整数どうしの掛け算を行います"""
        sa = a if a < (1 << 31) else a - (1 << 32)
        sb = b if b < (1 << 31) else b - (1 << 32)
        return ((sa * sb) >> cls.SHIFT) & cls.MASK

    @classmethod
    def divide(cls, a: int, b: int) -> int:
        """精密整数どうしの安全な割り算を行います"""
        sa = a if a < (1 << 31) else a - (1 << 32)
        sb = b if b < (1 << 31) else b - (1 << 32)
        if sb == 0:
            return 0
        return ((sa << cls.SHIFT) // sb) & cls.MASK

class DelayedFormula:
    """
    複雑な条件分岐を事前に組み立てておき、
    後から一気に効率よく計算するための遅延数式クラスです。
    """
    def __init__(self, operation: str, arguments: List[Any]):
        self.operation = operation
        self.arguments = arguments

    def evaluate(self, variables_dict: Dict[str, Any]) -> Any:
        """組み立てた数式に現在の数値を流し込んで計算結果を返します"""
        resolved_args = []
        for arg in self.arguments:
            if isinstance(arg, DelayedFormula):
                resolved_args.append(arg.evaluate(variables_dict))
            elif isinstance(arg, str) and arg in variables_dict:
                resolved_args.append(variables_dict[arg])
            else:
                resolved_args.append(arg)

        if self.operation == 'add':
            return resolved_args[0] + resolved_args[1]
        elif self.operation == 'sub':
            return resolved_args[0] - resolved_args[1]
        elif self.operation == 'mul':
            return resolved_args[0] * resolved_args[1]
        elif self.operation == 'where':
            return resolved_args[1] if resolved_args[0] else resolved_args[2]
        elif self.operation == 'clamp':
            return max(resolved_args[1], min(resolved_args[2], resolved_args[0]))
        return 0

def formula_sub(a, b) -> DelayedFormula: return DelayedFormula('sub', [a, b])

class PackedDataStorage:
    """
    複数の状態情報を32bit整数の中にギチギチに詰め込んで保存する
    メモリ効率に特化したデータ保管庫です。
    """
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.state_buffer = [0] * capacity
        self.position_x = [0] * capacity
        self.position_y = [0] * capacity
        self.velocity_x = [0] * capacity
        self.velocity_y = [0] * capacity
        self.high_precision_pool = {}  # カオス度が高い個体のみ一時的に格納する高精度エリア

    def pack_to_32bit(self, val_A: int, val_B: int, val_C: int, 
                      delta_A: int, delta_B: int, delta_C: int, 
                      life_state: int, wear_and_tear: int) -> int:
        """複数の動作パラメータを1つの32bit値に合体させます"""
        packed_val = 0
        packed_val |= (val_A & 0x3)
        packed_val |= ((val_B & 0x3) << 2)
        packed_val |= ((val_C & 0x3) << 4)
        packed_val |= (((delta_A + 32) & 0x3F) << 6)
        packed_val |= (((delta_B + 32) & 0x3F) << 12)
        packed_val |= (((delta_C + 32) & 0x3F) << 18)
        packed_val |= ((life_state & 0x7) << 24)
        packed_val |= ((wear_and_tear & 0x7) << 27)
        return packed_val & 0xFFFFFFFF

    def unpack_from_32bit(self, packed_val: int) -> Dict[str, int]:
        """詰め込まれた32bitデータから元の個別数値に解体します"""
        return {
            "val_A": packed_val & 0x3,
            "val_B": (packed_val >> 2) & 0x3,
            "val_C": (packed_val >> 4) & 0x3,
            "delta_A": ((packed_val >> 6) & 0x3F) - 32,
            "delta_B": ((packed_val >> 12) & 0x3F) - 32,
            "delta_C": ((packed_val >> 18) & 0x3F) - 32,
            "life_state": (packed_val >> 24) & 0x7,
            "wear_and_tear": (packed_val >> 27) & 0x7
        }

    def upgrade_to_high_precision(self, index: int):
        """激しく動く特定の要素を高精度計算モード（64bit想定）に昇格させます"""
        data = self.unpack_from_32bit(self.state_buffer[index])
        if data["life_state"] != 2:
            data["life_state"] = 2
            self.high_precision_pool[index] = {
                "val_A": data["val_A"] << 6,
                "val_B": data["val_B"] << 6,
                "val_C": data["val_C"] << 6,
                "delta_A": data["delta_A"] << 10,
                "delta_B": data["delta_B"] << 10,
                "delta_C": data["delta_C"] << 10,
            }
            self.state_buffer[index] = self.pack_to_32bit(
                data["val_A"], data["val_B"], data["val_C"],
                data["delta_A"], data["delta_B"], data["delta_C"],
                2, data["wear_and_tear"]
            )

    def downgrade_to_standard(self, index: int):
        """動きが落ち着いた要素を通常の省メモリモードに降格させます"""
        if index in self.high_precision_pool:
            p_data = self.high_precision_pool[index]
            data = self.unpack_from_32bit(self.state_buffer[index])
            val_A = (p_data["val_A"] >> 6) & 0x3
            val_B = (p_data["val_B"] >> 6) & 0x3
            val_C = (p_data["val_C"] >> 6) & 0x3
            delta_A = (p_data["delta_A"] >> 10)
            delta_B = (p_data["delta_B"] >> 10)
            delta_C = (p_data["delta_C"] >> 10)
            self.state_buffer[index] = self.pack_to_32bit(val_A, val_B, val_C, delta_A, delta_B, delta_C, 1, data["wear_and_tear"])
            del self.high_precision_pool[index]

class BackgroundNoiseCollector(threading.Thread):
    """
    メインの描画処理を阻害しないよう、裏でこっそり動きながら
    時間経過などの極小のブレからリアルな不規則さ（エントロピー）を集めるクラスです。
    """
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.noise_pool = []
        self.lock = threading.Lock()
        self.is_running = True

    def run(self):
        while self.is_running:
            raw_val = int((time.perf_counter() * 1e6) % 256)
            with self.lock:
                self.noise_pool.append(raw_val)
                if len(self.noise_pool) > 100:
                    self.noise_pool.pop(0)
            time.sleep(0.05)

    def retrieve_noise(self) -> List[int]:
        """集まった不規則な数値をメイン処理に引き渡して、プールをリセットします"""
        with self.lock:
            collected = list(self.noise_pool)
            self.noise_pool.clear()
            return collected

class SystemSyncManager:
    """
    裏で集まったバラバラなノイズを、システム内で
    安全にシード値として決定・統合する管理ユニットです。
    """
    def __init__(self, collector: BackgroundNoiseCollector):
        self.collector = collector
        self.official_seed = 0xAB

    def update_official_seed(self):
        """現在のフレームで使用する公式なノイズシードを安全に更新します"""
        raw_noises = self.collector.retrieve_noise()
        if raw_noises:
            total_noise = sum(raw_noises) % 256
            self.official_seed = ((self.official_seed ^ total_noise) * 16777619) & 0xFFFFFFFF
        else:
            self.official_seed = ((self.official_seed ^ 0x55) * 16777619) & 0xFFFFFFFF

class PhysicsEngine:
    """
    「やる気（V）」「激しさ（I）」「疲れ（F）」の3大要素から、
    マウスを引っ張るリアルな物理速度や位置の変化を計算する心臓部です。
    """
    def __init__(self, storage: PackedDataStorage, sync_manager: SystemSyncManager):
        self.storage = storage
        self.sync_manager = sync_manager

    def update_physics(self, target_x: int, target_y: int):
        """登録されているすべての点の論理座標と内部パラメータをターゲットに向けて進めます"""
        current_seed = self.sync_manager.official_seed

        for i in range(self.storage.capacity):
            data = self.storage.unpack_from_32bit(self.storage.state_buffer[i])
            
            # 疲れが限界（7）に達した要素は、その場に留まり停止します
            if data["wear_and_tear"] >= 7:
                continue

            # ターゲットから遠い要素は休眠し、近づくと目を覚まします（実体化）
            if data["life_state"] == 0:
                distance = abs(self.storage.position_x[i] - target_x) + abs(self.storage.position_y[i] - target_y)
                if distance < PreciseMath.from_float(200.0):
                    data["life_state"] = 1
                    self.storage.state_buffer[i] = self.storage.pack_to_32bit(
                        1, 1, 1, 0, 0, 0, 1, data["wear_and_tear"]
                    )
                continue

            motivation_v = data["val_A"] + data["val_B"] + data["val_C"]
            roughness_i = abs(data["delta_A"]) + abs(data["delta_B"]) + abs(data["delta_C"])
            fatigue_f = data["wear_and_tear"]

            # 激しすぎる場合は動的に高精度モードへ昇格
            if roughness_i > 40 and data["life_state"] == 1:
                self.storage.upgrade_to_high_precision(i)
                data = self.storage.unpack_from_32bit(self.storage.state_buffer[i])

            diff_x = formula_sub(target_x, self.storage.position_x[i]).evaluate({})
            diff_y = formula_sub(target_y, self.storage.position_y[i]).evaluate({})

            # ノイズを風のような不規則な推進力に変換
            wind_x = PreciseMath.from_float(((current_seed & 0xFF) - 128) / 128.0 * 2.0)
            wind_y = PreciseMath.from_float((((current_seed >> 8) & 0xFF) - 128) / 128.0 * 2.0)

            # 推進力の適用
            acceleration_scale = PreciseMath.from_float(0.01 + motivation_v * 0.005)
            force_x = PreciseMath.multiply(diff_x, acceleration_scale) + wind_x
            force_y = PreciseMath.multiply(diff_y, acceleration_scale) + wind_y

            self.storage.velocity_x[i] = (self.storage.velocity_x[i] + force_x) & PreciseMath.MASK
            self.storage.velocity_y[i] = (self.storage.velocity_y[i] + force_y) & PreciseMath.MASK

            # 疲れの蓄積に応じた摩擦ブレーキ
            friction = PreciseMath.from_float(0.95 - fatigue_f * 0.05)
            self.storage.velocity_x[i] = PreciseMath.multiply(self.storage.velocity_x[i], friction)
            self.storage.velocity_y[i] = PreciseMath.multiply(self.storage.velocity_y[i], friction)

            # 位置の更新
            self.storage.position_x[i] = (self.storage.position_x[i] + self.storage.velocity_x[i]) & PreciseMath.MASK
            self.storage.position_y[i] = (self.storage.position_y[i] + self.storage.velocity_y[i]) & PreciseMath.MASK

            # 激しい動きによる疲れの蓄積
            if roughness_i > 50:
                if random.random() < 0.02:
                    data["wear_and_tear"] = min(7, data["wear_and_tear"] + 1)

            # パラメータの次の状態への遷移と再パッキング
            next_v_A = min(3, max(0, data["val_A"] + (1 if current_seed % 7 == 0 else -1 if current_seed % 7 == 1 else 0)))
            next_v_B = min(3, max(0, data["val_B"] + (1 if current_seed % 11 == 0 else -1 if current_seed % 11 == 1 else 0)))
            next_v_C = min(3, max(0, data["val_C"] + (1 if current_seed % 13 == 0 else -1 if current_seed % 13 == 1 else 0)))
            next_delta_A = int(data["delta_A"] * 0.9) + (current_seed % 5 - 2)
            next_delta_B = int(data["delta_B"] * 0.9) + ((current_seed >> 4) % 5 - 2)
            next_delta_C = int(data["delta_C"] * 0.9) + ((current_seed >> 8) % 5 - 2)

            self.storage.state_buffer[i] = self.storage.pack_to_32bit(
                next_v_A, next_v_B, next_v_C,
                next_delta_A, next_delta_B, next_delta_C,
                data["life_state"], data["wear_and_tear"]
            )

            # 動きが収まったら通常精度へ降格
            if roughness_i < 10 and data["life_state"] == 2:
                self.storage.downgrade_to_standard(i)

class FutureRoutePredictor:
    """
    今いる位置からターゲットまでのいくつかのルート候補を予測・シミュレーションし、
    最もスムーズで不自然さのない次の一歩を割り出すナビゲーターです。
    """
    def __init__(self, search_steps: int = 5, search_branches: int = 3):
        self.search_steps = search_steps
        self.search_branches = search_branches

    def predict_optimal_target(self, start_x: int, start_y: int, goal_x: int, goal_y: int, current_seed: int) -> Tuple[int, int]:
        """進行方向を視野内に限定しながら、不自然なジャンプを防ぐ最も良好な座標を予測します"""
        best_candidate_x, best_candidate_y = start_x, start_y
        lowest_penalty_score = float('inf')

        vector_x = goal_x - start_x
        vector_y = goal_y - start_y
        direct_distance = math.hypot(vector_x, vector_y)
        if direct_distance == 0:
            return start_x, start_y

        for branch_idx in range(self.search_branches):
            angle_offset = ((current_seed + branch_idx * 45) % 360) * (math.pi / 180.0)
            step_size = min(direct_distance, PreciseMath.from_float(15.0))

            pred_x = start_x + int(step_size * math.cos(angle_offset))
            pred_y = start_y + int(step_size * math.sin(angle_offset))

            # 目的地から大幅に外れる不自然なルートはペナルティを課して除外
            penalty = abs(pred_x - goal_x) + abs(pred_y - goal_y)
            if branch_idx == 1:
                penalty -= PreciseMath.from_float(5.0)

            if penalty < lowest_penalty_score:
                lowest_penalty_score = penalty
                best_candidate_x, best_candidate_y = pred_x, pred_y

        return best_candidate_x, best_candidate_y

class RealMouseController:
    """
    システム内の高精度論理空間から、OSの実ピクセル座標へと変換し、
    現実のマウスを実際に移動させるコントローラーです。
    """
    def __init__(self):
        self.screen_width = 1920
        self.screen_height = 1080
        self.detect_screen_resolution()

    def detect_screen_resolution(self):
        """現在のPC画面の解像度（幅・高さ）を取得します"""
        if HAS_PYAUTOGUI:
            w, h = pyautogui.size()
            self.screen_width = w
            self.screen_height = h
        elif IS_WINDOWS:
            user32 = ctypes.windll.user32
            self.screen_width = user32.GetSystemMetrics(0)
            self.screen_height = user32.GetSystemMetrics(1)

    def get_current_mouse_pos(self) -> Tuple[int, int]:
        """現在の実際のマウス位置を取得します"""
        if HAS_PYAUTOGUI:
            return pyautogui.position()
        elif IS_WINDOWS:
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            pt = POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            return pt.x, pt.y
        return self.screen_width // 2, self.screen_height // 2

    def move_mouse_to(self, x: int, y: int):
        """マウスカーソルを画面上の指定ピクセル座標へ移動します"""
        x = max(0, min(self.screen_width - 1, x))
        y = max(0, min(self.screen_height - 1, y))

        if HAS_PYAUTOGUI:
            pyautogui.moveTo(x, y, duration=0.0)
        elif IS_WINDOWS:
            ctypes.windll.user32.SetCursorPos(x, y)
        else:
            print(f"[Virtual Mouse View] Position: ({x}, {y})")

class SmoothMouseSystem:
    """
    各演算コンポーネントを安全に統合し、
    一連の滑らかな動的シミュレーションを実行する全体の調整システムです。
    """
    def __init__(self):
        self.noise_collector = BackgroundNoiseCollector()
        self.noise_collector.start()

        self.sync_manager = SystemSyncManager(self.noise_collector)
        self.sync_manager.update_official_seed()

        self.storage = PackedDataStorage(capacity=10)
        
        self.mouse_controller = RealMouseController()
        start_x, start_y = self.mouse_controller.get_current_mouse_pos()

        # マウス要素[0]の初期化
        self.storage.position_x[0] = PreciseMath.from_float(start_x)
        self.storage.position_y[0] = PreciseMath.from_float(start_y)
        self.storage.state_buffer[0] = self.storage.pack_to_32bit(
            val_A=2, val_B=2, val_C=2,
            delta_A=0, delta_B=0, delta_C=0,
            life_state=1,
            wear_and_tear=0
        )

        # 随伴要素[1-9]の初期化
        for i in range(1, 10):
            self.storage.position_x[i] = PreciseMath.from_float(start_x + random.randint(-50, 50))
            self.storage.position_y[i] = PreciseMath.from_float(start_y + random.randint(-50, 50))
            self.storage.state_buffer[i] = self.storage.pack_to_32bit(
                val_A=1, val_B=1, val_C=1,
                delta_A=0, delta_B=0, delta_C=0,
                life_state=0,
                wear_and_tear=0
            )

        self.physics_engine = PhysicsEngine(self.storage, self.sync_manager)
        self.route_predictor = FutureRoutePredictor()

    def run_simulation(self):
        """永続的に動作し、不規則シグナルに基づく滑らかな移動シミュレーションを繰り返します"""
        print("マウス自動化システムを起動しました（永続動作中）")
        print("[!] 停止方法: キーボードの [Esc] キーを押すか、コンソール上で [Ctrl + C] を入力してください。\n")

        screen_center_x = self.mouse_controller.screen_width // 2
        screen_center_y = self.mouse_controller.screen_height // 2
        current_angle = 0.0

        try:
            while True:
                # ユーザーがEscキーを押した瞬間にループを抜けて終了します
                if is_esc_pressed():
                    print("\nEscキーを検知しました。動きを停止します。")
                    break

                frame_start_time = time.perf_counter()

                self.sync_manager.update_official_seed()
                seed_val = self.sync_manager.official_seed

                # ターゲットの移動軌跡の計算
                radius = 150.0 + 100.0 * math.sin(current_angle * 1.5) + (seed_val % 50)
                current_angle += 0.03
                target_pixel_x = screen_center_x + int(radius * math.cos(current_angle))
                target_pixel_y = screen_center_y + int(radius * math.sin(current_angle))

                target_precise_x = PreciseMath.from_float(target_pixel_x)
                target_precise_y = PreciseMath.from_float(target_pixel_y)

                # 最適な次移動座標の予測と物理パラメータ適用
                current_pos_x = self.storage.position_x[0]
                current_pos_y = self.storage.position_y[0]
                next_precise_x, next_precise_y = self.route_predictor.predict_optimal_target(
                    current_pos_x, current_pos_y, target_precise_x, target_precise_y, seed_val
                )

                self.physics_engine.update_physics(next_precise_x, next_precise_y)

                output_pixel_x = int(PreciseMath.to_float(self.storage.position_x[0]))
                output_pixel_y = int(PreciseMath.to_float(self.storage.position_y[0]))

                self.mouse_controller.move_mouse_to(output_pixel_x, output_pixel_y)

                # コンソール表示を1行でシンプルに書き換えます
                if int(current_angle * 10) % 5 == 0:
                    current_state = self.storage.unpack_from_32bit(self.storage.state_buffer[0])
                    accuracy_mode = "High" if current_state['life_state'] == 2 else "Std"
                    sys.stdout.write(
                        f"\r動作中... 現在地: X:{output_pixel_x:4d}, Y:{output_pixel_y:4d} | "
                        f"疲労度: {current_state['wear_and_tear']}/7 | "
                        f"精度: {accuracy_mode} | [Esc]キーで終了"
                    )
                    sys.stdout.flush()

                # 約60FPSを維持するためのインターバル処理
                elapsed_time = time.perf_counter() - frame_start_time
                sleep_duration = max(0.005, 0.016 - elapsed_time)
                time.sleep(sleep_duration)

        except KeyboardInterrupt:
            print("\nキーボード割り込み（Ctrl+C）を検知しました。終了します。")
        except Exception as e:
            print(f"\nエラーが発生したため緊急停止しました: {e}")
        finally:
            self.noise_collector.is_running = False
            self.noise_collector.join()
            print("\nシステムを正常に終了し、制御権を返却しました。")

if __name__ == "__main__":
    mouse_system = SmoothMouseSystem()
    mouse_system.run_simulation()
