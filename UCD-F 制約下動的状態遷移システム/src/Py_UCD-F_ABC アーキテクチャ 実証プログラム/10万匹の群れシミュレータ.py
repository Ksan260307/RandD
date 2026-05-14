import torch
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
from matplotlib.colors import ListedColormap

# =====================================================================
# Internal Logic: Py_UCD-F_ABC Core v1.0.0 Architecture
# (Continuous Online Learning & Full Dynamics Integration)
# =====================================================================

# --- Hyperparameters ---
NUM_ENTITIES = 100_000
RENDER_LIMIT = 5_000
WIDTH, HEIGHT = 1000.0, 1000.0
BASE_SPEED = 5.0
LEARNING_INTERVAL = 400 # 10 seconds interval for continuous learning

# --- Py_UCD-F_ABC Constants ---
FLAG_DEAD = 0        # Captured/Eliminated
FLAG_ACTIVE = 1      # Normal active entity
FLAG_ZERO_LOCK = 2   # Terrainized (Fatigue MAX, unable to move)
FLAG_PROB_CLOUD = 3  # Phase Transition (Safe distance, computation suspended)
FLAG_PROMOTED = 4    # Dynamic Bit-Resolution Promotion (Chaos zone, High-Res calculation)

def setup_environment():
    """Autonomous Environment Optimization"""
    print("🧠 100k AI Survival Continuous Learning Simulator 🧠\n")
    print("🔍 Checking Compute Units (GPU/MPS)...")
    print("💡 Press [H] to toggle UI overlay.\n")
    
    if torch.cuda.is_available():
        device = torch.device("cuda")
        print("🚀 [RESULT] NVIDIA GPU detected. Processing 100k brains in parallel.")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
        print("🍏 [RESULT] Apple Silicon detected. Utilizing Neural Engine.")
    else:
        device = torch.device("cpu")
        print("💻 [RESULT] CPU mode. Performance may be limited.")
    
    print(f"\n📊 Scale: {NUM_ENTITIES:,} independent neural networks thinking simultaneously.")
    return device

device = setup_environment()

# =====================================================================
# Memory Layout (Bit-packed SoA Structure Simulation)
# =====================================================================
pos = torch.rand((NUM_ENTITIES, 2), device=device) * torch.tensor([WIDTH, HEIGHT], device=device)
vel = torch.zeros((NUM_ENTITIES, 2), device=device)

intensity = torch.zeros(NUM_ENTITIES, device=device) # I: Panic level
fatigue = torch.zeros(NUM_ENTITIES, device=device)   # F: Fatigue level

state_flags = torch.ones(NUM_ENTITIES, dtype=torch.uint8, device=device) # Initialize all as ACTIVE
fitness = torch.zeros(NUM_ENTITIES, device=device)

# Neural Weights (Brain)
# Input(5): [NormRelativeX, NormRelativeY, NormAbsoluteDist, Fatigue, Bias]
# Output(2): [TargetDirectionX, TargetDirectionY]
brain_weights = (torch.rand((NUM_ENTITIES, 5, 2), device=device) - 0.5) * 2.0

# Stats Tracking
total_captured = 0
learning_cycles = 0
frame_count = 0
ui_visible = True
predator_pos = torch.tensor([WIDTH / 2, HEIGHT / 2], device=device)

