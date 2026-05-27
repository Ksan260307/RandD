import numpy as np
import math
import time

# --- 固定小数点アーキテクチャ設定 (16.16フォーマット) ---
# 浮動小数点の誤差を排除し、完全決定論的な計算を保証するための設定
FIXED_FRAC_BITS = 16
FIXED_ONE = 1 << FIXED_FRAC_BITS

# NumPyの配列に対して整数のみの平方根計算を行うためのベクトル化関数
@np.vectorize
def int_sqrt(n):
    return math.isqrt(max(0, n))

class ComputeGraph:
    """計算グラフビルダー（遅延評価エンジン）
    直接計算を実行せず、操作をキューに溜めて後から一括評価する仕組みです。
    """
    def __init__(self):
        self.operations = []
        
    def add_op(self, op_func, *args):
        self.operations.append((op_func, args))
        
    def execute(self):
        # 登録された演算を順次実行（全て固定小数点・整数演算として処理）
        for op_func, args in self.operations:
            op_func(*args)
        self.operations.clear()

class MemoryPool:
    """状態管理バッファ（SoA構造と32bitビットパッキング）
    キャッシュ効率を最大化するため、状態と物理座標を分離して管理します。
    """
    def __init__(self, capacity):
        self.capacity = capacity
        # 32bit状態パック: [0-7: 予備, 8-15: 観測状態フラグ, 16-23: 更新頻度, 24-31: 活性フラグ]
        self.states = np.zeros(capacity, dtype=np.uint32)
        
        # 物理バッファ (浮動小数点を排除した固定小数点 16.16 フォーマット)
        self.velocity = np.zeros(capacity, dtype=np.int64)      # 速度 (光速cに対する割合)
        self.position = np.zeros(capacity, dtype=np.int64)      # 位置
        self.proper_time = np.zeros(capacity, dtype=np.int64)   # 固有時（宇宙船内の時計）
        
    def set_entity(self, idx, v_frac, is_active=True, is_observed=True):
        """エンティティ（宇宙船など）の初期化"""
        # 速度設定 (0.0 ~ 1.0の割合を固定小数点で保存)
        self.velocity[idx] = int(v_frac * FIXED_ONE)
        
        # 状態のビットパッキング
        active_bit = 1 if is_active else 0
        observed_bit = 1 if is_observed else 0
        update_freq = 1 # 基本更新頻度
        
        packed = (active_bit << 24) | (update_freq << 16) | (observed_bit << 8)
        self.states[idx] = packed

class RelativitySimulator:
    """メインシミュレーションエンジン"""
    def __init__(self, entity_count):
        self.pool = MemoryPool(entity_count)
        self.graph = ComputeGraph()
        self.system_time = 0 # 外部の絶対時間（固定小数点）
        
        # 環境ノイズ同期（外部エントロピーの決定論的注入）
        self.rng = np.random.Generator(np.random.PCG64(42))
        
    def setup_entities(self):
        # 0: 地球（静止）
        self.pool.set_entity(0, 0.0)
        # 1: 光速の50%で移動する宇宙船 (時間の遅れは約15%)
        self.pool.set_entity(1, 0.5)
        # 2: 光速の86.6%で移動する宇宙船 (時間の遅れは約50%)
        self.pool.set_entity(2, 0.866)
        # 3: 光速の99%で移動する宇宙船 (時間の遅れは約86%)
        self.pool.set_entity(3, 0.99)
        # 4: 観測範囲外の宇宙船（計算をスキップし、確率雲として扱う）
        self.pool.set_entity(4, 0.5, is_observed=False)

    def _op_calculate_relativity(self, dt_fixed):
        """相対性理論の計算ノード（固定小数点エミュレーション）"""
        # 1. 状態のアンパッキングと可視範囲フィルタリング
        is_active = (self.pool.states >> 24) & 1
        is_observed = (self.pool.states >> 8) & 1
        
        # 観測されているアクティブな対象のみを計算対象とする（描画外は計算を間引く）
        mask = (is_active == 1) & (is_observed == 1)
        active_indices = np.where(mask)[0]
        
        if len(active_indices) == 0:
            return

        v = self.pool.velocity[active_indices]
        
        # 2. ローレンツ収縮・時間の遅れの計算 (dt_proper = dt * sqrt(1 - (v/c)^2))
        # 固定小数点上での (1 - (v/c)^2) のエミュレート
        c_sq = FIXED_ONE * FIXED_ONE
        v_sq = v * v
        diff = c_sq - v_sq
        
        # 整数のみでの平方根計算（完全決定論的）
        sqrt_diff = int_sqrt(diff).astype(np.int64)
        
        # 固定小数点の乗算: (dt * sqrt_diff) / 1.0
        dt_proper = (dt_fixed * sqrt_diff) >> FIXED_FRAC_BITS
        
        # 3. 動的更新スケジュールと環境ノイズの適用
        # 速度が極端に高い（カオスな）状態の個体に対し、決定論的ノイズをわずかに注入する
        noise = self.rng.integers(-5, 6, size=len(active_indices))
        dt_proper += noise
        
        # 4. バッファの更新
        self.pool.position[active_indices] += (v * dt_fixed) >> FIXED_FRAC_BITS
        self.pool.proper_time[active_indices] += dt_proper

    def step(self, dt_seconds):
        """1フレームの進行"""
        dt_fixed = int(dt_seconds * FIXED_ONE)
        self.system_time += dt_fixed
        
        # 処理を計算グラフに登録
        self.graph.add_op(self._op_calculate_relativity, dt_fixed)
        
        # グラフの評価（まとめて演算を実行）
        self.graph.execute()

    def print_logs(self):
        """コンソールへのシンプルログ出力"""
        sys_time_sec = self.system_time / FIXED_ONE
        print(f"=== 基準時間 (地球上の時計): {sys_time_sec:.1f} 年 ===")
        
        for i in range(self.pool.capacity):
            state = self.pool.states[i]
            is_active = (state >> 24) & 1
            is_observed = (state >> 8) & 1
            
            if not is_active:
                continue
                
            if is_observed:
                v_ratio = self.pool.velocity[i] / FIXED_ONE
                pos = self.pool.position[i] / FIXED_ONE
                proper_t = self.pool.proper_time[i] / FIXED_ONE
                
                # 基準時間との差分（遅れた時間）を計算
                time_dilation = sys_time_sec - proper_t
                
                print(f" 宇宙船 {i} [v = {v_ratio:.3f}c] | 進行距離: {pos:.2f} 光年 | "
                      f"船内時計: {proper_t:.2f} 年 (遅れ: {time_dilation:.2f} 年)")
            else:
                # 観測されていないエンティティは計算がスキップされ、マクロな確率として扱われる
                print(f" 宇宙船 {i} [観測範囲外] -> 確率雲に圧縮中。計算をスキップしました。")
        print("-" * 65)

# --- 実行プロセス ---
if __name__ == "__main__":
    print("相対性理論シミュレータ (完全決定論的エミュレータ) を起動します...\n")
    
    sim = RelativitySimulator(entity_count=5)
    sim.setup_entities()
    
    # 1年ごとの経過を5回ループしてログ出力
    for step in range(1, 6):
        sim.step(dt_seconds=1.0)
        sim.print_logs()
        time.sleep(0.5) # 視認性のためのディレイ