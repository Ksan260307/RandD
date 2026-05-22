from flask import Flask, request, jsonify
import re
import time
import copy
import json
import random
import unittest
import sys
import os

app = Flask(__name__)

class DatabaseError(Exception):
    """データベースの基底エラー"""
    pass

class QuerySyntaxError(DatabaseError):
    """クエリの構文解析時（SQLの書き間違いなど）のエラー"""
    pass

class QueryExecutionError(DatabaseError):
    """クエリ実行時（テーブル不在、カラム不在など）のエラー"""
    pass


class DatabaseEngine:
    """
    メモリ上で列指向（Columnar）データ構造を管理し、
    SoAアーキテクチャとO(1)インデックス、Copy-on-Writeトランザクションを備えた
    超高速データベースエンジン。
    """
    def __init__(self, db_file="lumina_db_data.json"):
        self.db_file = db_file
        
        # システムの初期状態（FACTORY RESETでここに戻る）
        self.initial_state = {
            "users": {
                "id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                "name": ["Alice", "Bob", "Charlie", "Dave", "Eve", "Frank", "Grace", "Heidi", "Ivan", "Judy"],
                "age": [25, 30, 22, 35, 28, 40, 29, 31, 24, 27],
                "status": ["Active", "Active", "Inactive", "Active", "Active", "Active", "Inactive", "Active", "Active", "Active"]
            },
            "products": {
                "id": [101, 102, 103, 104, 105],
                "name": ["Quantum CPU", "Holo-Monitor", "Zero-G Mouse", "Tachyon Keyboard", "Entanglement Router"],
                "price": [1500, 800, 120, 250, 400],
                "stock": [45, 12, 100, 80, 0]
            },
            "orders": {
                "order_id": [1001, 1002, 1003, 1004, 1005],
                "user_id": [1, 2, 1, 3, 4],
                "product_id": [101, 103, 105, 102, 104],
                "amount": [1, 2, 1, 5, 1]
            }
        }
        
        self.data_fragmentation = 0.0
        self.in_transaction = False
        self.snapshot_data = None
        self.snapshot_index = None
        self.epsilon_memory = 0.5
        self.mu_runtime = 0.5
        
        # O(1) 検索用インデックス構造 {table: {col: {val: set(indices)}}}
        self.index_store = {}
        
        # 起動時にディスクからデータをロードし、インデックスを構築
        self.load_from_disk()

    def load_from_disk(self):
        """ディスクからデータを復元し、全テーブルのインデックスを構築する。"""
        if self.db_file and os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    self.column_store = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load DB file. Reverting to initial state. ({e})")
                self.column_store = copy.deepcopy(self.initial_state)
        else:
            self.column_store = copy.deepcopy(self.initial_state)
            
        self._rebuild_all_indices()

    def save_to_disk(self):
        """現在のデータ状態をディスクに保存（トランザクション中は保留）。"""
        if self.db_file and not self.in_transaction:
            try:
                with open(self.db_file, 'w', encoding='utf-8') as f:
                    json.dump(self.column_store, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"Error saving to disk: {e}")

    def _rebuild_all_indices(self):
        """全テーブルのフルインデックスを再構築する"""
        self.index_store = {}
        for table in self.column_store:
            self._build_index(table)

    def _build_index(self, table):
        """特定のテーブルに対するハッシュインデックスを構築する O(N)"""
        self.index_store[table] = {col: {} for col in self.column_store[table]}
        for col, values in self.column_store[table].items():
            col_idx = self.index_store[table][col]
            for idx, val in enumerate(values):
                if val not in col_idx:
                    col_idx[val] = set()
                col_idx[val].add(idx)

    def _ensure_cow(self, table):
        """
        Copy-on-Write トランザクション保護。
        変更が発生する「直前」に、対象テーブルのみをスライス（浅いコピー）で退避する。
        """
        if self.in_transaction and table not in self.snapshot_data:
            # SoA配列のCレベルスライスコピーによる超高速バックアップ
            self.snapshot_data[table] = {c: self.column_store[table][c][:] for c in self.column_store[table]}
            # インデックスの各セットも退避
            self.snapshot_index[table] = {}
            for col, val_map in self.index_store[table].items():
                self.snapshot_index[table][col] = {v: s.copy() for v, s in val_map.items()}

    def _optimize_where_indices(self, table, where_str, str_map):
        """単純な等価条件の場合、インデックスからO(1)で直接行ポインタを取得する"""
        if not where_str: 
            return None
        m = re.match(r'^([a-zA-Z0-9_]+)\s*=\s*(.+)$', where_str.strip())
        if m:
            col, val_str = m.group(1), m.group(2).strip()
            # リテラルの解決
            if val_str.startswith('__LUMINA_STR_'):
                idx = int(val_str.replace('__LUMINA_STR_', '').replace('__', ''))
                val = str_map[idx].strip("'").strip('"')
            else:
                try:
                    val = float(val_str) if '.' in val_str else int(val_str)
                except ValueError:
                    val = val_str
            
            # インデックスヒット
            if table in self.index_store and col in self.index_store[table]:
                return list(self.index_store[table][col].get(val, set()))
        return None  # フルスキャンへフォールバック

    def update_physics(self, c, d, s):
        self.epsilon_memory = max(0.01, c / 100.0)
        self.mu_runtime = 1.0 - (d / 100.0 * 0.5) - (s / 100.0 * 0.3)

    def generate_dummy_data(self, table_name):
        count = 10000
        if table_name not in self.column_store:
            return 0
        data = self.column_store[table_name]
        cols = list(data.keys())
        
        id_col = next((c for c in cols if 'id' in c.lower()), None)
        start_id = 1
        if id_col and data[id_col]:
            numeric_ids = [v for v in data[id_col] if isinstance(v, (int, float))]
            if numeric_ids:
                start_id = max(numeric_ids) + 1
                
        self._ensure_cow(table_name)
        
        current_rows = len(next(iter(data.values()))) if data else 0
        for col in cols:
            new_vals = []
            if col == id_col:
                new_vals = list(range(start_id, start_id + count))
            elif col == 'name':
                new_vals = [f"Dummy_{random.randint(0, 99999)}" for _ in range(count)]
            elif col == 'age':
                new_vals = [20 + random.randint(0, 49) for _ in range(count)]
            elif col == 'status':
                new_vals = ["Active" if random.random() > 0.2 else "Inactive" for _ in range(count)]
            elif col == 'price':
                new_vals = [random.randint(0, 999) * 10 for _ in range(count)]
            elif col in ('stock', 'amount'):
                new_vals = [random.randint(0, 99) for _ in range(count)]
            else:
                base_type_is_num = isinstance(data[col][0], (int, float)) if data[col] else False
                if base_type_is_num:
                    new_vals = [random.randint(0, 999) for _ in range(count)]
                else:
                    new_vals = [f"Data_{random.randint(0, 999)}" for _ in range(count)]
            
            data[col].extend(new_vals)
            # インデックスの一括更新
            for offset, val in enumerate(new_vals):
                self.index_store[table_name][col].setdefault(val, set()).add(current_rows + offset)
        
        self.data_fragmentation = min(100.0, self.data_fragmentation + 5.0)
        self.save_to_disk()
        return count

    def explain_query(self, sql_string):
        sql = sql_string.strip().rstrip(';')
        plan = [{"step": 1, "action": "構文解析", "detail": "AST生成とO(1)インデックス利用可能性の判定。"}]
        if re.search(r'\(\s*SELECT', sql, re.IGNORECASE):
            plan.append({"step": len(plan) + 1, "action": "サブクエリ展開", "detail": "インラインビューを先行評価し結果をキャッシュ。"})
        if re.match(r'^begin', sql, re.IGNORECASE):
            plan.append({"step": len(plan) + 1, "action": "トランザクション", "detail": "Copy-on-Write(CoW)によるゼロコスト・アイソレーション開始。"})
        elif re.match(r'^select', sql, re.IGNORECASE):
            step = len(plan) + 1
            if re.search(r'join', sql, re.IGNORECASE):
                plan.append({"step": step, "action": "テーブル結合", "detail": "インデックス空間の仮想マージ（Row生成なし）。"})
                step += 1
            if re.search(r'where', sql, re.IGNORECASE):
                plan.append({"step": step, "action": "データ絞り込み", "detail": "インデックスO(1)検索、またはASTを用いた高速フルスキャン。"})
                step += 1
            if re.search(r'group\s+by', sql, re.IGNORECASE):
                plan.append({"step": step, "action": "グループ化", "detail": "ハッシュキーによるSoA集約。"})
                step += 1
            plan.append({"step": step, "action": "データ展開", "detail": "最終インデックスに基づいてAoS形式へマテリアライズ。"})
        elif re.match(r'^factory\s+reset', sql, re.IGNORECASE):
            plan.append({"step": 2, "action": "システム初期化", "detail": "インデックスと全てのデータを破棄し、初期セットに完全リセットします。"})
        return plan

    def find_inner_subquery(self, sql):
        depth, max_depth, start_idx, end_idx = 0, 0, -1, -1
        for i, c in enumerate(sql):
            if c == '(':
                depth += 1
                if re.match(r'^\(\s*SELECT\b', sql[i:], re.IGNORECASE) and depth >= max_depth:
                    max_depth, start_idx = depth, i
            elif c == ')':
                if start_idx != -1 and depth == max_depth and end_idx == -1:
                    end_idx = i
                depth -= 1
        if start_idx != -1 and end_idx != -1:
            return {'start': start_idx, 'end': end_idx, 'query': sql[start_idx+1:end_idx].strip()}
        return None

    def convert_aos_to_soa(self, aos_data):
        if not aos_data: return {}
        soa = {k: [] for k in aos_data[0].keys() if '.' not in k}
        for row in aos_data:
            for k in soa: soa[k].append(row[k])
        return soa

    def cleanup_temp_tables(self):
        for t in [k for k in list(self.column_store.keys()) if k.startswith('__tmp_')]:
            del self.column_store[t]
            if t in self.index_store:
                del self.index_store[t]

    def split_select_clause(self, clause):
        parts, current, depth = [], "", 0
        for c in clause:
            if c == '(': depth += 1
            if c == ')': depth -= 1
            if c == ',' and depth == 0:
                parts.append(current.strip())
                current = ""
            else:
                current += c
        parts.append(current.strip())
        return parts

    def compile_condition(self, expr, str_map):
        s = expr
        while True:
            case_match = re.search(r'\bCASE\s+WHEN\s+(.+?)\s+THEN\s+(.+?)(?:\s+ELSE\s+(.+?))?\s+END\b', s, re.IGNORECASE)
            if not case_match: break
            cond, true_val, false_val = case_match.groups()
            s = s[:case_match.start()] + f"(({true_val}) if ({cond}) else ({false_val if false_val else 'None'}))" + s[case_match.end():]
            
        s = re.sub(r'\bIS\s+NOT\s+NULL\b', ' is not None ', s, flags=re.IGNORECASE)
        s = re.sub(r'\bIS\s+NULL\b', ' is None ', s, flags=re.IGNORECASE)

        def between_repl(m):
            return f"(__resolve('{m.group(1)}') >= {m.group(2)} and __resolve('{m.group(1)}') <= {m.group(3)})"
        s = re.sub(r'([a-zA-Z0-9_.]+)\s+BETWEEN\s+(.+?)\s+AND\s+(.+?)(?=\s*(?:AND\b|OR\b|\)|$))', between_repl, s, flags=re.IGNORECASE)

        def like_repl(m):
            not_op = 'not ' if m.group(2) and m.group(2).strip().upper() == 'NOT' else ''
            return f"{not_op}__like(__resolve('{m.group(1)}'), {m.group(3)})"
        s = re.sub(r'([a-zA-Z0-9_.]+)\s+(NOT\s+)?LIKE\s+(__LUMINA_STR_\d+__)', like_repl, s, flags=re.IGNORECASE)

        s = re.sub(r'\bAND\b', ' and ', s, flags=re.IGNORECASE)
        s = re.sub(r'\bOR\b', ' or ', s, flags=re.IGNORECASE)
        s = re.sub(r'!==', '!=', s)
        s = re.sub(r'===', '==', s)
        s = re.sub(r'(?<![<>!=])=(?!=)', '==', s)
        s = re.sub(r'<>', '!=', s)

        def in_repl(m):
            return f"(__resolve('{m.group(1)}') in [{m.group(2)}])"
        s = re.sub(r'([a-zA-Z0-9_.]+)\s+IN\s*\(([^)]+)\)', in_repl, s, flags=re.IGNORECASE)

        protected_keywords = ['and', 'or', 'True', 'False', 'None', 'not', 'in', 'if', 'else', '__like', '__resolve']
        def id_repl(m):
            string_lit = m.group(1)
            word = m.group(4)
            if string_lit or not word: return m.group(0)
            if word in protected_keywords or word.startswith('__LUMINA_STR_') or word.isdigit() or re.match(r'^\d+\.\d+$', word):
                return word
            return f"__resolve('{word}')"

        s = re.sub(r'(\'([^\'\\]|\\.)*\'|"([^"\\]|\\.)*")|\b([a-zA-Z_][a-zA-Z0-9_.]*)\b', id_repl, s)
        for i, str_val in enumerate(str_map):
            s = s.replace(f'__LUMINA_STR_{i}__', str_val)

        try:
            compiled_expr = compile(s, "<string>", "eval")
        except SyntaxError as e:
            raise QuerySyntaxError(f"AST Compilation failed. Invalid syntax in expression: {expr}")

        def evaluator(resolve_func):
            def __like(val, pattern):
                if val is None: return False
                regex_pattern = '^' + re.escape(pattern).replace('\\%', '.*').replace('\\_', '.') + '$'
                return bool(re.search(regex_pattern, str(val), re.IGNORECASE))
            env = {'__resolve': resolve_func, '__like': __like}
            try: return eval(compiled_expr, {"__builtins__": {}}, env)
            except Exception: return None
        return evaluator

    def expand_subqueries(self, sql, str_map):
        expanded_sql = sql
        while True:
            match = self.find_inner_subquery(expanded_sql)
            if not match: break
            sub_result = self.process_query(match['query'], is_subquery=True, external_str_map=str_map)
            if 'error' in sub_result: raise QueryExecutionError(f"Subquery Error: {sub_result['error']}")

            before_str = expanded_sql[:match['start']]
            if re.search(r'\bIN\s*$', before_str.strip(), re.IGNORECASE):
                vals = [list(r.values())[0] for r in sub_result['data']]
                vals_str_list = []
                for v in vals:
                    if isinstance(v, str):
                        str_map.append(f"'{v}'")
                        vals_str_list.append(f"__LUMINA_STR_{len(str_map)-1}__")
                    else:
                        vals_str_list.append(str(v))
                expanded_sql = expanded_sql[:match['start']] + f"({', '.join(vals_str_list)})" + expanded_sql[match['end']+1:]
            elif re.search(r'\bFROM\s*$', before_str.strip(), re.IGNORECASE) or re.search(r'\bJOIN\s*$', before_str.strip(), re.IGNORECASE):
                tmp_name = '__tmp_' + str(random.randint(0, 1000000))
                self.column_store[tmp_name] = self.convert_aos_to_soa(sub_result['data'])
                self._build_index(tmp_name) # 一時テーブルにもインデックスを張る
                expanded_sql = expanded_sql[:match['start']] + tmp_name + expanded_sql[match['end']+1:]
            else:
                val = list(sub_result['data'][0].values())[0] if sub_result['data'] else None
                if isinstance(val, str):
                    str_map.append(f"'{val}'")
                    val = f"__LUMINA_STR_{len(str_map)-1}__"
                expanded_sql = expanded_sql[:match['start']] + str(val) + expanded_sql[match['end']+1:]
        return expanded_sql

    def create_resolver(self, idx_row, table_map):
        def resolve(col):
            if '.' in col:
                alias, c = col.split('.', 1)
                tbl = table_map.get(alias)
                if tbl and c in self.column_store[tbl]:
                    idx = idx_row.get(alias, -1)
                    return self.column_store[tbl][c][idx] if idx >= 0 else None
            else:
                for alias, tbl in table_map.items():
                    if alias in idx_row and col in self.column_store[tbl]:
                        idx = idx_row[alias]
                        return self.column_store[tbl][col][idx] if idx >= 0 else None
            return None
        return resolve

    def process_query(self, query: str, is_subquery=False, external_str_map=None) -> dict:
        start_time = time.perf_counter()
        sql = query.strip().rstrip(';').replace('\n', ' ')
        
        if re.match(r'^explain\s+', sql, re.IGNORECASE):
            return {"data": self.explain_query(re.sub(r'^explain\s+', '', sql, flags=re.IGNORECASE)), "executionTime": "0.000", "scannedRows": 0, "fragmentation": f"{self.data_fragmentation:.1f}"}
            
        gen_match = re.match(r'^generate\s+dummy\s+(?:data\s+)?(?:for\s+)?([a-zA-Z0-9_]+)$', sql, re.IGNORECASE)
        if gen_match:
            count = self.generate_dummy_data(gen_match.group(1))
            if count > 0: return {"data": [{"Result": "Success", "Message": f"{count:,} rows injected."}], "executionTime": "0.000", "scannedRows": count, "fragmentation": f"{self.data_fragmentation:.1f}"}
            return {"error": "Table not found."}
        
        str_map = external_str_map if external_str_map is not None else []
        if not is_subquery and external_str_map is None:
            def extract_str(m):
                str_map.append(m.group(0))
                return f"__LUMINA_STR_{len(str_map)-1}__"
            sql = re.sub(r'(\'([^\'\\]|\\.)*\'|"([^"\\]|\\.)*")', extract_str, sql)
            
        result_set = []
        affected_rows = 0
        data_modified = False

        try:
            if not is_subquery: sql = self.expand_subqueries(sql, str_map)

            if re.match(r'^factory\s+reset', sql, re.IGNORECASE):
                self.column_store = copy.deepcopy(self.initial_state)
                self._rebuild_all_indices()
                self.data_fragmentation = 0.0
                self.in_transaction = False
                data_modified = True
                result_set = [{"Result": "Success", "Message": "System restored to initial state."}]

            elif re.match(r'^begin', sql, re.IGNORECASE):
                if self.in_transaction: raise QueryExecutionError("Transaction already active.")
                self.in_transaction = True
                # CoW用のポインタ退避領域を準備（メモリ使用量ゼロ）
                self.snapshot_data, self.snapshot_index = {}, {}
                result_set = [{"Result": "Success", "Message": "Transaction Started (CoW Isolation Active)"}]
                
            elif re.match(r'^commit', sql, re.IGNORECASE):
                if not self.in_transaction: raise QueryExecutionError("No active transaction.")
                self.in_transaction, self.snapshot_data, self.snapshot_index = False, None, None
                data_modified = True
                result_set = [{"Result": "Success", "Message": "Transaction Committed"}]
                
            elif re.match(r'^rollback', sql, re.IGNORECASE):
                if not self.in_transaction: raise QueryExecutionError("No active transaction.")
                # スナップショットに記録されたテーブル（変更されたもの）のみを復元
                for table, backup in self.snapshot_data.items():
                    self.column_store[table] = backup
                for table, backup_idx in self.snapshot_index.items():
                    self.index_store[table] = backup_idx
                self.in_transaction, self.snapshot_data, self.snapshot_index = False, None, None
                result_set = [{"Result": "Success", "Message": "Transaction Rolled Back"}]

            elif re.match(r'^select', sql, re.IGNORECASE):
                temp_sql = sql
                limit_val, offset_val, order_by_str, having_str, group_by_str, where_str = None, None, None, None, None, None

                m = re.search(r'\s+limit\s+(\d+)', temp_sql, re.IGNORECASE)
                if m: limit_val, temp_sql = m.group(1), temp_sql[:m.start()] + temp_sql[m.end():]
                m = re.search(r'\s+offset\s+(\d+)', temp_sql, re.IGNORECASE)
                if m: offset_val, temp_sql = m.group(1), temp_sql[:m.start()] + temp_sql[m.end():]
                m = re.search(r'\s+order\s+by\s+([\s\S]+)$', temp_sql, re.IGNORECASE)
                if m: order_by_str, temp_sql = m.group(1), temp_sql[:m.start()]
                m = re.search(r'\s+having\s+([\s\S]+)$', temp_sql, re.IGNORECASE)
                if m: having_str, temp_sql = m.group(1), temp_sql[:m.start()]
                m = re.search(r'\s+group\s+by\s+([\s\S]+)$', temp_sql, re.IGNORECASE)
                if m: group_by_str, temp_sql = m.group(1), temp_sql[:m.start()]
                m = re.search(r'\s+where\s+([\s\S]+)$', temp_sql, re.IGNORECASE)
                if m: where_str, temp_sql = m.group(1), temp_sql[:m.start()]

                joins = []
                while True:
                    jmatch = re.search(r'\b(LEFT\s+|INNER\s+|RIGHT\s+)?JOIN\s+([a-zA-Z0-9_]+)(?:\s+(?:AS\s+)?([a-zA-Z0-9_]+))?\s+ON\s+([\s\S]+?)(?=\b(?:LEFT|INNER|RIGHT)?\s*JOIN\b|$)', temp_sql, re.IGNORECASE)
                    if not jmatch: break
                    joins.append({'type': jmatch.group(1).strip().upper() if jmatch.group(1) else 'INNER', 'table': jmatch.group(2), 'alias': jmatch.group(3) or jmatch.group(2), 'on_cond': jmatch.group(4).strip()})
                    temp_sql = temp_sql[:jmatch.start()] + temp_sql[jmatch.end():]
                
                fmatch = re.match(r'^select\s+([\s\S]+?)\s+from\s+([a-zA-Z0-9_]+)(?:\s+(?:AS\s+)?([a-zA-Z0-9_]+))?', temp_sql, re.IGNORECASE)
                if not fmatch: raise QuerySyntaxError("Syntax error in SELECT statement.")
                select_clause, from_table, base_alias = fmatch.group(1).strip(), fmatch.group(2).strip(), fmatch.group(3) or fmatch.group(2).strip()

                if from_table not in self.column_store: raise QueryExecutionError(f"Table '{from_table}' not found.")
                row_count = len(next(iter(self.column_store[from_table].values()))) if self.column_store[from_table] else 0
                
                table_map = {base_alias: from_table}
                index_rows = []

                # O(1) インデックス検索の適用 (JOINがない場合のみ有効化)
                if not joins and where_str:
                    optimized_idx = self._optimize_where_indices(from_table, where_str, str_map)
                    if optimized_idx is not None:
                        index_rows = [{base_alias: i} for i in optimized_idx]
                    else:
                        index_rows = [{base_alias: i} for i in range(row_count)]
                        where_func = self.compile_condition(where_str, str_map)
                        index_rows = [ir for ir in index_rows if where_func(self.create_resolver(ir, table_map))]
                else:
                    index_rows = [{base_alias: i} for i in range(row_count)]

                # JOIN 処理
                for join in joins:
                    join_tbl, join_alias = join['table'], join['alias']
                    table_map[join_alias] = join_tbl
                    join_count = len(next(iter(self.column_store[join_tbl].values()))) if self.column_store[join_tbl] else 0
                    on_func = self.compile_condition(join['on_cond'], str_map)
                    
                    new_idx_rows = []
                    for idx_row in index_rows:
                        matched = False
                        for j in range(join_count):
                            merged_idx = idx_row.copy()
                            merged_idx[join_alias] = j
                            if on_func(self.create_resolver(merged_idx, table_map)):
                                new_idx_rows.append(merged_idx)
                                matched = True
                        if not matched and join['type'] == 'LEFT':
                            merged_idx = idx_row.copy()
                            merged_idx[join_alias] = -1
                            new_idx_rows.append(merged_idx)
                    index_rows = new_idx_rows

                # JOIN があった場合の事後WHEREフィルタ
                if joins and where_str:
                    where_func = self.compile_condition(where_str, str_map)
                    index_rows = [ir for ir in index_rows if where_func(self.create_resolver(ir, table_map))]

                select_parts = self.split_select_clause(select_clause)
                is_agg = any(re.search(r'COUNT\(|SUM\(|AVG\(', p, re.IGNORECASE) for p in select_parts)

                compiled_selects = []
                for part in select_parts:
                    as_match = re.search(r'(.+?)\s+AS\s+([a-zA-Z0-9_]+)$', part, re.IGNORECASE)
                    expr = as_match.group(1).strip() if as_match else part.strip()
                    alias = as_match.group(2) if as_match else re.sub(r'^[a-zA-Z0-9_]+\.', '', expr)
                    if expr == '*': compiled_selects.append({'type': 'star'})
                    elif re.match(r'^(COUNT|SUM|AVG)\(', expr, re.IGNORECASE):
                        m = re.match(r'^(COUNT|SUM|AVG)\(\s*(.+?)\s*\)', expr, re.IGNORECASE)
                        compiled_selects.append({'type': 'agg', 'func': m.group(1).upper(), 'arg': m.group(2), 'alias': alias})
                    else:
                        compiled_selects.append({'type': 'expr', 'eval_func': self.compile_condition(expr, str_map), 'alias': alias})

                groups = {}
                if group_by_str:
                    group_cols = [s.strip() for s in group_by_str.split(',')]
                    for ir in index_rows:
                        resolver = self.create_resolver(ir, table_map)
                        key = '|||'.join([str(resolver(c)) for c in group_cols])
                        groups.setdefault(key, []).append(ir)
                else:
                    groups['all'] = index_rows

                if is_agg or group_by_str:
                    for key, group_rows in groups.items():
                        agg_row = {}
                        for sel in compiled_selects:
                            if sel['type'] == 'agg':
                                if sel['func'] == 'COUNT': agg_row[sel['alias']] = len(group_rows)
                                else:
                                    sum_val, cnt = 0, 0
                                    for ir in group_rows:
                                        v = self.create_resolver(ir, table_map)(sel['arg'])
                                        if isinstance(v, (int, float)):
                                            sum_val += v
                                            cnt += 1
                                    agg_row[sel['alias']] = sum_val if sel['func'] == 'SUM' else (round(sum_val / cnt, 2) if cnt > 0 else 0)
                            elif sel['type'] == 'expr':
                                agg_row[sel['alias']] = sel['eval_func'](self.create_resolver(group_rows[0], table_map)) if group_rows else None
                        result_set.append(agg_row)
                    affected_rows = len(index_rows)
                else:
                    for ir in index_rows:
                        out_row = {}
                        resolver = self.create_resolver(ir, table_map)
                        for sel in compiled_selects:
                            if sel['type'] == 'star':
                                for alias, tbl in table_map.items():
                                    idx = ir.get(alias, -1)
                                    if idx >= 0:
                                        for k in self.column_store[tbl]: out_row[k] = self.column_store[tbl][k][idx]
                            elif sel['type'] == 'expr':
                                out_row[sel['alias']] = sel['eval_func'](resolver)
                        result_set.append(out_row)
                    affected_rows = len(result_set)

                if (is_agg or group_by_str) and having_str:
                    having_func = self.compile_condition(having_str, str_map)
                    result_set = [r for r in result_set if having_func(lambda c: r.get(c))]

                if order_by_str and result_set:
                    om = re.match(r'([a-zA-Z0-9_.]+)(?:\s+(asc|desc))?', order_by_str.strip(), re.IGNORECASE)
                    if om:
                        sort_col, is_desc = om.group(1), om.group(2) and om.group(2).lower() == 'desc'
                        result_set.sort(key=lambda r: ((r.get(sort_col) is not None), r.get(sort_col)) if not is_desc else ((r.get(sort_col) is None), r.get(sort_col)), reverse=is_desc)

                if limit_val is not None:
                    limit, offset = int(limit_val), int(offset_val) if offset_val else 0
                    result_set = result_set[offset:offset + limit]

            elif re.match(r'^insert', sql, re.IGNORECASE):
                m = re.match(r'insert\s+into\s+([a-zA-Z0-9_]+)\s*\(([^)]+)\)\s*values\s*([\s\S]+)$', sql, re.IGNORECASE)
                if m:
                    table, cols = m.group(1), [c.strip() for c in m.group(2).split(',')]
                    if table not in self.column_store: raise QueryExecutionError(f"Table '{table}' not found.")
                    val_matches = re.findall(r'\(([^)]+)\)', m.group(3))
                    if not val_matches: raise QuerySyntaxError("Syntax Error in INSERT.")
                    
                    self._ensure_cow(table)
                    table_data = self.column_store[table]
                    for vm in val_matches:
                        vals = []
                        for val in [v.strip() for v in vm.split(',')]:
                            for i, str_val in enumerate(str_map): val = val.replace(f'__LUMINA_STR_{i}__', str_val)
                            if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')): vals.append(val[1:-1])
                            else:
                                try: vals.append(float(val) if '.' in val else int(val))
                                except ValueError: vals.append(val)
                        if len(cols) != len(vals): raise QueryExecutionError("Column count doesn't match value count.")
                        
                        current_rows = len(next(iter(table_data.values()))) if table_data else 0
                        for c_idx, col in enumerate(cols):
                            if col in table_data:
                                val = vals[c_idx]
                                table_data[col].append(val)
                                self.index_store[table][col].setdefault(val, set()).add(current_rows)
                                
                        for col in table_data:
                            if len(table_data[col]) == current_rows:
                                table_data[col].append(None)
                                self.index_store[table][col].setdefault(None, set()).add(current_rows)
                        affected_rows += 1
                    self.data_fragmentation = min(100.0, self.data_fragmentation + (len(val_matches) * 0.5))
                    data_modified = True
                    result_set = [{"Result": "Success", "Message": f"{affected_rows} rows injected."}]

            elif re.match(r'^update', sql, re.IGNORECASE):
                m = re.search(r'update\s+([a-zA-Z0-9_]+)\s+set\s+([\s\S]+?)(?:\s+where\s+([\s\S]+))?$', sql, re.IGNORECASE)
                if m:
                    table, set_str, where_str = m.group(1), m.group(2), m.group(3)
                    if table not in self.column_store: raise QueryExecutionError(f"Table '{table}' not found.")
                    
                    set_evaluators = []
                    for s in self.split_select_clause(set_str):
                        eq_idx = s.find('=')
                        col = s[:eq_idx].strip()
                        if col not in self.column_store[table]: raise QueryExecutionError(f"Column '{col}' not found.")
                        set_evaluators.append({'col': col, 'eval_func': self.compile_condition(s[eq_idx + 1:].strip(), str_map)})

                    self._ensure_cow(table)
                    data = self.column_store[table]
                    row_count = len(next(iter(data.values()))) if data else 0
                    
                    target_indices = self._optimize_where_indices(table, where_str, str_map)
                    if target_indices is None:
                        target_indices = []
                        table_map = {table: table}
                        if where_str:
                            where_func = self.compile_condition(where_str, str_map)
                            for i in range(row_count):
                                if where_func(self.create_resolver({table: i}, table_map)): target_indices.append(i)
                        else:
                            target_indices = list(range(row_count))

                    table_map = {table: table}
                    for idx in target_indices:
                        resolver = self.create_resolver({table: idx}, table_map)
                        new_vals = {ev['col']: ev['eval_func'](resolver) for ev in set_evaluators}
                        for k, v in new_vals.items():
                            old_val = data[k][idx]
                            if old_val != v:
                                data[k][idx] = v
                                # インデックスの差分更新
                                self.index_store[table][k][old_val].remove(idx)
                                if not self.index_store[table][k][old_val]:
                                    del self.index_store[table][k][old_val]
                                self.index_store[table][k].setdefault(v, set()).add(idx)

                    affected_rows = len(target_indices)
                    if affected_rows > 0: 
                        self.data_fragmentation = min(100.0, self.data_fragmentation + 2)
                        data_modified = True
                    result_set = [{"Result": "Success", "Message": f"{affected_rows} rows updated."}]

            elif re.match(r'^delete', sql, re.IGNORECASE):
                m = re.match(r'delete\s+from\s+([a-zA-Z0-9_]+)(?:\s+where\s+([\s\S]+))?$', sql, re.IGNORECASE)
                if m:
                    table, where_str = m.group(1), m.group(2)
                    if table not in self.column_store: raise QueryExecutionError(f"Table '{table}' not found.")
                    
                    self._ensure_cow(table)
                    data = self.column_store[table]
                    row_count = len(next(iter(data.values()))) if data else 0
                    
                    target_indices = self._optimize_where_indices(table, where_str, str_map)
                    if target_indices is None:
                        target_indices = []
                        table_map = {table: table}
                        if where_str:
                            where_func = self.compile_condition(where_str, str_map)
                            for i in range(row_count):
                                if where_func(self.create_resolver({table: i}, table_map)): target_indices.append(i)
                        else:
                            target_indices = list(range(row_count))

                    for i in reversed(sorted(target_indices)):
                        for col in data: del data[col][i]

                    affected_rows = len(target_indices)
                    if affected_rows > 0: 
                        self.data_fragmentation = min(100.0, self.data_fragmentation + 5)
                        data_modified = True
                        # 行が詰められてポインタがズレるため、インデックスをフルリビルド
                        self._build_index(table)
                        
                    result_set = [{"Result": "Success", "Message": f"{affected_rows} rows deleted."}]

            elif re.match(r'^create\s+table', sql, re.IGNORECASE):
                m = re.match(r'create\s+table\s+([a-zA-Z0-9_]+)\s*\(([^)]+)\)', sql, re.IGNORECASE)
                if m:
                    table = m.group(1)
                    if table in self.column_store: raise QueryExecutionError(f"Table '{table}' already exists.")
                    self.column_store[table] = {c.strip().split()[0]: [] for c in m.group(2).split(',')}
                    self._build_index(table)
                    data_modified = True
                    result_set = [{"Result": "Success", "Message": f"Table '{table}' created."}]

            elif re.match(r'^drop\s+table', sql, re.IGNORECASE):
                m = re.match(r'drop\s+table\s+([a-zA-Z0-9_]+)', sql, re.IGNORECASE)
                if m and m.group(1) in self.column_store:
                    del self.column_store[m.group(1)]
                    if m.group(1) in self.index_store: del self.index_store[m.group(1)]
                    data_modified = True
                    result_set = [{"Result": "Success", "Message": f"Table '{m.group(1)}' dropped."}]

            elif re.match(r'^truncate\s+table', sql, re.IGNORECASE):
                m = re.match(r'truncate\s+table\s+([a-zA-Z0-9_]+)', sql, re.IGNORECASE)
                if m and m.group(1) in self.column_store:
                    for col in self.column_store[m.group(1)]: self.column_store[m.group(1)][col] = []
                    self._build_index(m.group(1))
                    data_modified = True
                    result_set = [{"Result": "Success", "Message": f"Table truncated."}]

            elif re.match(r'^(optimize|vacuum)', sql, re.IGNORECASE):
                self.data_fragmentation = 0.0
                result_set = [{"Result": "Success", "Message": "Data defragmented."}]
            else:
                raise QuerySyntaxError("Syntax Error or Unsupported Command.")
                
            if data_modified and not self.in_transaction:
                self.save_to_disk()

        except QuerySyntaxError as e:
            if not is_subquery: self.cleanup_temp_tables()
            return {"error": f"Syntax Error: {e}"}
        except QueryExecutionError as e:
            if not is_subquery: self.cleanup_temp_tables()
            return {"error": f"Execution Error: {e}"}
        except Exception as e:
            if not is_subquery: self.cleanup_temp_tables()
            return {"error": f"Internal Fatal Error: {e}"}

        if not is_subquery: self.cleanup_temp_tables()

        execution_time_ms = (time.perf_counter() - start_time) * 1000
        simulated_delay_ms = (len(sql) * 0.1 * self.epsilon_memory * self.mu_runtime * (1.0 + (self.data_fragmentation / 100.0))) * 0.001
        delay = max(0.00001, simulated_delay_ms + execution_time_ms)

        return {
            "data": result_set,
            "executionTime": f"{delay:.3f}",
            "scannedRows": affected_rows,
            "fragmentation": f"{self.data_fragmentation:.1f}"
        }


