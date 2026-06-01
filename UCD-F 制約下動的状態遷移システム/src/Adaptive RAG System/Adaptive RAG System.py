# ============================================================================
# 動的適応型検索・状態遷移システム (Adaptive RAG & Dynamic State System)
# 
# 概要:
#   このシステムは、検索拡張生成(RAG)における静的な検索の限界を克服し、
#   リソース制約下でも効率的に動作する動的アーキテクチャを実装したものです。
#
# 実装された主要概念:
#   - 関連セクター抽出による計算対象の極小化 (旧: 影響円錐)
#   - 確率モデルを用いた動的クラスタリングと要約圧縮 (旧: 中華料理店過程/CRP)
#   - 関連性スコアの近傍波及 (旧: 反復的状態伝播)
#   - 計算頻度の間引きと非アクティブなデータのアーカイブ (旧: 局所時間拡張 / Zero-Lock)
#   - 32bit状態ビットパッキングと優先度昇格
#   - PID制御ベースの動的検索深度最適化
#   - [NEW] 5分(300秒)ごとのオンライン自動学習・再フィッティング機能
#
# フロントエンド: HTML, Tailwind CSS, Vanilla JS
# バックエンド: Python (標準ライブラリのみ)
# ============================================================================

import json
import math
import time
import re
import threading
import random
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from collections import defaultdict

# ============================================================================
# 1. 知識ベース (ダミーデータセット)
# ============================================================================
KNOWLEDGE_BASE = [
    {"id": "doc_001", "title": "大規模言語モデルの基礎", "content": "大規模言語モデル(LLM)は、膨大なテキストデータで訓練されたニューラルネットワークです。次に来る単語を予測することで文章を生成します。"},
    {"id": "doc_002", "title": "RAGシステムの利点", "content": "検索拡張生成(RAG)は、LLMの幻覚(ハルシネーション)を防ぐため、外部データベースから最新かつ正確な情報を検索し、回答の根拠として利用する仕組みです。"},
    {"id": "doc_003", "title": "PID制御の原理", "content": "PID制御は、比例(Proportional)、積分(Integral)、微分(Derivative)の3つの要素を用いて、目標値と現在値の誤差を最小化する古典的かつ強力なフィードバック制御アルゴリズムです。"},
    {"id": "doc_004", "title": "キャッシュの忘却曲線", "content": "エビングハウスの忘却曲線によれば、記憶は時間とともに指数関数的に減衰します。システムキャッシュにおいて、アクセスされない情報は徐々に劣化スコアを上げ、最終的に破棄されます。"},
    {"id": "doc_005", "title": "ベクトル検索とTF-IDF", "content": "テキスト検索には、単語の出現頻度に基づくTF-IDFと、意味的な近さを計算するベクトル埋め込み表現(Embedding)があります。ハイブリッド検索はこれらを組み合わせます。"},
    {"id": "doc_006", "title": "Pythonのメモリ管理", "content": "Pythonはガベージコレクションによってメモリを自動管理しますが、大量のオブジェクトを扱うとオーバーヘッドが増大します。これを防ぐためビットパッキング等の技術が使われます。"},
    {"id": "doc_007", "title": "動的スケーリング", "content": "システムの負荷に応じてリソースを増減させる動的スケーリングは、クラウドインフラストラクチャにおけるコスト最適化の鍵となります。"},
    {"id": "doc_008", "title": "不確実性の定量化", "content": "モデルが自身の出力にどれだけ自信を持っているかを測ることを不確実性の定量化と呼びます。ベイズ推論などが用いられ、信頼性が低い場合は追加の検索を行います。"},
    {"id": "doc_009", "title": "クラスタリングアルゴリズム", "content": "K-meansやDBSCANなどのクラスタリング手法は、大量のデータを類似性に基づいてグループ化します。情報過多の際、代表的な要約を抽出するのに役立ちます。"},
    {"id": "doc_010", "title": "Webブラウザのレンダリング", "content": "ブラウザはDOMツリーを構築し、画面に描画します。画面外の要素の描画を省略するカリング(Culling)技術は、パフォーマンス向上に寄与します。"},
    {"id": "doc_011", "title": "状態遷移システム", "content": "システムが有限個の状態を持ち、入力に応じて状態が切り替わるモデルを状態遷移システムと呼びます。堅牢な制御ロジックの設計に不可欠です。"},
    {"id": "doc_012", "title": "ビット演算の高速化", "content": "整数のビット単位での操作(AND, OR, XOR, シフト)は、CPU上で非常に高速に実行されます。大量のフラグを1つの整数に圧縮(パック)する際に利用されます。"},
    {"id": "doc_013", "title": "モンテカルロ法", "content": "乱数を用いて数値計算やシミュレーションを行う手法です。確率的な不確実性を評価する際によく利用されます。"},
    {"id": "doc_014", "title": "データサイエンスのエコシステム", "content": "Pandas, NumPy, Scikit-learnなどのライブラリは、データ処理から機械学習モデルの構築までをカバーする強力なエコシステムを形成しています。"},
    {"id": "doc_015", "title": "非同期処理とスレッド", "content": "重い計算やI/O待ちが発生する際、非同期処理やマルチスレッドを用いることで、メインプロセス(UIなど)のブロックを防ぎます。"}
]

