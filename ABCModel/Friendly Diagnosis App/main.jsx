import React, { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";

type AxisStateName = "Normal" | "Runaway" | "Zero";

type AxisConfig = {
  id: string;
  technical: string;
  label: string;
  short: string;
  desc: string;
  emoji: string;
};

type AxisState = {
  value: number;
  delta: number;
  gate: number;
  trend: 1 | -1;
  prevState: AxisStateName;
  zeroLock: number;
  zeroStreak: number;
  recentDeltas: number[];
};

type AxisResult = {
  id: string;
  label: string;
  short: string;
  emoji: string;
  value: number;
  delta: number;
  gate: number;
  state: AxisStateName;
  intensityLabel: string;
  strengthBand: "Low" | "Mid" | "High";
  varianceBand: "Stable" | "Swing" | "Spike";
  helpfulText: string;
  nextDelta: number;
  nextValue: number;
  nextZeroLock: number;
  nextZeroStreak: number;
};

const AXES: AxisConfig[] = [
  {
    id: "sensitivity",
    technical: "Sensitivity",
    label: "感じる力",
    short: "感性",
    desc: "刺激や気分の動きにどれくらい反応しやすいか",
    emoji: "✨",
  },
  {
    id: "abstraction",
    technical: "Abstraction",
    label: "考えをまとめる力",
    short: "抽象",
    desc: "全体像をつかんだり、考えを整理したりする力",
    emoji: "🧠",
  },
  {
    id: "focusDepth",
    technical: "FocusDepth",
    label: "深く集中する力",
    short: "集中",
    desc: "ひとつのことに深く入り込む力",
    emoji: "🎯",
  },
  {
    id: "socialFit",
    technical: "SocialFit",
    label: "場になじむ力",
    short: "適応",
    desc: "空気やルールに自然になじみやすいか",
    emoji: "🤝",
  },
  {
    id: "interpersonalDistance",
    technical: "InterpersonalDistance",
    label: "人との距離感",
    short: "距離感",
    desc: "人と近く関わるより、自分のペースを保ちやすいか",
    emoji: "🪐",
  },
  {
    id: "emotionalRange",
    technical: "EmotionalRange",
    label: "気分のふり幅",
    short: "感情幅",
    desc: "感情や行動の変化がどれくらい大きいか",
    emoji: "🌊",
  },
  {
    id: "selfStandard",
    technical: "SelfStandard",
    label: "自分の基準の強さ",
    short: "自分軸",
    desc: "自分らしいこだわりや判断基準の強さ",
    emoji: "🧭",
  },
  {
    id: "practicalStability",
    technical: "PracticalStability",
    label: "日々を回す安定感",
    short: "安定感",
    desc: "予定や作業を着実に進めやすいか",
    emoji: "🧱",
  },
  {
    id: "creativityStyle",
    technical: "CreativityStyle",
    label: "ひらめきの出方",
    short: "創造性",
    desc: "発想したり組み立てたりする力の出やすさ",
    emoji: "🎨",
  },
  {
    id: "adaptability",
    technical: "Adaptability",
    label: "切り替えのしやすさ",
    short: "柔軟さ",
    desc: "新しい情報や変化に合わせやすいか",
    emoji: "🍃",
  },
  {
    id: "impulseDynamics",
    technical: "ImpulseDynamics",
    label: "勢いの強さ",
    short: "勢い",
    desc: "気持ちや刺激にすばやく動かされやすいか",
    emoji: "⚡",
  },
  {
    id: "valueOrientation",
    technical: "ValueOrientation",
    label: "大事にしたい軸",
    short: "価値観",
    desc: "好き・正しさ・効率などの軸がどれくらいはっきりしているか",
    emoji: "💎",
  },
];

const STORAGE_KEY = "friendly-diagnosis-app-v1";

const clamp = (value: number, min = 0, max = 1) => Math.min(max, Math.max(min, value));

const starsFromValue = (value: number) => {
  const count = Math.max(1, Math.min(5, Math.round(value * 5)));
  return "■".repeat(count);
};

const formatPercent = (value: number) => `${Math.round(value * 100)}%`;

const intensityLabel = (value: number) => {
  if (value < 0.35) return "おだやか";
  if (value < 0.55) return "ほどよい";
  if (value < 0.75) return "はっきり";
  return "かなり強い";
};

const varianceLabel = (delta: number) => {
  if (delta < 0.15) return "落ち着きめ";
  if (delta < 0.45) return "ゆれあり";
  return "大きく動きやすい";
};

const stateView = (state: AxisStateName) => {
  if (state === "Runaway") {
    return {
      title: "高ぶり気味",
      className: "bg-amber-100 text-amber-800 border-amber-200",
    };
  }
  if (state === "Zero") {
    return {
      title: "閉じ気味",
      className: "bg-sky-100 text-sky-800 border-sky-200",
    };
  }
  return {
    title: "安定",
    className: "bg-emerald-100 text-emerald-800 border-emerald-200",
  };
};

const buildDefaultState = (): Record<string, AxisState> => {
  const entries = AXES.map((axis, index) => [
    axis.id,
    {
      value: [0.72, 0.66, 0.62, 0.56, 0.48, 0.58, 0.64, 0.6, 0.68, 0.57, 0.46, 0.62][index],
      delta: [0.18, 0.12, 0.16, 0.11, 0.14, 0.22, 0.14, 0.1, 0.2, 0.16, 0.24, 0.15][index],
      gate: 0.18,
      trend: 1 as 1,
      prevState: "Normal" as AxisStateName,
      zeroLock: 0,
      zeroStreak: 0,
      recentDeltas: [0.08, 0.12],
    },
  ]);

  return Object.fromEntries(entries);
};

const makePreset = (
  values: number[],
  deltas: number[],
  gate = 0.2,
): Record<string, AxisState> => {
  return Object.fromEntries(
    AXES.map((axis, index) => [
      axis.id,
      {
        value: values[index],
        delta: deltas[index],
        gate,
        trend: values[index] >= 0.5 ? 1 : -1,
        prevState: "Normal" as AxisStateName,
        zeroLock: 0,
        zeroStreak: 0,
        recentDeltas: [Math.max(0.04, deltas[index] * 0.5), Math.max(0.04, deltas[index] * 0.7)],
      },
    ]),
  );
};

const PRESETS = [
  {
    name: "バランス型",
    note: "全体をまんべんなく見たいとき",
    getState: () => buildDefaultState(),
  },
  {
    name: "ひらめき重視",
    note: "感性・発想・集中が強め",
    getState: () =>
      makePreset(
        [0.88, 0.75, 0.81, 0.42, 0.63, 0.74, 0.78, 0.45, 0.9, 0.52, 0.68, 0.8],
        [0.36, 0.22, 0.26, 0.14, 0.18, 0.3, 0.18, 0.1, 0.38, 0.2, 0.28, 0.22],
        0.22,
      ),
  },
  {
    name: "堅実型",
    note: "安定感と実行力が高め",
    getState: () =>
      makePreset(
        [0.46, 0.62, 0.58, 0.82, 0.34, 0.38, 0.56, 0.88, 0.44, 0.74, 0.28, 0.54],
        [0.08, 0.1, 0.12, 0.09, 0.1, 0.08, 0.1, 0.1, 0.12, 0.12, 0.09, 0.1],
        0.12,
      ),
  },
  {
    name: "マイペース型",
    note: "自分の基準と距離感がはっきり",
    getState: () =>
      makePreset(
        [0.62, 0.7, 0.76, 0.38, 0.86, 0.49, 0.84, 0.55, 0.66, 0.45, 0.4, 0.82],
        [0.16, 0.12, 0.18, 0.12, 0.16, 0.14, 0.12, 0.1, 0.16, 0.12, 0.1, 0.14],
        0.18,
      ),
  },
  {
    name: "揺れやすい日",
    note: "外からの負荷が大きい状態",
    getState: () =>
      makePreset(
        [0.76, 0.54, 0.66, 0.44, 0.52, 0.82, 0.7, 0.4, 0.72, 0.42, 0.84, 0.74],
        [0.48, 0.34, 0.42, 0.3, 0.32, 0.55, 0.28, 0.22, 0.46, 0.32, 0.58, 0.3],
        0.7,
      ),
  },
];

function evaluateAxis(axis: AxisConfig, state: AxisState, previousHadRunaway: boolean): AxisResult {
  const p = clamp(state.value);
  const d = clamp(state.delta);
  const g = clamp(state.gate);
  const quietHistory = (state.recentDeltas.slice(-2).length === 2
    ? state.recentDeltas.slice(-2)
    : [0.5, 0.5]
  ).every((item) => item < 0.05);

  const zeroInternalScore = (p <= 0.25 ? 1 : 0) + (d < 0.1 ? 1 : 0) + (quietHistory ? 1 : 0);
  const zeroExternalScore = g >= 0.7 ? 1 : 0;
  const zeroTriggered = zeroInternalScore + zeroExternalScore >= 2;

  const holdZero = state.zeroLock > 0 || (state.prevState === "Zero" && p < 0.35);
  const holdRunaway = state.prevState === "Runaway" && p > 0.7 && d >= 0.15;
  const triggerRunaway = (p >= 0.8 && d >= 0.45) || g >= 0.7;

  let currentState: AxisStateName = "Normal";
  if (holdZero || zeroTriggered) {
    currentState = "Zero";
  } else if ((holdRunaway || triggerRunaway) && state.zeroLock === 0) {
    currentState = "Runaway";
  }

  let nextDelta = d;
  if (p >= 0.75 && nextDelta >= 0.15) {
    nextDelta = Math.max(nextDelta - 0.15, 0);
  }
  if (!previousHadRunaway) {
    nextDelta = Math.max(nextDelta - 0.2, 0);
  }

  const nextZeroStreak = zeroTriggered ? state.zeroStreak + 1 : 0;
  let nextZeroLock = state.zeroLock;
  if (nextZeroStreak >= 2 || (g > 0.8 && zeroTriggered)) {
    nextZeroLock = 2;
  } else if (!previousHadRunaway) {
    nextZeroLock = Math.max(nextZeroLock - 1, 0);
  }

  let nextValue = p;
  if (currentState === "Runaway" && nextZeroLock === 0) {
    nextValue = clamp(p + nextDelta * (1 - g) * state.trend);
  } else if (currentState === "Zero") {
    nextValue = clamp(p - Math.max(0.05, g * 0.08 + nextDelta * 0.35));
  } else {
    nextValue = clamp(p + state.trend * nextDelta * 0.18 * (1 - g));
  }

  const strengthBand = p <= 0.35 ? "Low" : p < 0.75 ? "Mid" : "High";
  const varianceBand = d < 0.15 ? "Stable" : d < 0.45 ? "Swing" : "Spike";

  let helpfulText = `${intensityLabel(p)} / ${varianceLabel(d)}`;
  if (currentState === "Runaway") {
    helpfulText = "強く出やすく、勢いが前に出やすい状態";
  } else if (currentState === "Zero") {
    helpfulText = "力が内側にこもりやすく、出力が下がりやすい状態";
  } else if (strengthBand === "High") {
    helpfulText = "この力はもともとかなりはっきり出やすい";
  } else if (strengthBand === "Low") {
    helpfulText = "この力は控えめに出やすい";
  }

  return {
    id: axis.id,
    label: axis.label,
    short: axis.short,
    emoji: axis.emoji,
    value: p,
    delta: d,
    gate: g,
    state: currentState,
    intensityLabel: intensityLabel(p),
    strengthBand,
    varianceBand,
    helpfulText,
    nextDelta,
    nextValue,
    nextZeroLock,
    nextZeroStreak,
  };
}

function summarize(results: AxisResult[]) {
  const lookup = (id: string) => results.find((item) => item.id === id)?.value ?? 0;
  const byState = (state: AxisStateName) => results.filter((item) => item.state === state);

  const creative = (lookup("sensitivity") + lookup("abstraction") + lookup("creativityStyle")) / 3;
  const deepWork = (lookup("focusDepth") + lookup("selfStandard") + lookup("abstraction")) / 3;
  const social = (lookup("socialFit") + (1 - lookup("interpersonalDistance")) + lookup("adaptability")) / 3;
  const steady = (lookup("practicalStability") + lookup("adaptability") + (1 - lookup("impulseDynamics"))) / 3;
  const emotional = (lookup("emotionalRange") + lookup("impulseDynamics") + lookup("sensitivity")) / 3;

  const scores = [
    { label: "ひらめき", score: creative },
    { label: "深掘り", score: deepWork },
    { label: "対人バランス", score: social },
    { label: "安定運転", score: steady },
    { label: "感情の動き", score: emotional },
  ].sort((a, b) => b.score - a.score);

  const topTags = scores.slice(0, 3).map((item) => item.label);

  let oneLine = "落ち着いたバランス型";
  if (creative >= 0.72 && deepWork >= 0.68) {
    oneLine = "感性と深掘りが両立した探究型";
  } else if (steady >= 0.72 && social >= 0.62) {
    oneLine = "周囲に合わせながら安定して進める実務型";
  } else if (lookup("interpersonalDistance") >= 0.75 && lookup("selfStandard") >= 0.75) {
    oneLine = "自分のペースと基準を大切にする独立型";
  } else if (emotional >= 0.72) {
    oneLine = "気分の勢いが表現に出やすい躍動型";
  }

  const runawayCount = byState("Runaway").length;
  const zeroCount = byState("Zero").length;

  let climate = "全体は比較的安定しています";
  if (runawayCount >= 3) climate = "強く出すぎる力がいくつかあり、熱量が高めです";
  if (zeroCount >= 3) climate = "内側に閉じやすい力が多く、少し負荷がかかっています";
  if (runawayCount >= 2 && zeroCount >= 2) climate = "高ぶりと閉じ気味が同時にあり、波の大きい状態です";

  return {
    creative,
    deepWork,
    social,
    steady,
    emotional,
    topTags,
    oneLine,
    climate,
    runawayCount,
    zeroCount,
  };
}

export default function FriendlyDiagnosisApp() {
  const [axesState, setAxesState] = useState<Record<string, AxisState>>(buildDefaultState());
  const [stepCount, setStepCount] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as Record<string, AxisState>;
      if (parsed && typeof parsed === "object") {
        setAxesState(parsed);
      }
    } catch {
      // ignore storage issues
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(axesState));
    } catch {
      // ignore storage issues
    }
  }, [axesState]);

  const previousHadRunaway = useMemo(
    () => Object.values(axesState as Record<string, AxisState>).some((item) => item.prevState === "Runaway"),
    [axesState],
  );

  const results = useMemo(
    () => AXES.map((axis) => evaluateAxis(axis, axesState[axis.id], previousHadRunaway)),
    [axesState, previousHadRunaway],
  );

  const summary = useMemo(() => summarize(results), [results]);

  const radarData = useMemo(
    () => results.map((item) => ({ subject: item.short, value: Math.round(item.value * 100) })),
    [results],
  );

  const stateChart = useMemo(
    () =>
      results.map((item) => ({
        name: item.short,
        強さ: Math.round(item.value * 100),
        揺れ: Math.round(item.delta * 100),
      })),
    [results],
  );

  const applyPreset = (index: number) => {
    setAxesState(PRESETS[index].getState());
    setStepCount(0);
  };

  const updateValue = (axisId: string, next: number) => {
    setAxesState((current) => {
      const prev = current[axisId];
      const diff = Math.abs(next - prev.value);
      const trend: 1 | -1 = next >= prev.value ? 1 : -1;
      return {
        ...current,
        [axisId]: {
          ...prev,
          value: next,
          trend,
          delta: clamp(Math.max(prev.delta * 0.5, diff)),
          recentDeltas: [...prev.recentDeltas.slice(-1), diff],
        },
      };
    });
  };

  const updateAxisField = (axisId: string, patch: Partial<AxisState>) => {
    setAxesState((current) => ({
      ...current,
      [axisId]: {
        ...current[axisId],
        ...patch,
      },
    }));
  };

  const advanceOneStep = () => {
    setAxesState((current) => {
      const hadRunaway = Object.values(current as Record<string, AxisState>).some((item) => item.prevState === "Runaway");
      return Object.fromEntries(
        AXES.map((axis) => {
          const base = current[axis.id];
          const computed = evaluateAxis(axis, base, hadRunaway);
          return [
            axis.id,
            {
              ...base,
              value: computed.nextValue,
              delta: computed.nextDelta,
              prevState: computed.state,
              zeroLock: computed.nextZeroLock,
              zeroStreak: computed.nextZeroStreak,
              recentDeltas: [...base.recentDeltas.slice(-1), computed.nextDelta],
            },
          ];
        }),
      ) as Record<string, AxisState>;
    });
    setStepCount((count) => count + 1);
  };

  const calmAll = () => {
    setAxesState((current) =>
      Object.fromEntries(
        Object.entries(current as Record<string, AxisState>).map(([key, item]) => [
          key,
          {
            ...item,
            delta: clamp(item.delta * 0.55),
            gate: clamp(item.gate * 0.6),
            prevState: item.prevState === "Runaway" ? "Normal" : item.prevState,
            zeroLock: Math.max(item.zeroLock - 1, 0),
            recentDeltas: [...item.recentDeltas.slice(-1), Math.min(item.delta * 0.55, 0.1)],
          },
        ]),
      ) as Record<string, AxisState>,
    );
  };

  const resetAll = () => {
    setAxesState(buildDefaultState());
    setStepCount(0);
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.96),_rgba(236,253,245,0.92)_35%,_rgba(224,231,255,0.92)_70%,_rgba(249,250,251,1)_100%)] text-slate-800">
      <div className="mx-auto max-w-7xl px-4 py-6 md:px-8 md:py-10">
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 overflow-hidden rounded-[28px] border border-white/70 bg-white/75 p-6 shadow-[0_20px_80px_rgba(15,23,42,0.08)] backdrop-blur"
        >
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-3 py-1 text-sm font-medium text-white">
                <span>🌈</span>
                <span>直感で触れる性格バランス診断</span>
              </div>
              <div>
                <h1 className="text-3xl font-bold tracking-tight md:text-4xl">いまの自分らしさを、触って見える化</h1>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 md:text-base">
                  12の要素をスライダーで動かすと、今の出やすさ・揺れやすさ・外からの負荷をまとめて見られます。
                  むずかしい用語は出さず、見た目と短い言葉で感覚的に理解できるようにしています。
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => setShowDetails((value) => !value)}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium shadow-sm transition hover:-translate-y-0.5 hover:shadow"
              >
                {showDetails ? "詳細調整を隠す" : "詳細調整を開く"}
              </button>
              <button
                onClick={advanceOneStep}
                className="rounded-2xl bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-slate-300 transition hover:-translate-y-0.5"
              >
                1ステップ動かす
              </button>
              <button
                onClick={calmAll}
                className="rounded-2xl bg-emerald-500 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-emerald-200 transition hover:-translate-y-0.5"
              >
                少し落ち着かせる
              </button>
              <button
                onClick={resetAll}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium shadow-sm transition hover:-translate-y-0.5 hover:shadow"
              >
                初期状態へ
              </button>
            </div>
          </div>
        </motion.div>

        <div className="mb-6 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {PRESETS.map((preset, index) => (
            <button
              key={preset.name}
              onClick={() => applyPreset(index)}
              className="rounded-[24px] border border-white/80 bg-white/70 p-4 text-left shadow-sm transition hover:-translate-y-1 hover:shadow-lg"
            >
              <div className="text-sm font-semibold text-slate-900">{preset.name}</div>
              <div className="mt-1 text-sm text-slate-600">{preset.note}</div>
            </button>
          ))}
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2">
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-[28px] border border-white/80 bg-white/75 p-5 shadow-sm backdrop-blur"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-slate-500">全体のひとこと</div>
                    <div className="mt-2 text-2xl font-bold text-slate-900">{summary.oneLine}</div>
                  </div>
                  <div className="rounded-full bg-violet-100 px-3 py-1 text-sm font-semibold text-violet-700">
                    Step {stepCount}
                  </div>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-600">{summary.climate}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {summary.topTags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-sm font-medium text-slate-700"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 }}
                className="rounded-[28px] border border-white/80 bg-white/75 p-5 shadow-sm backdrop-blur"
              >
                <div className="text-sm font-medium text-slate-500">いま出ている状態</div>
                <div className="mt-4 grid grid-cols-3 gap-3 text-center">
                  <div className="rounded-2xl bg-emerald-50 p-4">
                    <div className="text-2xl font-bold text-emerald-700">
                      {results.filter((item) => item.state === "Normal").length}
                    </div>
                    <div className="mt-1 text-sm text-emerald-700">安定</div>
                  </div>
                  <div className="rounded-2xl bg-amber-50 p-4">
                    <div className="text-2xl font-bold text-amber-700">{summary.runawayCount}</div>
                    <div className="mt-1 text-sm text-amber-700">高ぶり気味</div>
                  </div>
                  <div className="rounded-2xl bg-sky-50 p-4">
                    <div className="text-2xl font-bold text-sky-700">{summary.zeroCount}</div>
                    <div className="mt-1 text-sm text-sky-700">閉じ気味</div>
                  </div>
                </div>
                <div className="mt-4 rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                  <div>安定：いつもの出方に近い状態</div>
                  <div>高ぶり気味：勢いが出すぎて空回りしやすい状態</div>
                  <div>閉じ気味：力が内側にこもって出にくい状態</div>
                </div>
              </motion.div>
            </div>

            <div className="rounded-[28px] border border-white/80 bg-white/75 p-4 shadow-sm backdrop-blur md:p-5">
              <div className="mb-4 flex items-center justify-between gap-4">
                <div>
                  <div className="text-lg font-semibold text-slate-900">12項目をスライダーで調整</div>
                  <p className="mt-1 text-sm text-slate-600">
                    上のスライダーは今の出やすさ。必要なら「くわしく」で揺れやすさと外からの負荷も調整できます。
                  </p>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                {results.map((result) => {
                  const stateChip = stateView(result.state);
                  const axisState = axesState[result.id];
                  const isOpen = expanded === result.id;

                  return (
                    <motion.div
                      key={result.id}
                      layout
                      className="rounded-[24px] border border-slate-100 bg-white p-4 shadow-sm"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex min-w-0 gap-3">
                          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-100 text-2xl">
                            {result.emoji}
                          </div>
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <h3 className="text-base font-semibold text-slate-900">{result.label}</h3>
                              <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${stateChip.className}`}>
                                {stateChip.title}
                              </span>
                            </div>
                            <p className="mt-1 text-sm leading-6 text-slate-600">{AXES.find((item) => item.id === result.id)?.desc}</p>
                          </div>
                        </div>
                        <button
                          onClick={() => setExpanded(isOpen ? null : result.id)}
                          className="rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-600"
                        >
                          {isOpen ? "閉じる" : "くわしく"}
                        </button>
                      </div>

                      <div className="mt-4 rounded-2xl bg-slate-50 p-3">
                        <div className="flex items-center justify-between text-sm">
                          <span className="font-medium text-slate-700">今の出やすさ</span>
                          <span className="font-semibold text-slate-900">{formatPercent(result.value)} ・ {starsFromValue(result.value)}</span>
                        </div>
                        <input
                          type="range"
                          min={0}
                          max={1}
                          step={0.01}
                          value={axisState.value}
                          onChange={(event) => updateValue(result.id, Number(event.target.value))}
                          className="mt-3 h-2 w-full cursor-pointer appearance-none rounded-full bg-gradient-to-r from-sky-100 via-violet-100 to-emerald-100"
                        />
                        <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
                          <span>控えめ</span>
                          <span>{result.intensityLabel}</span>
                          <span>かなり強い</span>
                        </div>
                      </div>

                      <div className="mt-3 grid gap-2 sm:grid-cols-3">
                        <div className="rounded-2xl bg-violet-50 p-3">
                          <div className="text-xs font-medium text-violet-600">出方</div>
                          <div className="mt-1 text-sm font-semibold text-violet-900">{result.intensityLabel}</div>
                        </div>
                        <div className="rounded-2xl bg-amber-50 p-3">
                          <div className="text-xs font-medium text-amber-600">揺れ</div>
                          <div className="mt-1 text-sm font-semibold text-amber-900">{varianceLabel(result.delta)}</div>
                        </div>
                        <div className="rounded-2xl bg-emerald-50 p-3">
                          <div className="text-xs font-medium text-emerald-600">ひとこと</div>
                          <div className="mt-1 text-sm font-semibold text-emerald-900">{result.helpfulText}</div>
                        </div>
                      </div>

                      <AnimatePresence initial={false}>
                        {(isOpen || showDetails) && (
                          <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            exit={{ opacity: 0, height: 0 }}
                            className="overflow-hidden"
                          >
                            <div className="mt-4 space-y-3 rounded-[24px] border border-dashed border-slate-200 bg-slate-50/70 p-4">
                              <div>
                                <div className="flex items-center justify-between text-sm">
                                  <span className="font-medium text-slate-700">最近の揺れやすさ</span>
                                  <span className="font-semibold text-slate-900">{formatPercent(axisState.delta)}</span>
                                </div>
                                <input
                                  type="range"
                                  min={0}
                                  max={1}
                                  step={0.01}
                                  value={axisState.delta}
                                  onChange={(event) =>
                                    updateAxisField(result.id, {
                                      delta: Number(event.target.value),
                                      recentDeltas: [
                                        ...axisState.recentDeltas.slice(-1),
                                        Number(event.target.value),
                                      ],
                                    })
                                  }
                                  className="mt-3 h-2 w-full cursor-pointer appearance-none rounded-full bg-gradient-to-r from-emerald-100 via-amber-100 to-rose-100"
                                />
                              </div>
                              <div>
                                <div className="flex items-center justify-between text-sm">
                                  <span className="font-medium text-slate-700">外からの負荷</span>
                                  <span className="font-semibold text-slate-900">{formatPercent(axisState.gate)}</span>
                                </div>
                                <input
                                  type="range"
                                  min={0}
                                  max={1}
                                  step={0.01}
                                  value={axisState.gate}
                                  onChange={(event) => updateAxisField(result.id, { gate: Number(event.target.value) })}
                                  className="mt-3 h-2 w-full cursor-pointer appearance-none rounded-full bg-gradient-to-r from-sky-100 via-fuchsia-100 to-orange-100"
                                />
                              </div>
                              <div>
                                <div className="flex items-center justify-between text-sm">
                                  <span className="font-medium text-slate-700">次の動く向き</span>
                                  <span className="font-semibold text-slate-900">{axisState.trend > 0 ? "上がる向き" : "下がる向き"}</span>
                                </div>
                                <div className="mt-3 flex gap-2">
                                  <button
                                    onClick={() => updateAxisField(result.id, { trend: 1 })}
                                    className={`flex-1 rounded-2xl px-3 py-2 text-sm font-medium ${
                                      axisState.trend > 0
                                        ? "bg-slate-900 text-white"
                                        : "border border-slate-200 bg-white text-slate-700"
                                    }`}
                                  >
                                    上がる向き
                                  </button>
                                  <button
                                    onClick={() => updateAxisField(result.id, { trend: -1 })}
                                    className={`flex-1 rounded-2xl px-3 py-2 text-sm font-medium ${
                                      axisState.trend < 0
                                        ? "bg-slate-900 text-white"
                                        : "border border-slate-200 bg-white text-slate-700"
                                    }`}
                                  >
                                    下がる向き
                                  </button>
                                </div>
                              </div>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </motion.div>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="space-y-6">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-[28px] border border-white/80 bg-white/75 p-5 shadow-sm backdrop-blur"
            >
              <div className="text-lg font-semibold text-slate-900">全体バランス</div>
              <p className="mt-1 text-sm text-slate-600">丸い形で、今どの力が前に出やすいかを見られます。</p>
              <div className="mt-4 h-[320px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={radarData} outerRadius="72%">
                    <PolarGrid />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: "#334155", fontSize: 12 }} />
                    <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                    <Radar dataKey="value" fill="rgba(99, 102, 241, 0.35)" stroke="rgb(79, 70, 229)" />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 }}
              className="rounded-[28px] border border-white/80 bg-white/75 p-5 shadow-sm backdrop-blur"
            >
              <div className="text-lg font-semibold text-slate-900">強さと揺れの見比べ</div>
              <p className="mt-1 text-sm text-slate-600">高いほど、出やすさや揺れやすさが大きいことを表します。</p>
              <div className="mt-4 h-[320px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stateChart} barGap={4}>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" />
                    <XAxis dataKey="name" fontSize={12} />
                    <YAxis width={36} />
                    <Tooltip />
                    <Bar dataKey="強さ" radius={[8, 8, 0, 0]} fill="rgba(14, 165, 233, 0.75)" />
                    <Bar dataKey="揺れ" radius={[8, 8, 0, 0]} fill="rgba(249, 115, 22, 0.75)" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.08 }}
              className="rounded-[28px] border border-white/80 bg-white/75 p-5 shadow-sm backdrop-blur"
            >
              <div className="text-lg font-semibold text-slate-900">読み取りのヒント</div>
              <div className="mt-4 space-y-3 text-sm leading-6 text-slate-600">
                <div className="rounded-2xl bg-slate-50 p-4">
                  <div className="font-semibold text-slate-900">まずは「今の出やすさ」を触る</div>
                  <div className="mt-1">自分の感覚に近いところまでスライダーを動かすと、全体の形がわかりやすくなります。</div>
                </div>
                <div className="rounded-2xl bg-slate-50 p-4">
                  <div className="font-semibold text-slate-900">波がある日は「最近の揺れやすさ」も上げる</div>
                  <div className="mt-1">気分や行動の波が大きい日ほど、状態が変わりやすく見えます。</div>
                </div>
                <div className="rounded-2xl bg-slate-50 p-4">
                  <div className="font-semibold text-slate-900">しんどい日は「外からの負荷」を足す</div>
                  <div className="mt-1">負荷が強いほど、一部の力が出すぎたり、逆に閉じたりしやすくなります。</div>
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </div>
    </div>
  );
}
