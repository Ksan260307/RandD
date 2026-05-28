import urllib.request
import urllib.error
import re
import time
import random
from urllib.parse import urlparse

# ==========================================
# 状態圧縮管理 (Packed State Management)
# ==========================================
# メモリ効率と判定速度を向上させるため、タスクの各指標を単一の整数に圧縮して管理します。
# 内部構成:
#   [0-1 bit] : 優先度 (0-3)
#   [2-3 bit] : リトライ回数 (0-3)
#   [4-6 bit] : 処理状態フラグ (0-7)
#   [7-9 bit] : 破綻スコア/疲労度 (0-7)

STATE_IDLE = 0       # 待機
STATE_RUNNING = 1    # 実行中
STATE_DONE = 2       # 完了
STATE_ERROR = 3      # エラー
STATE_PROMOTED = 4   # 動的昇格（データが大きく、詳細な解析が必要な状態）
STATE_RUINED = 5     # 破綻（リトライ上限超過により地形化）

def pack_state(priority, retry, status, ruin=0):
    """各指標をビット演算で1つの整数に圧縮"""
    return (priority & 0x3) | ((retry & 0x3) << 2) | ((status & 0x7) << 4) | ((ruin & 0x7) << 7)

def unpack_state(state):
    """圧縮された状態を展開"""
    priority = state & 0x3
    retry = (state >> 2) & 0x3
    status = (state >> 4) & 0x7
    ruin = (state >> 7) & 0x7
    return priority, retry, status, ruin

def update_status(state, new_status):
    """状態フラグのみを更新"""
    p, r, _, ruin = unpack_state(state)
    return pack_state(p, r, new_status, ruin)