# =====================================================================
# Core Logic (Tensor-based Parallel Inference & Evolution)
# =====================================================================
def update_ai_dynamics(pos, vel, intensity, fatigue, state_flags, fitness, brain_weights, predator_pos, frame):
    # Pre-calculate distances for Cone of Influence
    diff = predator_pos - pos
    dist = torch.norm(diff, dim=1, keepdim=True)
    dist_clamped = torch.clamp(dist, min=1.0)
    
    # 影響円錐: 怪獣の周辺（半径250以内）のみを計算・移動の対象とする
    is_near_predator = (dist.squeeze() < 250.0)
    
    # Determine which entities need computation
    active_mask = (state_flags == FLAG_ACTIVE) | (state_flags == FLAG_PROB_CLOUD) | (state_flags == FLAG_PROMOTED)
    
    # 1. Local Time Dilation (局所時間拡張)
    skip_calc = (intensity < 0.5) & (frame % 2 == 0) & active_mask
    do_calc = active_mask & ~skip_calc & is_near_predator
    
    # 2. Parallel Inference (Batch Matrix Multiplication)
    dist_norm_dir = diff / dist_clamped
    dist_val = dist_clamped / WIDTH
    bias = torch.ones((NUM_ENTITIES, 1), device=device)
    
    ai_input = torch.cat([dist_norm_dir, dist_val, fatigue.unsqueeze(1), bias], dim=1)
    ai_output = torch.bmm(ai_input.unsqueeze(1), brain_weights).squeeze(1)
    
    # 3. VIF Dynamics Integration & Dynamic Resolution Promotion
    new_intensity = torch.where(is_near_predator, intensity + 0.1, intensity - 0.05)
    new_intensity = torch.clamp(new_intensity, 0.0, 5.0)
    intensity = torch.where(do_calc, new_intensity, intensity)
    
    # Dynamic Bit-Resolution Promotion: Promoted entities have higher reaction gain
    promotion_multiplier = torch.where(state_flags.unsqueeze(1) == FLAG_PROMOTED, 1.5, 1.0)
    accel = ai_output * (intensity.unsqueeze(1) + 0.5) * promotion_multiplier
    
    new_vel = vel * 0.9 + accel * 0.1
    speed = torch.norm(new_vel, dim=1, keepdim=True)
    
    max_speed = BASE_SPEED * (1.0 - fatigue.unsqueeze(1))
    new_vel = (new_vel / torch.clamp(speed, min=0.1)) * max_speed
    vel = torch.where(do_calc.unsqueeze(1), new_vel, vel)
    
    # 遠くの個体は計算対象外となり、慣性で滑らかに停止する
    vel = torch.where(is_near_predator.unsqueeze(1), vel, vel * 0.5)
    
    new_fatigue = torch.where(speed.squeeze() > 2.0, fatigue + 0.005, fatigue - 0.001)
    new_fatigue = torch.clamp(new_fatigue, 0.0, 1.0)
    fatigue = torch.where(do_calc, new_fatigue, fatigue)
    
    # 位置更新は全員に行う（遠くの個体は vel が 0 になるためその場で静止する）
    new_pos = pos + vel
    new_pos[:, 0] = torch.remainder(new_pos[:, 0], WIDTH)
    new_pos[:, 1] = torch.remainder(new_pos[:, 1], HEIGHT)
    pos = new_pos
    
    # 4. State Transition Evaluation (状態の再評価)
    new_state_flags = state_flags.clone()
    is_alive_and_mobile = (state_flags == FLAG_ACTIVE) | (state_flags == FLAG_PROB_CLOUD) | (state_flags == FLAG_PROMOTED)
    
    # Dynamic Bit-Resolution Promotion (カオス領域での高解像度化)
    cond_promoted = (dist.squeeze() < 150.0) & is_alive_and_mobile
    # Phase Transition (確率雲への強制的相転移)
    cond_cloud = (dist.squeeze() >= 250.0) & (intensity < 0.1) & is_alive_and_mobile
    cond_active = ~(cond_promoted | cond_cloud) & is_alive_and_mobile
    
    new_state_flags = torch.where(cond_promoted, torch.tensor(FLAG_PROMOTED, dtype=torch.uint8, device=device), new_state_flags)
    new_state_flags = torch.where(cond_cloud, torch.tensor(FLAG_PROB_CLOUD, dtype=torch.uint8, device=device), new_state_flags)
    new_state_flags = torch.where(cond_active, torch.tensor(FLAG_ACTIVE, dtype=torch.uint8, device=device), new_state_flags)
    
    # 5. Zero-Lock Terrainization (死骸の地形化)
    cond_zero_lock = (fatigue >= 0.99) & is_alive_and_mobile
    new_state_flags = torch.where(cond_zero_lock, torch.tensor(FLAG_ZERO_LOCK, dtype=torch.uint8, device=device), new_state_flags)
    vel = torch.where(cond_zero_lock.unsqueeze(1), torch.zeros_like(vel), vel)
    
    # 6. Elimination Logic (脱落)
    captured = (dist.squeeze() < 30.0) & (new_state_flags != FLAG_DEAD)
    num_captured = torch.sum(captured).item()
    
    if num_captured > 0:
        new_state_flags = torch.where(captured, torch.tensor(FLAG_DEAD, dtype=torch.uint8, device=device), new_state_flags)
        vel = torch.where(captured.unsqueeze(1), torch.zeros_like(vel), vel)
    
    # Update Fitness for survivors and terrainized entities
    surviving_mask = (new_state_flags != FLAG_DEAD)
    fitness = torch.where(surviving_mask, fitness + 1.0, fitness)

    return num_captured, new_state_flags

