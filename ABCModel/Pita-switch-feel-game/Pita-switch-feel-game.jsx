import React, { useEffect, useMemo, useRef, useState } from "react";

const MODULES = [
  { id: "ramp", label: "さかみち", emoji: "🛝", hint: "すーっと前へ" },
  { id: "domino", label: "ドミノ", emoji: "🁢", hint: "カタカタ連鎖" },
  { id: "bumper", label: "はずみ玉", emoji: "💥", hint: "ポンッとはずむ" },
  { id: "fan", label: "ふうせん風", emoji: "💨", hint: "ふわっと押す" },
  { id: "spinner", label: "くるり板", emoji: "🌀", hint: "向きを整える" },
  { id: "bell", label: "ベル", emoji: "🔔", hint: "チリンで気持ちいい" },
  { id: "blank", label: "なにもなし", emoji: "▫️", hint: "ひと休み区間" },
];

const MODULE_MAP = Object.fromEntries(MODULES.map((m) => [m.id, m]));
const SLOT_X = [150, 270, 390, 510, 630, 750];
const STAGE = { width: 900, height: 430, baseY: 260, goalX: 848 };

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const lerp = (a, b, t) => a + (b - a) * t;
const uid = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

function scoreBand(value) {
  if (value >= 90) return "するする";
  if (value >= 75) return "かなりいい感じ";
  if (value >= 60) return "あと少しでハマる";
  return "ちょい調整で化ける";
}

function makeStars() {
  return new Array(18).fill(0).map((_, i) => ({
    id: i,
    x: 40 + ((i * 47) % 800),
    y: 30 + ((i * 59) % 140),
    r: 1.5 + ((i * 13) % 4),
    opacity: 0.15 + (((i * 19) % 7) / 20),
  }));
}

function computeDynamics(sliders) {
  const push = sliders.push / 50;
  const neat = sliders.neat / 50;
  const guideBase = sliders.guide / 50;
  const breeze = sliders.breeze / 50;
  const pressure = sliders.pressure / 50;
  const noise = sliders.noise / 50;

  let flow = clamp(push - 0.28 * (breeze + noise), 0, 2);
  let order = clamp(neat + Math.max(0.32 * pressure, 0.18 * noise), 0, 2);
  let guide = clamp(guideBase + Math.max(0.28 * pressure, 0.18 * noise, 0.18 * breeze), 0, 2);

  if (order > 1.45) guide = clamp(guide + 0.18, 0, 2);
  if (guide > 1.5 && flow <= 1) flow = clamp(flow - 0.22, 0, 2);

  const wobble = clamp(Math.max(breeze, noise) + (guide > 1.45 ? 0.25 : 0) - (flow >= 1.5 ? 0.35 : 0), 0, 2);

  const jam = clamp(
    Math.max(
      flow < 0.4 ? 1.2 : 0,
      guide > 1.55 && flow < 0.9 ? 1.5 : 0,
      order > 1.6 && guide > 1.2 && flow < 1 ? 1.7 : 0,
      0
    ) + wobble * 0.35,
    0,
    2
  );

  const smooth = clamp(
    flow * 0.75 + (2 - Math.abs(order - 1)) * 0.42 + (2 - Math.abs(guide - 1)) * 0.28 - jam * 0.55,
    0,
    2
  );

  const pleasant = clamp(Math.round(54 + smooth * 18 - jam * 15), 0, 100);

  let mood = "気持ちよくつながりやすい";
  let tip = "今のままでもかなり楽しめます。";

  if (jam > 1.45) {
    mood = "考えすぎて少しつっかえやすい";
    tip = "「見守りアシスト」か「きっちり度」を少し下げると、流れが戻りやすいです。";
  } else if (flow < 0.55) {
    mood = "勢いが足りず止まりやすい";
    tip = "「ころがる勢い」を上げるか、「ざわつき」を下げるのがおすすめです。";
  } else if (order > 1.65 && pressure > 1.2) {
    mood = "きっちりしすぎで慎重モード";
    tip = "「プレッシャー」を少し下げると、くるっと決まりやすくなります。";
  } else if (smooth > 1.55) {
    mood = "かなりするする";
    tip = "このバランスは当たりです。ベルやドミノを増やすとさらに爽快です。";
  }

  return {
    raw: { push, neat, guideBase, breeze, pressure, noise },
    flow,
    order,
    guide,
    wobble,
    jam,
    smooth,
    pleasant,
    mood,
    tip,
  };
}

