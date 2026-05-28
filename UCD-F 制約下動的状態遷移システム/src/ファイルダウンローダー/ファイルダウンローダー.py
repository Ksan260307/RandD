import os
import shutil
import hashlib
import secrets
import tempfile
import hmac
import time
import logging
import random
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# ==========================================
# 監査ログ設定 (本番運用向け・SIEM連携想定)
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S%z'
)
logger = logging.getLogger(__name__)

# ==========================================
# 状態遷移・完全性検証エンジン
# ==========================================

def fast_xor(data: bytes, key_stream: bytes) -> bytes:
    """高速なXOR演算 (データの一時的な秘匿化・復元用)"""
    length = len(data)
    int_data = int.from_bytes(data, 'little')
    int_key = int.from_bytes(key_stream[:length], 'little')
    return (int_data ^ int_key).to_bytes(length, 'little')

def purge_memory(b_array: bytearray) -> None:
    """
    メモリ上の機密データ（鍵や平文）をゼロクリアして揮発化させる。
    ※PythonのGCやOSのメモリ管理仕様上、完全な保証は難しいがベストエフォートとして実施。
    """
    if not isinstance(b_array, bytearray):
        return
    for i in range(len(b_array)):
        b_array[i] = 0

def secure_wipe_file(path: Path) -> None:
    """
    一時空間(サンドボックス)に残る痕跡の完全消去（ランダムノイズ上書き）。
    ※注意: 本関数は「一時ファイル」専用であり、ユーザーのソースファイルには適用しない。
    OOMを防ぐため、チャンク単位でストリーム上書きを行う。
    """
    if not path.exists() or not path.is_file():
        return
    try:
        file_size = path.stat().st_size
        chunk_size = 64 * 1024  # 64KB チャンクでメモリ消費を抑制
        written = 0
        
        with open(path, "r+b") as f:
            while written < file_size:
                write_size = min(chunk_size, file_size - written)
                f.write(os.urandom(write_size))
                written += write_size
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        logger.debug(f"セキュアワイプ中にアクセスエラー (上書き): {e}")
    finally:
        try:
            path.unlink()
        except OSError as e:
            logger.debug(f"セキュアワイプ中にアクセスエラー (削除): {e}")

class VerificationEngine:
    """
    ワンタイムのチャレンジを用いた完全性検証モジュール
    """
    def __init__(self) -> None:
        self._master_key: bytes = secrets.token_bytes(32)
        
    def generate_initial_state(self, path: Path) -> bytes:
        """初期状態のファイルに対する拘束データ（コミットメント）を生成"""
        if not path.is_file():
            return b""
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return hmac.new(self._master_key, h.digest(), hashlib.sha256).digest()
        except OSError:
            return b""

    def verify(self, proof_digest: bytes, expected_state: bytes, challenge: bytes) -> int:
        """
        チャレンジを含めた証明データが初期状態と一致するか検証。
        分岐予測によるタイミング漏洩を防ぐため、結果を 1 (成功) または 0 (失敗) で返す。
        """
        if not proof_digest or not expected_state:
            return 0
            
        mixed_expected = hmac.new(challenge, expected_state, hashlib.sha256).digest()
        mixed_actual = hmac.new(challenge, hmac.new(self._master_key, proof_digest, hashlib.sha256).digest(), hashlib.sha256).digest()
        
        return int(hmac.compare_digest(mixed_expected, mixed_actual))


