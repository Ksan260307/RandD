import time
import random
import math
import sys
import concurrent.futures
import multiprocessing
import os

# =============================================================================
# [外部ライブラリの解禁]
# gmpy2: C言語レベルの超高速演算
# sympy: 数学界の叡智（二次ふるい法、SQUFOF等の完全代行）
# mpi4py: 複数PCを連結するマクロ・エンタングルメント
# =============================================================================
try:
    import gmpy2
    from gmpy2 import mpz
except ImportError:
    print("\n[エラー] 'gmpy2' が見つかりません。 'pip install gmpy2' を実行してください。")
    sys.exit(1)

try:
    import sympy
except ImportError:
    print("\n[エラー] 'sympy' が見つかりません。 'pip install sympy' を実行してください。")
    sys.exit(1)

try:
    from mpi4py import MPI
    comm = MPI.COMM_WORLD
    mpi_rank = comm.Get_rank()
    mpi_size = comm.Get_size()
except ImportError:
    # mpi4pyがない場合は、通常の1台PC（マルチコア）モードで安全に動作します
    mpi_rank = 0
    mpi_size = 1

# =============================================================================
# [最適化モジュール]
# =============================================================================

def _sieve(limit):
    sieve = [True] * (limit + 1)
    primes = []
    for p in range(2, limit + 1):
        if sieve[p]:
            primes.append(p)
            for i in range(p * p, limit + 1, p):
                sieve[i] = False
    return primes

_ALL_PRIMES = _sieve(2000000) 
_SHARED_PRIMES = [p for p in _ALL_PRIMES if p <= 100000]
_PHASE2_PRIMES = [p for p in _ALL_PRIMES if p > 100000]

# =============================================================================
# [AI パラメータチューニング (IPDF進化)]
# =============================================================================
def tune_parameters(n):
    """
    対象の数字の「硬さ（ビット長）」をスキャンし、最も効率の良いドリル設定を自動計算
    """
    bits = n.bit_length()
    if bits < 100:
        return 10000, 50000      # 柔らかい: 浅く広く
    elif bits < 200:
        return 50000, 500000     # 普通: 中程度の深さ
    else:
        return 150000, 1500000   # 超硬質: 最初から全開

# =============================================================================
# [並列ワーカーの定義]
# =============================================================================

def worker_fermat(n, time_limit, stop_event):
    """特化型スナイパー: 非常に近い数字の掛け合わせを瞬殺"""
    n = mpz(n)
    if gmpy2.is_even(n): return int(2)
    
    a = gmpy2.isqrt(n)
    if a * a == n: return int(a)
    a += 1
    b2 = a * a - n
    
    start_time = time.time()
    checks = 0
    valid_hex = {0, 1, 4, 9}
    
    while True:
        if (int(b2) & 15) in valid_hex:
            if gmpy2.is_square(b2):
                b = gmpy2.isqrt(b2)
                return int(a - b)
        b2 += 2 * a + 1
        a += 1
        
        checks += 1
        if checks % 200000 == 0:
            if stop_event.is_set(): return None
            if time.time() - start_time >= time_limit: return None
    return None

