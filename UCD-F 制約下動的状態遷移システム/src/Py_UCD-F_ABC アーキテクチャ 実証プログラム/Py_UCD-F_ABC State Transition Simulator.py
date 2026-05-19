import numpy as np
import time

class Fixed16:
    """
    16.16 Fixed-Point Arithmetic Class for Deterministic Computations.
    Simulates fractional numbers using 32-bit integers to avoid float discrepancy.
    """
    SCALE = 65536  # 2^16
    MASK = 0xFFFFFFFF

    @staticmethod
    def from_float(f: float) -> np.int32:
        return np.int32(np.clip(np.round(f * Fixed16.SCALE), -2147483648, 2147483647))

    @staticmethod
    def to_float(x: np.int32) -> float:
        return float(x) / Fixed16.SCALE

    @staticmethod
    def mul(x: np.int32, y: np.int32) -> np.int32:
        # Cast to 64-bit integer to prevent overflow during multiplication
        val = (np.int64(x) * np.int64(y)) >> 16
        return np.int32(np.clip(val, -2147483648, 2147483647))

    @staticmethod
    def div(x: np.int32, y: np.int32) -> np.int32:
        if y == 0:
            return np.int32(2147483647)  # Infinity representation
        val = (np.int64(x) << 16) // np.int64(y)
        return np.int32(np.clip(val, -2147483648, 2147483647))


