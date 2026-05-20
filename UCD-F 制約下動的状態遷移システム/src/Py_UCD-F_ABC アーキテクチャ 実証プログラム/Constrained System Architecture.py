import numpy as np
import multiprocessing as mp
import time
import math
from typing import List, Dict, Tuple, Any

class ComputeGraphNode:
    """
    遅延評価グラフの基底クラス。
    ユーザーが定義するロジックを直接実行するのではなく、実行パスの分岐を排除した
    ハードウェア向け演算グラフにコンパイルするためのノード構造。
    """
    def __init__(self, op_type: str, *args):
        self.op_type = op_type
        self.inputs = args

    def __add__(self, other):
        return ComputeGraphNode("add", self, other)

    def __mul__(self, other):
        return ComputeGraphNode("mul", self, other)

    def __gt__(self, other):
        return ComputeGraphNode("greater", self, other)

def execute_graph_mock(node: ComputeGraphNode, env_vars: Dict[str, np.ndarray]) -> np.ndarray:
    """
    フォールバック環境用のグラフ評価関数。
    実際はコンパイラがハードウェア向けのシェーダー言語に変換するが、
    ここではCPU上でNumpyを用いてエミュレートする。
    """
    if isinstance(node, (int, float)):
        return node
    if isinstance(node, str):
        return env_vars[node]
    
    # 演算ノードの再帰的評価
    evaluated_inputs = [execute_graph_mock(inp, env_vars) for inp in node.inputs]
    
    if node.op_type == "add":
        return evaluated_inputs[0] + evaluated_inputs[1]
    elif node.op_type == "mul":
        return evaluated_inputs[0] * evaluated_inputs[1]
    elif node.op_type == "greater":
        return (evaluated_inputs[0] > evaluated_inputs[1]).astype(np.int32)
    return 0

class BitwiseMath:
    """
    状態を32bit整数にパック/アンパックするためのユーティリティおよび、
    浮動小数点に依存しない決定論的な固定小数点(16.16)演算を提供する。
    """
    FIXED_SCALE = 65536.0

    @staticmethod
    def to_fixed_16_16(val: float) -> np.int32:
        return np.int32(val * BitwiseMath.FIXED_SCALE)

    @staticmethod
    def from_fixed_16_16(val: np.int32) -> float:
        return val / BitwiseMath.FIXED_SCALE

    @staticmethod
    def pack_state(rx: int, ry: int, rz: int, 
                   px: int, py: int, pz: int, 
                   flag: int, wear: int) -> np.uint32:
        """
        複数の状態変数を1つの32bit空間に密にパッキングする。
        rx, ry, rz: 各2bit (0-3)
        px, py, pz: 各6bit (符号付き、-32~31 -> オフセット加算で0~63)
        flag: 3bit (0-7)
        wear: 3bit (0-7)
        """
        px_off = (px + 32) & 0x3F
        py_off = (py + 32) & 0x3F
        pz_off = (pz + 32) & 0x3F
        
        val = (rx & 0x3) | ((ry & 0x3) << 2) | ((rz & 0x3) << 4)
        val |= (px_off << 6) | (py_off << 12) | (pz_off << 18)
        val |= ((flag & 0x7) << 24)
        val |= ((wear & 0x7) << 27)
        return np.uint32(val)

    @staticmethod
    def unpack_state_vectorized(state_array: np.ndarray) -> Tuple[np.ndarray, ...]:
        """
        Numpyのベクトル演算を用いて一括でアンパックする。
        """
        rx = state_array & 0x3
        ry = (state_array >> 2) & 0x3
        rz = (state_array >> 4) & 0x3
        px = ((state_array >> 6) & 0x3F).astype(np.int32) - 32
        py = ((state_array >> 12) & 0x3F).astype(np.int32) - 32
        pz = ((state_array >> 18) & 0x3F).astype(np.int32) - 32
        flag = (state_array >> 24) & 0x7
        wear = (state_array >> 27) & 0x7
        return rx, ry, rz, px, py, pz, flag, wear