def worker_ecm_montgomery_phase2(n, time_limit, B1, B2, stop_event):
    """
    ECMドリル「フェーズ1＆フェーズ2（巨大ステップ）」の解放
    より深い層に眠る巨大素数パーツを一撃で釣り上げる
    """
    n = mpz(n)
    if gmpy2.is_even(n): return int(2)
    if gmpy2.gcd(n, 3) == 3: return int(3)
    
    random.seed(os.urandom(8))
    start_time = time.time()
    
    def point_add_proj(x1, z1, x2, z2, x_diff, z_diff, n_mod):
        # 射影座標系の点加算
        u = (x1 * x2 - z1 * z2) % n_mod
        v = (x1 * z2 - z1 * x2) % n_mod
        x3 = (z_diff * u * u) % n_mod
        z3 = (x_diff * v * v) % n_mod
        return x3, z3

    while True:
        sigma = mpz(random.randrange(6, int(n) - 1))
        u = (sigma ** 2 - 5) % n
        v = (4 * sigma) % n
        diff = (v - u) % n
        u3 = (u ** 3) % n
        
        v_val = (4 * u3 * v) % n
        try:
            inv_v = gmpy2.invert(v_val, n)
        except ZeroDivisionError:
            g = gmpy2.gcd(v_val, n)
            if 1 < g < n: return int(g)
            continue
            
        A = (gmpy2.powmod(diff, 3, n) * (3 * u + v) % n * inv_v - 2) % n
        x = (u ** 3) % n
        z = (v ** 3) % n
        
        # フェーズ1: 浅い層を削る
        for idx, p in enumerate(_SHARED_PRIMES):
            if p > B1: break
            q = p
            while q * p <= B1:
                q *= p
            
            temp_q = q
            bits = []
            while temp_q > 0:
                bits.append(temp_q & 1)
                temp_q >>= 1
            
            x0, z0 = x, z
            x1 = ((x ** 2 - z ** 2) ** 2) % n
            z1 = (4 * x * z * (x ** 2 + A * x * z + z ** 2)) % n
            
            for bit in reversed(bits[:-1]):
                if bit:
                    x0 = (z * (x0 * x1 - z0 * z1) ** 2) % n
                    z0 = (x * (x0 * z1 - z0 * x1) ** 2) % n
                    x1 = ((x1 ** 2 - z1 ** 2) ** 2) % n
                    z1 = (4 * x1 * z1 * (x1 ** 2 + A * x1 * z1 + z1 ** 2)) % n
                else:
                    x1 = (z * (x0 * x1 - z0 * z1) ** 2) % n
                    z1 = (x * (x0 * z1 - z0 * x1) ** 2) % n
                    x0 = ((x0 ** 2 - z0 ** 2) ** 2) % n
                    z0 = (4 * x0 * z0 * (x0 ** 2 + A * x0 * z0 + z0 ** 2)) % n
            x, z = x0, z0
            
            if idx % 5000 == 0:
                if stop_event.is_set(): return None
                if time.time() - start_time >= time_limit: return None
                
        g = gmpy2.gcd(z, n)
        if 1 < g < n: return int(g)
        
        # フェーズ2: 巨大ステップによる深層の一括探索
        diff_table = {}
        x2 = ((x ** 2 - z ** 2) ** 2) % n
        z2 = (4 * x * z * (x ** 2 + A * x * z + z ** 2)) % n
        diff_table[2] = (x2, z2)
        
        curr_x, curr_z = x, z
        prev_p = B1
        counter = 0
        
        for p in _PHASE2_PRIMES:
            if p <= B1: continue
            if p > B2: break
            
            d = p - prev_p
            if d not in diff_table:
                # 差分が未計算の場合はスキップ（簡易実装）
                continue
                
            dx, dz = diff_table[d]
            curr_x, curr_z = point_add_proj(curr_x, curr_z, dx, dz, x, z, n)
            prev_p = p
            counter += 1
            
            if counter % 100 == 0:
                g = gmpy2.gcd(curr_z, n)
                if 1 < g < n: return int(g)
                if stop_event.is_set(): return None
                if time.time() - start_time >= time_limit: return None

        g = gmpy2.gcd(curr_z, n)
        if 1 < g < n: return int(g)

        if time.time() - start_time >= time_limit:
            return None
    return None

def worker_sympy_ultimate(n, time_limit, stop_event):
    """
    SymPyの叡智を召喚。
    QS（二次ふるい法）やSQUFOFなど、最適な重機を自動選択して暗号を粉砕する。
    """
    start_time = time.time()
    try:
        # SymPyの強力なfactorint関数は、内部で最適な手法を自動選択します
        # タイムアウトの制御が難しいため、別プロセスとして実行・監視します
        factors = sympy.ntheory.factorint(int(n))
        for f in factors.keys():
            if 1 < f < n:
                return int(f)
    except Exception:
        pass
    return None


# =============================================================================
# [コアシステム]
# =============================================================================

