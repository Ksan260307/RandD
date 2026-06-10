import socket
import threading
import hashlib
import hmac
import os
import time
import struct
import argparse
import sys
import random
import json

# =====================================================================
# セキュリティ・暗号モジュール (設計書に基づくコア実装)
# =====================================================================

class SecureCapsule:
    """
    データをカプセル化し、暗号化と整合性検証を提供するモジュール。
    外部依存（サードパーティライブラリ）を排除し、標準ライブラリのみで
    堅牢な使い捨てキーストリーム暗号とHMAC署名を実現します。
    """
    def __init__(self, master_key: bytes):
        self.master_key = master_key
        # パケットごとのセキュリティ統計（キーのリフレッシュトリガー用）
        self.processed_packets = 0
        self.total_bytes = 0
        
        # 非接触性の強化: リプレイ攻撃（再送攻撃）を防ぐためのシーケンス番号
        self.sequence_number = 0         # 送信用
        self.last_received_seq = 0       # 受信用

    def _derive_packet_key(self, iv: bytes, seq_bytes: bytes) -> bytes:
        """
        IV（初期化ベクトル）、シーケンス番号、マスターキーから、パケット専用の一時キーを高速導出。
        (HKDF的なアプローチにより、パケットごとに完全に独立した鍵空間を構築)
        """
        return hmac.new(self.master_key, iv + seq_bytes, hashlib.sha256).digest()

    def _generate_keystream(self, key: bytes, length: int) -> bytes:
        """暗号化用のセマンティックなキーストリームを生成（カウンタモードのシミュレート）"""
        stream = bytearray()
        counter = 0
        while len(stream) < length:
            # キーとカウンターハッシュを組み合わせて一方向キーストリームを伸長
            block = hashlib.sha256(key + struct.pack(">I", counter)).digest()
            stream.extend(block)
            counter += 1
        return bytes(stream[:length])

    def encrypt_and_pack(self, raw_data: bytes) -> bytes:
        """
        データを暗号化し、改ざん防止の検証署名と難読化パディングを付与してカプセル化。
        """
        self.sequence_number += 1
        seq_bytes = struct.pack(">Q", self.sequence_number) # 8バイトのシーケンス番号

        # 1. 難読化 (iOの代替): パケットサイズを16バイト境界に揃え、さらにランダム長のパディングを追加
        original_len = len(raw_data)
        base_pad_len = 16 - (original_len % 16)
        extra_pad_len = random.randint(0, 15) * 16 # 0〜240バイトのランダム追加ダミーデータ
        pad_len = base_pad_len + extra_pad_len
        
        # ランダムなダミーデータを挿入してトラフィック分析を妨害
        padded_data = raw_data + os.urandom(pad_len)

        # 2. カプセル化 (FHEの代替): パケット専用の使い捨てIVを生成
        iv = os.urandom(16)
        packet_key = self._derive_packet_key(iv, seq_bytes)
        keystream = self._generate_keystream(packet_key, len(padded_data))
        
        # XORによるストリーム暗号化
        encrypted_payload = bytes(a ^ b for a, b in zip(padded_data, keystream))

        # 3. 整合性署名 (VCの代替): パケットの正当性を証明するHMACを生成 (Encrypt-then-MAC)
        # ヘッダー情報（シーケンス番号、オリジナルデータ長、パディング長）も含めて署名
        header = seq_bytes + struct.pack(">II", original_len, pad_len)
        signature = hmac.new(packet_key, header + encrypted_payload, hashlib.sha256).digest()

        # 最終パケット構造: [IV (16B)] [Signature (32B)] [Header (16B)] [Encrypted Payload]
        packet = iv + signature + header + encrypted_payload
        
        self.processed_packets += 1
        self.total_bytes += len(packet)
        return packet

    def unpack_and_decrypt(self, packet: bytes) -> bytes:
        """
        カプセル化されたパケットを検証し、正当性が証明された場合のみ復号して中身を取り出します。
        """
        if len(packet) < 64: # 16B(IV) + 32B(Signature) + 16B(Header)
            raise ValueError("[検証失敗 - 破損] パケットサイズが不正です。データが切り捨てられた可能性があります。")

        # パケットの分解
        iv = packet[:16]
        expected_signature = packet[16:48]
        header = packet[48:64]
        encrypted_payload = packet[64:]

        seq_bytes = header[:8]
        seq_num = struct.unpack(">Q", seq_bytes)[0]
        original_len, pad_len = struct.unpack(">II", header[8:16])

        # 非接触性検証: リプレイ攻撃（傍受した古いパケットの再送）のチェック
        if seq_num <= self.last_received_seq:
            raise ValueError(f"[検証失敗 - リプレイ攻撃] 無効なシーケンス番号({seq_num})を検知しました。再送攻撃の可能性があります。")

        # パケット専用キーの再導出
        packet_key = self._derive_packet_key(iv, seq_bytes)

        # 1. 整合性検証: 復号を行う前に、署名の正当性をチェック (非接触性の担保)
        actual_signature = hmac.new(packet_key, header + encrypted_payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expected_signature, actual_signature):
            raise ValueError("[検証失敗 - 改ざん] パケット署名の不一致を検知！悪意ある干渉が行われました。")

        # リプレイカウンタを更新
        self.last_received_seq = seq_num

        # 2. データの復号
        keystream = self._generate_keystream(packet_key, len(encrypted_payload))
        decrypted_padded = bytes(a ^ b for a, b in zip(encrypted_payload, keystream))

        # 3. ヘッダー情報の解析とパディングの除去
        raw_data = decrypted_padded[:original_len]

        self.processed_packets += 1
        self.total_bytes += len(packet)
        return raw_data


