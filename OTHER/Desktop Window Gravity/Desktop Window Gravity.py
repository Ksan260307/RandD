import sys
import ctypes
import time
import unittest
import random
from unittest.mock import patch, MagicMock

# --- 構造体定義 ---
class RECT(ctypes.Structure):
    """Windows APIのRECT構造体"""
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
    ]


# --- アプリケーション本体 ---
class WindowGravityApp:
    def __init__(self):
        self.running = False
        # Windows環境以外でモジュールインポートエラーを防ぐための処置
        if hasattr(ctypes, 'windll'):
            self.user32 = ctypes.windll.user32
        else:
            self.user32 = MagicMock()

    def get_active_window(self):
        """アクティブなウィンドウのハンドルを取得"""
        return self.user32.GetForegroundWindow()

    def get_class_name(self, hwnd):
        """ウィンドウのクラス名を取得（システムウィンドウ除外用）"""
        if not hasattr(ctypes, 'create_unicode_buffer'):
            return ""
        buffer = ctypes.create_unicode_buffer(256)
        self.user32.GetClassNameW(hwnd, buffer, 256)
        return buffer.value

    def get_all_visible_windows(self):
        """画面上の可視ウィンドウを取得（タスクバー等を除外）"""
        windows = []
        # 落としたくないシステム関連のウィンドウクラス名
        exclude_classes = [
            "Progman", "Shell_TrayWnd", "WorkerW", 
            "Windows.UI.Core.CoreWindow", "TopLevelWindowForOverflowShadow"
        ]

        def callback(hwnd, lParam):
            if self.user32.IsWindowVisible(hwnd):
                length = self.user32.GetWindowTextLengthW(hwnd)
                # タイトルがない透明なウィンドウなどを弾く
                if length > 0:
                    cls_name = self.get_class_name(hwnd)
                    if cls_name not in exclude_classes:
                        # 小さすぎるウィンドウを除外
                        rect = RECT()
                        self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                        w = rect.right - rect.left
                        h = rect.bottom - rect.top
                        if w > 50 and h > 50:
                            windows.append(hwnd)
            return True

        # コールバック関数の型を定義して EnumWindows を実行
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        self.user32.EnumWindows(EnumWindowsProc(callback), 0)
        return windows

    def get_screen_size(self):
        """メインディスプレイの解像度（幅、高さ）を取得"""
        width = self.user32.GetSystemMetrics(0)
        height = self.user32.GetSystemMetrics(1)
        return width, height

    def get_window_rect(self, hwnd):
        """ウィンドウの座標とサイズを取得"""
        rect = RECT()
        self.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        return float(rect.left), float(rect.top), float(width), float(height)

    def set_window_pos(self, hwnd, x, y):
        """ウィンドウの位置を強制的に変更"""
        # 0x0001 (SWP_NOSIZE) | 0x0004 (SWP_NOZORDER) = 5
        self.user32.SetWindowPos(hwnd, 0, int(x), int(y), 0, 0, 5)

    def is_lbutton_pressed(self):
        """マウスの左ボタンが押されているか判定"""
        return (self.user32.GetAsyncKeyState(1) & 0x8000) != 0

    def calculate_physics_2d(self, x, y, width, height, screen_w, screen_h, vx, vy, gravity=0.3):
        """重力ありの1フレーム分の物理演算（落下、摩擦、壁でのバウンド）"""
        
        # 横方向の摩擦（減衰を弱め、長く滑るように）
        vx *= 0.98
        
        # 常に重力が働く（下方向へ加速）
        vy += gravity

        new_x = x + vx
        new_y = y + vy

        # 反発係数（跳ね返りの強さ：1.0に近いほどエネルギーが保存される）
        bounce = -0.92
        
        # 左右の壁との衝突判定
        if new_x < 0:
            new_x = 0
            vx *= bounce
        elif new_x + width > screen_w:
            new_x = screen_w - width
            vx *= bounce

        # 上下の壁（タスクバー考慮）との衝突判定
        floor_y = screen_h - 40
        if new_y < 0:
            new_y = 0
            vy *= bounce
        elif new_y + height > floor_y:
            new_y = floor_y - height
            vy *= bounce
            
            # 床でバウンドが小さくなったら縦の動きを静止させる（プルプル防止）
            if abs(vy) < gravity * 2.0:
                vy = 0.0

        # 横の動きが小さくなったら静止させる
        if abs(vx) < 0.5: 
            vx = 0.0

        return new_x, new_y, vx, vy

    def run(self, multi=False, frames=0, delay=3, fps_wait=0.016):
        """アプリのメインループ"""
        if multi:
            print(f"【警告】{delay}秒後に、画面上の【すべてのウィンドウ】が落下します！")
        else:
            print(f"【警告】{delay}秒後にアクティブなウィンドウが落下します！")
            print("落としたいウィンドウをクリックして最前面にしてください...")
            
        print("マウスでタイトルバーを掴んで放り投げることができます！")
        
        if delay > 0:
            time.sleep(delay)

        # ターゲットとなるウィンドウのリストを取得
        if multi:
            hwnds = self.get_all_visible_windows()
            if not hwnds:
                print("対象となるウィンドウが見つかりませんでした。")
                return
        else:
            hwnd = self.get_active_window()
            if not hwnd:
                print("ウィンドウが取得できませんでした。")
                return
            hwnds = [hwnd]

        screen_w, screen_h = self.get_screen_size()
        
        # 各ウィンドウの状態を保持する辞書
        window_states = {}
        for h in hwnds:
            x, y, width, height = self.get_window_rect(h)
            window_states[h] = {
                'x': x, 'y': y, 'w': width, 'h': height,
                # 最初は横に少し弾け飛ぶように初速をつける
                'vx': random.choice([-1, 1]) * random.uniform(2.0, 5.0),
                'vy': random.uniform(-2.0, 2.0),
                'prev_x': x, 'prev_y': y
            }

        print(f"🚀 {'マルチ' if multi else 'シングル'}重力モード開始！ (Ctrl+Cでいつでも終了できます)")

        self.running = True
        count = 0
        try:
            while self.running:
                if frames > 0 and count >= frames:
                    break
                count += 1

                # ユーザーが現在操作中のウィンドウを特定
                active_hwnd = self.get_active_window()
                is_clicking = self.is_lbutton_pressed()

                for h, state in window_states.items():
                    actual_x, actual_y, _, _ = self.get_window_rect(h)
                    
                    is_active = (active_hwnd == h)

                    if is_active and is_clicking:
                        # 掴んでいる間は物理演算を止め、マウスの動きから初速をチャージ
                        state['vx'] = (actual_x - state['prev_x']) * 2.5
                        state['vy'] = (actual_y - state['prev_y']) * 2.5
                        state['x'], state['y'] = actual_x, actual_y
                    else:
                        # ユーザーの手動操作等で強制移動された場合の追従
                        if abs(actual_x - state['x']) > 20 or abs(actual_y - state['y']) > 20:
                            state['x'], state['y'] = actual_x, actual_y

                        # 重力・慣性移動の計算 (弱めの重力 0.3 を適用)
                        state['x'], state['y'], state['vx'], state['vy'] = self.calculate_physics_2d(
                            state['x'], state['y'], state['w'], state['h'], 
                            screen_w, screen_h, state['vx'], state['vy'], gravity=0.3
                        )
                        
                        # ウィンドウを動かす
                        self.set_window_pos(h, state['x'], state['y'])

                    state['prev_x'], state['prev_y'] = actual_x, actual_y

                # 60FPS相当のウェイト
                if fps_wait > 0:
                    time.sleep(fps_wait)
                    
            print("物理演算ループ終了。")
            
        except KeyboardInterrupt:
            print("\n強制停止しました。安全に終了します。")
        finally:
            self.running = False


