import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { FastForward, RotateCcw, TrendingUp, Sparkles } from 'lucide-react';

// --- CVM Core Logic Constants ---
const STATES = {
  BIRTH: 'Birth',
  GROWTH: 'Growth',
  MATURITY: 'Maturity',
  DECLINE: 'Decline',
  DEATH: 'Death'
};

const STATE_JP = {
  [STATES.BIRTH]: '赤ちゃん',
  [STATES.GROWTH]: '育ちざかり',
  [STATES.MATURITY]: '一人前',
  [STATES.DECLINE]: 'お疲れ気味',
  [STATES.DEATH]: '旅立ち（胞子）'
};

const L_MAX_BASE = 1000;
const TICK_RATE = 50; // ms

const App = () => {
  const [cycle, setCycle] = useState(1);
  const [state, setState] = useState(STATES.BIRTH);
  const [velocity, setVelocity] = useState(3);
  const [accumulation, setAccumulation] = useState(0);
  const [lMax, setLMax] = useState(L_MAX_BASE);
  const [evolutionBonus, setEvolutionBonus] = useState(0);
  const [isDead, setIsDead] = useState(false);

  const progress = Math.min((accumulation / lMax) * 100, 100);

  // --- CVM Logic ---
  useEffect(() => {
    if (isDead) return;

    const timer = setInterval(() => {
      setAccumulation(prev => {
        const nextVal = prev + (velocity * 0.5) + (evolutionBonus * 0.1);
        
        if (nextVal >= lMax) {
          setIsDead(true);
          setState(STATES.DEATH);
          setVelocity(10);
          return lMax;
        }
        
        const p = (nextVal / lMax) * 100;
        if (p < 15) setState(STATES.BIRTH);
        else if (p < 45) setState(STATES.GROWTH);
        else if (p < 75) setState(STATES.MATURITY);
        else setState(STATES.DECLINE);
        
        return nextVal;
      });
    }, TICK_RATE);

    return () => clearInterval(timer);
  }, [velocity, isDead, evolutionBonus, lMax]);

  const handleRebirth = useCallback(() => {
    setEvolutionBonus(prev => prev + 1.0);
    setLMax(prev => prev * 1.3);
    setAccumulation(0);
    setState(STATES.BIRTH);
    setVelocity(3);
    setIsDead(false);
    setCycle(prev => prev + 1);
  }, []);

  // 動的なアニメーション速度の計算
  const walkDuration = useMemo(() => `${(11 - velocity) * 0.12}s`, [velocity]);
  const bobDuration = useMemo(() => `${(11 - velocity) * 0.06}s`, [velocity]);
  const leanAngle = useMemo(() => `${velocity * 2}deg`, [velocity]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 p-4 flex flex-col items-center select-none overflow-x-hidden">
      
      {/* Header */}
      <div className="w-full max-w-md flex justify-between items-center mb-6 pt-4 px-2">
        <div className="flex flex-col">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Generation</span>
          <span className="text-2xl font-black text-indigo-600">{cycle}代め</span>
        </div>
        <div className="bg-white shadow-sm border border-slate-200 px-3 py-1 rounded-full flex items-center gap-1">
          <Sparkles size={14} className="text-amber-500" />
          <span className="text-sm font-bold">進歩: +{evolutionBonus.toFixed(1)}</span>
        </div>
      </div>

      {/* Main Visual Stage */}
      <div className="relative w-full max-w-md aspect-square bg-gradient-to-b from-sky-100 to-emerald-50 rounded-[3rem] shadow-inner border-4 border-white overflow-hidden flex items-center justify-center">
        
        {/* Shadow */}
        {!isDead && (
          <div 
            className="absolute bottom-[22%] w-24 h-4 bg-black/10 rounded-[100%] blur-md"
            style={{ animation: `shadow-pulse ${bobDuration} infinite alternate ease-in-out` }}
          />
        )}

        {/* Character Container */}
        <div 
          className="relative z-10"
          style={{ 
            transform: `scale(${0.8 + (progress / 200)}) rotate(${isDead ? '0deg' : leanAngle})`,
            transition: 'transform 0.5s ease-out'
          }}
        >
          {/* Bobbing Logic */}
          <div 
            style={{ 
              animation: isDead 
                ? 'ghost-float 3s infinite ease-in-out' 
                : `mushroom-jump ${bobDuration} infinite alternate ease-in-out` 
            }}
          >
            
            {/* Mushroom Head */}
            <div className={`text-8xl filter drop-shadow-2xl relative z-20 ${isDead ? 'opacity-60' : ''}`}>
              {isDead ? '👻' : '🍄'}
            </div>

            {/* まるっこい足 */}
            {!isDead && (
              <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 w-16 h-10 flex justify-around pointer-events-none">
                {/* Left Leg */}
                <div 
                  className="relative w-4 h-6 origin-top"
                  style={{ animation: `leg-swing-main ${walkDuration} infinite ease-in-out` }}
                >
                  <div className="w-full h-full bg-amber-800 rounded-full"></div>
                </div>

                {/* Right Leg */}
                <div 
                  className="relative w-4 h-6 origin-top"
                  style={{ 
                    animation: `leg-swing-main ${walkDuration} infinite ease-in-out`, 
                    animationDelay: `calc(${walkDuration} / -2)` 
                  }}
                >
                  <div className="w-full h-full bg-amber-800 rounded-full"></div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Status Badge */}
        <div className="absolute top-6 left-6 bg-white/90 backdrop-blur-md px-4 py-2 rounded-2xl border border-white shadow-lg">
          <p className="text-[10px] text-slate-400 font-bold uppercase mb-0.5 tracking-tighter">Status</p>
          <p className="text-lg font-black text-slate-800 tracking-tight">{STATE_JP[state]}</p>
        </div>
      </div>

      {/* Controls */}
      <div className="w-full max-w-md mt-8 space-y-6 px-2">
        {/* Progress Bar */}
        <div className="space-y-2">
          <div className="flex justify-between items-end px-1">
            <span className="text-sm font-bold text-slate-600 flex items-center gap-2">
              <TrendingUp size={16} className="text-indigo-400" />
              経験値（累積量）
            </span>
            <span className="text-xs font-mono text-slate-400 bg-slate-100 px-2 py-0.5 rounded-md">
              {Math.floor(accumulation).toLocaleString()} / {Math.floor(lMax).toLocaleString()}
            </span>
          </div>
          <div className="h-4 w-full bg-slate-200 rounded-full overflow-hidden p-0.5 shadow-inner border border-white">
            <div 
              className={`h-full rounded-full transition-all duration-300 ${isDead ? 'bg-amber-400' : 'bg-indigo-500 shadow-[0_0_10px_rgba(79,70,229,0.3)]'}`}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Simple Velocity Slider (Original Design) */}
        <div className={`p-6 rounded-[2rem] bg-white shadow-sm border border-slate-200 transition-all duration-500 ${isDead ? 'opacity-30 grayscale pointer-events-none' : ''}`}>
          <div className="flex justify-between items-center mb-5">
            <span className="font-black text-slate-700 flex items-center gap-2 tracking-tight">
              <FastForward size={20} className="text-indigo-500" />
              歩く元気
            </span>
            <div className="bg-indigo-50 px-3 py-1 rounded-xl">
              <span className="text-2xl font-black text-indigo-600">Lv.{velocity}</span>
            </div>
          </div>
          <input 
            type="range" min="1" max="10" 
            value={velocity} 
            onChange={(e) => !isDead && setVelocity(parseInt(e.target.value))}
            className="w-full h-3 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-indigo-600"
          />
          <div className="flex justify-between mt-2 px-1">
            <span className="text-[10px] font-bold text-slate-300 italic uppercase">Slow</span>
            <span className="text-[10px] font-bold text-slate-300 italic uppercase">Fast</span>
          </div>
        </div>

        {/* Action Button */}
        {isDead && (
          <button 
            onClick={handleRebirth}
            className="w-full py-6 bg-indigo-600 text-white rounded-[2rem] font-black text-xl shadow-2xl animate-pulse flex items-center justify-center gap-3 transition-transform active:scale-95"
          >
            <RotateCcw />
            次の代へ進化する
          </button>
        )}
      </div>

      <style>{`
        @keyframes mushroom-jump {
          0% { transform: translateY(0); }
          100% { transform: translateY(-18px); }
        }
        @keyframes shadow-pulse {
          0% { transform: scale(1.1); opacity: 0.15; }
          100% { transform: scale(0.6); opacity: 0.05; }
        }
        @keyframes leg-swing-main {
          0% { transform: rotate(40deg) translateY(0); }
          50% { transform: rotate(-40deg) translateY(-4px); }
          100% { transform: rotate(40deg) translateY(0); }
        }
        @keyframes ghost-float {
          0%, 100% { transform: translateY(0) rotate(0deg); }
          50% { transform: translateY(-30px) rotate(10deg); }
        }
        input[type='range']::-webkit-slider-thumb {
          -webkit-appearance: none;
          height: 24px; width: 24px;
          border-radius: 50%; background: #4f46e5;
          border: 4px solid white; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
          cursor: pointer;
        }
      `}</style>
    </div>
  );
};

export default App;