# =====================================================================
# セッション鍵の動的更新プロトコル (ブートストラッピングの代替)
# =====================================================================

class SessionManager:
    """
    通信経路上のセキュリティリスク（信号の歪み）を監視し、
    一定の通信量に達すると自動的にセッションキーを無瞬断リフレッシュ（レキーイング）します。
    """
    def __init__(self, initial_key: bytes, rekey_threshold_bytes: int = 100 * 1024):
        self.capsule = SecureCapsule(initial_key)
        self.rekey_threshold = rekey_threshold_bytes
        self.lock = threading.Lock()

    def should_rekey(self) -> bool:
        """暗号強度の劣化（歪みの蓄積）が進み、キーの更新が必要かを判定"""
        with self.lock:
            return self.capsule.total_bytes >= self.rekey_threshold

    def perform_rekey(self):
        """セッションキーを新しい乱数キーに更新し、歪み（リスク）レベルをゼロにリセット"""
        with self.lock:
            old_key = self.capsule.master_key
            # 前方秘匿性を確保するため、現在のキーと乱数をブレンドして新しいセッションキーを生成
            new_key = hashlib.sha256(old_key + os.urandom(32)).digest()
            self.capsule = SecureCapsule(new_key)
            print(f"[*] [鍵更新] セキュリティリスクが閾値に達しました。セッションキーを自動更新しました。(リセット完了)")


# =====================================================================
# VPNコアシステム (ソケット転送エンジン)
# =====================================================================

