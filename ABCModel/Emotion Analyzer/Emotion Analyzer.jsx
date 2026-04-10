import React, { useState, useEffect } from 'react';
import { 
  Heart, 
  Brain, 
  Eye, 
  Activity, 
  AlertTriangle, 
  CheckCircle2, 
  Loader2, 
  Send,
  Info
} from 'lucide-react';

// The execution environment provides the key at runtime.
const apiKey = ""; 

// --- API Logic ---
const analyzeTextWithGemini = async (text) => {
  const systemPrompt = `あなたは入力されたテキストを心理学的な「ABCモデル」および「感情体系v1.0」に基づいて分析する専門システムです。
以下の定義に従い、テキストに含まれる感情や心理状態を推定し、JSON形式で出力してください。

【感情体系 Layer-1 (基本感情)】
以下の9つの感情の強度を0.0から1.0の数値で評価してください。
- joy, sadness, anger, fear, surprise, disgust, expectation, trust, contempt

【感情体系 Layer-2 (詳細感情)】
具体的な感情語を3〜5個抽出。

【ABCモデル】
A (Authenticity), B (Aesthetic), C (Meta) それぞれについて:
- v (強度): 0, 1, 2
- delta (変動): 0, 1, 2
- state (状態): "Normal", "Runaway", "Zero"

【RuinScore (危険度)】
0から6の整数。

【出力JSONフォーマット】
{
  "emotions": { "joy": 0.5, "sadness": 0.1, ... },
  "layer2": ["単語1", "単語2"],
  "abc": {
    "A": { "v": 1, "delta": 0, "state": "Normal" },
    "B": { "v": 1, "delta": 1, "state": "Normal" },
    "C": { "v": 0, "delta": 0, "state": "Normal" }
  },
  "ruinScore": 1,
  "summary": "分析サマリー"
}`;

  // API configuration
  const modelId = "gemini-1.5-flash";
  // APIキーをURLに確実に含める
  const baseUrl = `https://generativelanguage.googleapis.com/v1beta/models/${modelId}:generateContent`;
  
  const payload = {
    contents: [
      { 
        role: "user",
        parts: [{ text: `以下のテキストを感情体系v1.0とABCモデルに基づき分析し、指定のJSON形式で返してください。必ずJSONのみを出力してください。:\n\n${text}` }] 
      }
    ],
    systemInstruction: { 
      parts: [{ text: systemPrompt }] 
    },
    generationConfig: {
      responseMimeType: "application/json",
    }
  };

  const fetchWithRetry = async (retries = 5) => {
    const delays = [1000, 2000, 4000, 8000, 16000];
    for (let i = 0; i < retries; i++) {
      try {
        // APIキーが空の場合のガード（通常、環境から提供されます）
        const finalUrl = `${baseUrl}?key=${apiKey}`;
        
        const response = await fetch(finalUrl, {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const msg = errorData.error?.message || `HTTP ${response.status}`;
          // もし "unregistered callers" エラーが出た場合は、認証の問題
          if (response.status === 403 || msg.includes("unregistered")) {
            throw new Error("APIキーが正しく認識されませんでした。ページをリロードして再度お試しください。");
          }
          throw new Error(msg);
        }
        
        const result = await response.json();
        const responseText = result.candidates?.[0]?.content?.parts?.[0]?.text;
        
        if (!responseText) throw new Error("APIから空のレスポンスが返されました。");
        
        // LLM特有のMarkdownコードブロック(```json ... ```)を除去する堅牢化処理を追加
        const cleanText = responseText.replace(/^```(json)?\n?|\n?```$/gi, '').trim();
        return JSON.parse(cleanText);
      } catch (error) {
        if (i === retries - 1) throw error;
        await new Promise(res => setTimeout(res, delays[i]));
      }
    }
  };

  return await fetchWithRetry();
};

// --- UI Components ---

const emotionLabels = {
  joy: { label: "喜び・楽しさ", color: "bg-amber-400" },
  expectation: { label: "期待・ワクワク", color: "bg-emerald-400" },
  trust: { label: "安心・信頼", color: "bg-teal-400" },
  surprise: { label: "驚き", color: "bg-orange-400" },
  sadness: { label: "悲しみ・孤独", color: "bg-blue-400" },
  fear: { label: "恐れ・不安", color: "bg-indigo-400" },
  anger: { label: "怒り・苛立ち", color: "bg-red-400" },
  disgust: { label: "嫌悪", color: "bg-lime-500" },
  contempt: { label: "軽蔑", color: "bg-slate-500" },
};

const EmotionBar = ({ name, value }) => {
  const config = emotionLabels[name];
  if (!config) return null;
  const percentage = Math.max(0, Math.min(100, Math.round(value * 100)));
  if (percentage < 1) return null; 

  return (
    <div className="mb-3">
      <div className="flex justify-between text-sm mb-1">
        <span className="font-medium text-slate-700">{config.label}</span>
        <span className="text-slate-500">{percentage}%</span>
      </div>
      <div className="h-2.5 w-full bg-slate-100 rounded-full overflow-hidden">
        <div 
          className={`h-full ${config.color} transition-all duration-1000 ease-out`} 
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};

const ABCCard = ({ title, icon: Icon, desc, data, colorClass }) => {
  if (!data) return null;

  const getBadgeClass = (state) => {
    switch (state) {
      case 'Normal': return 'bg-green-100 text-green-700 border-green-200';
      case 'Runaway': return 'bg-red-100 text-red-700 border-red-200 animate-pulse';
      case 'Zero': return 'bg-slate-100 text-slate-600 border-slate-200';
      default: return 'bg-gray-100 text-gray-700 border-gray-200';
    }
  };

  const getDeltaText = (delta) => {
    switch (delta) {
      case 0: return '安定 (Stable)';
      case 1: return '揺らぎ (Swing)';
      case 2: return '激しい (Spike)';
      default: return '-';
    }
  };

  const getIntensityBars = (v) => {
    const val = typeof v === 'number' ? v : 0;
    return (
      <div className="flex space-x-1">
        {[0, 1, 2].map(i => (
          <div key={i} className={`h-4 w-2 rounded-sm ${i <= val ? colorClass : 'bg-slate-100'}`} />
        ))}
      </div>
    );
  };

  return (
    <div className="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-center space-x-3 mb-2">
        <div className={`p-2 rounded-lg bg-slate-50 text-slate-600`}>
          <Icon size={20} />
        </div>
        <div>
          <h3 className="font-bold text-slate-800 text-lg leading-tight">{title}</h3>
          <p className="text-xs text-slate-500">{desc}</p>
        </div>
      </div>
      
      <div className="mt-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-600">状態 (State)</span>
          <span className={`text-xs px-2.5 py-1 rounded-md border font-semibold ${getBadgeClass(data.state)}`}>
            {data.state || 'Normal'}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-600">強度 (v)</span>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-medium text-slate-500">{['Low', 'Mid', 'High'][data.v] || 'Low'}</span>
            {getIntensityBars(data.v)}
          </div>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-600">変動 (Δ)</span>
          <span className="text-sm font-medium text-slate-700">{getDeltaText(data.delta)}</span>
        </div>
      </div>
    </div>
  );
};

const RuinScoreDisplay = ({ score }) => {
  const s = typeof score === 'number' ? score : 0;
  let color, label, icon, desc;

  if (s <= 2) {
    color = "text-emerald-500";
    label = "安定 (R0)";
    icon = <CheckCircle2 size={32} />;
    desc = "心理的な破綻リスクは極めて低く、安定しています。";
  } else if (s <= 4) {
    color = "text-amber-500";
    label = "注意 (R1)";
    icon = <AlertTriangle size={32} />;
    desc = "ストレスや感情の偏りが見られ、少し負荷がかかっています。";
  } else if (s === 5) {
    color = "text-orange-500";
    label = "危険 (R2)";
    icon = <Activity size={32} />;
    desc = "激しい変動や暴走状態にあります。セルフケアを推奨します。";
  } else {
    color = "text-red-500";
    label = "破綻/極限 (R3)";
    icon = <AlertTriangle size={32} />;
    desc = "システムが限界です。即座の休息や外部の支援が必要です。";
  }

  return (
    <div className="bg-white rounded-2xl p-6 border border-slate-100 shadow-sm flex flex-col items-center justify-center text-center h-full">
      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4">RUIN SCORE</h3>
      <div className={`flex items-center justify-center space-x-3 mb-2 ${color}`}>
        {icon}
        <span className="text-6xl font-black">{s}</span>
      </div>
      <div className={`text-lg font-bold ${color} mb-3`}>{label}</div>
      <p className="text-sm text-slate-500 leading-relaxed">{desc}</p>
    </div>
  );
};

// --- Main App ---
export default function App() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const handleAnalyze = async () => {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await analyzeTextWithGemini(text);
      setResult(data);
    } catch (err) {
      setError(`分析失敗: ${err.message}`);
      console.error("Analysis Error:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans p-4 md:p-8">
      <div className="max-w-5xl mx-auto space-y-8">
        
        {/* Header */}
        <header className="text-center space-y-3">
          <div className="inline-flex items-center justify-center p-2 bg-indigo-600 text-white rounded-2xl mb-2">
            <Brain size={32} />
          </div>
          <h1 className="text-3xl md:text-5xl font-black tracking-tight text-slate-900">
            Emotion Analyzer
          </h1>
          <p className="text-slate-500 text-sm md:text-lg max-w-2xl mx-auto">
            あなたのテキストから深層心理（ABCモデル）と感情バランスを解析し、現在の心の「危険度」を可視化します。
          </p>
        </header>

        {/* Input Area */}
        <div className="bg-white rounded-3xl shadow-xl shadow-slate-200/50 border border-slate-200 overflow-hidden transition-all focus-within:ring-4 focus-within:ring-indigo-500/10">
          <div className="p-6 md:p-8">
            <textarea
              className="w-full h-40 p-0 bg-transparent border-0 focus:ring-0 resize-none text-lg md:text-xl text-slate-700 placeholder:text-slate-300"
              placeholder="今、何を感じていますか？ 最近あった出来事や考えを自由に綴ってください..."
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            
            {error && (
              <div className="mt-4 p-4 bg-rose-50 text-rose-700 rounded-2xl border border-rose-100 flex items-start text-sm animate-in fade-in zoom-in duration-300">
                <AlertTriangle size={20} className="mr-3 flex-shrink-0" />
                <p className="font-medium">{error}</p>
              </div>
            )}

            <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-6">
              <p className="text-xs text-slate-400 font-medium hidden md:block">
                ※入力されたテキストは感情体系 v1.0 モデルに基づいて解析されます
              </p>
              <button
                onClick={handleAnalyze}
                disabled={loading || !text.trim()}
                className="w-full md:w-auto flex items-center justify-center px-8 py-4 bg-indigo-600 text-white font-bold rounded-2xl hover:bg-indigo-700 active:scale-95 transition-all shadow-lg shadow-indigo-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <Loader2 className="animate-spin mr-3" size={20} />
                ) : (
                  <Send className="mr-3" size={20} />
                )}
                {loading ? "解析中..." : "解析を開始する"}
              </button>
            </div>
          </div>
        </div>

        {/* Results Area */}
        {result && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-10 duration-1000">
            
            {/* Summary Panel */}
            <div className="bg-indigo-600 rounded-3xl p-8 text-white shadow-2xl shadow-indigo-200 relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:scale-110 transition-transform duration-700">
                <Brain size={120} />
              </div>
              <div className="relative z-10 flex gap-6 items-start">
                <div className="bg-white/20 p-3 rounded-2xl backdrop-blur-md">
                  <Info className="text-white" size={24} />
                </div>
                <div>
                  <h3 className="text-xl font-bold mb-2 opacity-80">AI Analysis Summary</h3>
                  <p className="text-lg md:text-xl leading-relaxed font-medium">{result.summary}</p>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Left Column: Emotion Distribution */}
              <div className="lg:col-span-2 bg-white rounded-3xl p-8 shadow-sm border border-slate-100">
                <h3 className="text-xl font-bold text-slate-800 mb-8 flex items-center">
                  <Activity className="mr-3 text-indigo-500" size={24} />
                  感情のバランス分布 (Layer-1)
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-12">
                  {result.emotions && Object.entries(result.emotions)
                    .sort(([, a], [, b]) => b - a) 
                    .map(([key, value]) => (
                      <EmotionBar key={key} name={key} value={value} />
                  ))}
                </div>

                {result.layer2 && result.layer2.length > 0 && (
                  <div className="mt-8 pt-8 border-t border-slate-100">
                    <h4 className="text-xs font-black text-slate-400 mb-4 uppercase tracking-widest">DETECTED TAGS (Layer-2)</h4>
                    <div className="flex flex-wrap gap-2">
                      {result.layer2.map((tag, idx) => (
                        // 型チェックを追加し、文字列以外が混入した場合のReactクラッシュを防止
                        typeof tag === 'string' ? (
                          <span key={idx} className="px-4 py-2 bg-slate-50 text-slate-600 text-sm font-bold rounded-xl border border-slate-100">
                            #{tag}
                          </span>
                        ) : null
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Right Column: Ruin Score */}
              <div className="lg:col-span-1">
                <RuinScoreDisplay score={result.ruinScore} />
              </div>

            </div>

            {/* Bottom Row: ABC Model */}
            {result.abc && (
              <div className="space-y-4">
                <h3 className="text-xl font-bold text-slate-800 ml-2 flex items-center">
                  <Brain className="mr-3 text-slate-400" size={24} />
                  心理構造の解析 (ABCモデル)
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <ABCCard 
                    title="A: Authenticity" 
                    desc="生の感情・身体感覚" 
                    icon={Heart} 
                    data={result.abc.A}
                    colorClass="bg-rose-500" 
                  />
                  <ABCCard 
                    title="B: Aesthetic" 
                    desc="評価基準・義務・比較" 
                    icon={Activity} 
                    data={result.abc.B}
                    colorClass="bg-blue-500" 
                  />
                  <ABCCard 
                    title="C: Meta" 
                    desc="俯瞰視点・自意識" 
                    icon={Eye} 
                    data={result.abc.C}
                    colorClass="bg-violet-500" 
                  />
                </div>
              </div>
            )}

          </div>
        )}

      </div>
      <footer className="mt-12 text-center text-slate-400 text-sm pb-8">
        © 2024 Emotion System v1.0 | ABC Psychology Framework
      </footer>
    </div>
  );
}