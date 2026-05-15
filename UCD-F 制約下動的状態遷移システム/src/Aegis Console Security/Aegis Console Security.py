import numpy as np
import time
import socket
import threading
import math
import hashlib
import os
from typing import Dict, Set

# ==========================================
# CUI表示用カラーコード
# ==========================================
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'

# ==========================================
# 内部ロジック用定数 (AAIMA / Py_UCD-F_ABC 仕様)
# ==========================================
TAU_PHI = 0.5           # 個を維持するための最小統合情報量 (Axiom: Exclusion)
THETA_AYT = 0.8         # 許容プローブ閾値 (カルバック・ライブラー情報量の推定上限)
TAU_CRITICAL = 0.2      # 自己崩壊検知のクリティカル閾値 (Phase Transition)
MAX_SAFE_PAYLOAD = 1024 # 安全とみなす最大ペイロードサイズ(Byte)

class ResponseStatus:
    SAFE_HEARTBEAT = "SAFE_HEARTBEAT"
    ASSIMILATION_THREAT = "ASSIMILATION_THREAT"
    SYBIL_THREAT = "SYBIL_THREAT"
    COMPROMISED = "COMPROMISED"

# ==========================================
# データモデル (32bit Bit-packed SoA & VIF Dynamics)
# ==========================================
class SecurityAgent:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.did = f"did:local:{agent_id}"  
        
        # IIT (統合情報理論) パラメータ
        self.phi = 1.0                           
        self.internal_state_seed = os.urandom(16) # 秘匿されたMICS(因果構造)シード
        
        # Py_UCD-F_ABC: VIFパラメータ
        self.vA = 3; self.vB = 3; self.vC = 3  # Velocity (ABC強度, 0-3)
        self.dA = 0; self.dB = 0; self.dC = 0  # Intensity (変動Δ, -32 to 31)
        self.is_active = True                  # State Flag (True: 実体, False: 確率雲/Zero-Lock)
        self.ruin_score = 0                    # Fatigue (累積破綻値, 0-7)
        
        self.bit_packed_abc = np.uint32(0)
        self._update_bit_packing()

    def _pack_6bit_signed(self, value: int) -> int:
        """6bitの符号付き整数をパッキング用に変換"""
        val = max(-32, min(31, int(value)))
        if val < 0:
            val = (1 << 6) + val
        return val & 0x3F

    def _update_bit_packing(self):
        """Py_UCD-F_ABC 仕様に基づく32bit完全ビットパッキング"""
        packed = np.uint32(0)
        
        # [0-1] vA, [2-3] vB, [4-5] vC : 強度 (各2bit)
        packed |= np.uint32(self.vA & 0x03)
        packed |= np.uint32(self.vB & 0x03) << 2
        packed |= np.uint32(self.vC & 0x03) << 4
        
        # [6-11] dA, [12-17] dB, [18-23] dC : 変動Δ (各6bit 符号付)
        packed |= np.uint32(self._pack_6bit_signed(self.dA)) << 6
        packed |= np.uint32(self._pack_6bit_signed(self.dB)) << 12
        packed |= np.uint32(self._pack_6bit_signed(self.dC)) << 18
        
        # [24-26] State フラグ (3bit: 1=Active, 0=Probability Cloud/Zero-Lock)
        state_flag = 1 if self.is_active else 0
        packed |= np.uint32(state_flag & 0x07) << 24
        
        # [27-29] RuinScore 累積破綻値 (3bit)
        packed |= np.uint32(self.ruin_score & 0x07) << 27
        
        # [30-31] Reserve (2bit) - 未使用
        self.bit_packed_abc = packed

    def generate_zkp_token(self) -> bytes:
        """内部状態を秘匿したまま存在を証明する Zero-Knowledge Proof トークンの生成"""
        nonce = os.urandom(8).hex()
        # 自身のDID、秘匿シード、ナンスからハッシュを生成し、リプレイ攻撃を防ぐ
        proof_payload = f"{self.did}:{self.internal_state_seed.hex()}:{nonce}:{self.phi > TAU_PHI}".encode('utf-8')
        zkp_hash = hashlib.sha256(proof_payload).hexdigest()
        return f"ZKP_PoE_SUCCESS: Identity Confirmed. Phi>Tau. Proof={zkp_hash[:16]}... Nonce={nonce}\n".encode('utf-8')

    def take_damage(self, entropy_intensity: float):
        """VIF理論に基づく状態遷移：外因性エントロピー(I)が変動Δに作用し、Fatigue(F)を蓄積させる"""
        if not self.is_active: return

        # 攻撃のエントロピーを内部の熱量（Intensity）変動に変換
        impact = int(entropy_intensity * 10)
        self.dA = min(31, self.dA + impact)
        self.dB = min(31, self.dB + impact)
        
        # 変動Δが許容値を超えるとポテンシャル(Velocity)が低下し、Phiが削られる
        if self.dA > 15 or self.dB > 15:
            self.vA = max(0, self.vA - 1)
            self.phi = max(0.0, self.phi - (entropy_intensity * 0.15))
            
        # Phiが低下するとRuinScore(Fatigue)が非可逆的に蓄積
        if self.phi < 0.8:
            self.ruin_score = min(7, self.ruin_score + 1)
            
        self._update_bit_packing()

    def heat_dissipation(self, heal_amount: float):
        """熱散逸処理（時間経過による熱量クールダウンとPhiの回復）"""
        if self.is_active:
            self.phi = min(1.0, self.phi + heal_amount)
            # 変動熱量(Intensity)の自然冷却
            self.dA = max(0, self.dA - 2)
            self.dB = max(0, self.dB - 2)
            
            # Phiが安定していればVelocityも徐々に回復
            if self.phi > 0.9:
                self.vA = min(3, self.vA + 1)
                self.vB = min(3, self.vB + 1)
                
            self._update_bit_packing()

    def phase_transition_to_cloud(self):
        """自己崩壊限界における確率雲への強制的相転移（Phase Transition）"""
        self.is_active = False
        self.ruin_score = 7
        self.internal_state_seed = b"\x00" * 16 # 内部状態の暗号的消去
        self.phi = 0.0
        self.dA, self.dB, self.dC = 0, 0, 0
        self.vA, self.vB, self.vC = 0, 0, 0
        self._update_bit_packing()

