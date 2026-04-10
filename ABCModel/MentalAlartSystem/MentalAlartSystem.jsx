import React, { useState, useRef, useEffect } from 'react';
import { HeartPulse, Brain, ShieldAlert, Wind, Users, Zap, Info, Clock, AlertTriangle, ShieldCheck, Lock, RotateCcw, Play } from 'lucide-react';

// ==========================================
// 1. Core Logic (Pythonシミュレーターの移植)
// ==========================================

const STATE = { NORMAL: 0, ZERO: 1, RUNAWAY: 2 };
const clamp = (val, min, max) => Math.max(min, Math.min(max, val));

const getDeltaBand = (d) => {
  if (d < 0.5) return 0; // STABLE
  if (d < 1.5) return 1; // SWING
  return 2; // SPIKE
};

const roundRBand = (r) => {
  if (r < 2.5) return 2;
  if (r < 4.4) return 4;
  if (r < 5.4) return 5;
  return 6;
};

// ユーザーの入力レベル(0~3, -1)をCore層のComponent(v, delta, state)に変換するマッパー
const mapLevelToEfComponent = (level) => {
  if (level === -1) return { v: 0.0, delta: 0.0, state: STATE.ZERO };
  if (level === 0) return { v: 0.0, delta: 0.0, state: STATE.NORMAL };
  if (level === 1) return { v: 0.8, delta: 0.5, state: STATE.NORMAL };
  if (level === 2) return { v: 1.5, delta: 1.0, state: STATE.NORMAL };
  if (level === 3) return { v: 2.0, delta: 1.5, state: STATE.RUNAWAY };
  return { v: 0.0, delta: 0.0, state: STATE.NORMAL };
};

