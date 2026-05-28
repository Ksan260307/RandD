import pandas as pd
import numpy as np
import time
import os
import io
import warnings
warnings.filterwarnings('ignore')

def optimize_dtypes(df):
    """
    データフレームのメモリ使用量を最適化するために、適切な型に変換する関数
    Qiitaの記事で紹介されている「reduce_mem_usage」と同等のロジック
    """
    for col in df.columns:
        col_type = df[col].dtype
        # object型に加え、category型も数値の最小/最大計算から除外する
        if col_type != object and str(col_type) != 'category':
            c_min = df[col].min()
            c_max = df[col].max()
            if str(col_type)[:3] == 'int':
                if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                    df[col] = df[col].astype(np.int16)
                elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                    df[col] = df[col].astype(np.int32)
                elif c_min > np.iinfo(np.int64).min and c_max < np.iinfo(np.int64).max:
                    df[col] = df[col].astype(np.int64)  
            else:
                if c_min > np.finfo(np.float16).min and c_max < np.finfo(np.float16).max:
                    df[col] = df[col].astype(np.float16)
                elif c_min > np.finfo(np.float32).min and c_max < np.finfo(np.float32).max:
                    df[col] = df[col].astype(np.float32)
                else:
                    df[col] = df[col].astype(np.float64)
    return df

def generate_dummy_data(num_rows=1000000):
    """
    検証用のダミーデータを生成する関数
    """
    print(f"[{num_rows}行]のダミーデータを生成中...")
    df = pd.DataFrame({
        'id': np.random.randint(0, 10000, num_rows),
        'value_a': np.random.rand(num_rows) * 100,
        'value_b': np.random.rand(num_rows) * 1000,
        'category': np.random.choice(['A', 'B', 'C', 'D'], num_rows)
    })
    
    # CSVに保存して、読み込みテストに備える
    df.to_csv('dummy_data.csv', index=False)
    return df

def run_normal_process():
    """
    型指定なし、forループを用いた「通常の（遅い）」処理のシミュレーション
    """
    print("\n--- 【検証1】通常の処理（遅いアプローチ） ---")
    start_time = time.time()
    
    # 1. 型指定なしでの読み込み
    load_start = time.time()
    df = pd.read_csv('dummy_data.csv')
    load_time = time.time() - load_start
    print(f"データ読み込み時間 (型指定なし): {load_time:.4f} 秒")
    
    # 2. メモリ使用量の確認
    mem_usage = df.memory_usage().sum() / 1024**2
    print(f"メモリ使用量 (最適化なし): {mem_usage:.2f} MB")
    
    # 3. forループによる処理 (わざと遅くする)
    process_start = time.time()
    results = []
    # 全件ループは時間がかかりすぎるため、先頭10000件で検証
    loop_limit = min(10000, len(df))
    print(f"forループ処理中 ({loop_limit}件)...")
    for index, row in df.head(loop_limit).iterrows():
        # 何らかの重い計算のシミュレーション
        res = row['value_a'] * 2 + row['value_b'] / 3
        results.append(res)
    df.loc[:loop_limit-1, 'result_normal'] = results
    process_time = time.time() - process_start
    print(f"forループ処理時間 ({loop_limit}件): {process_time:.4f} 秒")
    
    total_time = time.time() - start_time
    print(f"--- 合計時間 (通常): {total_time:.4f} 秒 ---")
    return total_time

def run_optimized_process():
    """
    型指定、最適化、apply/ベクトル化を用いた「改善された（速い）」処理のシミュレーション
    """
    print("\n--- 【検証2】改善された処理（高速アプローチ） ---")
    start_time = time.time()
    
    # 1. 型指定ありでの読み込み (一部だけ指定してみる)
    load_start = time.time()
    dtypes = {'id': np.int32, 'value_a': np.float64, 'value_b': np.float64, 'category': 'category'}
    df_opt = pd.read_csv('dummy_data.csv', dtype=dtypes)
    load_time = time.time() - load_start
    print(f"データ読み込み時間 (型指定あり): {load_time:.4f} 秒")
    
    # 2. 型の最適化 (Qiita記事の関数適用)
    opt_start = time.time()
    df_opt = optimize_dtypes(df_opt)
    opt_time = time.time() - opt_start
    mem_usage_opt = df_opt.memory_usage().sum() / 1024**2
    print(f"型の最適化処理時間: {opt_time:.4f} 秒")
    print(f"メモリ使用量 (最適化後): {mem_usage_opt:.2f} MB")
    
    # 3. ベクトル化処理 (forを使わない)
    process_start = time.time()
    # 同じ10000件に対してベクトル化処理を行う
    loop_limit = min(10000, len(df_opt))
    print(f"ベクトル化処理中 ({loop_limit}件)...")
    # applyを使うよりも、直接ベクトル演算する方がさらに速い
    # 今回はapplyの速さを見せるため、あえてapplyと直接演算のハイブリッドに
    df_opt.loc[:loop_limit-1, 'result_opt'] = df_opt['value_a'][:loop_limit] * 2 + df_opt['value_b'][:loop_limit] / 3
    
    process_time = time.time() - process_start
    print(f"ベクトル化処理時間 ({loop_limit}件): {process_time:.4f} 秒")
    
    total_time = time.time() - start_time
    print(f"--- 合計時間 (改善): {total_time:.4f} 秒 ---")
    return total_time

if __name__ == "__main__":
    print("=== Pandas高速化 検証開始 ===")
    # 100万行のデータを作成 (PCスペックに合わせて調整可能)
    try:
        generate_dummy_data(1000000)
        
        normal_time = run_normal_process()
        opt_time = run_optimized_process()
        
        print("\n=== 検証結果まとめ ===")
        print(f"通常処理: {normal_time:.4f} 秒")
        print(f"改善処理: {opt_time:.4f} 秒")
        print(f"--> 約 {normal_time / opt_time:.1f} 倍高速化されました！")
        
    finally:
        # 後始末：ダミーデータの削除
        if os.path.exists('dummy_data.csv'):
            os.remove('dummy_data.csv')
            print("\n※ ダミーデータファイルを削除しました。")