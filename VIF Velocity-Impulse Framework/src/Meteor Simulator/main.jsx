import React, { useState, useEffect, useRef } from 'react';
import { Moon, Star, AlertTriangle, Coffee, Eye, EyeOff, Zap } from 'lucide-react';

/**
 * --- UCD-F: State & Dynamics Layer (SoA Implementation) ---
 * 連続したメモリ領域を用いて数千の流星を高速処理
 */
class MeteorPool {
  constructor(maxSize) {
    this.maxSize = maxSize;
    this.count = 0;
    
    // SoA (Structure of Arrays) using TypedArrays
    this.x = new Float32Array(maxSize);
    this.y = new Float32Array(maxSize);
    this.vx = new Float32Array(maxSize);
    this.vy = new Float32Array(maxSize);
    this.life = new Float32Array(maxSize); 
    this.opacity = new Float32Array(maxSize);
    this.strength = new Float32Array(maxSize);
    this.quality = new Float32Array(maxSize);
    this.isSolid = new Uint8Array(maxSize); // 衝突判定を持つかどうかのフラグ
    this.radius = new Float32Array(maxSize); // 衝突半径
    
    // 状態管理用のインデックスプール
    this.activeIndices = new Int32Array(maxSize);
    this.activeCount = 0;
    this.freeIndices = Array.from({ length: maxSize }, (_, i) => i);
  }

  spawn(x, y, v, strength, quality) {
    if (this.freeIndices.length === 0) return;

    const idx = this.freeIndices.pop();
    const angle = Math.PI / 4 + (Math.random() * 0.2 - 0.1);
    const speed = 250 + Math.random() * 150 + (v * 80);

    this.x[idx] = x;
    this.y[idx] = y;
    this.vx[idx] = -Math.cos(angle) * speed;
    this.vy[idx] = Math.sin(angle) * speed;
    this.life[idx] = 1.0;
    this.strength[idx] = strength;
    this.quality[idx] = quality;
    this.opacity[idx] = quality * 0.8 + 0.2;
    
    // 一部の流星（約20%）に衝突判定を付与
    this.isSolid[idx] = Math.random() > 0.8 ? 1 : 0;
    this.radius[idx] = (2 + strength * 0.5) * quality;

    this.activeIndices[this.activeCount++] = idx;
  }

  update(dt, width, height) {
    let nextActiveCount = 0;

    // 1. 物理移動の更新
    for (let i = 0; i < this.activeCount; i++) {
      const idx = this.activeIndices[i];
      
      this.x[idx] += this.vx[idx] * dt;
      this.y[idx] += this.vy[idx] * dt;

      // 画面外判定
      if (this.x[idx] < -300 || this.y[idx] > height + 300 || this.x[idx] > width + 300) {
        this.freeIndices.push(idx);
      } else {
        this.activeIndices[nextActiveCount++] = idx;
      }
    }
    this.activeCount = nextActiveCount;

    // 2. 衝突判定と反発（Solidフラグを持つもの同士のみ）
    // 計算負荷軽減のため、簡易的な総当たり（実用上はグリッド分割が理想だが一部のみなのでこのまま実行）
    for (let i = 0; i < this.activeCount; i++) {
      const idxA = this.activeIndices[i];
      if (this.isSolid[idxA] === 0) continue;

      for (let j = i + 1; j < this.activeCount; j++) {
        const idxB = this.activeIndices[j];
        if (this.isSolid[idxB] === 0) continue;

        const dx = this.x[idxB] - this.x[idxA];
        const dy = this.y[idxB] - this.y[idxA];
        const distSq = dx * dx + dy * dy;
        const minDist = this.radius[idxA] + this.radius[idxB] + 15; // 判定を少し広めにとる

        if (distSq < minDist * minDist) {
          // 衝突応答: ベクトルの反転・偏向
          const dist = Math.sqrt(distSq);
          const nx = dx / dist; // 法線
          const ny = dy / dist;
          
          // 相対速度
          const rvx = this.vx[idxB] - this.vx[idxA];
          const rvy = this.vy[idxB] - this.vy[idxA];
          
          // 法線方向の速度成分
          const velInNormal = rvx * nx + rvy * ny;
          
          if (velInNormal < 0) {
            // 反発係数 0.8
            const impulse = -(1.8) * velInNormal;
            const jx = (impulse / 2) * nx;
            const jy = (impulse / 2) * ny;
            
            this.vx[idxA] -= jx;
            this.vy[idxA] -= jy;
            this.vx[idxB] += jx;
            this.vy[idxB] += jy;

            // 少しだけ品質を下げる（衝突によるノイズ）
            this.quality[idxA] *= 0.95;
            this.quality[idxB] *= 0.95;
          }
        }
      }
    }
  }
}