# ============================================================================
# 2. 自然言語処理・ベクトル・空間管理 (TF-IDF, Sector Hashing)
# ============================================================================
class SimpleTokenizer:
    @staticmethod
    def tokenize(text):
        text = text.lower()
        return re.findall(r'\w+', text)

class TFIDFVectorizer:
    def __init__(self):
        self.df = defaultdict(int)
        self.idf = {}
        self.vocab = {}
        self.num_docs = 0
        self.is_fitted = False

    def fit(self, corpus):
        self.num_docs = len(corpus)
        for doc in corpus:
            tokens = set(SimpleTokenizer.tokenize(doc))
            for token in tokens: self.df[token] += 1
        for token, count in self.df.items():
            self.idf[token] = math.log(self.num_docs / (1 + count)) + 1
            self.vocab[token] = len(self.vocab)
        self.is_fitted = True

    def transform(self, doc):
        if not self.is_fitted: raise ValueError("Vectorizer is not fitted.")
        tokens = SimpleTokenizer.tokenize(doc)
        tf = defaultdict(int)
        for token in tokens: tf[token] += 1
        vector = {}
        doc_len = max(len(tokens), 1)
        for token, count in tf.items():
            if token in self.idf:
                vector[self.vocab[token]] = (count / doc_len) * self.idf[token]
        return vector

def cosine_similarity(vec1, vec2):
    intersection = set(vec1.keys()) & set(vec2.keys())
    numerator = sum(vec1[x] * vec2[x] for x in intersection)
    sum1 = sum(val ** 2 for val in vec1.values())
    sum2 = sum(val ** 2 for val in vec2.values())
    denominator = math.sqrt(sum1) * math.sqrt(sum2)
    return numerator / denominator if denominator else 0.0

class TopicSectorManager:
    """トピックベースのセクター分割と、関連セクター抽出による計算対象の極小化"""
    def __init__(self, num_sectors=3):
        self.num_sectors = num_sectors
        self.centroids = []
        self.doc_to_sector = {}
        self.sector_docs = defaultdict(list)

    def fit(self, doc_vectors, doc_ids):
        # 簡易K-Means的アプローチでセクター(トピック空間)を分割
        random.seed(42)
        self.centroids = random.sample(doc_vectors, min(self.num_sectors, len(doc_vectors)))
        
        for _ in range(5): # 収束ループ
            new_clusters = defaultdict(list)
            for i, vec in enumerate(doc_vectors):
                best_sector = 0
                best_sim = -1
                for s_idx, centroid in enumerate(self.centroids):
                    sim = cosine_similarity(vec, centroid)
                    if sim > best_sim:
                        best_sim = sim
                        best_sector = s_idx
                new_clusters[best_sector].append((i, vec, doc_ids[i]))
            
            # 重心の再計算
            for s_idx in range(len(self.centroids)):
                if not new_clusters[s_idx]: continue
                new_centroid = defaultdict(float)
                for _, vec, _ in new_clusters[s_idx]:
                    for k, v in vec.items(): new_centroid[k] += v
                for k in new_centroid: new_centroid[k] /= len(new_clusters[s_idx])
                self.centroids[s_idx] = new_centroid
                
        # 最終割り当て
        self.doc_to_sector.clear()
        self.sector_docs.clear()
        for s_idx, items in new_clusters.items():
            for i, vec, doc_id in items:
                self.doc_to_sector[doc_id] = s_idx
                self.sector_docs[s_idx].append(doc_id)

    def get_relevant_sectors(self, query_vec, threshold=0.01):
        """クエリと関連性が高いセクターのみを抽出"""
        active_sectors = []
        for s_idx, centroid in enumerate(self.centroids):
            if cosine_similarity(query_vec, centroid) > threshold:
                active_sectors.append(s_idx)
        # 最低1つのセクターは選択する（フォールバック）
        if not active_sectors and self.centroids:
            best_sector = max(range(len(self.centroids)), key=lambda s: cosine_similarity(query_vec, self.centroids[s]))
            active_sectors.append(best_sector)
        return active_sectors

