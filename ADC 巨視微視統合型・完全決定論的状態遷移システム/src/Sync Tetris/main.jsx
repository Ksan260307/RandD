import React, { useState, useEffect, useCallback, useRef } from 'react';
import { initializeApp } from 'firebase/app';
import { getAuth, signInAnonymously, onAuthStateChanged, signInWithCustomToken } from 'firebase/auth';
import { getFirestore, doc, setDoc, onSnapshot, updateDoc, getDoc, increment, deleteDoc } from 'firebase/firestore';

// --- ADC Infrastructure Setup ---
const firebaseConfig = JSON.parse(__firebase_config);
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);
const appId = typeof __app_id !== 'undefined' ? __app_id : 'adc-tetris-core';

// --- Sound Engine (Web Audio API 8-bit Synthesizer) ---
let audioCtx;
let isPlayingBGM = false;
let nextNoteTime = 0;
let currentNote = 0;
let bgmTimer;

const melody = [
    { n: 76, d: 1 }, { n: 71, d: 0.5 }, { n: 72, d: 0.5 }, { n: 74, d: 1 },
    { n: 72, d: 0.5 }, { n: 71, d: 0.5 }, { n: 69, d: 1 }, { n: 69, d: 0.5 },
    { n: 72, d: 0.5 }, { n: 76, d: 1 }, { n: 74, d: 0.5 }, { n: 72, d: 0.5 },
    { n: 71, d: 1.5 }, { n: 72, d: 0.5 }, { n: 74, d: 1 }, { n: 76, d: 1 },
    { n: 72, d: 1 }, { n: 69, d: 1 }, { n: 69, d: 2 },
    { n: 74, d: 1.5 }, { n: 77, d: 0.5 }, { n: 81, d: 1 }, { n: 79, d: 0.5 }, { n: 77, d: 0.5 },
    { n: 76, d: 1.5 }, { n: 72, d: 0.5 }, { n: 76, d: 1 }, { n: 74, d: 0.5 }, { n: 72, d: 0.5 },
    { n: 71, d: 1 }, { n: 71, d: 0.5 }, { n: 72, d: 0.5 }, { n: 74, d: 1 }, { n: 76, d: 1 },
    { n: 72, d: 1 }, { n: 69, d: 1 }, { n: 69, d: 2 }
];

const playBGMStep = () => {
    if (!isPlayingBGM || !audioCtx) return;
    while (nextNoteTime < audioCtx.currentTime + 0.1) {
        const note = melody[currentNote];
        const freq = 440 * Math.pow(2, (note.n - 69) / 12);
        const duration = note.d * 0.35; 
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'square';
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.015, nextNoteTime); 
        gain.gain.exponentialRampToValueAtTime(0.001, nextNoteTime + duration - 0.05);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(nextNoteTime);
        osc.stop(nextNoteTime + duration);
        nextNoteTime += duration;
        currentNote = (currentNote + 1) % melody.length;
    }
    bgmTimer = setTimeout(playBGMStep, 25);
};

export const SoundEngine = {
    init: () => {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') audioCtx.resume();
    },
    setBGM: (play) => {
        if (play === isPlayingBGM) return;
        isPlayingBGM = play;
        if (play && audioCtx) {
            nextNoteTime = audioCtx.currentTime + 0.1;
            currentNote = 0;
            playBGMStep();
        } else {
            clearTimeout(bgmTimer);
        }
    },
    playSE: (type) => {
        if (!audioCtx || audioCtx.state === 'suspended') return;
        const t = audioCtx.currentTime;
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);

        if (type === 'move') {
            osc.type = 'square';
            osc.frequency.setValueAtTime(300, t);
            gain.gain.setValueAtTime(0.02, t);
            gain.gain.exponentialRampToValueAtTime(0.001, t + 0.05);
            osc.start(t); osc.stop(t + 0.05);
        } else if (type === 'rotate') {
            osc.type = 'square';
            osc.frequency.setValueAtTime(400, t);
            osc.frequency.setValueAtTime(500, t + 0.02);
            gain.gain.setValueAtTime(0.03, t);
            gain.gain.exponentialRampToValueAtTime(0.001, t + 0.05);
            osc.start(t); osc.stop(t + 0.05);
        } else if (type === 'drop') {
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(400, t);
            osc.frequency.exponentialRampToValueAtTime(50, t + 0.1);
            gain.gain.setValueAtTime(0.08, t);
            gain.gain.linearRampToValueAtTime(0, t + 0.1);
            osc.start(t); osc.stop(t + 0.1);
        } else if (type === 'clear') {
            osc.type = 'square';
            osc.frequency.setValueAtTime(600, t);
            osc.frequency.setValueAtTime(800, t + 0.05);
            gain.gain.setValueAtTime(0.08, t);
            gain.gain.linearRampToValueAtTime(0, t + 0.15);
            osc.start(t); osc.stop(t + 0.15);
        } else if (type === 'skill') {
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(800, t);
            osc.frequency.linearRampToValueAtTime(1200, t + 0.2);
            gain.gain.setValueAtTime(0.1, t);
            gain.gain.linearRampToValueAtTime(0, t + 0.2);
            osc.start(t); osc.stop(t + 0.2);
        } else if (type === 'gameover') {
            osc.type = 'sawtooth';
            osc.frequency.setValueAtTime(200, t);
            osc.frequency.linearRampToValueAtTime(50, t + 1.0);
            gain.gain.setValueAtTime(0.2, t);
            gain.gain.linearRampToValueAtTime(0, t + 1.0);
            osc.start(t); osc.stop(t + 1.0);
        } else if (type === 'hold') {
            osc.type = 'sine';
            osc.frequency.setValueAtTime(500, t);
            gain.gain.setValueAtTime(0.05, t);
            gain.gain.linearRampToValueAtTime(0, t + 0.1);
            osc.start(t); osc.stop(t + 0.1);
        }
    }
};

// --- Visual Effects Styles ---
const STYLES = `
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-4px) rotate(-1deg); }
  50% { transform: translateX(4px) rotate(1deg); }
  75% { transform: translateX(-4px) rotate(-1deg); }
}
.animate-shake { animation: shake 0.15s ease-in-out; }
@keyframes flash {
  0% { background-color: rgba(255, 255, 255, 0.8); box-shadow: inset 0 0 50px rgba(255,255,255,0.9); }
  100% { background-color: transparent; box-shadow: none; }
}
.animate-flash { animation: flash 0.3s ease-out forwards; }
@keyframes pop-in {
  0% { transform: scale(0.5); opacity: 0; }
  70% { transform: scale(1.1); opacity: 1; }
  100% { transform: scale(1); opacity: 1; }
}
.animate-pop { animation: pop-in 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards; }
@keyframes glitch {
  0% { transform: translate(0) }
  20% { transform: translate(-5px, 5px) }
  40% { transform: translate(-5px, -5px) }
  60% { transform: translate(5px, 5px) }
  80% { transform: translate(5px, -5px) }
  100% { transform: translate(0) }
}
.animate-glitch { animation: glitch 0.2s cubic-bezier(.25, .46, .45, .94) both; filter: hue-rotate(90deg) contrast(150%); }
@keyframes rewind {
  0% { filter: invert(0) grayscale(0); transform: scale(1); }
  50% { filter: invert(1) grayscale(1); transform: scale(0.95); }
  100% { filter: invert(0) grayscale(0); transform: scale(1); }
}
.animate-rewind { animation: rewind 0.5s ease-out forwards; }
`;

// --- Core Constants & Dimensional Definitions ---
const COLS = 10;
const ROWS = 20;

const TETROMINOS = {
  'I': { shape: [[1,1,1,1]], color: 'bg-[#2CB4AD]' }, 
  'J': { shape: [[1,0,0],[1,1,1]], color: 'bg-[#005AFF]' }, 
  'L': { shape: [[0,0,1],[1,1,1]], color: 'bg-[#F6AA00]' }, 
  'O': { shape: [[1,1],[1,1]], color: 'bg-[#FFF100]' }, 
  'S': { shape: [[0,1,1],[1,1,0]], color: 'bg-[#03AF7A]' }, 
  'T': { shape: [[0,1,0],[1,1,1]], color: 'bg-[#990099]' }, 
  'Z': { shape: [[1,1,0],[0,1,1]], color: 'bg-[#FF4B00]' }, 
  'G': { shape: [[1]], color: 'bg-neutral-500' } 
};
const SHAPES = ['I', 'J', 'L', 'O', 'S', 'T', 'Z'];

class PRNG {
  constructor(seed) { this.seed = seed; }
  next() {
    this.seed = (this.seed * 1664525 + 1013904223) % 4294967296;
    return this.seed / 4294967296;
  }
}

const emptyBoard = Array(ROWS).fill(null).map(() => Array(COLS).fill(""));

const createPieceObj = (type) => ({
  id: Math.random().toString(36).substring(2, 9),
  type,
  shape: TETROMINOS[type].shape,
  x: Math.floor(COLS / 2) - Math.floor(TETROMINOS[type].shape[0].length / 2),
  y: 0,
  rotIndex: 0
});