class ParallelMemoryBuffer:
    """
    エンティティのデータを属性ごとに独立した配列として管理し、
    キャッシュ効率を極大化するメモリ構造。
    """
    def __init__(self, capacity: int):
        self.capacity = capacity
        # 32bitパックされた状態
        self.states = np.zeros(capacity, dtype=np.uint32)
        # 固定小数点16.16による物理座標
        self.pos_x = np.zeros(capacity, dtype=np.int32)
        self.pos_y = np.zeros(capacity, dtype=np.int32)
        self.pos_z = np.zeros(capacity, dtype=np.int32)
        
        # 空間密度超過により確率的な集合体へ移行したパラメータ
        self.macro_clusters: Dict[int, Dict[str, float]] = {}
        # 高精度への動的プロモーションプール
        self.high_precision_pool: Dict[int, Dict[str, Any]] = {}
        
        # 状態フラグ定数
        self.FLAG_INACTIVE = 0
        self.FLAG_ACTIVE = 1
        self.FLAG_PROMOTED = 2
        self.FLAG_FROZEN = 3
        self.FLAG_AGGREGATED = 4

    def initialize_random(self):
        """初期状態のランダム配置"""
        for i in range(self.capacity):
            rx, ry, rz = np.random.randint(0, 4, 3)
            px, py, pz = np.random.randint(-10, 11, 3)
            # 初期は全て非アクティブ(観測外)とする
            self.states[i] = BitwiseMath.pack_state(rx, ry, rz, px, py, pz, self.FLAG_INACTIVE, 0)
            self.pos_x[i] = BitwiseMath.to_fixed_16_16(np.random.uniform(-100, 100))
            self.pos_y[i] = BitwiseMath.to_fixed_16_16(np.random.uniform(-100, 100))
            self.pos_z[i] = BitwiseMath.to_fixed_16_16(np.random.uniform(-100, 100))

def calculate_spatial_hash(px: np.ndarray, py: np.ndarray, pz: np.ndarray, cell_size: float) -> np.ndarray:
    """
    固定小数点座標から、空間グリッドごとのハッシュキー（モートンコード等に相当）を算出する。
    """
    grid_x = (px / (cell_size * BitwiseMath.FIXED_SCALE)).astype(np.int32)
    grid_y = (py / (cell_size * BitwiseMath.FIXED_SCALE)).astype(np.int32)
    grid_z = (pz / (cell_size * BitwiseMath.FIXED_SCALE)).astype(np.int32)
    
    # 簡易的なハッシュ関数
    h1 = 73856093
    h2 = 19349663
    h3 = 83492791
    return (grid_x * h1) ^ (grid_y * h2) ^ (grid_z * h3)

def apply_density_aggregation(memory: ParallelMemoryBuffer, max_density: int):
    """
    同一グリッド内の要素数が閾値を超えた場合、超過した要素を
    マクロな確率的集合体へ移行させ、演算負荷とメモリ破綻を防ぐ。
    """
    rx, ry, rz, px, py, pz, flags, wear = BitwiseMath.unpack_state_vectorized(memory.states)
    
    # アクティブな要素のみを対象
    active_mask = (flags == memory.FLAG_ACTIVE)
    if not np.any(active_mask):
        return

    hashes = calculate_spatial_hash(memory.pos_x, memory.pos_y, memory.pos_z, 10.0)
    active_hashes = hashes[active_mask]
    
    # グリッドごとのカウント
    unique_hashes, counts = np.unique(active_hashes, return_counts=True)
    overcrowded_hashes = unique_hashes[counts > max_density]

    for h in overcrowded_hashes:
        indices = np.where((hashes == h) & active_mask)[0]
        # 超過分を選択（ここでは簡易的に後半をカット）
        excess_indices = indices[max_density:]
        
        for idx in excess_indices:
            # 状態を更新して再パック
            memory.states[idx] = BitwiseMath.pack_state(
                rx[idx], ry[idx], rz[idx],
                px[idx], py[idx], pz[idx],
                memory.FLAG_AGGREGATED, wear[idx]
            )
        
        # 集合体としてのパラメータを加算
        if h not in memory.macro_clusters:
            memory.macro_clusters[h] = {"density": 0, "energy": 0.0}
        memory.macro_clusters[h]["density"] += len(excess_indices)
        memory.macro_clusters[h]["energy"] += np.sum(np.abs(px[excess_indices])) * 0.1