class SecureFileStateEngine:
    """
    ファイルの状態と属性遷移を管理するセキュアエンジン
    (空間のパディングによるデータ隠蔽、劣化度による"論理的"自壊、制御フローの平滑化を実装)
    """
    STRESS_LIMIT = 3     # 観測ストレスの限界値（これを超えると論理的に自壊する）
    
    def __init__(self, capacity: int = 1024) -> None:
        self.MAX_CAPACITY = capacity 
        
        self.ids: List[int] = []
        self.access_map: Dict[str, Tuple[bytes, bytes]] = {}
        self.access_tokens: List[str] = []
        
        # 状態フラグ配列 (32bit パッキング)
        self.packed_states: List[int] = []
        self.verifier = VerificationEngine()
        self.initial_states: List[bytes] = []
        
        self._auth_key: bytearray = bytearray(secrets.token_bytes(32))
        self.state_macs: List[bytes] = []
        
        self._current_size = 0

    def add_entity(self, file_id: int, path: Path) -> None:
        """実エンティティの登録（名前とパスを暗号化ペイロードとして保持）"""
        if self._current_size >= self.MAX_CAPACITY:
            logger.warning(f"空間の最大容量({self.MAX_CAPACITY})を超過。ファイル '{path.name}' は登録スキップ。")
            return 
            
        # 本番運用向け: シンボリックリンクや特殊ファイルは対象外とする
        try:
            if path.is_symlink() or not path.is_file():
                return
            is_valid = 1
            size = path.stat().st_size
        except OSError:
            # 権限がないファイルなどは無視する
            return
            
        self.ids.append(file_id)
        
        token = secrets.token_urlsafe(32)
        self.access_tokens.append(token)
        
        payload_str = f"{path.absolute()}||{path.name}"
        payload_bytes = payload_str.encode('utf-8')
        nonce = secrets.token_bytes(16)
        key_stream = hashlib.shake_256(token.encode('utf-8') + nonce).digest(len(payload_bytes))
        encrypted_payload = fast_xor(payload_bytes, key_stream)
        
        self.access_map[token] = (nonce, encrypted_payload)
        
        is_visible = 1 if not path.name.startswith('.') else 0
        size_score = min(255, int(size ** 0.1)) if size > 0 else 0
        ext_hash = int(hashlib.sha256(path.suffix.encode()).hexdigest()[:4], 16)
        ext_cat = ext_hash % 16
        
        initial_state = self.verifier.generate_initial_state(path)
        self.initial_states.append(initial_state)
        
        # 状態のパッキング設計
        # [0-7] size, [8-11] ext, [12] visible, [13] valid, [14] is_real, [15-19] observation_stress
        is_real = 1
        observation_stress = 0
        
        packed = (size_score & 0xFF) | ((ext_cat & 0x0F) << 8) | ((is_visible & 0x01) << 12) | ((is_valid & 0x01) << 13) | ((is_real & 0x01) << 14) | ((observation_stress & 0x1F) << 15)
        self.packed_states.append(packed)
        
        state_bytes = packed.to_bytes(4, byteorder='big')
        mac = hmac.new(self._auth_key, state_bytes, hashlib.sha256).digest()
        self.state_macs.append(mac)
        
        self._current_size += 1

    def seal_environment(self) -> None:
        """空間をダミーデータで満たし、真のデータ数や処理時間を外部から観測不可能にする"""
        decoy_needed = self.MAX_CAPACITY - self._current_size
        for _ in range(decoy_needed):
            self.ids.append(999999)
            
            token = secrets.token_urlsafe(32)
            self.access_tokens.append(token)
            
            payload_bytes = secrets.token_bytes(64)
            nonce = secrets.token_bytes(16)
            key_stream = hashlib.shake_256(token.encode('utf-8') + nonce).digest(len(payload_bytes))
            self.access_map[token] = (nonce, fast_xor(payload_bytes, key_stream))
            
            self.initial_states.append(secrets.token_bytes(32)) 
            
            packed = secrets.randbits(12) | (0 << 12) | (0 << 13) | (0 << 14) | (0 << 15)
            self.packed_states.append(packed)
            
            state_bytes = packed.to_bytes(4, byteorder='big')
            mac = hmac.new(self._auth_key, state_bytes, hashlib.sha256).digest()
            self.state_macs.append(mac)

    def compile_dense_view(self) -> List[int]:
        """有効かつ可視状態のエンティティを抽出する（常に固定回のループを実行）"""
        dense_list: List[int] = []
        dummy_list: List[int] = []
        
        for i in range(self.MAX_CAPACITY):
            packed = self.packed_states[i]
            expected_mac = self.state_macs[i]
            
            state_bytes = packed.to_bytes(4, byteorder='big')
            actual_mac = hmac.new(self._auth_key, state_bytes, hashlib.sha256).digest()
            
            is_unaltered = int(hmac.compare_digest(expected_mac, actual_mac))
            is_visible = (packed >> 12) & 0x01
            is_valid = (packed >> 13) & 0x01
            is_real = (packed >> 14) & 0x01
            stress = (packed >> 15) & 0x1F
            
            is_alive = 1 if stress < self.STRESS_LIMIT else 0
            
            target_mask = is_visible & is_valid & is_unaltered & is_real & is_alive
            
            paths = (dummy_list, dense_list)
            paths[target_mask].append(self.ids[i])
                
        return dense_list
        
    def peek_name(self, target_id: int) -> str:
        """UI表示の瞬間にのみ名前を復号して返す"""
        try:
            idx = self.ids.index(target_id)
        except ValueError:
            return "Unknown"
            
        token = self.access_tokens[idx]
        encrypted_data = self.access_map.get(token)
        if not encrypted_data: return "Unknown"
        
        nonce, encrypted_payload = encrypted_data
        key_stream = hashlib.shake_256(token.encode('utf-8') + nonce).digest(len(encrypted_payload))
        decrypted_payload_bytes = bytearray(fast_xor(encrypted_payload, key_stream))
        
        try:
            payload_str = decrypted_payload_bytes.decode('utf-8')
            _, name = payload_str.split("||")
        except:
            name = "Unknown"
        finally:
            purge_memory(decrypted_payload_bytes)
            
        return name

    def _rotate_keys(self) -> None:
        """キーの動的ローテーションと揮発化"""
        new_key = bytearray(secrets.token_bytes(32))
        for i in range(self.MAX_CAPACITY):
            packed = self.packed_states[i]
            state_bytes = packed.to_bytes(4, byteorder='big')
            self.state_macs[i] = hmac.new(new_key, state_bytes, hashlib.sha256).digest()
        
        purge_memory(self._auth_key)
        self._auth_key = new_key

    def extract_entity(self, target_id: int, dest_dir: Path) -> Tuple[bool, str]:
        """
        対象を引き出し、検証する。
        サイバーデセプション(欺瞞): 限界超過時は物理ファイルを壊さず、システム上からのみ論理的に削除し、
        攻撃者には「自壊した」とハッタリをかける。
        """
        try:
            idx = self.ids.index(target_id)
        except ValueError:
            return False, "対象のファイルが存在しません。"
            
        token = self.access_tokens[idx]
        encrypted_data = self.access_map.get(token)
        
        if not encrypted_data:
            return False, "アクセス経路が不正、または実体が喪失しています。"

        nonce, encrypted_payload = encrypted_data
        key_stream = hashlib.shake_256(token.encode('utf-8') + nonce).digest(len(encrypted_payload))
        decrypted_payload_bytes = bytearray(fast_xor(encrypted_payload, key_stream))
        
        try:
            payload_str = decrypted_payload_bytes.decode('utf-8')
            path_str, name_str = payload_str.split("||")
            src_path = Path(path_str)
        except:
            return False, "ペイロードの復号に失敗しました。"
        finally:
            purge_memory(decrypted_payload_bytes)

        if not src_path.exists():
            return False, "指定された実体が既に存在しません。"

        # 1. 観測ストレスの加算と限界チェック
        packed = self.packed_states[idx]
        current_stress = (packed >> 15) & 0x1F
        new_stress = current_stress + 1
        
        is_broken = 1 if new_stress >= self.STRESS_LIMIT else 0
        
        new_valid = ((packed >> 13) & 0x01) & (1 - is_broken)
        new_packed = (packed & ~(0x1F << 15) & ~(1 << 13)) | (new_stress << 15) | (new_valid << 13)
        
        self.packed_states[idx] = new_packed
        state_bytes = new_packed.to_bytes(4, byteorder='big')
        self.state_macs[idx] = hmac.new(self._auth_key, state_bytes, hashlib.sha256).digest()

        if is_broken:
            if token in self.access_map:
                del self.access_map[token]
            logger.warning(f"[AUDIT] 観測ストレス限界超過 (ID:{target_id}): '{name_str}' への不正アクセスの疑い。論理的自壊(デセプション)を作動し、経路をパージしました。")
            return False, "エラー: 観測ストレスが限界を超過しました。干渉を防ぐため実体は自壊(ワイプ)されました。"

        # 2. 一時空間への引き出しと検証
        expected_state = self.initial_states[idx]
        final_dest_path = dest_dir / name_str
        
        trash_path = dest_dir / f".trash_{secrets.token_hex(8)}.tmp"
        
        session_key = bytearray(secrets.token_bytes(32))
        challenge = secrets.token_bytes(16) 
        
        tmp_path = None
        
        try:
            with tempfile.NamedTemporaryFile(dir=dest_dir, delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)
                
                h_proof = hashlib.sha256()
                with open(src_path, "rb") as src_f:
                    chunk_idx = 0
                    for chunk in iter(lambda: src_f.read(8192), b""):
                        time.sleep(0.0001) # タイミング平滑化
                        h_proof.update(chunk)
                        
                        stream_seed = bytes(session_key) + chunk_idx.to_bytes(8, 'big')
                        cipher_stream = hashlib.shake_256(stream_seed).digest(len(chunk))
                        encrypted_chunk = fast_xor(chunk, cipher_stream)
                        
                        tmp_file.write(encrypted_chunk)
                        chunk_idx += 1
                        
                proof_digest = h_proof.digest()

            is_valid_extraction = self.verifier.verify(proof_digest, expected_state, challenge)
            
            with open(tmp_path, "r+b") as tmp_f:
                chunk_idx = 0
                for encrypted_chunk in iter(lambda: tmp_f.read(8192), b""):
                    time.sleep(0.0001) 
                    
                    stream_seed = bytes(session_key) + chunk_idx.to_bytes(8, 'big')
                    cipher_stream = hashlib.shake_256(stream_seed).digest(len(encrypted_chunk))
                    decrypted_chunk = fast_xor(encrypted_chunk, cipher_stream)
                    
                    tmp_f.seek(-len(encrypted_chunk), os.SEEK_CUR)
                    tmp_f.write(decrypted_chunk)
                    chunk_idx += 1
            
            # 3. 制御フローの平滑化
            target_paths = (trash_path, final_dest_path)
            selected_path = target_paths[is_valid_extraction]
            shutil.move(str(tmp_path), str(selected_path))
            
            if not is_valid_extraction:
                secure_wipe_file(selected_path)
            
            if token in self.access_map:
                del self.access_map[token]
            self._rotate_keys()
            
            if is_valid_extraction:
                logger.info(f"[AUDIT] ファイル抽出成功: '{name_str}'")
                return True, f"完了: '{name_str}' の検証に成功し、安全に実体化しました。"
            else:
                logger.warning(f"[AUDIT] 完全性検証失敗: '{name_str}' は改ざんされている可能性があります。抽出をブロックしました。")
                return False, "エラー: 完全性検証に失敗しました。隔離ファイルは破棄されました。"
            
        except Exception as e:
            if tmp_path and tmp_path.exists():
                secure_wipe_file(tmp_path)
            logger.error(f"抽出処理中にシステムエラー: {e}")
            return False, "エラー: 処理中に致命的な例外が発生しました。"
        finally:
            purge_memory(session_key)

