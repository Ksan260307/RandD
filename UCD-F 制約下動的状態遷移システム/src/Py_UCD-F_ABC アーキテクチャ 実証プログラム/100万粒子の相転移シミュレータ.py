import math
import sys

try:
    import taichi as ti
except ImportError:
    print("エラー: taichi がインストールされていません。")
    print("コマンドプロンプトやターミナルで 'pip install taichi' を実行してください。")
    sys.exit(1)

# ==========================================
# Py_UCD-F_ABC アーキテクチャ 実証プログラム
# ==========================================

# ti.initでGPUを自動検知して有効化します（これが圧倒的計算力の源です）
ti.init(arch=ti.gpu)

# 粒子の数（なんと100万個！）
N_PARTICLES = 1_000_000
WIDTH, HEIGHT = 800, 800

# GPUメモリ上に配置されるデータ配列（Bit-packed SoAの概念に相当）
pos = ti.Vector.field(2, dtype=float, shape=N_PARTICLES)
vel = ti.Vector.field(2, dtype=float, shape=N_PARTICLES) # 追加：速度ベクトル
target_offset = ti.Vector.field(2, dtype=float, shape=N_PARTICLES)
seed = ti.field(dtype=float, shape=N_PARTICLES)
pixels = ti.Vector.field(3, dtype=float, shape=(WIDTH, HEIGHT))

@ti.kernel
def init_particles():
    """初期化処理（GPUで並列実行されます）"""
    for i in pos:
        # ランダムな位置に配置
        pos[i] = [ti.random(), ti.random()]
        vel[i] = [0.0, 0.0] # 速度を初期化
        seed[i] = ti.random()
        
        # 観測された際（実体化時）にマウスの周りに作る形の目標座標
        r = ti.random() * 0.15
        theta = ti.random() * math.pi * 2.0
        target_offset[i] = [r * ti.cos(theta), r * ti.sin(theta)]

@ti.kernel
def fade_pixels():
    """画面の残像（軌跡）を作る処理"""
    for i, j in pixels:
        pixels[i, j] *= 0.80 # 残像を少し短くして動きをシャープに

@ti.kernel
def update_particles(t: float, mouse_x: float, mouse_y: float):
    """
    メインロジック: 100万個の粒子計算をGPUで同時実行します。
    """
    m = ti.Vector([mouse_x, mouse_y])
    
    for i in pos:
        p = pos[i]
        v = vel[i]
        
        # マウス（観測者）との距離と方向
        diff = m - p
        dist = diff.norm()
        
        # ==========================================
        # 相転移ロジック：観測状態による劇的な振る舞いの変化
        # ==========================================
        radius = 0.5 # 影響範囲を広くする
        
        if dist > radius:
            # 【非観測状態（確率雲）】
            # 遠くにある時は、砂嵐のようにランダムに漂う（ブラウン運動）
            noise = ti.Vector([ti.random() - 0.5, ti.random() - 0.5]) * 0.005
            v = v * 0.8 + noise
        else:
            # 【観測状態（実体化して強烈な渦を巻く）】
            # マウスに近づくほど、ブラックホールのように吸い込まれながら回転する
            force_dir = diff.normalized()
            
            # マウスへ向かう引力
            pull = force_dir * 0.0015
            # 渦を巻く横方向の力
            swirl = ti.Vector([-force_dir[1], force_dir[0]]) * 0.004
            
            # 観測が強い（近い）ほど力が強くなる
            intensity = 1.0 - (dist / radius)
            v = v * 0.98 + (pull + swirl) * intensity
        
        # 速度を位置に適用
        p += v
        
        # 画面端をループ（宇宙空間のような繋がり）
        p[0] = p[0] - ti.floor(p[0])
        p[1] = p[1] - ti.floor(p[1])
            
        # 計算結果を保存
        pos[i] = p
        vel[i] = v
        
        # ==========================================
        # 描画（ピクセルへの書き込み）
        # ==========================================
        ix = int(p[0] * WIDTH)
        iy = int(p[1] * HEIGHT)
        
        if 0 <= ix < WIDTH and 0 <= iy < HEIGHT:
            # 速度が速い（渦に巻き込まれている）ほど白く激しく輝く
            speed = v.norm() * 100.0
            
            # ベースは暗い青、高速時は眩しいシアン〜白
            color = ti.Vector([
                ti.min(speed * 0.3, 1.0),       # R (速いと白っぽくなる)
                ti.min(speed * 0.8, 1.0),       # G (シアン系)
                ti.min(0.2 + speed, 1.0)        # B (ベースの青)
            ])
            
            # ピクセルに加算合成（100万個が密集すると白飛びして圧倒的な光の束になる）
            pixels[ix, iy] += color * 0.15

def main():
    print("⚡ 1,000,000 粒子のシミュレーションを起動中...")
    print("💡 ウィンドウ上でマウスを動かして「観測」してみてください。")
    
    init_particles()
    
    # TaichiのビルトインGUIを使用
    gui = ti.GUI("1,000,000 Particles - Phase Transition", res=(WIDTH, HEIGHT), background_color=0x000000)
    
    time_elapsed = 0.0
    while gui.running:
        # マウス座標を取得
        mouse_x, mouse_y = gui.get_cursor_pos()
        
        # GPUカーネルを実行
        fade_pixels()
        update_particles(time_elapsed, mouse_x, mouse_y)
        
        # 計算されたピクセルデータを画面にセットして描画
        gui.set_image(pixels)
        gui.show()
        
        time_elapsed += 0.03

if __name__ == "__main__":
    main()