# ==========================================
# セキュリティ・エンジン (Graph Laplacian & Network Control)
# ==========================================
class AegisSecurityEngine:
    def __init__(self, host: str = '0.0.0.0', port: int = 8888):
        self.host_node = SecurityAgent("host_server")
        self.host = host
        self.port = port
        
        # 動的グラフ管理 (IP -> Node Index)
        self.ip_to_index: Dict[str, int] = {}
        self.index_to_ip: Dict[int, str] = {}
        self.num_nodes = 1
        
        # 署名付き隣接行列 A (初期はホスト自身のみ)
        self.A = np.zeros((1, 1), dtype=np.float32)
        
        # 状態リスト管理
        self.blocked_ips: Set[str] = set()
        self.trusted_ips: Set[str] = set()
        
        # サーバー制御フラグ
        self.server_running = False
        self.server_thread = None
        self.heal_thread = None
        self.server_socket = None
        self.is_monitoring = False

    def _get_or_create_node_index(self, ip: str) -> int:
        """動的トポロジ: 新規IPアクセス時にグラフ（隣接行列）を拡張する"""
        if ip in self.ip_to_index:
            return self.ip_to_index[ip]
        
        new_idx = self.num_nodes
        self.ip_to_index[ip] = new_idx
        self.index_to_ip[new_idx] = ip
        self.num_nodes += 1
        
        # 隣接行列 A の拡張 (ゼロ埋め)
        new_A = np.zeros((self.num_nodes, self.num_nodes), dtype=np.float32)
        new_A[:self.num_nodes-1, :self.num_nodes-1] = self.A
        self.A = new_A
        return new_idx

    def calculate_algebraic_connectivity(self) -> float:
        """グラフ・ラプラシアン L = D - A による代数的連結度(Fiedler Value)の計算"""
        if self.num_nodes <= 1:
            return 0.0
        
        D = np.diag(np.sum(np.abs(self.A), axis=1))
        L = D - self.A
        eigenvalues = np.linalg.eigvalsh(L)
        sorted_values = np.sort(eigenvalues)
        
        if len(sorted_values) > 1:
            return float(sorted_values[1])
        return 0.0

    def calculate_shannon_entropy(self, data: bytes) -> float:
        """受信パケットからのシャノン・エントロピー抽出"""
        if not data: return 0.0
        entropy = 0.0
        for x in range(256):
            p_x = float(data.count(x)) / len(data)
            if p_x > 0:
                entropy += - p_x * math.log2(p_x)
        return min(1.0, entropy / 8.0) 

    def evaluate_payload(self, data: bytes) -> tuple[str, float]:
        """ペイロードの相互情報量(抽出要求)判定"""
        entropy = self.calculate_shannon_entropy(data)
        data_size = len(data)

        # エントロピー同化（情報を奪い、均質化を図るプローブ）の検知
        if data_size > MAX_SAFE_PAYLOAD or entropy > THETA_AYT:
            return ResponseStatus.ASSIMILATION_THREAT, entropy
            
        return ResponseStatus.SAFE_HEARTBEAT, entropy

    def _stabilize_local_connectivity(self):
        """AAIMA: 孤立化を防ぐための健全なエッジの動的強化（クロッシングの維持）"""
        lambda_2 = self.calculate_algebraic_connectivity()
        threshold_connectivity = 0.5
        
        if lambda_2 < threshold_connectivity and self.trusted_ips:
            # 健全なノード(Trusted)とのエッジウェイトを増加させる(Rank-one perturbation)
            for ip in self.trusted_ips:
                idx = self.ip_to_index.get(ip)
                if idx is not None:
                    self.A[0, idx] = min(2.0, self.A[0, idx] + 0.2)
                    self.A[idx, 0] = self.A[0, idx]

    def start_server(self):
        if self.server_running: return
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)
            self.server_running = True
            
            self.server_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.server_thread.start()
            
            self.heal_thread = threading.Thread(target=self._auto_heal_loop, daemon=True)
            self.heal_thread.start()
            
            print(f"{Colors.GREEN}【起動】防衛ネットワーク監視を {self.host}:{self.port} で開始しました。{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}【エラー】サーバー起動失敗: {e}{Colors.RESET}")

    def stop_server(self):
        self.server_running = False
        if self.server_socket: self.server_socket.close()
        if self.server_thread: self.server_thread.join()
        if self.heal_thread: self.heal_thread.join()
        print(f"{Colors.YELLOW}【停止】ネットワーク監視を終了しました。{Colors.RESET}")

    def unblock_ip(self, ip_address: str) -> bool:
        """トポロジカル隔離の解除"""
        if ip_address in self.blocked_ips:
            self.blocked_ips.remove(ip_address)
            idx = self.ip_to_index.get(ip_address)
            if idx is not None:
                self.A[0, idx] = 1.0
                self.A[idx, 0] = 1.0
            return True
        return False

    def _auto_heal_loop(self):
        """Kugler/Turveyモデル: クロッシングを通じたエントロピーの散逸と自己組織化(自然回復)"""
        while self.server_running:
            time.sleep(5)
            if self.host_node.is_active:
                # グラフの代数的連結度が高いほど、回復力が向上する
                connectivity = self.calculate_algebraic_connectivity()
                crossing_bonus = min(0.08, connectivity * 0.02)
                
                # 熱散逸とPhiの回復
                self.host_node.heat_dissipation(heal_amount=0.01 + crossing_bonus)

    def _listen_loop(self):
        while self.server_running:
            # 継続的なPhiの監視 (フェーズ1)
            if self.host_node.is_active and self.host_node.phi <= TAU_CRITICAL:
                self._execute_phase_transition()
                break

            try:
                client_socket, addr = self.server_socket.accept()
                client_ip = addr[0]
            except socket.timeout:
                continue
            except OSError:
                break

            # 確率雲（Phase Transition済）状態の場合は全アクセスを無言でドロップ
            if not self.host_node.is_active:
                client_socket.close()
                continue

            node_idx = self._get_or_create_node_index(client_ip)

            # トポロジカル隔離判定 (排他処理)
            if client_ip in self.blocked_ips:
                client_socket.close()
                continue

            try:
                client_socket.settimeout(2.0)
                data = client_socket.recv(4096)
                if not data:
                    client_socket.close()
                    continue

                verdict, entropy = self.evaluate_payload(data)

                # --- リアルタイム観測モード ---
                if self.is_monitoring:
                    print(f"\n{Colors.CYAN}[MONITOR] パケット受信: {client_ip}{Colors.RESET}")
                    bar_length = 20
                    fill_length = int((entropy / 1.0) * bar_length)
                    meter_color = Colors.RED if entropy > THETA_AYT else Colors.GREEN
                    entropy_bar = f"[{meter_color}{'#' * fill_length}{'-' * (bar_length - fill_length)}{Colors.RESET}]"
                    print(f"{Colors.CYAN}[MONITOR] 要求エントロピー: {entropy_bar} ({entropy:.4f}){Colors.RESET}")
                    print(f"{Colors.CYAN}Aegis>{Colors.RESET} ", end="", flush=True)

                if verdict == ResponseStatus.ASSIMILATION_THREAT:
                    print(f"\n{Colors.YELLOW}【警告】IP {client_ip} から同化プローブ(過剰情報抽出)を検知！{Colors.RESET}")
                    
                    # ゼロ知識証明(ZKP)による防衛的応答
                    zkp_response = self.host_node.generate_zkp_token()
                    client_socket.sendall(zkp_response)
                    
                    # 動的トポロジ再構成: 敵対的エッジの切断
                    self.A[0, node_idx] = 0.0
                    self.A[node_idx, 0] = 0.0
                    self.blocked_ips.add(client_ip)
                    if client_ip in self.trusted_ips:
                        self.trusted_ips.remove(client_ip)
                        
                    # VIFダメージの適用
                    self.host_node.take_damage(entropy)
                    
                    print(f"{Colors.RED}【対応】ZKPトークンを返送し、対象ノードをグラフから論理遮断しました。{Colors.RESET}")
                    self._stabilize_local_connectivity()
                    print(f"{Colors.CYAN}Aegis>{Colors.RESET} ", end="", flush=True)
                    
                else:
                    if self.A[0, node_idx] == 0.0:
                        self.A[0, node_idx] = 1.0
                        self.A[node_idx, 0] = 1.0
                        
                    self.trusted_ips.add(client_ip)
                    client_socket.sendall(b"ACK: Heartbeat Accepted.\n")

            except Exception:
                pass
            finally:
                client_socket.close()

    def _execute_phase_transition(self):
        """フェーズ4: カスケード故障の防止 (確率雲への相転移)"""
        print(f"\n{Colors.MAGENTA}【臨界検知】内部状態(Phi)が崩壊限界を下回りました。同化の進行を検知！{Colors.RESET}")
        print(f"{Colors.MAGENTA}【相転移】物理実体としての処理を停止し、マクロな「確率雲(Probability Cloud)」へと状態を圧縮・移行します。{Colors.RESET}")
        print(f"{Colors.MAGENTA}【Zero-Lock】全ての外部干渉が無効化され、ネットワークから完全に姿を消しました。{Colors.RESET}")
        
        self.host_node.phase_transition_to_cloud()
        
        self.server_running = False
        if self.server_socket: self.server_socket.close()

    def print_status(self):
        if self.host_node.is_active:
            status_text = f"{Colors.GREEN}実体稼働中{Colors.RESET}" if self.server_running else f"{Colors.YELLOW}待機中{Colors.RESET}"
        else:
            status_text = f"{Colors.MAGENTA}確率雲 (Phase Transition / Zero-Lock){Colors.RESET}"
            
        connectivity = self.calculate_algebraic_connectivity()
        
        print(f"\n{Colors.CYAN}--- システムステータス ---{Colors.RESET}")
        print(f"状態           : {status_text}")
        print(f"システム健全度 : {int(self.host_node.phi * 100)} % (Phi)")
        print(f"システム疲労度 : {self.host_node.ruin_score} / 7 (Fatigue)")
        print(f"変動Δ (熱量)  : dA={self.host_node.dA}, dB={self.host_node.dB}")
        print(f"信頼済みIP     : {len(self.trusted_ips)} ノード")
        print(f"遮断済みIP     : {len(self.blocked_ips)} ノード")
        print(f"代数的連結度   : {connectivity:.4f} (クロッシング強度)")
        print(f"内部SoA状態    : 0x{self.host_node.bit_packed_abc:08X}")
        print(f"{Colors.CYAN}--------------------------{Colors.RESET}\n")

    def print_dump(self):
        """内部ビットパッキング(SoA)の詳細解析出力"""
        print(f"\n{Colors.CYAN}--- Py_UCD-F_ABC SoA Memory Dump ---{Colors.RESET}")
        packed = self.host_node.bit_packed_abc
        print(f"Raw 32bit Data : 0b{packed:032b}")
        
        vA = packed & 0x03
        vB = (packed >> 2) & 0x03
        vC = (packed >> 4) & 0x03
        
        # 6bit符号付きのデコード
        def decode_6bit(val):
            return val - 64 if val & 0x20 else val
            
        dA = decode_6bit((packed >> 6) & 0x3F)
        dB = decode_6bit((packed >> 12) & 0x3F)
        dC = decode_6bit((packed >> 18) & 0x3F)
        
        state = (packed >> 24) & 0x07
        ruin = (packed >> 27) & 0x07
        
        print(f"Velocity (ABC強度) : vA={vA}, vB={vB}, vC={vC} (Max 3)")
        print(f"Intensity(変動熱量): dA={dA}, dB={dB}, dC={dC} (Max 31)")
        print(f"State Flag         : {state} (1=Active, 0=Probability Cloud)")
        print(f"Fatigue (RuinScore): {ruin} (Max 7)")
        print(f"Secret MICS Seed   : {self.host_node.internal_state_seed.hex()}")
        print(f"{Colors.CYAN}------------------------------------{Colors.RESET}\n")


