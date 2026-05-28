import time
import sys
try:
    import redis
except ImportError:
    print("エラー: redisモジュールがインストールされていません。")
    print("実行前に 'pip install redis' を実行してください。")
    sys.exit(1)

def measure_time(func):
    """
    関数の実行時間を計測するデコレータ
    処理のボトルネック（通信の待機時間など）を可視化するために使用します。
    """
    def wrapper(*args, **kwargs):
        start_time = time.time()
        func(*args, **kwargs)
        end_time = time.time()
        return end_time - start_time
    return wrapper

class RedisPerformanceTester:
    """
    データ転送の最適化（通信オーバーヘッドの最小化）を検証するクラス。
    個別の通信を連続して行う状態から、データをまとめて一括送信する状態への
    処理効率の変化を計測します。
    """
    def __init__(self, host='localhost', port=6379, db=0):
        self.client = redis.StrictRedis(host=host, port=port, db=db, decode_responses=True)
        # 接続テスト
        try:
            self.client.ping()
        except redis.ConnectionError:
            print(f"エラー: Redisサーバー({host}:{port})に接続できません。")
            print("Docker等でRedisが起動しているか確認してください。")
            print("例: docker run --name redis -d -p 6379:6379 redis")
            sys.exit(1)

    def prepare_environment(self):
        """検証前にデータベースを初期化し、クリーンな状態を保ちます。"""
        self.client.flushdb()

    @measure_time
    def write_isolated(self, total_records):
        """
        [低速] 1件ずつ順番に書き込みを行う（ベースライン）。
        通信のオーバーヘッドが都度発生するため、リソースの消費が激しくなります。
        """
        self.prepare_environment()
        for i in range(total_records):
            self.client.set(f"data_iso:{i}", i)

    @measure_time
    def write_chunked(self, total_records, chunk_size):
        """
        [中〜高速] データを一定のサイズに分割（チャンク化）して書き込む。
        通信回数を減らし、一定のスループットを確保します。
        """
        self.prepare_environment()
        num_chunks = total_records // chunk_size
        
        for i in range(num_chunks):
            start = i * chunk_size
            end = (i + 1) * chunk_size
            # 送信用のデータ辞書を構築
            kv_payload = {f"data_chunk:{j}": j for j in range(start, end)}
            # msetを使用してまとめて書き込み（オーバーヘッド削減）
            self.client.mset(kv_payload)

    @measure_time
    def write_bulk(self, total_records):
        """
        [最高速] 全てのデータを一度の通信で書き込む。
        I/Oのボトルネックを完全に排除し、処理効率を最大化します。
        """
        self.prepare_environment()
        # 全データを含むペイロードを一括構築
        kv_payload = {f"data_bulk:{j}": j for j in range(total_records)}
        self.client.mset(kv_payload)

def main():
    # 検証条件の設定
    TOTAL_RECORDS = 10000
    CHUNK_SIZE = 100
    
    print("Redis接続を初期化中...")
    tester = RedisPerformanceTester()
    
    print(f"\n--- Redis 書き込み速度検証 ({TOTAL_RECORDS}件) ---")
    print("※ I/O通信の最適化による処理時間の変化を計測します\n")
    
    # 1. 1件ずつの書き込み（ベースライン）
    print("1. 1件ずつ書き込みを実行中...")
    time_isolated = tester.write_isolated(TOTAL_RECORDS)
    
    # 2. 100件ずつの書き込み
    print(f"2. {CHUNK_SIZE}件ずつまとめて書き込みを実行中...")
    time_chunked = tester.write_chunked(TOTAL_RECORDS, CHUNK_SIZE)
    
    # 3. 10000件一括の書き込み
    print("3. 全件一気にまとめて書き込みを実行中...")
    time_bulk = tester.write_bulk(TOTAL_RECORDS)
    
    print("\n--- 結果 ---")
    print(f"1. 1件ずつループ   : {time_isolated:.4f} sec (基準)")
    
    # 改善率の計算
    if time_chunked > 0:
        speedup_chunked = time_isolated / time_chunked
        print(f"2. {CHUNK_SIZE}件ずつまとめ : {time_chunked:.4f} sec (約 {speedup_chunked:.1f} 倍高速化)")
    
    if time_bulk > 0:
        speedup_bulk = time_isolated / time_bulk
        print(f"3. 全件一気にまとめ: {time_bulk:.4f} sec (約 {speedup_bulk:.1f} 倍高速化)")
        
    print("--------------------")
    print("結論: 個別に通信を行うよりも、データをまとめて一括送信(mset)することで")
    print("ネットワークやプロセス間の通信オーバーヘッドが排除され、圧倒的に高速化されます。")

if __name__ == "__main__":
    main()