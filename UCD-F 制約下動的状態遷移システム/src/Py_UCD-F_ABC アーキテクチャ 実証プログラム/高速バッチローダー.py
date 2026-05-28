import time
import numpy as np
import argparse
import logging
import os

# --- オプショナルライブラリのインポート ---
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

# --- ロギングの設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- 実用データセット管理 ---
def load_data(data_path=None, dummy_size=100000):
    """
    実環境でのデータ読み込みを想定した関数。
    実際の運用ではCSVやNumpyファイル、HDF5などから読み込みます。
    """
    if data_path and os.path.exists(data_path):
        logger.info(f"データファイルから読み込みます: {data_path}")
        # 例: np.load() や pandas.read_csv() などを実装
        # data = np.load(data_path)
        # return data['features'], data['labels']
        raise NotImplementedError("実際のファイル読み込み処理をここに実装してください。")
    else:
        logger.info(f"指定されたデータがないため、ダミーデータを生成します (サイズ: {dummy_size:,})")
        features = np.random.randn(dummy_size, 10).astype(np.float32)
        labels = np.random.randint(0, 2, size=(dummy_size, 1)).astype(np.float32)
        return features, labels

def get_active_indices(features, threshold=0.5):
    """
    実際の運用でのフィルタリング処理。
    例：特定の特徴量がある閾値を超えているデータのみを処理対象とするなど。
    """
    # 例: 0番目の特徴量が threshold より大きいデータのインデックスを取得
    active_mask = features[:, 0] > threshold
    return np.nonzero(active_mask)[0]

def to_tensor_transform(batch):
    """
    抽出したバッチ(Numpy配列のタプル)をPyTorchのTensorに変換するヘルパー関数
    """
    if HAS_TORCH:
        # as_tensor は可能であればコピーを避け、メモリを共有します
        return tuple(torch.as_tensor(arr) for arr in batch)
    else:
        logger.warning("PyTorchがインストールされていないため、Tensorへの変換をスキップします。")
        return batch

class FastDataLoader:
    """
    要素を1つずつ取り出すボトルネックを排除し、
    スライシングを用いて一括でバッチを取り出す高速ローダー。
    """
    def __init__(self, *arrays, batch_size=10000, indices=None, shuffle=False, transform=None):
        self.arrays = arrays
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.transform = transform
        
        if indices is not None:
            self.indices = indices
            self.data_size = len(indices)
        else:
            self.data_size = len(arrays[0])
            self.indices = np.arange(self.data_size)
            
        # 全ての配列のサイズが一致しているか検証
        assert all(len(arr) >= self.data_size for arr in arrays), "配列のサイズが不足しています"

    def __len__(self):
        """1エポックあたりのバッチ数を返す (PyTorchなどの学習ループ互換用)"""
        return (self.data_size + self.batch_size - 1) // self.batch_size

    def __iter__(self):
        self.current_idx = 0
        if self.shuffle:
            # インデックスのみをシャッフルし、実データの移動コストを抑える
            np.random.shuffle(self.indices)
        return self

    def __next__(self):
        if self.current_idx >= self.data_size:
            raise StopIteration

        start = self.current_idx
        end = min(start + self.batch_size, self.data_size)
        batch_indices = self.indices[start:end]

        if not self.shuffle and len(self.indices) == len(self.arrays[0]):
            # 全データ対象かつシャッフルなしの場合、直接スライスを返すことで
            # 新たなメモリ確保を行わず（ゼロコピー）超高速にビューを返す
            batch = tuple(arr[start:end] for arr in self.arrays)
        else:
            # シャッフルあり、または特定インデックスのみ抽出の場合
            batch = tuple(arr[batch_indices] for arr in self.arrays)

        if self.transform:
            batch = self.transform(batch)

        self.current_idx += self.batch_size
        return batch