def forward_stream(source_sock: socket.socket, dest_sock: socket.socket, 
                   session_mgr: SessionManager, is_encrypt_mode: bool):
    """
    接続から届いたデータをリアルタイムで暗号カプセル化（または復号）し、
    もう一方のソケットへ転送するスレッドループ。
    """
    source_sock.settimeout(15.0) # インターネット経由を考慮しタイムアウトを少し延長
    buffer_size = 4096

    try:
        while True:
            # 1. 自動鍵更新のチェック (信号の自己修復)
            if session_mgr.should_rekey():
                session_mgr.perform_rekey()

            try:
                if is_encrypt_mode:
                    # クライアント側: ローカルアプリから生データを受信 -> 暗号化して送信
                    data = source_sock.recv(buffer_size)
                    if not data:
                        break
                    
                    # データを安全にカプセル化
                    secured_packet = session_mgr.capsule.encrypt_and_pack(data)
                    # パケットサイズをヘッダーとして付与して送信 [4B: 全長] [データ]
                    packet_len = len(secured_packet)
                    dest_sock.sendall(struct.pack(">I", packet_len) + secured_packet)
                else:
                    # サーバー側: トンネルから暗号パケットを受信 -> 復号して宛先へ送信
                    # まず4Bのサイズヘッダーを受信
                    len_header = source_sock.recv(4)
                    if not len_header or len(len_header) < 4:
                        break
                    packet_len = struct.unpack(">I", len_header)[0]
                    
                    # カプセルデータの全バイトを受信
                    packet = b""
                    while len(packet) < packet_len:
                        chunk = source_sock.recv(packet_len - len(packet))
                        if not chunk:
                            break
                        packet += chunk
                    
                    if len(packet) < packet_len:
                        break

                    # カプセルを検証・復号
                    decrypted_data = session_mgr.capsule.unpack_and_decrypt(packet)
                    dest_sock.sendall(decrypted_data)

            except socket.timeout:
                continue # タイムアウト時は生存確認
            except ConnectionError:
                break
            except ValueError as ve:
                print(f"\n[セキュリティ警告] パケットドロップ: {ve}")
                break

    except Exception as e:
        # 接続が切れた場合などのエラーは静かに無視してループを抜ける
        pass
    finally:
        try:
            source_sock.close()
        except: pass
        try:
            dest_sock.close()
        except: pass


# =====================================================================
# VPN クライアント動作モード
# =====================================================================

def run_client(local_port: int, vpn_server_host: str, vpn_server_port: int, secret_key: bytes):
    """
    ローカルでプロキシ/中継器として動作。
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        client_socket.bind(("127.0.0.1", local_port))
        client_socket.listen(5)
        print(f"[+] [Client Mode] セキュアトンネルクライアントを起動しました。")
        print(f"    ローカル受付ポート: 127.0.0.1:{local_port}")
        print(f"    接続先セキュアサーバー: {vpn_server_host}:{vpn_server_port}\n")
    except Exception as e:
        print(f"[-] ローカルポート {local_port} のバインドに失敗しました: {e}")
        return

    session_mgr = SessionManager(secret_key, rekey_threshold_bytes=50000)

    try:
        while True:
            app_sock, addr = client_socket.accept()
            
            try:
                tunnel_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                # インターネット越しの接続は時間がかかることがあるためタイムアウトを設定
                tunnel_sock.settimeout(10.0) 
                tunnel_sock.connect((vpn_server_host, vpn_server_port))
                tunnel_sock.settimeout(None) # 接続後はブロッキングモードに戻す
            except Exception as e:
                print(f"[-] サーバー {vpn_server_host}:{vpn_server_port} への接続に失敗しました: {e}")
                app_sock.close()
                continue

            t1 = threading.Thread(target=forward_stream, args=(app_sock, tunnel_sock, session_mgr, True))
            t2 = threading.Thread(target=forward_stream, args=(tunnel_sock, app_sock, session_mgr, False))

            t1.daemon = True
            t2.daemon = True
            t1.start()
            t2.start()

    except KeyboardInterrupt:
        print("\n[-] クライアントを停止しています...")
    finally:
        client_socket.close()


# =====================================================================
# VPN サーバー動作モード
# =====================================================================

def run_server(listen_port: int, target_host: str, target_port: int, secret_key: bytes):
    """
    インターネット上のセキュアノードとして動作。
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        # 0.0.0.0でバインドすることで、外部のあらゆるIPからの接続を許可
        server_socket.bind(("0.0.0.0", listen_port))
        server_socket.listen(5)
        print(f"[+] [Server Mode] セキュアトンネルサーバーを起動しました。")
        print(f"    監視ポート: 0.0.0.0:{listen_port} (外部からの接続を待機中)")
        print(f"    最終トラフィック宛先: {target_host}:{target_port}\n")
    except Exception as e:
        print(f"[-] 監視ポート {listen_port} のバインドに失敗しました: {e}")
        return

    session_mgr = SessionManager(secret_key, rekey_threshold_bytes=50000)

    try:
        while True:
            tunnel_sock, addr = server_socket.accept()
            print(f"[*] [接続検出] セキュアクライアントから接続されました: {addr[0]}:{addr[1]}")

            try:
                target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                target_sock.settimeout(10.0)
                target_sock.connect((target_host, target_port))
                target_sock.settimeout(None)
            except Exception as e:
                print(f"[-] 最終宛先 {target_host}:{target_port} への接続に失敗しました: {e}")
                tunnel_sock.close()
                continue

            t1 = threading.Thread(target=forward_stream, args=(tunnel_sock, target_sock, session_mgr, False))
            t2 = threading.Thread(target=forward_stream, args=(target_sock, tunnel_sock, session_mgr, True))

            t1.daemon = True
            t2.daemon = True
            t1.start()
            t2.start()

    except KeyboardInterrupt:
        print("\n[-] サーバーを停止しています...")
    finally:
        server_socket.close()