function moduleOffset(type, local) {
  if (local < 0 || local > 1) return 0;
  const c = Math.abs(local - 0.5) * 2;
  switch (type) {
    case "ramp":
      return -34 * (1 - c);
    case "domino":
      return -10 * (1 - c);
    case "bumper":
      return -18 * Math.sin(local * Math.PI);
    case "fan":
      return -12 * Math.sin(local * Math.PI);
    case "spinner":
      return -14 * Math.sin(local * Math.PI * 2);
    case "bell":
      return -16 * Math.sin(local * Math.PI);
    default:
      return 0;
  }
}

function trackY(x, slots) {
  const zone = 58;
  let offset = 0;
  slots.forEach((type, index) => {
    const center = SLOT_X[index];
    const local = (x - (center - zone)) / (zone * 2);
    offset += moduleOffset(type, local) * 0.8;
  });
  return STAGE.baseY + clamp(offset, -46, 16);
}

function createParticles(x, y, emoji) {
  return new Array(8).fill(0).map((_, index) => ({
    id: uid(),
    x,
    y,
    dx: Math.cos((Math.PI * 2 * index) / 8) * (1.4 + index * 0.2),
    dy: Math.sin((Math.PI * 2 * index) / 8) * (1.2 + index * 0.18) - 0.6,
    life: 1,
    emoji,
    size: 14 + (index % 3) * 2,
  }));
}

function makeInitialSim(dynamics, running = false) {
  return {
    running,
    finished: false,
    failed: false,
    x: 62,
    y: trackY(62, ["blank", "blank", "blank", "blank", "blank", "blank"]),
    vx: 150 + dynamics.flow * 62,
    score: 0,
    combo: 0,
    bestCombo: 0,
    pleasantNow: dynamics.pleasant,
    lastLine: "部品を置いて、スタートを押してください。",
    triggered: {},
    particles: [],
    pulses: [],
    stall: 0,
    history: [],
  };
}

function moduleEffect(type, dynamics, slotIndex) {
  const sparkleY = 170 + (slotIndex % 2) * 10;
  const base = {
    gain: 0,
    score: 40,
    comboAdd: 1,
    line: "いい流れです。",
    emoji: "✨",
    glowY: sparkleY,
  };

  const freezePenalty = dynamics.guide > 1.55 && dynamics.flow < 0.92 ? 26 : 0;

  switch (type) {
    case "ramp":
      return {
        ...base,
        gain: 28 + dynamics.flow * 18 + dynamics.guide * 8 - dynamics.jam * 12,
        score: 72,
        line: dynamics.flow > 1.15 ? "すーっと坂をこえた" : "コトンと坂をのぼった",
        emoji: "✨",
      };
    case "domino":
      return dynamics.flow > 0.58
        ? {
            ...base,
            gain: 30 + dynamics.flow * 12 - dynamics.jam * 8,
            score: 84,
            comboAdd: 2,
            line: "カタカタッと連鎖した",
            emoji: "🟨",
          }
        : {
            ...base,
            gain: -18,
            score: 28,
            comboAdd: 0,
            line: "ドミノが惜しくもつながりきらない",
            emoji: "💭",
          };
    case "bumper":
      return {
        ...base,
        gain: 24 + dynamics.flow * 14 + (2 - Math.abs(dynamics.order - 1)) * 8 - freezePenalty,
        score: 68,
        comboAdd: dynamics.order > 0.7 && dynamics.order < 1.7 ? 2 : 1,
        line: freezePenalty > 0 ? "ちょっと考えすぎたけど、ポンッと進んだ" : "ポンッとはずんだ",
        emoji: "💥",
      };
    case "fan":
      return {
        ...base,
        gain: 18 + dynamics.raw.breeze * 10 + dynamics.guide * 10 - dynamics.jam * 6,
        score: 62,
        line: "ふわっと風に押された",
        emoji: "💨",
      };
    case "spinner":
      return dynamics.order + dynamics.guide > 1.28
        ? {
            ...base,
            gain: 28 + dynamics.order * 10 - dynamics.jam * 8,
            score: 76,
            comboAdd: 2,
            line: "くるんと向きがそろった",
            emoji: "🌀",
          }
        : {
            ...base,
            gain: 8,
            score: 40,
            comboAdd: 1,
            line: "くるっと回った",
            emoji: "🫧",
          };
    case "bell":
      return {
        ...base,
        gain: 12 + dynamics.smooth * 8,
        score: 88,
        comboAdd: 2,
        line: "チリン、とても気持ちいい",
        emoji: "🔔",
      };
    default:
      return {
        ...base,
        gain: -2 + dynamics.flow * 2 - dynamics.jam * 4,
        score: 16,
        comboAdd: 0,
        line: "ひと息ついた",
        emoji: "▫️",
      };
  }
}