# ============================================================================
# 3. メモリ管理と状態遷移 (Bit-Packing, Cache)
# ============================================================================
class StateBitPacker:
    """
    [0-1]   アクセス頻度 (Velocity, 0-3)
    [2-3]   重要度 (Intensity, 0-3)
    [4-5]   劣化度 (Fatigue, 0-3)
    [24-26] 状態フラグ (0:アーカイブ済/除外, 1:アクティブ, 2:優先度昇格, 3:クラスタ化)
    [27-29] 破綻判定値 (0-7)
    """
    @staticmethod
    def pack(velocity, intensity, fatigue, state_flag, ruin_score):
        packed = 0
        packed |= (min(max(int(velocity), 0), 3) & 0b11) << 0
        packed |= (min(max(int(intensity), 0), 3) & 0b11) << 2
        packed |= (min(max(int(fatigue), 0), 3) & 0b11) << 4
        packed |= (min(max(int(state_flag), 0), 7) & 0b111) << 24
        packed |= (min(max(int(ruin_score), 0), 7) & 0b111) << 27
        return packed

    @staticmethod
    def unpack(p):
        return {
            "velocity": (p >> 0) & 0b11, "intensity": (p >> 2) & 0b11,
            "fatigue": (p >> 4) & 0b11, "state_flag": (p >> 24) & 0b111,
            "ruin_score": (p >> 27) & 0b111
        }

class DynamicCacheMemory:
    def __init__(self, decay_rate=0.1):
        self.cache = {}
        self.decay_rate = decay_rate
        self.lock = threading.Lock()

    def get(self, query):
        with self.lock:
            t = time.time()
            if query in self.cache:
                item = self.cache[query]
                item['strength'] = item['strength'] * math.exp(-self.decay_rate * (t - item['last_accessed'])) + 1.0
                item['last_accessed'] = t
                return item['result'], True
            return None, False

    def put(self, query, result):
        with self.lock:
            self.cache[query] = {'result': result, 'strength': 1.0, 'last_accessed': time.time()}

    def cleanup_routine(self):
        with self.lock:
            t = time.time()
            deletes = [k for k, v in self.cache.items() if (v['strength'] * math.exp(-self.decay_rate * (t - v['last_accessed']))) < 0.1]
            for k in deletes: del self.cache[k]
            return len(deletes)

# ============================================================================
# 4. 最適化ロジック (動的クラスタリング, PID, ノイズ)
# ============================================================================
class DynamicProbabilisticClustering:
    """確率的アプローチに基づく動的クラスタリング (要約圧縮)"""
    def __init__(self, alpha=1.5):
        self.alpha = alpha

    def cluster(self, results):
        if not results: return [], 0
        tables = []
        for doc in results:
            if not tables:
                tables.append([doc])
                continue
            
            n_total = sum(len(t) for t in tables)
            probs = [len(t) / (n_total + self.alpha) for t in tables]
            probs.append(self.alpha / (n_total + self.alpha)) # 新しいグループの確率
            
            r = random.random()
            cum = 0.0
            chosen = len(tables)
            for i, p in enumerate(probs):
                cum += p
                if r <= cum:
                    chosen = i
                    break
                    
            if chosen == len(tables): tables.append([doc])
            else: tables[chosen].append(doc)
            
        # グループごとの要約メタドキュメント生成
        final_results = []
        for i, table in enumerate(tables):
            if len(table) == 1:
                final_results.append(table[0])
            else:
                titles = [d['title'] for d in table]
                avg_score = sum(d['score'] for d in table) / len(table)
                final_results.append({
                    "id": f"cluster_{i}_{int(time.time()*1000)}",
                    "title": f"【データ要約】 関連トピック群 ({len(table)}件)",
                    "content": f"情報密度が高いため、動的クラスタリングにより統合されました。要素: {', '.join(titles)}",
                    "score": avg_score, "is_clustered": True, "is_promoted": False
                })
        return final_results, len(tables)

class SystemNoiseGenerator:
    """システムの不確実性に揺らぎを与えるランダムノイズ"""
    @staticmethod
    def harvest(): return random.uniform(-0.05, 0.05)

class PIDController:
    """PID制御を用いた検索深度の動的調整"""
    def __init__(self, kp=2.0, ki=0.5, kd=1.0, target_confidence=0.85):
        self.kp = kp; self.ki = ki; self.kd = kd; self.target = target_confidence
        self.integral_error = 0.0; self.previous_error = 0.0; self.last_time = time.time()

    def update(self, current_confidence, entropy_noise=0.0):
        t = time.time()
        dt = max(t - self.last_time, 0.01)
        error = (self.target + entropy_noise) - current_confidence
        self.integral_error += error * dt
        derivative = (error - self.previous_error) / dt
        out = (self.kp * error) + (self.ki * self.integral_error) + (self.kd * derivative)
        self.previous_error = error; self.last_time = t
        return max(min(int(round(out)), 5), -2)

