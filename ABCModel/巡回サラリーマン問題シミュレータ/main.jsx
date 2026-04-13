import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Play, Pause, RotateCcw, MapPin, Coffee, TreePine, Building2, Briefcase, AlertTriangle } from 'lucide-react';

// --- ABCモデル 簡易計算エンジン ---
const MAX_V = 100;

const applyABCModel = (currentState, externalFactors) => {
  // undefinedガード
  const ef = externalFactors || { e0: 0, e1: 0, e2: 0, e3: 0 };
  let { a, b, c, ruin } = currentState;
  const { e0, e1, e2, e3 } = ef;

  // 1. 外部要因(EF)の投影
  let nextA = a - (e0 * 0.5) + (e1 * 2); 
  let nextB = b + (e2 * 2.5);
  let nextC = c + (e3 * 1.5) + (e0 * 0.2);

  // 2. 相互作用 I
  if (nextC > 60) nextA -= (nextC - 60) * 0.3;
  if (nextB > 50) nextC += (nextB - 50) * 0.2;
  if (nextA > 60) nextB -= (nextA - 60) * 0.4;

  // 自然減衰・回復
  nextA = nextA + (50 - nextA) * 0.05;
  nextB = nextB + (0 - nextB) * 0.05;
  nextC = nextC + (0 - nextC) * 0.1;

  // Clamp
  nextA = Math.max(0, Math.min(MAX_V, nextA));
  nextB = Math.max(0, Math.min(MAX_V, nextB));
  nextC = Math.max(0, Math.min(MAX_V, nextC));

  // 3. RuinScoreの算出
  let baseRuin = Math.max(0, (100 - nextA)*0.5, nextB*0.8, nextC);
  if (nextB > 80 && nextC > 80) baseRuin += 30;
  
  let nextRuin = Math.max(0, Math.min(100, baseRuin));

  return { a: nextA, b: nextB, c: nextC, ruin: nextRuin };
};

// --- マップデータ定義 ---
const NODES = {
  start: { id: 'start', x: 10, y: 50, name: '自社', icon: Building2, color: 'text-gray-600', ef: { e0: 0, e1: 0, e2: 0, e3: 0 } },
  client1: { id: 'client1', x: 30, y: 20, name: '顧客A (通常)', icon: Briefcase, color: 'text-blue-600', ef: { e0: 1, e1: 0, e2: 2, e3: 1 } },
  client2: { id: 'client2', x: 60, y: 80, name: '顧客B (激怒)', icon: AlertTriangle, color: 'text-red-600', ef: { e0: 2, e1: 0, e2: 6, e3: 5 } },
  client3: { id: 'client3', x: 80, y: 30, name: '顧客C (重鎮)', icon: Briefcase, color: 'text-purple-600', ef: { e0: 1, e1: 0, e2: 4, e3: 2 } },
  cafe: { id: 'cafe', x: 45, y: 50, name: '純喫茶', icon: Coffee, color: 'text-amber-700', ef: { e0: -2, e1: 8, e2: -2, e3: -2 } },
  park: { id: 'park', x: 70, y: 55, name: '公園', icon: TreePine, color: 'text-green-600', ef: { e0: -1, e1: 5, e2: -3, e3: -5 } },
};

const ROUTES = {
  shortest: {
    id: 'shortest',
    name: '物理的最短ルート (効率重視)',
    desc: '移動距離は短いが、連続するストレス(E2/E3)で評価圧(B)と監視(C)が暴走し、メンタル崩壊の危機。',
    path: ['start', 'client1', 'client3', 'client2', 'start']
  },
  mental: {
    id: 'mental',
    name: 'ABC最適化ルート (メンタル保護)',
    desc: '移動距離は長いが、間にカフェや公園(E1)を挟むことで生感(A)を維持し、Bの暴走を抑制(A→B=-1)する真の最適解。',
    path: ['start', 'client1', 'cafe', 'client3', 'park', 'client2', 'start']
  }
};