const initEngine = (prng) => {
  const nextPieces = [
    SHAPES[Math.floor(prng.next() * SHAPES.length)],
    SHAPES[Math.floor(prng.next() * SHAPES.length)],
    SHAPES[Math.floor(prng.next() * SHAPES.length)],
  ];
  return {
    board: emptyBoard,
    piece: createPieceObj(SHAPES[Math.floor(prng.next() * SHAPES.length)]),
    nextPieces,
    holdPiece: null,
    canHold: true,
    score: 0,
    totalLines: 0,
    sp: 1,
    gameOver: false,
    lastGarbageHole: Math.floor(prng.next() * COLS)
  };
};

const isValidMove = (board, piece, dx, dy, newShape = piece.shape) => {
  for (let y = 0; y < newShape.length; y++) {
    for (let x = 0; x < newShape[y].length; x++) {
      if (newShape[y][x]) {
        const newY = piece.y + y + dy;
        const newX = piece.x + x + dx;
        if (newY < 0 || newY >= ROWS || newX < 0 || newX >= COLS || (board[newY] && board[newY][newX] !== "")) {
          return false;
        }
      }
    }
  }
  return true;
};

const evaluateBoard = (board) => {
  let aggregateHeight = 0, holes = 0, bumpiness = 0;
  const heights = new Array(COLS).fill(0);
  for (let c = 0; c < COLS; c++) {
    for (let r = 0; r < ROWS; r++) {
      if (board[r][c] !== "") { heights[c] = ROWS - r; break; }
    }
    aggregateHeight += heights[c];
  }
  for (let c = 0; c < COLS; c++) {
    let blockFound = false;
    for (let r = 0; r < ROWS; r++) {
      if (board[r][c] !== "") blockFound = true;
      else if (blockFound) holes++;
    }
  }
  for (let c = 0; c < COLS - 1; c++) { bumpiness += Math.abs(heights[c] - heights[c + 1]); }
  const completeLines = board.filter(row => row.every(cell => cell !== "")).length;
  return -0.510066 * aggregateHeight + 0.760666 * completeLines - 0.35663 * holes - 0.184483 * bumpiness;
};

const calculateBestMove = (engine, level) => {
  const candidates = [];
  const { board, piece, holdPiece, nextPieces, canHold } = engine;
  if (!piece) return null;
  const evalMove = (p, isHold) => {
    let currentShape = p.shape;
    for (let rot = 0; rot < 4; rot++) {
      for (let x = -2; x < COLS + 2; x++) {
        let tempPiece = { ...p, shape: currentShape, x: x, y: 0 };
        if (isValidMove(board, tempPiece, 0, 0)) {
          let dy = 0;
          while (isValidMove(board, tempPiece, 0, dy + 1)) dy++;
          tempPiece.y += dy;
          const newBoard = board.map(row => [...row]);
          tempPiece.shape.forEach((row, py) => {
            row.forEach((cell, px) => {
              if (cell) {
                const by = tempPiece.y + py, bx = tempPiece.x + px;
                if (by >= 0 && by < ROWS && bx >= 0 && bx < COLS) newBoard[by][bx] = tempPiece.type;
              }
            });
          });
          const score = evaluateBoard(newBoard);
          candidates.push({ x, rotation: rot, score, useHold: isHold });
        }
      }
      currentShape = currentShape[0].map((val, index) => currentShape.map(row => row[index]).reverse());
    }
  };
  evalMove(piece, false);
  if (canHold) {
    const holdP = createPieceObj(holdPiece || nextPieces[0]);
    evalMove(holdP, true);
  }
  if (candidates.length === 0) return { x: 0, rotation: 0, useHold: false };
  candidates.sort((a, b) => b.score - a.score);
  let selectedIndex = 0;
  if (level === 1) selectedIndex = Math.floor(Math.random() * candidates.length); 
  else if (level === 2) selectedIndex = Math.floor(Math.random() * Math.min(10, candidates.length)); 
  else if (level === 3) selectedIndex = Math.floor(Math.random() * Math.min(3, candidates.length)); 
  return candidates[selectedIndex];
};

const getGhostY = (board, piece) => {
  if (!piece) return 0;
  let dy = 0;
  while (isValidMove(board, piece, 0, dy + 1)) dy++;
  return piece.y + dy;
};

const getDisplayBoard = (board, piece) => {
  const newBoard = board.map(row => [...row]);
  if (!piece) return newBoard;
  const ghostY = getGhostY(board, piece);
  piece.shape.forEach((row, y) => {
    row.forEach((cell, x) => {
      if (cell) {
        const boardY = y + ghostY, boardX = x + piece.x;
        if (boardY >= 0 && boardY < ROWS && boardX >= 0 && boardX < COLS && newBoard[boardY][boardX] === "") {
          newBoard[boardY][boardX] = piece.type + '_GHOST';
        }
      }
    });
  });
  piece.shape.forEach((row, y) => {
    row.forEach((cell, x) => {
      if (cell) {
        const boardY = y + piece.y, boardX = x + piece.x;
        if (boardY >= 0 && boardY < ROWS && boardX >= 0 && boardX < COLS) {
          newBoard[boardY][boardX] = piece.type;
        }
      }
    });
  });
  return newBoard;
};

