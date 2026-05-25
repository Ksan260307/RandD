import os
import sys
import argparse
import re
import concurrent.futures
import fnmatch
import shutil
from pathlib import Path

# 外部ライブラリのフォールバック機構（システムの制約への適応）
try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False

# ANSIエスケープシーケンス（コンソール色付け用）
COLOR_GREEN = '\033[92m'
COLOR_YELLOW = '\033[93m'
COLOR_RED = '\033[91m'
COLOR_RESET = '\033[0m'

# 無駄な演算対象を初期段階で枝刈りするための除外ディレクトリ群（ベース）
BASE_EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode", "build", "dist"}

def detect_encoding(raw_bytes: bytes) -> str:
    """
    バイト列から最適なエンコーディングを推論する。
    """
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff"):
        return "utf-16"

    try:
        raw_bytes.decode("utf-8", errors="strict")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    if HAS_CHARDET:
        result = chardet.detect(raw_bytes[:4096])
        if result and result["encoding"]:
            enc = result["encoding"].lower()
            if enc in ("shift_jis", "shift-jis", "sjis"):
                return "cp932" 
            return enc

    for enc in ("cp932", "euc-jp", "iso-2022-jp", "latin-1"):
        try:
            raw_bytes[:4096].decode(enc, errors="strict")
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
            
    return "utf-8" 

def execute_replace(file_path: Path, pattern: re.Pattern, replace_str: str, encoding: str, make_backup: bool) -> int:
    """
    ファイル内の該当パターンを置換文字列で置換し、上書き保存する。
    """
    try:
        with open(file_path, "r", encoding=encoding, errors="surrogateescape") as f:
            content = f.read()
            
        new_content, count = pattern.subn(replace_str, content)
        
        if count > 0:
            if make_backup:
                backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                shutil.copy2(file_path, backup_path)
                
            with open(file_path, "w", encoding=encoding, errors="surrogateescape") as f:
                f.write(new_content)
            return count
    except Exception as e:
        print(f"  [エラー] {file_path.name} の置換に失敗: {e}")
    return 0

def process_file(file_path: Path, pattern: re.Pattern, base_dir: Path, 
                 files_with_matches: bool = False, only_matching: bool = False, force_encoding: str = None) -> tuple:
    """
    単一ファイル内のパターン検索を実行する。
    """
    results = []
    encoding = force_encoding if force_encoding else "utf-8"
    try:
        with open(file_path, "rb") as f:
            sample_bytes = f.read(8192)
            
            if not sample_bytes:
                return file_path, results, encoding
                
            if b"\x00" in sample_bytes and not (sample_bytes.startswith(b"\xff\xfe") or sample_bytes.startswith(b"\xfe\xff")):
                 return file_path, results, encoding

            if not force_encoding:
                encoding = detect_encoding(sample_bytes)

        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            if files_with_matches:
                for line in f:
                    if pattern.search(line):
                        rel_path = str(file_path.relative_to(base_dir))
                        results.append((rel_path, None, None))
                        break
            else:
                for line_num, line in enumerate(f, 1):
                    if only_matching:
                        for match in pattern.finditer(line):
                            rel_path = str(file_path.relative_to(base_dir))
                            results.append((rel_path, line_num, match.group(0)))
                    else:
                        if pattern.search(line):
                            rel_path = str(file_path.relative_to(base_dir))
                            results.append((rel_path, line_num, line.rstrip()))
                    
    except Exception:
        pass
        
    return file_path, results, encoding

def build_dense_file_list(target_dir: Path, include_patterns: list, exclude_patterns: list, exclude_dirs: set) -> list:
    """
    指定パスから除外ディレクトリを枝刈りし、密な（有効な）ファイルパスのリストを構築する。
    """
    file_list = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
        
        for file in files:
            if file.startswith('.'):
                continue
                
            file_path = Path(root) / file
            rel_path = file_path.relative_to(target_dir)
            rel_path_str = str(rel_path).replace("\\", "/")
            
            if exclude_patterns:
                if any(fnmatch.fnmatch(rel_path_str, p) or fnmatch.fnmatch(file, p) for p in exclude_patterns):
                    continue
            
            if include_patterns:
                if not any(fnmatch.fnmatch(rel_path_str, p) or fnmatch.fnmatch(file, p) for p in include_patterns):
                    continue
                    
            file_list.append(file_path)
            
    return file_list