# --- 動的単体テスト（全網羅） ---
class TestWindowGravityApp(unittest.TestCase):
    def setUp(self):
        self.app = WindowGravityApp()
        self.app.user32 = MagicMock()

    def test_get_active_window(self):
        self.app.user32.GetForegroundWindow.return_value = 9999
        self.assertEqual(self.app.get_active_window(), 9999)

    def test_get_screen_size(self):
        self.app.user32.GetSystemMetrics.side_effect = lambda x: 1920 if x == 0 else 1080
        self.assertEqual(self.app.get_screen_size(), (1920, 1080))

    def test_get_window_rect(self):
        self.app.get_window_rect(123)
        self.assertTrue(self.app.user32.GetWindowRect.called)
        
    def test_set_window_pos(self):
        self.app.set_window_pos(123, 10.5, 20.8)
        self.app.user32.SetWindowPos.assert_called_with(123, 0, 10, 20, 0, 0, 5)

    def test_is_lbutton_pressed(self):
        self.app.user32.GetAsyncKeyState.return_value = 0x8000
        self.assertTrue(self.app.is_lbutton_pressed())
        self.app.user32.GetAsyncKeyState.return_value = 0x0001
        self.assertFalse(self.app.is_lbutton_pressed())

    def test_calculate_physics_2d_friction_and_gravity(self):
        # 重力0にして摩擦(X軸)のテスト
        nx, ny, nvx, nvy = self.app.calculate_physics_2d(
            x=100, y=100, width=100, height=100, screen_w=1920, screen_h=1080, vx=10, vy=10, gravity=0.0
        )
        self.assertAlmostEqual(nvx, 10 * 0.98)
        self.assertAlmostEqual(nvy, 10.0) # Yは重力0なので速度変わらず
        self.assertEqual(nx, 100 + 10 * 0.98)
        
        # 重力ありのテスト
        _, _, _, nvy_grav = self.app.calculate_physics_2d(
            x=100, y=100, width=100, height=100, screen_w=1920, screen_h=1080, vx=0, vy=10, gravity=1.5
        )
        self.assertAlmostEqual(nvy_grav, 11.5)

    def test_calculate_physics_2d_bounce(self):
        # X軸（右の壁）と Y軸（下の壁）でのバウンドテスト
        nx, ny, nvx, nvy = self.app.calculate_physics_2d(
            x=1850, y=1000, width=100, height=100, screen_w=1920, screen_h=1080, vx=50, vy=50, gravity=1.5
        )
        f_vx = 50 * 0.98
        f_vy = 50 + 1.5
        self.assertAlmostEqual(nvx, f_vx * -0.92)
        self.assertAlmostEqual(nvy, f_vy * -0.92)
        self.assertEqual(nx, 1920 - 100)
        self.assertEqual(ny, 1080 - 40 - 100)

    @patch('time.sleep', return_value=None)
    @patch.object(WindowGravityApp, 'get_active_window', return_value=0)
    def test_run_no_window(self, mock_get_win, mock_sleep):
        self.app.run(delay=0)
        mock_get_win.assert_called_once()
        self.assertFalse(self.app.running)

    @patch('time.sleep', return_value=None)
    @patch.object(WindowGravityApp, 'get_active_window', return_value=123)
    @patch.object(WindowGravityApp, 'get_screen_size', return_value=(1920, 1080))
    @patch.object(WindowGravityApp, 'get_window_rect', return_value=(0, 0, 100, 100))
    @patch.object(WindowGravityApp, 'is_lbutton_pressed', return_value=False)
    @patch.object(WindowGravityApp, 'set_window_pos')
    def test_run_physics_loop(self, mock_set_pos, mock_click, mock_rect, mock_size, mock_win, mock_sleep):
        self.app.run(frames=1, delay=0, fps_wait=0)
        mock_set_pos.assert_called_once()
        self.assertFalse(self.app.running)

    @patch('time.sleep', return_value=None)
    @patch.object(WindowGravityApp, 'get_all_visible_windows', return_value=[111, 222])
    @patch.object(WindowGravityApp, 'get_screen_size', return_value=(1920, 1080))
    @patch.object(WindowGravityApp, 'get_window_rect', return_value=(0, 0, 100, 100))
    @patch.object(WindowGravityApp, 'is_lbutton_pressed', return_value=False)
    @patch.object(WindowGravityApp, 'set_window_pos')
    def test_run_multi_mode(self, mock_set_pos, mock_click, mock_rect, mock_size, mock_get_multi, mock_sleep):
        # マルチモードで複数ウィンドウに対して SetWindowPos が呼ばれるかのテスト
        self.app.run(multi=True, frames=1, delay=0, fps_wait=0)
        self.assertEqual(mock_set_pos.call_count, 2)

# --- エントリポイント ---
if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == "test":
            print("=== 動的単体テストを実行します ===")
            del sys.argv[1:] 
            unittest.main()
        elif arg == "multi":
            app = WindowGravityApp()
            app.run(multi=True)
        else:
            print(f"不明なコマンド: {arg}。 'test' または 'multi' を指定してください。")
    else:
        app = WindowGravityApp()
        app.run(multi=False)