// --- Main App Component ---
export default function App() {
  const [user, setUser] = useState(null);
  const [sessionId] = useState(() => Math.random().toString(36).substring(2, 10));
  const [gameState, setGameState] = useState('menu');
  const [roomId, setRoomId] = useState('');
  const [pwdInput, setPwdInput] = useState('');
  const [isHost, setIsHost] = useState(false);
  const [message, setMessage] = useState('');
  const [gameResult, setGameResult] = useState(null);
  const [cpuLevel, setCpuLevel] = useState(3);
  const [skillsEnabled, setSkillsEnabled] = useState(true);
  const [forceJoin, setForceJoin] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [isSoftDropping, setIsSoftDropping] = useState(false);
  
  // Game Engines & PRNG
  const prngRef = useRef(new PRNG(12345));
  const [engine, setEngine] = useState(() => initEngine(new PRNG(12345)));
  const engineRef = useRef(engine);
  const isHostRef = useRef(isHost);
  const soundEnabledRef = useRef(soundEnabled);
  
  // History Tracker
  const historyRef = useRef([]);
  const cpuHistoryRef = useRef([]);

  // Effects & Skills
  const [boardShake, setBoardShake] = useState(false);
  const [boardFlash, setBoardFlash] = useState(false);
  const [visualEffect, setVisualEffect] = useState(null);
  const [oppVisualEffect, setOppVisualEffect] = useState(null);
  const [activeEffect, setActiveEffect] = useState(null);
  const scoreRef = useRef(0);
  const lastProcessedEffectIdRef = useRef(null);
  
  // Cooldown Tracking
  const playerCooldownRef = useRef(0);
  const cpuCooldownRef = useRef(0);
  const [playerCooldownRemaining, setPlayerCooldownRemaining] = useState(0);

  // Network roles & states
  const myRole = isHost ? 'HOST' : 'CLIENT';
  const oppRole = isHost ? 'CLIENT' : 'HOST';
  const isFrozen = activeEffect?.type === 'FREEZE' && activeEffect.target === myRole;
  const isOppFrozen = activeEffect?.type === 'FREEZE' && activeEffect.target === oppRole;
  const isAccel = activeEffect?.type === 'ACCEL';
  const isFrozenRef = useRef(isFrozen);

  const [pendingGarbage, setPendingGarbage] = useState(0);
  const [cpuPendingGarbage, setCpuPendingGarbage] = useState(0); 
  const processedGarbageRef = useRef(0);
  const cpuPrngRef = useRef(new PRNG(99999));
  const [cpuEngine, setCpuEngine] = useState(() => initEngine(new PRNG(99999)));
  const [opponentState, setOpponentState] = useState(null);
  const cpuTargetRef = useRef(null);

  const gameStateRef = useRef(gameState);

  // Touch handling refs
  const touchRef = useRef({ startX: 0, startY: 0, lastX: 0, lastY: 0, moved: false, startTime: 0, hardDropped: false });

  useEffect(() => { gameStateRef.current = gameState; }, [gameState]);
  useEffect(() => { engineRef.current = engine; }, [engine]);
  useEffect(() => { isHostRef.current = isHost; }, [isHost]);
  useEffect(() => { isFrozenRef.current = isFrozen; }, [isFrozen]);
  useEffect(() => { soundEnabledRef.current = soundEnabled; }, [soundEnabled]);

  // Audio BGM controller
  useEffect(() => {
    if (soundEnabled && (gameState === 'playing' || gameState === 'waiting') && !gameResult) {
      SoundEngine.setBGM(true);
    } else {
      SoundEngine.setBGM(false);
    }
  }, [soundEnabled, gameState, gameResult]);

  // Auth Init
  useEffect(() => {
    const initAuth = async () => {
      try {
        if (typeof __initial_auth_token !== 'undefined' && __initial_auth_token) await signInWithCustomToken(auth, __initial_auth_token);
        else await signInAnonymously(auth);
      } catch (e) { console.error("Auth Error:", e); }
    };
    initAuth();
    const unsubscribe = onAuthStateChanged(auth, setUser);
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    const handleBeforeUnload = () => {
      if (roomId) {
        const docRef = doc(db, 'artifacts', appId, 'public', 'data', 'tetris_rooms', roomId);
        if (isHostRef.current) deleteDoc(docRef).catch(()=>{});
        else updateDoc(docRef, { clientUid: null, status: 'waiting' }).catch(()=>{});
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [roomId]);

  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      const pRem = Math.max(0, playerCooldownRef.current - now);
      setPlayerCooldownRemaining(prev => (prev > 0 || pRem > 0) ? pRem : prev);
    }, 50);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (gameState === 'playing' || gameState === 'waiting') {
      historyRef.current.push({ state: engine, time: Date.now() });
      if (historyRef.current.length > 500) historyRef.current.shift();
    }
  }, [engine, gameState]);

  useEffect(() => {
    if (gameState === 'waiting') {
      cpuHistoryRef.current.push({ state: cpuEngine, time: Date.now() });
      if (cpuHistoryRef.current.length > 500) cpuHistoryRef.current.shift();
    }
  }, [cpuEngine, gameState]);

  useEffect(() => {
    if (activeEffect) {
      const timeToExpiry = activeEffect.expiresAt - Date.now();
      if (timeToExpiry > 0) {
        const t = setTimeout(() => {
          setActiveEffect(null);
          if (isHostRef.current && roomId) updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'tetris_rooms', roomId), { activeEffect: null }).catch(()=>{});
        }, timeToExpiry);
        return () => clearTimeout(t);
      } else setActiveEffect(null);
    }
  }, [activeEffect, roomId]);

  // --- Core Game Mechanics ---
  const lockAndSpawn = (prev, prng, setGarbageOut = null) => {
    const newBoard = prev.board.map(row => [...row]);
    prev.piece.shape.forEach((row, y) => {
      row.forEach((cell, x) => {
        if (cell) {
          const by = prev.piece.y + y, bx = prev.piece.x + x;
          if (by >= 0 && by < ROWS) newBoard[by][bx] = prev.piece.type;
        }
      });
    });

    if (prev.piece.y <= 0) return { ...prev, board: newBoard, gameOver: true };

    const filteredBoard = newBoard.filter(row => row.some(cell => cell === ""));
    const linesCleared = ROWS - filteredBoard.length;
    const emptyRows = Array(linesCleared).fill(null).map(() => Array(COLS).fill(""));
    const finalBoard = [...emptyRows, ...filteredBoard];

    if (linesCleared > 1 && setGarbageOut) setGarbageOut(g => g + (linesCleared === 4 ? 4 : linesCleared - 1));

    const nextType = prev.nextPieces[0];
    const newNextPieces = [...prev.nextPieces.slice(1), SHAPES[Math.floor(prng.next() * SHAPES.length)]];
    const newTotalLines = prev.totalLines + linesCleared;
    const gainedSp = Math.floor(newTotalLines / 30) - Math.floor(prev.totalLines / 30);

    return {
      ...prev, board: finalBoard, piece: createPieceObj(nextType), nextPieces: newNextPieces,
      canHold: true, score: prev.score + (linesCleared * 100 * linesCleared),
      totalLines: newTotalLines, sp: prev.sp + gainedSp
    };
  };

  const addGarbage = (prev, amount) => {
    const newBoard = prev.board.map(row => [...row]);
    let currentHole = prev.lastGarbageHole !== undefined ? prev.lastGarbageHole : Math.floor(Math.random() * COLS);
    for (let i = 0; i < amount; i++) {
      newBoard.shift();
      if (Math.random() > 0.7) currentHole = Math.floor(Math.random() * COLS);
      const garbageRow = Array(COLS).fill("G");
      garbageRow[currentHole] = "";
      newBoard.push(garbageRow);
    }
    return { ...prev, board: newBoard, piece: { ...prev.piece, y: Math.max(0, prev.piece.y - amount) }, lastGarbageHole: currentHole };
  };

  const movePiece = (prev, dx, dy, prng, setGarbageOut) => {
    if (prev.gameOver) return prev;
    if (isValidMove(prev.board, prev.piece, dx, dy)) return { ...prev, piece: { ...prev.piece, x: prev.piece.x + dx, y: prev.piece.y + dy } };
    if (dy > 0) return lockAndSpawn(prev, prng, setGarbageOut);
    return prev;
  };

  const rotatePiece = (prev) => {
    if (prev.gameOver) return prev;
    const rotatedShape = prev.piece.shape[0].map((val, index) => prev.piece.shape.map(row => row[index]).reverse());
    const nextRotIndex = ((prev.piece.rotIndex || 0) + 1) % 4;
    if (isValidMove(prev.board, prev.piece, 0, 0, rotatedShape)) return { ...prev, piece: { ...prev.piece, shape: rotatedShape, rotIndex: nextRotIndex } };
    if (isValidMove(prev.board, prev.piece, -1, 0, rotatedShape)) return { ...prev, piece: { ...prev.piece, shape: rotatedShape, x: prev.piece.x - 1, rotIndex: nextRotIndex } };
    if (isValidMove(prev.board, prev.piece, 1, 0, rotatedShape)) return { ...prev, piece: { ...prev.piece, shape: rotatedShape, x: prev.piece.x + 1, rotIndex: nextRotIndex } };
    return prev;
  };

  const hardDrop = (prev, prng, setGarbageOut) => {
    if (prev.gameOver) return prev;
    let dy = 0;
    while (isValidMove(prev.board, prev.piece, 0, dy + 1)) dy++;
    const droppedState = { ...prev, piece: { ...prev.piece, y: prev.piece.y + dy } };
    return lockAndSpawn(droppedState, prng, setGarbageOut);
  };

  const holdCurrentPiece = (prev, prng) => {
    if (prev.gameOver || !prev.canHold) return prev;
    const currentType = prev.piece.type;
    let nextType, newNextPieces;
    if (prev.holdPiece) {
      nextType = prev.holdPiece; newNextPieces = prev.nextPieces;
    } else {
      nextType = prev.nextPieces[0]; newNextPieces = [...prev.nextPieces.slice(1), SHAPES[Math.floor(prng.next() * SHAPES.length)]];
    }
    return { ...prev, piece: createPieceObj(nextType), nextPieces: newNextPieces, holdPiece: currentType, canHold: false };
  };

  // --- Skill Activation ---
  const activateSkill = useCallback((skillType) => {
    if (!skillsEnabled || (gameState !== 'playing' && gameState !== 'waiting')) return;
    if (engineRef.current.sp < 1 || gameResult || isFrozenRef.current || Date.now() < playerCooldownRef.current) return;
    
    setEngine(prev => ({ ...prev, sp: prev.sp - 1 }));
    const now = Date.now();
    playerCooldownRef.current = now + 15000;
    if (soundEnabledRef.current) setTimeout(() => SoundEngine.playSE('skill'), 0);

    const docRef = roomId ? doc(db, 'artifacts', appId, 'public', 'data', 'tetris_rooms', roomId) : null;
    const effectPayload = { type: skillType, id: now, sender: myRole };

    if (skillType === 'REWIND') {
      setVisualEffect('REWIND'); setOppVisualEffect('REWIND');
      setTimeout(() => { setVisualEffect(null); setOppVisualEffect(null); }, 500);
      const targetTime = now - 10000;
      const pastState = historyRef.current.find(h => h.time >= targetTime) || historyRef.current[0];
      if (pastState) setEngine(prev => ({ ...pastState.state, sp: prev.sp, totalLines: prev.totalLines }));

      if (gameState === 'waiting') {
        const pastCpu = cpuHistoryRef.current.find(h => h.time >= targetTime) || cpuHistoryRef.current[0];
        if (pastCpu) setCpuEngine(pastCpu.state);
      } else {
        effectPayload.target = 'ALL'; effectPayload.expiresAt = now + 1500;
        if (docRef) updateDoc(docRef, { activeEffect: effectPayload }).catch(()=>{});
      }
    } 
    else if (skillType === 'ERASE') {
      setVisualEffect('ERASE'); setOppVisualEffect('ERASE');
      setTimeout(() => { setVisualEffect(null); setOppVisualEffect(null); }, 500);
      setEngine(prev => {
        let futureState = { ...prev };
        for(let i=0; i<3; i++) {
          futureState = movePiece(futureState, prngRef.current.next() > 0.5 ? 1 : -1, 0, prngRef.current, setPendingGarbage);
          if(prngRef.current.next() > 0.5) futureState = rotatePiece(futureState);
          futureState = hardDrop(futureState, prngRef.current, setPendingGarbage);
        }
        return futureState;
      });

      if (gameState === 'waiting') {
        setCpuEngine(prev => {
          let futureState = { ...prev };
          for(let i=0; i<3; i++) {
            futureState = movePiece(futureState, cpuPrngRef.current.next() > 0.5 ? 1 : -1, 0, cpuPrngRef.current, null);
            if(cpuPrngRef.current.next() > 0.5) futureState = rotatePiece(futureState);
            futureState = hardDrop(futureState, cpuPrngRef.current, null);
          }
          return futureState;
        });
      } else {
        effectPayload.target = 'ALL'; effectPayload.expiresAt = now + 1500;
        if (docRef) updateDoc(docRef, { activeEffect: effectPayload }).catch(()=>{});
      }
    }
    else if (skillType === 'FREEZE') {
      effectPayload.target = oppRole; effectPayload.expiresAt = now + 5000;
      if (docRef) updateDoc(docRef, { activeEffect: effectPayload }).catch(()=>{});
    }
    else if (skillType === 'ACCEL') {
      effectPayload.target = 'ALL'; effectPayload.expiresAt = now + 8000;
      if (docRef) updateDoc(docRef, { activeEffect: effectPayload }).catch(()=>{});
    }
  }, [gameState, gameResult, oppRole, roomId, myRole, skillsEnabled]);

  const activateCpuSkill = useCallback((skillType) => {
    if (!skillsEnabled || gameState !== 'waiting' || gameResult || isOppFrozen || Date.now() < cpuCooldownRef.current) return;
    const now = Date.now();
    cpuCooldownRef.current = now + 15000;
    setCpuEngine(prev => ({ ...prev, sp: prev.sp - 1 }));

    if (skillType === 'REWIND') {
      setVisualEffect('REWIND'); setOppVisualEffect('REWIND');
      setTimeout(() => { setVisualEffect(null); setOppVisualEffect(null); }, 500);
      const targetTime = now - 10000;
      const pastState = historyRef.current.find(h => h.time >= targetTime) || historyRef.current[0];
      if (pastState) setEngine(prev => ({ ...pastState.state, sp: prev.sp, totalLines: prev.totalLines }));
      const pastCpu = cpuHistoryRef.current.find(h => h.time >= targetTime) || cpuHistoryRef.current[0];
      if (pastCpu) setCpuEngine(prev => ({ ...pastCpu.state, sp: prev.sp, totalLines: prev.totalLines }));
    } 
    else if (skillType === 'ERASE') {
      setVisualEffect('ERASE'); setOppVisualEffect('ERASE');
      setTimeout(() => { setVisualEffect(null); setOppVisualEffect(null); }, 500);
      setEngine(prev => {
        let futureState = { ...prev };
        for(let i=0; i<3; i++) {
          futureState = movePiece(futureState, prngRef.current.next() > 0.5 ? 1 : -1, 0, prngRef.current, setPendingGarbage);
          if(prngRef.current.next() > 0.5) futureState = rotatePiece(futureState);
          futureState = hardDrop(futureState, prngRef.current, setPendingGarbage);
        }
        return futureState;
      });
      setCpuEngine(prev => {
        let futureState = { ...prev };
        for(let i=0; i<3; i++) {
          futureState = movePiece(futureState, cpuPrngRef.current.next() > 0.5 ? 1 : -1, 0, cpuPrngRef.current, null);
          if(cpuPrngRef.current.next() > 0.5) futureState = rotatePiece(futureState);
          futureState = hardDrop(futureState, cpuPrngRef.current, null);
        }
        return futureState;
      });
    }
    else if (skillType === 'FREEZE') setActiveEffect({ type: 'FREEZE', target: myRole, expiresAt: now + 5000, sender: oppRole });
    else if (skillType === 'ACCEL') setActiveEffect({ type: 'ACCEL', target: 'ALL', expiresAt: now + 8000, sender: oppRole });
  }, [gameState, gameResult, myRole, oppRole, skillsEnabled, isOppFrozen]);

  // --- Input Handling & Sound Triggering ---
  const handleInput = useCallback((action) => {
    if (gameState !== 'playing' && gameState !== 'waiting') return;
    if (engineRef.current.gameOver || gameResult || isFrozenRef.current) return;

    if (action === 'DROP') { setBoardShake(true); setTimeout(() => setBoardShake(false), 150); }

    setEngine(prev => {
      let nextState = prev;
      let seType = null;

      switch(action) {
        case 'LEFT': 
          nextState = movePiece(prev, -1, 0, prngRef.current, null); 
          if (nextState.piece.x !== prev.piece.x) seType = 'move';
          break;
        case 'RIGHT': 
          nextState = movePiece(prev, 1, 0, prngRef.current, null); 
          if (nextState.piece.x !== prev.piece.x) seType = 'move';
          break;
        case 'DOWN': 
          nextState = movePiece(prev, 0, 1, prngRef.current, setPendingGarbage); 
          break;
        case 'ROTATE': 
          nextState = rotatePiece(prev); 
          if (nextState.piece.rotIndex !== prev.piece.rotIndex) seType = 'rotate';
          break;
        case 'DROP': 
          nextState = hardDrop(prev, prngRef.current, setPendingGarbage); 
          seType = 'drop';
          break;
        case 'HOLD': 
          nextState = holdCurrentPiece(prev, prngRef.current); 
          if (!prev.holdPiece || nextState.holdPiece !== prev.holdPiece) seType = 'hold';
          break;
        default: return prev;
      }

      if (nextState.totalLines > prev.totalLines) seType = 'clear';
      if (soundEnabledRef.current && seType) setTimeout(() => SoundEngine.playSE(seType), 0);

      return nextState;
    });
  }, [gameState, gameResult]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' '].includes(e.key)) e.preventDefault();
      if (e.key === 'ArrowLeft') handleInput('LEFT');
      if (e.key === 'ArrowRight') handleInput('RIGHT');
      if (e.key === 'ArrowDown') {
        setIsSoftDropping(true);
        if (!e.repeat) handleInput('DOWN');
      }
      if (e.key === 'ArrowUp') handleInput('ROTATE');
      if (e.key === ' ') handleInput('DROP');
      if (e.key.toLowerCase() === 'z' || e.key.toLowerCase() === 'x') handleInput('ROTATE');
      if (e.key === 'Shift' || e.key.toLowerCase() === 'c') handleInput('HOLD');
      
      if (skillsEnabled && Date.now() >= playerCooldownRef.current) {
        if (e.key === '1') activateSkill('REWIND');
        if (e.key === '2') activateSkill('ERASE');
        if (e.key === '3') activateSkill('FREEZE');
        if (e.key === '4') activateSkill('ACCEL');
      }
    };
    const handleKeyUp = (e) => {
      if (e.key === 'ArrowDown') setIsSoftDropping(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [handleInput, activateSkill, skillsEnabled]);

  // --- Touch Control Handlers (Swipe & Tap) ---
  const handleTouchStart = useCallback((e) => {
    if (gameState !== 'playing' && gameState !== 'waiting') return;
    if (e.target.closest('button') || e.target.closest('input')) return;
    const touch = e.touches[0];
    touchRef.current = {
      startX: touch.clientX, startY: touch.clientY,
      lastX: touch.clientX, lastY: touch.clientY,
      moved: false, startTime: Date.now(), hardDropped: false
    };
  }, [gameState]);

  const handleTouchMove = useCallback((e) => {
    if (gameState !== 'playing' && gameState !== 'waiting') return;
    if (e.target.closest('button') || e.target.closest('input')) return;
    if (touchRef.current.hardDropped) return;
    
    const touch = e.touches[0];
    const { startX, startY, lastX, lastY, startTime } = touchRef.current;
    const dx = touch.clientX - lastX;
    const dy = touch.clientY - lastY;
    const totalDy = touch.clientY - startY;
    const duration = Date.now() - startTime;

    if (Math.abs(touch.clientX - startX) > 10 || Math.abs(touch.clientY - startY) > 10) {
      touchRef.current.moved = true;
    }

    // Flick UP for Hard Drop
    if (totalDy < -40 && duration < 300) {
      handleInput('DROP');
      touchRef.current.hardDropped = true;
      return;
    }

    if (Math.abs(dx) > 30) {
      if (dx > 0) handleInput('RIGHT'); else handleInput('LEFT');
      touchRef.current.lastX = touch.clientX;
    }

    if (dy > 30) {
      handleInput('DOWN');
      touchRef.current.lastY = touch.clientY;
    }
  }, [gameState, handleInput]);

  const handleTouchEnd = useCallback((e) => {
    if (gameState !== 'playing' && gameState !== 'waiting') return;
    if (e.target.closest('button') || e.target.closest('input')) return;
    if (touchRef.current.hardDropped) return;

    const touch = e.changedTouches[0];
    const { moved, startTime } = touchRef.current;
    const duration = Date.now() - startTime;

    if (!moved && duration < 300) {
      const { innerWidth } = window;
      if (touch.clientX < innerWidth / 3) {
        handleInput('LEFT');
      } else if (touch.clientX > (innerWidth * 2) / 3) {
        handleInput('RIGHT');
      } else {
        handleInput('ROTATE'); 
      }
    }
  }, [gameState, handleInput]);


  useEffect(() => {
    if (engine.score > scoreRef.current) {
      setBoardFlash(true);
      const t = setTimeout(() => setBoardFlash(false), 300);
      scoreRef.current = engine.score;
      return () => clearTimeout(t);
    } else if (engine.score === 0) scoreRef.current = 0;
  }, [engine.score]);

  useEffect(() => {
    if (gameState === 'playing') {
      if (engine.gameOver) {
        setGameResult('LOSE');
        if (soundEnabledRef.current) setTimeout(() => SoundEngine.playSE('gameover'), 0);
      }
      else if (opponentState?.gameOver) {
        setGameResult('WIN');
        if (soundEnabledRef.current) setTimeout(() => SoundEngine.playSE('gameover'), 0);
      }
    }
  }, [engine.gameOver, opponentState?.gameOver, gameState]);

  // --- Gravity (Tick Engine) ---
  useEffect(() => {
    if (gameState !== 'playing' && gameState !== 'waiting') return;
    if (gameResult || isFrozen) return;
    
    let tickRate = isAccel ? 150 : 800; 
    if (isSoftDropping) tickRate = 40; 

    const interval = setInterval(() => handleInput('DOWN'), tickRate);
    return () => clearInterval(interval);
  }, [gameState, gameResult, isFrozen, isAccel, isSoftDropping, handleInput]);

  // --- CPU Heuristic Brain ---
  useEffect(() => {
    if (gameState !== 'waiting' || gameResult || isOppFrozen) return;
    
    const TICK_RATES = { 1: 800, 2: 500, 3: 250, 4: 100, 5: 40 };
    const tickRate = isAccel ? 100 : TICK_RATES[cpuLevel] || 250;

    const interval = setInterval(() => {
      setCpuEngine(prev => {
        if (prev.gameOver) { cpuTargetRef.current = null; return initEngine(cpuPrngRef.current); }
        let newState = prev;

        if (skillsEnabled && newState.sp > 0 && Date.now() >= cpuCooldownRef.current) {
          let cpuHeight = 0;
          for (let r = 0; r < ROWS; r++) {
            if (newState.board[r].some(cell => cell !== "")) { cpuHeight = ROWS - r; break; }
          }
          if (cpuHeight > 12) {
             const skill = Math.random() > 0.5 ? 'REWIND' : 'ERASE';
             setTimeout(() => activateCpuSkill(skill), 0); 
          } else if (Math.random() < 0.05) { 
             const skill = Math.random() > 0.5 ? 'FREEZE' : 'ACCEL';
             setTimeout(() => activateCpuSkill(skill), 0);
          }
        }
        
        if (!cpuTargetRef.current || cpuTargetRef.current.pieceId !== newState.piece.id) {
           const target = calculateBestMove(newState, cpuLevel);
           cpuTargetRef.current = { ...target, pieceId: newState.piece.id, hasHeld: false };
        }
        
        const target = cpuTargetRef.current;
        if (target) {
          let moved = false;
          if (target.useHold && !target.hasHeld) {
             newState = holdCurrentPiece(newState, cpuPrngRef.current);
             target.hasHeld = true; target.pieceId = newState.piece.id; moved = true;
          }
          if (!moved) {
            if ((newState.piece.rotIndex || 0) !== target.rotation) {
               const rotated = rotatePiece(newState);
               if (rotated.piece.shape !== newState.piece.shape) { newState = rotated; moved = true; }
            }
            if (!moved && newState.piece.x > target.x) {
               const left = movePiece(newState, -1, 0, cpuPrngRef.current, null);
               if (left.piece.x !== newState.piece.x) { newState = left; moved = true; }
            }
            if (!moved && newState.piece.x < target.x) {
               const right = movePiece(newState, 1, 0, cpuPrngRef.current, null);
               if (right.piece.x !== newState.piece.x) { newState = right; moved = true; }
            }
            if (!moved) {
               if ((newState.piece.rotIndex || 0) === target.rotation && newState.piece.x === target.x) {
                   newState = hardDrop(newState, cpuPrngRef.current, setCpuPendingGarbage);
               } else {
                   newState = movePiece(newState, 0, 1, cpuPrngRef.current, null);
               }
            }
          }
        } else {
           newState = movePiece(newState, 0, 1, cpuPrngRef.current, null); 
        }
        return newState;
      });
    }, tickRate);
    return () => clearInterval(interval);
  }, [gameState, gameResult, isOppFrozen, isAccel, cpuLevel, skillsEnabled, activateCpuSkill]);

  // --- Local CPU Combat (Garbage Exchange) ---
  useEffect(() => {
    if (gameState === 'waiting' && pendingGarbage > 0) {
      setCpuEngine(prev => addGarbage(prev, pendingGarbage));
      setPendingGarbage(0);
    }
  }, [pendingGarbage, gameState]);

  useEffect(() => {
    if (gameState === 'waiting' && cpuPendingGarbage > 0) {
      setEngine(prev => addGarbage(prev, cpuPendingGarbage));
      setCpuPendingGarbage(0);
    }
  }, [cpuPendingGarbage, gameState]);

  // --- Network Connections ---
  const handleConnect = async () => {
    if (!user) { setMessage("Auth processing, please wait."); return; }
    if (pwdInput.length !== 5) { setMessage("Hash must be exactly 5 characters."); return; }
    
    setMessage("Syncing...");
    const docRef = doc(db, 'artifacts', appId, 'public', 'data', 'tetris_rooms', pwdInput);
    const playerId = `${user.uid}_${sessionId}`;
    
    try {
      const snap = await getDoc(docRef);
      const initialSeed = Math.floor(Math.random() * 1000000);
      
      processedGarbageRef.current = 0;
      setPendingGarbage(0); setCpuPendingGarbage(0);
      setGameResult(null); setActiveEffect(null);
      historyRef.current = []; cpuHistoryRef.current = [];
      lastProcessedEffectIdRef.current = null; cpuTargetRef.current = null;
      playerCooldownRef.current = 0; cpuCooldownRef.current = 0;

      if (!snap.exists() || forceJoin) {
        await setDoc(docRef, {
          password: pwdInput, hostUid: playerId, clientUid: null,
          seed: initialSeed, status: 'waiting', skillsEnabled: skillsEnabled,
          hostState: null, clientState: null, hostGarbage: 0, clientGarbage: 0, activeEffect: null
        });
        setIsHost(true); prngRef.current = new PRNG(initialSeed);
        setEngine(initEngine(prngRef.current)); setCpuEngine(initEngine(cpuPrngRef.current));
        setGameState('waiting'); setForceJoin(false);
      } else {
        const data = snap.data();
        if (data.hostUid !== playerId && !data.clientUid) {
          await updateDoc(docRef, { clientUid: playerId, status: 'playing' });
          setIsHost(false); prngRef.current = new PRNG(data.seed);
          setSkillsEnabled(data.skillsEnabled !== false);
          setEngine(initEngine(prngRef.current)); setGameState('playing');
        } else if (data.hostUid === playerId || data.clientUid === playerId) {
          setIsHost(data.hostUid === playerId); prngRef.current = new PRNG(data.seed);
          setSkillsEnabled(data.skillsEnabled !== false);
          setEngine(initEngine(prngRef.current)); setGameState(data.status);
        } else {
          setMessage("Room is full. Click again to force overwrite.");
          setForceJoin(true); return;
        }
      }
      setRoomId(pwdInput); setMessage("");
    } catch (err) { setMessage("Connection failed."); }
  };

  const handleLeaveMatch = async () => {
    if (roomId) {
      try {
        const docRef = doc(db, 'artifacts', appId, 'public', 'data', 'tetris_rooms', roomId);
        if (isHostRef.current) await deleteDoc(docRef);
        else await updateDoc(docRef, { clientUid: null, status: 'waiting' });
      } catch (e) {}
    }
    setGameState('menu'); setRoomId(''); setOpponentState(null); setGameResult(null); setActiveEffect(null);
    lastProcessedEffectIdRef.current = null; cpuTargetRef.current = null;
    playerCooldownRef.current = 0; cpuCooldownRef.current = 0; setForceJoin(false);
    setMessage(isHostRef.current ? 'Room closed.' : 'Left the room.');
    setEngine(initEngine(prngRef.current));
  };

  // --- Network Listeners ---
  useEffect(() => {
    if (!user || !roomId) return;
    const docRef = doc(db, 'artifacts', appId, 'public', 'data', 'tetris_rooms', roomId);
    const unsubscribe = onSnapshot(docRef, (snap) => {
      if (!snap.exists()) {
        if (gameStateRef.current !== 'menu') {
          setGameState('menu'); setRoomId(''); setOpponentState(null); setGameResult(null); setActiveEffect(null);
          setMessage("Room was closed by opponent.");
        }
        return;
      }
      const data = snap.data();
      if (data.status === 'playing' && gameStateRef.current === 'waiting') {
        prngRef.current = new PRNG(data.seed);
        setEngine(initEngine(prngRef.current));
        setGameResult(null); setGameState('playing'); playerCooldownRef.current = 0;
      }
      if (gameStateRef.current === 'playing' && data.status === 'waiting') {
        setGameState('menu'); setRoomId(''); setOpponentState(null); setGameResult(null); setActiveEffect(null);
        lastProcessedEffectIdRef.current = null; setMessage("Opponent left the room."); return;
      }
      if (data.activeEffect) {
        const isNew = data.activeEffect.id !== lastProcessedEffectIdRef.current;
        if (isNew) {
          lastProcessedEffectIdRef.current = data.activeEffect.id;
          const effect = data.activeEffect;
          const myCurrentRole = isHostRef.current ? 'HOST' : 'CLIENT';
          const isTarget = effect.target === 'ALL' || effect.target === myCurrentRole;
          const isSender = effect.sender === myCurrentRole;

          if (isTarget && !isSender) {
            if (soundEnabledRef.current) setTimeout(() => SoundEngine.playSE('skill'), 0);
            if (effect.type === 'REWIND') {
              setVisualEffect('REWIND'); setOppVisualEffect('REWIND');
              setTimeout(() => { setVisualEffect(null); setOppVisualEffect(null); }, 500);
              const targetTime = Date.now() - 10000;
              const pastState = historyRef.current.find(h => h.time >= targetTime) || historyRef.current[0];
              if (pastState) setEngine(prev => ({ ...pastState.state, sp: prev.sp, totalLines: prev.totalLines }));
            } else if (effect.type === 'ERASE') {
              setVisualEffect('ERASE'); setOppVisualEffect('ERASE');
              setTimeout(() => { setVisualEffect(null); setOppVisualEffect(null); }, 500);
              setEngine(prev => {
                let futureState = { ...prev };
                for(let i=0; i<3; i++) {
                  futureState = movePiece(futureState, prngRef.current.next() > 0.5 ? 1 : -1, 0, prngRef.current, setPendingGarbage);
                  if(prngRef.current.next() > 0.5) futureState = rotatePiece(futureState);
                  futureState = hardDrop(futureState, prngRef.current, setPendingGarbage);
                }
                return futureState;
              });
            }
          }
        }
        if (data.activeEffect.expiresAt && data.activeEffect.expiresAt > Date.now()) setActiveEffect(data.activeEffect);
        else if (!data.activeEffect.expiresAt || data.activeEffect.expiresAt <= Date.now()) setActiveEffect(null);
      } else { setActiveEffect(null); }

      const isHostLocal = isHostRef.current;
      const oppStateStr = isHostLocal ? data.clientState : data.hostState;
      if (oppStateStr) {
        try {
          const parsed = JSON.parse(oppStateStr);
          setOpponentState({ 
            board: parsed.b.map(row => row.split("").map(c => c === "0" ? "" : c)), 
            score: parsed.s, gameOver: parsed.g, holdPiece: parsed.h || null,
            nextPieces: parsed.n ? parsed.n.split("") : [], sp: parsed.sp || 0, totalLines: parsed.tl || 0
          });
        } catch(e) {}
      }

      const myGarbage = isHostLocal ? data.hostGarbage : data.clientGarbage;
      if (myGarbage > processedGarbageRef.current) {
        const diff = myGarbage - processedGarbageRef.current;
        processedGarbageRef.current = myGarbage;
        setEngine(prev => addGarbage(prev, diff));
      }
    });
    return () => unsubscribe();
  }, [user, roomId]);

  useEffect(() => {
    if (gameState !== 'playing' || !roomId) return;
    const interval = setInterval(() => {
      const isHostLocal = isHostRef.current;
      const compressedBoard = getDisplayBoard(engineRef.current.board, engineRef.current.piece)
        .map(row => row.map(c => (c && !c.includes('_GHOST')) ? c.charAt(0) : "0").join(""));
      const stateStr = JSON.stringify({
        b: compressedBoard, s: engineRef.current.score, g: engineRef.current.gameOver,
        h: engineRef.current.holdPiece || "", n: engineRef.current.nextPieces.join(""),
        sp: engineRef.current.sp, tl: engineRef.current.totalLines
      });
      updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'tetris_rooms', roomId), { 
        [isHostLocal ? 'hostState' : 'clientState']: stateStr 
      }).catch(() => {});
    }, 500);
    return () => clearInterval(interval);
  }, [gameState, roomId]);

  useEffect(() => {
    if (pendingGarbage > 0 && roomId && gameState === 'playing') {
      const targetRole = isHostRef.current ? 'clientGarbage' : 'hostGarbage';
      updateDoc(doc(db, 'artifacts', appId, 'public', 'data', 'tetris_rooms', roomId), { [targetRole]: increment(pendingGarbage) }).catch(()=>{});
      setPendingGarbage(0);
    }
  }, [pendingGarbage, roomId, gameState]);

  // --- Render Utilities ---
  const Block = ({ type }) => {
    const sizeClasses = "w-[14px] h-[14px] min-[375px]:w-[18px] min-[375px]:h-[18px] sm:w-[22px] sm:h-[22px] md:w-[24px] md:h-[24px]";
    if (!type || type === "") return <div className={`${sizeClasses} border border-neutral-800/40 bg-neutral-900/40`} />;
    const isGhost = type.includes('_GHOST');
    const baseType = isGhost ? type.replace('_GHOST', '') : type;
    const info = TETROMINOS[baseType] || TETROMINOS['G'];
    let pattern = null;
    
    if (baseType === 'J') pattern = <div className="w-2 h-2 bg-white/40 rounded-full" />;
    else if (baseType === 'L') pattern = <div className="w-full h-1 bg-white/40" />;
    else if (baseType === 'O') pattern = <div className="w-3 h-3 border-2 border-white/50" />;
    else if (baseType === 'S') pattern = <div className="w-0 h-0 border-l-[6px] border-r-[6px] border-b-[10px] border-l-transparent border-r-transparent border-b-white/40" />;
    else if (baseType === 'T') pattern = <div className="w-3 h-3 bg-white/40 rotate-45" />;
    else if (baseType === 'Z') pattern = <div className="w-full h-full bg-[linear-gradient(45deg,transparent_40%,rgba(255,255,255,0.4)_40%,rgba(255,255,255,0.4)_60%,transparent_60%)]" />;
    else if (baseType === 'G') pattern = <div className="w-full h-full bg-[repeating-linear-gradient(45deg,transparent,transparent_2px,rgba(0,0,0,0.6)_2px,rgba(0,0,0,0.6)_4px)]" />;

    return <div className={`${sizeClasses} border ${isGhost ? 'border-white/30 bg-white/10' : 'border-black/50 ' + info.color} flex items-center justify-center shadow-inner overflow-hidden`}>{!isGhost && pattern}</div>;
  };

  const BoardDisplay = ({ boardData }) => (
    <div className="bg-black border-2 border-neutral-700 p-1 shadow-2xl relative">
      {boardData.map((row, y) => <div key={y} className="flex">{row.map((cell, x) => <Block key={`${x}-${y}`} type={cell} />)}</div>)}
    </div>
  );

  const MiniBoard = ({ type, label }) => {
    const shape = type ? TETROMINOS[type].shape : null;
    return (
      <div className="flex flex-col items-center">
        <div className="text-[8px] md:text-[10px] text-neutral-500 mb-1 tracking-wider font-bold">{label}</div>
        <div className="flex flex-col items-center justify-center bg-neutral-900/50 border border-neutral-800 p-1 min-h-[2.5rem] min-w-[2.5rem] md:min-h-[3rem] md:min-w-[3rem]">
          {shape ? shape.map((row, y) => (
            <div key={y} className="flex">
              {row.map((cell, x) => cell ? <div key={`${x}-${y}`} className={`w-[8px] h-[8px] min-[375px]:w-[10px] min-[375px]:h-[10px] md:w-3 md:h-3 border border-black/50 ${TETROMINOS[type].color} shadow-inner`} /> : <div key={`${x}-${y}`} className="w-[8px] h-[8px] min-[375px]:w-[10px] min-[375px]:h-[10px] md:w-3 md:h-3" />)}
            </div>
          )) : <div className="text-neutral-700 text-xs">-</div>}
        </div>
      </div>
    );
  };

  const PlayerPanel = ({ title, board, score, holdPiece, nextPieces, isYou, localGameOverVisible, isPanelFrozen, isPanelAccel, vEffect, sp, onHoldClick, opponentPanel, mobileSkillButtons }) => (
    <div className={`flex flex-col items-center p-1 md:p-4 border-neutral-800 ${isYou ? 'md:border-l' : 'md:border-r'} ${isPanelAccel ? 'shadow-[inset_0_0_50px_rgba(249,115,22,0.15)] border-orange-500/50' : ''} w-full`}>
       <div className="flex justify-between items-center w-full max-w-[260px] md:max-w-[300px] mb-1 md:mb-4 px-2">
         <h2 className="text-[10px] md:text-sm text-[#2CB4AD] tracking-widest uppercase font-bold">{title}</h2>
         {skillsEnabled && <div className="text-[8px] md:text-[10px] font-bold bg-neutral-800 px-2 py-0.5 rounded text-neutral-300 border border-neutral-700">SP: <span className="text-cyan-400 text-xs">{sp}</span></div>}
       </div>
       
       <div className="flex gap-1 md:gap-4 items-start w-full px-1 justify-center">
         {/* HOLD Area */}
         <div className="flex-1 flex flex-col items-end pt-1 md:pt-4 relative min-w-[50px]">
            <MiniBoard type={holdPiece} label="HOLD" />
            {isYou && (
              <button 
                onClick={(e) => { e.stopPropagation(); onHoldClick && onHoldClick(); }}
                className="md:hidden mt-2 w-full max-w-[2.5rem] min-[375px]:max-w-[3.5rem] bg-blue-900/80 active:bg-blue-800 text-white font-bold py-1.5 rounded text-[8px] shadow-lg border border-blue-500/50 pointer-events-auto"
              >
                HOLD
              </button>
            )}
            {/* 変更箇所: 相手盤面をHOLDボタンの真下に配置 */}
            {isYou && opponentPanel && (
              <div className="md:hidden mt-4 w-full flex justify-end">
                 <div className="origin-top-right scale-[0.22] opacity-80 pointer-events-none w-[200px]">
                   {opponentPanel}
                 </div>
              </div>
            )}
         </div>

         {/* Main Board */}
         <div className={`shrink-0 relative ${isYou && boardShake ? 'animate-shake' : ''} ${vEffect === 'REWIND' ? 'animate-rewind' : ''} ${vEffect === 'ERASE' ? 'animate-glitch' : ''}`}>
           <BoardDisplay boardData={board} />
           {isYou && boardFlash && <div className="absolute inset-0 animate-flash pointer-events-none" />}
           {isPanelFrozen && <div className="absolute inset-0 bg-blue-900/40 backdrop-blur-[1px] flex items-center justify-center border-2 border-blue-400 z-10"><div className="bg-black/80 px-2 py-1 text-blue-300 font-bold tracking-widest text-[10px] md:text-sm border border-blue-500 animate-pulse">TIME STOPPED</div></div>}
           {localGameOverVisible && (
              <div className="absolute inset-0 bg-black/80 flex flex-col items-center justify-center text-red-500 border border-red-500 backdrop-blur-sm z-20">
                <span className="font-bold tracking-widest mb-2 text-center text-[10px] md:text-sm">SYSTEM HALTED</span>
                {isYou && <button onClick={() => setEngine(initEngine(prngRef.current))} className="px-3 py-1 md:px-4 md:py-2 bg-neutral-800 text-white text-[10px] md:text-xs hover:bg-neutral-700 rounded border border-neutral-600 pointer-events-auto">REBOOT</button>}
              </div>
           )}
         </div>

         {/* NEXT Area */}
         <div className="flex-1 flex flex-col gap-1 md:gap-2 items-start pt-1 md:pt-4 min-w-[50px]">
           <MiniBoard type={nextPieces && nextPieces[0]} label="NEXT" />
           <MiniBoard type={nextPieces && nextPieces[1]} label="" />
           <MiniBoard type={nextPieces && nextPieces[2]} label="" />
         </div>
       </div>

       <div className="mt-1 md:mt-4 text-[11px] md:text-sm text-neutral-500 tracking-wider font-bold text-center">
         SCORE: <br className="md:hidden"/><span className="text-[#F6AA00] text-lg md:text-2xl">{score}</span>
       </div>
       
       {isYou && mobileSkillButtons && (
          <div className="md:hidden w-full px-2 mt-2">
            {mobileSkillButtons}
          </div>
       )}
    </div>
  );

  const playerDisplayBoard = getDisplayBoard(engine.board, engine.piece);
  let leftBoard = emptyBoard, leftScore = 0, leftStatus = `CPU (LEVEL ${cpuLevel})`, leftHold = null, leftNext = [], leftSp = 0;
  if (gameState === 'waiting') {
    leftBoard = getDisplayBoard(cpuEngine.board, cpuEngine.piece); leftScore = cpuEngine.score; leftHold = cpuEngine.holdPiece; leftNext = cpuEngine.nextPieces; leftSp = cpuEngine.sp || 0;
  } else if (gameState === 'playing' && opponentState) {
    leftBoard = opponentState.board; leftScore = opponentState.score; leftHold = opponentState.holdPiece; leftNext = opponentState.nextPieces; leftSp = opponentState.sp || 0; leftStatus = "PLAYER 2 (OPPONENT)";
  }

  const isCoolingDown = playerCooldownRemaining > 0;

  const opponentUI = (gameState === 'playing' || gameState === 'waiting') ? (
    <PlayerPanel title={leftStatus} board={leftBoard} score={leftScore} holdPiece={leftHold} nextPieces={leftNext} sp={leftSp} isYou={false} localGameOverVisible={false} isPanelFrozen={isOppFrozen} isPanelAccel={isAccel} vEffect={oppVisualEffect} />
  ) : null;

  const mobileSkillButtonsUI = skillsEnabled ? (
    <div className="flex justify-between gap-1 w-full max-w-[260px] mx-auto pointer-events-auto">
      <button onClick={(e) => { e.stopPropagation(); activateSkill('REWIND'); }} disabled={engine.sp < 1 || isFrozen || isCoolingDown} className="flex-1 bg-blue-900/80 disabled:opacity-50 p-1.5 rounded text-[9px] text-white font-bold border border-blue-500/30">⏪ REW</button>
      <button onClick={(e) => { e.stopPropagation(); activateSkill('ERASE'); }} disabled={engine.sp < 1 || isFrozen || isCoolingDown} className="flex-1 bg-purple-900/80 disabled:opacity-50 p-1.5 rounded text-[9px] text-white font-bold border border-purple-500/30">⏭️ ERA</button>
      <button onClick={(e) => { e.stopPropagation(); activateSkill('FREEZE'); }} disabled={engine.sp < 1 || isFrozen || isCoolingDown} className="flex-1 bg-teal-900/80 disabled:opacity-50 p-1.5 rounded text-[9px] text-white font-bold border border-teal-500/30">⏸️ FRZ</button>
      <button onClick={(e) => { e.stopPropagation(); activateSkill('ACCEL'); }} disabled={engine.sp < 1 || isFrozen || isCoolingDown} className="flex-1 bg-orange-900/80 disabled:opacity-50 p-1.5 rounded text-[9px] text-white font-bold border border-orange-500/30">⏩ ACC</button>
    </div>
  ) : null;

  return (
    <>
      <style>{STYLES}</style>
      <div 
        className={`flex flex-col md:flex-row h-[100dvh] w-full bg-[#0a0a0a] text-[#d4d4d4] font-sans overflow-hidden select-none relative ${(gameState === 'playing' || gameState === 'waiting') ? 'touch-none' : ''}`}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        
        {/* Fullscreen Win/Lose Overlay */}
        {gameResult && (
          <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-black/80 backdrop-blur-md pointer-events-auto">
             <div className={`animate-pop text-6xl md:text-8xl font-black tracking-tighter mb-4 ${gameResult === 'WIN' ? 'text-yellow-400 drop-shadow-[0_0_30px_rgba(250,204,21,0.6)]' : 'text-red-500 drop-shadow-[0_0_30px_rgba(239,68,68,0.6)]'}`}>YOU {gameResult}</div>
             <button onClick={handleLeaveMatch} className="px-6 py-3 bg-neutral-900 text-white font-bold tracking-widest hover:bg-neutral-800 transition-colors border border-neutral-700 rounded shadow-lg pointer-events-auto">RETURN TO MENU</button>
          </div>
        )}

        {/* --- PC Left Panel (Opponent) --- */}
        <div className="hidden md:flex flex-1 flex-col items-center justify-center p-4 border-r border-neutral-800">
           {opponentUI}
        </div>

        {/* --- Center Menu / Status Panel --- */}
        <div className={
          gameState === 'menu'
            ? 'absolute inset-0 z-50 flex flex-col items-center justify-center bg-[#0a0a0a] overflow-y-auto'
            : 'w-full md:w-80 flex flex-col items-center p-4 sm:p-6 z-10 shrink-0 bg-transparent md:bg-[#111] absolute top-1 md:relative md:top-auto pointer-events-none justify-start md:justify-center'
        }>
           <div className={`text-center mb-4 pointer-events-auto ${gameState !== 'menu' && 'hidden md:block'}`}>
             <h1 className="text-2xl sm:text-3xl font-black text-[#2CB4AD] mb-1 tracking-tighter">SYNC TETRIS</h1>
             <div className="text-[10px] sm:text-xs text-neutral-600 uppercase tracking-widest">Real-time Synchronized Puzzle</div>
           </div>

           {gameState === 'menu' && (
             <div className="w-full max-w-sm flex flex-col gap-4 pointer-events-auto my-auto p-6 bg-[#111] border border-neutral-800 rounded-xl shadow-[0_0_40px_rgba(44,180,173,0.1)]">
               <div className="text-center mb-4">
                 <h1 className="text-3xl font-black text-[#2CB4AD] mb-1 tracking-tighter">SYNC TETRIS</h1>
                 <div className="text-[10px] text-neutral-600 uppercase tracking-widest">Real-time Synchronized Puzzle</div>
               </div>

               <input type="text" maxLength={5} value={pwdInput} onChange={e => { setPwdInput(e.target.value.toUpperCase()); setForceJoin(false); setMessage(''); }} placeholder="ROOM CODE (5 CHARS)" className="w-full bg-neutral-900 border border-neutral-700 p-3 text-center text-lg sm:text-xl font-mono tracking-[0.2em] focus:outline-none focus:border-[#2CB4AD] rounded placeholder:text-neutral-600" />
               <button onClick={handleConnect} className={`w-full ${forceJoin ? 'bg-red-500 hover:bg-red-400 text-white' : 'bg-[#2CB4AD] hover:bg-cyan-400 text-black'} font-bold py-3 rounded tracking-wide text-sm transition-colors`}>{forceJoin ? 'FORCE OVERWRITE' : 'CONNECT / MATCH'}</button>
               {message && <div className={`${forceJoin ? 'text-yellow-400' : 'text-red-400'} text-xs text-center mt-2`}>{message}</div>}
               
               <div className="mt-2 flex flex-col bg-neutral-900/50 p-3 rounded border border-neutral-800 gap-4">
                 <div className="flex items-center justify-between px-2">
                   <span className="text-[10px] text-neutral-500 font-bold tracking-widest">AUDIO (BGM & SE)</span>
                   <button onClick={() => { const nextState = !soundEnabled; setSoundEnabled(nextState); if (nextState) SoundEngine.init(); }} className={`w-10 h-5 rounded-full relative transition-colors ${soundEnabled ? 'bg-cyan-600' : 'bg-neutral-700'}`}><div className={`w-4 h-4 rounded-full bg-white absolute top-0.5 transition-all ${soundEnabled ? 'left-5' : 'left-0.5'}`} /></button>
                 </div>
                 <div className="flex items-center justify-between px-2 border-t border-neutral-800 pt-3">
                   <span className="text-[10px] text-neutral-500 font-bold tracking-widest">SKILLS ENABLED</span>
                   <button onClick={() => setSkillsEnabled(!skillsEnabled)} className={`w-10 h-5 rounded-full relative transition-colors ${skillsEnabled ? 'bg-cyan-600' : 'bg-neutral-700'}`}><div className={`w-4 h-4 rounded-full bg-white absolute top-0.5 transition-all ${skillsEnabled ? 'left-5' : 'left-0.5'}`} /></button>
                 </div>
                 <div className="flex flex-col items-center border-t border-neutral-800 pt-3">
                   <span className="text-[10px] text-neutral-500 font-bold mb-2 tracking-widest">CPU LEVEL (PRACTICE)</span>
                   <div className="flex gap-2">
                     {[1,2,3,4,5].map(lvl => <button key={lvl} onClick={() => setCpuLevel(lvl)} className={`w-8 h-8 flex items-center justify-center text-xs font-bold rounded border transition-colors ${cpuLevel === lvl ? 'bg-cyan-900 border-cyan-400 text-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.3)]' : 'bg-neutral-800 border-neutral-700 text-neutral-500 hover:border-neutral-500'}`}>{lvl}</button>)}
                   </div>
                 </div>
               </div>
             </div>
           )}

           {gameState === 'waiting' && (
             <div className="text-center w-full flex flex-col items-center pointer-events-auto bg-black/60 md:bg-transparent p-2 rounded mt-8 md:mt-0">
               <div className="text-[10px] md:text-sm text-[#2CB4AD] mb-1 animate-pulse tracking-widest font-bold">WAITING FOR PLAYER...</div>
               <div className="text-[10px] md:text-xs text-neutral-500">ROOM: <span className="font-mono text-neutral-300">{roomId}</span></div>
               <button onClick={handleLeaveMatch} className="mt-2 w-full max-w-[120px] md:max-w-xs bg-red-900/60 text-red-200 font-bold py-1 md:py-2 hover:bg-red-800/60 rounded text-[9px] md:text-xs">CANCEL</button>
             </div>
           )}

           {gameState === 'playing' && (
             <div className="text-center w-full flex flex-col items-center mb-0 md:mb-4 pointer-events-auto bg-black/60 md:bg-transparent p-1 rounded mt-8 md:mt-0">
               <div className="text-[10px] md:text-sm text-[#03AF7A] mb-1 tracking-widest font-bold border-b border-[#03AF7A]/30 pb-1 w-full">CONNECTED</div>
               <div className="text-[10px] md:text-xs text-neutral-500">ROOM: <span className="font-mono text-neutral-400">{roomId}</span></div>
             </div>
           )}

           {/* PC UI for Skills */}
           {skillsEnabled && (gameState === 'playing' || gameState === 'waiting') && !gameResult && (
             <div className="hidden md:block w-full max-w-[260px] bg-neutral-900/80 border border-neutral-700 p-3 rounded-lg mb-4 pointer-events-auto">
               <div className="flex justify-between text-[10px] text-neutral-400 mb-1 font-bold">
                 <span>SKILL CHARGE</span>
                 {isCoolingDown ? <span className="text-red-400 animate-pulse">COOLDOWN {Math.ceil(playerCooldownRemaining / 1000)}s</span> : <span>{(engine.totalLines % 30)} / 30 LINES</span>}
               </div>
               <div className="w-full h-1.5 bg-neutral-800 rounded-full mb-3 overflow-hidden relative">
                 <div className={`h-full transition-all duration-300 ${isCoolingDown ? 'bg-neutral-600' : 'bg-cyan-400'}`} style={{ width: isCoolingDown ? '100%' : `${((engine.totalLines % 30) / 30) * 100}%` }} />
                 {isCoolingDown && <div className="absolute top-0 left-0 h-full bg-red-500/80" style={{ width: `${(playerCooldownRemaining / 15000) * 100}%` }} />}
               </div>
               <div className="grid grid-cols-2 gap-2">
                 <button onClick={() => activateSkill('REWIND')} disabled={engine.sp < 1 || isFrozen || isCoolingDown} className="disabled:opacity-30 disabled:cursor-not-allowed bg-blue-900 hover:bg-blue-800 text-[9px] p-2 rounded text-white font-bold tracking-wider shadow-inner transition-colors">⏪ REWIND (1)</button>
                 <button onClick={() => activateSkill('ERASE')} disabled={engine.sp < 1 || isFrozen || isCoolingDown} className="disabled:opacity-30 disabled:cursor-not-allowed bg-purple-900 hover:bg-purple-800 text-[9px] p-2 rounded text-white font-bold tracking-wider shadow-inner transition-colors">⏭️ ERASE (2)</button>
                 <button onClick={() => activateSkill('FREEZE')} disabled={engine.sp < 1 || isFrozen || isCoolingDown} className="disabled:opacity-30 disabled:cursor-not-allowed bg-teal-900 hover:bg-teal-800 text-[9px] p-2 rounded text-white font-bold tracking-wider shadow-inner transition-colors">⏸️ FREEZE (3)</button>
                 <button onClick={() => activateSkill('ACCEL')} disabled={engine.sp < 1 || isFrozen || isCoolingDown} className="disabled:opacity-30 disabled:cursor-not-allowed bg-orange-900 hover:bg-orange-800 text-[9px] p-2 rounded text-white font-bold tracking-wider shadow-inner transition-colors">⏩ ACCEL (4)</button>
               </div>
             </div>
           )}
           
           <div className="hidden md:block text-[9px] text-neutral-600 text-center leading-relaxed pointer-events-auto mt-4">
              CONTROLS: L/R ARROWS to Move, UP to Rotate<br/>DOWN to Soft Drop, SPACE to Hard Drop, SHIFT/C to Hold<br/>{skillsEnabled && "Number Keys 1-4 to Activate Skills"}
           </div>
        </div>

        {/* --- Right Panel (Player) & Controls Container --- */}
        <div className="flex-1 flex flex-col w-full h-full z-0 relative overflow-hidden pointer-events-none">
           <div className="flex-1 flex flex-col justify-center items-center w-full min-h-0 pointer-events-none pt-2 md:pt-0">
               <PlayerPanel 
                  title="PLAYER 1 (YOU)" board={playerDisplayBoard} score={engine.score} holdPiece={engine.holdPiece} 
                  nextPieces={engine.nextPieces} sp={engine.sp} isYou={true} localGameOverVisible={engine.gameOver && !gameResult} 
                  isPanelFrozen={isFrozen} isPanelAccel={isAccel} vEffect={visualEffect} 
                  onHoldClick={() => handleInput('HOLD')} opponentPanel={opponentUI} 
                  mobileSkillButtons={mobileSkillButtonsUI}
               />
           </div>

           {/* --- Mobile Controls (Flex Bottom) --- */}
           {(gameState === 'playing' || gameState === 'waiting') && !gameResult && (
             <div className="md:hidden w-full px-2 pb-2 pt-1 z-30 flex flex-col gap-1 shrink-0 bg-transparent pointer-events-auto">
               <div className="text-[9px] text-center text-neutral-500 mt-1 pointer-events-none font-bold tracking-widest leading-tight">
                  TAP (L/R/C): Move & Rotate<br/>SWIPE UP: Hard Drop | SWIPE DOWN: Soft Drop
               </div>
             </div>
           )}
        </div>

      </div>
    </>
  );
}