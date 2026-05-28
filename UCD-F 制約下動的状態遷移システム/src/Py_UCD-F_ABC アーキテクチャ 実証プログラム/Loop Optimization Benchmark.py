import time
import numpy as np

def run_benchmark():
    DATA_SIZE = 1_000_000
    print("=" * 55)
    print(f" Python forループ 爆速化検証 (データ数: {DATA_SIZE:,}件)")
    print("=" * 55)

    # 状態の初期パラメータ: 速度(Velocity), 強度(Intensity), 疲労(Fatigue)
    vel_init = 1
    int_init = 2
    fat_init = 0

    print("\n[1] 通常のforループ (オブジェクトの都度評価と型確認)")
    # 記事で指摘されている「すべてがオブジェクト」ゆえに遅いパターン
    vel_list = [vel_init] * DATA_SIZE
    int_list = [int_init] * DATA_SIZE
    fat_list = [fat_init] * DATA_SIZE

    start = time.perf_counter()
    for i in range(DATA_SIZE):
        vel_list[i] += int_list[i]
        # 条件に応じた状態遷移（疲労の蓄積）
        if vel_list[i] > 10:
            fat_list[i] += 1
    time_for = time.perf_counter() - start
    print(f"  -> 実行時間: {time_for:.5f} 秒 (基準)")

    print("\n[2] 次善策: リスト内包表記 (インタプリタ解釈コストの削減)")
    # 組み込み機能を活用し、Python内部の最適化の恩恵を受けるパターン
    vel_list = [vel_init] * DATA_SIZE
    fat_list = [fat_init] * DATA_SIZE

    start = time.perf_counter()
    # 速度の更新を一括生成
    vel_list = [v + i for v, i in zip(vel_list, int_list)]
    # 疲労の更新を一括生成（三項演算子で条件分岐を表現）
    fat_list = [f + 1 if v > 10 else f for f, v in zip(fat_list, vel_list)]
    time_comp = time.perf_counter() - start
    print(f"  -> 実行時間: {time_comp:.5f} 秒 (約 {time_for/time_comp:.1f} 倍速化)")

    print("\n[3] 最善策: 配列構造化とベクトル演算 (C言語層への処理委譲)")
    # データを連続した配列として分離管理し、最適化ライブラリに計算を一任する設計
    vel_arr = np.full(DATA_SIZE, vel_init, dtype=np.int32)
    int_arr = np.full(DATA_SIZE, int_init, dtype=np.int32)
    fat_arr = np.full(DATA_SIZE, fat_init, dtype=np.int32)

    start = time.perf_counter()
    # for文を一切使わず、計算グラフとして一括演算
    vel_arr += int_arr
    # 対象データの条件絞り込みも一括処理
    fat_arr = np.where(vel_arr > 10, fat_arr + 1, fat_arr)
    time_vec = time.perf_counter() - start
    print(f"  -> 実行時間: {time_vec:.5f} 秒 (約 {time_for/time_vec:.1f} 倍速化)")

    print("\n[4] 究極系: データ圧縮と一括演算 (単一整数への状態格納)")
    # キャッシュ効率を極限まで高めるため、複数の状態を1つの32bit整数に圧縮格納する設計思想
    # V: 0-7bit, I: 8-15bit, F: 16-23bit
    packed_val = vel_init | (int_init << 8) | (fat_init << 16)
    packed_arr = np.full(DATA_SIZE, packed_val, dtype=np.uint32)

    start = time.perf_counter()
    # ビットマスクで展開して演算
    v_arr = packed_arr & 0xFF
    i_arr = (packed_arr >> 8) & 0xFF
    f_arr = (packed_arr >> 16) & 0xFF

    v_arr += i_arr
    f_arr = np.where(v_arr > 10, f_arr + 1, f_arr)

    # 再度1つの整数に圧縮
    packed_arr = v_arr | (i_arr << 8) | (f_arr << 16)
    time_packed = time.perf_counter() - start
    print(f"  -> 実行時間: {time_packed:.5f} 秒")
    print("  ※注: Python上でのビット展開コストが含まれるため、実際のシステムでは")
    print("        この処理プロセスごと外部の高速計算エンジン(GPU等)へ完全に委譲します。")

    print("\n" + "=" * 55)
    print(" 結論: ボトルネックの克服")
    print("=" * 55)
    print(" 1. オブジェクトごとの型確認を行うPythonの通常forループは非常に重い。")
    print(f" 2. 配列構造化とベクトル演算により、驚異的な爆速化（約{time_for/time_vec:.0f}倍）が可能。")
    print(" 3. 極限の速度を求める場合、CPU側のループ解釈を排除し、")
    print("    最適化された外部の計算層へ処理を委譲することが絶対的な解決策となる。")
    print("=" * 55)

if __name__ == "__main__":
    run_benchmark()