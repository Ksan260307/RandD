import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { FastForward, RotateCcw, TrendingUp, Sparkles, BatteryWarning, CloudSun, CloudRain, Sun, Target, Activity, Cpu } from 'lucide-react';

// --- CVM Core Logic Constants ---
const STATES = {
  BIRTH: 'Birth',
  GROWTH: 'Growth',
  MATURITY: 'Maturity',
  MUTATION: 'Mutation', 
  DECLINE: 'Decline',
  DEATH: 'Death'
};

const STATE_JP = {
  [STATES.BIRTH]: '赤ちゃん',
  [STATES.GROWTH]: '育ちざかり',
  [STATES.MATURITY]: '一人前',
  [STATES.MUTATION]: '突然変異 (X)',
  [STATES.DECLINE]: 'お疲れ気味',
  [STATES.DEATH]: '旅立ち（最大化）'
};

const STATE_MULT = {
  [STATES.BIRTH]: 0.8,
  [STATES.GROWTH]: 1.5,
  [STATES.MATURITY]: 1.1,
  [STATES.MUTATION]: 3.0, 
  [STATES.DECLINE]: 0.5,
  [STATES.DEATH]: 0
};

const REC_VELOCITY = {
  [STATES.BIRTH]: '2〜4 (無理せず)',
  [STATES.GROWTH]: '6〜9 (ぐんぐん)',
  [STATES.MATURITY]: '4〜6 (安定)',
  [STATES.MUTATION]: 'MAX!! (全力!!)', 
  [STATES.DECLINE]: '1〜3 (ゆっくり)'
};

const WEATHER = {
  SUNNY: { id: 'Sunny', icon: Sun, color: 'text-amber-500', name: '快晴', mult: 1.2, desc: '成長しやすい' },
  CLOUDY: { id: 'Cloudy', icon: CloudSun, color: 'text-slate-500', name: 'くもり', mult: 1.0, desc: 'おだやか' },
  RAINY: { id: 'Rainy', icon: CloudRain, color: 'text-blue-500', name: '雨', mult: 0.8, desc: '疲れやすい' }
};

const L_MAX_BASE = 1000;
const TICK_RATE = 50;

// 円環描画用の定数
const RING_RADIUS = 120;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