def process_batch(batch_idx, batch_data, use_tqdm=False):
    """
    実際の推論や学習処理を行うモック関数。
    """
    features, labels = batch_data
    
    # -------------------------------------------------------------
    # ここに PyTorch の model(features) や loss_fn(output, labels) 
    # などの実際の処理を記述します。
    # -------------------------------------------------------------
    
    # 擬似的な計算負荷（学習や推論にかかる時間をシミュレート）
    time.sleep(0.001) 
    
    if not use_tqdm and batch_idx % 100 == 0 and batch_idx > 0:
        # tqdmを使わない場合のみ定期的にログ出力
        logger.info(f"  - {batch_idx} バッチ処理完了 (Shape: {features.shape}, Type: {type(features)})")

def run_pipeline(args):
    """
    データ読み込みからバッチ処理までのメインパイプライン
    """
    logger.info("=== データ処理パイプラインを開始します ===")
    
    # 1. データの準備
    features, labels = load_data(args.data_path, args.data_size)
    
    indices = None
    if args.filter:
        logger.info("アクティブデータのフィルタリングを実行中...")
        indices = get_active_indices(features)
        logger.info(f"フィルタリング完了: 対象データ {len(indices):,} 件 / 全体 {len(features):,} 件")
        
    transform_fn = to_tensor_transform if args.to_tensor else None
    if args.to_tensor and not HAS_TORCH:
        logger.error("PyTorchが見つかりません。--to_tensorオプションは無視されます。")
    
    # 2. ローダーの初期化
    logger.info(f"FastDataLoaderを初期化: バッチサイズ={args.batch_size}, シャッフル={args.shuffle}")
    loader = FastDataLoader(
        features, labels,
        batch_size=args.batch_size,
        indices=indices,
        shuffle=args.shuffle,
        transform=transform_fn
    )
    
    # 3. エポックループ（処理の実行）
    total_batches = len(loader)
    logger.info(f"処理を開始します (全 {args.epochs} エポック, 1エポックあたり {total_batches} バッチ)")
    
    use_tqdm_flag = args.use_tqdm and HAS_TQDM
    if args.use_tqdm and not HAS_TQDM:
        logger.warning("tqdmがインストールされていません。通常のログ出力にフォールバックします。")
    
    for epoch in range(1, args.epochs + 1):
        epoch_start = time.perf_counter()
        
        # tqdmによるプログレスバーの表示制御
        batch_iter = tqdm(loader, desc=f"Epoch {epoch}/{args.epochs}", leave=False) if use_tqdm_flag else loader
        
        for batch_idx, batch in enumerate(batch_iter):
            process_batch(batch_idx, batch, use_tqdm=use_tqdm_flag)
            
        epoch_time = time.perf_counter() - epoch_start
        logger.info(f"Epoch {epoch}/{args.epochs} 完了 | 処理時間: {epoch_time:.4f} 秒")
        
    logger.info("=== パイプラインが正常に終了しました ===")

def main():
    parser = argparse.ArgumentParser(description="実運用向け 高速バッチ処理アプリケーション")
    parser.add_argument("--data_path", type=str, default="", help="入力データファイルのパス (CSV, NPY等。指定がなければダミーデータを使用)")
    parser.add_argument("--data_size", type=int, default=1000000, help="ダミーデータ生成時のデータサイズ")
    parser.add_argument("--batch_size", type=int, default=10000, help="ミニバッチのサイズ")
    parser.add_argument("--epochs", type=int, default=2, help="処理を実行するエポック数")
    parser.add_argument("--shuffle", action="store_true", help="毎エポックデータをシャッフルするかどうか")
    parser.add_argument("--filter", action="store_true", help="特定条件のデータのみを抽出して処理するかどうか")
    parser.add_argument("--to_tensor", action="store_true", help="バッチをPyTorchのTensorに変換して出力するかどうか")
    parser.add_argument("--use_tqdm", action="store_true", help="プログレスバー(tqdm)を使用して進捗を表示するかどうか")
    
    args = parser.parse_args()
    
    # 手動で実行する場合（引数なしの場合）は、デフォルトで少し動作がわかるように設定を上書き
    if not any(vars(args).values()) or args.data_size == 1000000:
        # デモ用に少し値を調整
        args.epochs = 2
        args.batch_size = 50000
    
    run_pipeline(args)

if __name__ == "__main__":
    main()