/**
 * --- VIF Core: Logic Layer ---
 */
class VIFController {
  constructor() {
    this.v = 0;
    this.v_target = 0;
    this.strength = 5;
    this.fatigue = 0;
    this.quality = 1.0;
    this.isBreakdown = false;

    // 定数
    this.alpha = 0.05;
    this.fatigueRate = 0.005; 
    this.recoveryRate = 2.0;
    this.heatThreshold = 300;
    this.maxFatigue = 80;
    this.fatigueVelocityThreshold = 4;
  }

  update(dt) {
    if (this.isBreakdown) {
      this.v_target = 0;
      this.v += this.alpha * (this.v_target - this.v);
      this.fatigue -= this.recoveryRate * 1.5 * dt;
      this.quality = 0;
      if (this.fatigue <= 0) {
        this.fatigue = 0;
        this.isBreakdown = false;
      }
      return;
    }

    this.v += this.alpha * (this.v_target - this.v);
    
    if (this.v_target === 0 && this.v < 0.5) {
      this.fatigue -= this.recoveryRate * dt;
      if (this.fatigue < 0) this.fatigue = 0;
    } else if (this.v >= this.fatigueVelocityThreshold) {
      this.fatigue += (this.v * this.strength) * this.fatigueRate * dt;
    }

    const currentHeat = this.v * this.fatigue;
    if (currentHeat > this.heatThreshold || this.fatigue > this.maxFatigue) {
      this.isBreakdown = true;
    }

    const denominator = 1 + (0.05 * this.v) + (0.02 * this.fatigue);
    this.quality = Math.max(0, 1 / denominator);
  }
}