const App = () => {
  const [cycle, setCycle] = useState(1);
  const [state, setState] = useState(STATES.BIRTH);
  const [velocity, setVelocity] = useState(3);
  const [accumulation, setAccumulation] = useState(0);
  const [displayAcc, setDisplayAcc] = useState(0); 
  const [lMax, setLMax] = useState(L_MAX_BASE);
  const [evolutionBonus, setEvolutionBonus] = useState(0);
  const [isDead, setIsDead] = useState(false);
  const [weather, setWeather] = useState(WEATHER.SUNNY);
  const [history, setHistory] = useState([]);
  
  const [isMutated, setIsMutated] = useState(false); 
  const [isAutoMode, setIsAutoMode] = useState(false); 
  
  const [eventMessage, setEventMessage] = useState(null);
  const [clicks, setClicks] = useState([]);
  const startTimeRef = useRef(Date.now());

  const progress = Math.min((accumulation / lMax) * 100, 100);
  const ringOffset = RING_CIRCUMFERENCE - (progress / 100) * RING_CIRCUMFERENCE;

  // --- 表示用数値の滑らかな追従 ---
  useEffect(() => {
    let animationFrameId;
    const animateValue = () => {
      setDisplayAcc(prev => {
        const diff = accumulation - prev;
        if (Math.abs(diff) < 0.5) return accumulation;
        return prev + diff * 0.1;
      });
      animationFrameId = requestAnimationFrame(animateValue);
    };
    animateValue();
    return () => cancelAnimationFrame(animationFrameId);
  }, [accumulation]);

  // --- 0. 環境要因 (E) の変化 ---
  useEffect(() => {
    if (isDead) return;
    const weatherTimer = setInterval(() => {
      const rand = Math.random();
      if (rand < 0.35) setWeather(WEATHER.SUNNY);
      else if (rand < 0.65) setWeather(WEATHER.CLOUDY);
      else setWeather(WEATHER.RAINY);
    }, 12000);
    return () => clearInterval(weatherTimer);
  }, [isDead]);

  // --- メッセージクリアタイマー ---
  useEffect(() => {
    if (eventMessage) {
      const timer = setTimeout(() => setEventMessage(null), 2500);
      return () => clearTimeout(timer);
    }
  }, [eventMessage]);

  // --- 1. 状態遷移（State Machine） ---
  useEffect(() => {
    if (isDead) return;
    
    if (progress >= 100) {
      setIsDead(true);
      setState(STATES.DEATH);
      setVelocity(10);
      setAccumulation(lMax);
    } else if (progress < 15) {
      setState(STATES.BIRTH);
    } else if (progress < 45) {
      setState(STATES.GROWTH);
    } else if (progress < 75) {
      setState(isMutated ? STATES.MUTATION : STATES.MATURITY);
    } else {
      setState(STATES.DECLINE);
    }
  }, [progress, isDead, lMax, isMutated]);

  // --- オートドライブ機構 (CVM Auto-Optimizer) ---
  useEffect(() => {
    if (!isAutoMode || isDead) return;
    const autoTimer = setInterval(() => {
      let targetV = velocity;
      switch (state) {
        case STATES.BIRTH: targetV = 3; break;
        case STATES.GROWTH: targetV = 8; break;
        case STATES.MATURITY: targetV = 5; break;
        case STATES.MUTATION: targetV = 10; break;
        case STATES.DECLINE: targetV = 2; break;
        default: break;
      }
      
      if (velocity !== targetV) {
        setVelocity(v => v < targetV ? v + 1 : v - 1);
      }
    }, 800);
    return () => clearInterval(autoTimer);
  }, [isAutoMode, isDead, state, velocity]);

  // --- 2. 累積とベロシティの自動更新 ---
  useEffect(() => {
    if (isDead) return;

    const timer = setInterval(() => {
      const efficiency = STATE_MULT[state] * weather.mult;
      const growthDelta = ((velocity * 0.6) + (evolutionBonus * 0.15)) * efficiency;
      
      setAccumulation(prev => prev + growthDelta);
      
      const rand = Math.random();
      
      if (state === STATES.DECLINE) {
        const dropChance = weather.id === 'Rainy' ? 0.25 : 0.1;
        if (rand < dropChance) {
          setVelocity(prevV => Math.max(1, prevV - 1));
        }
      } else {
        if (rand < 0.015 && velocity < 10) {
          setVelocity(prevV => Math.min(10, prevV + 1));
          setEventMessage("💨 気まぐれに加速！");
        } else if (rand > 0.985 && velocity > 1) {
          setVelocity(prevV => Math.max(1, prevV - 1));
          setEventMessage("💦 ちょっと一息…");
        }
      }
    }, TICK_RATE);

    return () => clearInterval(timer);
  }, [velocity, isDead, evolutionBonus, state, weather]);

  // --- 3. 再誕と進化の多様性判定（Rebirth） ---
  const handleRebirth = useCallback(() => {
    const lifespan = Math.floor((Date.now() - startTimeRef.current) / 1000);
    
    let typeName = "標準的な命";
    let bonusDelta = 1.0;
    let lMaxMult = 1.35;

    if (isMutated) {
      typeName = "突然変異体 🧬";
      bonusDelta = 2.0;
      lMaxMult = 1.2;
    } else if (lifespan < 20) {
      typeName = "駆け抜けた命 ⚡️";
      bonusDelta = 1.5;
      lMaxMult = 1.15;
    } else if (lifespan > 50) {
      typeName = "のんびり屋 🐢";
      bonusDelta = 0.5;
      lMaxMult = 1.6;
    } else if (evolutionBonus > 3) {
      typeName = "エリートきのこ ✨";
      bonusDelta = 1.2;
      lMaxMult = 1.4;
    }

    setHistory(prev => [{ 
      cycle, 
      lMax, 
      bonus: evolutionBonus, 
      weather: weather.name,
      time: lifespan,
      type: typeName
    }, ...prev].slice(0, 3));
    
    const newBonus = evolutionBonus + bonusDelta;
    setEvolutionBonus(newBonus);
    setLMax(prev => prev * lMaxMult);
    setAccumulation(0);
    setState(STATES.BIRTH);
    setVelocity(Math.min(3 + Math.floor(newBonus / 2), 6));
    
    const mutationChance = Math.min(0.05 + (newBonus * 0.01), 0.15);
    setIsMutated(Math.random() < mutationChance);
    
    setIsDead(false);
    setCycle(prev => prev + 1);
    setEventMessage(null);
    startTimeRef.current = Date.now();
  }, [cycle, lMax, evolutionBonus, weather, isMutated]);

  // --- 応援タップ機能 ---
  const handleTap = useCallback((e) => {
    if (isDead) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const id = Date.now() + Math.random();
    
    setClicks(prev => [...prev, { id, x, y }]);
    setAccumulation(prev => prev + (lMax * 0.005)); 
    
    if (Math.random() < 0.15 && velocity < 10) {
       setVelocity(v => Math.min(10, v + 1));
    }
    
    setTimeout(() => {
      setClicks(prev => prev.filter(c => c.id !== id));
    }, 800);
  }, [isDead, lMax, velocity]);

  // --- 4. 視覚的表現 ---
  const stateSpeedMultiplier = useMemo(() => {
    if (state === STATES.BIRTH) return 0.8;
    if (state === STATES.DECLINE) return 1.4;
    if (state === STATES.MUTATION) return 0.5;
    return 1.0;
  }, [state]);

  const walkDuration = useMemo(() => `${(11 - velocity) * 0.12 * stateSpeedMultiplier}s`, [velocity, stateSpeedMultiplier]);
  const bobDuration = useMemo(() => `${(11 - velocity) * 0.06 * stateSpeedMultiplier}s`, [velocity, stateSpeedMultiplier]);
  const leanAngle = useMemo(() => `${velocity * 2}deg`, [velocity]);
  
  const mushroomColorFilter = useMemo(() => {
    if (state === STATES.MUTATION) return `hue-rotate(${Date.now() % 360}deg) saturate(200%) brightness(1.2) contrast(1.2)`;
    return `hue-rotate(${cycle * 45}deg) saturate(${100 + (cycle * 5)}%)`;
  }, [cycle, state, displayAcc]);

  // 天候による背景グラデーションの切り替え
  const weatherBackgroundClass = useMemo(() => {
    if (isDead) return 'from-amber-100 to-orange-50';
    switch (weather.id) {
      case 'Sunny': return 'from-sky-200 to-emerald-100';
      case 'Cloudy': return 'from-slate-300 to-slate-200';
      case 'Rainy': return 'from-slate-600 to-slate-400';
      default: return 'from-sky-100 to-emerald-50';
    }
  }, [weather.id, isDead]);

  const WeatherIcon = weather.icon;
  const currentEfficiency = useMemo(() => (STATE_MULT[state] * weather.mult).toFixed(1), [state, weather]);

  // 雨粒の生成（Rainy用）
  const raindrops = useMemo(() => {
    return Array.from({ length: 15 }).map((_, i) => ({
      id: i,
      left: `${Math.random() * 100}%`,
      animationDuration: `${Math.random() * 0.5 + 0.5}s`,
      animationDelay: `${Math.random()}s`
    }));
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 p-4 flex flex-col items-center select-none overflow-x-hidden font-sans pb-12">
      
      {/* Header */}
      <div className="w-full max-w-md flex justify-between items-center mb-6 pt-4 px-2">
        <div className="flex flex-col">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Generation</span>
          <span className="text-2xl font-black text-indigo-600">{cycle}代め</span>
        </div>
        <div className="bg-white shadow-sm border border-slate-200 px-3 py-1.5 rounded-full flex items-center gap-1.5 relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-indigo-100 to-transparent translate-x-[-100%] animate-[shimmer_2s_infinite]"></div>
          <Sparkles size={14} className="text-amber-500 animate-pulse relative z-10" />
          <span className="text-sm font-bold relative z-10 text-indigo-900">進化: +{evolutionBonus.toFixed(1)}</span>
        </div>
      </div>

      {/* Main Visual Stage */}
      <div className={`relative w-full max-w-md aspect-square bg-gradient-to-b ${weatherBackgroundClass} rounded-[3rem] shadow-inner border-4 overflow-hidden flex items-center justify-center transition-colors duration-1000 ${isDead ? 'border-amber-300 shadow-[inset_0_0_50px_rgba(251,191,36,0.4)]' : 'border-white'}`}>
        
        {/* Weather Graphics Layer (背景エフェクト) */}
        <div className="absolute inset-0 overflow-hidden rounded-[3rem] pointer-events-none z-0">
          {weather.id === 'Sunny' && !isDead && (
            <div className="absolute -top-10 -right-10 w-48 h-48 bg-yellow-100/60 rounded-full blur-2xl animate-pulse"></div>
          )}
          {weather.id === 'Cloudy' && !isDead && (
            <>
              <div className="absolute top-12 left-[-30%] w-40 h-12 bg-white/40 rounded-full blur-md animate-[cloud-drift_15s_linear_infinite]"></div>
              <div className="absolute top-28 left-[-50%] w-32 h-10 bg-white/30 rounded-full blur-sm animate-[cloud-drift_20s_linear_infinite_2s]"></div>
            </>
          )}
          {weather.id === 'Rainy' && !isDead && (
            <div className="absolute inset-0">
               {raindrops.map((drop) => (
                 <div key={drop.id} className="absolute w-0.5 h-6 bg-blue-100/50 rounded-full"
                      style={{
                        left: drop.left,
                        top: `-20px`,
                        animation: `rain-fall ${drop.animationDuration} linear infinite ${drop.animationDelay}`
                      }} />
               ))}
               <div className="absolute inset-0 bg-blue-900/10 transition-opacity duration-1000"></div>
            </div>
          )}
        </div>

        {/* ライフサイクル円環 (SVG Ring) */}
        <div className="absolute inset-0 flex items-center justify-center opacity-20 pointer-events-none z-0">
          <svg className="w-[85%] h-[85%] -rotate-90 transform" viewBox="0 0 260 260">
            <circle cx="130" cy="130" r={RING_RADIUS} stroke="currentColor" strokeWidth="8" fill="none" className="text-slate-900/10" />
            
            {[15, 45, 75].map((percent) => {
              const angle = (percent / 100) * 360 * (Math.PI / 180);
              const x = 130 + Math.cos(angle) * RING_RADIUS;
              const y = 130 + Math.sin(angle) * RING_RADIUS;
              const x2 = 130 + Math.cos(angle) * (RING_RADIUS + 8);
              const y2 = 130 + Math.sin(angle) * (RING_RADIUS + 8);
              return (
                <line key={percent} x1={x} y1={y} x2={x2} y2={y2} stroke="currentColor" strokeWidth="3" className="text-slate-900/20" />
              );
            })}

            <circle 
              cx="130" cy="130" r={RING_RADIUS} 
              stroke="currentColor" strokeWidth="12" fill="none" 
              strokeLinecap="round"
              className={isDead ? "text-amber-500" : state === STATES.MUTATION ? "text-fuchsia-500" : "text-indigo-500 transition-all duration-300 ease-out"}
              style={{ strokeDasharray: RING_CIRCUMFERENCE, strokeDashoffset: ringOffset }}
            />
          </svg>
        </div>

        {/* Shadow */}
        {!isDead && (
          <div 
            className={`absolute bottom-[22%] w-24 h-4 rounded-[100%] blur-md z-0 transition-colors duration-1000 ${weather.id === 'Rainy' ? 'bg-black/30' : 'bg-black/10'}`}
            style={{ animation: `shadow-pulse ${bobDuration} infinite alternate ease-in-out` }}
          />
        )}

        {/* Character Container */}
        <div 
          className="relative z-10 cursor-pointer"
          onClick={handleTap}
          style={{ 
            transform: `scale(${0.8 + (progress / 200)}) rotate(${isDead ? '0deg' : leanAngle})`,
            transition: 'transform 0.5s ease-out',
            filter: mushroomColorFilter
          }}
        >
          {/* タップエフェクト */}
          {clicks.map(click => (
            <div 
              key={click.id} 
              className="absolute text-amber-500 font-black text-xl pointer-events-none z-50 animate-[float-up_0.8s_ease-out_forwards]"
              style={{ left: click.x - 20, top: click.y - 40 }}
            >
              +EXP!
            </div>
          ))}

          {/* 生体ノイズイベントメッセージ */}
          {eventMessage && !isDead && (
            <div className="absolute -top-12 left-1/2 -translate-x-1/2 whitespace-nowrap bg-white/90 backdrop-blur-sm px-3 py-1 rounded-full text-xs font-bold text-indigo-600 shadow-md animate-[bounce_0.5s_infinite] pointer-events-none z-50">
              {eventMessage}
            </div>
          )}

          <div 
            style={{ 
              animation: isDead 
                ? 'ghost-ascend 4s infinite ease-in-out' 
                : `mushroom-jump ${bobDuration} infinite alternate ease-in-out` 
            }}
          >
            {/* Mushroom Emoji */}
            <div className={`text-8xl filter drop-shadow-2xl relative z-20 transition-opacity duration-1000 ${isDead ? 'opacity-90' : 'opacity-100'}`}>
              {isDead ? '👻' : '🍄'}
              {isDead && (
                <div className="absolute inset-0 pointer-events-none -z-10">
                  <div className="absolute inset-0 bg-amber-200 blur-3xl rounded-full opacity-60 animate-pulse"></div>
                  <div className="absolute inset-0 border-4 border-amber-400 rounded-full animate-[ping_2s_infinite]"></div>
                  <div className="absolute inset-0 border-2 border-yellow-200 rounded-full animate-[ping_3s_infinite_0.5s]"></div>
                </div>
              )}
              {state === STATES.MUTATION && !isDead && (
                <div className="absolute inset-0 bg-fuchsia-400 blur-2xl rounded-full opacity-50 -z-10 animate-pulse"></div>
              )}
            </div>

            {/* まるっこい足 */}
            {!isDead && (
              <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 w-16 h-10 flex justify-around pointer-events-none">
                <div className="relative w-4 h-6 origin-top" style={{ animation: `leg-swing-main ${walkDuration} infinite ease-in-out` }}>
                  <div className="w-full h-full bg-amber-800 rounded-full shadow-[inset_-2px_-2px_4px_rgba(0,0,0,0.3)]"></div>
                </div>
                <div className="relative w-4 h-6 origin-top" style={{ animation: `leg-swing-main ${walkDuration} infinite ease-in-out`, animationDelay: `calc(${walkDuration} / -2)` }}>
                  <div className="w-full h-full bg-amber-800 rounded-full shadow-[inset_-2px_-2px_4px_rgba(0,0,0,0.3)]"></div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Status Badge & Environment */}
        <div className="absolute top-6 left-6 flex flex-col gap-2 z-20">
          <div className={`bg-white/90 backdrop-blur-md px-4 py-2 rounded-2xl border ${isDead ? 'border-amber-300' : state === STATES.MUTATION ? 'border-fuchsia-400' : 'border-white'} shadow-lg flex items-center gap-2 transition-colors`}>
            {state === STATES.DECLINE && <BatteryWarning size={14} className="text-rose-500 animate-pulse" />}
            {state === STATES.MUTATION && <Activity size={14} className="text-fuchsia-500 animate-bounce" />}
            {isDead && <Sparkles size={14} className="text-amber-500 animate-[spin_3s_linear_infinite]" />}
            <div>
              <p className="text-[10px] text-slate-400 font-bold uppercase mb-0.5 tracking-tighter leading-none">Status</p>
              <p className={`text-lg font-black tracking-tight leading-none ${state === STATES.DECLINE ? 'text-rose-500' : state === STATES.MUTATION ? 'text-fuchsia-600' : isDead ? 'text-amber-500' : 'text-slate-800'}`}>
                {STATE_JP[state]}
              </p>
            </div>
          </div>
          
          {!isDead && (
            <div className="bg-white/80 backdrop-blur-sm px-3 py-1.5 rounded-xl border border-white shadow-sm flex items-center gap-2 animate-[fade-in_0.5s_ease-out]">
              <WeatherIcon size={14} className={weather.color} />
              <span className="text-xs font-bold text-slate-600">{weather.name}</span>
            </div>
          )}
        </div>

        {/* Efficiency Indicator */}
        {!isDead && (
           <div className="absolute bottom-6 right-6 bg-white/80 backdrop-blur-sm px-3 py-1.5 rounded-xl border border-white shadow-sm flex flex-col items-center z-20">
             <span className="flex items-center gap-1 text-[9px] font-bold text-slate-400 uppercase tracking-tighter">
               <Activity size={10} /> 蓄積効率
             </span>
             <span className={`text-sm font-black ${state === STATES.MUTATION ? 'text-fuchsia-600 animate-pulse' : currentEfficiency >= 1.2 ? 'text-indigo-600' : currentEfficiency < 1.0 ? 'text-rose-500' : 'text-slate-700'}`}>
               x{currentEfficiency}
             </span>
           </div>
        )}
      </div>

      {/* Controls */}
      <div className="w-full max-w-md mt-8 space-y-5 px-2">
        {/* Progress Bar */}
        <div className="space-y-1.5">
          <div className="flex justify-between items-end px-1">
            <span className="text-sm font-bold flex items-center gap-2">
              <TrendingUp size={16} className={isDead ? 'text-amber-500' : 'text-indigo-400'} />
              <span className={isDead ? 'text-amber-600' : 'text-slate-600'}>
                {isDead ? '生命の最大化到達' : '経験値（Accumulation）'}
              </span>
            </span>
            <span className="text-xs font-mono font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md shadow-inner">
              {Math.floor(displayAcc).toLocaleString()} / {Math.floor(lMax).toLocaleString()}
            </span>
          </div>
          <div className="h-4 w-full bg-slate-200 rounded-full overflow-hidden p-0.5 shadow-inner border border-white relative">
            <div 
              className={`h-full rounded-full transition-all duration-300 relative overflow-hidden ${isDead ? 'bg-gradient-to-r from-amber-400 to-yellow-300 shadow-[0_0_15px_rgba(251,191,36,0.8)]' : state === STATES.MUTATION ? 'bg-gradient-to-r from-fuchsia-500 to-purple-500 shadow-[0_0_15px_rgba(217,70,239,0.5)]' : 'bg-gradient-to-r from-indigo-500 to-blue-500 shadow-[0_0_10px_rgba(79,70,229,0.3)]'}`}
              style={{ width: `${progress}%` }}
            >
               <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0IiBoZWlnaHQ9IjQiPgo8cmVjdCB3aWR0aD0iNCIgaGVpZ2h0PSI0IiBmaWxsPSIjZmZmIiBmaWxsLW9wYWNpdHk9IjAuMSIvPgo8L3N2Zz4=')] opacity-50"></div>
            </div>
          </div>
        </div>

        {/* Velocity Slider */}
        <div className={`p-5 rounded-[2rem] bg-white shadow-sm border transition-all duration-500 ${isDead ? 'opacity-30 grayscale pointer-events-none border-slate-200' : state === STATES.DECLINE ? 'border-rose-200 bg-rose-50/50' : state === STATES.MUTATION ? 'border-fuchsia-300 bg-fuchsia-50/30' : 'border-slate-200'}`}>
          <div className="flex justify-between items-center mb-4">
            <span className="font-black flex items-center gap-2 tracking-tight text-slate-700">
              <FastForward size={18} className={state === STATES.DECLINE ? 'text-rose-500' : state === STATES.MUTATION ? 'text-fuchsia-500' : 'text-indigo-500'} />
              歩く元気 (Velocity)
            </span>
            <div className="flex items-center gap-2">
              <button 
                onClick={() => setIsAutoMode(!isAutoMode)}
                className={`flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-bold transition-colors border ${isAutoMode ? 'bg-indigo-500 text-white border-indigo-600 shadow-inner' : 'bg-slate-100 text-slate-400 border-slate-200 hover:bg-slate-200'}`}
              >
                <Cpu size={12} className={isAutoMode ? "animate-pulse" : ""} /> AUTO
              </button>
              
              <div className={`px-3 py-1 rounded-xl transition-colors shadow-inner ${isDead ? 'bg-amber-100 text-amber-600' : state === STATES.DECLINE ? 'bg-rose-100 text-rose-600' : state === STATES.MUTATION ? 'bg-fuchsia-100 text-fuchsia-600' : 'bg-indigo-50 text-indigo-600'}`}>
                <span className="text-xl font-black">Lv.{velocity}</span>
              </div>
            </div>
          </div>
          
          <input 
            type="range" min="1" max="10" 
            value={velocity} 
            onChange={(e) => {
              if (!isDead) {
                setVelocity(parseInt(e.target.value));
                if (isAutoMode) setIsAutoMode(false);
              }
            }}
            className={`w-full h-3 bg-slate-100 rounded-lg appearance-none cursor-pointer transition-colors ${isDead ? 'accent-amber-500' : state === STATES.DECLINE ? 'accent-rose-500' : state === STATES.MUTATION ? 'accent-fuchsia-500' : 'accent-indigo-600'}`}
          />
          
          <div className="flex justify-between mt-3 px-1 items-start">
             <div className="flex flex-col">
               <span className="text-[9px] font-bold text-slate-300 italic uppercase">Slow</span>
             </div>
             {!isDead && (
               <div className={`flex flex-col items-center px-3 py-1 rounded-full border transition-colors ${state === STATES.MUTATION ? 'bg-fuchsia-50 border-fuchsia-200' : 'bg-slate-50 border-slate-100'}`}>
                 <span className={`flex items-center gap-1 text-[9px] font-bold uppercase tracking-tighter ${state === STATES.MUTATION ? 'text-fuchsia-400' : 'text-slate-400'}`}>
                   <Target size={10} /> 推奨ペース
                 </span>
                 <span className={`text-[10px] font-bold ${state === STATES.MUTATION ? 'text-fuchsia-600 animate-pulse' : 'text-indigo-500'}`}>
                   {REC_VELOCITY[state]}
                 </span>
               </div>
             )}
             <div className="flex flex-col items-end">
               <span className="text-[9px] font-bold text-slate-300 italic uppercase">Fast</span>
             </div>
          </div>
        </div>

        {/* Action Button */}
        {isDead && (
          <button 
            onClick={handleRebirth}
            className="w-full py-5 bg-gradient-to-r from-amber-400 to-orange-500 text-white rounded-[2rem] font-black text-xl shadow-[0_10px_25px_rgba(245,158,11,0.4)] animate-bounce flex items-center justify-center gap-3 transition-transform active:scale-95"
          >
            <RotateCcw />
            次の代へ進化する
          </button>
        )}
      </div>

      {/* Cycle Memory (History) */}
      {history.length > 0 && (
        <div className="w-full max-w-md mt-4 px-2 animate-[fade-in_0.5s_ease-out]">
          <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2 flex items-center gap-2 border-b border-slate-200 pb-1">
            <RotateCcw size={10} /> Cycle Memory
          </h3>
          <div className="space-y-2">
            {history.map((h, i) => (
              <div key={i} className="flex flex-col bg-white/60 px-3 py-2.5 rounded-xl border border-slate-100 shadow-sm relative overflow-hidden">
                <div className="absolute right-0 top-0 bg-indigo-50 text-indigo-500 text-[9px] font-bold px-2 py-1 rounded-bl-lg">
                  {h.type}
                </div>
                <div className="flex justify-between items-center text-xs mb-1">
                  <span className="font-bold text-slate-700">{h.cycle}代め</span>
                  <span className="text-indigo-500 font-mono font-bold pr-16">L_max: {Math.floor(h.lMax).toLocaleString()}</span>
                </div>
                <div className="flex justify-between items-center text-[10px] text-slate-400">
                   <span>進化ボーナス: +{h.bonus.toFixed(1)}</span>
                   <span>生存: {h.time}秒 / 天気: {h.weather}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <style>{`
        @keyframes mushroom-jump {
          0% { transform: translateY(0); }
          100% { transform: translateY(-15px); }
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
        @keyframes ghost-ascend {
          0% { transform: translateY(0) rotate(0deg); opacity: 0.8; }
          50% { transform: translateY(-40px) rotate(8deg); opacity: 1; }
          100% { transform: translateY(0) rotate(0deg); opacity: 0.8; }
        }
        @keyframes shimmer {
          100% { transform: translateX(100%); }
        }
        @keyframes fade-in {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes float-up {
          0% { transform: translateY(0) scale(0.5); opacity: 1; }
          100% { transform: translateY(-40px) scale(1.2); opacity: 0; }
        }
        @keyframes cloud-drift {
          0% { transform: translateX(0); opacity: 0; }
          10% { opacity: 1; }
          90% { opacity: 1; }
          100% { transform: translateX(400px); opacity: 0; }
        }
        @keyframes rain-fall {
          0% { transform: translateY(0) rotate(15deg); opacity: 0; }
          20% { opacity: 1; }
          80% { opacity: 1; }
          100% { transform: translateY(300px) rotate(15deg); opacity: 0; }
        }
        input[type='range']::-webkit-slider-thumb {
          -webkit-appearance: none;
          height: 24px; width: 24px;
          border-radius: 50%; background: currentColor;
          border: 3px solid white; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.15);
          cursor: pointer;
        }
      `}</style>
    </div>
  );
};

export default App;