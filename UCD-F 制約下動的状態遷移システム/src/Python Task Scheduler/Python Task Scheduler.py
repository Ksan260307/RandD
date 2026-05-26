import os
import subprocess
import threading
import time
import datetime
import uuid
import sys
import json
import psutil
from flask import Flask, request, jsonify, render_template_string, send_file
from io import BytesIO

STATUS_IDLE = "待機中"
STATUS_RUNNING = "実行中"
STATUS_SCHEDULED = "スケジュール済み"
STATUS_ERROR = "エラー"
STATUS_QUEUED = "待機キュー"

DATA_FILE = "tasks_db.json"
MAX_CONCURRENT = 3

app = Flask(__name__)

class TaskManager:
    def __init__(self):
        self.tasks = {}
        self.queue = []
        self.lock = threading.Lock()
        self._load_tasks()
        threading.Thread(target=self._scheduler_loop, daemon=True).start()
        threading.Thread(target=self._queue_worker, daemon=True).start()

    def _load_tasks(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    saved_tasks = json.load(f)
                    for t_id, t_data in saved_tasks.items():
                        self.tasks[t_id] = {
                            "id": t_data["id"],
                            "name": t_data["name"],
                            "filepath": t_data["filepath"],
                            "status": STATUS_SCHEDULED if t_data.get("scheduled_time") else STATUS_IDLE,
                            "process": None, 
                            "logs": [],
                            "scheduled_time": t_data.get("scheduled_time"),
                            "last_run": t_data.get("last_run"),
                            "run_history": t_data.get("run_history", []),
                            "current_run_start": None
                        }
            except: pass

    def _save_tasks(self):
        save_keys = ["id", "name", "filepath", "scheduled_time", "last_run", "run_history"]
        save_data = {t_id: {k: v for k, v in t.items() if k in save_keys} for t_id, t in self.tasks.items()}
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=4)
        except: pass

    def add_task(self, name, filepath):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"指定されたファイルが見つかりません: {filepath}")
        with self.lock:
            tid = str(uuid.uuid4())
            self.tasks[tid] = {
                "id": tid, "name": name, "filepath": filepath, 
                "status": STATUS_IDLE, "process": None, "logs": [], 
                "scheduled_time": None, "last_run": None,
                "run_history": [], "current_run_start": None
            }
            self._save_tasks()
            return tid

    def delete_task(self, task_id):
        with self.lock:
            if task_id in self.tasks:
                if self.tasks[task_id]["process"] and self.tasks[task_id]["process"].poll() is None:
                    self.tasks[task_id]["process"].terminate()
                del self.tasks[task_id]
                self._save_tasks()
                return True
        return False

    def run_task(self, task_id):
        with self.lock:
            if task_id in self.tasks and self.tasks[task_id]["status"] not in [STATUS_RUNNING, STATUS_QUEUED]:
                self.queue.append(task_id)
                self.tasks[task_id]["status"] = STATUS_QUEUED
                return True
        return False

    def stop_task(self, task_id):
        with self.lock:
            t = self.tasks.get(task_id)
            if t:
                is_killed = False
                if t["process"] and t["process"].poll() is None:
                    try:
                        # terminateより強力なkillを使用して強制終了
                        t["process"].kill()
                    except:
                        pass
                    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    t["logs"].append(f"\n[{now_str}] ユーザーによって強制終了されました")
                    is_killed = True
                    
                    if t.get("current_run_start"):
                        end_time = time.time()
                        duration = round(end_time - t["current_run_start"], 2)
                        t["run_history"].insert(0, {
                            "start": t["last_run"],
                            "end": now_str,
                            "duration": duration,
                            "status": "強制終了"
                        })
                        t["run_history"] = t["run_history"][:50] # 履歴は最大50件保持
                        t["current_run_start"] = None

                elif t["status"] == STATUS_QUEUED and task_id in self.queue:
                    self.queue.remove(task_id)
                    t["logs"].append(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] キューから削除されました")
                    is_killed = True
                
                # 強制終了された場合はスケジュールも解除する
                if is_killed:
                    t["scheduled_time"] = None
                
                t["status"] = STATUS_SCHEDULED if t["scheduled_time"] else STATUS_IDLE
                t["process"] = None
                self._save_tasks()
                return True
            return False

    def schedule_task(self, task_id, time_str):
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id]["scheduled_time"] = time_str if time_str and time_str != "none" else None
                if self.tasks[task_id]["status"] not in [STATUS_RUNNING, STATUS_QUEUED]:
                    self.tasks[task_id]["status"] = STATUS_SCHEDULED if self.tasks[task_id]["scheduled_time"] else STATUS_IDLE
                
                # 間隔指定のスケジュールが組まれた場合、起点として現在時刻を last_run に仮設定（即時実行を防ぐため）
                if time_str and time_str.startswith("interval:"):
                    self.tasks[task_id]["last_run"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                self._save_tasks()
                return True
            return False

    def clear_task_logs(self, task_id):
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id]["logs"] = []
                return True
            return False

    def get_all_tasks_info(self):
        with self.lock:
            # process、logs、そしてリスト表示用には不要なrun_historyを省いて送る
            exclude_keys = ["process", "logs", "run_history"]
            return {tid: {k: v for k, v in t.items() if k not in exclude_keys} for tid, t in self.tasks.items()}

    def get_task_logs(self, task_id):
        with self.lock:
            t = self.tasks.get(task_id)
            return t["logs"] if t else []

    def get_system_stats(self):
        return {"cpu": psutil.cpu_percent(), "memory": psutil.virtual_memory().percent}

    def _queue_worker(self):
        while True:
            tid_to_run = None
            with self.lock:
                running_count = sum(1 for t in self.tasks.values() if t["status"] == STATUS_RUNNING)
                if self.queue and running_count < MAX_CONCURRENT:
                    tid_to_run = self.queue.pop(0)
            
            if tid_to_run:
                threading.Thread(target=self._run_process, args=(tid_to_run,), daemon=True).start()
            time.sleep(1)

    def _run_process(self, task_id):
        with self.lock:
            task = self.tasks.get(task_id)
            if not task: return
            task["status"] = STATUS_RUNNING
            task["current_run_start"] = time.time()
            now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # ログをリセットせず、区切り線とともに蓄積する
            task["logs"].append(f"\n--- [{now_str}] 実行開始: {task['filepath']} ---")
            task["last_run"] = now_str
            self._save_tasks()
        
        try:
            process = subprocess.Popen(
                [sys.executable, "-u", task["filepath"]],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            with self.lock:
                task["process"] = process
            
            for line in process.stdout:
                with self.lock:
                    if task_id in self.tasks:
                        self.tasks[task_id]["logs"].append(line.rstrip('\n'))
            process.wait()
            
            with self.lock:
                if task_id in self.tasks:
                    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    end_time = time.time()
                    duration = round(end_time - task.get("current_run_start", end_time), 2)

                    if process.returncode == 0:
                        task["logs"].append(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 正常終了")
                        status_str = "正常終了"
                    else:
                        task["logs"].append(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] エラー終了 (コード: {process.returncode})")
                        status_str = f"エラー (コード: {process.returncode})"
                    
                    task["run_history"].insert(0, {
                        "start": task["last_run"],
                        "end": now_str,
                        "duration": duration,
                        "status": status_str
                    })
                    task["run_history"] = task["run_history"][:50]
                    task["current_run_start"] = None

                    task["status"] = STATUS_SCHEDULED if task["scheduled_time"] else STATUS_IDLE
                    task["process"] = None
                    self._save_tasks()
        except Exception as e:
            with self.lock:
                if task_id in self.tasks:
                    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    end_time = time.time()
                    duration = round(end_time - task.get("current_run_start", end_time), 2)
                    
                    task["status"] = STATUS_ERROR
                    task["logs"].append(f"\nシステムエラー: {str(e)}")
                    
                    task["run_history"].insert(0, {
                        "start": task["last_run"],
                        "end": now_str,
                        "duration": duration,
                        "status": "システムエラー"
                    })
                    task["run_history"] = task["run_history"][:50]
                    task["current_run_start"] = None
                    task["process"] = None
                    self._save_tasks()

    def _match_cron(self, cron_str, dt):
        parts = cron_str.split()
        if len(parts) != 5: return False
        
        def match_part(part, val):
            if part == '*': return True
            if '/' in part:
                b, s = part.split('/')
                if not s.isdigit(): return False
                return val % int(s) == 0 if b == '*' else False
            if '-' in part:
                try:
                    s, e = part.split('-')
                    return int(s) <= val <= int(e)
                except: return False
            if ',' in part:
                return str(val) in part.split(',')
            return part.isdigit() and int(part) == val

        return (match_part(parts[0], dt.minute) and
                match_part(parts[1], dt.hour) and
                match_part(parts[2], dt.day) and
                match_part(parts[3], dt.month) and
                match_part(parts[4], dt.isoweekday() % 7))

    def _should_run(self, task, now):
        sched = task.get("scheduled_time")
        if not sched:
            return False

        last_run_str = task.get("last_run")
        last_run = datetime.datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S") if last_run_str else None

        # Interval: 指定秒数経過で実行
        if sched.startswith("interval:"):
            try:
                seconds = int(sched.split(":", 1)[1])
                if not last_run: return True
                return (now - last_run).total_seconds() >= seconds
            except: return False

        # それ以外の指定（毎分0秒のタイミングでのみ1回判定し、重複実行を防ぐ）
        if now.second != 0:
            return False

        # この分ですでに実行済みの場合はスキップ
        if last_run and last_run.strftime("%Y-%m-%d %H:%M") == now.strftime("%Y-%m-%d %H:%M"):
            return False

        if sched.startswith("daily:"):
            target = sched.split(":", 1)[1]
            return now.strftime("%H:%M") == target

        elif sched.startswith("date:"):
            target = sched.split(":", 1)[1]
            return now.strftime("%Y-%m-%d %H:%M") == target

        elif sched.startswith("cron:"):
            target = sched.split(":", 1)[1]
            return self._match_cron(target, now)

        # 過去バージョンの互換性（HH:MM形式）
        if ":" in sched and len(sched) == 5:
            return now.strftime("%H:%M") == sched

        return False

    def _scheduler_loop(self):
        while True:
            now = datetime.datetime.now()
            tasks_to_run = []
            
            with self.lock:
                for task_id, task in self.tasks.items():
                    if task["status"] not in [STATUS_RUNNING, STATUS_QUEUED]:
                        if self._should_run(task, now):
                            tasks_to_run.append(task_id)
            
            for tid in tasks_to_run:
                self.run_task(tid)
            # 高精度な判定のため1秒周期でループ
            time.sleep(1)

task_manager = TaskManager()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Python Task Manager</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .modal { display: none; }
        .modal.active { display: flex; }
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #1f2937; }
        ::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
        .hidden-el { display: none !important; }
    </style>
</head>
<body class="bg-gray-100 p-8 min-h-screen text-gray-800">
    <div class="max-w-6xl mx-auto">
        <h1 class="text-2xl font-bold mb-6 text-gray-800 flex items-center gap-2">
            <svg class="w-6 h-6 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
            PyTask Scheduler
        </h1>

        <!-- 監視ダッシュボード -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <div class="bg-white p-4 rounded-lg shadow-sm border border-gray-200 flex justify-between items-center">
                <span class="text-gray-500 font-semibold">システム CPU使用率</span>
                <span class="text-2xl font-bold text-blue-600"><span id="cpuVal">0</span>%</span>
            </div>
            <div class="bg-white p-4 rounded-lg shadow-sm border border-gray-200 flex justify-between items-center">
                <span class="text-gray-500 font-semibold">システム メモリ使用率</span>
                <span class="text-2xl font-bold text-purple-600"><span id="memVal">0</span>%</span>
            </div>
        </div>
        
        <div class="bg-white p-6 rounded-lg shadow-md border border-gray-200">
            <!-- タスク追加フォーム -->
            <div class="flex flex-col md:flex-row gap-4 mb-6 bg-gray-50 p-4 rounded-lg border">
                <input type="text" id="taskName" placeholder="タスク名 (例: データクローリング)" class="border p-2 rounded flex-1 focus:ring focus:ring-blue-100 outline-none">
                <input type="text" id="taskPath" placeholder="Pythonファイルの絶対/相対パス (例: ./script.py)" class="border p-2 rounded flex-1 focus:ring focus:ring-blue-100 outline-none">
                <button onclick="addTask()" class="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 transition font-medium shadow-sm whitespace-nowrap">タスクを追加</button>
            </div>

            <!-- タスク一覧 -->
            <div class="overflow-x-auto w-full">
                <table class="w-full text-left border-collapse bg-white rounded-lg overflow-hidden min-w-[800px]">
                    <thead>
                        <tr class="bg-gray-100 border-b">
                            <th class="p-4 font-semibold text-gray-600">タスク名</th>
                            <th class="p-4 font-semibold text-gray-600">ファイルパス</th>
                            <th class="p-4 font-semibold text-gray-600 w-32">ステータス</th>
                            <th class="p-4 font-semibold text-gray-600 w-56">次回実行 / 最終実行</th>
                            <th class="p-4 font-semibold text-gray-600 text-right w-32">アクション</th>
                        </tr>
                    </thead>
                    <tbody id="taskList" class="divide-y divide-gray-100">
                        <!-- JSにて動的に注入 -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- 周期スケジュール設定 モーダル -->
    <div id="scheduleModal" class="modal fixed inset-0 bg-black bg-opacity-60 items-center justify-center z-50 p-4">
        <div class="bg-white rounded-lg shadow-2xl w-full max-w-md flex flex-col">
            <div class="p-4 border-b flex justify-between items-center bg-gray-100 rounded-t-lg">
                <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2">
                    <svg class="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    周期実行スケジュール設定
                </h2>
                <button onclick="closeScheduleModal()" class="text-gray-500 hover:text-gray-900 text-2xl leading-none">&times;</button>
            </div>
            <div class="p-6 space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">実行タイプ</label>
                    <select id="schedType" class="w-full border p-2 rounded focus:ring focus:ring-blue-100 outline-none" onchange="updateSchedUI()">
                        <option value="none">未設定 (スケジュールなし)</option>
                        <option value="interval">一定間隔 (秒/分/時間)</option>
                        <option value="daily">毎日 特定の時間</option>
                        <option value="date">特定の日付と時間 (1回のみ)</option>
                        <option value="cron">Cron式 (高度なスケジュール)</option>
                    </select>
                </div>
                
                <!-- Type: Interval -->
                <div id="uiInterval" class="sched-ui">
                    <label class="block text-sm font-medium text-gray-700 mb-1">実行間隔</label>
                    <div class="flex gap-2">
                        <input type="number" id="schedIntervalValue" class="border p-2 rounded flex-1 focus:ring focus:ring-blue-100 outline-none" value="60" min="1">
                        <select id="schedIntervalUnit" class="border p-2 rounded w-32 focus:ring focus:ring-blue-100 outline-none">
                            <option value="1">秒ごと</option>
                            <option value="60" selected>分ごと</option>
                            <option value="3600">時間ごと</option>
                        </select>
                    </div>
                </div>

                <!-- Type: Daily -->
                <div id="uiDaily" class="sched-ui hidden-el">
                    <label class="block text-sm font-medium text-gray-700 mb-1">実行時間 (HH:MM)</label>
                    <input type="time" id="schedDailyTime" class="border p-2 rounded w-full focus:ring focus:ring-blue-100 outline-none" value="12:00">
                </div>

                <!-- Type: Date -->
                <div id="uiDate" class="sched-ui hidden-el">
                    <label class="block text-sm font-medium text-gray-700 mb-1">実行日時</label>
                    <input type="datetime-local" id="schedDateVal" class="border p-2 rounded w-full focus:ring focus:ring-blue-100 outline-none">
                </div>

                <!-- Type: Cron -->
                <div id="uiCron" class="sched-ui hidden-el">
                    <label class="block text-sm font-medium text-gray-700 mb-1">Cron式 (分 時 日 月 曜日)</label>
                    <input type="text" id="schedCronExp" class="border p-2 rounded w-full font-mono focus:ring focus:ring-blue-100 outline-none" placeholder="* * * * *">
                    <p class="text-xs text-gray-500 mt-1">例: <code class="bg-gray-100 px-1 rounded">0 12 * * 1-5</code> (平日12時)</p>
                </div>
            </div>
            <div class="p-4 border-t bg-gray-50 rounded-b-lg flex justify-between gap-3">
                <button onclick="clearSchedule()" class="px-4 py-2 text-red-600 bg-red-50 hover:bg-red-100 rounded transition font-medium border border-red-200">スケジュールクリア</button>
                <div class="flex gap-2">
                    <button onclick="closeScheduleModal()" class="px-4 py-2 text-gray-600 hover:bg-gray-200 rounded transition font-medium">キャンセル</button>
                    <button onclick="saveSchedule()" class="bg-purple-600 text-white px-6 py-2 rounded hover:bg-purple-700 transition shadow-sm font-medium">設定を保存</button>
                </div>
            </div>
        </div>
    </div>

    <!-- 実行ログ（所要時間・履歴）モーダル -->
    <div id="historyModal" class="modal fixed inset-0 bg-black bg-opacity-60 items-center justify-center z-50 p-4">
        <div class="bg-white rounded-lg shadow-2xl w-full max-w-4xl flex flex-col max-h-[85vh]">
            <div class="p-4 border-b flex justify-between items-center bg-gray-100 rounded-t-lg">
                <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2" id="historyModalTitle">
                    <svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                    実行ログ
                </h2>
                <button onclick="closeRunHistoryModal()" class="text-gray-500 hover:text-gray-900 text-3xl leading-none">&times;</button>
            </div>
            <div class="flex-1 p-4 overflow-y-auto bg-white">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="bg-gray-50 border-b">
                            <th class="p-3 font-semibold text-gray-600 text-sm">開始時間</th>
                            <th class="p-3 font-semibold text-gray-600 text-sm">終了時間</th>
                            <th class="p-3 font-semibold text-gray-600 text-sm">所要時間</th>
                            <th class="p-3 font-semibold text-gray-600 text-sm">ステータス</th>
                        </tr>
                    </thead>
                    <tbody id="historyList" class="divide-y divide-gray-100 text-sm">
                        <!-- JSにて動的に注入 -->
                    </tbody>
                </table>
            </div>
            <div class="p-4 border-t bg-gray-50 rounded-b-lg flex flex-col sm:flex-row justify-between items-center gap-4">
                <button onclick="downloadLogsFromHistory()" class="bg-blue-600 text-white px-5 py-2 rounded hover:bg-blue-700 transition font-medium shadow-sm flex items-center gap-2 w-full sm:w-auto justify-center">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                    コンソールログ出力 (全件DL)
                </button>
                <button onclick="closeRunHistoryModal()" class="px-6 py-2 text-gray-600 bg-gray-200 hover:bg-gray-300 rounded transition font-medium w-full sm:w-auto">閉じる</button>
            </div>
        </div>
    </div>

    <!-- コンソールログ モーダル -->
    <div id="logModal" class="modal fixed inset-0 bg-black bg-opacity-60 items-center justify-center z-50 p-4">
        <div class="bg-white rounded-lg shadow-2xl w-full max-w-5xl flex flex-col h-[80vh]">
            <div class="p-4 border-b flex justify-between items-center bg-gray-100 rounded-t-lg">
                <h2 class="text-lg font-bold text-gray-800 flex items-center gap-2" id="modalTitle">
                    <span class="w-3 h-3 rounded-full bg-green-500 animate-pulse"></span>
                    コンソール出力
                </h2>
                <div class="flex gap-3">
                    <button onclick="downloadLogs()" class="bg-blue-500 text-white px-3 py-1 rounded text-sm hover:bg-blue-600 shadow-sm transition">DL</button>
                    <button onclick="clearLogs()" class="bg-red-500 text-white px-3 py-1 rounded text-sm hover:bg-red-600 shadow-sm transition">クリア</button>
                    <button onclick="closeLogModal()" class="text-gray-500 hover:text-gray-900 text-3xl leading-none">&times;</button>
                </div>
            </div>
            <div class="flex-1 p-4 bg-gray-900 overflow-y-auto" id="logContentContainer">
                <pre id="logContent" class="text-green-400 font-mono text-sm whitespace-pre-wrap"></pre>
            </div>
            <div class="p-3 border-t bg-gray-100 rounded-b-lg flex justify-between items-center">
                <span class="text-sm text-gray-500">リアルタイム監視中...</span>
                <button onclick="closeLogModal()" class="bg-gray-600 text-white px-5 py-2 rounded hover:bg-gray-700 transition font-medium">閉じる</button>
            </div>
        </div>
    </div>

    <script>
        let currentLogTaskId = null;
        let logPollInterval = null;
        let currentSchedTaskId = null;
        let currentHistoryTaskId = null;
        let allTasksData = {};

        document.addEventListener('DOMContentLoaded', () => {
            fetchTasks();
            setInterval(fetchTasks, 2000);
            setInterval(fetchStats, 3000);
        });

        async function fetchStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                document.getElementById('cpuVal').innerText = data.cpu;
                document.getElementById('memVal').innerText = data.memory;
            } catch(e) {}
        }

        async function fetchTasks() {
            try {
                const res = await fetch('/api/tasks');
                const tasks = await res.json();
                allTasksData = tasks;
                renderTasks(tasks);
            } catch (e) {}
        }

        function formatScheduleDisplay(sched) {
            if (!sched) return '<span class="text-gray-400">未設定</span>';
            if (sched.startsWith('interval:')) {
                let sec = parseInt(sched.split(':')[1]);
                if (sec >= 3600 && sec % 3600 === 0) return `${sec/3600}時間ごと`;
                if (sec >= 60 && sec % 60 === 0) return `${sec/60}分ごと`;
                return `${sec}秒ごと`;
            }
            if (sched.startsWith('daily:')) return `毎日 ${sched.split('daily:')[1]}`;
            if (sched.startsWith('date:')) return `指定 ${sched.split('date:')[1]}`;
            if (sched.startsWith('cron:')) return `Cron [${sched.split('cron:')[1]}]`;
            return sched; // 互換用
        }

        function renderTasks(tasks) {
            const tbody = document.getElementById('taskList');
            let html = '';
            
            if(Object.keys(tasks).length === 0) {
                html = `<tr><td colspan="5" class="p-8 text-center text-gray-500">登録されているタスクはありません</td></tr>`;
            } else {
                Object.values(tasks).forEach(task => {
                    const isRunningOrQueued = task.status === '実行中' || task.status === '待機キュー';
                    
                    html += `
                        <tr class="hover:bg-gray-50 transition border-b border-gray-100 last:border-0">
                            <td class="p-4 font-medium text-gray-800 align-middle whitespace-nowrap overflow-hidden text-ellipsis max-w-[12rem]" title="${task.name}">${task.name}</td>
                            <td class="p-4 text-sm text-gray-500 font-mono align-middle whitespace-nowrap overflow-hidden text-ellipsis max-w-[12rem]" title="${task.filepath}">${task.filepath}</td>
                            <td class="p-4 align-middle whitespace-nowrap">
                                <span class="px-3 py-1 rounded-full text-xs font-semibold text-white ${getStatusColor(task.status)} shadow-sm inline-block">
                                    ${task.status || '不明'}
                                </span>
                            </td>
                            <td class="p-4 text-xs text-gray-500 leading-relaxed min-w-[14rem] align-middle whitespace-nowrap">
                                <span class="font-bold text-purple-600 flex items-center gap-1">
                                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                                    ${formatScheduleDisplay(task.scheduled_time)}
                                </span>
                                <div class="mt-1 flex items-center gap-1">
                                    <span class="text-gray-400">最終:</span> ${task.last_run ? task.last_run : '未実行'}
                                </div>
                            </td>
                            <td class="p-4 align-middle">
                                <!-- 縦1列に並べるためのフレックスコンテナ -->
                                <div class="flex flex-col gap-2 w-full max-w-[100px] ml-auto">
                                    <button onclick="runTask('${task.id}')" class="bg-green-500 text-white px-2 py-1.5 rounded text-xs font-semibold hover:bg-green-600 disabled:opacity-50 transition shadow-sm w-full text-center" ${isRunningOrQueued ? 'disabled' : ''}>手動実行</button>
                                    <button onclick="stopTask('${task.id}')" class="bg-red-500 text-white px-2 py-1.5 rounded text-xs font-semibold hover:bg-red-600 disabled:opacity-30 transition shadow-sm w-full text-center" ${!isRunningOrQueued ? 'disabled' : ''}>強制終了</button>
                                    
                                    <button onclick="openScheduleModal('${task.id}')" class="bg-purple-500 text-white px-2 py-1.5 rounded text-xs font-semibold hover:bg-purple-600 transition shadow-sm w-full text-center">周期設定</button>
                                    <button onclick="openLogModal('${task.id}', '${task.name}')" class="bg-gray-700 text-white px-2 py-1.5 rounded text-xs font-semibold hover:bg-gray-800 transition shadow-sm w-full text-center">コンソール</button>
                                    
                                    <button onclick="openRunHistoryModal('${task.id}', '${task.name}')" class="bg-blue-500 text-white px-2 py-1.5 rounded text-xs font-semibold hover:bg-blue-600 transition shadow-sm w-full text-center">実行ログ</button>
                                    
                                    <button onclick="deleteTask('${task.id}')" class="text-red-600 bg-red-50 hover:bg-red-100 px-2 py-1.5 rounded text-xs font-bold transition border border-red-200 w-full text-center" title="削除">削除</button>
                                </div>
                            </td>
                        </tr>
                    `;
                });
            }
            tbody.innerHTML = html;
        }

        function getStatusColor(status) {
            switch(status) {
                case '実行中': return 'bg-blue-500';
                case '待機キュー': return 'bg-yellow-500';
                case '待機中': return 'bg-gray-400';
                case 'スケジュール済み': return 'bg-purple-500';
                case 'エラー': return 'bg-red-500';
                default: return 'bg-gray-400';
            }
        }

        async function addTask() {
            const name = document.getElementById('taskName').value.trim();
            const filepath = document.getElementById('taskPath').value.trim();
            
            if(!name || !filepath) {
                alert("タスク名とファイルパスを入力してください。");
                return;
            }

            try {
                const res = await fetch('/api/tasks/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ name, filepath })
                });
                
                const data = await res.json();
                if (res.ok) {
                    document.getElementById('taskName').value = '';
                    document.getElementById('taskPath').value = '';
                    fetchTasks();
                } else {
                    alert("エラー: " + data.error);
                }
            } catch (e) {
                alert("通信エラーが発生しました。");
            }
        }

        async function runTask(id) {
            await fetch(`/api/tasks/${id}/run`, { method: 'POST' });
            fetchTasks();
        }

        async function stopTask(id) {
            await fetch(`/api/tasks/${id}/stop`, { method: 'POST' });
            fetchTasks();
        }

        async function deleteTask(id) {
            if(confirm("このタスクを削除してもよろしいですか？")) {
                await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
                fetchTasks();
            }
        }

        // --- 周期スケジュール関連 ---
        function openScheduleModal(id) {
            currentSchedTaskId = id;
            document.getElementById('scheduleModal').classList.add('active');
            
            // 現在のスケジュール設定をUIに復元
            const task = allTasksData[id];
            const schedType = document.getElementById('schedType');
            
            if (task && task.scheduled_time) {
                const sched = task.scheduled_time;
                if (sched.startsWith('interval:')) {
                    schedType.value = 'interval';
                    let sec = parseInt(sched.split(':')[1]);
                    if (sec >= 3600 && sec % 3600 === 0) {
                        document.getElementById('schedIntervalValue').value = sec / 3600;
                        document.getElementById('schedIntervalUnit').value = '3600';
                    } else if (sec >= 60 && sec % 60 === 0) {
                        document.getElementById('schedIntervalValue').value = sec / 60;
                        document.getElementById('schedIntervalUnit').value = '60';
                    } else {
                        document.getElementById('schedIntervalValue').value = sec;
                        document.getElementById('schedIntervalUnit').value = '1';
                    }
                } else if (sched.startsWith('daily:')) {
                    schedType.value = 'daily';
                    document.getElementById('schedDailyTime').value = sched.split(':')[1];
                } else if (sched.startsWith('date:')) {
                    schedType.value = 'date';
                    const dateStr = sched.split('date:')[1];
                    document.getElementById('schedDateVal').value = dateStr.replace(' ', 'T');
                } else if (sched.startsWith('cron:')) {
                    schedType.value = 'cron';
                    document.getElementById('schedCronExp').value = sched.split('cron:')[1];
                }
            } else {
                schedType.value = 'none';
            }
            updateSchedUI();
        }

        function closeScheduleModal() {
            document.getElementById('scheduleModal').classList.remove('active');
            currentSchedTaskId = null;
        }

        function updateSchedUI() {
            const type = document.getElementById('schedType').value;
            document.querySelectorAll('.sched-ui').forEach(el => el.classList.add('hidden-el'));
            
            if (type === 'interval') document.getElementById('uiInterval').classList.remove('hidden-el');
            else if (type === 'daily') document.getElementById('uiDaily').classList.remove('hidden-el');
            else if (type === 'date') document.getElementById('uiDate').classList.remove('hidden-el');
            else if (type === 'cron') document.getElementById('uiCron').classList.remove('hidden-el');
        }
        
        async function clearSchedule() {
            if (!currentSchedTaskId) return;
            try {
                await fetch(`/api/tasks/${currentSchedTaskId}/schedule`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ time: "none" })
                });
                closeScheduleModal();
                fetchTasks();
            } catch(e) {
                alert("クリアに失敗しました");
            }
        }

        async function saveSchedule() {
            if (!currentSchedTaskId) return;
            
            const type = document.getElementById('schedType').value;
            let schedStr = "";

            if (type === 'interval') {
                const val = parseInt(document.getElementById('schedIntervalValue').value) || 60;
                const unit = parseInt(document.getElementById('schedIntervalUnit').value) || 1;
                schedStr = `interval:${val * unit}`;
            } else if (type === 'daily') {
                const time = document.getElementById('schedDailyTime').value;
                if (!time) { alert('時間を入力してください'); return; }
                schedStr = `daily:${time}`;
            } else if (type === 'date') {
                const d = document.getElementById('schedDateVal').value;
                if (!d) { alert('日時を入力してください'); return; }
                schedStr = `date:${d.replace('T', ' ')}`;
            } else if (type === 'cron') {
                const cron = document.getElementById('schedCronExp').value.trim();
                if (!cron) { alert('Cron式を入力してください'); return; }
                schedStr = `cron:${cron}`;
            } else {
                schedStr = "none";
            }

            try {
                await fetch(`/api/tasks/${currentSchedTaskId}/schedule`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ time: schedStr })
                });
                closeScheduleModal();
                fetchTasks();
            } catch(e) {
                alert("設定に失敗しました");
            }
        }

        // --- 実行ログ (所要時間) モーダル ---
        async function openRunHistoryModal(id, taskName) {
            currentHistoryTaskId = id;
            document.getElementById('historyModalTitle').innerHTML = `
                <svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                実行ログ - ${taskName}`;
            document.getElementById('historyModal').classList.add('active');
            
            const tbody = document.getElementById('historyList');
            tbody.innerHTML = '<tr><td colspan="4" class="p-4 text-center text-gray-500">読み込み中...</td></tr>';
            
            try {
                const res = await fetch(`/api/tasks/${id}/history`);
                const history = await res.json();
                
                if (history.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" class="p-4 text-center text-gray-500">実行履歴がありません</td></tr>';
                    return;
                }
                
                let html = '';
                history.forEach(h => {
                    const isError = h.status.includes('エラー') || h.status.includes('強制終了');
                    const statusClass = isError ? 'text-red-600 font-semibold' : 'text-green-600 font-semibold';
                    html += `
                        <tr class="hover:bg-gray-50 transition">
                            <td class="p-3 text-gray-800 whitespace-nowrap">${h.start}</td>
                            <td class="p-3 text-gray-800 whitespace-nowrap">${h.end}</td>
                            <td class="p-3 text-gray-600 whitespace-nowrap">${h.duration} 秒</td>
                            <td class="p-3 whitespace-nowrap ${statusClass}">${h.status}</td>
                        </tr>
                    `;
                });
                tbody.innerHTML = html;
                
            } catch(e) {
                tbody.innerHTML = '<tr><td colspan="4" class="p-4 text-center text-red-500">履歴の取得に失敗しました</td></tr>';
            }
        }

        function closeRunHistoryModal() {
            document.getElementById('historyModal').classList.remove('active');
            currentHistoryTaskId = null;
        }

        function downloadLogsFromHistory() {
            if(!currentHistoryTaskId) return;
            window.location.href = `/api/tasks/${currentHistoryTaskId}/logs/download`;
        }

        // --- コンソールログ モーダル関連 ---
        function openLogModal(id, taskName) {
            currentLogTaskId = id;
            document.getElementById('modalTitle').innerHTML = `<span class="w-3 h-3 rounded-full bg-green-500 animate-pulse"></span> コンソール出力 - ${taskName}`;
            document.getElementById('logContent').textContent = '読み込み中...';
            document.getElementById('logModal').classList.add('active');
            
            fetchLogs();
            logPollInterval = setInterval(fetchLogs, 1000);
        }

        function closeLogModal() {
            document.getElementById('logModal').classList.remove('active');
            currentLogTaskId = null;
            if(logPollInterval) {
                clearInterval(logPollInterval);
                logPollInterval = null;
            }
        }

        async function fetchLogs() {
            if(!currentLogTaskId) return;
            try {
                const res = await fetch(`/api/tasks/${currentLogTaskId}/logs`);
                const logs = await res.json();
                const container = document.getElementById('logContentContainer');
                const content = document.getElementById('logContent');
                
                const isScrolledToBottom = container.scrollHeight - container.clientHeight <= container.scrollTop + 50;
                content.textContent = logs.join('\\n');
                if (isScrolledToBottom) {
                    container.scrollTop = container.scrollHeight;
                }
            } catch(e) {}
        }

        async function clearLogs() {
            if(!currentLogTaskId) return;
            if(confirm("このタスクのコンソールログをクリアしますか？")) {
                await fetch(`/api/tasks/${currentLogTaskId}/logs/clear`, { method: 'POST' });
                document.getElementById('logContent').textContent = '';
            }
        }

        function downloadLogs() {
            if(!currentLogTaskId) return;
            window.location.href = `/api/tasks/${currentLogTaskId}/logs/download`;
        }
    </script>