const simulateStep = (prevState, currentEfLevels) => {
  const { core, params } = prevState;
  
  // EFコンポーネント化
  const ef = {
    E0: mapLevelToEfComponent(currentEfLevels.E0),
    E1: mapLevelToEfComponent(currentEfLevels.E1),
    E2: mapLevelToEfComponent(currentEfLevels.E2),
    E3: mapLevelToEfComponent(currentEfLevels.E3)
  };

  let newParams = {
    zeroLock: params.zeroLock,
    runawayAbsentCount: params.runawayAbsentCount,
    cooldowns: { ...params.cooldowns }
  };
  let logs = [];

  // --- 1. 外部要因の投影 ---
  const gamma_social = 1.0; 
  const adjE2 = Math.min(2.0, ef.E2.v + (gamma_social - 1.0));

  const v_prime = {
    A: core.A.v - 0.5 * (ef.E1.v + ef.E3.v + ef.E0.v),
    B: core.B.v + Math.max(0.5 * adjE2, 0.5 * ef.E3.v),
    C: core.C.v + Math.max(0.5 * adjE2, 0.5 * ef.E3.v, 0.5 * ef.E0.v)
  };

  const delta_prime = {
    A: Math.max(core.A.delta, ef.E1.delta, ef.E3.delta, ef.E0.delta),
    B: Math.max(core.B.delta, ef.E2.delta, ef.E3.delta),
    C: Math.min(2.0, Math.max(core.C.delta, ef.E2.delta, ef.E3.delta, ef.E0.delta))
  };

  const state_prime = { A: core.A.state, B: core.B.state, C: core.C.state };

  if (ef.E1.state === STATE.RUNAWAY && v_prime.A >= 1.0) state_prime.A = STATE.RUNAWAY;
  if (ef.E3.state === STATE.RUNAWAY && delta_prime.C >= 1.5) state_prime.C = STATE.RUNAWAY;
  if (ef.E0.state === STATE.ZERO && v_prime.A <= 1.0) state_prime.A = STATE.ZERO;
  if (ef.E0.state === STATE.RUNAWAY && delta_prime.C >= 1.5) state_prime.C = STATE.RUNAWAY;

  // --- 2. 相互作用 ---
  const gate_E2C = adjE2 / 2.0;
  const v_double_prime = {};
  
  for(let x of ['A','B','C']) {
    let vx_p = clamp(v_prime[x], 0, 2);
    let interaction_sum = 0;
    for(let y of ['A','B','C']) {
      if(x === y) continue;
      let k = 0;
      if(y === 'C' && x === 'A') k = -1;
      if(y === 'B' && x === 'C') k = 1;
      if(y === 'A' && x === 'B') k = -1;

      if(y === 'B' && x === 'C') k *= (1.0 - gate_E2C);
      if(y === 'A' && x === 'B') k *= (1.0 - 0.2 * 0.5); // wB1=0.5

      if(k === 0) continue;

      let w_y = 0;
      if(state_prime[y] === STATE.RUNAWAY) w_y = 0.9;
      else if(state_prime[y] === STATE.ZERO) w_y = 0.25;

      let sgn_y = state_prime[y] === STATE.RUNAWAY ? 1 : 0;
      let boost_y = delta_prime[y] >= 1.5 ? 1.35 : 1.0;
      let g_vy = 0.5 * Math.tanh(0.7 * clamp(v_prime[y], 0, 2));

      interaction_sum += sgn_y * w_y * k * g_vy * boost_y;
    }
    v_double_prime[x] = clamp(vx_p + interaction_sum, 0, 2);
  }

  const delta_double_prime = {};
  for(let x of ['A','B','C']) {
    let d_min = 0.0;
    if(state_prime[x] === STATE.RUNAWAY) d_min = Math.max(d_min, 1.0);
    if(state_prime[x] === STATE.ZERO) d_min = Math.max(d_min, 0.5);
    
    let has_active_y = ['A','B','C'].filter(y => y!==x).some(y => state_prime[y] === STATE.RUNAWAY || state_prime[y] === STATE.ZERO);
    if(has_active_y) d_min = Math.max(d_min, 0.5);
    
    delta_double_prime[x] = Math.max(delta_prime[x], d_min);
  }

  // --- 3. TR判定 (ルール) ---
  let working = {
    A: { v: v_double_prime.A, delta: delta_double_prime.A, state: state_prime.A },
    B: { v: v_double_prime.B, delta: delta_double_prime.B, state: state_prime.B },
    C: { v: v_double_prime.C, delta: delta_double_prime.C, state: state_prime.C }
  };

  if(newParams.cooldowns.TR1 === 0 && working.C.state === STATE.RUNAWAY && working.C.delta >= 1.5 && working.A.v <= 1.0) {
    working.A.state = STATE.ZERO;
    newParams.cooldowns.TR1 = 1;
    logs.push("【警戒】俯瞰しすぎてエネルギー喪失（虚無状態）");
  }

  if(newParams.cooldowns.TR2 === 0 && newParams.zeroLock === 0 && working.B.state === STATE.RUNAWAY && working.A.state === STATE.ZERO && working.B.v >= 1.6) {
    working.C.state = STATE.RUNAWAY;
    newParams.cooldowns.TR2 = 2;
    logs.push("【警戒】強いプレッシャーにより自己監視が暴走");
  }

  if(working.A.v >= 1.55 && working.B.delta >= 0.5) {
    working.B.delta = 1.0;
    // logs.push("生気によってプレッシャーの揺れが安定化");
  }

  if(newParams.cooldowns.TR5 === 0 && ef.E2.state === STATE.RUNAWAY) {
    working.B.state = STATE.RUNAWAY;
    newParams.cooldowns.TR5 = 1;
    logs.push("【警戒】社会圧によりプレッシャーが暴走");
  }

  // --- 4. Zero-Lock管理 ---
  if(working.A.state === STATE.ZERO) {
    if(ef.E2.state === STATE.RUNAWAY || ef.E0.state === STATE.RUNAWAY || ef.E1.state === STATE.RUNAWAY) {
       if (newParams.zeroLock === 0) logs.push("🔒 虚無ロック発動 (回復しにくい状態です)");
       newParams.zeroLock = Math.max(newParams.zeroLock, 2);
    }
  }

  if(newParams.zeroLock > 0) {
    working.A.state = STATE.ZERO;
    let all_not_runaway = ['A','B','C'].every(x => working[x].state !== STATE.RUNAWAY);
    if(all_not_runaway) {
       newParams.runawayAbsentCount += 1;
       if(newParams.runawayAbsentCount >= 2) {
          newParams.zeroLock = Math.max(0, newParams.zeroLock - 1);
          newParams.runawayAbsentCount = 0;
          if (newParams.zeroLock === 0) logs.push("🔓 虚無ロックが解除されました");
       }
    } else {
       newParams.runawayAbsentCount = 0;
    }
  }

  // --- 5. RuinScore 計算 ---
  const getRuinScore = (comp, name) => {
    let w_v = name === 'A' ? -1.0 : 1.0;
    let base = w_v * comp.v + comp.delta + comp.state;
    let score = base;
    if(getDeltaBand(comp.delta) === 2 && comp.state === STATE.RUNAWAY) score = Math.max(score, 5.0);
    if(comp.state === STATE.ZERO) score = Math.max(score, 3.0);
    return clamp(score, 0, 6);
  };

  let scores = { A: getRuinScore(working.A, 'A'), B: getRuinScore(working.B, 'B'), C: getRuinScore(working.C, 'C') };
  let r_core = Math.max(scores.A, scores.B, scores.C);

  let r_ef_list = Object.values(ef).map(e_comp => {
    let e_score = e_comp.v + e_comp.delta + e_comp.state;
    if(e_comp.delta >= 1.5 && e_comp.state === STATE.RUNAWAY) e_score = Math.max(e_score, 5.0);
    if(e_comp.state === STATE.ZERO) e_score = Math.max(e_score, 3.0);
    return clamp(e_score, 0, 6);
  });
  let r_ef = Math.max(...r_ef_list);

  let final_r_cont = Math.max(r_core, r_ef);
  let final_r_label = roundRBand(final_r_cont);

  for(let k in newParams.cooldowns) {
    newParams.cooldowns[k] = Math.max(0, newParams.cooldowns[k] - 1);
  }

  if (logs.length === 0) {
     if (final_r_label <= 2) logs.push("状態は安定しています。");
     else if (final_r_label >= 5) logs.push("危険な兆候が続いています。");
  }

  return {
    core: working,
    params: newParams,
    score: { label: final_r_label, raw: final_r_cont },
    logs: logs
  };
};

