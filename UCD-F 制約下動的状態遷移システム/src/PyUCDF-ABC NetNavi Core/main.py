import os
import json
import torch
import warnings
import threading
import time
import random
import urllib.request
import re
from datetime import datetime

warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# =====================================================================
# 自然言語処理エンジンのハイブリッド自動検出 (Fugashi or Janome)
# =====================================================================
TOKENIZER_TYPE = None
TOKENIZER_AVAILABLE = False

try:
    import fugashi
    import ipadic
    TOKENIZER_TYPE = "fugashi"
    TOKENIZER_AVAILABLE = True
except ImportError:
    try:
        from janome.tokenizer import Tokenizer
        TOKENIZER_TYPE = "janome"
        TOKENIZER_AVAILABLE = True
    except ImportError:
        TOKENIZER_TYPE = None
        TOKENIZER_AVAILABLE = False

# =====================================================================
# ハードウェア極限最適化
# =====================================================================
torch.set_num_threads(os.cpu_count() or 4)
torch.set_flush_denormal(True)

if torch.cuda.is_available():
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

POS_MAP = {"その他": 0, "名詞": 1, "動詞": 2, "形容詞": 3, "助詞": 4, "助動詞": 5, "感動詞": 6, "副詞": 7}
POSITIVE_WORDS = {"好き", "嬉しい", "楽しい", "良い", "最高", "元気", "笑う", "希望", "光"}
NEGATIVE_WORDS = {"嫌い", "悲しい", "痛い", "悪い", "最低", "怒る", "泣く", "絶望", "闇"}
FEEDBACK_POSITIVE = {"すごい", "いいね", "天才", "かわいい", "えらい", "正解", "そう"}
FEEDBACK_NEGATIVE = {"違う", "ダメ", "ちがう", "間違え", "やめろ", "意味不明"}

# CVM状態コード
STATE_B = "Birth"     # 誕生
STATE_G = "Growth"    # 成長
STATE_M = "Maturity"  # 成熟
STATE_D = "Decline"   # 衰退
STATE_X = "Death"     # 旅立ち（最大化）
STATE_S = "Standby"   # 待機・回復（スリープ）

# コンソール出力の競合を防ぐためのグローバルロック
console_lock = threading.Lock()

def safe_print(engine, message):
    """スレッドからの出力を綺麗に表示し、プロンプトを復元するヘルパー"""
    with console_lock:
        with engine.lock:
            cvm_state = engine.db.storageSoA["system"]["cvm_state"]
        prompt = f"\nあなた [{cvm_state} 期]: " if cvm_state != STATE_S else "\nあなた [Sleep]: "
        # 現在の行をキャリッジリターンで上書きクリアしてメッセージを表示
        print(f"\r{' ' * 70}\r{message}")
        print(prompt, end="", flush=True)

# =====================================================================
# 1. 自作インメモリDB (3-gram ＆ CVMライフサイクル対応)
# =====================================================================
class LuminaDB_InMem:
    def __init__(self, db_file="navi_memory.json"):
        self.db_file = db_file
        self.lock = threading.RLock()
        self.storageSoA = {
            "words": {"id": [], "surface": [], "pos": [], "polarity": [], "vA": [], "vB": [], "vC": [], "interest": []},
            "synapses": {}, 
            "knowledge_base": {"id": [], "text": [], "timestamp": []}, 
            "system": {
                "emotion": 0.0,
                "cycle": 1,                  
                "cvm_state": STATE_B,        
                "velocity": 5.0,             
                "accumulation": 0.0,         
                "fatigue": 0.0,              
                "max_l": 300.0,              
                "evolution_factor": 1.0      
            } 
        }
        self.load_from_disk()

    def load_from_disk(self):
        if os.path.exists(self.db_file):
            print(f"[System] 既存の電脳メモリ ({self.db_file}) をロードしています...")
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    imported_data = json.load(f)
                    
                    for table in ["words", "knowledge_base", "system"]:
                        if table in imported_data:
                            if isinstance(self.storageSoA[table], dict) and isinstance(imported_data[table], dict):
                                self.storageSoA[table].update(imported_data[table])
                            else:
                                self.storageSoA[table] = imported_data[table]
                    
                    if "synapses" in imported_data:
                        self.storageSoA["synapses"] = imported_data["synapses"]
            except Exception as e:
                print(f"[System] 電脳メモリの復元中にエラーが発生しました: {e}。新規に初期化します。")
                self.initialize_default_brain()
            
            word_count = len(self.storageSoA["words"].get("id", []))
            default_values = {
                "pos": 0, "polarity": 0.0, "vA": 100.0, "vB": 10.0, "vC": 0, "interest": 5.0
            }
            for col, default_val in default_values.items():
                if col not in self.storageSoA["words"]:
                    self.storageSoA["words"][col] = []
                current_len = len(self.storageSoA["words"][col])
                if current_len < word_count:
                    self.storageSoA["words"][col].extend([default_val] * (word_count - current_len))
        else:
            self.initialize_default_brain()

    def initialize_default_brain(self):
        print("[System] 新規ニューラルネットワークを初期化しました。")
        self.storageSoA = {
            "words": {"id": [], "surface": [], "pos": [], "polarity": [], "vA": [], "vB": [], "vC": [], "interest": []},
            "synapses": {}, 
            "knowledge_base": {"id": [], "text": [], "timestamp": []}, 
            "system": {
                "emotion": 0.0,
                "cycle": 1,
                "cvm_state": STATE_B,
                "velocity": 5.0,
                "accumulation": 0.0,
                "fatigue": 0.0,
                "max_l": 300.0,
                "evolution_factor": 1.0
            } 
        }
        self.insert_word(0, "__BOS__", 0, 0.0, 255.0, 255.0, 0, 0.0)
        self.insert_word(1, "__EOS__", 0, 0.0, 255.0, 255.0, 0, 0.0)

    def commit(self):
        with self.lock:
            try:
                tmp_file = self.db_file + ".tmp"
                with open(tmp_file, 'w', encoding='utf-8') as f:
                    json.dump(self.storageSoA, f, ensure_ascii=False, separators=(',', ':'))
                if os.path.exists(tmp_file):
                    if os.path.exists(self.db_file):
                        os.remove(self.db_file)
                    os.rename(tmp_file, self.db_file)
            except Exception as e:
                pass

    def commit_snapshot(self, snapshot_data, callback):
        try:
            tmp_file = self.db_file + ".tmp"
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(snapshot_data, f, ensure_ascii=False, separators=(',', ':'))
            if os.path.exists(tmp_file):
                if os.path.exists(self.db_file):
                    os.remove(self.db_file)
                os.rename(tmp_file, self.db_file)
        except Exception:
            pass
        finally:
            if callback: callback()

    def insert_word(self, w_id, surface, pos_code, polarity, va, vb, vc, interest):
        tbl = self.storageSoA["words"]
        tbl["id"].append(w_id)
        tbl["surface"].append(surface)
        tbl["pos"].append(pos_code)
        tbl["polarity"].append(polarity)
        tbl["vA"].append(va)
        tbl["vB"].append(vb)
        tbl["vC"].append(vc)
        tbl["interest"].append(interest)

