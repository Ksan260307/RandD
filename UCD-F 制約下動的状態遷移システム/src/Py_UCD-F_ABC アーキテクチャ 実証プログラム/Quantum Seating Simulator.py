import numpy as np
import time
from typing import List, Tuple, Dict, Optional

# =====================================================================
# Py_UCD-F_ABC: Universal Constrained Dynamics Framework (Fallback Backend)
# モジュール: Quantum Seating Simulator (並行宇宙展開型 席替えエンジン)
# =====================================================================

# 魂のビットパッキング (32bit Base Layout)
# メモリ帯域幅を極大化するため、エンティティの状態を1つの uint32 にパッキングします。
# [0-7]   : Student ID (8 bits, max 255)
# [8-9]   : vA: Gender (2 bits, 0:None, 1:Male, 2:Female)
# [10]    : vB: Needs Front Row (1 bit, 0:False, 1:True)
# [11-18] : vC: Conflict Group ID (8 bits, 0=None)
ID_SHIFT = 0
ID_MASK = 0xFF
GENDER_SHIFT = 8
GENDER_MASK = 0x03
FRONT_SHIFT = 10
FRONT_MASK = 0x01
CONFLICT_SHIFT = 11
CONFLICT_MASK = 0xFF

class Student:
    """ユーザー空間のエンティティ定義"""
    def __init__(self, student_id: int, gender: int, needs_front: bool, conflict_id: int = 0):
        self.id = student_id
        self.gender = gender            # 1: 男性, 2: 女性
        self.needs_front = needs_front  # True: 前列優先
        self.conflict_id = conflict_id  # 共通のIDを持つ生徒同士は隣接不可

def pack_students(students: List[Student]) -> np.ndarray:
    """CPU-GPU境界の完全WGSL委譲をエミュレートするSoAパッキング"""
    packed = np.zeros(len(students), dtype=np.uint32)
    for i, s in enumerate(students):
        val = np.uint32(0)
        val |= (np.uint32(s.id) & ID_MASK) << ID_SHIFT
        val |= (np.uint32(s.gender) & GENDER_MASK) << GENDER_SHIFT
        val |= (np.uint32(1 if s.needs_front else 0) & FRONT_MASK) << FRONT_SHIFT
        val |= (np.uint32(s.conflict_id) & CONFLICT_MASK) << CONFLICT_SHIFT
        packed[i] = val
    return packed

