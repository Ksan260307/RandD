import React, { useState, useEffect, useRef } from 'react';
import { Settings, Sun, CloudRain, Activity, Sparkles } from 'lucide-react';

export default function App() {
  // --- State & Refs ---
  const [tvd, setTvd] = useState({ D: 0.5, R: 0.5, F_int: 0.5, dD: 0, dR: 0 });
  const [pos, setPos] = useState({ head: 100, tail: 40 });
  
  // ユーザーが操作するパラメータ群
  const [params, setParams] = useState({
    F_ext: 0.5,        // まわりの環境 (0~1) ※0.8だと張り付くので0.5をデフォルトに
    Input: 0,          // ちょっかい (-1~1)
    lambda_eff: 0.2,   // マイペースさ (0.05~0.5) 減衰・安定性
    epsilon: 0.01,     // つかれやすさ (0~0.1) 動的減衰
    k: 1.5,
    alpha: 0.5
  });

  const tvdRef = useRef({ D: 0.5, R: 0.5, F_int: 0.5 });
  const posRef = useRef({ head: 100, tail: 40 });
  const paramsRef = useRef(params);
  const timeRef = useRef(0);

  useEffect(() => {
    paramsRef.current = params;
  }, [params]);

  // --- TVD Core Logic Loop ---
  useEffect(() => {
    let animationFrameId;
    
    const loop = () => {
      const dt = 0.05; // 固定時間ステップ
      timeRef.current += dt;
      
      const currentTvd = tvdRef.current;
      const currentPos = posRef.current;
      const p = paramsRef.current;

      const { D, R, F_int } = currentTvd;

      // 1. Field統合（外部環境に呼吸のような揺らぎを少し足す）
      const breath = Math.sin(timeRef.current * 2) * 0.03;
      const F_ext_effective = Math.max(0, Math.min(1, p.F_ext + breath));
      const F_total = Math.max(0, Math.min(1, F_int + F_ext_effective));

      // 2. ベロシティ計算 (v = v0 + W_state*X + W_input*Input)
      const v_D = D + p.Input;
      const v_R = R;
      const v_F = F_int;

      const sigmoid = x => 1 / (1 + Math.exp(-x));
      const calcG = v => Math.exp(p.k * ((1 + 9 * sigmoid(v)) / 10 - 0.5));

      const G_D = calcG(v_D);
      const G_R = calcG(v_R);
      const G_F = calcG(v_F);

      // 3. 状態更新式 (Euler積分)
      let dD = G_D * (F_total - R) - p.lambda_eff * D * (1 - D) - p.epsilon * D * D + p.alpha * Math.tanh(p.Input);
      let dR = G_R * (D - F_total) - p.lambda_eff * R * (1 - R) - p.epsilon * R * R;
      
      // 新解釈：「伸びる(D主導)と元気を消費し、縮む(R主導)と元気が回復する」ことで美しいサイクル(歩行)を生む
      let dF = G_F * (R - D) - p.lambda_eff * F_int * (1 - F_int) - p.epsilon * F_int * F_int;

      // ドリフト対策（停滞したら少しノイズを入れて発火させる）
      if (Math.abs(dD) < 0.01 && Math.abs(dR) < 0.01) {
        dD += (Math.random() - 0.5) * 0.2;
        dR += (Math.random() - 0.5) * 0.2;
      }

      const next_D = Math.max(0, Math.min(1, D + dt * dD));
      const next_R = Math.max(0, Math.min(1, R + dt * dR));
      const next_F_int = Math.max(0, Math.min(1, F_int + dt * dF));

      tvdRef.current = { D: next_D, R: next_R, F_int: next_F_int };
      setTvd({ D: next_D, R: next_R, F_int: next_F_int, dD, dR });

      // 4. しゃくとりむしの移動マッピング
      // のびる力(D)とちぢむ力(R)の差分を「目標の長さ」にする
      const targetL = Math.max(20, 40 + (next_D - next_R) * 60);
      const currentL = currentPos.head - currentPos.tail;
      const diff = targetL - currentL;
      const moveSpeed = 0.2;

      let headMove = 0;
      let tailMove = 0;

      if (next_D > next_R) {
        // D主導：伸びるフェーズ（頭を前に出す）
        headMove = diff * moveSpeed;
      } else {
        // R主導：縮むフェーズ（お尻を前に寄せる）
        tailMove = -diff * moveSpeed;
      }

      // Input(ちょっかい)の直接介入
      if (p.Input < 0) {
        // 驚いて後ずさる
        headMove += p.Input * 4;
        tailMove += p.Input * 4;
      } else if (p.Input > 0) {
        // おされて進む
        headMove += p.Input * 2;
        tailMove += p.Input * 2;
      }

      // Inputがない時は「前進のみ（逆止弁）」の構造にする
      if (p.Input === 0) {
        headMove = Math.max(0, headMove);
        tailMove = Math.max(0, tailMove);
      }

      let nextHead = currentPos.head + headMove;
      let nextTail = currentPos.tail + tailMove;

      // 物理的な長さ制約
      if (nextHead - nextTail < 15) {
        if (next_D > next_R) nextHead = nextTail + 15;
        else nextTail = nextHead - 15;
      }
      if (nextHead - nextTail > 120) {
        if (next_D > next_R) nextTail = nextHead - 120;
        else nextHead = nextTail + 120;
      }

      posRef.current = { head: nextHead, tail: nextTail };
      setPos({ head: nextHead, tail: nextTail });

      animationFrameId = requestAnimationFrame(loop);
    };

    animationFrameId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animationFrameId);
  }, []);

  // --- Render Helpers ---
  const cameraX = (pos.head + pos.tail) / 2 - 200; // 画面中央(200)に虫を配置
  const bgOffset = -(cameraX % 40);

  // 草の無限スクロール生成
  const grasses = Array.from({ length: 15 }).map((_, i) => (
    <path 
      key={i} 
      d={`M ${i * 40 + bgOffset} 180 Q ${i * 40 + 5 + bgOffset} 170 ${i * 40 + 10 + bgOffset} 180`} 
      stroke="#65a30d" fill="none" strokeWidth="2" strokeLinecap="round" 
    />
  ));

  const relTail = pos.tail - cameraX;
  const relHead = pos.head - cameraX;
  const currentLen = pos.head - pos.tail;
  const archHeight = Math.max(10, 80 - currentLen * 0.7);

  // 表情ロジック
  let eyeStyle = "normal";
  if (params.Input < -0.1) eyeStyle = "scared";
  else if (tvd.F_int < 0.3) eyeStyle = "sleepy";
  else if (tvd.D > 0.8) eyeStyle = "excited";

  const renderEyes = (cx, cy) => {
    if (eyeStyle === "scared") {
      return (
        <g stroke="#064e3b" strokeWidth="2" fill="none" strokeLinecap="round">
          <path d={`M ${cx-4} ${cy-3} L ${cx} ${cy} L ${cx-4} ${cy+3}`} />
          <path d={`M ${cx+8} ${cy-3} L ${cx+4} ${cy} L ${cx+8} ${cy+3}`} />
        </g>
      );
    } else if (eyeStyle === "sleepy") {
      return (
        <g stroke="#064e3b" strokeWidth="2" strokeLinecap="round">
          <line x1={cx-2} y1={cy+2} x2={cx+2} y2={cy+2} />
          <line x1={cx+6} y1={cy+2} x2={cx+10} y2={cy+2} />
        </g>
      );
    } else {
      return (
        <g fill="#064e3b">
          <circle cx={cx} cy={cy} r="2.5" />
          <circle cx={cx+8} cy={cy} r="2.5" />
          {tvd.F_int > 0.6 && <circle cx={cx-2} cy={cy+4} r="3" fill="#fca5a5" opacity="0.8" />}
        </g>
      );
    }
  };

  // 足の振り
  const legSwing = (tvd.D - tvd.R) * 6;

  return (
    <div className="h-screen w-full flex flex-col max-w-md mx-auto bg-slate-50 shadow-2xl overflow-hidden font-sans text-slate-800">
      
      {/* Header */}
      <header className="p-3 bg-white shadow-sm flex items-center justify-between z-10 shrink-0">
        <h1 className="text-lg font-bold text-green-600 flex items-center gap-2">
          🐛 しゃくとりむしのさんぽ
        </h1>
        <span className="text-[10px] bg-green-100 text-green-800 px-2 py-1 rounded-full font-bold">
          TVD Core
        </span>
      </header>

      {/* Canvas Area */}
      <div 
        className="relative w-full h-56 shrink-0 border-b-4 border-green-700 transition-colors duration-1000"
        style={{ backgroundColor: params.F_ext > 0.5 ? '#e0f2fe' : '#cbd5e1' }}
      >
        {/* Weather */}
        <div className="absolute top-4 right-6 transition-all duration-1000">
          {params.F_ext > 0.5 ? (
            <Sun className="w-12 h-12 text-amber-400 fill-amber-400/20 drop-shadow-md" />
          ) : (
            <CloudRain className="w-12 h-12 text-slate-500 fill-slate-500/20 drop-shadow-md" />
          )}
        </div>

        <svg width="100%" height="100%" viewBox="0 0 400 224" preserveAspectRatio="xMidYMid slice">
          {/* Ground */}
          <rect y="180" width="400" height="44" fill="#a3b18a" />
          {grasses}

          {/* Bug */}
          <g>
            {/* Back Legs */}
            <line x1={relTail - 6 - legSwing} y1={180} x2={relTail - 10 - legSwing} y2={188} stroke="#166534" strokeWidth="4" strokeLinecap="round" />
            <line x1={relTail + 4 - legSwing} y1={180} x2={relTail - legSwing} y2={188} stroke="#166534" strokeWidth="4" strokeLinecap="round" />
            
            {/* Front Legs */}
            <line x1={relHead - 6 + legSwing} y1={180} x2={relHead - 10 + legSwing} y2={188} stroke="#166534" strokeWidth="4" strokeLinecap="round" />
            <line x1={relHead + 4 + legSwing} y1={180} x2={relHead + legSwing} y2={188} stroke="#166534" strokeWidth="4" strokeLinecap="round" />

            {/* Body */}
            <path 
              d={`M ${relTail} 175 Q ${(relTail+relHead)/2} ${175 - archHeight * 2} ${relHead} 175`} 
              stroke="#4ade80" 
              strokeWidth="20" 
              fill="none" 
              strokeLinecap="round" 
              strokeLinejoin="round"
            />
            {/* Body inner highlight */}
            <path 
              d={`M ${relTail} 175 Q ${(relTail+relHead)/2} ${175 - archHeight * 2} ${relHead} 175`} 
              stroke="#22c55e" 
              strokeWidth="10" 
              fill="none" 
              strokeLinecap="round" 
            />

            {/* Head */}
            <circle cx={relHead + 2} cy={175} r="16" fill="#4ade80" />
            {/* Antennae */}
            <path d={`M ${relHead} 160 Q ${relHead-5} 150 ${relHead+5} 145`} stroke="#166534" fill="none" strokeWidth="2" strokeLinecap="round" />
            <path d={`M ${relHead+8} 163 Q ${relHead+15} 150 ${relHead+20} 152`} stroke="#166534" fill="none" strokeWidth="2" strokeLinecap="round" />
            
            {/* Face */}
            {renderEyes(relHead + 2, 172)}
          </g>
        </svg>
      </div>

      {/* Control Area (Scrollable) */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 pb-10">
        
        {/* Status Meters (TVD Model Observers) */}
        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
          <h2 className="text-xs font-bold text-slate-400 mb-3 flex items-center gap-1 uppercase tracking-wider">
            <Activity className="w-4 h-4" /> いまの内部状態
          </h2>
          <div className="space-y-3">
            <Meter label="🔴 のびる力 (D)" value={tvd.D} color="bg-rose-400" />
            <Meter label="🔵 ちぢむ力 (R)" value={tvd.R} color="bg-sky-400" />
            <Meter label="💛 げんき (F_int)" value={tvd.F_int} color="bg-amber-400" />
          </div>
          
          <div className="mt-4 pt-3 border-t border-slate-100 flex justify-between text-xs text-slate-500 font-medium">
            <div className="flex items-center gap-1">
               <Sparkles className="w-3 h-3 text-indigo-400" /> 
               すすむ力(D-R): {((tvd.D - tvd.R)*100).toFixed(0)}
            </div>
            <div>
               かつどう量: {((tvd.D + tvd.R + tvd.F_int)*33.3).toFixed(0)}
            </div>
          </div>
        </div>

        {/* User Controls */}
        <div className="bg-white p-4 rounded-2xl shadow-sm border border-slate-100 space-y-6">
          <h2 className="text-xs font-bold text-slate-400 mb-2 flex items-center gap-1 uppercase tracking-wider">
            <Settings className="w-4 h-4" /> あそぶ・いじる
          </h2>
          
          <SliderControl 
            label="☀️ まわりの環境" 
            desc="天気がいいと活発に動くよ"
            min={0} max={1} step={0.05} 
            value={params.F_ext} 
            onChange={v => setParams({...params, F_ext: parseFloat(v)})} 
            leftIcon="🌧️" rightIcon="☀️"
          />

          <SliderControl 
            label="👉 ちょっかいを出す" 
            desc="はなすと元に戻るよ"
            min={-1} max={1} step={0.1} 
            value={params.Input} 
            onChange={v => setParams({...params, Input: parseFloat(v)})} 
            onRelease={() => setParams({...params, Input: 0})}
            leftIcon="⏪" rightIcon="⏩"
            accent="accent-rose-500"
          />

          <div className="pt-2 border-t border-slate-50 border-dashed space-y-6">
            <SliderControl 
              label="🐢 マイペースさ" 
              desc="安定しようとする力 (λ_eff)"
              min={0.05} max={0.5} step={0.05} 
              value={params.lambda_eff} 
              onChange={v => setParams({...params, lambda_eff: parseFloat(v)})} 
              leftIcon="暴走" rightIcon="安定"
            />

            <SliderControl 
              label="🔋 つかれやすさ" 
              desc="エネルギーの減り (ε)"
              min={0.0} max={0.1} step={0.01} 
              value={params.epsilon} 
              onChange={v => setParams({...params, epsilon: parseFloat(v)})} 
              leftIcon="タフ" rightIcon="バテる"
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// --- UI Components ---

function Meter({ label, value, color }) {
  return (
    <div className="flex items-center gap-3 text-sm">
      <div className="w-28 font-bold text-slate-600 truncate">{label}</div>
      <div className="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden shadow-inner">
        <div 
          className={`h-full ${color} transition-all duration-100 ease-out`} 
          style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} 
        />
      </div>
    </div>
  );
}

function SliderControl({ label, desc, min, max, step, value, onChange, onRelease, leftIcon, rightIcon, accent="accent-green-500" }) {
  return (
    <div>
      <div className="flex justify-between items-baseline mb-2">
        <label className="font-bold text-slate-700">{label}</label>
        <span className="text-[10px] font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded-md">{desc}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-lg">{leftIcon}</span>
        <input 
          type="range" 
          min={min} max={max} step={step} 
          value={value} 
          onChange={e => onChange(e.target.value)}
          onMouseUp={onRelease}
          onTouchEnd={onRelease}
          className={`flex-1 h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer ${accent}`}
        />
        <span className="text-lg">{rightIcon}</span>
      </div>
    </div>
  );
}