def update_viewport_activation(memory: ParallelMemoryBuffer, view_center: Tuple[float, float, float], radius: float):
    """
    描画・観測領域内に入った非アクティブ要素をアクティブへ即時フリップさせる。
    """
    vx, vy, vz = view_center
    rad_fixed = BitwiseMath.to_fixed_16_16(radius)
    vx_fixed = BitwiseMath.to_fixed_16_16(vx)
    vy_fixed = BitwiseMath.to_fixed_16_16(vy)
    vz_fixed = BitwiseMath.to_fixed_16_16(vz)

    dist_sq = (memory.pos_x - vx_fixed)**2 + (memory.pos_y - vy_fixed)**2 + (memory.pos_z - vz_fixed)**2
    rad_sq = rad_fixed**2

    # 観測圏内で非アクティブなものを抽出
    rx, ry, rz, px, py, pz, flags, wear = BitwiseMath.unpack_state_vectorized(memory.states)
    to_activate = (dist_sq < rad_sq) & (flags == memory.FLAG_INACTIVE)
    
    if np.any(to_activate):
        flags[to_activate] = memory.FLAG_ACTIVE
        # 更新して書き戻し
        for i in np.where(to_activate)[0]:
            memory.states[i] = BitwiseMath.pack_state(rx[i], ry[i], rz[i], px[i], py[i], pz[i], flags[i], wear[i])

def generate_active_indices(memory: ParallelMemoryBuffer, frame_count: int) -> np.ndarray:
    """
    変動量（Power）に応じて要素ごとの更新頻度を変え、
    次フレームで計算すべき要素の密なリストを生成する。
    """
    rx, ry, rz, px, py, pz, flags, wear = BitwiseMath.unpack_state_vectorized(memory.states)
    
    power_magnitude = np.abs(px) + np.abs(py) + np.abs(pz)
    
    # 変動量が大きいほど更新頻度が高い（インターバルが短い）
    update_interval = np.ones_like(power_magnitude)
    update_interval[power_magnitude < 10] = 2
    update_interval[power_magnitude < 5] = 4
    
    # フラグがアクティブ、かつ現在フレームが更新タイミングに合致するもの
    is_active = (flags == memory.FLAG_ACTIVE)
    is_time_to_update = (frame_count % update_interval) == 0
    
    valid_mask = is_active & is_time_to_update
    return np.where(valid_mask)[0]

def sensor_daemon_process(shared_noise: mp.Value, running_flag: mp.Value):
    """
    メインシミュレーションを阻害しないよう、別プロセスで
    システム負荷や外部環境のノイズを収穫するワーカー。
    """
    import random
    while running_flag.value == 1:
        # ランダムウォークによる環境ノイズのシミュレーション
        current = shared_noise.value
        shared_noise.value = max(0.0, min(1.0, current + random.uniform(-0.05, 0.05)))
        time.sleep(0.1)

class DecentralizedSyncMock:
    """
    決定論的ロックステップにおける、他ノードとの入力履歴および
    収穫ノイズの合意形成を行う層のモック。
    """
    def __init__(self):
        self.agreed_noise = 0.5

    def synchronize_and_authorize(self, local_noise: float) -> float:
        # ネットワーク全体で単一の真実として権威化する処理の模倣
        self.agreed_noise = self.agreed_noise * 0.9 + local_noise * 0.1
        return self.agreed_noise

class LocalPathPredictor:
    """
    特定座標周辺の未来状態を限定的に探索し、
    破壊的パラメータ（Wear）を最小化する最適入力を探すモジュール。
    """
    def __init__(self, depth: int, max_trials: int):
        self.depth = depth
        self.max_trials = max_trials

    def find_optimal_action(self, memory: ParallelMemoryBuffer, epicenter: Tuple[int, int, int], radius: int) -> np.ndarray:
        # 本来は影響範囲内の要素だけを抽出し、木探索を行う。
        # ここではモックとして、ランダムな入力を返す。
        return np.array([0, 1, 0], dtype=np.int32)

