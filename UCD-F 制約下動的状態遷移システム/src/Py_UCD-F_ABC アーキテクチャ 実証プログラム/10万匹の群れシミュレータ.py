import torch
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np

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
    # Determine which entities need computation
    active_mask = (state_flags == FLAG_ACTIVE) | (state_flags == FLAG_PROB_CLOUD)
    
    # 1. Local Time Dilation (局所時間拡張)
    # Entities with low intensity are calculated less frequently to save resources
    skip_calc = (intensity < 0.5) & (frame % 2 == 0) & active_mask
    do_calc = active_mask & ~skip_calc
    
    # Pre-calculate distances for Cone of Influence
    diff = predator_pos - pos
    dist = torch.norm(diff, dim=1, keepdim=True)
    dist_clamped = torch.clamp(dist, min=1.0)
    
    # 2. Parallel Inference (Batch Matrix Multiplication)
    dist_norm_dir = diff / dist_clamped
    dist_val = dist_clamped / WIDTH
    bias = torch.ones((NUM_ENTITIES, 1), device=device)
    
    ai_input = torch.cat([dist_norm_dir, dist_val, fatigue.unsqueeze(1), bias], dim=1)
    ai_output = torch.bmm(ai_input.unsqueeze(1), brain_weights).squeeze(1)
    
    # 3. VIF Dynamics Integration
    is_near = (dist.squeeze() < 200.0)
    new_intensity = torch.where(is_near, intensity + 0.1, intensity - 0.05)
    new_intensity = torch.clamp(new_intensity, 0.0, 5.0)
    intensity = torch.where(do_calc, new_intensity, intensity)
    
    accel = ai_output * (intensity.unsqueeze(1) + 0.5)
    new_vel = vel * 0.9 + accel * 0.1
    speed = torch.norm(new_vel, dim=1, keepdim=True)
    
    max_speed = BASE_SPEED * (1.0 - fatigue.unsqueeze(1))
    new_vel = (new_vel / torch.clamp(speed, min=0.1)) * max_speed
    vel = torch.where(do_calc.unsqueeze(1), new_vel, vel)
    
    new_fatigue = torch.where(speed.squeeze() > 2.0, fatigue + 0.005, fatigue - 0.001)
    new_fatigue = torch.clamp(new_fatigue, 0.0, 1.0)
    fatigue = torch.where(do_calc, new_fatigue, fatigue)
    
    new_pos = pos + vel
    new_pos[:, 0] = torch.remainder(new_pos[:, 0], WIDTH)
    new_pos[:, 1] = torch.remainder(new_pos[:, 1], HEIGHT)
    pos = torch.where(do_calc.unsqueeze(1), new_pos, pos)
    
    # 4. Phase Transition (確率雲への強制的相転移)
    # Safe and calm entities transition to PROB_CLOUD to suspend physics
    prob_cloud_cond = (dist.squeeze() > 600.0) & (intensity < 0.1) & active_mask
    state_flags = torch.where(prob_cloud_cond, torch.tensor(FLAG_PROB_CLOUD, dtype=torch.uint8, device=device), state_flags)
    wake_up_cond = (dist.squeeze() <= 600.0) & (state_flags == FLAG_PROB_CLOUD)
    state_flags = torch.where(wake_up_cond, torch.tensor(FLAG_ACTIVE, dtype=torch.uint8, device=device), state_flags)
    
    # 5. Zero-Lock Terrainization (死骸の地形化)
    # Entities that reach max fatigue become obstacles (Zero-Lock) and stop moving entirely
    zero_lock_cond = (fatigue >= 0.99) & active_mask
    state_flags = torch.where(zero_lock_cond, torch.tensor(FLAG_ZERO_LOCK, dtype=torch.uint8, device=device), state_flags)
    vel = torch.where(zero_lock_cond.unsqueeze(1), torch.zeros_like(vel), vel)
    
    # 6. Elimination Logic
    captured = (dist.squeeze() < 30.0) & (state_flags != FLAG_DEAD)
    num_captured = torch.sum(captured).item()
    
    if num_captured > 0:
        state_flags = torch.where(captured, torch.tensor(FLAG_DEAD, dtype=torch.uint8, device=device), state_flags)
        vel = torch.where(captured.unsqueeze(1), torch.zeros_like(vel), vel)
    
    # Update Fitness for survivors and terrainized entities
    surviving_mask = (state_flags != FLAG_DEAD)
    fitness = torch.where(surviving_mask, fitness + 1.0, fitness)

    return num_captured, state_flags