class UncertaintyEvaluator:
    @staticmethod
    def evaluate(scores):
        if not scores: return 0.0, 1.0
        mu = sum(scores) / len(scores)
        var = sum((s - mu)**2 for s in scores) / len(scores)
        sigma = math.sqrt(var)
        return max(min(mu - (0.3 * sigma), 1.0), 0.0), sigma

# ============================================================================
# 5. 統合RAGパイプライン
# ============================================================================
class AdaptiveRAGPipeline:
    def __init__(self, knowledge_base):
        self.kb = knowledge_base
        self.vectorizer = TFIDFVectorizer()
        self.doc_vectors = []
        self.sector_manager = TopicSectorManager(num_sectors=3)
        self.cache = DynamicCacheMemory()
        self.clustering = DynamicProbabilisticClustering(alpha=1.2)
        self.time_step = 0
        self.training_count = 0
        self.last_training_time = time.time()
        self.lock = threading.Lock()
        
        print("初期化: TF-IDFモデルと空間セクターの学習中...")
        self._fit_models()

    def _fit_models(self):
        corpus = [doc['title'] + " " + doc['content'] for doc in self.kb]
        self.vectorizer.fit(corpus)
        self.doc_vectors.clear()
        doc_ids = []
        for i, doc in enumerate(corpus):
            vec = self.vectorizer.transform(doc)
            self.doc_vectors.append(vec)
            doc_ids.append(self.kb[i]['id'])
            
        self.sector_manager.fit(self.doc_vectors, doc_ids)
        if not hasattr(self, 'state_db'):
            self.state_db = {}
        
        for doc_id in doc_ids:
            if doc_id not in self.state_db:
                self.state_db[doc_id] = StateBitPacker.pack(0, 0, 0, 1, 0)

    def retrain(self):
        """オンライン自動学習(再トレーニング)処理"""
        with self.lock:
            # モック: 新しい学習データを追加
            new_doc_id = f"doc_auto_{int(time.time())}"
            new_doc = {
                "id": new_doc_id,
                "title": f"オンライン学習データ ({time.strftime('%H:%M:%S')})",
                "content": f"このドキュメントはオンライン自動学習プロセスによって定期的にシステムに統合された新しい知識です。"
            }
            self.kb.append(new_doc)
            
            # ベクトルおよびセクターの再計算
            self._fit_models()
            
            self.training_count += 1
            self.last_training_time = time.time()

    def process_query(self, query_text, client_visible_docs=None):
        with self.lock:
            start_time = time.time()
            self.time_step += 1
            logs = []
            
            sys_noise = SystemNoiseGenerator.harvest()
            logs.append(f"システムノイズの適用: {sys_noise:.4f}")

            # 1. キャッシュ確認
            cached_result, is_hit = self.cache.get(query_text)
            if is_hit:
                logs.append("Cache Hit: 動的メモリから結果を即時返却")
                return {"results": cached_result, "logs": logs, "metrics": {"latency_ms": (time.time() - start_time) * 1000, "source": "cache"}}

            # 2. 関連セクター抽出による計算対象空間の絞り込み
            query_vec = self.vectorizer.transform(query_text)
            active_sectors = self.sector_manager.get_relevant_sectors(query_vec)
            active_doc_ids = set()
            for s_idx in active_sectors:
                active_doc_ids.update(self.sector_manager.sector_docs[s_idx])
                
            prune_ratio = (1.0 - (len(active_doc_ids) / len(self.kb))) * 100 if len(self.kb) > 0 else 0
            logs.append(f"関連セクター抽出: {len(active_sectors)}個のトピックを活性化 (検索空間を{prune_ratio:.1f}%削減)")

            # 3. 初期検索 (計算間引き & アーカイブ済の除外)
            scored_docs = []
            skipped = 0
            for i, doc_id in enumerate([doc['id'] for doc in self.kb]):
                if doc_id not in active_doc_ids: continue
                
                state = StateBitPacker.unpack(self.state_db[doc_id])
                if state['state_flag'] == 0: continue # アーカイブ済(除外)
                
                # 計算間引き (Compute Throttling)
                if state['velocity'] == 0 and self.time_step % 2 != 0:
                    skipped += 1
                    continue
                    
                score = cosine_similarity(query_vec, self.doc_vectors[i])
                if score > 0.05:
                    scored_docs.append({
                        "id": doc_id, "title": self.kb[i]['title'], "content": self.kb[i]['content'],
                        "score": score, "is_clustered": False, "sector": self.sector_manager.doc_to_sector.get(doc_id)
                    })
                    
            if skipped > 0: logs.append(f"計算間引き: アクセス頻度の低い {skipped} 件の演算をスキップしました。")
            scored_docs.sort(key=lambda x: x['score'], reverse=True)
            
            # 4. PID制御ループによる検索深度の調整
            current_k = 2
            pid = PIDController(target_confidence=0.7)
            for iteration in range(3):
                current_results = scored_docs[:current_k]
                scores = [r['score'] for r in current_results]
                confidence, uncertainty = UncertaintyEvaluator.evaluate(scores)
                logs.append(f"反復 {iteration+1}: 信頼度={confidence:.2f}, 不確実性={uncertainty:.2f} (K={current_k})")
                if confidence >= 0.7 or current_k >= len(scored_docs): break
                delta_k = pid.update(confidence, entropy_noise=sys_noise)
                current_k = max(current_k + delta_k, 1)

            final_results = scored_docs[:current_k]

            # 5. 動的クラスタリング (要約圧縮)
            original_len = len(final_results)
            if original_len > 3:
                final_results, tables_count = self.clustering.cluster(final_results)
                logs.append(f"動的クラスタリング: {original_len}件のドキュメントを {tables_count} 個の要約グループに圧縮。")

            # 6. 関連性スコアの波及 & 状態更新
            sector_intensity_pool = defaultdict(int)
            for r in final_results:
                if r.get('is_clustered'): continue
                if r['sector'] is not None:
                    sector_intensity_pool[r['sector']] += 1
                
                state = StateBitPacker.unpack(self.state_db[r['id']])
                is_promoted = r['score'] > 0.4
                r['is_promoted'] = is_promoted
                
                state_flag = 2 if is_promoted else 1
                intensity = 3 if is_promoted else min(state['intensity'] + 2, 3)
                self.state_db[r['id']] = StateBitPacker.pack(3, intensity, 0, state_flag, state['ruin_score'])

            # 状態の適用とアーカイブ化
            client_visible_docs = client_visible_docs or []
            for doc_id, packed_state in self.state_db.items():
                state = StateBitPacker.unpack(packed_state)
                if state['state_flag'] == 0: continue
                
                is_result = doc_id in [r.get('id') for r in final_results if not r.get('is_clustered')]
                
                # スコアの波及
                sector = self.sector_manager.doc_to_sector.get(doc_id)
                propagated_intensity = 0
                if not is_result and sector in sector_intensity_pool:
                    propagated_intensity = 1 # セクター内でヒットがあった場合に波及
                    
                if not is_result and doc_id not in client_visible_docs:
                    new_fatigue = state['fatigue'] + 1
                    ruin_score = state['ruin_score']
                    state_flag = state['state_flag']
                    if new_fatigue > 3:
                        new_fatigue = 3; ruin_score += 1
                    if ruin_score > 5:
                        state_flag = 0 # アーカイブ化(除外)
                    
                    new_intensity = min(max(0, state['intensity'] - 1) + propagated_intensity, 3)
                    self.state_db[doc_id] = StateBitPacker.pack(
                        max(0, state['velocity'] - 1), new_intensity, new_fatigue, state_flag, ruin_score
                    )
                    
            # 7. メモリへの定着
            if final_results: self.cache.put(query_text, final_results)
            return {"results": final_results, "logs": logs, "metrics": {"latency_ms": (time.time() - start_time) * 1000, "source": "compute", "k_used": current_k}}

    def get_system_status(self):
        status_counts = {"active": 0, "degraded": 0, "archived": 0, "promoted": 0}
        with self.lock:
            for packed in self.state_db.values():
                s = StateBitPacker.unpack(packed)
                if s['state_flag'] == 0: status_counts['archived'] += 1
                elif s['state_flag'] == 2: status_counts['promoted'] += 1
                elif s['fatigue'] < 2: status_counts['active'] += 1
                else: status_counts['degraded'] += 1
                
        return {
            "total_docs": len(self.kb), "cached_queries": len(self.cache.cache),
            "cache_cleaned": self.cache.cleanup_routine(),
            "memory_states": status_counts, "time_step": self.time_step,
            "sectors": self.sector_manager.num_sectors,
            "training_count": self.training_count,
            "last_training_time": time.strftime('%H:%M:%S', time.localtime(self.last_training_time))
        }