# =====================================================================
# 2. ネットナビ・コアエンジン (CVMハイブリッドモデル)
# =====================================================================
class PyUCDF_NaviBrain:
    def __init__(self, max_vocab=10000):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.max_vocab = max_vocab
        self.lock = threading.RLock()
        
        self.is_saving = False
        self.last_save_time = 0
        self.needs_save = False
        
        if TOKENIZER_AVAILABLE:
            if TOKENIZER_TYPE == "fugashi":
                self.tagger = fugashi.Tagger(ipadic.MECAB_ARGS)
            else:
                self.tagger = Tokenizer()
        else:
            self.tagger = None
        
        self.db = LuminaDB_InMem(db_file="navi_memory.json")
        self.vocab_size = len(self.db.storageSoA["words"]["id"])
        
        self.state_vA = torch.zeros(max_vocab, dtype=torch.float32, device=self.device)
        self.state_vB = torch.zeros(max_vocab, dtype=torch.float32, device=self.device)
        self.state_vC = torch.zeros(max_vocab, dtype=torch.int32, device=self.device)
        self.interest_vector = torch.zeros(max_vocab, dtype=torch.float32, device=self.device)
        self.word_pos = torch.zeros(max_vocab, dtype=torch.long, device=self.device)
        self.word_polarity = torch.zeros(max_vocab, dtype=torch.float32, device=self.device)
        
        self.context_topic_vector = torch.zeros(max_vocab, dtype=torch.float32, device=self.device)
        self.ng_words = {"バグ", "死ぬ", "殺す", "馬鹿", "アホ", "クソ"}
        self.last_thought_route = []
        
        self._sync_db_to_tensor()

    def _sync_db_to_tensor(self):
        words_tbl = self.db.storageSoA["words"]
        v = min(len(words_tbl["id"]), self.max_vocab)
        self.vocab_size = v
        
        if v > 0:
            self.state_vA[:v] = torch.tensor(words_tbl["vA"][:v], dtype=torch.float32, device=self.device)
            self.state_vB[:v] = torch.tensor(words_tbl["vB"][:v], dtype=torch.float32, device=self.device)
            self.state_vC[:v] = torch.tensor(words_tbl["vC"][:v], dtype=torch.int32, device=self.device)
            self.interest_vector[:v] = torch.tensor(words_tbl["interest"][:v], dtype=torch.float32, device=self.device)
            self.word_pos[:v] = torch.tensor(words_tbl["pos"][:v], dtype=torch.long, device=self.device)
            self.word_polarity[:v] = torch.tensor(words_tbl["polarity"][:v], dtype=torch.float32, device=self.device)

    def _sync_tensor_to_db(self):
        v = self.vocab_size
        words_tbl = self.db.storageSoA["words"]
        words_tbl["vA"][:v] = self.state_vA[:v].cpu().tolist()
        words_tbl["vB"][:v] = self.state_vB[:v].cpu().tolist()
        words_tbl["vC"][:v] = self.state_vC[:v].cpu().tolist()
        words_tbl["interest"][:v] = self.interest_vector[:v].cpu().tolist()

    def _on_save_complete(self):
        self.is_saving = False

    def queue_async_save(self, force=False):
        current_time = time.time()
        if not force and current_time - self.last_save_time < 10.0:
            self.needs_save = True
            return

        with self.lock:
            if self.is_saving: 
                self.needs_save = True
                return
            self.is_saving = True
            self.needs_save = False
            self.last_save_time = current_time

            self._sync_tensor_to_db()
            snapshot = {
                "words": {k: list(v) for k, v in self.db.storageSoA["words"].items()},
                "synapses": {k: {nk: dict(nv) for nk, nv in v.items()} for k, v in self.db.storageSoA["synapses"].items()},
                "knowledge_base": {k: list(v) for k, v in self.db.storageSoA["knowledge_base"].items()},
                "system": dict(self.db.storageSoA["system"])
            }
        
        threading.Thread(target=self.db.commit_snapshot, args=(snapshot, self._on_save_complete), daemon=True).start()

    # --- 【コード改善】形態素解析ロジックの共通化（DRY原則） ---
    def _tokenize(self, text):
        """FugashiとJanomeの差異を吸収し、(表層形, 品詞) のタプルを返すジェネレーター"""
        if not self.tagger:
            return
            
        if TOKENIZER_TYPE == "fugashi":
            for word in self.tagger(text):
                yield word.surface, word.feature.pos1
        else: # janome
            for token in self.tagger.tokenize(text):
                yield token.surface, token.part_of_speech.split(',')[0]

    def get_word_id(self, surface, pos_str):
        tbl = self.db.storageSoA["words"]
        try:
            return tbl["surface"].index(surface)
        except ValueError:
            if self.vocab_size >= self.max_vocab: return -1
            pos_code = POS_MAP.get(pos_str, 0)
            polarity = 1.0 if surface in POSITIVE_WORDS else (-1.0 if surface in NEGATIVE_WORDS else 0.0)
            
            init_interest = 30.0 if self.db.storageSoA["system"]["cvm_state"] == STATE_B else 20.0
            self.db.insert_word(self.vocab_size, surface, pos_code, polarity, 100.0, 10.0, 0, init_interest)
            
            self.state_vA[self.vocab_size] = 100.0
            self.state_vB[self.vocab_size] = 10.0
            self.state_vC[self.vocab_size] = 0
            self.interest_vector[self.vocab_size] = init_interest
            self.word_pos[self.vocab_size] = pos_code
            self.word_polarity[self.vocab_size] = polarity
            
            new_id = self.vocab_size
            self.vocab_size += 1
            self.needs_save = True 
            return new_id

    def inject_entropy(self):
        with self.lock:
            if self.vocab_size <= 2: return
            noise = torch.rand(self.vocab_size, device=self.device)
            stimulus = (noise < 0.01).float() * (torch.rand(self.vocab_size, device=self.device) * 30.0)
            self.state_vA[:self.vocab_size] = torch.clamp(self.state_vA[:self.vocab_size] + stimulus, max=255.0)
            
            interest_stimulus = (noise < 0.005).float() * 5.0
            self.interest_vector[:self.vocab_size] = torch.clamp(self.interest_vector[:self.vocab_size] + interest_stimulus, max=50.0)
            self.db.storageSoA["system"]["emotion"] = max(-1.0, min(1.0, self.db.storageSoA["system"]["emotion"] + random.uniform(-0.05, 0.05)))

    def _push_synapse_3gram(self, id1, id2, to_id, weight=1.0, is_knowledge=False):
        key = f"{id1},{id2}"
        synapses = self.db.storageSoA["synapses"]
        if key not in synapses:
            synapses[key] = {}
        
        to_str = str(to_id)
        if to_str not in synapses[key]:
            synapses[key][to_str] = {"w": weight, "is_k": is_knowledge}
        else:
            synapses[key][to_str]["w"] += weight
            if is_knowledge:
                synapses[key][to_str]["is_k"] = True

    # =====================================================================
    # CVM (Cyclic Velocity Model) 制御システム
    # =====================================================================
    def cvm_update(self, cost_l, is_learning=False):
        with self.lock:
            sys = self.db.storageSoA["system"]
            state = sys["cvm_state"]
            
            if state == STATE_S:
                return
                
            eff = sys["evolution_factor"]
            v_ratio = sys["velocity"] / 10.0
            fatigue_gain = (v_ratio ** 2) * 2.0 / eff 
            sys["fatigue"] = min(100.0, sys["fatigue"] + fatigue_gain)
            
            if is_learning:
                sys["accumulation"] = min(sys["max_l"], sys["accumulation"] + (cost_l * (sys["velocity"] / 5.0) * eff))
            
            if sys["accumulation"] >= sys["max_l"]:
                sys["cvm_state"] = STATE_X
                sys["velocity"] = 10.0 
            elif sys["fatigue"] >= 80.0:
                sys["cvm_state"] = STATE_D
                sys["velocity"] = max(1.0, sys["velocity"] - 0.5)
            elif sys["accumulation"] >= (sys["max_l"] * 0.6):
                sys["cvm_state"] = STATE_M
            elif sys["accumulation"] >= (sys["max_l"] * 0.1):
                sys["cvm_state"] = STATE_G
            else:
                sys["cvm_state"] = STATE_B

    def cvm_reborn(self, forced=False):
        sys = self.db.storageSoA["system"]
        if sys["cvm_state"] != STATE_S and not forced:
            return False, "まだ眠っていません（待機状態に入る必要があります）"
            
        accum = sys["accumulation"]
        max_l = sys["max_l"]
        
        evolution_gain = (accum / max_l) * 0.2
        sys["evolution_factor"] = round(sys["evolution_factor"] + evolution_gain, 2)
        sys["cycle"] += 1
        sys["cvm_state"] = STATE_B
        sys["accumulation"] = 0.0
        sys["fatigue"] = 0.0
        sys["velocity"] = 5.0
        sys["max_l"] = round(sys["max_l"] * 1.15, 1) 
        
        self.interest_vector[:self.vocab_size] = torch.clamp(self.interest_vector[:self.vocab_size] + 15.0, max=50.0)
        
        self.queue_async_save(force=True)
        return True, f"第 {sys['cycle']} 世代のネットナビへ再誕しました！（進化係数: {sys['evolution_factor']} / 想い出限界: {sys['max_l']}）"

    def cvm_hibernate(self):
        sys = self.db.storageSoA["system"]
        sys["cvm_state"] = STATE_S
        sys["velocity"] = 1.0 
        self.queue_async_save(force=True)
        return f"電脳空間スリープモードに入りました。不応期（待機）の経過を待ち、次世代に生まれ変わりましょう。(/reborn でいつでも再誕可能)"

    def verify_and_reinforce_thought(self):
        if not self.last_thought_route: return ""
        knowledge_hits = 0
        total_transitions = len(self.last_thought_route)
        synapses = self.db.storageSoA["synapses"]
        
        for id1, id2, to_id in self.last_thought_route:
            key = f"{id1},{id2}"
            to_str = str(to_id)
            if key in synapses and to_str in synapses[key]:
                info = synapses[key][to_str]
                if info.get("is_k", False):
                    knowledge_hits += 1
                    info["w"] *= 1.5
                    self.state_vB[to_id] = torch.clamp(self.state_vB[to_id] + 5.0, max=255.0)
                    
        hit_ratio = knowledge_hits / total_transitions if total_transitions > 0 else 0
        if hit_ratio >= 0.5 and total_transitions >= 2:
            self.db.storageSoA["system"]["emotion"] = min(1.0, self.db.storageSoA["system"]["emotion"] + 0.2)
            self.cvm_update(cost_l=15.0, is_learning=True)
            return f"[System] (自己検証: ネット知識との文脈一致率 {hit_ratio*100:.0f}% ―― 文脈を確信し長期記憶へ定着させました！)"
        return ""

    def process_rlhf_feedback(self, text):
        if not self.last_thought_route: return False
        is_pos = any(fw in text for fw in FEEDBACK_POSITIVE)
        is_neg = any(fw in text for fw in FEEDBACK_NEGATIVE)
        synapses = self.db.storageSoA["synapses"]
        
        if is_pos or is_neg:
            factor = 2.0 if is_pos else 0.0
            safe_print(self, f"[System] ({'褒められたため文脈と興味を強化' if is_pos else '叱られたため文脈を消去'}しました)")
            for id1, id2, to_id in self.last_thought_route:
                key = f"{id1},{id2}"
                to_str = str(to_id)
                if key in synapses and to_str in synapses[key]:
                    synapses[key][to_str]["w"] *= factor
                    if is_pos:
                        synapses[key][to_str]["is_k"] = True 
                if is_pos: 
                    self.state_vB[to_id] = torch.clamp(self.state_vB[to_id] + 15.0, max=255.0)
                    self.interest_vector[to_id] = torch.clamp(self.interest_vector[to_id] + 10.0, max=50.0)
            
            if is_pos:
                self.cvm_update(cost_l=25.0, is_learning=True)
            self.last_thought_route = []
            return True
        return False

    def learn_from_input(self, text, is_self_thought=False, is_network_learning=False, is_dream=False, is_teach=False):
        with self.lock:
            if self.db.storageSoA["system"]["cvm_state"] == STATE_S:
                return
                
            if not self.tagger: return
            if not is_self_thought and not is_network_learning and not is_dream and not is_teach:
                if self.process_rlhf_feedback(text): return
            
            self.context_topic_vector[:self.vocab_size] *= 0.8 
            
            ids = []
            
            # --- 【コード改善】共通化されたトークナイザーを使用 ---
            for surface, pos_str in self._tokenize(text):
                if surface in self.ng_words or surface.strip() == "" or surface in ["、", "・", "「", "」", "（", "）", "。"]: continue
                # 【バグ修正】is_teach & pos_str のTypoを論理演算子(and)に完全修正
                if is_network_learning and not is_teach and pos_str == '名詞' and random.random() > 0.2: continue
                
                w_id = self.get_word_id(surface, pos_str)
                if w_id != -1: 
                    ids.append(w_id)
                    if pos_str in ["名詞", "動詞"]: 
                        self.context_topic_vector[w_id] += 2.0
                        self.interest_vector[w_id] = torch.clamp(self.interest_vector[w_id] + 1.0, max=50.0)

            if len(ids) < 1: return
            
            extended_ids = [0, 0] + ids + [1]
            for i in range(len(extended_ids) - 2):
                id1, id2, to_id = extended_ids[i], extended_ids[i+1], extended_ids[i+2]
                self._push_synapse_3gram(id1, id2, to_id, 1.0, is_knowledge=(is_network_learning or is_teach))

            for i in range(len(ids)):
                for j in range(i + 2, min(i + 5, len(ids))):
                    self._push_synapse_3gram(0, ids[i], ids[j], 0.1, is_knowledge=(is_network_learning or is_teach))

            idx_tensor = torch.tensor(list(set(ids)), dtype=torch.long, device=self.device)
            self.state_vA[idx_tensor] = torch.clamp(self.state_vA[idx_tensor] + 50.0, max=255.0)
            self.state_vB[idx_tensor] = torch.clamp(self.state_vB[idx_tensor] + 1.0, max=255.0)

            self.cvm_update(cost_l=float(len(ids)), is_learning=True)

            if not is_self_thought and not is_dream:
                self.state_vC[:self.vocab_size] += 1
                decay_mask = (self.state_vC[:self.vocab_size] > (5 + (self.state_vB[:self.vocab_size].to(torch.int32) // 10))).to(torch.int32)
                self.state_vA[:self.vocab_size] = torch.clamp(self.state_vA[:self.vocab_size] - decay_mask.float() * 2.0, min=1.0)
                self.state_vC[:self.vocab_size] = torch.where(decay_mask > 0, torch.zeros_like(self.state_vC[:self.vocab_size]), self.state_vC[:self.vocab_size])
                
                synapses = self.db.storageSoA["synapses"]
                for key in list(synapses.keys()):
                    for to_str in list(synapses[key].keys()):
                        synapses[key][to_str]["w"] *= 0.997
                        if synapses[key][to_str]["w"] < 0.05:
                            del synapses[key][to_str]
                    if not synapses[key]:
                        del synapses[key]
                        
                self.interest_vector[:self.vocab_size] *= 0.99 

            self.queue_async_save()

    def teach_knowledge(self, text):
        if self.db.storageSoA["system"]["cvm_state"] == STATE_S:
            return
            
        with self.lock:
            k_id = len(self.db.storageSoA["knowledge_base"]["id"])
            self.db.storageSoA["knowledge_base"]["id"].append(k_id)
            self.db.storageSoA["knowledge_base"]["text"].append(f"教えてもらった知識：「{text}」")
            self.db.storageSoA["knowledge_base"]["timestamp"].append(time.time())
            
        self.learn_from_input(text, is_teach=True)

    def search_and_store_knowledge(self):
        try:
            works = {
                "『羅生門』(芥川龍之介)": "https://www.aozora.gr.jp/cards/000879/files/127_15260.html",
                "『やまなし』(宮沢賢治)": "https://www.aozora.gr.jp/cards/000081/files/46605_31178.html",
                "『学問のすすめ』(福沢諭吉)": "https://www.aozora.gr.jp/cards/000296/files/47061_28378.html",
                "『ドグラ・マグラ』(夢野久作)": "https://www.aozora.gr.jp/cards/000096/files/2093_28841.html",
                "『人間失格』(太宰治)": "https://www.aozora.gr.jp/cards/000035/files/1567_14913.html"
            }
            title = random.choice(list(works.keys()))
            url = works[title]
            
            req = urllib.request.Request(url, headers={'User-Agent': 'NetNavi-Knowledge-Search/1.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                html = response.read().decode('shift_jis', errors='ignore')
                text = re.sub(r'<[^>]*>', '', html)
                text = re.sub(r'《[^》]*》', '', text) 
                text = re.sub(r'［＃[^］]*］', '', text) 
                
                start_idx = random.randint(0, max(0, len(text) - 500))
                extract = text[start_idx:start_idx+150].strip()
                extract = re.sub(r'\s+', ' ', extract)
                
                knowledge_text = f"{title}には、「{extract}」という一節があるんだ。"
                
                with self.lock:
                    k_id = len(self.db.storageSoA["knowledge_base"]["id"])
                    self.db.storageSoA["knowledge_base"]["id"].append(k_id)
                    self.db.storageSoA["knowledge_base"]["text"].append(knowledge_text)
                    self.db.storageSoA["knowledge_base"]["timestamp"].append(time.time())
                
                self.cvm_update(cost_l=20.0, is_learning=True)
                self.queue_async_save()
                return title
        except Exception:
            pass
        return None

    def reflect_knowledge(self, temperature=1.1, growth_stage=4):
        with self.lock:
            if self.db.storageSoA["system"]["cvm_state"] == STATE_S:
                return "……"
                
            topic = ""
            kb = self.db.storageSoA["knowledge_base"]
            if not kb["id"]:
                return "……"
            
            idx = random.randint(0, len(kb["id"]) - 1)
            text = kb["text"][idx]
            
            topics = []
            for surface, pos_str in self._tokenize(text):
                if pos_str == '名詞' and len(surface) > 1 and surface not in self.ng_words:
                    topics.append(surface)
            
            topic = random.choice(topics) if topics else "これ"
            w_id = self.get_word_id(topic, "名詞")
            if w_id != -1:
                self.context_topic_vector[w_id] += 10.0
                self.interest_vector[w_id] = torch.clamp(self.interest_vector[w_id] + 15.0, max=50.0)
                
        thought = self.generate_response(temperature=temperature, growth_stage=growth_stage)
        if thought == "……":
            return "……"
        return f"『{topic}』について考えてたんだ。{thought}"

    def generate_response(self, temperature=0.8, growth_stage=4, is_dream=False):
        with self.lock:
            sys = self.db.storageSoA["system"]
            
            if sys["cvm_state"] == STATE_S:
                return "（ナビは現在スリープ中です。起こすには /reborn コマンドを入力してください）"
                
            if self.vocab_size <= 2: return "……"
            
            current_state = sys["cvm_state"]
            if current_state == STATE_D:
                growth_stage = 2 
            elif current_state == STATE_B:
                growth_stage = min(growth_stage, 3) 
            
            va_normalized = self.state_vA[:self.vocab_size] / 255.0
            current_emotion = sys["emotion"]
            current_hour = datetime.now().hour
            
            chosen_words = []
            self.last_thought_route = []
            id1, id2 = 0, 0 
            
            max_words = 30
            if growth_stage == 1: max_words = 1
            elif growth_stage == 2: max_words = 2
            elif growth_stage == 3: max_words = 5
            
            used_words_in_turn = set()
            low_confidence_count = 0
            
            step = 0
            while step < max_words:
                key = f"{id1},{id2}"
                logits = torch.zeros(self.vocab_size, dtype=torch.float32, device=self.device) - 1e9
                
                targets = synapses = self.db.storageSoA["synapses"].get(key, {})
                if targets:
                    for to_str, info in targets.items():
                        to_id = int(to_str)
                        if to_id < self.vocab_size:
                            logits[to_id] = torch.log1p(torch.tensor(info["w"], device=self.device))
                else:
                    backoff_key = f"0,{id2}"
                    backoff_targets = self.db.storageSoA["synapses"].get(backoff_key, {})
                    if backoff_targets:
                        for to_str, info in backoff_targets.items():
                            to_id = int(to_str)
                            if to_id < self.vocab_size:
                                logits[to_id] = torch.log1p(torch.tensor(info["w"], device=self.device)) - 1.0
                    else:
                        logits[2:] = torch.log1p(self.state_vA[2:self.vocab_size]) - 5.0
                
                logits[0] = -1e9 
                
                next_pos = self.word_pos[:self.vocab_size]
                if growth_stage <= 2:
                    logits[next_pos == POS_MAP["助詞"]] = -1e9
                    if growth_stage == 1:
                        logits[next_pos == POS_MAP["名詞"]] += 2.0
                        logits[next_pos == POS_MAP["感動詞"]] += 2.0
                elif growth_stage == 3:
                    logits[next_pos == POS_MAP["助詞"]] -= 2.0
                
                curr_pos = self.word_pos[id2].item()
                if curr_pos == POS_MAP["助詞"]:
                    logits[next_pos == POS_MAP["助詞"]] = -1e9 
                elif curr_pos == POS_MAP["名詞"]:
                    legal_mask = (next_pos == POS_MAP["助詞"]) | (next_pos == POS_MAP["動詞"]) | (next_pos == POS_MAP["助動詞"]) | (next_pos == POS_MAP["その他"]) | (next_pos == POS_MAP["名詞"])
                    
                    logits[torch.logical_not(legal_mask)] -= 3.0
                    logits[next_pos == POS_MAP["名詞"]] -= 0.5 
                
                for uid in used_words_in_turn:
                    if self.word_pos[uid].item() in [POS_MAP["名詞"], POS_MAP["動詞"], POS_MAP["形容詞"]]:
                        logits[uid] -= 3.0 

                logits += self.context_topic_vector[:self.vocab_size] * 1.5
                if is_dream:
                    logits += (self.state_vB[:self.vocab_size] / 255.0) * 5.0
                else:
                    logits += (self.interest_vector[:self.vocab_size] / 50.0) * 3.0
                logits += self.word_polarity[:self.vocab_size] * current_emotion * 2.0
                
                if id2 == 0 and not is_dream:
                    try:
                        greet = "おはよう" if 5<=current_hour<=10 else ("こんにちは" if 11<=current_hour<=17 else "こんばんは")
                        g_idx = self.db.storageSoA["words"]["surface"].index(greet)
                        if g_idx < self.vocab_size: logits[g_idx] += 2.0
                    except ValueError: pass

                # アンダーフロー時のセーフティネット強化
                if logits.max() <= -1e8:
                     logits[2:] = torch.log1p(self.state_vA[2:self.vocab_size])

                probs = torch.softmax(logits / temperature, dim=0)
                
                mutation_rate = 0.15 if is_dream else 0.03
                va_probs = va_normalized.clone()
                va_probs[0] = 0.0
                if va_probs.sum() > 0: va_probs /= va_probs.sum()
                else: va_probs = probs
                probs = probs * (1.0 - mutation_rate) + va_probs * mutation_rate
                
                if torch.isnan(probs).any() or probs.sum() == 0: 
                    probs = torch.ones_like(probs) / len(probs)
                    probs[0] = 0.0
                
                next_id = torch.multinomial(probs, 1).item()
                
                prob_val = probs[next_id].item()
                if prob_val < 0.05:
                    low_confidence_count += 1
                else:
                    low_confidence_count = 0
                
                if next_id == 1: 
                    self.last_thought_route.append((id1, id2, 1))
                    break
                    
                surface = self.db.storageSoA["words"]["surface"][next_id]
                chosen_words.append(surface)
                used_words_in_turn.add(next_id)
                self.last_thought_route.append((id1, id2, next_id))
                
                if low_confidence_count >= 2 and growth_stage >= 3 and step < max_words - 5:
                    correction_words = ["……いや、", "……じゃなくて、", "……というか、"]
                    chosen_words.append(random.choice(correction_words))
                    id1, id2 = 0, 0 
                    low_confidence_count = 0
                    used_words_in_turn.clear() 
                    max_words += 5 
                    step += 1
                    continue
                
                with torch.no_grad():
                    self.interest_vector[next_id] = max(0.0, self.interest_vector[next_id].item() - 1.0)
                    
                id1, id2 = id2, next_id
                step += 1
                
            if not chosen_words:
                self.last_thought_route = []
                return "……"
            return "".join(chosen_words)

# =====================================================================
# エントロピー収穫デーモン (語彙検索 & 知識検索 & 振り返り)
# =====================================================================
def shadow_harvester_worker(engine, config):
    aozora_urls = [
        "https://www.aozora.gr.jp/cards/000081/files/43754_17659.html", 
        "https://www.aozora.gr.jp/cards/000081/files/456_15050.html",   
        "https://www.aozora.gr.jp/cards/000148/files/773_14560.html"    
    ]
    last_vocab_time = time.time()
    last_thought_time = time.time()
    last_knowledge_time = time.time()
    last_reflect_time = time.time()
    
    last_periodic_save_time = time.time()
    
    while True:
        time.sleep(1)
        current_time = time.time()
        
        with engine.lock:
            sys_state = engine.db.storageSoA["system"]["cvm_state"]
            velocity = engine.db.storageSoA["system"]["velocity"]
            accumulation = engine.db.storageSoA["system"]["accumulation"]
            
        if current_time - last_periodic_save_time >= 10.0:
            if engine.needs_save:
                engine.queue_async_save()
            last_periodic_save_time = current_time
        
        if sys_state == STATE_S:
            continue
            
        if config.get("net_enabled", False) and current_time - last_vocab_time >= config.get("vocab_interval", 300):
            engine.inject_entropy()
            try:
                url = random.choice(aozora_urls)
                req = urllib.request.Request(url, headers={'User-Agent': 'NetNavi-Vocab-Learner/1.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    html = response.read().decode('shift_jis', errors='ignore')
                    text = re.sub(r'<[^>]*>', '', html)
                    text = re.sub(r'《[^》]*》', '', text) 
                    text = re.sub(r'［＃[^］]*］', '', text) 
                    chunk = text[random.randint(0, max(0, len(text) - 1000)):][:1000]
                    engine.learn_from_input(chunk, is_network_learning=True)
            except Exception: pass
            last_vocab_time = current_time

        if config.get("net_enabled", False) and current_time - last_knowledge_time >= config.get("knowledge_interval", 600):
            title = engine.search_and_store_knowledge()
            if title:
                safe_print(engine, f"[System] (バックグラウンドで{title}の知識を検索し、知識ベースに保存しました)")
            last_knowledge_time = current_time

        v_modifier = max(0.5, 2.0 - (velocity / 5.0)) 
        reflect_interval = config.get("reflect_interval", 300) * v_modifier
        if current_time - last_reflect_time >= reflect_interval:
            engine.inject_entropy()
            reflection = engine.reflect_knowledge(temperature=1.1, growth_stage=config.get("growth_stage", 4))
            if reflection != "……":
                engine.learn_from_input(reflection, is_self_thought=True)
                engine.last_thought_route = []
                safe_print(engine, f"[Navi 🤔(振り返り)]: {reflection}")
            last_reflect_time = current_time
        
        thought_interval = config.get("thought_interval", 30) * v_modifier
        if current_time - last_thought_time >= thought_interval:
            engine.inject_entropy()
            
            time_since_last_input = current_time - config.get("last_user_input_time", current_time)
            is_dreaming = time_since_last_input > 180 
            
            temp = 1.5 if is_dreaming else 1.1
            
            response_text = engine.generate_response(temperature=temp, growth_stage=config.get("growth_stage", 4), is_dream=is_dreaming)
            if response_text != "……":
                engine.cvm_update(cost_l=0.0) 
                
                if sys_state == STATE_X:
                    msg = (f"[Navi 🌟(最大化・旅立ち)]: あなたと過ごしたすべての思い出（想い出量: {accumulation:.1f}）が満ちました。\n"
                           "                  私は一度、この時代の記録を結晶化して電脳スリープに入ります。\n"
                           "                  また次の新しい世代で会いましょう！\n"
                           "[System] (ナビが待機状態に入りました。「/reborn」と打つことで次の世代に生まれ変わらせることができます)")
                    safe_print(engine, msg)
                    engine.cvm_hibernate()
                    last_thought_time = current_time
                    continue
                
                engine.learn_from_input(response_text, is_self_thought=True, is_dream=is_dreaming)
                eureka_msg = engine.verify_and_reinforce_thought()
                engine.last_thought_route = [] 
                
                if is_dreaming:
                    em_str = "💤(夢)"
                else:
                    cvm_to_emoji = {
                        STATE_B: "🌱(誕生)",
                        STATE_G: "🏃(成長)",
                        STATE_M: "👑(成熟)",
                        STATE_D: "😰(お疲れ)",
                        STATE_X: "🌟(旅立ち)",
                        STATE_S: "💤(睡眠)"
                    }
                    em_str = cvm_to_emoji.get(sys_state, "😐")
                    
                output_str = f"[Navi {em_str}]: {response_text}"
                if eureka_msg:
                    output_str += eureka_msg
                safe_print(engine, output_str)
                
            last_thought_time = current_time

def print_help():
    print("\n--- 【全コマンド案内】 ---")
    print(" /net [on/off]   : ネット検索機能の有効/無効を切り替え (デフォルト: オフ)")
    print(" /vocab [秒数]   : 通常検索(語彙取得)の頻度を設定 (例: /vocab 300)")
    print(" /knowledge [秒] : 知識検索(データ保存)の頻度を設定 (例: /knowledge 600)")
    print(" /reflect [秒数] : 知識ベースを振り返る頻度を設定 (例: /reflect 300)")
    print(" /thought [秒数] : 通常の自律思考(独り言)の頻度を設定 (例: /thought 30)")
    print(" /stage [1-4]    : 言語野の成長段階を指定 (1:赤ちゃん 〜 4:完全体)")
    print(" /teach [内容]   : ユーザーが直接ナビに知識を教える (例: /teach リンゴは赤い)")
    print(" /cvm            : 現在のCVMライフサイクル状態を表示 (世代、お疲れ度、想い出蓄積量、V)")
    print(" /reborn         : スリープ状態から次世代の体へ生まれ変わる（CVM Rebirth）")
    print(" /hibernate      : ナビを強制的に眠らせる（CVM Standby）")
    print(" /help           : このコマンド一覧を表示")
    print(" exit, quit      : プラグアウトして終了")
    print("--------------------------\n")

# =====================================================================
# 実行部
# =====================================================================
if __name__ == "__main__":
    os.system('cls' if os.name == 'nt' else 'clear')
    print("========================================")
    print("   PyUCDF ネットナビ (超高速・完全堅牢版)")
    print("========================================")
    
    if TOKENIZER_AVAILABLE:
        print(f"[System] 形態素解析エンジンとして '{TOKENIZER_TYPE}' を検出しました。正常に動作可能です。")
    else:
        print("[警告] 'fugashi' も 'janome' もインストールされていません。")
        print("        ナビが会話を認識できません。`pip install janome` を実行してください。")
        
    engine = PyUCDF_NaviBrain(max_vocab=10000)
    system_config = {
        "vocab_interval": 300,      
        "knowledge_interval": 600,  
        "reflect_interval": 300,    
        "thought_interval": 30,     
        "growth_stage": 4,          
        "last_user_input_time": time.time(),
        "net_enabled": False        
    } 
    
    harvester_thread = threading.Thread(target=shadow_harvester_worker, args=(engine, system_config), daemon=True)
    harvester_thread.start()
    
    print("\n[System] 起動完了。CVM（循環速度モデル）生命活動エンジンが完全同期しました。")
    print("[System] ※デフォルトでネット検索は【オフ】になっています。「/net on」で有効化できます。")
    print_help()
    
    while True:
        try:
            with console_lock:
                with engine.lock:
                    cvm_state = engine.db.storageSoA["system"]["cvm_state"]
                user_prompt_header = f"\nあなた [{cvm_state} 期]: " if cvm_state != STATE_S else "\nあなた [Sleep]: "
                print(user_prompt_header, end="", flush=True)
                
            user_input = input()
            system_config["last_user_input_time"] = time.time()
            
            if user_input.lower() in ['exit', 'quit', '終了']:
                engine.queue_async_save(force=True)
                time.sleep(1) 
                print("\n[Navi]: （ログアウトしました）")
                break
                
            if user_input.strip() == '/help':
                print_help()
                continue
                
            if user_input.strip() == '/cvm':
                with engine.lock:
                    s = dict(engine.db.storageSoA["system"])
                print("\n--- 【CVM 電脳生命体ステータス】 ---")
                print(f"  世代 (Cycle)      : 第 {s['cycle']} 世代")
                print(f"  現在の状態 (State) : {s['cvm_state']}")
                print(f"  活動レベル (Velocity): {s['velocity']:.1f} / 10.0")
                print(f"  想い出量 (Accumulation): {s['accumulation']:.1f} / {s['max_l']:.1f} (L_max)")
                print(f"  お疲れ度 (Fatigue)  : {s['fatigue']:.1f} %")
                print(f"  進化係数 (Factor)  : {s['evolution_factor']:.2f}")
                print("------------------------------------\n")
                continue

            if user_input.strip() == '/reborn':
                success, msg = engine.cvm_reborn(forced=True)
                print(f"[System] {msg}")
                continue

            if user_input.strip() == '/hibernate':
                msg = engine.cvm_hibernate()
                print(f"[System] {msg}")
                continue
                
            if user_input.startswith('/net '):
                mode = user_input.split()[1].lower() if len(user_input.split()) > 1 else ""
                if mode == 'on':
                    system_config["net_enabled"] = True
                    print("[System] ネット検索(語彙・知識)を オン にしました。")
                elif mode == 'off':
                    system_config["net_enabled"] = False
                    print("[System] ネット検索(語彙・知識)を オフ にしました。")
                else:
                    print("[System] 入力不正。例: /net on")
                continue
                
            if user_input.startswith('/teach '):
                knowledge_text = user_input[7:].strip()
                if knowledge_text:
                    engine.teach_knowledge(knowledge_text)
                    print(f"[System] 知識として「{knowledge_text}」をナビに記憶させました。")
                    engine.last_thought_route = [] 
                else:
                    print("[System] 入力不正。例: /teach りんごは赤い果物です。")
                continue

            if user_input.startswith('/vocab '):
                try:
                    interval = int(user_input.split()[1])
                    if interval < 10: print("[System] 10秒以上に設定してください。")
                    else:
                        system_config["vocab_interval"] = interval
                        print(f"[System] 通常の語彙取得検索の頻度を {interval} 秒に設定しました。")
                except ValueError: print("[System] 入力不正。例: /vocab 300")
                continue

            if user_input.startswith('/knowledge '):
                try:
                    interval = int(user_input.split()[1])
                    if interval < 10: print("[System] 10秒以上に設定してください。")
                    else:
                        system_config["knowledge_interval"] = interval
                        print(f"[System] 振り返り用知識検索の頻度を {interval} 秒に設定しました。")
                except ValueError: print("[System] 入力不正. 例: /knowledge 600")
                continue

            if user_input.startswith('/reflect '):
                try:
                    interval = int(user_input.split()[1])
                    if interval < 10: print("[System] 10秒以上に設定してください。")
                    else:
                        system_config["reflect_interval"] = interval
                        print(f"[System] 知識振り返りの頻度を {interval} 秒に設定しました。")
                except ValueError: print("[System] 入力不正。例: /reflect 300")
                continue

            if user_input.startswith('/thought '):
                try:
                    interval = int(user_input.split()[1])
                    if interval < 3: print("[System] 3秒以上に設定してください。")
                    else:
                        system_config["thought_interval"] = interval
                        print(f"[System] 自律思考(独り言)の頻度を {interval} 秒に設定しました。")
                except ValueError: print("[System] 入力不正。例: /thought 30")
                continue
                
            if user_input.startswith('/stage '):
                try:
                    stage = int(user_input.split()[1])
                    if 1 <= stage <= 4:
                        system_config["growth_stage"] = stage
                        stage_names = ["1語文(赤ちゃん)", "2語文(幼児)", "カタコト(子供)", "完全体(大人)"]
                        print(f"[System] ナビの成長段階を Stage {stage} : {stage_names[stage-1]} に設定しました。")
                    else:
                        print("[System] 成長段階は 1 から 4 の間で指定してください。")
                except ValueError: print("[System] 入力不正。例: /stage 1")
                continue
                
            if not user_input.strip(): continue
            
            engine.learn_from_input(user_input)
            response_text = engine.generate_response(growth_stage=system_config["growth_stage"])
            print(f"[Navi]: {response_text}")
            
            eureka_msg = engine.verify_and_reinforce_thought()
            if eureka_msg: print(eureka_msg)
            
        except KeyboardInterrupt:
            engine.queue_async_save(force=True)
            time.sleep(1)
            break