def online_learning_event():
    """Continuous Online Learning: Learn from eliminated entities without resetting"""
    global brain_weights, pos, vel, intensity, fatigue, state_flags, fitness, learning_cycles
    
    dead_mask = (state_flags == FLAG_DEAD)
    num_dead = dead_mask.sum().item()
    
    # Only learn if there is a sufficient sample of failures (eliminated entities)
    if num_dead > 0:
        alive_mask = (state_flags == FLAG_ACTIVE) | (state_flags == FLAG_PROB_CLOUD)
        
        if alive_mask.sum().item() > 0:
            alive_fitness = fitness.clone()
            alive_fitness[~alive_mask] = -1.0 # Ignore dead entities for elite selection
            
            # Select elites from survivors
            num_elites = max(1, int(alive_mask.sum().item() * 0.1))
            _, elite_indices = torch.topk(alive_fitness, num_elites)
            elite_brains = brain_weights[elite_indices]
            
            # Replace eliminated brains with mutated elite brains
            # (Learning from failures: "Those who died were wrong, adopt strategies of those who survived")
            parent_indices = torch.randint(0, num_elites, (num_dead,), device=device)
            new_brains = elite_brains[parent_indices]
            
            mutation = (torch.rand((num_dead, 5, 2), device=device) - 0.5) * 0.4
            new_brains += mutation
            brain_weights[dead_mask] = new_brains
            
            # Respawn eliminated entities as new learners
            pos[dead_mask] = torch.rand((num_dead, 2), device=device) * torch.tensor([WIDTH, HEIGHT], device=device)
            vel[dead_mask] = 0.0
            intensity[dead_mask] = 0.0
            fatigue[dead_mask] = 0.0
            fitness[dead_mask] = 0.0
            state_flags[dead_mask] = FLAG_ACTIVE
            
        # Micro-mutation for survivors to encourage continuous adaptation
        alive_idx = torch.nonzero(alive_mask).squeeze()
        if alive_idx.numel() > 0:
            micro_mutation = (torch.rand((alive_idx.numel(), 5, 2), device=device) - 0.5) * 0.05
            brain_weights[alive_idx] += micro_mutation

    learning_cycles += 1
    print(f"🧬 [ONLINE LEARNING] Cycle {learning_cycles}: Analyzed {num_dead} eliminations. AI strategies updated.")

# =====================================================================
# View Layer
# =====================================================================
fig, ax = plt.subplots(figsize=(8, 8))
fig.canvas.manager.set_window_title('🧠 100k AI Evolution Simulator 🧠')
ax.set_facecolor('#0a0a0a')

# Scatter for entities
scatter = ax.scatter([], [], s=2, c=[], cmap='winter', vmin=0, vmax=5, alpha=0.6)
ax.set_xlim(0, WIDTH)
ax.set_ylim(0, HEIGHT)
ax.axis('off')

# Monster Emoji representation
predator_text = ax.text(WIDTH/2, HEIGHT/2, '🦖', fontsize=30, ha='center', va='center')

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
    
    # Predator movement (Continuous external entropy)
    angle = frame_count * 0.04
    predator_pos[0] = WIDTH / 2 + torch.cos(torch.tensor(angle, device=device)) * 350
    predator_pos[1] = HEIGHT / 2 + torch.sin(torch.tensor(angle, device=device)) * 200
    
    # Physics & AI updates
    deaths, current_state_flags = update_ai_dynamics(
        pos, vel, intensity, fatigue, state_flags, fitness, brain_weights, predator_pos, frame_count
    )
    total_captured += deaths
    
    # Trigger Online Learning every 10 seconds (LEARNING_INTERVAL)
    if frame_count % LEARNING_INTERVAL == 0:
        online_learning_event()
    
    # --- Visual Update (Schrödinger's Culling equivalent) ---
    # Draw ACTIVE and ZERO_LOCK entities, but skip PROB_CLOUD (invisible/compressed)
    draw_mask = (current_state_flags == FLAG_ACTIVE) | (current_state_flags == FLAG_ZERO_LOCK)
    draw_idx = torch.nonzero(draw_mask).squeeze()
    
    if draw_idx.numel() > 0:
        step = max(1, draw_idx.numel() // RENDER_LIMIT)
        render_idx = draw_idx[::step]
        
        pos_cpu = pos[render_idx].cpu().numpy()
        intensity_cpu = intensity[render_idx].cpu().numpy()
        
        scatter.set_offsets(pos_cpu)
        scatter.set_array(intensity_cpu)
    else:
        scatter.set_offsets(np.empty((0, 2)))
        
    predator_text.set_position((predator_pos[0].cpu().item(), predator_pos[1].cpu().item()))
    
    # Update UI text
    if ui_visible:
        survivors = (current_state_flags != FLAG_DEAD).sum().item()
        zero_locked = (current_state_flags == FLAG_ZERO_LOCK).sum().item()
        clouded = (current_state_flags == FLAG_PROB_CLOUD).sum().item()
        
        frames_to_learn = LEARNING_INTERVAL - (frame_count % LEARNING_INTERVAL)
        
        ui_string = (
            f">> AI SURVIVAL MONITOR <<\n"
            f"LEARN CYCLES : {learning_cycles}\n"
            f"SURVIVORS    : {survivors:,}\n"
            f"  - ACTIVE   : {survivors - zero_locked - clouded:,}\n"
            f"  - TERRAIN  : {zero_locked:,} (Zero-Lock)\n"
            f"  - CLOUDED  : {clouded:,} (Phase Transition)\n"
            f"CUM. DEATHS  : {total_captured:,}\n"
            f"NEXT LEARN IN: {frames_to_learn} frames\n"
            f"--------------------------\n"
            f"PRESS [H] TO TOGGLE UI"
        )
        info_text.set_text(ui_string)
    
    return scatter, predator_text, info_text

ani = animation.FuncAnimation(fig, animate, frames=2000, interval=25, blit=True)

plt.tight_layout()
plt.show()