rag_pipeline = AdaptiveRAGPipeline(KNOWLEDGE_BASE)

# ============================================================================
# 6. バックグラウンド スレッド (5分ごとの自動オンライン学習)
# ============================================================================
def auto_learning_worker(pipeline, interval_seconds=300):
    while True:
        time.sleep(interval_seconds)
        print("\n[システム] オンライン自動学習プロセスを開始します...")
        pipeline.retrain()
        print(f"[システム] オンライン自動学習が完了しました (実行回数: {pipeline.training_count})")

# ============================================================================
# 7. フロントエンド HTML/CSS/JS
# ============================================================================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Adaptive Optimization System Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        body { font-family: 'Inter', sans-serif; background-color: #f8fafc; }
        .log-container { scroll-behavior: smooth; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
        .fade-in { animation: fadeIn 0.3s ease-in-out forwards; opacity: 0; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .glass-panel { background: rgba(255, 255, 255, 0.95); box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); border: 1px solid rgba(226, 232, 240, 1); }
    </style>
</head>
<body class="text-slate-800 h-screen flex flex-col overflow-hidden">
    
    <header class="bg-indigo-700 text-white p-4 flex justify-between items-center z-10 relative shadow-sm border-b border-indigo-800">
        <div>
            <h1 class="text-xl font-bold flex items-center gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-indigo-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                </svg>
                Adaptive Retrieval Dashboard
            </h1>
            <p class="text-indigo-200 text-xs mt-1">Dynamic Clustering & Auto-Learning Enabled</p>
        </div>
        <div class="flex gap-4 text-sm font-medium">
            <div class="bg-indigo-800 px-3 py-1.5 rounded flex items-center gap-2 border border-indigo-600">
                <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_rgba(52,211,153,0.8)]"></span>
                System Online <span id="timeStepDisplay" class="text-indigo-300 ml-1 font-mono"></span>
            </div>
        </div>
    </header>

    <main class="flex-1 flex overflow-hidden">
        <div class="w-7/12 p-6 flex flex-col gap-4 overflow-y-auto bg-slate-50">
            <div class="glass-panel p-4 rounded-xl">
                <form id="searchForm" class="flex gap-2">
                    <input type="text" id="queryInput" placeholder="検索クエリを入力してください (例: ビット演算)" 
                           class="flex-1 px-4 py-3 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white transition-shadow text-sm">
                    <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-3 rounded-lg font-medium shadow-sm flex items-center gap-2 transition-colors">
                        検索実行
                    </button>
                </form>
                <div class="mt-3 flex gap-2" id="metricsDisplay">
                    <span class="bg-slate-100 text-slate-500 px-2 py-1 rounded text-xs font-mono border border-slate-200">Waiting for query...</span>
                </div>
            </div>

            <div id="resultsArea" class="flex flex-col gap-4 pb-8">
                <div class="text-center text-slate-400 mt-16 flex flex-col items-center">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 mb-3 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    検索を実行すると、関連性の高い情報が動的に抽出され表示されます。
                </div>
            </div>
        </div>

        <div class="w-5/12 bg-white border-l border-slate-200 p-6 flex flex-col gap-6 overflow-y-auto shadow-[-4px_0_15px_rgba(0,0,0,0.02)] z-0">
            <div>
                <h2 class="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
                    State & Memory Telemetry
                </h2>
                <div class="grid grid-cols-2 gap-3">
                    <div class="p-3 rounded-lg border border-slate-100 bg-slate-50 flex justify-between items-center col-span-2 shadow-sm">
                        <div>
                            <div class="text-[11px] text-indigo-700 font-bold flex items-center gap-1">
                                <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse"></span>
                                Online Auto-Learning
                            </div>
                            <div class="text-[10px] text-slate-500">Updates every 5 mins</div>
                        </div>
                        <div class="text-right">
                            <div class="text-lg font-bold text-slate-700"><span id="statDocs">0</span> Docs</div>
                            <div class="text-[9px] text-slate-400">Last Update: <span id="statLastTraining">--</span> (x<span id="statTrainingCount">0</span>)</div>
                        </div>
                    </div>
                    <div class="p-3 rounded-lg border border-slate-100 bg-slate-50 flex justify-between items-center">
                        <div>
                            <div class="text-[10px] text-slate-500 font-medium">Sectors</div>
                            <div class="text-[10px] text-slate-400">Topic Groups</div>
                        </div>
                        <div class="text-xl font-bold text-slate-700" id="statSectors">0</div>
                    </div>
                    <div class="p-3 rounded-lg border border-slate-100 bg-slate-50 flex justify-between items-center">
                        <div>
                            <div class="text-[10px] text-slate-500 font-medium">Dynamic Cache</div>
                            <div class="text-[10px] text-slate-400">In-Memory</div>
                        </div>
                        <div class="text-xl font-bold text-indigo-600" id="statCache">0</div>
                    </div>
                    <div class="p-3 rounded-lg border border-indigo-100 bg-indigo-50 flex justify-between items-center col-span-2 shadow-sm">
                        <div>
                            <div class="text-[11px] text-indigo-700 font-bold">Priority Promoted</div>
                            <div class="text-[10px] text-indigo-500">High relevance items</div>
                        </div>
                        <div class="text-2xl font-bold text-indigo-700" id="statPromoted">0</div>
                    </div>
                    <div class="p-3 rounded-lg border border-slate-100 bg-slate-50 flex justify-between items-center">
                        <div>
                            <div class="text-[10px] text-slate-500 font-medium">Active (Norm)</div>
                            <div class="text-[10px] text-emerald-500">Standard status</div>
                        </div>
                        <div class="text-lg font-bold text-slate-600" id="statActive">0</div>
                    </div>
                    <div class="p-3 rounded-lg border border-slate-100 bg-slate-50 flex justify-between items-center">
                        <div>
                            <div class="text-[10px] text-slate-500 font-medium">Degraded</div>
                            <div class="text-[10px] text-orange-400">Low access frequency</div>
                        </div>
                        <div class="text-lg font-bold text-slate-600" id="statDegraded">0</div>
                    </div>
                    <div class="p-3 rounded-lg border border-slate-200 bg-slate-100 flex justify-between items-center col-span-2">
                        <div>
                            <div class="text-[11px] text-slate-600 font-bold">Archived (Excluded)</div>
                            <div class="text-[10px] text-slate-500">Removed from active compute</div>
                        </div>
                        <div class="text-xl font-bold text-slate-700" id="statArchived">0</div>
                    </div>
                </div>
            </div>

            <div class="flex-1 flex flex-col pt-2">
                <h2 class="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                    Process Stream
                </h2>
                <div class="bg-[#0f172a] text-[#38bdf8] p-4 rounded-xl flex-1 min-h-[250px] overflow-y-auto text-[11px] log-container shadow-inner border border-slate-800" id="logTerminal">
                    <div class="text-slate-400">System initialized. Awaiting queries...</div>
                </div>
            </div>
        </div>
    </main>

    <script>
        const searchForm = document.getElementById('searchForm');
        const queryInput = document.getElementById('queryInput');
        const resultsArea = document.getElementById('resultsArea');
        const logTerminal = document.getElementById('logTerminal');
        let visibleDocumentIds = [];

        function appendLogs(logs) {
            logs.forEach(log => {
                const div = document.createElement('div');
                div.className = 'mb-1.5 opacity-90 leading-tight';
                
                if(log.includes("関連セクター")) div.className += ' text-emerald-400';
                else if(log.includes("PID制御")) div.className += ' text-yellow-300';
                else if(log.includes("動的クラスタリング")) div.className += ' text-fuchsia-400';
                else if(log.includes("アーカイブ") || log.includes("計算間引き")) div.className += ' text-orange-400';
                
                div.innerHTML = `<span class="text-slate-500 mr-2">▶</span>${log}`;
                logTerminal.appendChild(div);
            });
            logTerminal.scrollTop = logTerminal.scrollHeight;
        }

        searchForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const query = queryInput.value.trim();
            if (!query) return;

            resultsArea.innerHTML = '<div class="text-center text-indigo-500 mt-16"><div class="animate-spin inline-block w-6 h-6 border-2 border-current border-t-transparent text-indigo-600 rounded-full mb-2"></div><br><span class="text-sm font-medium">Extracting Relevant Sectors...</span></div>';
            
            try {
                const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&visible=${visibleDocumentIds.join(',')}`);
                const data = await response.json();
                
                document.getElementById('metricsDisplay').innerHTML = `
                    <span class="bg-indigo-50 text-indigo-700 border border-indigo-200 px-2.5 py-1 rounded text-xs font-mono">Latency: ${data.metrics.latency_ms.toFixed(1)}ms</span>
                    <span class="bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 rounded text-xs font-mono">Source: ${data.metrics.source}</span>
                    ${data.metrics.k_used ? `<span class="bg-slate-100 text-slate-600 border border-slate-200 px-2.5 py-1 rounded text-xs font-mono">Depth (K): ${data.metrics.k_used}</span>` : ''}
                `;

                appendLogs(data.logs);
                resultsArea.innerHTML = '';
                visibleDocumentIds = [];

                if (data.results.length === 0) {
                    resultsArea.innerHTML = '<div class="text-center text-slate-500 mt-10">該当する情報が見つかりませんでした。</div>';
                    return;
                }

                data.results.forEach((result, index) => {
                    if(!result.is_clustered) visibleDocumentIds.push(result.id);
                    
                    const card = document.createElement('div');
                    card.className = `glass-panel p-5 rounded-xl fade-in relative overflow-hidden group `;
                    
                    if(result.is_clustered) card.className += 'bg-gradient-to-r from-fuchsia-50 to-white border-fuchsia-200';
                    else if(result.is_promoted) card.className += 'bg-gradient-to-r from-indigo-50 to-white border-indigo-200';
                    else card.className += 'bg-white border-slate-200';

                    card.style.animationDelay = `${index * 0.08}s`;
                    
                    let badge = '';
                    if(result.is_clustered) badge = `<span class="bg-fuchsia-100 text-fuchsia-700 text-[10px] px-2 py-1 rounded border border-fuchsia-200 font-bold uppercase tracking-wider flex items-center gap-1"><svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" viewBox="0 0 20 20" fill="currentColor"><path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zM11 13a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" /></svg>DYNAMIC CLUSTER</span>`;
                    else if(result.is_promoted) badge = `<span class="bg-indigo-100 text-indigo-700 text-[10px] px-2 py-1 rounded border border-indigo-200 font-bold uppercase tracking-wider flex items-center gap-1"><svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.381z" clip-rule="evenodd" /></svg>HIGH PRIORITY</span>`;
                    else badge = `<span class="bg-slate-100 text-slate-500 text-[10px] px-2 py-1 rounded border border-slate-200 font-mono">Score: ${result.score.toFixed(3)}</span>`;

                    card.innerHTML = `
                        <div class="flex justify-between items-start mb-2 relative z-10">
                            <h3 class="text-base font-bold text-slate-800 pr-4">${result.title}</h3>
                            <div class="shrink-0">${badge}</div>
                        </div>
                        <p class="text-sm text-slate-600 leading-relaxed relative z-10">${result.content}</p>
                        ${result.sector !== undefined ? `<div class="absolute bottom-2 right-3 text-[9px] text-slate-300 font-mono">Sector: ${result.sector}</div>` : ''}
                    `;
                    resultsArea.appendChild(card);
                });
                
                updateTelemetry();
            } catch (err) {
                resultsArea.innerHTML = `<div class="text-center text-red-500 mt-10 text-sm">Error: ${err.message}</div>`;
                appendLogs([`CRITICAL ERROR: ${err.message}`]);
            }
        });

        async function updateTelemetry() {
            try {
                const res = await fetch('/api/status');
                const status = await res.json();
                
                document.getElementById('statDocs').textContent = status.total_docs;
                document.getElementById('statSectors').textContent = status.sectors;
                document.getElementById('statCache').textContent = status.cached_queries;
                document.getElementById('statActive').textContent = status.memory_states.active;
                document.getElementById('statPromoted').textContent = status.memory_states.promoted;
                document.getElementById('statDegraded').textContent = status.memory_states.degraded;
                document.getElementById('statArchived').textContent = status.memory_states.archived;
                document.getElementById('timeStepDisplay').textContent = `[T=${status.time_step}]`;
                
                document.getElementById('statTrainingCount').textContent = status.training_count;
                document.getElementById('statLastTraining').textContent = status.last_training_time;
                
                if (status.cache_cleaned > 0) {
                    appendLogs([`System: ${status.cache_cleaned}件の劣化した動的キャッシュをGCしました。`]);
                }
            } catch (e) {
                console.error("Telemetry update failed", e);
            }
        }

        updateTelemetry();
        setInterval(updateTelemetry, 4000);
    </script>
