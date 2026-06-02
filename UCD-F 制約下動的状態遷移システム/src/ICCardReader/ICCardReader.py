import sys
import numpy as np
import time
import threading
import queue

try:
    from smartcard.System import readers
    from smartcard.util import toHexString
    from smartcard.Exceptions import NoCardException, CardConnectionException
except ImportError:
    print("エラー: 実際のICカードリーダーを使用するには 'pyscard' ライブラリが必要です。")
    print("以下のコマンドを実行してインストールしてください:")
    print("pip install pyscard")
    sys.exit(1)

# ==========================================
# 定数・システム設定
# ==========================================
NUM_ENTITIES = 50000       # 同時計算対象のデータポイント数
FIXED_POINT_SHIFT = 16     # 物理空間座標用の固定小数点シフト数 (16.16フォーマット)
TARGET_FPS = 30            # シミュレーションループの目標FPS

class ICCardReaderThread:
    """
    USB接続されたICリーダーからの入力を収集するバックグラウンド処理。
    メインの計算ループを阻害しないよう、非同期プロセスとして稼働します。
    """
    def __init__(self):
        self.input_queue = queue.Queue()
        self.running = False
        self.thread = None
        self.last_uid = None
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._hardware_read_loop, daemon=True)
        self.thread.start()
        
    def _hardware_read_loop(self):
        """
        pyscardを用いて実際のUSBリーダーからICカード読み取りを行うループ。
        """
        available_readers = readers()
        if not available_readers:
            print("[警告] ICカードリーダーが見つかりません。接続を確認してください。")
            return
            
        reader = available_readers[0]
        print(f"[情報] リーダーを検出しました: {reader}")
        
        connection = reader.createConnection()
        
        while self.running:
            try:
                connection.connect()
                # UIDを取得する一般的なAPDUコマンド (Mifare/FeliCa等)
                GET_UID_APDU = [0xFF, 0xCA, 0x00, 0x00, 0x00]
                data, sw1, sw2 = connection.transmit(GET_UID_APDU)
                
                # 正常に読み取れた場合 (SW1=90, SW2=00)
                if sw1 == 0x90 and sw2 == 0x00:
                    uid_str = toHexString(data).replace(" ", "")
                    
                    # 同じカードを連続で読み取るのを防ぐ
                    if uid_str != self.last_uid:
                        # UIDのバイト配列から、データポイントに与える「影響度」を計算 (0.0〜1.0)
                        intensity = sum(data) / (255 * len(data)) if data else 0.5
                        
                        print(f"\n[データ収集] IC情報を検知: UID={uid_str} (影響度: {intensity:.4f})")
                        self.input_queue.put({"uid": uid_str, "intensity": intensity})
                        self.last_uid = uid_str
                        
                time.sleep(0.5) # 連続読み取りの負荷軽減
                
            except (NoCardException, CardConnectionException):
                # カードが置かれていない場合は状態をリセットして待機
                self.last_uid = None
                time.sleep(0.5)
            except Exception as e:
                print(f"[エラー] 読み取り中にエラーが発生しました: {e}")
                time.sleep(1.0)

    def get_latest_input(self):
        """
        蓄積された入力データをメインシステム側へ渡す。
        """
        try:
            return self.input_queue.get_nowait()
        except queue.Empty:
            return None