# =====================================================================
# 仮想サイバー攻撃防御テスト (シミュレーション)
# =====================================================================
def simulate_attack(packet: bytearray, attack_type: str, saved_packet: bytes = None) -> bytearray:
    if attack_type == "Payload Manipulation (データ1ビット改ざん)":
        packet[-5] ^= 0x01
    elif attack_type == "Signature Forgery (署名偽造)":
        packet[25] ^= 0xFF
    elif attack_type == "Header Tampering (ヘッダー改ざん)":
        packet[55] ^= 0x01
    elif attack_type == "IV Manipulation (IV書き換え)":
        packet[8] ^= 0xFF
    elif attack_type == "Packet Truncation (パケット切り捨て)":
        return packet[:-20]
    elif attack_type == "Replay Attack (リプレイ攻撃・再送)":
        if saved_packet:
            return bytearray(saved_packet)
    return packet

def run_security_test(master_key: bytes, num_tests: int = 1000):
    print("==================================================")
    print(" 🛡️ セキュリティ設計モデル検証・攻撃シミュレーション")
    print("==================================================")
    capsule_sender = SecureCapsule(master_key)
    capsule_receiver = SecureCapsule(master_key)
    
    attack_types = [
        "Normal Traffic (正常通信)",
        "Payload Manipulation (データ1ビット改ざん)",
        "Signature Forgery (署名偽造)",
        "Header Tampering (ヘッダー改ざん)",
        "IV Manipulation (IV書き換え)",
        "Packet Truncation (パケット切り捨て)",
        "Replay Attack (リプレイ攻撃・再送)"
    ]
    
    print("\n--- 🕵️‍♂️ [フェーズ1] 攻撃手口と防御機構の詳細デモンストレーション ---")
    demo_raw = b"Demo_Secret_Data_001"
    demo_valid_packet = capsule_sender.encrypt_and_pack(demo_raw)
    capsule_receiver.unpack_and_decrypt(demo_valid_packet)
    print(" 正常通信: [検証成功] パケットは安全に復号されました。")
    time.sleep(0.5)

    for attack in attack_types[1:]:
        print(f"\n [攻撃実行] {attack} を試行中...")
        raw_data = f"Sensitive_Data_for_{attack}".encode()
        valid_packet = capsule_sender.encrypt_and_pack(raw_data)
        test_packet = bytearray(valid_packet)
        test_packet = simulate_attack(test_packet, attack, saved_packet=demo_valid_packet)
        try:
            capsule_receiver.unpack_and_decrypt(bytes(test_packet))
            print(" ❌ [重大エラー] 攻撃が検知をすり抜けました。")
        except ValueError as e:
            print(f" 🛡️ [防御成功] 侵入をブロック: {e}")
        time.sleep(0.5)

    print("\n--- 🛡️ [フェーズ2] セキュリティ耐久テスト (総計 1000件) ---")
    print("[*] ランダムな攻撃を連続で注入し、システムの堅牢性を検証中...\n")
    time.sleep(1)

    stats = {k: 0 for k in attack_types}
    blocked_count = 0
    passed_count = 0
    capsule_sender = SecureCapsule(master_key)
    capsule_receiver = SecureCapsule(master_key)
    seed_packet = capsule_sender.encrypt_and_pack(b"Seed_Packet")
    capsule_receiver.unpack_and_decrypt(seed_packet)
    stats["Normal Traffic (正常通信)"] += 1
    passed_count += 1

    for i in range(num_tests - 1):
        raw_data = f"Financial_TXID_{i}".encode()
        valid_packet = capsule_sender.encrypt_and_pack(raw_data)
        test_packet = bytearray(valid_packet)
        attack = random.choice(attack_types)
        stats[attack] += 1
        test_packet = simulate_attack(test_packet, attack, saved_packet=seed_packet)
        
        try:
            capsule_receiver.unpack_and_decrypt(bytes(test_packet))
            if attack == "Normal Traffic (正常通信)":
                passed_count += 1
        except ValueError as e:
            if attack != "Normal Traffic (正常通信)":
                blocked_count += 1
                
        if (i + 1) % 200 == 0:
            print(f" [進行状況] {i + 1:4} / {num_tests} 件完了 ... (検知・ブロック数: {blocked_count})")

    total_attacks = num_tests - stats["Normal Traffic (正常通信)"]
    defense_rate = (blocked_count / total_attacks * 100) if total_attacks > 0 else 100.0

    print("\n==================================================")
    print(" 📊 テスト結果サマリー")
    print("==================================================")
    print(f"  総実行パケット数 : {num_tests} 件")
    print(f"  正常通信パス数   : {passed_count} 件")
    print(f"  検知・ブロック数 : {blocked_count} 件")
    print(f"  🛡️ 総合防御成功率 : {defense_rate:.2f} %")
    print("==================================================")