function advanceSim(state, dt, slots, dynamics) {
  if (!state.running) return state;

  let next = {
    ...state,
    particles: state.particles
      .map((p) => ({
        ...p,
        x: p.x + p.dx * dt * 60,
        y: p.y + p.dy * dt * 60,
        dy: p.dy + 0.04,
        life: p.life - dt * 1.2,
      }))
      .filter((p) => p.life > 0),
    pulses: state.pulses
      .map((p) => ({ ...p, radius: p.radius + dt * 54, life: p.life - dt * 1.4 }))
      .filter((p) => p.life > 0),
  };

  const friction = 0.9965 + dynamics.smooth * 0.0009 - dynamics.jam * 0.0017;
  next.vx = clamp(next.vx * Math.pow(friction, dt * 60) + (dynamics.flow - dynamics.jam * 0.55) * dt * 18, 65, 480);
  next.x += next.vx * dt;
  next.y = trackY(next.x, slots);
  next.pleasantNow = clamp(Math.round(dynamics.pleasant + next.combo * 3 - dynamics.jam * 8), 0, 100);

  if (next.vx < 100 && !next.finished) {
    next.stall += dt;
  } else {
    next.stall = Math.max(0, next.stall - dt * 0.5);
  }

  slots.forEach((type, index) => {
    const center = SLOT_X[index];
    if (!next.triggered[index] && next.x >= center - 6) {
      const effect = moduleEffect(type, dynamics, index);
      next.vx = clamp(next.vx + effect.gain, 60, 500);
      next.score += Math.max(0, Math.round(effect.score + effect.gain));
      next.combo += effect.comboAdd;
      next.bestCombo = Math.max(next.bestCombo, next.combo);
      next.lastLine = effect.line;
      next.history = [effect.line, ...next.history].slice(0, 5);
      next.triggered = { ...next.triggered, [index]: true };
      next.particles = [...next.particles, ...createParticles(center, next.y - 24, effect.emoji)];
      next.pulses = [...next.pulses, { id: uid(), x: center, y: next.y - 18, radius: 12, life: 1 }];
    }
  });

  if (next.x >= STAGE.goalX) {
    const finalBonus = 120 + next.bestCombo * 18 + Math.round(dynamics.smooth * 30);
    const pleasantBonus = Math.round((next.vx / 5) + dynamics.pleasant * 0.3);
    next.score += finalBonus;
    next.pleasantNow = clamp(next.pleasantNow + pleasantBonus / 6, 0, 100);
    next.lastLine = next.pleasantNow >= 88 ? "ゴール！ かなり気持ちいい一本でした" : "ゴール！ ちゃんとつながりました";
    next.finished = true;
    next.running = false;
  }

  if (!next.finished && next.stall > 2.3) {
    next.failed = true;
    next.running = false;
    next.combo = Math.max(0, next.combo - 1);
    next.lastLine = "少しつっかえました。勢いか静けさを足すと通りやすいです。";
  }

  return next;
}

