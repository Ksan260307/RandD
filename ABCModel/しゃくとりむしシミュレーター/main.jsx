import React, { useState, useEffect, useRef } from 'react';

// --- ABCモデル Core層(v3.2.0) 簡易演算ロジック ---
function calculateCore(a, b, c, e) {
  // 1. 外部環境(EF)の重畳
  let vA = Math.max(0, Math.min(2, a - 0.5 * e));
  let vB = Math.max(0, Math.min(2, b + 0.5 * e));
  let vC = Math.max(0, Math.min(2, c + 0.5 * e));

  // 2. 暴走(Runaway)判定
  const runA = vA >= 1.5;
  const runB = vB >= 1.5;
  const runC = vC >= 1.5;

  // 3. 相互作用 (I)
  // C→A (-1): 考えすぎが本能的な元気を抑制
  if (runC) vA = Math.max(0, vA - 0.5);
  // B→C (+1): プレッシャーがメタ認知（考えすぎ）を加速
  if (runB) vC = Math.min(2, vC + 0.5);
  // A→B (-1): 元気があればプレッシャーを跳ね除ける
  if (runA) vB = Math.max(0, vB - 0.5);

  // 4. フリーズ(Zero)判定 (TR-1ルール)
  // 考えすぎが暴走し、かつ元気がない場合、完全に停止する
  let isZero = false;
  if (runC && vA <= 1.0) {
    isZero = true;
    vA = 0; // 行動停止
  }

  // 5. ストレス度(RuinScore)の計算 (0〜6)
  // プレッシャー(B)、考えすぎ(C)、環境(E)の最大値をベースに計算
  let rBase = Math.max(vB, vC, e) * 2;
  if (runB || runC) rBase += 1; // 暴走があれば加点
  if (isZero) rBase = Math.max(rBase, 5); // Zero状態なら危険度MAXクラス(5以上)

  const ruinScore = Math.min(6, Math.max(0, Math.floor(rBase)));

  return { vA, vB, vC, ruinScore, isZero };
}