class QuantumSeatingSimulator:
    """未来予測プロセス(Shadow Worker)に基づく席替えシミュレータ"""
    
    def __init__(self, rows: int, cols: int, front_limit: int):
        self.rows = rows
        self.cols = cols
        self.front_limit = front_limit
        self.total_seats = rows * cols

    def execute_simulation(self, students: List[Student], disabled_indices: List[int], universes: int = 10000) -> Tuple[np.ndarray, int]:
        """
        指定された並行宇宙(universes)の数だけ座席配置をテンソル上で同時展開し、
        影響円錐に基づく一括RuinScore評価を行う
        """
        # 前列優先と通常生徒を分離してパッキング
        front_students = [s for s in students if s.needs_front]
        regular_students = [s for s in students if not s.needs_front]
        
        packed_front = pack_students(front_students)
        packed_regular = pack_students(regular_students)
        
        num_front = len(packed_front)
        num_regular = len(packed_regular)

        # 利用可能な座席のインデックス空間を構築
        all_indices = set(range(self.total_seats))
        enabled_indices = list(all_indices - set(disabled_indices))
        
        if len(enabled_indices) < len(students):
            raise ValueError("Zero-Lock: 使用可能な座席が生徒数よりも少なくなっています。")
            
        front_idx_list = [i for i in enabled_indices if (i // self.cols) < self.front_limit]
        back_idx_list = [i for i in enabled_indices if (i // self.cols) >= self.front_limit]
        
        front_idx_arr = np.array(front_idx_list, dtype=np.int32)
        back_idx_arr = np.array(back_idx_list, dtype=np.int32)

        # --- 決定論的ロックステップ: universes 個の未来を並行生成 ---
        
        # 1. 前列インデックスの並行シャッフル
        front_rand = np.random.rand(universes, len(front_idx_arr))
        front_shuffled_idx = front_idx_arr[np.argsort(front_rand, axis=1)]
        
        # 前列に座るインデックスと、余ったインデックスに分割
        selected_front_idx = front_shuffled_idx[:, :num_front]
        remaining_front_idx = front_shuffled_idx[:, num_front:]

        # 2. 通常生徒用インデックスの構築と並行シャッフル
        back_idx_batch = np.tile(back_idx_arr, (universes, 1))
        
        if remaining_front_idx.shape[1] > 0:
            remaining_idx = np.concatenate([remaining_front_idx, back_idx_batch], axis=1)
        else:
            remaining_idx = back_idx_batch
            
        regular_rand = np.random.rand(universes, remaining_idx.shape[1])
        remaining_shuffled_idx = remaining_idx[np.arange(universes)[:, None], np.argsort(regular_rand, axis=1)]
        selected_remaining_idx = remaining_shuffled_idx[:, :num_regular]

        # 3. テンソル空間への全生徒の一括配置 (Zero-copy Interoperabilityを想定)
        assignments = np.zeros((universes, self.total_seats), dtype=np.uint32)
        batch_indices = np.arange(universes)[:, None]
        
        assignments[batch_indices, selected_front_idx] = packed_front
        assignments[batch_indices, selected_remaining_idx] = packed_regular
        
        # 形状を2次元グリッド (N, rows, cols) に変換
        grid = assignments.reshape((universes, self.rows, self.cols))

        # --- RuinScore(破綻値) の遅延評価グラフ演算 ---
        
        # 各種プロパティの抽出
        gender_grid = (grid >> GENDER_SHIFT) & GENDER_MASK
        conflict_grid = (grid >> CONFLICT_SHIFT) & CONFLICT_MASK
        
        # 1. 男女交互制約 (隣り合う性別が同じなら +1点)
        # 横方向の評価
        valid_h = (gender_grid[:, :, :-1] != 0) & (gender_grid[:, :, 1:] != 0)
        gender_conf_h = valid_h & (gender_grid[:, :, :-1] == gender_grid[:, :, 1:])
        # 縦方向の評価
        valid_v = (gender_grid[:, :-1, :] != 0) & (gender_grid[:, 1:, :] != 0)
        gender_conf_v = valid_v & (gender_grid[:, :-1, :] == gender_grid[:, 1:, :])
        
        gender_score = gender_conf_h.sum(axis=(1, 2)) + gender_conf_v.sum(axis=(1, 2))

        # 2. 相性最悪制約 (隣り合うconflict_idが同じなら +1000点)
        # 横方向の評価
        valid_conf_h = (conflict_grid[:, :, :-1] != 0) & (conflict_grid[:, :, 1:] != 0)
        hard_conf_h = valid_conf_h & (conflict_grid[:, :, :-1] == conflict_grid[:, :, 1:])
        # 縦方向の評価
        valid_conf_v = (conflict_grid[:, :-1, :] != 0) & (conflict_grid[:, 1:, :] != 0)
        hard_conf_v = valid_conf_v & (conflict_grid[:, :-1, :] == conflict_grid[:, 1:, :])
        
        hard_score = (hard_conf_h.sum(axis=(1, 2)) + hard_conf_v.sum(axis=(1, 2))) * 1000

        # 総RuinScoreの算出
        total_ruin_score = gender_score + hard_score
        
        # 最小のエントロピー（破綻値）を持つ並行宇宙のインデックスを観測
        best_universe_idx = np.argmin(total_ruin_score)
        best_score = total_ruin_score[best_universe_idx]
        best_grid = grid[best_universe_idx]
        
        return best_grid, best_score

def print_seating(grid: np.ndarray, students_dict: Dict[int, Student]):
    """ビットパックされた最適解をターミナル上に復元・可視化する"""
    rows, cols = grid.shape
    for r in range(rows):
        row_str = []
        for c in range(cols):
            packed = grid[r, c]
            if packed == 0:
                row_str.append("[   空 席   ]")
            else:
                s_id = packed & ID_MASK
                student = students_dict.get(s_id)
                g_str = "♂" if student.gender == 1 else "♀"
                f_str = "前" if student.needs_front else "  "
                c_str = f"X{student.conflict_id}" if student.conflict_id > 0 else "  "
                row_str.append(f"[{s_id:02d}:{g_str}:{f_str}:{c_str}]")
        print(" ".join(row_str))

def main():
    # 空間構造の定義: 5行 x 5列 (25席)
    rows, cols = 5, 5
    front_limit = 2
    
    # 死骸の地形化(Zero-Lock): 左上と右上の席を使用不可とする
    disabled_indices = [0, 4] 
    
    # エンティティの生成: 23名
    students = []
    for i in range(1, 24):
        gender = 1 if i <= 12 else 2 # 男12名, 女11名
        needs_front = True if i in [1, 2, 13, 14] else False
        
        # 相性グループの付与 (同じIDは隣接不可)
        conflict = 0
        if i in [3, 4]: conflict = 1
        elif i in [15, 16]: conflict = 2
        
        students.append(Student(i, gender, needs_front, conflict))
        
    simulator = QuantumSeatingSimulator(rows, cols, front_limit)
    
    print("=== Py_UCD-F_ABC: Quantum Seating Simulator ===")
    print("状態: 未来宇宙の並行展開とMCTS評価を開始します...\n")
    
    start_time = time.perf_counter()
    # 1万回の席替えパターンを同時展開
    best_grid, best_score = simulator.execute_simulation(students, disabled_indices, universes=10000)
    end_time = time.perf_counter()
    
    # 観測結果の出力
    print(f"探索完了: 10,000 個の並行宇宙を評価しました。")
    print(f"計算時間: {(end_time - start_time)*1000:.2f} ms")
    print(f"最小 RuinScore: {best_score}")
    print("\n[ 実体化された最適座席配置 ] (ID:性別:前列:相性NG)")
    
    students_dict = {s.id: s for s in students}
    print_seating(best_grid, students_dict)

if __name__ == "__main__":
    main()

# respect for https://qiita.com/rio-taro117/items/42d1e5dcf965b1f03019