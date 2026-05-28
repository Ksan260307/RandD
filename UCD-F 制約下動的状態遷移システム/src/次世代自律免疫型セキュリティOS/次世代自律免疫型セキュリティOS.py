import math
import time
import threading
import socket
import select
import logging
import sys

# 監査ログの設定
logging.basicConfig(
    filename='immune_os.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

class Vector2D:
    """攻撃や防衛の力を表す2次元ベクトル"""
    def __init__(self, x=0.0, y=0.0):
        self.x = x
        self.y = y

    def add(self, other):
        self.x += other.x
        self.y += other.y

    def inverse(self):
        """逆行列(逆ベクトル)を生成し、力を反転させる"""
        return Vector2D(-self.x, -self.y)

    def magnitude(self):
        return math.sqrt(self.x**2 + self.y**2)

    def reset(self):
        self.x = 0.0
        self.y = 0.0

class SensorNode:
    """特定のポートを監視するセンサーノード（システムの末梢神経）"""
    def __init__(self, node_id, port):
        self.id = node_id
        self.port = port
        self.socket = None
        
        self.is_active = True
        self.is_quarantined = False
        
        # 動態パラメータ
        self.attack_power = 0.0
        self.system_damage = 0.0     # 接続過多による負荷
        self.stress_potential = 0.0  # 内部歪み（ナブラ演算用）
        self.malicious_vector = Vector2D(0, 0)
        
        self.connections_handled = 0

class AutonomousImmuneOS:
    def __init__(self, ports_to_monitor):
        self.nodes = []
        self.blacklist_ips = set()
        self.is_running = True
        self.monitor_threads = []
        
        # 自律神経（修復ループ）スレッド
        self.healing_thread = threading.Thread(target=self._healing_loop, daemon=True)
        
        self._initialize_sensors(ports_to_monitor)
        
    def _initialize_sensors(self, ports):
        for i, port in enumerate(ports):
            node = SensorNode(i, port)
            self.nodes.append(node)
            # 各ポートごとに監視スレッドを立ち上げる
            t = threading.Thread(target=self._monitor_port, args=(node,), daemon=True)
            self.monitor_threads.append(t)

    def start(self):
        """OSのコアシステムと監視神経を起動"""
        logging.info("Mats-OS: Autonomous Immune System Starting...")
        print("[*] 自律免疫システムを起動しています...")
        for t in self.monitor_threads:
            t.start()
        self.healing_thread.start()
        print("[+] 全センサーノードの稼働を確認しました。")

    def shutdown(self):
        """システムを安全に停止"""
        self.is_running = False
        print("\n[*] 監視ソケットをシャットダウンしています...")
        for node in self.nodes:
            if node.socket:
                try:
                    node.socket.close()
                except:
                    pass
        logging.info("Mats-OS: System Shutdown Safely.")

    def _monitor_port(self, node):
        """特定のポートを監視し、異常なベクトル（接続）を検知する"""
        try:
            node.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 再起動時のポートバインドエラーを防ぐ
            node.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            node.socket.bind(('0.0.0.0', node.port))
            node.socket.listen(5)
            node.socket.settimeout(1.0) # 1秒ごとにブロックを解除して終了フラグを確認
        except Exception as e:
            msg = f"ノード {node.id} (Port {node.port}) のバインドに失敗: {e}"
            print(f"\n[!] {msg}")
            logging.error(msg)
            node.is_quarantined = True
            return

        while self.is_running and not node.is_quarantined:
            try:
                conn, addr = node.socket.accept()
                ip = addr[0]
                node.connections_handled += 1
                
                # 攻撃ベクトルの生成 (x: データ量/ポート番号ベース, y: アクセス頻度)
                attack_vec = Vector2D(node.port * 0.01, 10.0)
                node.malicious_vector.add(attack_vec)
                node.attack_power = node.malicious_vector.magnitude()
                
                if ip in self.blacklist_ips:
                    # すでに隔離済みのベクトルは即座に破棄（物理的な防壁化）
                    conn.close()
                    node.malicious_vector.reset()
                    node.attack_power = 0.0
                    continue

                msg = f"検知: ノード {node.id} (Port {node.port}) への不正アクセス IP: {ip}"
                logging.warning(msg)
                print(f"\n[!] {msg}")
                
                self._neutralize_threat(node, conn, ip)

            except socket.timeout:
                continue # タイムアウトは正常動作（ループを回すため）
            except Exception as e:
                if self.is_running:
                    logging.error(f"ノード {node.id} 監視エラー: {e}")

    def _neutralize_threat(self, node, conn, ip):
        """逆行列（逆ベクトル）の概念を適用し、接続を即座に切断・隔離する"""
        # 1. 逆ベクトル生成による中和（接続の即時切断）
        antibody_vector = node.malicious_vector.inverse()
        node.malicious_vector.add(antibody_vector) # ベクトル和を0にする
        
        try:
            conn.close()
        except:
            pass

        # 2. 攻撃元IPを空間から排除（ブラックリスト化）
        self.blacklist_ips.add(ip)
        
        # 3. 余波（内部歪み）の蓄積
        node.stress_potential += node.attack_power * 0.2
        node.system_damage += 1.0
        node.attack_power = 0.0
        
        logging.info(f"中和成功: IP {ip} をブラックリストに追加し、ベクトルを相殺しました。")
        print(f"[+] 防衛成功: IP {ip} を隔離。逆ベクトルにより攻撃を無効化しました。")

        # 限界を超えたらポートを閉じる（完全隔離）
        if node.system_damage >= 20.0:
            node.is_quarantined = True
            node.socket.close()
            msg = f"致命的エラー: ノード {node.id} (Port {node.port}) を完全隔離（ネットワークから切り離し）しました。"
            logging.critical(msg)
            print(f"\n[!] {msg}")

    def _healing_loop(self):
        """バックグラウンドで常に実行される自律修復（ナブラ演算）ループ"""
        while self.is_running:
            time.sleep(5.0) # 5秒ごとにシステム全体の歪みを評価
            
            active_nodes = [n for n in self.nodes if n.is_active and not n.is_quarantined]
            if not active_nodes:
                continue

            stress_diff = {n.id: 0.0 for n in active_nodes}
            total_stress = sum(n.stress_potential for n in active_nodes)

            # システム全体の歪みが存在する場合、ナブラ演算(∇・F)で負荷を分散
            if total_stress > 0.5:
                for node in active_nodes:
                    if node.stress_potential > 0:
                        # 自然治癒力
                        node.stress_potential *= 0.8
                        node.system_damage = max(0, node.system_damage - 0.5)
                        
                        # 隣接ノード（ここでは他のポート）への負荷の平滑化
                        neighbors = [other for other in active_nodes if other.id != node.id]
                        if neighbors:
                            distribution = (node.stress_potential * 0.1) / len(neighbors)
                            for neighbor in neighbors:
                                stress_diff[neighbor.id] += distribution
                            stress_diff[node.id] -= (distribution * len(neighbors))

                for node in active_nodes:
                    node.stress_potential = max(0.0, node.stress_potential + stress_diff[node.id])
                
                logging.info(f"自律修復: 幾何微積分(∇)演算により内部歪みを平滑化しました。")

    def print_status(self):
        print("\n=== Mats-OS 稼働ステータス ===")
        print(f"ブラックリスト登録IP数: {len(self.blacklist_ips)}")
        print("---------------------------------------------------------")
        print("ID | Port  | 状態   | 処理件数 | 疲労度 | 内部歪み(∇ポテンシャル)")
        print("---------------------------------------------------------")
        for node in self.nodes:
            state = "隔離済" if node.is_quarantined else "監視中"
            print(f"{node.id:2d} | {node.port:5d} | {state:4s} | {node.connections_handled:8d} | {node.system_damage:6.1f} | {node.stress_potential:8.2f}")
        print("---------------------------------------------------------\n")


def main():
    print("==================================================")
    print(" Mats-OS (自律免疫型セキュリティ) - 稼働モード ")
    print("==================================================")
    
    # ハニーポットとして監視するポート群（権限不要のハイポートをデフォルト設定）
    monitor_ports = [8080, 22222, 33890, 50000]
    
    system = AutonomousImmuneOS(monitor_ports)
    system.start()
    
    print("\nシステムはバックグラウンドでネットワークを監視しています。")
    print("コマンド: status (状態確認), clear (画面クリア), exit (終了)")
    print("※別のターミナルから `telnet localhost 8080` 等でアクセスすると防衛反応を確認できます。\n")

    try:
        while True:
            # ユーザーからのコマンド入力
            command = input("Mats-OS> ").strip().lower()
            if not command:
                continue
                
            if command == "exit" or command == "quit":
                break
            elif command == "status":
                system.print_status()
            elif command == "clear":
                # 簡易的な画面クリア
                print("\n" * 50)
            else:
                print("不明なコマンドです。利用可能: status, clear, exit")
                
    except KeyboardInterrupt:
        # Ctrl+C が押された場合の処理
        print("\n[!] KeyboardInterrupt (Ctrl+C) を検知しました。")
    finally:
        # 必ずクリーンアップを実行
        system.shutdown()
        print("システムを終了しました。")
        sys.exit(0)

if __name__ == "__main__":
    main()