import torch
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# ==========================================
# 🌟 UCD-Fベース 宇宙の初期設定
# ==========================================
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
NUM_STARS = 100_000   
NUM_LEADERS = 150     
G_CONST = 0.005       
DT = 0.5              

# 【設計書 4.1】 魂のビットパッキング用フラグマスク
# 32bitの代わりにテンソル効率の良い uint8 を使用し状態をパックする
FLAG_ACTIVE  = 0b0000_0001  # 生存状態
FLAG_PROMOTE = 0b0000_0010  # カオス領域での高解像度プロモート状態
FLAG_RUIN    = 0b0000_0100  # 破綻・地形化フラグ

# ==========================================
# 📦 状態の初期化 (SoA分離 & ビットパッキング)
# ==========================================
r = torch.rand(NUM_STARS, device=DEVICE) * 100.0
theta = torch.rand(NUM_STARS, device=DEVICE) * 2 * np.pi

# 物理座標と速度バッファ (設計書 4.1 物理座標のSoA分離)
pos = torch.stack([r * torch.cos(theta), r * torch.sin(theta)], dim=1)
vel = torch.stack([-pos[:, 1], pos[:, 0]], dim=1) / r.unsqueeze(1) * 2.5
vel += torch.randn_like(vel) * 0.2

# 状態ビットバッファ: 全エンティティに ACTIVE ビットを立てて初期化
state_buffer = torch.full((NUM_STARS,), FLAG_ACTIVE, dtype=torch.uint8, device=DEVICE)

# 【設計書 5.1】 局所時間拡張用: 星ごとの更新頻度 (1=毎フレーム, 2=2フレームに1回...)
time_dilation = torch.randint(1, 4, (NUM_STARS,), device=DEVICE, dtype=torch.int32)

# 【設計書 8.1】 VIFモデルの「Fatigue(疲労)」バッファ
# 強烈な重力場にさらされた際の不可逆的ダメージ（破綻値）を蓄積する
fatigue = torch.zeros(NUM_STARS, dtype=torch.float32, device=DEVICE)

# 【設計書 4.5】 マクロな確率雲パラメータへの圧縮 (特異点の状態)
bh_pos = torch.tensor([0.0, 0.0], device=DEVICE) 
bh_mass = torch.tensor(100.0, device=DEVICE)      
frame_count = 0

# ==========================================
# ⚙️ 状態遷移関数 C (Core Logic)
# ==========================================
def update_universe():
    global pos, vel, state_buffer, fatigue, time_dilation, bh_mass, frame_count
    frame_count += 1
    
    # 1. ビット演算による状態デコード (Stream Compactionの近似)
    is_active = (state_buffer & FLAG_ACTIVE) > 0
    
    # 2. 【設計書 5.1】 局所時間拡張 (Time Dilation)
    needs_update = (frame_count % time_dilation) == 0
    
    update_mask = is_active & needs_update
    alive_idx = update_mask.nonzero(as_tuple=True)[0]
    
    if len(alive_idx) == 0:
        return
    
    alive_pos = pos[alive_idx]
    
    # 3. 【設計書 4.7 / 6.2】 セクター・リーダー制による計算極小化と権威化
    num_current_leaders = min(NUM_LEADERS, len(alive_idx))
    leader_idx = torch.randperm(len(alive_idx), device=DEVICE)[:num_current_leaders]
    leaders_pos = alive_pos[leader_idx]
    
    diff = leaders_pos.unsqueeze(0) - alive_pos.unsqueeze(1)
    dist_sq = (diff ** 2).sum(dim=-1) + 1.0
    
    force_mag = G_CONST / dist_sq
    force_stars = (diff / torch.sqrt(dist_sq).unsqueeze(-1)) * force_mag.unsqueeze(-1)
    total_force = force_stars.sum(dim=1) 
    
    # 確率雲(ブラックホール)からの引力追加
    diff_bh = bh_pos - alive_pos
    dist_bh_sq = (diff_bh ** 2).sum(dim=-1) + 1.0
    dist_bh = torch.sqrt(dist_bh_sq)
    
    force_bh_mag = (G_CONST * bh_mass * 10) / dist_bh_sq
    total_force += (diff_bh / dist_bh.unsqueeze(-1)) * force_bh_mag.unsqueeze(-1)
    
    # 4. 速度・位置の更新
    vel[alive_idx] += total_force * DT
    pos[alive_idx] += vel[alive_idx] * DT
    
    # ==========================================
    # 🧠 UCD-F 高度ロジック適用セクション
    # ==========================================
    event_horizon = torch.sqrt(bh_mass) * 0.25 
    
    # 【設計書 10.2】 影響円錐 (Cone of Influence) の判定
    # 地平面の3倍以内の距離を「カオス領域」とする
    in_cone = dist_bh < (event_horizon * 3.0)
    in_cone_global_idx = alive_idx[in_cone]
    
    # 【設計書 5.1】 影響円錐内の星は間引き計算をやめ、毎フレーム更新に強制昇格(Time Dilation解除)
    time_dilation[in_cone_global_idx] = 1
    
    # 【設計書 8.1】 VIFモデル (Fatigue蓄積)
    # 重力強度に比例してFatigue（破綻値）が蓄積
    fatigue[alive_idx] += force_bh_mag * 0.5
    
    # 【設計書 4.2】 動的ビット解像度プロモーション判定
    speed_sq = (vel[alive_idx]**2).sum(dim=1)
    promoted_mask = in_cone & (speed_sq > 5.0)
    
    # 一旦フラグを落としてから、条件を満たす星のみ立て直す
    state_buffer[alive_idx] &= ~FLAG_PROMOTE
    state_buffer[alive_idx[promoted_mask]] |= FLAG_PROMOTE
    
    # 5. 【設計書 4.5】 密度限界と確率雲への強制的相転移
    # 地平面に接触した、またはFatigueが限界(1.0)を超えて破綻した星を吸収
    sucked = (dist_bh < event_horizon) | (fatigue[alive_idx] > 1.0)
    
    if sucked.any():
        sucked_count = sucked.sum()
        bh_mass += sucked_count * 0.5
        
        sucked_global_idx = alive_idx[sucked]
        # ACTIVEフラグを落とし、RUIN(破綻・地形化)フラグを立てる
        state_buffer[sucked_global_idx] &= ~FLAG_ACTIVE
        state_buffer[sucked_global_idx] |= FLAG_RUIN
        
        # 描画対象外・演算対象外の空間へ退避
        pos[sucked_global_idx] = 9999.0