export default function App() {
  const canvasRef = useRef(null);
  const vifRef = useRef(new VIFController());
  const poolRef = useRef(new MeteorPool(5000)); 
  
  const [uiState, setUiState] = useState({
    velocity: 0,
    strength: 5,
    quality: 100,
    fatigueLevel: 0,
    isBreakdown: false,
    activeCount: 0
  });

  const [showUI, setShowUI] = useState(true);
  const lastTimeRef = useRef(performance.now());

  const animate = (time) => {
    const dt = Math.min((time - lastTimeRef.current) / 1000, 0.1); 
    lastTimeRef.current = time;

    const vif = vifRef.current;
    const pool = poolRef.current;
    const canvas = canvasRef.current;
    
    vif.update(dt);

    if (canvas) {
      const ctx = canvas.getContext('2d');
      const { width, height } = canvas;

      // 1. Logic Update
      pool.update(dt, width, height);

      // 2. Spawn
      if (!vif.isBreakdown && vif.v > 0) {
        const spawnCount = Math.floor(vif.v * 1.2 * Math.random());
        for(let i = 0; i < spawnCount; i++) {
          pool.spawn(
            Math.random() * width * 1.5, 
            -150, 
            vif.v, 
            vif.strength, 
            vif.quality
          );
        }
      }

      // 3. Render Layer
      const fatigueRatio = Math.min(1, vif.fatigue / vif.maxFatigue);
      const bgR = Math.floor(5 + fatigueRatio * 30);
      const bgG = Math.floor(10 - fatigueRatio * 5);
      const bgB = Math.floor(25 - fatigueRatio * 15);
      
      ctx.fillStyle = `rgba(${bgR}, ${bgG}, ${bgB}, 0.25)`; 
      ctx.fillRect(0, 0, width, height);

      for (let i = 0; i < pool.activeCount; i++) {
        const idx = pool.activeIndices[i];
        const x = pool.x[idx];
        const y = pool.y[idx];
        const q = pool.quality[idx];
        const s = pool.strength[idx];
        const solid = pool.isSolid[idx];
        
        const len = (40 + s * 10) * (0.5 + q * 0.5);
        const thickness = (1 + s * 0.4) * q;
        
        ctx.beginPath();
        ctx.moveTo(x, y);
        // 速度ベクトルに合わせて尾を引く
        const tailX = x - pool.vx[idx] * 0.05;
        const tailY = y - pool.vy[idx] * 0.05;
        ctx.lineTo(tailX, tailY);
        
        const r = Math.floor(255 * (1 - q) + 150 * q);
        const g = Math.floor(200 * q);
        const b = Math.floor(255 * q + 150 * (1 - q));
        
        ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${pool.opacity[idx]})`;
        ctx.lineWidth = thickness;
        ctx.lineCap = 'round';
        ctx.stroke();

        // 衝突判定がある流星は核（コア）を強調
        if (solid === 1) {
          ctx.beginPath();
          ctx.arc(x, y, thickness * 1.5, 0, Math.PI * 2);
          ctx.fillStyle = q > 0.5 ? 'rgba(255, 255, 255, 0.9)' : 'rgba(200, 200, 200, 0.5)';
          ctx.fill();
          // 外光
          ctx.beginPath();
          ctx.arc(x, y, thickness * 4, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(${r}, ${g}, ${b}, 0.2)`;
          ctx.fill();
        } else if (q > 0.8) {
          // 通常の高品質流星の輝き
          ctx.beginPath();
          ctx.arc(x, y, thickness * 0.8, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';
          ctx.fill();
        }
      }
    }

    if (time % 100 < 20) {
      setUiState({
        velocity: vif.v_target,
        strength: vif.strength,
        quality: Math.round(vif.quality * 100),
        fatigueLevel: Math.min(100, Math.max(
          (vif.v * vif.fatigue / vif.heatThreshold) * 100,
          (vif.fatigue / vif.maxFatigue) * 100
        )),
        isBreakdown: vif.isBreakdown,
        activeCount: pool.activeCount
      });
    }

    requestAnimationFrame(animate);
  };

  useEffect(() => {
    const handleResize = () => {
      if (canvasRef.current) {
        canvasRef.current.width = window.innerWidth;
        canvasRef.current.height = window.innerHeight;
      }
    };
    window.addEventListener('resize', handleResize);
    handleResize();
    const animId = requestAnimationFrame(animate);
    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animId);
    };
  }, []);

  return (
    <div className="relative w-full h-screen overflow-hidden bg-slate-950 text-white font-sans touch-none selection:bg-transparent">
      {/* Meteor Canvas */}
      <canvas
        ref={canvasRef}
        className="absolute inset-0 w-full h-full block cursor-pointer"
        onClick={() => setShowUI(!showUI)}
      />

      {/* Stats UI */}
      {!uiState.isBreakdown && (
        <div className="absolute bottom-4 left-4 text-[10px] text-slate-500 font-mono pointer-events-none">
          UCD-F POOL: {uiState.activeCount} / 5000 | COLLISION: ENABLED
        </div>
      )}

      {/* Breakdown Overlay */}
      {uiState.isBreakdown && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-red-950/50 backdrop-blur-md z-20">
          <AlertTriangle size={64} className="text-red-400 mb-4 animate-pulse" />
          <h2 className="text-2xl font-bold text-red-200 mb-2">システム限界超過</h2>
          <div className="w-64 h-2 bg-slate-800 rounded-full overflow-hidden mt-4">
            <div 
              className="h-full bg-red-500 transition-all duration-300"
              style={{ width: `${uiState.fatigueLevel}%` }}
            ></div>
          </div>
        </div>
      )}

      {/* UI Toggle Button */}
      <button 
        onClick={() => setShowUI(!showUI)}
        className="absolute top-6 right-6 z-30 p-3 bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 rounded-2xl backdrop-blur-xl border border-slate-700/50 transition-all shadow-xl"
      >
        {showUI ? <EyeOff size={22} /> : <Eye size={22} />}
      </button>

      {/* Main UI */}
      <div className={`absolute inset-0 flex flex-col justify-between p-6 pb-12 transition-all duration-700 ease-in-out ${showUI ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4 pointer-events-none'}`}>
        
        {/* Top Status */}
        <div className="flex flex-col gap-3 w-full max-sm mx-auto z-10 pointer-events-auto">
          <div className="bg-slate-900/60 backdrop-blur-2xl p-5 rounded-3xl border border-white/5 shadow-2xl">
            <div className="flex justify-between items-center mb-3">
              <div className="flex items-center gap-2">
                <Star size={18} className={uiState.quality > 80 ? "text-blue-400 fill-blue-400" : "text-slate-500"} />
                <span className="font-semibold text-xs text-slate-400 tracking-wider uppercase">星の美しさ (Quality)</span>
              </div>
              <span className="text-lg font-bold font-mono">{uiState.quality}%</span>
            </div>
            <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div 
                className="h-full transition-all duration-500 rounded-full"
                style={{ 
                  width: `${uiState.quality}%`,
                  background: uiState.quality > 70 ? 'linear-gradient(90deg, #60a5fa, #c084fc)' : '#475569'
                }}
              ></div>
            </div>
          </div>

          <div className="bg-slate-900/60 backdrop-blur-2xl p-5 rounded-3xl border border-white/5 shadow-2xl">
            <div className="flex justify-between items-center mb-3">
              <div className="flex items-center gap-2">
                <Coffee size={18} className={uiState.fatigueLevel > 75 ? "text-orange-400" : "text-slate-500"} />
                <span className="font-semibold text-xs text-slate-400 tracking-wider uppercase">つかれ (Fatigue)</span>
              </div>
              <span className="text-sm font-bold text-slate-300">
                {uiState.velocity === 0 && uiState.fatigueLevel > 0 ? "回復中" : `${Math.round(uiState.fatigueLevel)}%`}
              </span>
            </div>
            <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div 
                className="h-full transition-all duration-300 rounded-full"
                style={{ 
                  width: `${uiState.fatigueLevel}%`,
                  backgroundColor: uiState.fatigueLevel > 80 ? '#f87171' : 
                                   uiState.fatigueLevel > 50 ? '#fbbf24' : '#10b981'
                }}
              ></div>
            </div>
          </div>
        </div>

        {/* Bottom Controls */}
        <div className="w-full max-w-sm mx-auto z-10 pointer-events-auto bg-slate-900/90 backdrop-blur-3xl p-8 rounded-[40px] border border-white/10 shadow-[0_32px_64px_-16px_rgba(0,0,0,0.6)]">
          
          {/* Velocity Control */}
          <div className="mb-10">
            <div className="flex justify-between items-center mb-6">
              <label className="font-bold text-xl text-white flex items-center gap-3">
                <Zap size={22} className="text-blue-400 fill-blue-400/20"/>
                ペース
              </label>
              <div className="flex flex-col items-end">
                <span className="text-2xl font-black text-blue-400 font-mono leading-none">
                  {uiState.velocity === 0 ? "0" : uiState.velocity}
                </span>
              </div>
            </div>
            <input 
              type="range" 
              min="0" max="10" step="1"
              value={uiState.velocity}
              onChange={(e) => vifRef.current.v_target = parseFloat(e.target.value)}
              disabled={uiState.isBreakdown}
              className="w-full h-4 bg-slate-800 rounded-full appearance-none cursor-pointer accent-blue-500 transition-all hover:bg-slate-700"
            />
            <div className="flex justify-between text-[10px] font-bold text-slate-600 mt-4 px-1 uppercase tracking-widest">
              <span>Recovery</span>
              <span>Stability</span>
              <span>Max</span>
            </div>
          </div>

          {/* Strength Control */}
          <div>
            <div className="flex justify-between items-center mb-6">
              <label className="font-bold text-lg text-slate-300">
                星の濃さ
              </label>
              <span className="text-xl font-bold text-indigo-400 font-mono">
                {uiState.strength}
              </span>
            </div>
            <input 
              type="range" 
              min="1" max="10" step="1"
              value={uiState.strength}
              onChange={(e) => vifRef.current.strength = parseFloat(e.target.value)}
              disabled={uiState.isBreakdown}
              className="w-full h-2.5 bg-slate-800 rounded-full appearance-none cursor-pointer accent-indigo-500 hover:bg-slate-700"
            />
          </div>
        </div>
      </div>
    </div>
  );
}