class SystemOrchestrator:
    """
    全てのサブシステムを統合し、決定論的な計算ステップを実行する。
    """
    def __init__(self, capacity: int):
        self.memory = ParallelMemoryBuffer(capacity)
        self.memory.initialize_random()
        self.sync_layer = DecentralizedSyncMock()
        self.predictor = LocalPathPredictor(depth=3, max_trials=10)
        
        # デーモンのセットアップ
        self.running_flag = mp.Value('i', 1)
        self.shared_noise = mp.Value('d', 0.5)
        self.daemon = mp.Process(target=sensor_daemon_process, args=(self.shared_noise, self.running_flag))
        self.daemon.start()
        
        self.frame_count = 0

    def step(self):
        # 1. 現実エントロピーの取得と権威化
        local_noise = self.shared_noise.value
        authorized_noise = self.sync_layer.synchronize_and_authorize(local_noise)

        # 2. 観測者効果による非アクティブ状態の崩壊（実体化）
        # 仮の視点座標
        view_center = (math.sin(self.frame_count*0.1)*50, 0, 0)
        update_viewport_activation(self.memory, view_center, radius=30.0)

        # 3. 密度限界判定と集合体への移行
        apply_density_aggregation(self.memory, max_density=5)

        # 4. 動的頻度に基づくアクティブリポジトリの抽出
        active_indices = generate_active_indices(self.memory, self.frame_count)

        # 5. 状態遷移計算（固定小数点・ベクトル演算）
        if len(active_indices) > 0:
            rx, ry, rz, px, py, pz, flags, wear = BitwiseMath.unpack_state_vectorized(self.memory.states[active_indices])
            
            # ノイズをトリガーとした変動の減衰と力学適用
            px = np.clip(px + int((authorized_noise - 0.5) * 4), -32, 31)
            py = np.clip(py - 1, -32, 31) # 擬似的な重力方向への変動
            
            # 物理座標への適用（固定小数点）
            self.memory.pos_x[active_indices] += px * 100 
            self.memory.pos_y[active_indices] += py * 100
            self.memory.pos_z[active_indices] += pz * 100

            # 疲労（Wear）の蓄積と完全凍結判定
            wear_increase_condition = (np.abs(px) > 20) | (np.abs(py) > 20)
            wear = np.where(wear_increase_condition, np.minimum(wear + 1, 7), wear)
            
            # 最大限界に達した個体は凍結し、以後の演算から除外
            flags = np.where(wear == 7, self.memory.FLAG_FROZEN, flags)

            # 更新した状態の再パック
            for i, global_idx in enumerate(active_indices):
                self.memory.states[global_idx] = BitwiseMath.pack_state(
                    rx[i], ry[i], rz[i], px[i], py[i], pz[i], flags[i], wear[i]
                )

        # 6. キャッシュ最適化のための定期的なメモリアライメント
        if self.frame_count % 60 == 0:
            self._reorder_memory_by_spatial_locality()

        self.frame_count += 1

    def _reorder_memory_by_spatial_locality(self):
        """
        空間的な局所性に基づいて配列要素を物理的に並び替え、
        ハードウェアキャッシュのヒット率を高める。
        """
        hashes = calculate_spatial_hash(self.memory.pos_x, self.memory.pos_y, self.memory.pos_z, 20.0)
        sort_indices = np.argsort(hashes)
        
        self.memory.states = self.memory.states[sort_indices]
        self.memory.pos_x = self.memory.pos_x[sort_indices]
        self.memory.pos_y = self.memory.pos_y[sort_indices]
        self.memory.pos_z = self.memory.pos_z[sort_indices]

    def shutdown(self):
        self.running_flag.value = 0
        self.daemon.join()

if __name__ == '__main__':
    # コンソール出力は指示通り極力シンプルにする
    system = SystemOrchestrator(capacity=1000)
    
    try:
        for i in range(5):
            system.step()
    finally:
        system.shutdown()
        
    print("Execution completed.")