function Meter({ label, value, helper, accent = "from-cyan-400 to-sky-500" }) {
  return (
    <div className="rounded-2xl bg-white/70 p-3 shadow-sm ring-1 ring-black/5 backdrop-blur">
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="font-medium text-slate-700">{label}</span>
        <span className="font-semibold text-slate-900">{value}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-200">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${accent} transition-all duration-300`}
          style={{ width: `${clamp(value, 0, 100)}%` }}
        />
      </div>
      <div className="mt-1 text-xs text-slate-500">{helper}</div>
    </div>
  );
}

function SliderRow({ label, value, onChange, left, right }) {
  return (
    <div className="rounded-2xl bg-white/70 p-3 shadow-sm ring-1 ring-black/5 backdrop-blur">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-slate-800">{label}</div>
          <div className="text-xs text-slate-500">{left} ← → {right}</div>
        </div>
        <div className="rounded-full bg-slate-900 px-2 py-1 text-xs font-semibold text-white">{value}</div>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-200 accent-sky-500"
      />
    </div>
  );
}

function ModuleButton({ module, active, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`min-w-[96px] rounded-2xl border px-3 py-3 text-left transition-all ${
        active
          ? "border-sky-400 bg-sky-50 shadow-sm"
          : "border-slate-200 bg-white/70 hover:border-slate-300 hover:bg-white"
      }`}
    >
      <div className="text-2xl">{module.emoji}</div>
      <div className="mt-1 text-sm font-semibold text-slate-800">{module.label}</div>
      <div className="text-xs text-slate-500">{module.hint}</div>
    </button>
  );
}

function drawModule(type, center, index, active) {
  const common = {
    x: center - 34,
    y: 302,
    width: 68,
    height: 64,
    rx: 20,
  };
  const glow = active ? "drop-shadow-[0_0_18px_rgba(56,189,248,0.35)]" : "";
  const label = MODULE_MAP[type]?.emoji ?? "▫️";

  return (
    <g key={`${type}-${index}`} className={glow}>
      <rect {...common} fill="rgba(255,255,255,0.68)" stroke="rgba(255,255,255,0.85)" />
      <circle cx={center} cy={264} r={18} fill="rgba(255,255,255,0.35)" />
      <text x={center} y={275} textAnchor="middle" fontSize="28">
        {label}
      </text>
      <text x={center} y={347} textAnchor="middle" fontSize="11" fill="#475569">
        {MODULE_MAP[type]?.label}
      </text>
      {type === "ramp" && <path d={`M ${center - 28} 296 L ${center + 22} 258 L ${center + 22} 296 Z`} fill="rgba(125,211,252,0.55)" />}
      {type === "domino" && (
        <g>
          {[0, 1, 2].map((n) => (
            <rect
              key={n}
              x={center - 20 + n * 13}
              y={270 - n * 3}
              width="8"
              height="26"
              rx="3"
              fill="rgba(251,191,36,0.8)"
              transform={`rotate(${n === 2 ? 14 : n === 1 ? 7 : 0} ${center - 16 + n * 13} ${283 - n * 3})`}
            />
          ))}
        </g>
      )}
      {type === "bumper" && <circle cx={center} cy={276} r={18} fill="rgba(248,113,113,0.72)" />}
      {type === "fan" && (
        <g>
          <circle cx={center} cy={278} r={8} fill="rgba(34,197,94,0.8)" />
          <path d={`M ${center} 278 L ${center + 24} 272 Q ${center + 14} 286 ${center} 278`} fill="rgba(34,197,94,0.48)" />
          <path d={`M ${center} 278 L ${center - 20} 260 Q ${center - 10} 280 ${center} 278`} fill="rgba(34,197,94,0.38)" />
          <path d={`M ${center} 278 L ${center - 8} 302 Q ${center + 6} 294 ${center} 278`} fill="rgba(34,197,94,0.28)" />
        </g>
      )}
      {type === "spinner" && (
        <g>
          <circle cx={center} cy={278} r={16} fill="rgba(168,85,247,0.24)" stroke="rgba(168,85,247,0.72)" />
          <path d={`M ${center - 16} 278 L ${center + 16} 278`} stroke="rgba(168,85,247,0.8)" strokeWidth="4" strokeLinecap="round" />
          <path d={`M ${center} 262 L ${center} 294`} stroke="rgba(168,85,247,0.8)" strokeWidth="4" strokeLinecap="round" />
        </g>
      )}
      {type === "bell" && (
        <g>
          <path d={`M ${center - 18} 290 Q ${center} 252 ${center + 18} 290 Z`} fill="rgba(251,191,36,0.72)" />
          <circle cx={center} cy={292} r={5} fill="rgba(146,64,14,0.7)" />
        </g>
      )}
    </g>
  );
}

