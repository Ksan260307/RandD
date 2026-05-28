import numpy as np
import time

def normal_append(data_source):
    """
    通常のNumpy appendを用いた追加処理。
    ※ループ毎にメモリの再確保が発生するため、要素数が増えるほどパフォーマンスが低下します。
    """
    buffer = np.array([], dtype=np.uint32)
    start_time = time.time()
    
    for item in data_source:
        buffer = np.append(buffer, item)
        
    elapsed_time = time.time() - start_time
    return elapsed_time

def optimized_append(data_source):
    """
    リストを経由した改善版の追加処理。
    ※Pythonの可変長配列（リスト）を用いてメモリ再確保のコストを抑え、
    　最後に一括してNumpy配列（固定長配列）へ変換します。
    """
    buffer = np.array([], dtype=np.uint32)
    start_time = time.time()
    
    # 一時的にリストへ変換
    temp_list = buffer.tolist()
    
    for item in data_source:
        temp_list.append(item)
        
    # 一括でNumpy配列へ再変換
    buffer = np.asarray(temp_list, dtype=np.uint32)
    
    elapsed_time = time.time() - start_time
    return elapsed_time

def main():
    print("=== 配列データ追加 高速化検証 ===")
    
    # 状態データを想定したダミーデータ（32bit整数）の生成
    # ※通常のappendは非常に重いため、まずは10万件で検証します。
    data_count = 100000
    print(f"検証データ件数: {data_count} 件\n")
    
    # ダミーソースデータの準備
    dummy_data = np.random.randint(0, 4294967295, size=data_count, dtype=np.uint32)

    # 1. 通常手法の計測
    print("1. 通常のNumpy appendを実行中...")
    time_normal = normal_append(dummy_data)
    print(f"   -> 所要時間: {time_normal:.4f} 秒\n")

    # 2. 改善手法の計測
    print("2. 改善版のappend(リスト経由)を実行中...")
    time_opt = optimized_append(dummy_data)
    print(f"   -> 所要時間: {time_opt:.4f} 秒\n")

    # 3. 比較結果の出力
    if time_opt > 0:
        speed_up = time_normal / time_opt
        print("=== 結論 ===")
        print(f"改善手法は通常手法と比較して 約 {speed_up:.1f} 倍 高速に処理を完了しました。")
    else:
        print("=== 結論 ===")
        print("処理が速すぎて正確な倍率が計算できませんでした（データ件数を増やして再検証してください）。")

if __name__ == "__main__":
    main()