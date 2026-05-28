import os
import sys
from typing import List, Tuple

class FileEnvironmentState:
    """
    ファイルシステムの現在の状態と、操作対象となるファイル群を保持・管理するクラス。
    設計思想における「状態ベクトル」と「環境制約」を一般的なファイル管理に置き換えたものです。
    """
    def __init__(self, target_directory: str, search_keyword: str):
        self.target_directory = target_directory
        self.search_keyword = search_keyword
        self.target_files: List[str] = []
        self.processed_files: List[Tuple[str, bool, str]] = [] # (filepath, is_success, message)
        self.is_valid_environment = os.path.isdir(target_directory)

class EvaluationEngine:
    """
    指定された条件に基づいて環境をスキャンし、操作対象を特定するエンジン。
    実行（削除）は行わず、対象のリストアップのみを行うことで副作用を防ぎます。
    """
    @staticmethod
    def evaluate(state: FileEnvironmentState) -> None:
        if not state.is_valid_environment:
            return

        state.target_files.clear()
        
        # ディレクトリ内を走査し、キーワードを含むファイルを抽出（可視性制御に基づくフィルタリング）
        try:
            for root, _, files in os.walk(state.target_directory):
                for file in files:
                    if state.search_keyword in file:
                        full_path = os.path.join(root, file)
                        state.target_files.append(full_path)
        except Exception as e:
            print(f"[環境エラー] ディレクトリの走査中に問題が発生しました: {e}")

class ExecutionEngine:
    """
    評価された対象に対して実際の削除操作を適用するエンジン。
    OSの権限エラーなどの外部要因（ノイズ）を捕捉し、システムが破綻しないよう制御します。
    """
    @staticmethod
    def execute(state: FileEnvironmentState) -> None:
        state.processed_files.clear()
        
        for file_path in state.target_files:
            try:
                # 実際のファイルシステムに対して状態遷移（削除）を適用
                os.remove(file_path)
                state.processed_files.append((file_path, True, "削除成功"))
            except PermissionError:
                # 権限不足などの環境制約によるエラーを捕捉
                state.processed_files.append((file_path, False, "アクセス権限がありません"))
            except FileNotFoundError:
                state.processed_files.append((file_path, False, "ファイルが既に見つかりません"))
            except Exception as e:
                # 予期せぬ外部要因（エントロピー）によるエラー
                state.processed_files.append((file_path, False, f"予期せぬエラー: {str(e)}"))

class ConsoleView:
    """
    ユーザーとの対話を行うインターフェース。
    ユーザーの確認（観測）によって初めて実行プロセスが確定します。
    """
    @staticmethod
    def request_input(prompt: str) -> str:
        return input(prompt).strip()

    @staticmethod
    def display_targets(state: FileEnvironmentState) -> bool:
        if not state.target_files:
            print(f"\n[結果] キーワード '{state.search_keyword}' を含むファイルは見つかりませんでした。")
            return False

        print("\n--- 削除対象ファイル一覧 ---")
        for idx, file_path in enumerate(state.target_files, 1):
            print(f"{idx:03d}: {file_path}")
        print("----------------------------")
        print(f"合計 {len(state.target_files)} 件のファイルが見つかりました。")
        return True

    @staticmethod
    def display_results(state: FileEnvironmentState) -> None:
        print("\n--- 実行結果 ---")
        success_count = 0
        for file_path, success, msg in state.processed_files:
            status = "[ OK ]" if success else "[NG]"
            if success:
                success_count += 1
            print(f"{status} {file_path} - {msg}")
        
        print("----------------")
        print(f"処理完了: {success_count} / {len(state.processed_files)} 件成功")

def main():
    print("========================================")
    print(" 指定文字列ファイル一括削除ツール")
    print("========================================")

    # 1. ユーザーからのアクション（入力）の受付
    target_dir = ConsoleView.request_input("対象のフォルダパスを入力してください: ")
    keyword = ConsoleView.request_input("削除したいファイル名に含まれる文字を入力してください: ")

    if not target_dir or not keyword:
        print("[終了] パスまたはキーワードが空のため、処理を中止します。")
        sys.exit(0)

    # 2. 初期状態の構築
    state = FileEnvironmentState(target_dir, keyword)
    
    if not state.is_valid_environment:
        print(f"[エラー] 指定されたディレクトリが見つからないか、無効です: {target_dir}")
        sys.exit(1)

    # 3. 評価フェーズ（対象の予測と抽出）
    print("\n対象ファイルを検索しています...")
    EvaluationEngine.evaluate(state)

    # 4. 観測フェーズ（対象の提示とユーザーによる実行の権威化）
    has_targets = ConsoleView.display_targets(state)
    
    if has_targets:
        confirm = ConsoleView.request_input("\nこれらのファイルを本当に削除しますか？ (y/N): ").lower()
        
        # 5. 実行フェーズ（状態の更新）
        if confirm == 'y' or confirm == 'yes':
            print("\n削除処理を実行しています...")
            ExecutionEngine.execute(state)
            ConsoleView.display_results(state)
        else:
            print("\n[キャンセル] 削除処理はキャンセルされました。環境に変更はありません。")

if __name__ == "__main__":
    # OSの強制終了などで不整合が起きないよう、トップレベルでのエラーハンドリング
    try:
        main()
    except KeyboardInterrupt:
        print("\n[中断] ユーザーによって強制終了されました。")
        sys.exit(0)
    except Exception as e:
        print(f"\n[致命的エラー] システムが予期せず終了しました: {e}")
        sys.exit(1)