# ==========================================
# ユーザーインターフェース (CUIループ)
# ==========================================
def main():
    print(f"{Colors.CYAN}=================================================={Colors.RESET}")
    print(" 汎用型耐同化自己同一性維持システム [Aegis-AAIMA] 起動完了")
    print(" バックグラウンドで動的トポロジ構成およびZKPエンジンが稼働中。")
    print(f"{Colors.CYAN}=================================================={Colors.RESET}")
    
    engine = AegisSecurityEngine(host='0.0.0.0', port=8888)
    engine.start_server()
    
    help_text = f"""
{Colors.YELLOW}使用可能なコマンド:{Colors.RESET}
  {Colors.GREEN}status{Colors.RESET}       : 現在のシステム健全度とグラフ連結度を表示します
  {Colors.GREEN}dump{Colors.RESET}         : 内部SoAメモリ(VIFダイナミクス)の詳細解析を表示します
  {Colors.GREEN}blocks{Colors.RESET}       : 現在遮断されているIPアドレスのリストを表示します
  {Colors.CYAN}monitor{Colors.RESET}      : パケットエントロピーのリアルタイム観測のON/OFF
  {Colors.CYAN}unblock [ip]{Colors.RESET} : 指定IPのグラフ論理遮断を解除します
  {Colors.CYAN}heal{Colors.RESET}         : 内部状態(Phi)の強制修復を実行します
  {Colors.CYAN}test [ip]{Colors.RESET}    : 指定IPへ疑似同化プローブ(高エントロピー)を送信します
  {Colors.GREEN}help{Colors.RESET}         : ヘルプを表示します
  {Colors.GREEN}quit{Colors.RESET}         : システムを終了します
    """
    print(help_text)

    while True:
        try:
            user_input = input(f"{Colors.CYAN}Aegis>{Colors.RESET} ").strip().split()
            if not user_input: continue
            cmd = user_input[0].lower()

            if cmd in ["quit", "exit"]:
                engine.stop_server()
                print("システムを終了します...")
                break
            elif cmd == "help":
                print(help_text)
            elif cmd == "status":
                engine.print_status()
            elif cmd == "dump":
                engine.print_dump()
            elif cmd == "blocks":
                print(f"\n{Colors.YELLOW}--- 遮断済みトポロジ ---{Colors.RESET}")
                if not engine.blocked_ips: print("なし")
                else:
                    for ip in engine.blocked_ips: print(f"- {ip}")
                print(f"{Colors.YELLOW}------------------------{Colors.RESET}\n")
            elif cmd == "monitor":
                engine.is_monitoring = not engine.is_monitoring
                state = "ON" if engine.is_monitoring else "OFF"
                print(f"{Colors.CYAN}【設定】リアルタイム・パケット観測を {state} に変更しました。{Colors.RESET}")
            elif cmd == "unblock":
                if len(user_input) < 2:
                    print(f"{Colors.YELLOW}使用法: unblock [IPアドレス]{Colors.RESET}")
                    continue
                if engine.unblock_ip(user_input[1]):
                    print(f"{Colors.GREEN}【復帰】グラフ上の {user_input[1]} のリンクを復元しました。{Colors.RESET}")
                else:
                    print(f"{Colors.YELLOW}指定IPは遮断リストに存在しません。{Colors.RESET}")
            elif cmd == "heal":
                if not engine.host_node.is_active:
                    print(f"{Colors.MAGENTA}現在は確率雲へ相転移しているため修復できません。物理実体への再構築(再起動)が必要です。{Colors.RESET}")
                else:
                    engine.host_node.heat_dissipation(0.3)
                    print(f"{Colors.GREEN}【修復】熱散逸を加速させ、内部統合情報量(Phi)を回復させました。{Colors.RESET}")
            elif cmd == "test":
                target_ip = '127.0.0.1' if len(user_input) == 1 else user_input[1]
                print(f"【テスト】{target_ip} へ高エントロピー・ペイロードを送信します...")
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(3.0)
                    s.connect((target_ip, 8888))
                    test_payload = np.random.bytes(2048) # MAX_SAFE_PAYLOAD超過
                    s.sendall(test_payload)
                    response = s.recv(1024)
                    print(f"【応答】: {response.decode(errors='ignore').strip()}")
                    s.close()
                except Exception as e:
                    print(f"{Colors.RED}通信失敗 (遮断済み、または確率雲状態): {e}{Colors.RESET}")
            else:
                print(f"不明なコマンドです: {cmd}")
                
        except KeyboardInterrupt:
            engine.stop_server()
            print("\n終了します...")
            break
        except Exception as e:
            print(f"{Colors.RED}エラー: {e}{Colors.RESET}")

if __name__ == "__main__":
    main()