# ==========================================
# データ並列構造 (Structure of Arrays)
# ==========================================
class ScraperSystem:
    def __init__(self):
        # オブジェクトリストの代わりに、属性ごとの独立した配列群として管理し
        # 一括処理時のキャッシュ効率を高めます。
        self.urls = []         # 対象URL
        self.states = []       # 圧縮された状態
        self.contents = []     # 取得した生データ（非観測時は生のまま保持）
        self.input_log = []    # 決定論的な入力履歴
        self.domain_ruin_scores = {} # 破綻の地形化（ドメインごとのペナルティ環境要因）

    def add_task(self, url):
        """タスクをキューに追加（遅延評価の準備）"""
        self.urls.append(url)
        self.states.append(pack_state(0, 0, STATE_IDLE, 0))
        self.contents.append(None)
        self.input_log.append(f"ADD: {url}")
        print(f"  [+] タスクを追加しました: {url}")

    def _fetch_url(self, url):
        """URLからのデータ取得処理"""
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.read().decode('utf-8', errors='ignore')
        except Exception as e:
            return None

    def execute_batch(self):
        """溜まったタスクを一括で処理（並行プロセスのエミュレーション）"""
        print("\n--- 処理開始 ---")
        
        # 1. Stream Compaction (ストリームコンパクション)
        # スレッドの非効率化を防ぐため、実行が必要な対象のみの密なリストを生成
        active_indices = []
        for i in range(len(self.urls)):
            _, _, status, _ = unpack_state(self.states[i])
            if status == STATE_IDLE:
                active_indices.append(i)
        
        if not active_indices:
            print("  実行可能な待機タスクがありません。")
            print("--- 処理終了 ---\n")
            return

        # 密なリストに対してのみ処理を実行
        for i in active_indices:
            p, r, status, ruin = unpack_state(self.states[i])
            url = self.urls[i]
            domain = urlparse(url).netloc
            
            self.states[i] = update_status(self.states[i], STATE_RUNNING)
            
            # コンソールへのシンプルな進行出力
            print(f"  実行中 [{i}]: {url[:50]}... ", end="", flush=True)
            
            # ドメイン地形化（RuinScore）による環境ペナルティの適用
            domain_penalty = self.domain_ruin_scores.get(domain, 0)
            
            # エントロピーの注入: サーバー負荷軽減のためのランダムなジッター
            entropy_delay = random.uniform(0.1, 0.5)
            wait_time = entropy_delay + (domain_penalty * 0.5)
            
            if wait_time > 0.6:
                print(f"(環境負荷により {wait_time:.1f}秒待機) ", end="", flush=True)
            time.sleep(wait_time)
            
            content = self._fetch_url(url)
            
            if content:
                # 動的昇格: 取得データが大きい場合、詳細解析が必要な状態へプロモート
                if len(content) > 50000:
                    self.states[i] = update_status(self.states[i], STATE_PROMOTED)
                    print("完了 (詳細解析へ昇格)")
                else:
                    self.states[i] = update_status(self.states[i], STATE_DONE)
                    print("完了")
                
                self.contents[i] = content
                
                # 成功したらドメインの破綻スコアを少し回復（環境の安定化）
                if domain in self.domain_ruin_scores and self.domain_ruin_scores[domain] > 0:
                    self.domain_ruin_scores[domain] -= 1
            else:
                # エラー発生時の処理
                if r < 3: # 最大3回までリトライ
                    self.states[i] = pack_state(p, r + 1, STATE_IDLE, ruin + 1)
                    # 動的待機時間調整: リトライ回数と破綻度に応じて待機時間を延長
                    delay = (r + 1) * 0.5 + (ruin * 0.2)
                    print(f"失敗 (再試行予定: {delay:.1f}秒待機)")
                    time.sleep(delay)
                else:
                    self.states[i] = update_status(self.states[i], STATE_RUINED)
                    print("完全失敗 (破綻状態へ移行・地形化)")
                    # 対象ドメインの環境を悪化させる（以降の同一ドメインアクセスの遅延増加）
                    self.domain_ruin_scores[domain] = self.domain_ruin_scores.get(domain, 0) + 2
                    
        print("--- 処理終了 ---\n")

    def extract_data(self):
        """
        要求されたタイミングで必要な情報だけを実体化して表示。
        未使用のデータはメモリ内に圧縮保持したままにします。
        """
        print("\n--- 抽出結果 ---")
        has_result = False
        for i in range(len(self.urls)):
            _, _, status, ruin = unpack_state(self.states[i])
            
            if status in (STATE_DONE, STATE_PROMOTED):
                has_result = True
                html = self.contents[i]
                if not html: continue
                
                # タイトルの抽出
                title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else "タイトルなし"
                
                print(f"[{i}] {title}")
                print(f"    URL: {self.urls[i]}")
                print(f"    データ量: {len(html)} bytes")
                
                # プロモート状態の場合は、探索範囲を限定してリンクを抽出
                if status == STATE_PROMOTED:
                    print("    ※ 情報量が多いため、内部リンクの一部を抽出します:")
                    links = re.findall(r'href=[\'"]?(https?://[^\'" >]+)', html)
                    # 探索範囲の限定（リソース保護）
                    for link in list(set(links))[:3]: 
                        print(f"      - {link}")
                print()
                
        if not has_result:
            print("  表示できる完了データがありません。")
        print("----------------\n")


# ==========================================
# コンソール対話インターフェース
# ==========================================
def main():
    print("=====================================")
    print(" 高効率ウェブスクレイパー 起動")
    print("=====================================")
    system = ScraperSystem()
    
    while True:
        print("[メニュー] 1:URL追加  2:一括処理実行  3:結果表示  q:終了")
        cmd = input("選択 > ").strip()
        
        if cmd == '1':
            url = input("  URLを入力してください: ").strip()
            if url.startswith("http"):
                system.add_task(url)
            else:
                print("  [!] エラー: 有効なURL (http/https) を入力してください。")
        elif cmd == '2':
            system.execute_batch()
        elif cmd == '3':
            system.extract_data()
        elif cmd.lower() == 'q':
            print("システムを終了します。")
            break
        else:
            print("  [!] 無効なコマンドです。")

if __name__ == "__main__":
    main()