</body>
</html>
"""

# ============================================================================
# 8. WebサーバーとAPIルーティング
# ============================================================================
class AdaptiveRAGRequestHandler(BaseHTTPRequestHandler):
    def _send_response(self, content, content_type='application/json', status=200):
        self.send_response(status)
        self.send_header('Content-type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        if isinstance(content, str): self.wfile.write(content.encode('utf-8'))
        else: self.wfile.write(json.dumps(content, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        parsed_path = urlparse(self.path)
        if parsed_path.path == '/':
            self._send_response(HTML_TEMPLATE, content_type='text/html')
        elif parsed_path.path == '/api/search':
            query_params = parse_qs(parsed_path.query)
            q = query_params.get('q', [''])[0]
            visible_str = query_params.get('visible', [''])[0]
            if not q:
                self._send_response({"error": "Query is required"}, status=400)
                return
            result = rag_pipeline.process_query(q, client_visible_docs=visible_str.split(',') if visible_str else [])
            self._send_response(result)
        elif parsed_path.path == '/api/status':
            self._send_response(rag_pipeline.get_system_status())
        else:
            self._send_response({"error": "Not Found"}, status=404)

    def log_message(self, format, *args): pass

def run_server(port=8000):
    server_address = ('', port)
    httpd = HTTPServer(server_address, AdaptiveRAGRequestHandler)
    
    # [NEW] 5分(300秒)ごとのオンライン学習スレッドの起動
    learning_thread = threading.Thread(target=auto_learning_worker, args=(rag_pipeline, 300), daemon=True)
    learning_thread.start()

    print("=" * 60)
    print(f"Adaptive RAG System Core v1.3 稼働開始")
    print(f"一般用語版 & 自動オンライン学習機能統合")
    print(f"ダッシュボードURL: http://localhost:{port}")
    print("=" * 60)
    try: httpd.serve_forever()
    except KeyboardInterrupt: pass
    finally: httpd.server_close()

if __name__ == '__main__':
    run_server()