def run_search(args, is_interactive=False):
    """
    1回分の検索、結果表示、置換、保存のフローを実行するコア関数。
    エラー発生時は sys.exit せず return して対話ループの継続を担保する。
    """
    if getattr(args, 'filename_only', False) and getattr(args, 'replace', None) is not None:
        print("エラー: --filename-only と --replace は同時に指定できません。")
        return
    
    target_dir = Path(args.target_path).resolve()
    if not target_dir.is_dir():
        print(f"エラー: 指定されたパスが存在しないか、ディレクトリではありません: {target_dir}")
        return

    pattern_str = args.pattern
    if getattr(args, 'fixed_strings', False):
        pattern_str = re.escape(pattern_str)
    if getattr(args, 'word', False):
        pattern_str = rf"\b{pattern_str}\b"

    flags = re.IGNORECASE if getattr(args, 'ignore_case', False) else 0
    try:
        compiled_pattern = re.compile(pattern_str, flags)
    except re.error as e:
        print(f"正規表現エラー: {e}")
        return

    include_patterns = [p.strip() for p in args.include.split(",")] if getattr(args, 'include', None) else []
    exclude_patterns = [p.strip() for p in args.exclude.split(",")] if getattr(args, 'exclude', None) else []
    
    active_exclude_dirs = set(BASE_EXCLUDE_DIRS)
    if getattr(args, 'exclude_dir', None):
        custom_dirs = {d.strip() for d in args.exclude_dir.split(",")}
        active_exclude_dirs.update(custom_dirs)

    print(f"\n検索開始: '{args.pattern}' (対象: {target_dir})")
    if getattr(args, 'fixed_strings', False): print("  - リテラル(完全一致)検索: 有効")
    if getattr(args, 'word', False): print("  - 単語単位検索: 有効")
    if getattr(args, 'filename_only', False): print("  - ファイル名のみ検索: 有効")
    if getattr(args, 'files_with_matches', False): print("  - マッチしたファイル名のみ出力: 有効")
    if getattr(args, 'only_matching', False): print("  - マッチ部分のみ抽出: 有効")
    if getattr(args, 'replace', None) is not None: print(f"  - 置換対象: 有効 ('{args.replace}')")
    if getattr(args, 'encoding', None): print(f"  - 強制エンコーディング: {args.encoding}")
    if include_patterns: print(f"  - 含めるファイル: {', '.join(include_patterns)}")
    if exclude_patterns: print(f"  - 除外するファイル: {', '.join(exclude_patterns)}")
    if getattr(args, 'exclude_dir', None): print(f"  - 追加除外ディレクトリ: {args.exclude_dir}")
    
    files = build_dense_file_list(target_dir, include_patterns, exclude_patterns, active_exclude_dirs)
    total_files = len(files)
    print(f"対象ファイル数: {total_files}")

    raw_output_lines = [] 
    matched_files_info = [] 
    matched_files_count = 0 
    
    print("\n--- 検索結果 ---")

    if getattr(args, 'filename_only', False):
        for f in files:
            rel_path = f.relative_to(target_dir)
            rel_path_str = str(rel_path).replace("\\", "/")
            if compiled_pattern.search(rel_path_str):
                matched_files_count += 1
                colored_path = compiled_pattern.sub(lambda m: f"{COLOR_RED}{m.group(0)}{COLOR_RESET}", str(rel_path))
                print(colored_path)
                raw_output_lines.append(str(rel_path))
    else:
        workers = os.cpu_count() or 4
        if workers > 1 and total_files > 50:
            with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(
                        process_file, f, compiled_pattern, target_dir, 
                        getattr(args, 'files_with_matches', False), 
                        getattr(args, 'only_matching', False), 
                        getattr(args, 'encoding', None)
                    ): f for f in files
                }
                for future in concurrent.futures.as_completed(futures):
                    f_path, res_tuples, enc = future.result()
                    if res_tuples:
                        matched_files_info.append((f_path, enc))
                        matched_files_count += 1
                        for res in res_tuples:
                            rel_path, line_num, line_text = res
                            if getattr(args, 'files_with_matches', False):
                                print(f"{COLOR_GREEN}{rel_path}{COLOR_RESET}")
                                raw_output_lines.append(rel_path)
                            else:
                                if getattr(args, 'only_matching', False):
                                    print(f"{COLOR_GREEN}{rel_path}{COLOR_RESET}({COLOR_YELLOW}{line_num}{COLOR_RESET}): {COLOR_RED}{line_text}{COLOR_RESET}")
                                    raw_output_lines.append(f"{rel_path}({line_num}): {line_text}")
                                else:
                                    colored_line = compiled_pattern.sub(lambda m: f"{COLOR_RED}{m.group(0)}{COLOR_RESET}", line_text)
                                    print(f"{COLOR_GREEN}{rel_path}{COLOR_RESET}({COLOR_YELLOW}{line_num}{COLOR_RESET}): {colored_line}")
                                    raw_output_lines.append(f"{rel_path}({line_num}): {line_text}")
        else:
            for f in files:
                f_path, res_tuples, enc = process_file(
                    f, compiled_pattern, target_dir, 
                    getattr(args, 'files_with_matches', False), 
                    getattr(args, 'only_matching', False), 
                    getattr(args, 'encoding', None)
                )
                if res_tuples:
                    matched_files_info.append((f_path, enc))
                    matched_files_count += 1
                    for res in res_tuples:
                        rel_path, line_num, line_text = res
                        if getattr(args, 'files_with_matches', False):
                            print(f"{COLOR_GREEN}{rel_path}{COLOR_RESET}")
                            raw_output_lines.append(rel_path)
                        else:
                            if getattr(args, 'only_matching', False):
                                print(f"{COLOR_GREEN}{rel_path}{COLOR_RESET}({COLOR_YELLOW}{line_num}{COLOR_RESET}): {COLOR_RED}{line_text}{COLOR_RESET}")
                                raw_output_lines.append(f"{rel_path}({line_num}): {line_text}")
                            else:
                                colored_line = compiled_pattern.sub(lambda m: f"{COLOR_RED}{m.group(0)}{COLOR_RESET}", line_text)
                                print(f"{COLOR_GREEN}{rel_path}{COLOR_RESET}({COLOR_YELLOW}{line_num}{COLOR_RESET}): {colored_line}")
                                raw_output_lines.append(f"{rel_path}({line_num}): {line_text}")

    if not raw_output_lines:
        print("一致する文字列は見つかりませんでした。")
    else:
        print(f"\n[集計] {matched_files_count} 個のファイルで合計 {len(raw_output_lines)} 件マッチしました。")

    # 置換機能の対話式実行
    if getattr(args, 'replace', None) is not None and matched_files_info:
        print("\n=== 置換の実行 ===")
        print(f"置換: '{args.pattern}' -> '{args.replace}'")
        if not getattr(args, 'no_backup', False):
            print("  ※実行前に元のファイルのバックアップ(.bak)を作成します。")
            
        matched_files_info.sort(key=lambda x: x[0])
        for i, (f_path, enc) in enumerate(matched_files_info, 1):
            rel_path = f_path.relative_to(target_dir)
            print(f"  [{i}] {rel_path}")
            
        print("\n置換するファイルを選択してください。")
        print("  - 'all' : すべて置換")
        print("  - '1,3' : 番号で指定 (カンマ区切り)")
        print("  - 'n'   : 置換しない (キャンセル)")
        
        choice = input("入力 (all / 番号 / n): ").strip().lower()
        
        target_indices = []
        if choice == 'all':
            target_indices = list(range(len(matched_files_info)))
        elif choice == 'n' or choice == '':
            print("置換をキャンセルしました。")
        else:
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(",") if x.strip().isdigit()]
                target_indices = [i for i in indices if 0 <= i < len(matched_files_info)]
            except ValueError:
                print("無効な入力です。置換をキャンセルしました。")
                
        if target_indices:
            print("\n置換を実行中...")
            total_replaced = 0
            make_backup = not getattr(args, 'no_backup', False)
            for i in target_indices:
                f_path, enc = matched_files_info[i]
                count = execute_replace(f_path, compiled_pattern, args.replace, enc, make_backup)
                rel_path = f_path.relative_to(target_dir)
                if count > 0:
                    print(f"  - {rel_path}: {count} 箇所置換完了")
                    total_replaced += count
            print(f"完了: 合計 {total_replaced} 箇所を置換しました。")

    # ファイルへの永続化 (任意化)
    if raw_output_lines:
        should_save = False
        if is_interactive:
            save_ans = input("\n検索結果をファイルに保存しますか？ (y/N): ").strip().lower()
            if save_ans == 'y':
                should_save = True
        elif getattr(args, 'save', False):
            should_save = True

        if should_save:
            raw_output_lines.sort()
            safe_pattern = re.sub(r'[\\/*?:"<>|]', "_", args.pattern)[:30]
            output_filename = f"GREP_{safe_pattern}.txt"
            
            try:
                with open(output_filename, "w", encoding="utf-8") as out_f:
                    out_f.write(f"検索文字列: {args.pattern}\n")
                    out_f.write(f"対象ディレクトリ: {target_dir}\n")
                    out_f.write(f"検索件数: {matched_files_count} ファイル / {len(raw_output_lines)} 箇所\n")
                    out_f.write("-" * 40 + "\n")
                    for res in raw_output_lines:
                        out_f.write(res + "\n")
                print(f"検索結果をファイルに保存しました: {output_filename}")
            except IOError as e:
                 print(f"検索結果ファイルの保存に失敗しました: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="超高速GREPツール (fastgrep)",
        epilog="★ 引数なしで実行すると対話モードで起動します ★"
    )
    parser.add_argument("pattern", nargs="?", help="検索文字列")
    parser.add_argument("target_path", nargs="?", help="検索対象のディレクトリパス")
    parser.add_argument("-i", "--ignore-case", action="store_true", help="大文字小文字を区別しない")
    parser.add_argument("-w", "--word", action="store_true", help="単語単位で検索する")
    parser.add_argument("-F", "--fixed-strings", action="store_true", help="正規表現を使わずリテラル検索する")
    parser.add_argument("-l", "--files-with-matches", action="store_true", help="マッチしたファイル名のみを出力する")
    parser.add_argument("-o", "--only-matching", action="store_true", help="マッチした部分文字列のみを出力する")
    parser.add_argument("--filename-only", action="store_true", help="ファイル名のみを検索対象にする")
    parser.add_argument("--replace", help="マッチした文字列を指定した文字列で置換する")
    parser.add_argument("--encoding", help="ファイルのエンコーディングを強制指定する (例: utf-8, cp932)")
    parser.add_argument("--include", help="含めるファイルパターン (例: *.py,src/*)")
    parser.add_argument("--exclude", help="除外するファイルパターン (例: *.test.js,out/*)")
    parser.add_argument("--exclude-dir", help="除外するディレクトリを追加 (カンマ区切り, 例: logs,tmp,vendor)")
    parser.add_argument("--save", action="store_true", help="検索結果をファイルに保存する")
    parser.add_argument("--no-backup", action="store_true", help="置換時にバックアップファイル(.bak)を作成しない")
    
    if os.name == 'nt':
        os.system('color')
    
    args = parser.parse_args()

    # --- 対話モードの処理 (ループ待機化) ---
    if len(sys.argv) == 1:
        print("=== FastGrep 対話モード ===")
        print("※ 各プロンプトで Ctrl+C を押すとプログラムを終了します。")
        last_path = ""
        
        while True:
            try:
                print("\n" + "="*50)
                
                # 1. パスの入力 (前回のパスがあればデフォルト化)
                prompt = f"1. 検索対象のディレクトリパスを入力 [{last_path}]: " if last_path else "1. 検索対象のディレクトリパスを入力: "
                raw_path = input(prompt).strip(' "\'')
                
                if not raw_path and last_path:
                    raw_path = last_path
                elif not raw_path:
                    print("エラー: ディレクトリパスが入力されませんでした。")
                    continue
                    
                args.target_path = raw_path
                last_path = raw_path
                
                # 2. 検索文字列の入力
                raw_pattern = input("2. 検索文字列を入力: ")
                if not raw_pattern:
                    print("エラー: 検索文字列が入力されませんでした。")
                    continue
                args.pattern = raw_pattern
                
                # 3. アクションの確認
                action = input("3. アクションを選択 (Enter:通常検索 / r:置換 / o:マッチ部分のみ抽出): ").strip().lower()
                args.replace = None
                args.only_matching = False
                if action == 'r':
                    args.replace = input("   置換後の文字列を入力してください: ")
                elif action == 'o':
                    args.only_matching = True
                    
                # 検索実行
                run_search(args, is_interactive=True)
                
            except (KeyboardInterrupt, EOFError):
                print("\n\nプログラムを終了します。")
                sys.exit(0)
    else:
        # --- コマンドラインからの単発実行処理 ---
        if not args.pattern or not args.target_path:
            parser.print_help(sys.stderr)
            sys.exit(1)
            
        try:
            run_search(args, is_interactive=False)
        except KeyboardInterrupt:
            print("\n\n処理が中断されました。")
            sys.exit(1)

if __name__ == "__main__":
    main()