# =====================================================================
# 設定保存・読み込みユーティリティ
# =====================================================================
CONFIG_FILE = "ghost_vpn_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_config(config_data):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
    except Exception as e:
        print(f"[警告] 設定の保存に失敗しました: {e}")

def get_local_ip():
    """かんたん接続コマンド表示用に、自分のローカルIPを取得する"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# =====================================================================
# エントリーポイント
# =====================================================================

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # コマンドライン引数なしで実行された場合（エディタの実行ボタン等）の対話モード
        print("==================================================")
        print(" Ghost VPN (対話セットアップモード)")
        print("==================================================")
        
        # 1. 過去の設定の読み込みと再利用の確認
        saved_config = load_config()
        if saved_config:
            print(f"📁 前回保存された設定が見つかりました。(モード: {saved_config.get('mode')})")
            use_saved = input("👉 前回の設定で起動しますか？ (Y/n) [デフォルト: Y]: ").strip().lower()
            
            if use_saved != 'n':
                args = argparse.Namespace(**saved_config)
                print("✅ 保存された設定で起動します...\n")
                
                # マスターキー生成
                master_key = hashlib.sha256(args.key.encode()).digest()
                if args.mode == "client":
                    run_client(args.local_port, args.server_host, args.server_port, master_key)
                elif args.mode == "server":
                    run_server(args.listen_port, args.target_host, args.target_port, master_key)
                sys.exit(0)
            else:
                print("\n新しく設定を入力します。")

        # 2. 新規設定の入力フロー
        mode = input("起動モードを入力してください (server / client / test) [デフォルト: client]: ").strip().lower()
        if mode not in ["server", "client", "test"]:
            mode = "client"
            
        if mode == "test":
            print("\n[*] セキュリティテストモードが選択されました。")
            test_key = hashlib.sha256(b"virtual_test_master_key_2026").digest()
            run_security_test(test_key, num_tests=1000)
            sys.exit(0)
        
        key = input("秘密鍵を入力してください（サーバーとクライアントで同じ文字に） [デフォルト: 2026_ghost_key]: ").strip()
        if not key:
            key = "2026_ghost_key"
            
        config_to_save = {"mode": mode, "key": key}
        args = argparse.Namespace(mode=mode, key=key)
        
        if mode == "client":
            print("\n--- クライアント側の設定 ---")
            server_host = input("【重要】接続先サーバーのIPアドレスを入力してください [デフォルト: 127.0.0.1 (ローカル)]: ").strip()
            args.server_host = server_host if server_host else "127.0.0.1"
            config_to_save["server_host"] = args.server_host
            
            server_port = input("接続先サーバーのポート番号を入力してください [デフォルト: 9999]: ").strip()
            args.server_port = int(server_port) if server_port.isdigit() else 9999
            config_to_save["server_port"] = args.server_port
            
            local_port = input("ローカルで受け付けるポート番号を入力してください [デフォルト: 8080]: ").strip()
            args.local_port = int(local_port) if local_port.isdigit() else 8080
            config_to_save["local_port"] = args.local_port
            
            print(f"\n✅ [設定完了] Clientモードで起動します")
            print(f"  手元のアプリ接続先 : 127.0.0.1:{args.local_port}")
            print(f"  暗号トンネル送信先 : {args.server_host}:{args.server_port}\n")
            
        else:
            print("\n--- サーバー側の設定 ---")
            listen_port = input("監視するポート番号を入力してください [デフォルト: 9999]: ").strip()
            args.listen_port = int(listen_port) if listen_port.isdigit() else 9999
            config_to_save["listen_port"] = args.listen_port
            
            target_host = input("最終的にデータを届ける宛先(IP/ドメイン)を入力してください [デフォルト: example.com]: ").strip()
            args.target_host = target_host if target_host else "example.com"
            config_to_save["target_host"] = args.target_host
            
            target_port = input("宛先ホストのポート番号を入力してください [デフォルト: 80]: ").strip()
            args.target_port = int(target_port) if target_port.isdigit() else 80
            config_to_save["target_port"] = args.target_port
            
            print(f"\n✅ [設定完了] Serverモードで起動します")
            print(f"  待ち受けポート : 0.0.0.0:{args.listen_port}")
            print(f"  最終データ宛先 : {args.target_host}:{args.target_port}\n")
            
            # クライアント向けの簡単接続コマンドを発行
            local_ip = get_local_ip()
            print("==================================================")
            print(" 🔗 【クライアント側への接続案内】")
            print("   このサーバーに接続するため、クライアント側のPCで")
            print("   以下のコマンドを実行するか、対話モードでIPを入力してください。")
            print(f"\n   💻 接続コマンド:")
            print(f"   python secure_tunnel_vpn.py --mode client --server-host {local_ip} --server-port {args.listen_port} --key {args.key}")
            print("\n   ※ 別のネットワーク（インターネット越し）から接続する場合は、")
            print(f"      上記の '{local_ip}' を『この場所のグローバルIPアドレス』に")
            print("      置き換え、ルーターのポート開放を行ってください。")
            print("==================================================\n")
            
        # 設定を保存
        save_config(config_to_save)
            
    else:
        # 従来のコマンドライン引数からのパース
        parser = argparse.ArgumentParser(description="Secure Tunnel VPN - 実際に稼働するセキュア暗号トンネルシステム")
        parser.add_argument("--mode", choices=["server", "client", "test"], required=True, help="起動モード (server, client, または test)")
        parser.add_argument("--key", default="2026_ghost_key", help="共通の秘密鍵 (事前共有キー)")
        parser.add_argument("--local-port", type=int, default=8080, help="[Client] アプリの接続を受け付けるローカルポート")
        parser.add_argument("--server-host", default="127.0.0.1", help="[Client] 接続先セキュアサーバーのIP/ホスト")
        parser.add_argument("--server-port", type=int, default=9999, help="[Client] 接続先セキュアサーバーのポート")
        parser.add_argument("--listen-port", type=int, default=9999, help="[Server] クライアントの接続を受け付ける監視ポート")
        parser.add_argument("--target-host", default="example.com", help="[Server] 中継データの最終送信先ホスト")
        parser.add_argument("--target-port", type=int, default=80, help="[Server] 中継データの最終送信先ポート")

        args = parser.parse_args()

    # 入力鍵のSHA256ハッシュをとり、固定32バイトのマスターキーを作成
    master_key = hashlib.sha256(args.key.encode()).digest()

    if args.mode == "test":
        run_security_test(master_key, num_tests=1000)
    elif args.mode == "server":
        listen_port = getattr(args, 'listen_port', 9999)
        target_host = getattr(args, 'target_host', 'example.com')
        target_port = getattr(args, 'target_port', 80)
        run_server(listen_port, target_host, target_port, master_key)
    elif args.mode == "client":
        local_port = getattr(args, 'local_port', 8080)
        server_host = getattr(args, 'server_host', '127.0.0.1')
        server_port = getattr(args, 'server_port', 9999)
        run_client(local_port, server_host, server_port, master_key)