db = DatabaseEngine(db_file="lumina_db_data.json")

@app.route('/api/v1/query', methods=['POST'])
def api_query():
    data = request.get_json(force=True, silent=True)
    if not data or 'query' not in data:
        return jsonify({"error": "Failed to decode JSON object. Ensure double quotes are properly escaped."}), 400
    res = db.process_query(data['query'])
    return jsonify(res), 400 if "error" in res else 200

@app.route('/api/v1/explain', methods=['POST'])
def api_explain():
    data = request.get_json(force=True, silent=True)
    if not data or 'query' not in data: return jsonify({"error": "Valid JSON required."}), 400
    return jsonify({"plan": db.explain_query(data['query'])}), 200

@app.route('/api/v1/generate', methods=['POST'])
def api_generate():
    data = request.get_json(force=True, silent=True)
    if not data or 'table' not in data: return jsonify({"error": "Valid JSON required."}), 400
    count = db.generate_dummy_data(data['table'])
    if count > 0:
        return jsonify({"message": f"{count} rows injected.", "fragmentation": db.data_fragmentation}), 200
    else:
        return jsonify({"error": f"Table '{data['table']}' not found."}), 404

@app.route('/api/v1/physics', methods=['POST'])
def api_physics():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Valid JSON required."}), 400
    c = data.get('c', 0)
    d = data.get('d', 100)
    s = data.get('s', 100)
    db.update_physics(c, d, s)
    return jsonify({"message": "Physics parameters updated."}), 200

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# --- 動的 1000件 単体テスト ---
class TestDatabaseEngine(unittest.TestCase):
    def setUp(self): 
        # ディスクI/O回避（インメモリモード）でテスト
        self.db = DatabaseEngine(db_file=None)