class PyUCDFSynchronizer:
    """
    Universal Constrained Dynamics Framework (UCD-F) 
    Strict implementation of Py_UCD-F_ABC state transition under strict constraints.
    Adheres to "Zero-Allocation" (pre-allocated static buffers) to avoid malloc/free.
    """

    def __init__(self, max_entities: int = 1000):
        self.max_entities = max_entities

        # --- Bit-packed Structure of Arrays (SoA) base buffers (Pre-allocated) ---
        self.state_abc_32 = np.zeros(self.max_entities, dtype=np.uint32)
        
        # Extended buffers for Dynamic Bit-Resolution Promotion (64-bit)
        self.state_abc_64 = np.zeros(self.max_entities, dtype=np.uint64)
        self.is_promoted = np.zeros(self.max_entities, dtype=bool)

        # Fixed-point physics buffers (SoA format - 16.16)
        self.pos_x = np.zeros(self.max_entities, dtype=np.int32)
        self.pos_y = np.zeros(self.max_entities, dtype=np.int32)
        self.vel_x = np.zeros(self.max_entities, dtype=np.int32)
        self.vel_y = np.zeros(self.max_entities, dtype=np.int32)

        # Time dilation control accumulation buffers
        self.local_time_accumulator = np.zeros(self.max_entities, dtype=np.int32)
        self.last_update_tick = np.zeros(self.max_entities, dtype=np.uint64)

        # Spatial grid partition management
        self.grid_sector = np.zeros(self.max_entities, dtype=np.int32)

        # Macro probability clouds for spatial overflow resolution (Phase Transition)
        self.probability_clouds = {}  # key: sector_id, value: {density: int, thermal_energy: int}

        # Main system clock
        self.global_tick = 0


    def pack_32bit_state(self, v_a: int, v_b: int, v_c: int, d_a: int, d_b: int, d_c: int, state: int, ruin: int) -> np.uint32:
        """
        Packs ABC dynamic indicators and state flags into a single 32-bit unsigned integer.
        Bit Layout:
        [0-1] vA (2bit), [2-3] vB (2bit), [4-5] vC (2bit)
        [6-11] dA (6bit), [12-17] dB (6bit), [18-23] dC (6bit) (Signed with offset 32)
        [24-26] State (3bit) (0: Inactive, 1: Active, 2: Culled, 3: Zero-Lock Terrain)
        [27-29] RuinScore (3bit)
        [30-31] Reserve (2bit)
        """
        v_a_clamped = np.uint32(v_a & 0x3)
        v_b_clamped = np.uint32(v_b & 0x3)
        v_c_clamped = np.uint32(v_c & 0x3)

        d_a_clamped = np.uint32((d_a + 32) & 0x3F)
        d_b_clamped = np.uint32((d_b + 32) & 0x3F)
        d_c_clamped = np.uint32((d_c + 32) & 0x3F)

        state_clamped = np.uint32(state & 0x7)
        ruin_clamped = np.uint32(ruin & 0x7)

        packed = (v_a_clamped) | \
                 (v_b_clamped << 2) | \
                 (v_c_clamped << 4) | \
                 (d_a_clamped << 6) | \
                 (d_b_clamped << 12) | \
                 (d_c_clamped << 18) | \
                 (state_clamped << 24) | \
                 (ruin_clamped << 27)
        return packed

    def unpack_32bit_state(self, val: np.uint32) -> dict:
        """Unpacks the packed 32-bit state value into its component metrics."""
        return {
            "v_a": int(val & 0x3),
            "v_b": int((val >> 2) & 0x3),
            "v_c": int((val >> 4) & 0x3),
            "d_a": int(((val >> 6) & 0x3F)) - 32,
            "d_b": int(((val >> 12) & 0x3F)) - 32,
            "d_c": int(((val >> 18) & 0x3F)) - 32,
            "state": int((val >> 24) & 0x7),
            "ruin_score": int((val >> 27) & 0x7)
        }


    def promote_to_64bit(self, idx: int):
        """Promotes state to high-resolution 64-bit when limits are exceeded or in focal chaos zones."""
        if self.is_promoted[idx]:
            return
        
        st = self.unpack_32bit_state(self.state_abc_32[idx])
        
        # Scaling values to 64-bit pack structure
        v_a = np.uint64(st["v_a"] * 8)
        v_b = np.uint64(st["v_b"] * 8)
        v_c = np.uint64(st["v_c"] * 8)
        d_a = np.uint64(st["d_a"] + 32768)
        d_b = np.uint64(st["d_b"] + 32768)
        d_c = np.uint64(st["d_c"] + 32768)
        state_f = np.uint64(st["state"])
        ruin = np.uint64(st["ruin_score"])

        packed_64 = v_a | (v_b << 8) | (v_c << 16) | (d_a << 24) | (d_b << 40) | (state_f << 56) | (ruin << 60)
        self.state_abc_64[idx] = packed_64
        self.is_promoted[idx] = True

    def demote_to_32bit(self, idx: int):
        """Demotes state back to 32-bit when stability returns or entity goes out of focus."""
        if not self.is_promoted[idx]:
            return
        
        val = self.state_abc_64[idx]
        v_a = int((val & 0xFF) // 8)
        v_b = int(((val >> 8) & 0xFF) // 8)
        v_c = int(((val >> 16) & 0xFF) // 8)
        d_a = int((val >> 24) & 0xFFFF) - 32768
        d_b = int((val >> 40) & 0xFFFF) - 32768
        
        # Safeguard clamps
        d_a = max(-32, min(31, d_a))
        d_b = max(-32, min(31, d_b))
        state_f = int((val >> 56) & 0xF)
        ruin = int((val >> 60) & 0xF)

        self.state_abc_32[idx] = self.pack_32bit_state(v_a, v_b, 0, d_a, d_b, 0, state_f, ruin)
        self.is_promoted[idx] = False


    def apply_schrodingers_culling(self, idx: int, observer_pos_x: np.int32, observer_pos_y: np.int32):
        """
        Applies Lod/Culling based on observer's field of view (Schrödinger's Culling).
        Deactivates updates for entities that fall outside the defined observation radius.
        """
        dx = self.pos_x[idx] - observer_pos_x
        dy = self.pos_y[idx] - observer_pos_y
        dist_sq = Fixed16.mul(dx, dx) + Fixed16.mul(dy, dy)

        # Distance threshold roughly equivalent to 100.0 units
        threshold = Fixed16.from_float(100.0)
        st = self.unpack_32bit_state(self.state_abc_32[idx])

        if dist_sq > threshold and st["state"] == 1:
            # Out of bounds -> Collapse to probability wave
            st["state"] = 2
            self.state_abc_32[idx] = self.pack_32bit_state(
                st["v_a"], st["v_b"], st["v_c"], st["d_a"], st["d_b"], st["d_c"], st["state"], st["ruin_score"]
            )
        elif dist_sq <= threshold and st["state"] == 2:
            # Within bounds -> Re-materialize entity
            st["state"] = 1
            self.state_abc_32[idx] = self.pack_32bit_state(
                st["v_a"], st["v_b"], st["v_c"], st["d_a"], st["d_b"], st["d_c"], st["state"], st["ruin_score"]
            )


    def handle_spatial_density_limit(self, sector_id: int, indices_in_sector: list, max_density: int = 5):
        """
        Spatial Density Resolution using forced Phase Transition to Probability Clouds.
        Prevents static overflow by collapsing weak entities (lowest VIF metric) when density limit is reached.
        """
        if len(indices_in_sector) <= max_density:
            return

        # Sort active candidates by total VIF strength
        candidates = []
        for idx in indices_in_sector:
            st = self.unpack_32bit_state(self.state_abc_32[idx])
            if st["state"] == 1:
                strength = st["v_a"] + st["v_b"] + st["v_c"]
                candidates.append((strength, idx))

        candidates.sort(key=lambda x: x[0])

        excess_count = len(indices_in_sector) - max_density
        if sector_id not in self.probability_clouds:
            self.probability_clouds[sector_id] = {"density": 0, "thermal_energy": 0}

        for i in range(min(excess_count, len(candidates))):
            strength, idx = candidates[i]
            
            # Repossess physical entity state
            st = self.unpack_32bit_state(self.state_abc_32[idx])
            st["state"] = 0  # Mark as inactive (reclaim slot)
            self.state_abc_32[idx] = self.pack_32bit_state(0, 0, 0, 0, 0, 0, 0, 0)
            
            # Accumulate entropy into macro probability cloud
            self.probability_clouds[sector_id]["density"] += 1
            self.probability_clouds[sector_id]["thermal_energy"] += strength
            
            # Clear physical values
            self.pos_x[idx] = 0
            self.pos_y[idx] = 0
            self.vel_x[idx] = 0
            self.vel_y[idx] = 0


    def spawn_entity(self, px: float, py: float, vx: float, vy: float, v_a: int, v_b: int) -> int:
        """Spawns an entity using static pool reclamation (zero allocation, no malloc calls)."""
        for i in range(self.max_entities):
            st = self.unpack_32bit_state(self.state_abc_32[i])
            if st["state"] == 0:  # Reclaim unused slot
                self.pos_x[i] = Fixed16.from_float(px)
                self.pos_y[i] = Fixed16.from_float(py)
                self.vel_x[i] = Fixed16.from_float(vx)
                self.vel_y[i] = Fixed16.from_float(vy)
                
                # Default packed configuration: State = 1 (Active), Ruin = 0
                self.state_abc_32[i] = self.pack_32bit_state(v_a, v_b, 0, 0, 0, 0, 1, 0)
                self.is_promoted[i] = False
                self.local_time_accumulator[i] = 0
                return i
        return -1  # Pool depleted


    def step(self, dt: float, observer_pos: tuple):
        """Runs one computational loop (Deterministic lockstep execution)."""
        self.global_tick += 1
        dt_fixed = Fixed16.from_float(dt)
        obs_x_fixed = Fixed16.from_float(observer_pos[0])
        obs_y_fixed = Fixed16.from_float(observer_pos[1])

        sector_map = {}

        for i in range(self.max_entities):
            st = self.unpack_32bit_state(self.state_abc_32[i])
            if st["state"] == 0:
                continue

            # 1. Apply observer culling
            self.apply_schrodingers_culling(i, obs_x_fixed, obs_y_fixed)
            st = self.unpack_32bit_state(self.state_abc_32[i])

            if st["state"] == 2:
                # Bypass execution for culled entities (Schrödinger's Optimization)
                continue

            if st["state"] == 3:
                # Zero-Lock Terrain optimization: static environment factor, bypass update
                continue

            # 2. Local Time Dilation calculation
            chaos_index = abs(st["d_a"]) + abs(st["d_b"])
            if chaos_index > 20:
                # High chaos triggers high-resolution 64-bit promotion
                if not self.is_promoted[i]:
                    self.promote_to_64bit(i)
                time_dilation_factor = Fixed16.from_float(1.0)
            else:
                if self.is_promoted[i]:
                    self.demote_to_32bit(i)
                # Normal conditions delay processing frequency to save computational cost
                time_dilation_factor = Fixed16.from_float(0.5)

            self.local_time_accumulator[i] += Fixed16.mul(dt_fixed, time_dilation_factor)
            
            # Process only when threshold step time has passed
            if self.local_time_accumulator[i] < Fixed16.from_float(0.01):
                continue
            
            step_dt = self.local_time_accumulator[i]
            self.local_time_accumulator[i] = 0

            # 3. Position integration
            self.pos_x[i] += Fixed16.mul(self.vel_x[i], step_dt)
            self.pos_y[i] += Fixed16.mul(self.vel_y[i], step_dt)

            # 4. ABC/VIF Dynamics propagation
            pot_v_a = Fixed16.from_float(st["v_a"] * 0.1)
            pot_v_b = Fixed16.from_float(st["v_b"] * 0.1)
            self.vel_x[i] += Fixed16.from_float(st["d_a"] * 0.05) - Fixed16.mul(self.vel_x[i], pot_v_a)
            self.vel_y[i] += Fixed16.from_float(st["d_b"] * 0.05) - Fixed16.mul(self.vel_y[i], pot_v_b)

            # Accumulate entropy into fatigue metrics
            new_d_a = st["d_a"] + int(np.sign(self.vel_x[i]))
            new_d_b = st["d_b"] + int(np.sign(self.vel_y[i]))
            
            new_d_a = max(-32, min(31, new_d_a))
            new_d_b = max(-32, min(31, new_d_b))

            new_ruin = st["ruin_score"]
            if abs(new_d_a) > 25 or abs(new_d_b) > 25:
                new_ruin += 1

            # 5. Lock degradation (Zero-Lock Transition)
            if new_ruin >= 7:
                st["state"] = 3  # Grounded to static terrain element
                self.vel_x[i] = 0
                self.vel_y[i] = 0
            
            self.state_abc_32[i] = self.pack_32bit_state(
                st["v_a"], st["v_b"], st["v_c"], new_d_a, new_d_b, st["d_c"], st["state"], new_ruin
            )

            # Hash sector calculation
            sec_x = int(Fixed16.to_float(self.pos_x[i]) / 10.0)
            sec_y = int(Fixed16.to_float(self.pos_y[i]) / 10.0)
            sector_key = (sec_x * 73856093) ^ (sec_y * 19349663)
            self.grid_sector[i] = sector_key

            if sector_key not in sector_map:
                sector_map[sector_key] = []
            sector_map[sector_key].append(i)

        # 6. Apply spatial limit constraints (Phase Transition)
        for sec_id, idx_list in sector_map.items():
            self.handle_spatial_density_limit(sec_id, idx_list, max_density=3)


def analyze_system_efficiency(sys: PyUCDFSynchronizer):
    """Prints a clear, clean metrics overview of the active static memory layouts."""
    states = [sys.unpack_32bit_state(val) for val in sys.state_abc_32]
    
    counts = {
        "active": sum(1 for s in states if s["state"] == 1),
        "culled": sum(1 for s in states if s["state"] == 2),
        "locked": sum(1 for s in states if s["state"] == 3),
        "unused": sum(1 for s in states if s["state"] == 0)
    }

    cloud_energy = sum(c["thermal_energy"] for c in sys.probability_clouds.values())
    cloud_entities = sum(c["density"] for c in sys.probability_clouds.values())

    print(f" [Pool Allocation] Capacity: {sys.max_entities} | Active: {counts['active']} | Culled: {counts['culled']} | Terrain-locked: {counts['locked']} | Free Slots: {counts['unused']}")
    if cloud_entities > 0:
        print(f" [Phase Transition] Absorbed: {cloud_entities} entities into Probability Clouds (Total Heat: {cloud_energy})")


if __name__ == "__main__":
    print(">>> Initializing Py_UCD-F_ABC Synchronizer (Zero-Allocation Pool Model) <<<")

    # Launching highly-constrained environment (10 static slots)
    system = PyUCDFSynchronizer(max_entities=10)

    # Spawning initial entities
    system.spawn_entity(px=1.0, py=2.0, vx=0.5, vy=-0.2, v_a=2, v_b=1)
    system.spawn_entity(px=-3.0, py=5.0, vx=1.2, vy=0.1, v_a=1, v_b=3)
    system.spawn_entity(px=10.0, py=10.0, vx=-0.1, vy=-0.5, v_a=3, v_b=2)
    
    # Overload specific location to force Phase Transition
    for _ in range(5):
        system.spawn_entity(px=15.0, py=15.0, vx=0.0, vy=0.0, v_a=1, v_b=1)

    observer = (0.0, 0.0)

    print("\n--- Executing Timestep Cycles ---")
    for tick in range(1, 4):
        print(f"\n[Cycle #{tick}] Observer moving to ({tick*2.0:.1f}, {tick*2.0:.1f})")
        observer = (float(tick * 2.0), float(tick * 2.0))
        system.step(dt=0.1, observer_pos=observer)
        
        analyze_system_efficiency(system)
        
        # Display individual slot metrics concisely
        for idx in range(system.max_entities):
            st = system.unpack_32bit_state(system.state_abc_32[idx])
            px = Fixed16.to_float(system.pos_x[idx])
            py = Fixed16.to_float(system.pos_y[idx])
            print(f"  Slot [{idx}] State: {st['state']} (Ruin: {st['ruin_score']}) | Pos: ({px:5.1f}, {py:5.1f}) | Dynamics (dA:{st['d_a']}, dB:{st['d_b']})")