</body>
</html>
"""

# ==========================================
# Web API & ルーティング
# ==========================================
@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/stats")
def stats(): 
    return jsonify(task_manager.get_system_stats())

@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    return jsonify(task_manager.get_all_tasks_info())

@app.route("/api/tasks/add", methods=["POST"])
def add_task_api():
    data = request.json
    name = data.get("name")
    filepath = data.get("filepath")
    if not name or not filepath:
        return jsonify({"error": "Invalid data"}), 400
    try:
        task_id = task_manager.add_task(name, filepath)
        return jsonify({"id": task_id})
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task_api(task_id):
    success = task_manager.delete_task(task_id)
    return jsonify({"success": success})

@app.route("/api/tasks/<task_id>/run", methods=["POST"])
def run_task_api(task_id):
    success = task_manager.run_task(task_id)
    return jsonify({"success": success})

@app.route("/api/tasks/<task_id>/stop", methods=["POST"])
def stop_task_api(task_id):
    success = task_manager.stop_task(task_id)
    return jsonify({"success": success})

@app.route("/api/tasks/<task_id>/schedule", methods=["POST"])
def schedule_task_api(task_id):
    data = request.json
    time_str = data.get("time")
    success = task_manager.schedule_task(task_id, time_str)
    return jsonify({"success": success})

@app.route("/api/tasks/<task_id>/logs", methods=["GET"])
def get_logs_api(task_id):
    logs = task_manager.get_task_logs(task_id)
    return jsonify(logs)

@app.route("/api/tasks/<task_id>/logs/clear", methods=["POST"])
def clear_task_logs_api(task_id):
    success = task_manager.clear_task_logs(task_id)
    return jsonify({"success": success})

@app.route("/api/tasks/<task_id>/logs/download", methods=["GET"])
def download_logs_api(task_id):
    logs = task_manager.get_task_logs(task_id)
    content = "\n".join(logs)
    f = BytesIO(content.encode('utf-8'))
    return send_file(f, mimetype='text/plain', as_attachment=True, download_name=f'log_{task_id}.txt')

@app.route("/api/tasks/<task_id>/history", methods=["GET"])
def get_history_api(task_id):
    with task_manager.lock:
        t = task_manager.tasks.get(task_id)
        return jsonify(t.get("run_history", []) if t else [])

if __name__ == "__main__":
    print("="*50)
    print(" PyTask Scheduler 起動中...")
    print(" ブラウザで http://127.0.0.1:5000 にアクセスしてください")
    print(" (停止するには Ctrl+C を押してください)")
    print("="*50)
    app.run(host="127.0.0.1", port=5000, debug=False)