export default function App() {
  const [activeRouteId, setActiveRouteId] = useState('shortest');
  const [progress, setProgress] = useState(0); 
  const [isPlaying, setIsPlaying] = useState(false);
  const animationRef = useRef(null);

  const activeRoute = ROUTES[activeRouteId];
  const pathNodes = useMemo(() => activeRoute.path.map(id => NODES[id]), [activeRoute]);

  // 進捗に応じた状態計算
  const currentStatus = useMemo(() => {
    let state = { a: 80, b: 10, c: 10, ruin: 0 };
    const totalSteps = pathNodes.length - 1;
    if (totalSteps <= 0) return state;

    // 現在のステップと区間内進捗
    const currentGlobalStep = (progress / 100) * totalSteps;
    const currentIndex = Math.floor(currentGlobalStep);
    // 小数点誤差を考慮し、範囲を0-1に限定
    const stepProgress = Math.min(1, Math.max(0, currentGlobalStep - currentIndex));

    // 1. 過去の確定済み区間の累積影響
    for (let i = 0; i < currentIndex; i++) {
      state = applyABCModel(state, pathNodes[i].ef); // 立ち寄り
      state = applyABCModel(state, { e0: 2, e1: 0, e2: 0, e3: 0 }); // 区間移動負荷
    }

    // 2. 現在滞在中のノード、または移動開始直後の衝撃
    const activeNode = pathNodes[currentIndex];
    if (activeNode) {
       state = applyABCModel(state, activeNode.ef);
    }

    // 3. 現在移動中の区間でのリアルタイム負荷
    if (currentIndex < totalSteps && stepProgress > 0) {
      state = applyABCModel(state, { e0: 1 * stepProgress, e1: 0, e2: 0, e3: 0 });
    }

    return state;
  }, [progress, pathNodes]);

  // サラリーマンの現在位置計算
  const currentPosition = useMemo(() => {
    const totalSteps = pathNodes.length - 1;
    if (progress >= 100 || totalSteps <= 0) {
      const goal = pathNodes[totalSteps];
      return { x: goal?.x || 0, y: goal?.y || 0 };
    }
    
    const currentGlobalStep = (progress / 100) * totalSteps;
    const currentIndex = Math.min(Math.floor(currentGlobalStep), totalSteps - 1);
    const stepProgress = Math.min(1, Math.max(0, currentGlobalStep - currentIndex));
    
    const startNode = pathNodes[currentIndex];
    const endNode = pathNodes[currentIndex + 1];
    
    if (!startNode || !endNode) return { x: 0, y: 0 };
    
    return {
      x: startNode.x + (endNode.x - startNode.x) * stepProgress,
      y: startNode.y + (endNode.y - startNode.y) * stepProgress
    };
  }, [progress, pathNodes]);

  // アニメーションループ
  useEffect(() => {
    if (isPlaying) {
      let lastTime = performance.now();
      const animate = (time) => {
        const deltaTime = time - lastTime;
        setProgress((prev) => {
          const nextProgress = prev + (deltaTime * 0.005);
          if (nextProgress >= 100) {
            setIsPlaying(false);
            return 100;
          }
          return nextProgress;
        });
        lastTime = time;
        animationRef.current = requestAnimationFrame(animate);
      };
      animationRef.current = requestAnimationFrame(animate);
    } else {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    }
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [isPlaying]);

  const handleRouteSwitch = (routeId) => {
    setIsPlaying(false);
    setActiveRouteId(routeId);
    setProgress(0);
  };

  // メーター描画コンポーネント
  const Meter = ({ label, value, colorClass, desc, isReversed = false }) => {
    const displayValue = Math.round(value || 0);
    const isDanger = isReversed ? displayValue < 30 : displayValue > 70;
    
    return (
      <div className="mb-4">
        <div className="flex justify-between text-sm mb-1">
          <span className="font-bold flex items-center gap-2 text-slate-700">
            {label}
            {isDanger && <AlertTriangle size={14} className="text-red-500 animate-pulse" />}
          </span>
          <span className="text-slate-500 font-mono">{displayValue}</span>
        </div>
        <div className="w-full bg-slate-200 rounded-full h-3 overflow-hidden">
          <div 
            className={`h-3 rounded-full transition-all duration-300 ease-out ${colorClass}`} 
            style={{ width: `${displayValue}%` }}
          />
        </div>
        <p className="text-[10px] text-slate-500 mt-1 leading-tight">{desc}</p>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-slate-50 p-4 md:p-8 font-sans text-slate-800">
      <div className="max-w-6xl mx-auto space-y-6">
        
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
          <h1 className="text-2xl font-bold mb-2 flex items-center gap-2 text-slate-900">
            <Briefcase className="text-slate-700" />
            巡回サラリーマン問題シミュレータ
          </h1>
          <p className="text-slate-600 text-sm">
            「物理的な最短距離」が本当に最適なのか？ABC感情モデル(Core v3.2.0)を用いて、
            サラリーマンの内部状態（生感、評価圧、監視認知）の相互作用を可視化します。
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-white rounded-2xl p-4 shadow-sm border border-slate-200 relative h-[420px] w-full overflow-hidden">
              <div className="absolute inset-0 bg-[linear-gradient(to_right,#f8fafc_1px,transparent_1px),linear-gradient(to_bottom,#f8fafc_1px,transparent_1px)] bg-[size:20px_20px]" />
              
              <svg className="w-full h-full absolute inset-0 pointer-events-none" preserveAspectRatio="none">
                <polyline
                  points={pathNodes.map(n => `${n.x}%, ${n.y}%`).join(' ')}
                  fill="none"
                  stroke="#e2e8f0"
                  strokeWidth="4"
                  strokeDasharray="8 8"
                />
                
                {progress > 0 && (
                  <path
                    d={`M ${pathNodes[0].x}% ${pathNodes[0].y}% ` + 
                       pathNodes.slice(1).map((n, i) => {
                         const step = (i + 1) * (100 / (pathNodes.length - 1));
                         if (progress >= step) return `L ${n.x}% ${n.y}%`;
                         return '';
                       }).join(' ') + 
                       (progress < 100 ? `L ${currentPosition.x}% ${currentPosition.y}%` : '')
                    }
                    fill="none"
                    stroke={activeRouteId === 'shortest' ? '#f43f5e' : '#0ea5e9'}
                    strokeWidth="6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="transition-all duration-100"
                  />
                )}
              </svg>

              {Object.values(NODES).map((node) => {
                const Icon = node.icon;
                const isTarget = activeRoute.path.includes(node.id);
                return (
                  <div
                    key={node.id}
                    className={`absolute transform -translate-x-1/2 -translate-y-1/2 flex flex-col items-center transition-opacity duration-300 ${isTarget ? 'opacity-100' : 'opacity-20'}`}
                    style={{ left: `${node.x}%`, top: `${node.y}%` }}
                  >
                    <div className={`p-3 rounded-full bg-white shadow-lg border-2 ${node.color.replace('text-', 'border-')} z-10`}>
                      <Icon size={20} className={node.color} />
                    </div>
                    <span className="mt-2 text-[10px] font-bold bg-white/90 px-2 py-0.5 rounded shadow-sm border border-slate-100 backdrop-blur-sm whitespace-nowrap">
                      {node.name}
                    </span>
                  </div>
                );
              })}

              <div 
                className="absolute transform -translate-x-1/2 -translate-y-1/2 z-20 transition-all duration-75"
                style={{ left: `${currentPosition.x}%`, top: `${currentPosition.y}%` }}
              >
                <div className="relative">
                  <div className={`w-12 h-12 rounded-full flex items-center justify-center shadow-xl border-4 bg-white
                    ${currentStatus.ruin > 70 ? 'border-red-500 animate-bounce' : 'border-slate-800'}`}>
                    <span className="text-2xl">{currentStatus.ruin > 70 ? '🥵' : currentStatus.ruin > 40 ? '😰' : '😐'}</span>
                  </div>
                  {currentStatus.ruin > 80 && (
                    <span className="absolute -top-10 left-1/2 -translate-x-1/2 text-[10px] font-black bg-red-600 text-white px-3 py-1 rounded-full animate-pulse shadow-lg whitespace-nowrap">
                      RUNAWAY (暴走中)
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200">
              <div className="flex flex-wrap gap-4 mb-6">
                <button
                  onClick={() => handleRouteSwitch('shortest')}
                  className={`flex-1 py-3 px-4 rounded-xl font-bold transition-all border-2 ${
                    activeRouteId === 'shortest' 
                      ? 'bg-red-50 text-red-700 border-red-200 shadow-inner' 
                      : 'bg-white text-slate-400 border-slate-100 hover:bg-slate-50 hover:text-slate-600'
                  }`}
                >
                  最短距離ルート
                </button>
                <button
                  onClick={() => handleRouteSwitch('mental')}
                  className={`flex-1 py-3 px-4 rounded-xl font-bold transition-all border-2 ${
                    activeRouteId === 'mental' 
                      ? 'bg-sky-50 text-sky-700 border-sky-200 shadow-inner' 
                      : 'bg-white text-slate-400 border-slate-100 hover:bg-slate-50 hover:text-slate-600'
                  }`}
                >
                  ABC最適化ルート
                </button>
              </div>
              
              <div className="text-xs text-slate-500 mb-6 bg-slate-50 p-4 rounded-xl border border-slate-100 italic">
                <span className="font-bold text-slate-700 not-italic">Strategy: </span>{activeRoute.desc}
              </div>

              <div className="flex items-center gap-6">
                <div className="flex gap-2">
                  <button 
                    onClick={() => setIsPlaying(!isPlaying)}
                    className="w-12 h-12 flex items-center justify-center bg-slate-900 text-white rounded-full hover:bg-slate-800 transition-transform active:scale-95 shadow-md"
                  >
                    {isPlaying ? <Pause size={20} fill="currentColor" /> : <Play size={20} className="ml-1" fill="currentColor" />}
                  </button>
                  <button 
                    onClick={() => { setProgress(0); setIsPlaying(false); }}
                    className="w-12 h-12 flex items-center justify-center bg-slate-100 text-slate-600 rounded-full hover:bg-slate-200 transition-transform active:scale-95 shadow-sm"
                  >
                    <RotateCcw size={20} />
                  </button>
                </div>
                
                <div className="flex-1">
                  <input 
                    type="range" 
                    min="0" 
                    max="100" 
                    step="0.1"
                    value={progress}
                    onChange={(e) => {
                      setProgress(Number(e.target.value));
                      setIsPlaying(false);
                    }}
                    className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-slate-800"
                  />
                  <div className="flex justify-between text-[10px] text-slate-400 mt-2 font-mono tracking-tighter uppercase font-bold">
                    <span>Departure</span>
                    <span className="text-slate-600">Sync: {Math.round(progress)}%</span>
                    <span>Arrived</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200 h-full">
              <h2 className="text-sm font-black text-slate-900 uppercase tracking-widest border-b border-slate-100 pb-4 mb-6 flex items-center gap-2">
                Internal Dashboard
              </h2>

              <Meter 
                label="A: Authenticity (生感)" 
                value={currentStatus.a} 
                colorClass="bg-emerald-500"
                desc="体感・自然反応。休息や環境(E1)で回復。"
                isReversed={true}
              />
              
              <Meter 
                label="B: Aesthetic (評価圧)" 
                value={currentStatus.b} 
                colorClass="bg-sky-500"
                desc="比較・基準。社会圧(E2)で上昇。"
              />

              <Meter 
                label="C: Meta (監視認知)" 
                value={currentStatus.c} 
                colorClass="bg-violet-500"
                desc="俯瞰・監視。Bに釣られて上昇し、Aを抑制。"
              />

              <div className="mt-8 pt-6 border-t border-slate-100">
                <div className="flex items-end justify-between mb-2">
                  <span className="font-black text-xs text-slate-900 uppercase tracking-tighter">
                    Ruin Score
                  </span>
                  <span className={`text-3xl font-black font-mono ${currentStatus.ruin > 80 ? 'text-red-600' : currentStatus.ruin > 40 ? 'text-orange-500' : 'text-slate-900'}`}>
                    {(currentStatus.ruin / 16.6).toFixed(1)}
                  </span>
                </div>
                
                <div className="w-full bg-slate-100 rounded-full h-8 p-1 overflow-hidden relative border border-slate-100">
                  <div 
                    className={`h-full rounded-full transition-all duration-300 ease-out flex items-center justify-end
                      ${currentStatus.ruin < 40 ? 'bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.5)]' : 
                        currentStatus.ruin < 80 ? 'bg-orange-400 shadow-[0_0_10px_rgba(251,146,60,0.5)]' : 
                        'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]'}`}
                    style={{ width: `${Math.max(8, currentStatus.ruin)}%` }}
                  />
                  <div className="absolute inset-0 flex justify-between px-2 items-center pointer-events-none opacity-20">
                    {[1,2,3,4,5].map(i => <div key={i} className="h-4 w-px bg-slate-900" />)}
                  </div>
                </div>
                <div className="mt-4 p-4 rounded-xl bg-slate-50 border border-slate-100">
                   <p className="text-[10px] font-bold text-slate-800 uppercase mb-1 flex items-center gap-1">
                     <AlertTriangle size={10} className="text-orange-500" /> Interaction Logic
                   </p>
                   <ul className="text-[10px] text-slate-500 space-y-1 font-medium">
                     <li className={currentStatus.c > 60 ? "text-red-500" : ""}>• C → A (-1): 監視が強いと生感が低下</li>
                     <li className={currentStatus.b > 50 ? "text-red-500" : ""}>• B → C (+1): 評価圧が監視を誘発</li>
                     <li className={currentStatus.a > 60 ? "text-emerald-600" : ""}>• A → B (-1): 生感が評価を無効化</li>
                   </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}