def online_learning_event():
    """Continuous Online Learning & Data Reordering"""
    global brain_weights, pos, vel, intensity, fatigue, state_flags, fitness, learning_cycles
    
    alive_mask = (state_flags != FLAG_DEAD)
    num_alive = alive_mask.sum().item()
    
    if num_alive > 0:
        alive_indices = torch.nonzero(alive_mask).squeeze()
        
        # Avoid shape errors if there's only 1 survivor
        if alive_indices.dim() == 0:
            alive_indices = alive_indices.unsqueeze(0)
            
        alive_fitness = fitness[alive_indices]
        
        # Select elites from survivors
        num_elites = max(1, int(num_alive * 0.1))
        _, elite_local_indices = torch.topk(alive_fitness, num_elites)
        elite_global_indices = alive_indices[elite_local_indices]
        elite_brains = brain_weights[elite_global_indices]
        
        # Share knowledge: Update all survivors' brains by blending with mutated elite brains
        parent_indices = torch.randint(0, num_elites, (num_alive,), device=device)
        selected_elite_brains = elite_brains[parent_indices]
        
        mutation = (torch.rand((num_alive, 5, 2), device=device) - 0.5) * 0.2
        updated_brains = selected_elite_brains + mutation
        
        # 30% of the new knowledge is blended into the survivors' current brains
        brain_weights[alive_indices] = brain_weights[alive_indices] * 0.7 + updated_brains * 0.3

    # Data Reordering / Stream Compaction (データ・リアライメント)
    # Move DEAD entities to the end of the arrays to maximize L1/L2 cache hits for active computation
    sort_keys = (state_flags == FLAG_DEAD).to(torch.int8)
    _, sorted_indices = torch.sort(sort_keys)
    
    pos = pos[sorted_indices]
    vel = vel[sorted_indices]
    intensity = intensity[sorted_indices]
    fatigue = fatigue[sorted_indices]
    state_flags = state_flags[sorted_indices]
    fitness = fitness[sorted_indices]
    brain_weights = brain_weights[sorted_indices]

    learning_cycles += 1
    print(f"🧬 [ONLINE LEARNING] Cycle {learning_cycles}: Remaining survivors upgraded. Cache reordered.")

# =====================================================================
# View Layer
# =====================================================================
fig, ax = plt.subplots(figsize=(8, 8))
fig.canvas.manager.set_window_title('🧠 100k AI Evolution Simulator 🧠')
ax.set_facecolor('#0a0a0a')

# カスタムカラーマップ: 0=通常色(シアン), 1=逃走色(イエロー)
custom_cmap = ListedColormap(['#00BCD4', '#FFEB3B'])
scatter = ax.scatter([], [], s=2, c=[], cmap=custom_cmap, vmin=0, vmax=1, alpha=0.6)

ax.set_xlim(0, WIDTH)
ax.set_ylim(0, HEIGHT)
ax.axis('off')

# Predator representation
predator_dot, = ax.plot([], [], 'ro', ms=15, label='Monster', markeredgecolor='white')

# Stats UI
info_text = ax.text(0.02, 0.98, "", transform=ax.transAxes, 
                     color='#00FFCC', fontsize=11, family='monospace', va='top',
                     bbox=dict(facecolor='black', alpha=0.8, edgecolor='#00FFCC', boxstyle='round,pad=0.5'))

def on_key(event):
    """Toggle UI visibility"""
    global ui_visible
    if event.key == 'h' or event.key == 'H':
        ui_visible = not ui_visible
        info_text.set_visible(ui_visible)

fig.canvas.mpl_connect('key_press_event', on_key)