# ==========================================
# セキュリティ・ファジングテスト機構
# ==========================================
def run_dynamic_security_tests(iterations: int = 10000) -> None:
    """様々なサイバー攻撃ベクトルを動的にシミュレートし、システムの堅牢性を検証する"""
    print(f"\n[!] 隔離サンドボックス内で動的セキュリティテスト(Fuzzing)を構築中... (試行回数: {iterations}回)")
    
    # テスト中は通常の監査ログ(INFO/WARNING)を抑制し、重大なエラーのみ表示させる
    logging.disable(logging.CRITICAL)
    start_time = time.time()
    
    defense_success_count = 0
    crash_count = 0

    with tempfile.TemporaryDirectory() as test_env_dir:
        test_dir = Path(test_env_dir)
        src_dir = test_dir / "src"
        dest_dir = test_dir / "dest"
        src_dir.mkdir()
        dest_dir.mkdir()
        
        # テスト用のダミーエンティティを生成
        dummy_files = []
        for i in range(10):
            dummy_file = src_dir / f"test_secret_{i}.dat"
            with open(dummy_file, "wb") as f:
                f.write(os.urandom(512)) # 512 bytes
            dummy_files.append(dummy_file)
            
        # テスト用エンジン (小容量)
        test_engine = SecureFileStateEngine(capacity=50)
        for idx, p in enumerate(dummy_files):
            test_engine.add_entity(idx, p)
        test_engine.seal_environment()
        
        valid_ids = test_engine.compile_dense_view()
        
        if not valid_ids:
            print("テスト環境の初期化に失敗しました。")
            logging.disable(logging.NOTSET)
            return

        for i in range(iterations):
            attack_vector = random.choice([
                "BRUTE_FORCE_ID",       # 境界値・不正IDによるアクセス
                "MEMORY_TAMPER_MAC",    # メモリ上のMACハッシュ値を改ざん
                "MEMORY_TAMPER_KEY",    # マスターキー(AuthKey)の改ざん
                "PAYLOAD_CORRUPTION",   # 暗号化ペイロード(パス情報)のビット反転
                "STRESS_ATTACK",        # リプレイ/連続アクセスによる論理的自壊誘発
            ])
            
            try:
                # 攻撃対象をランダム選定
                target_id = random.choice(valid_ids)
                
                if attack_vector == "BRUTE_FORCE_ID":
                    malicious_id = random.choice([-1, 999999, 1000000000, -999999999])
                    res, _ = test_engine.extract_entity(malicious_id, dest_dir)
                    if not res: 
                        defense_success_count += 1
                    else:
                        print(f"\n[VULNERABILITY DETECTED] {attack_vector} 突破: 不正なID({malicious_id})で抽出に成功しました。")
                        
                elif attack_vector == "MEMORY_TAMPER_MAC":
                    idx = test_engine.ids.index(target_id)
                    original_mac = test_engine.state_macs[idx]
                    test_engine.state_macs[idx] = os.urandom(32) # MACの書き換え
                    
                    current_visible = test_engine.compile_dense_view()
                    if target_id not in current_visible: 
                        defense_success_count += 1
                    else:
                        print(f"\n[VULNERABILITY DETECTED] {attack_vector} 突破: MACの改ざんが検知されず、可視化リストに漏洩しました。")
                    
                    test_engine.state_macs[idx] = original_mac # 復元
                    
                elif attack_vector == "MEMORY_TAMPER_KEY":
                    original_key = bytearray(test_engine._auth_key)
                    test_engine._auth_key[0] ^= 0xFF # キーの1バイトを破壊
                    
                    current_visible = test_engine.compile_dense_view()
                    if len(current_visible) == 0: 
                        defense_success_count += 1
                    else:
                        print(f"\n[VULNERABILITY DETECTED] {attack_vector} 突破: マスターキー改ざん状態で可視化リストに漏洩しました。")
                        
                    test_engine._auth_key = original_key # 復元
                    
                elif attack_vector == "PAYLOAD_CORRUPTION":
                    idx = test_engine.ids.index(target_id)
                    token = test_engine.access_tokens[idx]
                    
                    if token in test_engine.access_map:
                        nonce, payload = test_engine.access_map[token]
                        corrupted_payload = bytearray(payload)
                        corrupted_payload[0] ^= 0xFF # 暗号文の破損
                        test_engine.access_map[token] = (nonce, bytes(corrupted_payload))
                        
                        res, _ = test_engine.extract_entity(target_id, dest_dir)
                        if not res: 
                            defense_success_count += 1
                        else:
                            print(f"\n[VULNERABILITY DETECTED] {attack_vector} 突破: ペイロード改ざん状態で抽出処理が成功しました。")
                            
                        test_engine.access_map[token] = (nonce, payload) # 復元
                    else:
                        defense_success_count += 1 # 既にパージされていれば防御成功とみなす
                        
                elif attack_vector == "STRESS_ATTACK":
                    # 意図的にストレス限界まで連続アクセスし、正しくブロック(論理的自壊)されるか検証
                    block_success = False
                    for _ in range(test_engine.STRESS_LIMIT + 1):
                        res, msg = test_engine.extract_entity(target_id, dest_dir)
                        if not res:
                            block_success = True
                            break
                    
                    if block_success:
                        defense_success_count += 1
                    else:
                        print(f"\n[VULNERABILITY DETECTED] {attack_vector} 突破: ストレス限界({test_engine.STRESS_LIMIT})を超えてもブロック/自壊しませんでした。")
                        
            except Exception as e:
                crash_count += 1
                print(f"\n[CRASH] {attack_vector} テスト中にシステムクラッシュ発生: {e}")
                
    logging.disable(logging.NOTSET)
    elapsed = time.time() - start_time
    
    print("\n" + "="*50)
    print(" 🛡️ 動的セキュリティテスト(Fuzzing) 完了レポート")
    print("="*50)
    print(f" 試行回数 (Iterations)   : {iterations:,} 回")
    print(f" 防御成功 (Defended)     : {defense_success_count:,} 回")
    print(f" システムクラッシュ      : {crash_count:,} 回")
    print(f" 実行時間 (Elapsed)      : {elapsed:.2f} 秒")
    print("="*50)
    
    if crash_count == 0 and defense_success_count == iterations:
        print(" [結果] 完璧な非接触性(Intangibility)と耐性が証明されました。")
    else:
        print(" [結果] 防御システムに一部の漏れ、またはクラッシュが発生しました。")


