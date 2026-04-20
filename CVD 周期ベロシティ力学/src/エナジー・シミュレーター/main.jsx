import React, { useState, useEffect, useRef } from 'react';
import { Battery, BatteryCharging, Zap, Activity, ChevronDown, ChevronUp } from 'lucide-react';

const EnergySimulator = () => {
  const canvasRef = useRef(null);
  const requestRef = useRef();

  // --- ユーザーが操作するパラメータ ---
  const [rhythm, setRhythm] = useState(50);     // 波の長さ（生活リズム）
  const [amplitude, setAmplitude] = useState(60); // 波の大きさ（エネルギーの起伏）

  // --- シミュレーションの状態（表示用） ---
  const [currentState, setCurrentState] = useState('元気');
  const [velocity, setVelocity] = useState(0);
  const [direction, setDirection] = useState('up');
  const [desireLevel, setDesireLevel] = useState(0);
  const [message, setMessage] = useState('');

  // 内部変数
  const timeRef = useRef(0);
  const boostRef = useRef(0); // レッドブルによる外乱（ブースト）

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    
    // スマホ対応：キャンバスのサイズを親要素に合わせる
    const resizeCanvas = () => {
      canvas.width = canvas.parentElement.clientWidth;
      canvas.height = 200;
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    const animate = () => {
      timeRef.current += 0.05;
      const t = timeRef.current;

      // パラメータの変換
      const T = 10 + (100 - rhythm) * 0.4; // 周期
      const A = amplitude / 100; // 振幅 (0.0 ~ 1.0)

      // ブースト（外乱）の減衰処理
      boostRef.current *= 0.96;

      // 画面のクリア
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const centerY = canvas.height / 2;
      const graphHeight = canvas.height * 0.4;

      // 過去の軌跡を描画
      ctx.beginPath();
      for (let x = 0; x < canvas.width; x++) {
        const timeAtX = t - (canvas.width - x) * 0.05;
        // CVD基本式： y = A * sin(wt) + boost
        const yBase = A * Math.sin((2 * Math.PI / T) * timeAtX);
        // ブーストは現在の時間にのみ強くかかるよう調整（過去の軌跡には過去のブーストを計算すべきだが、ここでは簡略化して現在値に繋げる）
        const drawY = centerY - (yBase * graphHeight);
        
        if (x === 0) ctx.moveTo(x, drawY);
        else ctx.lineTo(x, drawY);
      }
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
      ctx.lineWidth = 3;
      ctx.stroke();

      // 現在の状態計算（一番右端）
      const currentYBase = A * Math.sin((2 * Math.PI / T) * t);
      const currentY = currentYBase + boostRef.current;
      
      // ベロシティ（微分＝変化の勢い）の計算
      const currentVBase = A * (2 * Math.PI / T) * Math.cos((2 * Math.PI / T) * t);
      const currentV = currentVBase; // ブーストの変化量は無視して本来のバイオリズムの勢いを見る

      // CVDロジックの判定
      // 状態 (Drive / Rest) -> Y軸が上か下か
      const isDrive = currentY > 0;
      setCurrentState(isDrive ? '活動モード' : '休息モード');

      // 変化の方向
      const isGoingUp = currentV > 0;
      setDirection(isGoingUp ? 'up' : 'down');

      // 勢い (0-10段階に量子化)
      const maxV = A * (2 * Math.PI / T);
      const rawVelocityLevel = Math.min(10, Math.floor((Math.abs(currentV) / maxV) * 10));
      // 万が一NaNになった時の対策
      const velocityLevel = isNaN(rawVelocityLevel) ? 0 : rawVelocityLevel;
      setVelocity(velocityLevel);

      // --- 新解釈：レッドブル欲求度の計算 ---
      // CVDの「最大ベロシティは中間状態で発生する」を応用。
      // 「下向き（疲労方向）に最も勢いがある時」に欲求が最大化する。
      let desire = 0;
      if (!isGoingUp) {
        desire = (Math.abs(currentV) / maxV) * 100;
      }
      
      // ブースト中は欲求をリセット
      if (boostRef.current > 0.5) desire = 0;
      setDesireLevel(Math.min(100, Math.max(0, desire)));

      // メッセージの出し分け
      if (boostRef.current > 0.5) {
        setMessage('⚡️限界突破！エナジー全開！');
      } else if (isDrive && isGoingUp) {
        setMessage('どんどん調子が上がってる！');
      } else if (isDrive && !isGoingUp && velocityLevel > 6) {
        setMessage('急にペースダウン…少し焦りを感じる');
      } else if (!isDrive && !isGoingUp && velocityLevel > 7) {
        setMessage('ヤバい、急激に疲れが…！翼が欲しい！');
      } else if (!isDrive && isGoingUp) {
        setMessage('どん底は抜けた。ゆっくり回復中。');
      } else {
        setMessage('安定しています。');
      }

      // 現在位置の描画（ボール）
      const ballY = centerY - (currentY * graphHeight);
      
      // 欲求度に応じてボールの色を変える
      let ballColor = '#3b82f6'; // デフォルト青
      if (boostRef.current > 0.5) ballColor = '#facc15'; // ブースト時 黄色
      else if (desire > 70) ballColor = '#ef4444'; // 欲求大 赤
      else if (isDrive) ballColor = '#10b981'; // 活動 緑

      ctx.beginPath();
      ctx.arc(canvas.width - 20, Math.min(canvas.height-10, Math.max(10, ballY)), 10, 0, Math.PI * 2);
      ctx.fillStyle = ballColor;
      ctx.fill();
      ctx.shadowBlur = 15;
      ctx.shadowColor = ballColor;
      ctx.fill(); // シャドウ用
      ctx.shadowBlur = 0;

      // 中央線（基準点）
      ctx.beginPath();
      ctx.moveTo(0, centerY);
      ctx.lineTo(canvas.width, centerY);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
      ctx.lineWidth = 1;
      ctx.setLineDash([5, 5]);
      ctx.stroke();
      ctx.setLineDash([]);

      requestRef.current = requestAnimationFrame(animate);
    };

    requestRef.current = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(requestRef.current);
      window.removeEventListener('resize', resizeCanvas);
    };
  }, [rhythm, amplitude]);

  const handleDrink = () => {
    // 外乱応答：一気に状態を跳ね上げる
    boostRef.current = 1.5;
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 font-sans flex flex-col items-center">
      <div className="w-full max-w-md bg-slate-900 rounded-3xl shadow-2xl overflow-hidden border border-slate-800 pb-6">
        
        {/* ヘッダー */}
        <div className="bg-gradient-to-r from-blue-900 to-indigo-900 p-5 text-center relative overflow-hidden">
          <h1 className="text-xl font-bold tracking-wider text-white z-10 relative">ENERGY SIMULATOR</h1>
          <p className="text-blue-300 text-xs mt-1 z-10 relative">Powered by CVD Framework</p>
          <div className="absolute top-0 left-0 w-full h-full bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI4IiBoZWlnaHQ9IjgiPgo8cmVjdCB3aWR0aD0iOCIgaGVpZ2h0PSI4IiBmaWxsPSIjZmZmIiBmaWxsLW9wYWNpdHk9IjAuMDUiLz4KPC9zdmc+')] opacity-20"></div>
        </div>

        {/* キャンバス（波形） */}
        <div className="w-full h-[200px] relative bg-slate-950">
          <canvas ref={canvasRef} className="w-full h-full block" />
          <div className="absolute top-2 left-2 text-xs text-emerald-400 opacity-70">元気ゾーン (Drive)</div>
          <div className="absolute bottom-2 left-2 text-xs text-blue-400 opacity-70">お疲れゾーン (Rest)</div>
        </div>

        {/* ステータス表示 */}
        <div className="px-6 py-4 space-y-4">
          <div className="text-center min-h-[3rem] flex items-center justify-center">
            <p className="text-lg font-medium text-white">{message}</p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="bg-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
              <span className="text-xs text-slate-400 mb-1">今の状態</span>
              <div className="flex items-center space-x-2">
                {currentState === '活動モード' ? <Activity className="w-5 h-5 text-emerald-400" /> : <Battery className="w-5 h-5 text-blue-400" />}
                <span className="font-bold">{currentState}</span>
              </div>
            </div>
            <div className="bg-slate-800 rounded-2xl p-4 flex flex-col items-center justify-center">
              <span className="text-xs text-slate-400 mb-1">変化の勢い</span>
              <div className="flex items-center space-x-1">
                {direction === 'up' ? <ChevronUp className="w-5 h-5 text-emerald-400" /> : <ChevronDown className="w-5 h-5 text-red-400" />}
                <span className="font-bold text-xl">{velocity}</span>
                <span className="text-xs text-slate-500">/10</span>
              </div>
            </div>
          </div>

          {/* 欲求度メーター */}
          <div className="bg-slate-800 rounded-2xl p-4">
            <div className="flex justify-between items-end mb-2">
              <span className="text-sm font-bold text-slate-300">エナジードリンク欲求度</span>
              <span className="text-xl font-black" style={{ color: desireLevel > 80 ? '#ef4444' : '#f8fafc' }}>
                {Math.round(desireLevel)}%
              </span>
            </div>
            <div className="w-full bg-slate-900 rounded-full h-4 overflow-hidden border border-slate-700">
              <div 
                className="h-full transition-all duration-300 ease-out"
                style={{ 
                  width: `${desireLevel}%`,
                  background: desireLevel > 80 ? 'linear-gradient(90deg, #f59e0b, #ef4444)' : 'linear-gradient(90deg, #3b82f6, #8b5cf6)'
                }}
              ></div>
            </div>
          </div>
        </div>

        {/* コントロール（スライダー） */}
        <div className="px-6 py-2 space-y-6">
          <div>
            <div className="flex justify-between mb-1">
              <span className="text-sm text-slate-300">生活のリズム</span>
              <span className="text-xs text-slate-500">{rhythm < 40 ? 'せかせか' : rhythm > 60 ? 'ゆったり' : '普通'}</span>
            </div>
            <input 
              type="range" 
              min="0" max="100" 
              value={rhythm} 
              onChange={(e) => setRhythm(Number(e.target.value))}
              className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
            />
          </div>
          
          <div>
            <div className="flex justify-between mb-1">
              <span className="text-sm text-slate-300">エネルギーの起伏</span>
              <span className="text-xs text-slate-500">{amplitude < 40 ? '安定・平坦' : amplitude > 60 ? '激しい' : '普通'}</span>
            </div>
            <input 
              type="range" 
              min="0" max="100" 
              value={amplitude} 
              onChange={(e) => setAmplitude(Number(e.target.value))}
              className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-indigo-500"
            />
          </div>
        </div>

        {/* アクションボタン */}
        <div className="px-6 mt-6">
          <button 
            onClick={handleDrink}
            className="w-full bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-bold py-4 rounded-2xl shadow-[0_0_20px_rgba(6,182,212,0.4)] transition-all transform active:scale-95 flex items-center justify-center space-x-2"
          >
            <Zap className="w-6 h-6" />
            <span>翼をさずかる（エナジーチャージ）</span>
          </button>
          <p className="text-center text-[10px] text-slate-500 mt-3">※押すと一時的に「状態」を限界突破させます（外乱モデル）</p>
        </div>

      </div>
    </div>
  );
};

export default EnergySimulator;