def animate(frame):
    global pos, vel, intensity, fatigue, state_flags, fitness, brain_weights
    global frame_count, total_captured, predator_pos
    
    frame_count += 1
    
    # Predator movement (Speed Increased)
    t = frame_count * 0.04 # 速度アップ
    
    # 1. 画面全体を不規則に巡回するベース軌道
    base_x = WIDTH / 2 + torch.cos(torch.tensor(t * 1.3, device=device)) * (WIDTH * 0.4)
    base_y = HEIGHT / 2 + torch.sin(torch.tensor(t * 1.7, device=device)) * (HEIGHT * 0.4)
    
    # 2. 生き残っている人々の「重心」を計算
    alive_mask = (state_flags != FLAG_DEAD)
    if alive_mask.sum() > 0:
        center_of_mass = pos[alive_mask].mean(dim=0)
        target_x = base_x * 0.5 + center_of_mass[0] * 0.5
        target_y = base_y * 0.5 + center_of_mass[1] * 0.5
    else:
        target_x = base_x
        target_y = base_y
        
    # 3. 慣性をつけてスムーズにターゲットへ追従 (追従スピードアップ)
    predator_pos[0] += (target_x - predator_pos[0]) * 0.1
    predator_pos[1] += (target_y - predator_pos[1]) * 0.1
    
    # Physics & AI updates
    deaths, current_state_flags = update_ai_dynamics(
        pos, vel, intensity, fatigue, state_flags, fitness, brain_weights, predator_pos, frame_count
    )
    total_captured += deaths
    state_flags = current_state_flags
    
    # Trigger Online Learning every 10 seconds (LEARNING_INTERVAL)
    if frame_count % LEARNING_INTERVAL == 0:
        online_learning_event()
    
    # --- Visual Update ---
    # 死骸以外を描画する（遠くの静止している群衆も見えるようにする）
    draw_mask = (state_flags != FLAG_DEAD)
    draw_idx = torch.nonzero(draw_mask).squeeze()
    
    if draw_idx.numel() > 0:
        if draw_idx.dim() == 0:
            draw_idx = draw_idx.unsqueeze(0)
            
        step = max(1, draw_idx.numel() // RENDER_LIMIT)
        render_idx = draw_idx[::step]
        
        pos_cpu = pos[render_idx].cpu().numpy()
        
        # 色の判定: パニック状態(Intensity > 0.1)なら黄色(1.0)、そうでないなら通常色(0.0)
        intensity_cpu = intensity[render_idx].cpu().numpy()
        is_escaping = (intensity_cpu > 0.1).astype(float)
        
        scatter.set_offsets(pos_cpu)
        scatter.set_array(is_escaping)
    else:
        scatter.set_offsets(np.empty((0, 2)))
        
    predator_dot.set_data([predator_pos[0].cpu().item()], [predator_pos[1].cpu().item()])
    
    # Update UI text
    if ui_visible:
        survivors = (state_flags != FLAG_DEAD).sum().item()
        zero_locked = (state_flags == FLAG_ZERO_LOCK).sum().item()
        clouded = (state_flags == FLAG_PROB_CLOUD).sum().item()
        promoted = (state_flags == FLAG_PROMOTED).sum().item()
        active = survivors - zero_locked - clouded - promoted
        
        frames_to_learn = LEARNING_INTERVAL - (frame_count % LEARNING_INTERVAL)
        
        ui_string = (
            f">> AI SURVIVAL MONITOR <<\n"
            f"LEARN CYCLES : {learning_cycles}\n"
            f"SURVIVORS    : {survivors:,}\n"
            f"  - ACTIVE   : {active:,}\n"
            f"  - PROMOTED : {promoted:,} (High-Res)\n"
            f"  - TERRAIN  : {zero_locked:,} (Zero-Lock)\n"
            f"  - CLOUDED  : {clouded:,} (Phase Trans)\n"
            f"CUM. DEATHS  : {total_captured:,}\n"
            f"NEXT LEARN IN: {frames_to_learn} frames\n"
            f"--------------------------\n"
            f"PRESS [H] TO TOGGLE UI"
        )
        info_text.set_text(ui_string)
    
    return scatter, predator_dot, info_text

ani = animation.FuncAnimation(fig, animate, frames=2000, interval=25, blit=True)

plt.tight_layout()
plt.show()