export default function App() {
  // スライダーの入力値 (0.0 〜 2.0)
  const [inputs, setInputs] = useState({ a: 1.5, b: 0.5, c: 0.5, e: 0.0 });
  // 内部状態 (演算後)
  const [coreState, setCoreState] = useState(calculateCore(1.5, 0.5, 0.5, 0.0));
  
  const canvasRef = useRef(null);
  
  // アニメーション用の状態をRefで保持（再レンダリングを防ぐため）
  const animState = useRef({
    phase: 'THINK', // THINK(待機) -> STRETCH(伸びる) -> CONTRACT(縮む)
    timer: 0,
    headX: 40,
    tailX: -40,
    totalDist: 0,
    raindrops: [],
  });

  // スライダー変更時
  const handleChange = (key, value) => {
    const newInputs = { ...inputs, [key]: parseFloat(value) };
    setInputs(newInputs);
    setCoreState(calculateCore(newInputs.a, newInputs.b, newInputs.c, newInputs.e));
  };

  // メインアニメーションループ
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    let animationFrameId;

    const render = () => {
      // 画面サイズ調整
      const width = canvas.parentElement.clientWidth;
      const height = 250;
      if (canvas.width !== width) canvas.width = width;
      if (canvas.height !== height) canvas.height = height;

      const state = animState.current;
      const { vA, vB, vC, ruinScore, isZero } = coreState;
      const { e } = inputs;

      // --- 行動ロジック ---
      // A(元気)が高いほど速く、歩幅が大きい
      const speed = isZero ? 0 : (vA * 1.5 + 0.5);
      const maxStride = 40 + vA * 40; 
      const minStride = 20;
      
      // B(プレッシャー)が高いほど震える
      const jitter = vB * 4; 
      
      // C(考えすぎ)が高いほど待機時間が長い
      const thinkDuration = isZero ? Infinity : Math.max(0, (vC * 40) - 10);

      // フェーズ進行
      if (!isZero) {
        if (state.phase === 'THINK') {
          state.timer++;
          if (state.timer > thinkDuration) {
            state.phase = 'STRETCH';
            state.timer = 0;
          }
        } else if (state.phase === 'STRETCH') {
          state.headX += speed * 2;
          if (state.headX - state.tailX >= maxStride) {
            state.headX = state.tailX + maxStride;
            state.phase = 'CONTRACT';
          }
        } else if (state.phase === 'CONTRACT') {
          state.tailX += speed * 2;
          if (state.headX - state.tailX <= minStride) {
            state.tailX = state.headX - minStride;
            state.phase = 'THINK';
            state.timer = 0;
            state.totalDist += maxStride - minStride;
            // 画面中心に維持するため、相対位置をリセット
            const center = (state.headX + state.tailX) / 2;
            state.headX -= center;
            state.tailX -= center;
          }
        }
      }

      // --- 描画処理 ---
      ctx.clearRect(0, 0, width, height);
      
      // 背景（空）
      ctx.fillStyle = e > 1.0 ? '#4b5563' : (e > 0.5 ? '#9ca3af' : '#e0f2fe');
      ctx.fillRect(0, 0, width, height);

      // 地面
      const groundY = height - 50;
      ctx.fillStyle = e > 1.0 ? '#374151' : '#86efac';
      ctx.fillRect(0, groundY, width, 50);

      // スクロールする地面の模様
      ctx.fillStyle = e > 1.0 ? '#1f2937' : '#4ade80';
      const offset = -(state.totalDist + state.headX) % 40;
      for (let i = offset; i < width; i += 40) {
        ctx.fillRect(i, groundY, 20, 50);
      }

      // 雨(環境要因 e)
      if (e > 0) {
        if (Math.random() < e * 0.5) {
          state.raindrops.push({ x: Math.random() * width, y: 0, speed: 5 + Math.random() * 5 });
        }
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.6)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        for (let i = state.raindrops.length - 1; i >= 0; i--) {
          const drop = state.raindrops[i];
          ctx.moveTo(drop.x, drop.y);
          ctx.lineTo(drop.x - drop.speed * 0.2, drop.y + drop.speed);
          drop.y += drop.speed;
          drop.x -= drop.speed * 0.2;
          if (drop.y > height) state.raindrops.splice(i, 1);
        }
        ctx.stroke();
      }

      // しゃくとりむしの描画 (画面中央に固定して描画)
      const centerX = width / 2;
      const drawHeadX = centerX + state.headX + (Math.random() - 0.5) * jitter;
      const drawTailX = centerX + state.tailX + (Math.random() - 0.5) * jitter;
      const bodyLength = drawHeadX - drawTailX;
      
      // 体の色
      let bodyColor = '#4ade80'; // 通常
      if (isZero) bodyColor = '#991b1b'; // フリーズ
      else if (ruinScore >= 5) bodyColor = '#ef4444'; // パニック
      else if (ruinScore >= 3) bodyColor = '#f59e0b'; // 緊張

      // 体のアーチ(節)を描画
      const numSegments = 6;
      ctx.fillStyle = bodyColor;
      ctx.strokeStyle = 'rgba(0,0,0,0.1)';
      ctx.lineWidth = 2;

      for (let i = 0; i <= numSegments; i++) {
        const t = i / numSegments;
        const x = drawTailX + bodyLength * t;
        // 距離が短いほどアーチが高くなる
        const archHeight = Math.max(0, (maxStride - bodyLength) * 0.8);
        const y = groundY - 15 - Math.sin(t * Math.PI) * archHeight;
        
        ctx.beginPath();
        ctx.arc(x, y + (Math.random() - 0.5) * jitter, 15, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }

      // 顔の描画 (頭の節)
      const headY = groundY - 15 - Math.sin(1 * Math.PI) * 0; // t=1
      ctx.fillStyle = '#111827'; // 目の色
      
      const eyeOffsetX = 5;
      if (isZero) {
        // バッテン目 (X X)
        ctx.font = '14px sans-serif';
        ctx.fillText('x', drawHeadX + eyeOffsetX - 5, headY - 2);
        ctx.fillText('x', drawHeadX + eyeOffsetX + 5, headY - 2);
      } else if (ruinScore >= 4) {
        // 苦しい目 (> <)
        ctx.font = '12px sans-serif';
        ctx.fillText('>', drawHeadX + eyeOffsetX - 6, headY - 2);
        ctx.fillText('<', drawHeadX + eyeOffsetX + 4, headY - 2);
      } else if (state.phase === 'THINK' && vC > 1.0) {
        // 考え中 (キョロキョロ)
        const lookDir = Math.sin(Date.now() / 200) * 3;
        ctx.beginPath(); ctx.arc(drawHeadX + eyeOffsetX - 4 + lookDir, headY - 4, 2, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(drawHeadX + eyeOffsetX + 4 + lookDir, headY - 4, 2, 0, Math.PI * 2); ctx.fill();
      } else {
        // 通常目 (・ ・)
        ctx.beginPath(); ctx.arc(drawHeadX + eyeOffsetX - 4, headY - 4, 2, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(drawHeadX + eyeOffsetX + 4, headY - 4, 2, 0, Math.PI * 2); ctx.fill();
      }

      // 汗(プレッシャーが高い時)
      if (vB > 1.0 && !isZero) {
        ctx.fillStyle = '#60a5fa';
        ctx.beginPath();
        ctx.arc(drawHeadX - 10, headY - 10 + Math.sin(Date.now()/100)*2, 3, 0, Math.PI*2);
        ctx.fill();
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animationFrameId);
  }, [coreState, inputs]);

  // ステータスメッセージの生成
  let statusEmoji = '🐛';
  let statusText = 'のびのび進んでいるよ！';
  if (coreState.isZero) {
    statusEmoji = '💀'; statusText = 'ストレス限界…！動けなくなってしまった (フリーズ状態)';
  } else if (coreState.ruinScore >= 5) {
    statusEmoji = '🚨'; statusText = 'プレッシャーでパニック寸前！動きがバラバラだ！';
  } else if (coreState.vC >= 1.5) {
    statusEmoji = '🤔'; statusText = 'まわりを気にしすぎて、立ち止まってばかりいる…';
  } else if (coreState.vB >= 1.5) {
    statusEmoji = '💦'; statusText = 'プレッシャーで体がカクカク震えている…';
  } else if (inputs.e >= 1.5) {
    statusEmoji = '🌧️'; statusText = '雨が強くて進みづらい！元気が奪われていく…';
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col font-sans">
      {/* Header */}
      <header className="bg-white shadow-sm p-4 text-center">
        <h1 className="text-xl font-bold text-gray-800">🌱 ABCしゃくとりむし</h1>
        <p className="text-xs text-gray-500 mt-1">心の状態が動きに出るシミュレーター</p>
      </header>

      {/* Canvas Area */}
      <div className="w-full bg-white relative">
        <canvas ref={canvasRef} className="w-full block shadow-inner" />
        
        {/* ストレス・メーター (Ruin Score) */}
        <div className="absolute top-4 right-4 bg-white/90 p-2 rounded-lg shadow backdrop-blur-sm border border-gray-100">
          <div className="text-xs font-bold text-gray-600 mb-1">ストレス度 (RuinScore)</div>
          <div className="flex gap-1 h-3">
            {[1,2,3,4,5,6].map(level => (
              <div 
                key={level} 
                className={`w-4 rounded-sm transition-colors duration-300 ${
                  coreState.ruinScore >= level 
                    ? (level >= 5 ? 'bg-red-500' : level >= 3 ? 'bg-amber-400' : 'bg-green-400')
                    : 'bg-gray-200'
                }`}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Message Area */}
      <div className="bg-white border-b px-4 py-3">
        <div className={`p-3 rounded-xl border flex items-center gap-3 transition-colors duration-500 ${
          coreState.isZero ? 'bg-red-50 border-red-200 text-red-800' : 
          coreState.ruinScore >= 4 ? 'bg-amber-50 border-amber-200 text-amber-800' : 
          'bg-green-50 border-green-200 text-green-800'
        }`}>
          <span className="text-2xl">{statusEmoji}</span>
          <span className="text-sm font-medium">{statusText}</span>
        </div>
      </div>

      {/* Control Panel (Sliders) */}
      <div className="flex-1 p-4 overflow-y-auto pb-8">
        <div className="grid gap-6 max-w-md mx-auto">
          
          <Slider 
            label="🌱 じぶんの元気 (A)" 
            desc="本能的な進む力。高いとのびのび速く動く。"
            value={inputs.a} 
            onChange={(v) => handleChange('a', v)} 
            colorClass="accent-green-500"
          />
          
          <Slider 
            label="👀 まわりの目 (B)" 
            desc="プレッシャー。高いと動きがカクカクして震える。"
            value={inputs.b} 
            onChange={(v) => handleChange('b', v)} 
            colorClass="accent-blue-500"
          />
          
          <Slider 
            label="🤔 考えすぎ (C)" 
            desc="状況の客観視。高いと進む前に長く立ち止まる。"
            value={inputs.c} 
            onChange={(v) => handleChange('c', v)} 
            colorClass="accent-purple-500"
          />
          
          <div className="h-px bg-gray-200 my-2"></div>

          <Slider 
            label="🌧️ 環境のおじゃま (EF)" 
            desc="外部の悪天候。すべてのストレスを底上げする。"
            value={inputs.e} 
            onChange={(v) => handleChange('e', v)} 
            colorClass="accent-gray-600"
          />

        </div>
      </div>
    </div>
  );
}

// 再利用可能なスライダーコンポーネント
function Slider({ label, desc, value, onChange, colorClass }) {
  // 0: Low, 1: Mid, 2: High のラベル付け
  const getLabel = (val) => {
    if (val < 0.5) return '低い';
    if (val > 1.5) return '過剰!';
    return 'ふつう';
  };

  return (
    <div className="bg-white p-4 rounded-2xl shadow-sm border border-gray-100">
      <div className="flex justify-between items-end mb-2">
        <div>
          <label className="block text-sm font-bold text-gray-700">{label}</label>
          <p className="text-xs text-gray-400 mt-0.5">{desc}</p>
        </div>
        <span className="text-xs font-bold text-gray-500 bg-gray-100 px-2 py-1 rounded-md">
          {getLabel(value)} ({value.toFixed(1)})
        </span>
      </div>
      <input 
        type="range" 
        min="0" max="2" step="0.1" 
        value={value} 
        onChange={(e) => onChange(e.target.value)}
        className={`w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer ${colorClass}`}
      />
      <div className="flex justify-between text-[10px] text-gray-400 mt-1 px-1">
        <span>0.0</span>
        <span>1.0</span>
        <span>2.0</span>
      </div>
    </div>
  );
}