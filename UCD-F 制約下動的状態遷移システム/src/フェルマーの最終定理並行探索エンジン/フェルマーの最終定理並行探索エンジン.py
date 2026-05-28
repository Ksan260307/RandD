import numpy as np
import time
import sys

# 状態定義定数
STATUS_ACTIVE = 0  # 探索継続
STATUS_FOUND = 1   # 反証発見
STATUS_INVALID = 2 # 探索無効（これ以上の計算は不要）

class FermatParallelSearchEngine:
    """
    大規模並行探索フレームワーク
    設計思想の「状態のパッキング」「テンソル演算による一括遷移」「不要要素の動的抽出」を取り入れた探索エンジン
    """
    def __init__(self, max_val=100, max_n=5):
        self.max_val = max_val
        self.max_n = max_n
        
    def _pack_state(self, x, y, z, n, status):
        """
        状態のビットパッキング (32bit整数への圧縮)
        メモリ効率の極大化とデータアクセスの連続性を確保します。
        - [0-7]ビット: x (最大255)
        - [8-15]ビット: y (最大255)
        - [16-23]ビット: z (最大255)
        - [24-27]ビット: n (最大15)
        - [28-29]ビット: 状態フラグ (Active/Found/Invalid)
        """
        x = np.asarray(x, dtype=np.uint32)
        y = np.asarray(y, dtype=np.uint32)
        z = np.asarray(z, dtype=np.uint32)
        n = np.asarray(n, dtype=np.uint32)
        status = np.asarray(status, dtype=np.uint32)
        
        packed = (x & 0xFF) | ((y & 0xFF) << 8) | ((z & 0xFF) << 16) | ((n & 0x0F) << 24) | ((status & 0x03) << 28)
        return packed

    def _unpack_state(self, packed):
        """状態のアンパック（復元）"""
        x = packed & 0xFF
        y = (packed >> 8) & 0xFF
        z = (packed >> 16) & 0xFF
        n = (packed >> 24) & 0x0F
        status = (packed >> 28) & 0x03
        return x, y, z, n, status

    def _generate_sector(self, n_val, x_start, x_end):
        """
        空間セクターの生成 (計算対象の極小化とメモリ保護)
        影響範囲を絞り込み、全空間ではなく局所的なブロックごとに状態を生成します。
        """
        x_range = np.arange(x_start, x_end + 1, dtype=np.uint32)
        y_range = np.arange(1, self.max_val + 1, dtype=np.uint32)
        z_range = np.arange(1, self.max_val + 1, dtype=np.uint32)
        
        # 配列演算ベースで全ての組み合わせを構築
        X, Y, Z = np.meshgrid(x_range, y_range, z_range, indexing='ij')
        X = X.ravel()
        Y = Y.ravel()
        Z = Z.ravel()
        N = np.full_like(X, n_val)
        Status = np.full_like(X, STATUS_ACTIVE)
        
        return self._pack_state(X, Y, Z, N, Status)

    def _evaluate_batch(self, packed_states):
        """
        純粋なベクトル演算による状態遷移
        浮動小数点を排除し、完全な整数演算のみで並行評価を実行します。
        """
        if len(packed_states) == 0:
            return packed_states

        x, y, z, n, status = self._unpack_state(packed_states)
        
        # 計算中のオーバーフローを防ぐため、内部計算のみ64bit(拡張精度)へ一時的に移行
        x_64 = x.astype(np.uint64)
        y_64 = y.astype(np.uint64)
        z_64 = z.astype(np.uint64)
        n_64 = n.astype(np.uint64)
        
        x_pow = x_64 ** n_64
        y_pow = y_64 ** n_64
        z_pow = z_64 ** n_64
        
        # x^n + y^n == z^n の判定
        is_match = (x_pow + y_pow) == z_pow
        
        # Z が大きすぎる等の明らかな不成立パターンの枝刈り (無効状態への移行)
        is_invalid = (x_pow + y_pow) < z_pow
        
        # 状態の更新
        status = np.where(is_match, STATUS_FOUND, status)
        status = np.where(is_invalid, STATUS_INVALID, status)
        
        return self._pack_state(x, y, z, n, status)

    def _stream_compaction(self, packed_states):
        """
        アクティブ要素の抽出 (コンパクション)
        計算を継続する必要のない要素（無効化されたもの）をメモリ配列から除外し、密度を高めます。
        """
        _, _, _, _, status = self._unpack_state(packed_states)
        
        found_mask = status == STATUS_FOUND
        found_states = packed_states[found_mask]
        
        active_mask = status == STATUS_ACTIVE
        active_states = packed_states[active_mask]
        
        return active_states, found_states

    def run(self):
        """探索のメインループ"""
        print(f"=== フェルマーの最終定理 大規模並行探索開始 ===")
        print(f"探索範囲: x, y, z ∈ [1, {self.max_val}]")
        print(f"検証次数: n ∈ [3, {self.max_n}]")
        print(f"システム: メモリ保護(セクター分割) 有効 / ベクトル化演算 有効\n")
        
        start_time = time.time()
        total_found = []
        
        for n_val in range(3, self.max_n + 1):
            print(f"[*] 次数 n = {n_val} の空間探索を開始...")
            
            # メモリ枯渇を防ぐため、Xの範囲をセクター（ブロック）に分割して処理
            x_step = 10 
            for x_start in range(1, self.max_val + 1, x_step):
                x_end = min(x_start + x_step - 1, self.max_val)
                
                # 1. 空間セクターの生成
                packed_sector = self._generate_sector(n_val, x_start, x_end)
                initial_count = len(packed_sector)
                
                # 2. 状態の一括遷移評価
                evaluated_sector = self._evaluate_batch(packed_sector)
                
                # 3. アクティブ要素抽出による枝刈り
                active_states, found_states = self._stream_compaction(evaluated_sector)
                pruned_count = initial_count - len(active_states) - len(found_states)
                
                # 結果の記録
                if len(found_states) > 0:
                    fx, fy, fz, fn, _ = self._unpack_state(found_states)
                    for i in range(len(fx)):
                        total_found.append((fx[i], fy[i], fz[i], fn[i]))
                        print(f"\n  >>> [反証発見] x={fx[i]}, y={fy[i]}, z={fz[i]}, n={fn[i]}")
                
                # 進捗のリアルタイム更新（コンソール用）
                sys.stdout.write(f"\r  進捗: x={x_start:03d}~{x_end:03d} | 総評価: {initial_count:7d}件 | 枝刈り: {pruned_count:7d}件 | 継続: {len(active_states):7d}件")
                sys.stdout.flush()
                
            print("\n  完了。")

        elapsed_time = time.time() - start_time
        print(f"\n=== 探索終了 ===")
        print(f"総所要時間: {elapsed_time:.3f} 秒")
        if len(total_found) == 0:
            print(f"最終結果: 指定範囲において反証は発見されませんでした。定理は維持されています。")
        else:
            print(f"最終結果: {len(total_found)} 件の反証が発見されました。")

if __name__ == "__main__":
    # 探索の範囲（例として x, y, z は100まで、nは5まで）
    # パソコンのスペックに応じて max_val を大きくすることができます。
    app = FermatParallelSearchEngine(max_val=100, max_n=5)
    app.run()