class DataAnalysisEngine:
    """
    データポイントの状態遷移と物理計算を行うコアエンジン。
    CPUのループボトルネックを排除するため、NumPyベクトル演算として実装。
    """
    def __init__(self, num_entities):
        self.num = num_entities
        
        # ----------------------------------------------------
        # メモリレイアウト: ビットパッキング (SoA)
        # ----------------------------------------------------
        # 32bit整数内に全状態をパッキングしてメモリアクセスを効率化する
        # [0-1] 活性度A, [2-3] 活性度B, [4-5] 活性度C
        # [24-26] 状態フラグ (アクティブ状態など)
        # [27-29] 累積ダメージ (計算除外までの限界値)
        self.states = np.zeros(self.num, dtype=np.uint32)
        
        # 物理座標バッファ (16.16 固定小数点フォーマット)
        # 丸め誤差を防ぐための整数バッファ管理
        self.pos_x = np.zeros(self.num, dtype=np.int32)
        self.pos_y = np.zeros(self.num, dtype=np.int32)
        
        self._initialize_buffers()

    def _initialize_buffers(self):
        """データポイントの初期配置を生成"""
        # 物理座標をランダムな位置に配置 (0.0 〜 1000.0)
        rand_x = np.random.uniform(0, 1000, self.num)
        rand_y = np.random.uniform(0, 1000, self.num)
        
        # 固定小数点(整数)への変換
        self.pos_x[:] = (rand_x * (1 << FIXED_POINT_SHIFT)).astype(np.int32)
        self.pos_y[:] = (rand_y * (1 << FIXED_POINT_SHIFT)).astype(np.int32)
        
        # 初期状態フラグの設定 (24bit目を1にしてアクティブ化)
        active_flag = np.uint32(1 << 24)
        self.states[:] = active_flag
        
    def process_ic_data(self, input_data):
        """
        読み取ったICデータを系全体に適用し、状態を変動させる。
        """
        if not input_data:
            return
            
        intensity = input_data["intensity"]
        
        # 影響度に応じて対象となるデータポイント群を選出（マスク生成）
        mask = np.random.rand(self.num) < intensity
        
        # 影響を受けたデータポイントの活性度ビットを最大値(3)に書き換える
        boost_val = np.uint32(3)
        
        # 既存の活性度ビットをクリアして、新しい値をOR演算でセット
        self.states[mask] &= ~np.uint32(0b11)
        self.states[mask] |= boost_val

    def step(self):
        """
        1フレーム分の状態遷移計算。
        純粋なベクトル演算のみで記述し、分岐（if文）による処理遅延を防ぐ。
        """
        
        # --- 1. アンパッキング ---
        # ビット演算で活性度とダメージ値を取り出す
        intensity_a = self.states & np.uint32(0b11)
        damage = (self.states >> np.uint32(27)) & np.uint32(0b111)
        
        # --- 2. 状態遷移と物理計算 ---
        # 速度の計算: 活性度が高いほど速く、ダメージが高いほど遅くなる
        velocity = (intensity_a.astype(np.float32) / 3.0) * (1.0 - damage.astype(np.float32) / 7.0)
        
        # 固定小数点用の速度ベクトルへの変換
        fixed_vel = (velocity * (1 << FIXED_POINT_SHIFT)).astype(np.int32)
        
        # 移動方向の決定
        dir_x = np.random.choice(np.array([-1, 0, 1], dtype=np.int32), self.num)
        dir_y = np.random.choice(np.array([-1, 0, 1], dtype=np.int32), self.num)
        
        # 座標の更新
        self.pos_x += fixed_vel * dir_x
        self.pos_y += fixed_vel * dir_y
        
        # 境界判定 (0 〜 1000.0)
        max_pos = np.int32(1000 * (1 << FIXED_POINT_SHIFT))
        self.pos_x = np.clip(self.pos_x, 0, max_pos)
        self.pos_y = np.clip(self.pos_y, 0, max_pos)
        
        # --- 3. 状態の減衰と再パッキング ---
        # 移動したデータポイントは一定確率でダメージが蓄積、または活性度が減衰する
        # (条件分岐の代わりにブールマスクを用いた算術計算)
        decay_mask = (intensity_a > 0) & (np.random.rand(self.num) < 0.05)
        damage_mask = (velocity > 0) & (np.random.rand(self.num) < 0.01)
        
        new_intensity = np.maximum(intensity_a.astype(np.int32) - decay_mask.astype(np.int32), 0).astype(np.uint32)
        new_damage = np.minimum(damage.astype(np.int32) + damage_mask.astype(np.int32), 7).astype(np.uint32)
        
        # ビットをクリアして再セット
        self.states &= ~np.uint32(0b11) # 活性度クリア
        self.states &= ~(np.uint32(0b111) << np.uint32(27)) # ダメージクリア
        
        self.states |= new_intensity
        self.states |= (new_damage << np.uint32(27))

    def render_analytics_summary(self, frame, last_uid):
        """
        コンソールへの定期的なサマリー出力。
        空間内のデータポイント群の全体的な状態を分析して表示する。
        """
        active_mask = ((self.states >> np.uint32(24)) & np.uint32(1)) == 1
        active_count = np.sum(active_mask)
        
        intensity_a = self.states & np.uint32(0b11)
        damage = (self.states >> np.uint32(27)) & np.uint32(0b111)
        
        high_intensity_count = np.sum(intensity_a == 3)
        dead_count = np.sum(damage == 7) # 完全停止状態
        
        # 固定小数点を浮動小数点に戻して重心を計算
        cx = np.mean(self.pos_x) / (1 << FIXED_POINT_SHIFT)
        cy = np.mean(self.pos_y) / (1 << FIXED_POINT_SHIFT)
        
        print(f"[{frame:05d}] 最終読取IC: {last_uid if last_uid else '待機中':<8} | "
              f"総データ数: {active_count} | "
              f"高活性群: {high_intensity_count:<5} | "
              f"停止群: {dead_count:<5} | "
              f"空間重心: ({cx:.1f}, {cy:.1f})")


def main():
    print("==================================================")
    print(" IC情報分析・状態遷移システム ")
    print("==================================================")
    
    print(">>> ICカードリーダー接続処理を開始します...")
    reader_thread = ICCardReaderThread()
    reader_thread.start()
    
    print(f">>> 分析エンジンを初期化中... (対象データ数: {NUM_ENTITIES:,})")
    print(">>> メモリ領域確保完了。")
    engine = DataAnalysisEngine(num_entities=NUM_ENTITIES)
    
    print(">>> 分析ループを開始します。ICカードをタッチしてください。(Ctrl+Cで終了)\n")
    
    frame = 0
    last_uid_read = None
    
    try:
        while True:
            start_time = time.time()
            
            # 1. 外部入力の確認と適用
            input_data = reader_thread.get_latest_input()
            if input_data:
                last_uid_read = input_data["uid"]
                engine.process_ic_data(input_data)
            
            # 2. データ群の状態遷移計算
            engine.step()
            
            # 3. 定期的なサマリー出力
            if frame % TARGET_FPS == 0:
                engine.render_analytics_summary(frame, last_uid_read)
                
            frame += 1
            
            # 処理タイミングの制御
            elapsed = time.time() - start_time
            sleep_time = max(0, (1.0 / TARGET_FPS) - elapsed)
            time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        print("\n>>> 終了シグナルを受信しました。システムを安全に停止します。")
        reader_thread.running = False

if __name__ == "__main__":
    main()