# ==========================================
# 🎨 描画アダプタ (View Layer) - スタイリッシュUI
# ==========================================
fig, ax = plt.subplots(figsize=(8, 8), facecolor='black')
fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
ax.set_facecolor('black')
ax.set_xlim(-100, 100)
ax.set_ylim(-100, 100)
ax.axis('off')

# GPU->CPUのゼロコピー(numpy化)連携
pos_cpu = pos.cpu().numpy()
scatter = ax.scatter(pos_cpu[:, 0], pos_cpu[:, 1], s=0.15, c='#00FFFF', alpha=0.7, edgecolors='none')

# ブラックホールのスタイリッシュな階層的透過グラフィック
bh_disk = plt.Circle((0, 0), radius=2.0, fill=False, edgecolor='#FF00FF', linestyle=':', alpha=0.4, zorder=9, linewidth=1.5)
bh_horizon = plt.Circle((0, 0), radius=1.0, color='crimson', alpha=0.25, zorder=10)
bh_core = plt.Circle((0, 0), radius=0.5, color='black', zorder=11)

ax.add_patch(bh_disk)
ax.add_patch(bh_horizon)
ax.add_patch(bh_core)

title_text = ax.text(0.05, 0.95, '', transform=ax.transAxes, color='white', fontsize=12, va='top', family='monospace')

def animate(frame):
    for _ in range(3):
        update_universe()
        
    scatter.set_offsets(pos.cpu().numpy())
    
    # 観測者効果：プロモート状態(影響円錐内のカオス)の星をネオンピンクでハイライト
    is_promoted = (state_buffer & FLAG_PROMOTE) > 0
    colors = np.where(is_promoted.cpu().numpy(), '#FF007F', '#00FFFF')
    scatter.set_color(colors)
    
    current_mass = bh_mass.item()
    base_r = np.sqrt(current_mass) * 0.25
    
    # 特異点、地平面、降着円盤のスケールを動的に連動
    bh_core.set_radius(base_r * 0.6)
    bh_horizon.set_radius(base_r)
    bh_disk.set_radius(base_r * 2.5)
    
    alive_count = ((state_buffer & FLAG_ACTIVE) > 0).sum().item()
    title_text.set_text(f"Frame: {frame_count}\nAlive Stars: {alive_count:,}\nBlackHole Mass: {current_mass:.1f}")
    
    return scatter, bh_disk, bh_horizon, bh_core, title_text

# アニメーション生成・実行
ani = animation.FuncAnimation(fig, animate, frames=200, interval=30, blit=True)
plt.show()