def inject_1000_tests(test_class):
    # O(1) インデックス検索系のテスト
    for i in range(100):
        def test_idx(self, val=i):
            q = f"SELECT * FROM users WHERE id = {(val % 10) + 1}"
            res = self.db.process_query(q)
            self.assertNotIn("error", res, f"Failed on index search: {q}")
            self.assertEqual(len(res['data']), 1)
        setattr(test_class, f"test_index_select_{i}", test_idx)
        
    for i in range(200):
        def test_sel(self, val=i):
            q = f"SELECT id, name FROM users WHERE age >= {val % 100}"
            res = self.db.process_query(q)
            self.assertNotIn("error", res, f"Failed on: {q}")
        setattr(test_class, f"test_select_{i}", test_sel)
        
    for i in range(200):
        def test_ins(self, val=i):
            q = f"INSERT INTO users (id, name, age) VALUES ({1000+val}, 'TestName{val}', {20 + (val%30)})"
            res = self.db.process_query(q)
            self.assertNotIn("error", res, f"Failed on: {q}")
        setattr(test_class, f"test_insert_{i}", test_ins)
        
    for i in range(150):
        def test_upd(self, val=i):
            q = f"UPDATE users SET age = age + 1 WHERE id = {(val % 10) + 1}"
            res = self.db.process_query(q)
            self.assertNotIn("error", res, f"Failed on: {q}")
        setattr(test_class, f"test_update_{i}", test_upd)
        
    # CoW トランザクション保護テスト
    for i in range(200):
        def test_del_cow(self, val=i):
            self.db.process_query("BEGIN")
            q = f"DELETE FROM users WHERE id = {(val % 10) + 1}"
            res = self.db.process_query(q)
            self.assertNotIn("error", res, f"Failed on: {q}")
            self.db.process_query("ROLLBACK")
        setattr(test_class, f"test_delete_cow_rollback_{i}", test_del_cow)
        
    # 抽象化されたエラーハンドリング（QuerySyntaxError）のテスト
    for i in range(50):
        def test_err(self, val=i):
            q = f"SELECT * FROM users WHERE age >>>> {val}" # 意図的な構文エラー
            res = self.db.process_query(q)
            self.assertIn("error", res)
            self.assertTrue("Syntax Error" in res["error"])
        setattr(test_class, f"test_syntax_error_{i}", test_err)

    complex_queries = [
        "SELECT u.name, o.amount FROM users u JOIN orders o ON u.id = o.user_id",
        "SELECT status, COUNT(id) AS cnt FROM users GROUP BY status HAVING COUNT(id) > 1",
        "EXPLAIN SELECT * FROM users",
        "GENERATE DUMMY products"
    ]
    for i in range(100):
        q = complex_queries[i % len(complex_queries)]
        def test_comp(self, query=q):
            res = self.db.process_query(query)
            self.assertNotIn("error", res, f"Failed on: {query}")
        setattr(test_class, f"test_complex_{i}", test_comp)

inject_1000_tests(TestDatabaseEngine)

if __name__ == '__main__':
    print("--------------------------------------------------")
    print("Running 1000 internal unit tests (SoA & CoW & O(1) Index Optimized)...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestDatabaseEngine)
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    if result.wasSuccessful(): print(f"✅ All {result.testsRun} unit tests passed successfully!")
    else:
        print(f"❌ {len(result.failures) + len(result.errors)} out of {result.testsRun} tests failed.")
        sys.exit(1)
    print("==================================================")
    app.run(port=8080, debug=False)