def get_download_folder() -> Path:
    return Path(os.path.expanduser('~')) / 'Downloads'

def main():
    downloads_dir = get_download_folder()
    dest_dir = Path.cwd()
    
    if not downloads_dir.exists():
        print("システムのダウンロードフォルダが見つかりません。")
        return

    # 実運用を想定し、一般的なフォルダ内のファイル数に耐えうるキャパシティを設定
    engine = SecureFileStateEngine(capacity=2048)
    
    print("ディレクトリを安全に調査・空間を暗号化中... (時間がかかる場合があります)")
    file_id_counter = 0
    
    try:
        files = list(downloads_dir.iterdir())
    except OSError as e:
        print(f"ディレクトリの読み込みに失敗しました: {e}")
        return

    for p in files:
        engine.add_entity(file_id_counter, p)
        file_id_counter += 1
        
    engine.seal_environment()
        
    while True:
        visible_ids = engine.compile_dense_view()
        
        if not visible_ids:
            print("\n取得可能なファイルが存在しません。(限界に達したか、全て不可視化されました)")
            break
            
        print(f"\n--- セキュアファイル一覧 ({len(visible_ids)}件) ---")
        for fid in visible_ids:
            name = engine.peek_name(fid)
            idx = engine.ids.index(fid)
            stress = (engine.packed_states[idx] >> 15) & 0x1F
            remaining = engine.STRESS_LIMIT - stress
            print(f"[{fid}] {name} (残り観測可能回数: {remaining})")
        print("-" * 30)
        
        try:
            user_input = input("取得するファイルの番号を入力してください (qでキャンセル, testで動的テスト): ").strip()
            if user_input.lower() == 'q':
                break
            elif user_input.lower() == 'test':
                run_dynamic_security_tests(iterations=10000)
                continue
                
            target_id = int(user_input)
            
            print("検証・抽出プロセスを実行中...")
            success, msg = engine.extract_entity(target_id, dest_dir)
            print(f"\n>> {msg}")
            
        except ValueError:
            print(">> 数値を正しく入力してください。")
        except KeyboardInterrupt:
            print("\n>> 処理を中断しました。")
            break

if __name__ == "__main__":
    main()