import React, { useState, useEffect } from 'react';
import { Sparkles, Compass, Moon, Sun, Activity, Shield, ArrowRight, RotateCcw, Stars } from 'lucide-react';

const App = () => {
  // --- State Management ---
  const [step, setStep] = useState('input'); // 'input', 'loading', 'result'
  
  // ユーザー入力値 (0-100)
  const [worry, setWorry] = useState(50);      // 内部的には Y_risk に相当
  const [confusion, setConfusion] = useState(50); // 内部的には Y_uncertainty に相当
  const [freedom, setFreedom] = useState(50);    // 内部的には Y_optionality に相当

  // 占い結果データ
  const [fortuneResult, setFortuneResult] = useState(null);

  // --- IPDF Core Logic ---
  // 設計書に基づく虚数位相力学フレームワークの計算
  const calculateIPDF = () => {
    // 1. ユーザー入力を正規化 (0.0 - 1.0)
    const Y_risk = worry / 100;
    const Y_uncertainty = confusion / 100;
    const Y_optionality = freedom / 100;

    // 設計パラメータ
    const k_r = 10.0;    // リスク感度
    const theta_r = 0.5; // リスク閾値
    const k_u = 2.0;     // 不確実性減衰係数

    // 4.2 制御重みの初期計算
    // R_weight: リスクに対する重み (シグモイド関数)
    let R_weight = 1 / (1 + Math.exp(-k_r * (Y_risk - theta_r)));
    // D_weight: 探索・オプションに対する重み
    let D_weight = (1 - Y_risk) * Y_optionality;
    // Speed: 不確実性による行動速度の減衰
    const Speed = Math.exp(-k_u * Y_uncertainty);

    // 4.3 動的調整
    D_weight = D_weight * Speed;
    R_weight = R_weight + (1 - Speed);

    // 4.4 正規化 (D_weight + R_weight = 1)
    const total = D_weight + R_weight;
    const normalized_D = D_weight / total;
    const normalized_R = R_weight / total;

    // 7. 位相ダイナミクス
    const activity_level = Math.abs(normalized_D - normalized_R);
    // phase: 位相角 (アークタンジェント)
    const phase = Math.atan2(Y_risk, activity_level);

    // 7.2 モード判定 (UI向けに翻訳)
    let mode = "";
    let title = "";
    let message = "";
    let actionAdvice = "";
    let colorClass = "";

    if (normalized_D > normalized_R && Y_risk < 0.4) {
      mode = "探索";
      title = "大いなる旅立ちの刻";
      message = "未来の可能性が大きく開かれています。あなたの直感は正しく、新しいことに挑戦する絶好のタイミングです。";
      actionAdvice = "普段なら迷うような選択肢でも、今は「面白そう」と感じた方へ進んでみましょう。";
      colorClass = "from-amber-400 to-orange-600";
    } else if (normalized_R > normalized_D && Y_risk > 0.6) {
      mode = "安定";
      title = "静寂と守護の刻";
      message = "今は見えない霧に包まれている状態です。無理に動くよりも、足元を固め、エネルギーを蓄えるべき時期です。";
      actionAdvice = "大きな決断は先送りにして、いつもの日常を大切に過ごすことで運気が安定します。";
      colorClass = "from-blue-500 to-indigo-800";
    } else {
      mode = "適応";
      title = "調和と変化の刻";
      message = "環境が少しずつ変化しようとしています。状況に合わせて柔軟に身をこなすことで、予期せぬ幸運を掴めるでしょう。";
      actionAdvice = "周囲の意見に耳を傾けつつ、小さな一歩を試してみるのが吉です。";
      colorClass = "from-emerald-400 to-teal-700";
    }

    setFortuneResult({
      mode,
      title,
      message,
      actionAdvice,
      stats: {
        adventure: Math.round(normalized_D * 100), // D_weight
        defense: Math.round(normalized_R * 100),   // R_weight
        energy: Math.round(Speed * 100)            // Speed
      },
      colorClass
    });
  };

  // --- Handlers ---
  const handlePredict = () => {
    setStep('loading');
    calculateIPDF();
    
    // 神秘的なローディング演出のためのタイムアウト
    setTimeout(() => {
      setStep('result');
    }, 2500);
  };

  const handleReset = () => {
    setStep('input');
    setWorry(50);
    setConfusion(50);
    setFreedom(50);
  };

  // --- Render Helpers ---
  const renderSlider = (label, value, setValue, icon, leftText, rightText) => (
    <div className="bg-slate-800/50 p-4 rounded-2xl border border-slate-700 backdrop-blur-sm mb-6">
      <div className="flex items-center gap-2 mb-3 text-slate-200 font-medium">
        {icon}
        <span>{label}</span>
      </div>
      <input
        type="range"
        min="0"
        max="100"
        value={value}
        onChange={(e) => setValue(parseInt(e.target.value))}
        className="w-full h-2 bg-slate-600 rounded-lg appearance-none cursor-pointer accent-indigo-500"
      />
      <div className="flex justify-between text-xs text-slate-400 mt-2 font-medium">
        <span>{leftText}</span>
        <span>{rightText}</span>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-indigo-500/30 relative overflow-hidden flex flex-col items-center justify-center p-4">
      
      {/* Background Effects */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-indigo-600/20 blur-[120px] rounded-full pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-600/20 blur-[120px] rounded-full pointer-events-none" />

      <div className="w-full max-w-md relative z-10">
        
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center p-3 bg-indigo-500/10 rounded-2xl border border-indigo-500/20 mb-4">
            <Compass className="w-8 h-8 text-indigo-400" />
          </div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-indigo-300 to-purple-400 bg-clip-text text-transparent">
            星導の羅針盤
          </h1>
          <p className="text-slate-400 text-sm mt-1">あなたの潜在意識から未来を導く</p>
        </div>

        {/* --- STEP 1: Input --- */}
        {step === 'input' && (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="mb-8">
              <p className="text-center text-sm text-slate-300 mb-6">
                今のあなたの状態を教えてください。直感で選ぶのがポイントです。
              </p>

              {renderSlider(
                "今の心配事は？", worry, setWorry, <Shield className="w-5 h-5 text-blue-400" />,
                "全くない", "とても心配"
              )}
              {renderSlider(
                "心に迷いはある？", confusion, setConfusion, <Moon className="w-5 h-5 text-purple-400" />,
                "スッキリ", "モヤモヤ"
              )}
              {renderSlider(
                "これからどうしたい？", freedom, setFreedom, <Sun className="w-5 h-5 text-amber-400" />,
                "現状維持", "大冒険したい"
              )}
            </div>

            <button
              onClick={handlePredict}
              className="w-full py-4 rounded-2xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-lg shadow-lg shadow-indigo-900/50 transition-all active:scale-95 flex items-center justify-center gap-2"
            >
              <Sparkles className="w-5 h-5" />
              未来を読み解く
            </button>
          </div>
        )}

        {/* --- STEP 2: Loading --- */}
        {step === 'loading' && (
          <div className="flex flex-col items-center justify-center py-20 animate-in fade-in duration-500">
            <div className="relative">
              <div className="w-16 h-16 border-4 border-slate-700 rounded-full"></div>
              <div className="w-16 h-16 border-4 border-indigo-500 rounded-full border-t-transparent animate-spin absolute top-0 left-0"></div>
              <Stars className="w-6 h-6 text-indigo-400 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 animate-pulse" />
            </div>
            <p className="mt-6 text-slate-400 text-sm animate-pulse tracking-widest">
              潜在確率を観測中...
            </p>
          </div>
        )}

        {/* --- STEP 3: Result --- */}
        {step === 'result' && fortuneResult && (
          <div className="animate-in fade-in zoom-in-95 duration-500">
            
            <div className="bg-slate-800/80 backdrop-blur-md rounded-3xl border border-slate-700 overflow-hidden shadow-2xl">
              {/* Header colored by Mode */}
              <div className={`p-6 bg-gradient-to-br ${fortuneResult.colorClass} relative overflow-hidden`}>
                <div className="absolute top-0 right-0 p-4 opacity-20">
                  <Activity className="w-24 h-24" />
                </div>
                <span className="inline-block px-3 py-1 bg-white/20 rounded-full text-xs font-bold text-white mb-3 backdrop-blur-md">
                  {fortuneResult.mode}の位相
                </span>
                <h2 className="text-2xl font-bold text-white relative z-10">
                  {fortuneResult.title}
                </h2>
              </div>

              {/* Content */}
              <div className="p-6">
                <p className="text-slate-200 leading-relaxed mb-6">
                  {fortuneResult.message}
                </p>

                <div className="bg-slate-900/50 rounded-xl p-4 mb-6 border border-slate-700/50">
                  <h3 className="text-xs font-bold text-slate-400 mb-3 uppercase tracking-wider">
                    今のアクション指針
                  </h3>
                  <div className="flex items-start gap-3">
                    <ArrowRight className="w-5 h-5 text-indigo-400 mt-0.5 shrink-0" />
                    <p className="text-sm text-slate-300 font-medium">
                      {fortuneResult.actionAdvice}
                    </p>
                  </div>
                </div>

                {/* Status Bars (IPDF internal stats) */}
                <div className="space-y-4">
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-amber-400 flex items-center gap-1"><Sun className="w-3 h-3"/> 冒険への推進力</span>
                      <span className="text-slate-300">{fortuneResult.stats.adventure}%</span>
                    </div>
                    <div className="w-full bg-slate-700 rounded-full h-1.5">
                      <div className="bg-amber-400 h-1.5 rounded-full transition-all duration-1000" style={{ width: `${fortuneResult.stats.adventure}%` }}></div>
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-blue-400 flex items-center gap-1"><Shield className="w-3 h-3"/> 守護と安定の力</span>
                      <span className="text-slate-300">{fortuneResult.stats.defense}%</span>
                    </div>
                    <div className="w-full bg-slate-700 rounded-full h-1.5">
                      <div className="bg-blue-400 h-1.5 rounded-full transition-all duration-1000" style={{ width: `${fortuneResult.stats.defense}%` }}></div>
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-emerald-400 flex items-center gap-1"><Activity className="w-3 h-3"/> 行動エネルギー</span>
                      <span className="text-slate-300">{fortuneResult.stats.energy}%</span>
                    </div>
                    <div className="w-full bg-slate-700 rounded-full h-1.5">
                      <div className="bg-emerald-400 h-1.5 rounded-full transition-all duration-1000" style={{ width: `${fortuneResult.stats.energy}%` }}></div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <button
              onClick={handleReset}
              className="w-full mt-6 py-4 rounded-2xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-lg border border-slate-700 transition-all flex items-center justify-center gap-2"
            >
              <RotateCcw className="w-5 h-5" />
              もう一度占う
            </button>
          </div>
        )}

      </div>
    </div>
  );
};

export default App;