export default function PitaSwitchFeelGame() {
  const [slots, setSlots] = useState(["ramp", "domino", "bumper", "spinner", "bell", "fan"]);
  const [selectedSlot, setSelectedSlot] = useState(0);
  const [sliders, setSliders] = useState({
    push: 70,
    neat: 58,
    guide: 50,
    breeze: 30,
    pressure: 28,
    noise: 18,
  });

  const stars = useMemo(() => makeStars(), []);
  const dynamics = useMemo(() => computeDynamics(sliders), [sliders]);
  const [sim, setSim] = useState(() => makeInitialSim(dynamics, false));
  const simRef = useRef(sim);

  useEffect(() => {
    simRef.current = sim;
  }, [sim]);

  useEffect(() => {
    if (!sim.running) return;
    let frame = 0;
    let raf = 0;
    let last = performance.now();

    const loop = (now) => {
      const dt = Math.min(0.03, (now - last) / 1000);
      last = now;
      frame += 1;
      const next = advanceSim(simRef.current, dt, slots, dynamics);
      simRef.current = next;
      if (frame % 1 === 0) setSim(next);
      if (next.running) raf = requestAnimationFrame(loop);
    };

    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [sim.running, slots, dynamics]);

  const stageBallY = sim.running || sim.finished || sim.failed ? sim.y : trackY(62, slots);

  const replaceSlot = (moduleId) => {
    setSlots((prev) => prev.map((slot, idx) => (idx === selectedSlot ? moduleId : slot)));
  };

  const randomCourse = () => {
    const pool = ["ramp", "domino", "bumper", "fan", "spinner", "bell", "blank"];
    const next = SLOT_X.map(() => pool[Math.floor(Math.random() * pool.length)]);
    setSlots(next);
    setSelectedSlot(0);
  };

  const recommendedCourse = () => {
    const soft = dynamics.jam > 1.25;
    setSlots(soft ? ["fan", "ramp", "spinner", "bell", "blank", "bell"] : ["ramp", "domino", "bumper", "spinner", "bell", "fan"]);
    setSim(makeInitialSim(dynamics, false));
  };

  const tidyBalance = () => {
    setSliders((prev) => ({
      ...prev,
      push: 72,
      neat: 56,
      guide: 44,
      breeze: 24,
      pressure: 22,
      noise: 14,
    }));
  };

  const startRun = () => {
    const fresh = makeInitialSim(dynamics, true);
    fresh.y = trackY(fresh.x, slots);
    fresh.lastLine = "スタート。ころころ進みます。";
    setSim(fresh);
    simRef.current = fresh;
  };

  const resetRun = () => {
    const fresh = makeInitialSim(dynamics, false);
    fresh.y = trackY(fresh.x, slots);
    setSim(fresh);
    simRef.current = fresh;
  };

  const finishScore = clamp(Math.round((sim.score * 0.32) + sim.pleasantNow * 0.85 + sim.bestCombo * 6), 0, 100);

  return (
    <div className="min-h-screen w-full bg-[radial-gradient(circle_at_top,_#dff6ff,_#f8fbff_42%,_#eef2ff)] p-5 text-slate-900">
      <div className="mx-auto grid max-w-7xl gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-5">
          <div className="rounded-[28px] bg-white/75 p-5 shadow-[0_20px_80px_rgba(148,163,184,0.18)] ring-1 ring-white/70 backdrop-blur">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold text-sky-700">
                  ① 部品をえらぶ ② スライダーを動かす ③ スタート
                </div>
                <h1 className="mt-3 text-3xl font-black tracking-tight text-slate-900">ころころピタっと工房</h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                  小さな仕掛けを並べて、玉が気持ちよくゴールする流れをつくるゲームです。
                  難しい言葉はなしで、勢い・整い方・見守り具合をスライダーで触れます。
                </p>
              </div>
              <div className="grid min-w-[240px] gap-2 sm:grid-cols-2">
                <button
                  onClick={recommendedCourse}
                  className="rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:-translate-y-0.5 hover:bg-slate-800"
                >
                  いい感じに整える
                </button>
                <button
                  onClick={randomCourse}
                  className="rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-slate-700 ring-1 ring-slate-200 transition hover:-translate-y-0.5"
                >
                  おまかせ配置
                </button>
                <button
                  onClick={startRun}
                  className="rounded-2xl bg-gradient-to-r from-cyan-500 to-sky-500 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:-translate-y-0.5"
                >
                  スタート
                </button>
                <button
                  onClick={resetRun}
                  className="rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-slate-700 ring-1 ring-slate-200 transition hover:-translate-y-0.5"
                >
                  リセット
                </button>
              </div>
            </div>

            <div className="mt-5 overflow-hidden rounded-[28px] bg-gradient-to-br from-sky-200/85 via-cyan-100/80 to-indigo-100/90 p-3 shadow-inner ring-1 ring-white/60">
              <div className="relative overflow-hidden rounded-[24px] bg-[linear-gradient(180deg,rgba(255,255,255,0.4),rgba(255,255,255,0.18))]">
                <svg viewBox={`0 0 ${STAGE.width} ${STAGE.height}`} className="h-[430px] w-full">
                  <defs>
                    <linearGradient id="trackGrad" x1="0" x2="1">
                      <stop offset="0%" stopColor="#0ea5e9" />
                      <stop offset="100%" stopColor="#6366f1" />
                    </linearGradient>
                    <linearGradient id="groundGrad" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stopColor="rgba(255,255,255,0.7)" />
                      <stop offset="100%" stopColor="rgba(255,255,255,0.14)" />
                    </linearGradient>
                  </defs>

                  <rect x="0" y="0" width={STAGE.width} height={STAGE.height} fill="url(#groundGrad)" />
                  {stars.map((star) => (
                    <circle key={star.id} cx={star.x} cy={star.y} r={star.r} fill="white" opacity={star.opacity} />
                  ))}

                  <rect x="38" y="314" width="820" height="40" rx="20" fill="rgba(255,255,255,0.45)" />
                  <path d={`M 50 ${STAGE.baseY} L 850 ${STAGE.baseY}`} stroke="url(#trackGrad)" strokeWidth="10" strokeLinecap="round" />
                  <path d={`M 50 ${STAGE.baseY + 20} L 850 ${STAGE.baseY + 20}`} stroke="rgba(255,255,255,0.6)" strokeWidth="4" strokeLinecap="round" />

                  <circle cx="64" cy={STAGE.baseY} r="26" fill="rgba(255,255,255,0.72)" />
                  <text x="64" y={STAGE.baseY + 7} textAnchor="middle" fontSize="28">🏁</text>

                  <rect x="838" y="212" width="28" height="88" rx="12" fill="rgba(15,23,42,0.12)" />
                  <circle cx="852" cy="210" r="24" fill="rgba(255,255,255,0.82)" />
                  <text x="852" y="218" textAnchor="middle" fontSize="24">🎯</text>

                  {slots.map((type, index) => drawModule(type, SLOT_X[index], index, sim.triggered[index]))}

                  {sim.pulses.map((pulse) => (
                    <circle
                      key={pulse.id}
                      cx={pulse.x}
                      cy={pulse.y}
                      r={pulse.radius}
                      fill="none"
                      stroke="rgba(255,255,255,0.75)"
                      strokeWidth="3"
                      opacity={pulse.life}
                    />
                  ))}

                  {sim.particles.map((particle) => (
                    <text
                      key={particle.id}
                      x={particle.x}
                      y={particle.y}
                      fontSize={particle.size}
                      textAnchor="middle"
                      opacity={particle.life}
                    >
                      {particle.emoji}
                    </text>
                  ))}

                  <circle cx={sim.running || sim.finished || sim.failed ? sim.x : 62} cy={stageBallY - 10} r="14" fill="rgba(15,23,42,0.18)" />
                  <circle cx={sim.running || sim.finished || sim.failed ? sim.x : 62} cy={stageBallY - 18} r="18" fill="white" opacity="0.4" />
                  <circle cx={sim.running || sim.finished || sim.failed ? sim.x : 62} cy={stageBallY - 22} r="16" fill="#fde68a" />
                  <circle cx={(sim.running || sim.finished || sim.failed ? sim.x : 62) - 5} cy={stageBallY - 28} r="4" fill="white" opacity="0.85" />
                </svg>

                <div className="absolute left-4 top-4 rounded-2xl bg-white/72 px-4 py-3 shadow-sm ring-1 ring-white/80 backdrop-blur">
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">いまのひとこと</div>
                  <div className="mt-1 text-sm font-semibold text-slate-900">{sim.lastLine}</div>
                </div>

                <div className="absolute bottom-4 left-4 right-4 grid gap-3 md:grid-cols-4">
                  <div className="rounded-2xl bg-white/70 p-3 shadow-sm ring-1 ring-white/80 backdrop-blur">
                    <div className="text-xs text-slate-500">つながりスコア</div>
                    <div className="text-2xl font-black text-slate-900">{sim.score}</div>
                  </div>
                  <div className="rounded-2xl bg-white/70 p-3 shadow-sm ring-1 ring-white/80 backdrop-blur">
                    <div className="text-xs text-slate-500">気持ちよさ</div>
                    <div className="text-2xl font-black text-slate-900">{finishScore}</div>
                  </div>
                  <div className="rounded-2xl bg-white/70 p-3 shadow-sm ring-1 ring-white/80 backdrop-blur">
                    <div className="text-xs text-slate-500">最高コンボ</div>
                    <div className="text-2xl font-black text-slate-900">{sim.bestCombo}</div>
                  </div>
                  <div className="rounded-2xl bg-white/70 p-3 shadow-sm ring-1 ring-white/80 backdrop-blur">
                    <div className="text-xs text-slate-500">今のムード</div>
                    <div className="text-base font-bold text-slate-900">{scoreBand(finishScore)}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-[28px] bg-white/75 p-5 shadow-[0_20px_80px_rgba(148,163,184,0.18)] ring-1 ring-white/70 backdrop-blur">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-black text-slate-900">部品を並べる</h2>
                <p className="text-sm text-slate-500">まず、どの位置を変えるか選びます。</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {slots.map((slot, idx) => (
                  <button
                    key={idx}
                    onClick={() => setSelectedSlot(idx)}
                    className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                      selectedSlot === idx
                        ? "bg-slate-900 text-white"
                        : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                    }`}
                  >
                    {idx + 1}番目：{MODULE_MAP[slot].emoji}
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              {MODULES.map((module) => (
                <ModuleButton
                  key={module.id}
                  module={module}
                  active={slots[selectedSlot] === module.id}
                  onClick={() => replaceSlot(module.id)}
                />
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-5">
          <div className="rounded-[28px] bg-white/75 p-5 shadow-[0_20px_80px_rgba(148,163,184,0.18)] ring-1 ring-white/70 backdrop-blur">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-black text-slate-900">スライダー調整</h2>
                <p className="text-sm text-slate-500">数値はその場で反映されます。動かしながら探るのがおすすめです。</p>
              </div>
              <button
                onClick={tidyBalance}
                className="rounded-2xl bg-sky-50 px-4 py-2 text-sm font-semibold text-sky-700 ring-1 ring-sky-200 transition hover:bg-sky-100"
              >
                バランスおすすめ
              </button>
            </div>

            <div className="mt-4 grid gap-3">
              <SliderRow
                label="ころがる勢い"
                value={sliders.push}
                onChange={(value) => setSliders((prev) => ({ ...prev, push: value }))}
                left="おっとり"
                right="ぐいぐい"
              />
              <SliderRow
                label="きっちり度"
                value={sliders.neat}
                onChange={(value) => setSliders((prev) => ({ ...prev, neat: value }))}
                left="ゆるめ"
                right="かっちり"
              />
              <SliderRow
                label="見守りアシスト"
                value={sliders.guide}
                onChange={(value) => setSliders((prev) => ({ ...prev, guide: value }))}
                left="おまかせ"
                right="見守る"
              />
              <SliderRow
                label="風の強さ"
                value={sliders.breeze}
                onChange={(value) => setSliders((prev) => ({ ...prev, breeze: value }))}
                left="しずか"
                right="ふわふわ"
              />
              <SliderRow
                label="プレッシャー"
                value={sliders.pressure}
                onChange={(value) => setSliders((prev) => ({ ...prev, pressure: value }))}
                left="気楽"
                right="気になる"
              />
              <SliderRow
                label="ざわつき"
                value={sliders.noise}
                onChange={(value) => setSliders((prev) => ({ ...prev, noise: value }))}
                left="すっきり"
                right="ごちゃごちゃ"
              />
            </div>
          </div>

          <div className="rounded-[28px] bg-white/75 p-5 shadow-[0_20px_80px_rgba(148,163,184,0.18)] ring-1 ring-white/70 backdrop-blur">
            <h2 className="text-xl font-black text-slate-900">今のバランス</h2>
            <p className="mt-1 text-sm text-slate-500">内部の難しい計算は見せずに、触り心地だけをわかりやすく見せています。</p>
            <div className="mt-4 grid gap-3">
              <Meter label="すすみやすさ" value={Math.round(dynamics.flow * 50)} helper="高いほど前へ行きやすい" accent="from-emerald-400 to-cyan-500" />
              <Meter label="そろいやすさ" value={Math.round(dynamics.order * 50)} helper="高いほどカチッと決まりやすい" accent="from-amber-400 to-orange-500" />
              <Meter label="見守り感" value={Math.round(dynamics.guide * 50)} helper="高すぎると慎重になりすぎることも" accent="from-violet-400 to-fuchsia-500" />
              <Meter label="つっかえやすさ" value={Math.round(dynamics.jam * 50)} helper="高いと途中で止まりやすい" accent="from-rose-400 to-red-500" />
            </div>
            <div className="mt-4 rounded-2xl bg-slate-900 px-4 py-4 text-white shadow-sm">
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">ひとことガイド</div>
              <div className="mt-2 text-lg font-bold">{dynamics.mood}</div>
              <div className="mt-1 text-sm leading-6 text-slate-300">{dynamics.tip}</div>
            </div>
          </div>

          <div className="rounded-[28px] bg-white/75 p-5 shadow-[0_20px_80px_rgba(148,163,184,0.18)] ring-1 ring-white/70 backdrop-blur">
            <h2 className="text-xl font-black text-slate-900">遊び方メモ</h2>
            <div className="mt-3 grid gap-3 text-sm leading-6 text-slate-600">
              <div className="rounded-2xl bg-slate-50 p-3">勢いが足りないときは「ころがる勢い」を上げるか、「ざわつき」を下げると通りやすくなります。</div>
              <div className="rounded-2xl bg-slate-50 p-3">「見守りアシスト」と「きっちり度」が高すぎると、慎重になりすぎて途中でつっかえることがあります。</div>
              <div className="rounded-2xl bg-slate-50 p-3">ベルやドミノをうまくつなぐと、気持ちよさが一気に伸びます。</div>
            </div>
            {sim.history.length > 0 && (
              <div className="mt-4 rounded-2xl bg-sky-50 p-4 ring-1 ring-sky-100">
                <div className="text-sm font-semibold text-sky-900">今回の流れ</div>
                <div className="mt-2 space-y-2 text-sm text-sky-900">
                  {sim.history.map((line, idx) => (
                    <div key={`${line}-${idx}`} className="rounded-xl bg-white/80 px-3 py-2">{line}</div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
