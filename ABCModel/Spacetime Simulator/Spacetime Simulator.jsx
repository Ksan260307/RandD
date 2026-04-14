import React, { useState, useEffect, useRef } from 'react';
import { Info, X, Zap, Target, Eye } from 'lucide-react';

export default function App() {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const [showInfo, setShowInfo] = useState(false);
  
  // UI表示用のステータス（Canvasループから定期的に同期）
  const [status, setStatus] = useState({
    A: { val: 1, state: 0 },
    B: { val: 0, state: 0 },
    C: { val: 0, state: 0 },
    ruin: 0
  });

  // 物理演算の内部状態（ABCモデル Core層の変数群）
  const sim = useRef({
    tA: 1, tB: 0, tC: 0,       // Target (ユーザー入力 0~2)
    cA: 1, cB: 0, cC: 0,       // Current (追従中の現在値 0~2)
    calcA: 1, calcB: 0, calcC: 0, // 相互作用適用後の最終値
    sA: 0, sB: 0, sC: 0,       // State (-1:Zero, 0:Normal, 1:Runaway)
    time: 0,
    particles: []
  });

  // --- ABC Model & 物理演算ロジック ---
  const updatePhysics = () => {
    const p = sim.current;
    p.time += 0.016; // 約60fps

    // 1. 目標値への追従と変動幅(Δ)の疑似計算
    const speed = 0.05;
    const dA = p.tA - p.cA;
    const dB = p.tB - p.cB;
    const dC = p.tC - p.cC;
    
    p.cA += dA * speed;
    p.cB += dB * speed;
    p.cC += dC * speed;

    // 変動量（Δ）を0〜2のスケールに変換
    const deltaA = Math.min(2, Math.abs(dA) * 10);
    const deltaB = Math.min(2, Math.abs(dB) * 10);
    const deltaC = Math.min(2, Math.abs(dC) * 10);

    // 2. ベース状態の判定 (Low/Mid/High, Spike等から推測)
    const getState = (v) => {
      if (v >= 1.6) return 1; // Runaway (暴走/崩壊)
      if (v <= 0.2) return -1; // Zero (凍結/停止)
      return 0; // Normal (安定)
    };
    let sA = getState(p.cA);
    let sB = getState(p.cB);
    let sC = getState(p.cC);

    // 3. 相互作用 I の計算 (Core v3.2.0準拠)
    // C→A (-1: 観測は生感を抑制)
    // B→C (+1: 評価圧は監視を強化)
    // A→B (-1: 生感は評価を減衰)
    const g = (v) => 0.5 * Math.tanh(0.7 * v);
    const w = (state) => state === 1 ? 0.9 : (state === -1 ? 0.25 : 0);
    const sgn = (state) => state === 1 ? 1 : 0; // Zeroの符号は中立(0)
    
    // スパイク時のブースト
    const boostA = 1 + 0.35 * (deltaA >= 1.5 ? 1 : 0);
    const boostB = 1 + 0.35 * (deltaB >= 1.5 ? 1 : 0);
    const boostC = 1 + 0.35 * (deltaC >= 1.5 ? 1 : 0);

    let calcA = p.cA + sgn(sC) * w(sC) * (-1) * g(p.cC) * boostC; 
    let calcB = p.cB + sgn(sA) * w(sA) * (-1) * g(p.cA) * boostA;
    let calcC = p.cC + sgn(sB) * w(sB) * (+1) * g(p.cB) * boostB;

    const clamp = v => Math.max(0, Math.min(2, v));
    calcA = clamp(calcA);
    calcB = clamp(calcB);
    calcC = clamp(calcC);

    // 4. TR (Transition Rules) の簡易適用
    // TR-1: 観測(C)暴走、ΔCスパイク、A弱いで AがZero化（観測問題・時間停止）
    if (sC === 1 && deltaC >= 1.5 && calcA <= 1.0) {
      sA = -1;
    }
    // TR-2: 重力(B)暴走、AがZeroで Cも暴走（事象の地平面の完成）
    if (sB === 1 && sA === -1) {
      sC = 1;
    }
    // TR-3: AがHigh、BがSwingで B減衰（内なる光による重力の安定化）
    if (calcA >= 1.5 && deltaB >= 0.5) {
      calcB = 1.0; 
      sB = 0; 
    }

    // 結果の保存
    p.calcA = calcA; p.calcB = calcB; p.calcC = calcC;
    p.sA = sA; p.sB = sB; p.sC = sC;
  };

  // --- Canvas 描画ロジック ---
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    let animationFrameId;

    // パーティクル（光子）の初期化
    const initParticles = (width, height) => {
      sim.current.particles = Array.from({ length: 150 }, () => ({
        angle: Math.random() * Math.PI * 2,
        baseRadius: 20 + Math.random() * Math.max(width, height) * 0.4,
        yOffset: (Math.random() - 0.5) * 60,
        size: Math.random() * 2 + 0.5,
        speed: (Math.random() * 0.015 + 0.005),
        hue: Math.random() * 60 + 180, // 青ベース
      }));
    };

    const resize = () => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      // 高解像度ディスプレイ対応
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      initParticles(rect.width, rect.height);
    };

    window.addEventListener('resize', resize);
    resize();

    // 描画ループ
    const render = () => {
      updatePhysics();
      const p = sim.current;
      const rect = containerRef.current.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;
      const cx = w / 2;
      const cy = h / 2;

      // 背景のクリア（残像効果）
      ctx.fillStyle = `rgba(5, 5, 10, ${p.sC === 1 ? 0.4 : 0.2})`;
      ctx.fillRect(0, 0, w, h);

      // --- 空間の歪み（重力・グリッド） ---
      ctx.lineWidth = 1;
      const maxRadius = Math.max(w, h);
      for(let r = maxRadius; r > 10; r -= 40) {
        // calcB に応じて中心に吸い込まれる波動
        let currentR = r - (p.time * 30 * (p.calcB + 0.1)) % 40;
        if (currentR < 0) currentR = 0;
        
        // 暴走時は歪みを加える
        const distortion = p.sB === 1 ? (Math.random() - 0.5) * 10 : 0;
        
        const radiusX = Math.max(0, currentR + distortion);
        const radiusY = Math.max(0, currentR * 0.4 + distortion);
        
        ctx.beginPath();
        ctx.ellipse(cx, cy, radiusX, radiusY, 0, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(40, 80, 150, ${Math.min(0.3, currentR / maxRadius * p.calcB)})`;
        ctx.stroke();
      }

      // --- 光子（パーティクル）の描画 ---
      p.particles.forEach(pt => {
        // calcA (光量/エネルギー) に応じた速度
        let currentSpeed = pt.speed * (p.calcA + 0.2);
        if (p.sA === -1) currentSpeed *= 0.02; // Zero時はほぼ停止

        pt.angle += currentSpeed;

        // calcB (重力) に応じた半径の収縮
        let currentRadius = pt.baseRadius * (1 - p.calcB * 0.45);
        if (p.sB === 1) {
          // 暴走時は軌道が乱れる
          currentRadius += (Math.random() - 0.5) * (30 * p.calcB);
        }

        const x = cx + Math.cos(pt.angle) * currentRadius;
        const y = cy + Math.sin(pt.angle) * currentRadius * 0.4 + pt.yOffset;

        // 色の決定（Stateに基づく）
        let color = `hsl(${pt.hue}, 80%, 70%)`;
        if (p.sA === -1) {
          color = `rgba(150, 150, 150, 0.4)`; // 時間凍結（灰色）
        } else if (p.sB === 1) {
          color = `hsl(${Math.random() * 40 + 0}, 100%, 60%)`; // 重力崩壊（赤）
        } else if (p.sC === 1) {
          color = `hsl(${Math.random() * 60 + 260}, 90%, 60%)`; // 事象の地平（紫）
        } else {
          // Aが高いとより明るく
          const l = 50 + (p.calcA * 20);
          color = `hsl(${pt.hue}, 80%, ${l}%)`;
        }

        ctx.beginPath();
        ctx.arc(x, y, pt.size * (p.calcA + 0.5), 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
      });

      // --- 中心星（ブラックホール / 恒星） ---
      ctx.beginPath();
      const coreSize = 10 + p.calcB * 20;
      ctx.arc(cx, cy, coreSize, 0, Math.PI * 2);
      
      const coreGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreSize * 2);
      if (p.sB === 1) {
        coreGrad.addColorStop(0, 'black');
        coreGrad.addColorStop(1, 'rgba(255, 0, 50, 0)');
      } else if (p.sA === -1) {
        coreGrad.addColorStop(0, '#333');
        coreGrad.addColorStop(1, 'rgba(50, 50, 50, 0)');
      } else {
        coreGrad.addColorStop(0, `rgba(200, 230, 255, ${p.calcA})`);
        coreGrad.addColorStop(1, 'rgba(0, 100, 255, 0)');
      }
      ctx.fillStyle = coreGrad;
      ctx.fill();

      // --- 観測の境界（ビネット効果） ---
      if (p.calcC > 0.1 || p.sC === 1) {
        const vigGrad = ctx.createRadialGradient(cx, cy, Math.min(w,h)*0.3, cx, cy, Math.max(w,h)*0.8);
        if (p.sC === 1) {
          vigGrad.addColorStop(0, 'rgba(0,0,0,0)');
          vigGrad.addColorStop(1, `rgba(150, 0, 80, ${0.4 + Math.random()*0.2})`);
        } else {
          vigGrad.addColorStop(0, 'rgba(0,0,0,0)');
          vigGrad.addColorStop(1, `rgba(40, 0, 60, ${p.calcC * 0.5})`);
        }
        ctx.fillStyle = vigGrad;
        ctx.fillRect(0, 0, w, h);
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    // UI用のステータス同期（軽量化のため別周期）
    const syncInterval = setInterval(() => {
      const p = sim.current;
      // RuinScore（危険度）の簡易計算
      let ruin = 0;
      if (p.sA === -1 || p.sB === 1 || p.sC === 1) ruin = 2; // R1-R2
      if (p.sB === 1 && p.sA === -1) ruin = 3; // R3 (Critical)

      setStatus({
        A: { val: p.calcA, state: p.sA },
        B: { val: p.calcB, state: p.sB },
        C: { val: p.calcC, state: p.sC },
        ruin
      });
    }, 200);

    return () => {
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(animationFrameId);
      clearInterval(syncInterval);
    };
  }, []);

  // スライダー操作ハンドラー (0~100 を 0~2 にマッピング)
  const handleSlider = (type, val) => {
    const v = (val / 100) * 2;
    if (type === 'A') sim.current.tA = v;
    if (type === 'B') sim.current.tB = v;
    if (type === 'C') sim.current.tC = v;
  };

  // UI上の状態テキストを取得
  const getStateText = (type, st) => {
    if (st.state === -1) return { text: "凍結", color: "text-gray-400" };
    if (st.state === 1) return { text: "崩壊", color: "text-red-400" };
    if (st.val > 1.5) return { text: "高揚", color: "text-blue-300" };
    if (st.val < 0.5) return { text: "微弱", color: "text-gray-500" };
    return { text: "安定", color: "text-green-400" };
  };

  return (
    <div className="relative w-full h-screen bg-black text-white font-sans overflow-hidden" ref={containerRef}>
      {/* 描画キャンバス */}
      <canvas ref={canvasRef} className="absolute inset-0 block" />

      {/* ヘッダー＆ステータス */}
      <div className="absolute top-0 left-0 w-full p-4 md:p-6 flex justify-between items-start pointer-events-none">
        <div className="bg-black/40 backdrop-blur-md rounded-2xl border border-white/10 p-4 shadow-xl pointer-events-auto">
          <h1 className="text-sm font-bold tracking-widest text-white/80 mb-3 flex items-center">
            SPACETIME STATUS
            {status.ruin > 0 && (
              <span className={`ml-2 w-2 h-2 rounded-full animate-ping ${status.ruin === 3 ? 'bg-red-500' : 'bg-yellow-500'}`} />
            )}
          </h1>
          <div className="space-y-2 text-xs font-mono">
            {[
              { label: "固有時 [光]", icon: <Zap size={14}/>, data: status.A },
              { label: "重力場 [歪]", icon: <Target size={14}/>, data: status.B },
              { label: "観測界 [壁]", icon: <Eye size={14}/>, data: status.C }
            ].map((item, i) => {
              const info = getStateText(item.label, item.data);
              return (
                <div key={i} className="flex items-center justify-between gap-6">
                  <div className="flex items-center gap-2 text-white/60">
                    {item.icon}
                    <span>{item.label}</span>
                  </div>
                  <div className={`font-bold ${info.color}`}>
                    {info.text}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <button 
          onClick={() => setShowInfo(true)}
          className="p-3 bg-black/40 backdrop-blur-md rounded-full border border-white/10 hover:bg-white/10 transition pointer-events-auto"
        >
          <Info size={20} />
        </button>
      </div>

      {/* コントロールパネル */}
      <div className="absolute bottom-4 left-4 right-4 md:left-1/2 md:-translate-x-1/2 md:w-full md:max-w-lg">
        <div className="bg-black/50 backdrop-blur-xl rounded-3xl border border-white/10 p-5 md:p-6 shadow-2xl">
          <div className="space-y-5">
            <SliderRow 
              label="主観的なエネルギー (光)" 
              color="bg-blue-500" 
              defaultValue={50}
              onChange={(v) => handleSlider('A', v)}
            />
            <SliderRow 
              label="他者との比較 (重力場)" 
              color="bg-red-500" 
              defaultValue={0}
              onChange={(v) => handleSlider('B', v)}
            />
            <SliderRow 
              label="客観的な視線 (観測の壁)" 
              color="bg-purple-500" 
              defaultValue={0}
              onChange={(v) => handleSlider('C', v)}
            />
          </div>
        </div>
      </div>

      {/* 解説モーダル */}
      {showInfo && (
        <div className="absolute inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6 z-50">
          <div className="bg-gray-900 border border-white/10 rounded-2xl p-6 md:p-8 max-w-md relative">
            <button 
              onClick={() => setShowInfo(false)}
              className="absolute top-4 right-4 text-white/50 hover:text-white"
            >
              <X size={24} />
            </button>
            <h2 className="text-xl font-bold mb-4">時空の歪みと内なる力学</h2>
            <div className="space-y-4 text-sm text-white/70 leading-relaxed">
              <p>
                もし、アインシュタインの相対性理論が「人間の感情の力学」を表すメタファーだとしたら？
              </p>
              <p>
                <strong>・光（固有時）：</strong>あなた自身のエネルギー、体感、自然な反応。<br/>
                <strong>・重力（歪み）：</strong>他者との比較、評価の基準、外部からの圧。<br/>
                <strong>・観測（境界）：</strong>第三者の視点、監視されているという認知。
              </p>
              <p>
                これらは互いに干渉し合います。例えば、観測の眼が強すぎると量子力学の観測問題のようにあなたのエネルギーは停止します（時間凍結）。また、重力が強すぎると光さえ逃げられないブラックホール（崩壊）が生まれます。
              </p>
              <p className="text-xs text-white/40 pt-4 border-t border-white/10">
                ※このシミュレータは、特定の感情力学モデルの相互作用ロジックに基づいて時空の振る舞いを計算しています。パラメータを動かして、あなただけの宇宙を観察してください。
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// カスタムスライダーコンポーネント
function SliderRow({ label, color, defaultValue, onChange }) {
  const [value, setValue] = useState(defaultValue);

  const handleChange = (e) => {
    const val = parseInt(e.target.value, 10);
    setValue(val);
    onChange(val);
  };

  return (
    <div className="space-y-2">
      <div className="flex justify-between text-xs text-white/70">
        <label>{label}</label>
        <span className="font-mono">{value}%</span>
      </div>
      <div className="relative w-full h-2 bg-gray-800 rounded-full overflow-hidden">
        <div 
          className={`absolute top-0 left-0 h-full ${color} opacity-80`} 
          style={{ width: `${value}%` }}
        />
        <input 
          type="range" 
          min="0" 
          max="100" 
          value={value}
          onChange={handleChange}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
        />
      </div>
    </div>
  );
}