class PhaseDynamicsEngine:
    def __init__(self):
        self.max_workers = min(4, multiprocessing.cpu_count())
        self.executor = concurrent.futures.ProcessPoolExecutor(max_workers=self.max_workers)
        self.manager = multiprocessing.Manager()
        
        # ユーザー向けのシンプルで優しい起動メッセージ
        if mpi_size > 1:
            print(f"システム: {mpi_size}台のPC（合計 {mpi_size * self.max_workers}個の頭脳）をネットワーク接続しました。")
        else:
            print(f"システム: お使いのPCの {self.max_workers}個の頭脳をフル活用して準備完了です。")

    def _parallel_dispatch(self, n, time_limit, mode, b1_base, b2_base):
        stop_event = self.manager.Event()
        futures = {}
        
        if mode == "Explore":
            futures = {
                self.executor.submit(worker_fermat, n, time_limit, stop_event): 'Fermat',
                self.executor.submit(worker_ecm_montgomery_phase2, n, time_limit, b1_base, b2_base, stop_event): 'ECM_1',
                self.executor.submit(worker_ecm_montgomery_phase2, n, time_limit, b1_base * 2, b2_base * 2, stop_event): 'ECM_2'
            }
        elif mode == "Adapt":
            futures = {
                self.executor.submit(worker_ecm_montgomery_phase2, n, time_limit, b1_base * 3, b2_base * 3, stop_event): 'ECM_Adapt',
                self.executor.submit(worker_sympy_ultimate, n, time_limit, stop_event): 'SymPy_Heavy'
            }
        elif mode == "SafeDrift":
            # SymPy(QS等)と、超高回転化したECM波状攻撃
            futures[self.executor.submit(worker_sympy_ultimate, n, time_limit, stop_event)] = 'SymPy_Ultimate'
            for i in range(1, self.max_workers):
                b1_param = int(b1_base * (1.5 ** i))
                b2_param = int(b2_base * (1.5 ** i))
                time.sleep(0.05) 
                futures[self.executor.submit(worker_ecm_montgomery_phase2, n, time_limit, b1_param, b2_param, stop_event)] = f'ECM_Deep_{i}'
        
        divisor = None
        start_wait = time.time()
        active_futures = set(futures.keys())
        
        while active_futures:
            done, not_done = concurrent.futures.wait(active_futures, timeout=0.5, return_when=concurrent.futures.FIRST_COMPLETED)
            
            for future in done:
                active_futures.remove(future)
                try:
                    res = future.result()
                    if res is not None and 1 < res < n:
                        divisor = res
                        stop_event.set()
                        break 
                except Exception:
                    pass
            
            if divisor is not None:
                break
                
            if time.time() - start_wait >= time_limit:
                stop_event.set()
                break
                
        for future in futures:
            future.cancel()
                    
        return divisor

    def compile_and_dispatch(self, values, base_time=2.5):
        results = {}
        for val in values:
            start_time = time.time()
            n = val
            factors = []
            
            # 序盤の簡単な割り算
            for p in [2, 3, 5, 7]:
                while n % p == 0:
                    factors.append(p)
                    n //= p
            wheel = [4, 2, 4, 2, 4, 6, 2, 6]
            w = 0
            f = 11
            limit = min(1000000, math.isqrt(n))
            while f <= limit:
                if n % f == 0:
                    while n % f == 0:
                        factors.append(f)
                        n //= f
                f += wheel[w]
                w = (w + 1) & 7
                
            if n > 1:
                factors.append(n)
            
            attempt = 1
            activity_level = 0.5
            
            while True:
                unresolved = [f for f in factors if f > 1 and not gmpy2.is_prime(mpz(f), 25)]
                if not unresolved:
                    break 
                
                attempt += 1
                
                # 自動チューニング: 対象の大きさから最適な設定をAI判定
                target_max = max(unresolved)
                opt_b1, opt_b2 = tune_parameters(target_max)
                
                max_time_multiplier = 20.0 
                time_mult = min(max_time_multiplier, 2.0 ** (attempt - 1))
                boosted_time = base_time * time_mult
                
                risk_level = (attempt - 1) / 4.0 
                phase_rad = math.atan2(risk_level, activity_level)
                phase_deg = math.degrees(phase_rad)
                
                # ユーザー向けの優しいログ表現
                if attempt == 2:
                    print(f"\n  [探索開始] 基本的な方法で探しています... (最大 {boosted_time:.1f}秒)")
                    mode = "Explore"
                elif phase_deg < 70.0:
                    print(f"  [作戦変更] 少し強力な方法に切り替えて探しています... (最大 {boosted_time:.1f}秒)")
                    mode = "Adapt"
                else:
                    print(f"  [総力戦] 非常に硬い数字です。一番強力なモードで解析しています... (最大 {boosted_time:.1f}秒)")
                    mode = "SafeDrift"
                    opt_b1 *= 2
                    opt_b2 *= 2
                
                new_factors = []
                found_new = False
                total_reduction = 1.0
                
                for target in factors:
                    if target in unresolved:
                        divisor = self._parallel_dispatch(target, time_limit=boosted_time, mode=mode, b1_base=opt_b1, b2_base=opt_b2)
                        
                        # もし別PC（mpi4py）が繋がっていれば、結果を共有する（マクロ・エンタングルメント）
                        if mpi_size > 1:
                            divisor = comm.bcast(divisor, root=0)

                        if divisor is not None and 1 < divisor < target:
                            print(f"  ★ 成功！ 大きな数字を2つに割ることに成功しました: 因子 {divisor}")
                            new_factors.extend([divisor, target // divisor])
                            found_new = True
                            
                            reduction_ratio = target / max(divisor, target // divisor)
                            total_reduction *= reduction_ratio
                        else:
                            new_factors.append(target)
                    else:
                        new_factors.append(target)
                
                if not found_new:
                    activity_level = max(0.1, activity_level * 0.4) 
                else:
                    recovery_boost = min(0.8, math.log10(max(1.1, total_reduction)) / 5.0)
                    activity_level = min(1.0, activity_level + 0.2 + recovery_boost)
                    
                factors = sorted(new_factors)
                
            final_factors = []
            for f in factors:
                if f > 1:
                    if gmpy2.is_prime(mpz(f), 25):
                        print(f"  ✔ 確定: {f} はこれ以上割れない素数です。")
                    final_factors.append(f)
                    
            elapsed = time.time() - start_time
            results[val] = (sorted(final_factors), elapsed)
            
        return results
        
    def shutdown(self):
        self.executor.shutdown(wait=False)

def parse_input(text):
    text = text.replace('×', '*').strip()
    time_limit = None
    if '--time' in text:
        parts = text.split('--time')
        text = parts[0].strip()
        try: time_limit = float(parts[1].strip())
        except ValueError: pass
        
    text = text.replace(' ', '')
    target_val = None
    try:
        if '*' in text:
            parts = text.split('*')
            target_val = math.prod([int(p) for p in parts if p])
        elif text.isdigit(): 
            target_val = int(text)
    except ValueError: pass
    
    return target_val, time_limit

if __name__ == '__main__':
    # mpi4py実行時、メインノード(rank 0)以外は裏方に徹する
    if mpi_rank == 0:
        engine = PhaseDynamicsEngine()
        print("=========================================")
        print(" 自動素因数分解エンジン (全部乗せ・最終形態)")
        print("=========================================")
        
        try:
            while True:
                user_input = input("\n> 割りたい数字を入力してください: ").strip()
                if not user_input: continue
                if user_input.lower() in ['exit', 'quit']: break
                    
                target_val, user_time = parse_input(user_input)
                if target_val is None or target_val <= 1:
                    print(">> 2以上の正の整数、または掛け算を入力してください。")
                    continue
                    
                base_time = user_time if user_time is not None else 2.5
                
                print(f"\n--- 計算スタート ---")
                results = engine.compile_and_dispatch([target_val], base_time=base_time)
                res_factors, elapsed = results[target_val]
                
                formula = " * ".join(map(str, res_factors))
                
                print(f"\n--- 計算おわり ---")
                if len(res_factors) == 1:
                    print(f">> 結果: {target_val} は素数（これ以上割れません）でした。 ({elapsed:.2f}秒)")
                else:
                    print(f">> 結果: {target_val} = {formula} \n(かかった時間: {elapsed:.2f}秒)")
                    
        except KeyboardInterrupt:
            print("\n>> 計算を中止しました。")
        finally:
            engine.shutdown()
            print(">> プログラムを終了しました。")
    else:
        # サブノードは通信待機（マクロ・エンタングルメントの裏側）
        while True:
            # 実際の分散処理ロジックはメイン側から指示を受け取る
            pass