// ==========================================
// 2. UI Components
// ==========================================

const INITIAL_CORE = {
  A: { v: 1.0, delta: 0.0, state: STATE.NORMAL },
  B: { v: 1.0, delta: 0.0, state: STATE.NORMAL },
  C: { v: 1.0, delta: 0.0, state: STATE.NORMAL }
};

export default function App() {
  const [day, setDay] = useState(1);
  const [core, setCore] = useState(INITIAL_CORE);
  const [params, setParams] = useState({ zeroLock: 0, runawayAbsentCount: 0, cooldowns: { TR1: 0, TR2: 0, TR5: 0 } });
  const [score, setScore] = useState({ label: 0, raw: 0 });
  const [efLevels, setEfLevels] = useState({ E0: 0, E1: 0, E2: 0, E3: 0 });
  const [historyLogs, setHistoryLogs] = useState(["シミュレーションを開始しました。"]);

  const handleStep = () => {
    const nextState = simulateStep({ core, params }, efLevels);
    setCore(nextState.core);
    setParams(nextState.params);
    setScore(nextState.score);
    if (nextState.logs.length > 0) {
      setHistoryLogs(prev => [`[Day ${day}] ${nextState.logs.join(" / ")}`, ...prev].slice(0, 10));
    }
    setDay(d => d + 1);
  };

  const handleReset = () => {
    setCore(INITIAL_CORE);
    setParams({ zeroLock: 0, runawayAbsentCount: 0, cooldowns: { TR1: 0, TR2: 0, TR5: 0 } });
    setScore({ label: 0, raw: 0 });
    setEfLevels({ E0: 0, E1: 0, E2: 0, E3: 0 });
    setDay(1);
    setHistoryLogs(["システムをリセットしました。"]);
  };

  const applyPreset = (presetName) => {
    let newEf = { E0: 0, E1: 0, E2: 0, E3: 0 };
    if (presetName === 'overwork') newEf = { E0: 2, E1: 3, E2: 1, E3: 2 };
    if (presetName === 'sns_burnout') newEf = { E0: 1, E1: 0, E2: 3, E3: 3 };
    if (presetName === 'sick') newEf = { E0: -1, E1: 1, E2: 0, E3: 0 }; // 虚無体調
    if (presetName === 'rest') newEf = { E0: 0, E1: 0, E2: 0, E3: 0 };
    setEfLevels(newEf);
  };

  const getScoreColor = (label) => {
    if (label <= 2) return "text-green-500";
    if (label <= 4) return "text-yellow-500";
    if (label === 5) return "text-orange-500";
    return "text-red-500";
  };

  const getStateBadge = (state) => {
    if (state === STATE.NORMAL) return <span className="px-2 py-1 text-xs font-bold rounded bg-green-100 text-green-700">安定 (Normal)</span>;
    if (state === STATE.ZERO) return <span className="px-2 py-1 text-xs font-bold rounded bg-slate-200 text-slate-600">虚無 (Zero)</span>;
    if (state === STATE.RUNAWAY) return <span className="px-2 py-1 text-xs font-bold rounded bg-red-100 text-red-700 animate-pulse">暴走 (Runaway)</span>;
  };

  const ComponentBar = ({ label, icon, comp, desc }) => (
    <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-100 mb-3">
      <div className="flex justify-between items-center mb-2">
        <div className="flex items-center gap-2">
          {icon}
          <h3 className="font-semibold text-slate-800">{label}</h3>
        </div>
        {getStateBadge(comp.state)}
      </div>
      <p className="text-xs text-slate-500 mb-3">{desc}</p>
      
      <div className="space-y-2">
        <div>
          <div className="flex justify-between text-xs text-slate-600 mb-1">
            <span>強度 (Velocity)</span>
            <span>{comp.v.toFixed(2)}</span>
          </div>
          <div className="w-full bg-slate-100 rounded-full h-2">
            <div className={`h-2 rounded-full ${comp.v > 1.5 ? 'bg-red-400' : 'bg-blue-400'}`} style={{ width: `${(comp.v / 2) * 100}%` }}></div>
          </div>
        </div>
        <div>
          <div className="flex justify-between text-xs text-slate-600 mb-1">
            <span>揺れ (Delta)</span>
            <span>{comp.delta.toFixed(2)}</span>
          </div>
          <div className="w-full bg-slate-100 rounded-full h-1.5">
            <div className={`h-1.5 rounded-full ${comp.delta > 1.0 ? 'bg-orange-400' : 'bg-slate-400'}`} style={{ width: `${(comp.delta / 2) * 100}%` }}></div>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 font-sans p-4 md:p-8">
      <header className="max-w-5xl mx-auto mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2 text-indigo-900">
            <Brain className="w-8 h-8 text-indigo-600" />
            ABCメンタルシミュレーター
          </h1>
          <p className="text-sm text-slate-500 mt-1">Core層 v3.2.0 ロジックに基づく感情動態ダッシュボード</p>
        </div>
        <div className="text-right">
          <div className="text-sm text-slate-500 font-medium">現在のシミュレーション</div>
          <div className="text-xl font-bold text-indigo-700">Day {day}</div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* 左カラム：入力・操作 */}
        <div className="lg:col-span-4 space-y-6">
          <div className="bg-white p-5 rounded-2xl shadow-sm border border-slate-200">
            <h2 className="text-lg font-bold mb-4 flex items-center gap-2 border-b pb-2">
              <Zap className="w-5 h-5 text-yellow-500" />
              外部環境の変化
            </h2>
            <p className="text-xs text-slate-500 mb-4">今の状況にあわせてスライダーを動かしてください。</p>

            <div className="space-y-5">
              {[
                { id: 'E0', label: '体調・身体負荷', icon: <HeartPulse className="w-4 h-4 text-rose-500"/>, hasZero: true },
                { id: 'E1', label: '環境・休息不足', icon: <Wind className="w-4 h-4 text-cyan-500"/> },
                { id: 'E2', label: '社会圧力・比較', icon: <Users className="w-4 h-4 text-purple-500"/> },
                { id: 'E3', label: 'ノイズ・情報過多', icon: <AlertTriangle className="w-4 h-4 text-orange-500"/> }
              ].map(ef => (
                <div key={ef.id}>
                  <div className="flex justify-between items-center mb-2 text-sm font-medium">
                    <span className="flex items-center gap-1">{ef.icon} {ef.label}</span>
                    <span className="text-slate-500 text-xs">
                      {efLevels[ef.id] === -1 ? '極限(虚無)' : efLevels[ef.id] === 0 ? '平穏' : efLevels[ef.id] === 1 ? '軽度' : efLevels[ef.id] === 2 ? '重度' : '危険'}
                    </span>
                  </div>
                  <input 
                    type="range" 
                    min={ef.hasZero ? -1 : 0} max="3" step="1" 
                    value={efLevels[ef.id]} 
                    onChange={(e) => setEfLevels({...efLevels, [ef.id]: parseInt(e.target.value)})}
                    className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-indigo-600"
                  />
                </div>
              ))}
            </div>

            <div className="mt-6 space-y-2">
              <div className="text-xs font-semibold text-slate-500 mb-2">シナリオ・プリセット</div>
              <div className="grid grid-cols-2 gap-2">
                <button onClick={() => applyPreset('overwork')} className="text-xs py-1.5 px-2 bg-slate-100 hover:bg-slate-200 rounded text-slate-700 transition">残業続き</button>
                <button onClick={() => applyPreset('sns_burnout')} className="text-xs py-1.5 px-2 bg-slate-100 hover:bg-slate-200 rounded text-slate-700 transition">SNS疲れ</button>
                <button onClick={() => applyPreset('sick')} className="text-xs py-1.5 px-2 bg-slate-100 hover:bg-slate-200 rounded text-slate-700 transition">体調不良ダウン</button>
                <button onClick={() => applyPreset('rest')} className="text-xs py-1.5 px-2 bg-green-50 hover:bg-green-100 rounded text-green-700 transition">十分な休息</button>
              </div>
            </div>
          </div>

          <div className="flex gap-3">
            <button 
              onClick={handleReset}
              className="flex-1 py-3 bg-white border border-slate-300 text-slate-600 rounded-xl font-bold flex items-center justify-center gap-2 hover:bg-slate-50 transition shadow-sm"
            >
              <RotateCcw className="w-5 h-5" /> リセット
            </button>
            <button 
              onClick={handleStep}
              className="flex-[2] py-3 bg-indigo-600 text-white rounded-xl font-bold flex items-center justify-center gap-2 hover:bg-indigo-700 transition shadow-md"
            >
              <Play className="w-5 h-5" /> 1日進める
            </button>
          </div>
        </div>

        {/* 右カラム：ダッシュボード */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          
          {/* 上段：メインスコアと状態 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            
            {/* Ruin Score */}
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex flex-col justify-center items-center relative overflow-hidden">
              <div className="absolute top-4 left-4 flex items-center gap-1 text-slate-400 text-xs font-bold">
                <ShieldCheck className="w-4 h-4" /> RUIN SCORE (危険度)
              </div>
              
              <div className="mt-4 flex flex-col items-center">
                <span className={`text-6xl font-extrabold tracking-tighter ${getScoreColor(score.label)}`}>
                  {score.label}
                </span>
                <div className="text-sm font-medium text-slate-500 mt-2">
                  {score.label <= 2 ? "安全レベル" : score.label <= 4 ? "注意レベル (疲労)" : score.label === 5 ? "危険レベル (暴走リスク)" : "限界レベル (即時対処)"}
                </div>
                <div className="text-xs text-slate-400 mt-1">Raw: {score.raw.toFixed(2)}</div>
              </div>
            </div>

            {/* Zero Lock Alert */}
            <div className={`p-6 rounded-2xl shadow-sm border flex flex-col justify-center transition-colors ${params.zeroLock > 0 ? 'bg-slate-800 text-white border-slate-900' : 'bg-white border-slate-200 text-slate-400'}`}>
               <div className="flex items-center gap-3 mb-2">
                 {params.zeroLock > 0 ? <Lock className="w-6 h-6 text-yellow-400" /> : <Info className="w-6 h-6" />}
                 <h3 className={`font-bold ${params.zeroLock > 0 ? 'text-lg' : ''}`}>虚無ロック (Zero-Lock)</h3>
               </div>
               {params.zeroLock > 0 ? (
                 <>
                  <p className="text-sm text-slate-300">エネルギー喪失が定着しており、一時的な休息では回復しにくい状態です。</p>
                  <div className="mt-3 text-xs bg-slate-700 p-2 rounded text-slate-200">
                    ロック強度: {params.zeroLock} (回復には平穏な日が複数日必要です)
                  </div>
                 </>
               ) : (
                 <p className="text-sm">現在、感情のロック状態はありません。正常に回復・変動が可能な状態です。</p>
               )}
            </div>
          </div>

          {/* 中段：ABC内部状態メーター */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <ComponentBar 
              label="生気・エネルギー (A)" 
              desc="自然な意欲や体感の強さ"
              comp={core.A} 
              icon={<HeartPulse className="w-5 h-5 text-pink-500" />} 
            />
            <ComponentBar 
              label="プレッシャー (B)" 
              desc="他者からの評価や理想との差"
              comp={core.B} 
              icon={<AlertTriangle className="w-5 h-5 text-yellow-500" />} 
            />
            <ComponentBar 
              label="客観視・監視 (C)" 
              desc="自分を俯瞰・監視する思考"
              comp={core.C} 
              icon={<Brain className="w-5 h-5 text-indigo-500" />} 
            />
          </div>

          {/* 下段：履歴ログ */}
          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-5 flex-1">
            <h3 className="text-sm font-bold text-slate-700 flex items-center gap-2 mb-3 border-b pb-2">
              <Clock className="w-4 h-4 text-slate-400" />
              シミュレーション・ログ
            </h3>
            <div className="space-y-2 max-h-[150px] overflow-y-auto pr-2">
              {historyLogs.map((log, i) => (
                <div key={i} className={`text-sm py-2 px-3 rounded ${i === 0 ? 'bg-indigo-50 text-indigo-900 font-medium border-l-4 border-indigo-500' : 'text-slate-600 bg-slate-50'}`}>
                  {log}
                </div>
              ))}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}