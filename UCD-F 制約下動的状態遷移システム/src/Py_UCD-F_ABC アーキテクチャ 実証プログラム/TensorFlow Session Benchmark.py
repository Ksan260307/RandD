import time
import os
import tensorflow as tf
import numpy as np

# TensorFlowの不要なシステムログ出力を抑制し、コンソールをシンプルに保つ
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)

# 現代のTensorFlow 2.x環境で、記事にある1.x系のSession APIを使用するための設定
tf.compat.v1.disable_eager_execution()

def build_graph():
    """
    計算グラフ（電源のない回路）を構築します。
    ここでは検証用に、シンプルな行列の加算と乗算を定義します。
    """
    graph = tf.compat.v1.Graph()
    with graph.as_default():
        # 入力となるプレースホルダー（変数）
        a = tf.compat.v1.placeholder(tf.float32, shape=[100, 100], name="input_a")
        b = tf.compat.v1.placeholder(tf.float32, shape=[100, 100], name="input_b")
        
        # 演算処理（加算と行列積）
        add_op = tf.add(a, b, name="addition")
        mul_op = tf.matmul(add_op, b, name="multiplication")
        
    return graph, a, b, mul_op

def run_inefficiently(graph, a_tensor, b_tensor, target_op, iterations, feed_data):
    """
    【非効率なパターン】（リソース初期化のボトルネック発生）
    ループのたびにセッション（通電）を作成・破棄するため、
    メモリ確保等のオーバーヘッドが都度発生してしまいます。
    """
    start_time = time.time()
    
    for _ in range(iterations):
        # ループ内で毎回セッションを作成する（遅い原因）
        with tf.compat.v1.Session(graph=graph) as sess:
            _ = sess.run(target_op, feed_dict={a_tensor: feed_data, b_tensor: feed_data})
            
    end_time = time.time()
    return end_time - start_time

def run_efficiently(graph, a_tensor, b_tensor, target_op, iterations, feed_data):
    """
    【効率的なパターン】（コンテキストの再利用による最適化）
    最初に1度だけセッションを作成し、そのセッションを使い回して
    演算のみを連続して実行します。
    """
    start_time = time.time()
    
    # ループの外でセッションを1度だけ作成する（改善策）
    with tf.compat.v1.Session(graph=graph) as sess:
        for _ in range(iterations):
            _ = sess.run(target_op, feed_dict={a_tensor: feed_data, b_tensor: feed_data})
            
    end_time = time.time()
    return end_time - start_time

def main():
    print("=" * 55)
    print(" TensorFlow sess.run() 実行速度 比較検証 ")
    print("=" * 55)
    
    iterations = 200
    print(f"-> 検証実行回数: {iterations}回\n")
    
    # グラフの構築とテストデータの準備
    graph, a_tensor, b_tensor, target_op = build_graph()
    dummy_data = np.ones((100, 100), dtype=np.float32)
    
    # --- 非効率な実行（通常・遅いパターン） ---
    print("[1] 毎回セッションを作成する実行 (非効率)")
    print("    処理中...")
    slow_time = run_inefficiently(graph, a_tensor, b_tensor, target_op, iterations, dummy_data)
    print(f"    => 処理時間: {slow_time:.4f} 秒\n")
    
    # --- 効率的な実行（改善・速いパターン） ---
    print("[2] セッションを使い回す実行 (改善)")
    print("    処理中...")
    fast_time = run_efficiently(graph, a_tensor, b_tensor, target_op, iterations, dummy_data)
    print(f"    => 処理時間: {fast_time:.4f} 秒\n")
    
    # --- 結果比較 ---
    print("-" * 55)
    print("[検証結果]")
    if fast_time > 0:
        speedup = slow_time / fast_time
        print(f"改善された実装は、通常の実装に比べて 約 {speedup:.1f}倍 高速化されました。")
        print("（リソースの初期化オーバーヘッドが排除され、演算が最適化されています）")
    else:
        print("処理が速すぎて測定不能です。")
    print("=" * 55)

if __name__ == "__main__":
    main()