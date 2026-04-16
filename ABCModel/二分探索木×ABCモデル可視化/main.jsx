<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>BST x ABC Model Visualizer</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;700&display=swap');
        body { font-family: 'Noto Sans JP', sans-serif; background-color: #0f172a; color: #f8fafc; overflow-x: hidden; }
        .node { transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1); }
        .path-line { transition: stroke-dashoffset 0.5s ease-in-out; }
        .slider-thumb::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 20px;
            height: 20px;
            background: #38bdf8;
            border-radius: 50%;
            cursor: pointer;
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.5);
        }
        .abc-card { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(8px); border: 1px solid rgba(255,255,255,0.1); }
        .status-badge { font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }
        .pulse { animation: pulse 2s infinite; }
        @keyframes pulse {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.1); opacity: 0.8; }
        }
    </style>
</head>
<body class="p-4">
    <!-- Header -->
    <header class="mb-6">
        <h1 class="text-xl font-bold text-sky-400">木を探索するココロの動き</h1>
        <p class="text-xs text-slate-400">二分探索木のアルゴリズムをABCモデルで体感する</p>
    </header>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Visualization Area -->
        <div class="lg:col-span-2 relative">
            <div id="canvas-container" class="w-full aspect-square md:aspect-video bg-slate-900 rounded-2xl border border-slate-700 shadow-2xl relative overflow-hidden">
                <svg id="tree-svg" class="w-full h-full">
                    <g id="links-layer"></g>
                    <g id="nodes-layer"></g>
                </svg>
                <!-- Search Highlighter -->
                <div id="pointer" class="absolute w-10 h-10 border-4 border-yellow-400 rounded-full hidden pointer-events-none transition-all duration-500 z-50"></div>
                
                <!-- Status Overlay -->
                <div class="absolute bottom-4 left-4 flex flex-col gap-2">
                    <div id="ruin-label" class="bg-red-500/20 text-red-400 border border-red-500/50 px-3 py-1 rounded-full text-sm font-bold opacity-0 transition-opacity">
                        危険度上昇中！
                    </div>
                </div>
            </div>

            <!-- Controls (Mobile optimized) -->
            <div class="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
                <div class="abc-card p-4 rounded-xl">
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-sm font-bold text-emerald-400">勢い (直感)</span>
                        <span id="vA-val" class="text-xs font-mono">Normal</span>
                    </div>
                    <input type="range" id="slider-A" min="0" max="2" step="0.1" value="1" class="w-full h-2 bg-slate-700 rounded-lg appearance-none slider-thumb">
                    <p class="text-[10px] text-slate-500 mt-2">探索をどんどん進めるエネルギー</p>
                </div>
                <div class="abc-card p-4 rounded-xl">
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-sm font-bold text-rose-400">審判 (比較)</span>
                        <span id="vB-val" class="text-xs font-mono">Normal</span>
                    </div>
                    <input type="range" id="slider-B" min="0" max="2" step="0.1" value="1" class="w-full h-2 bg-slate-700 rounded-lg appearance-none slider-thumb">
                    <p class="text-[10px] text-slate-500 mt-2">左右を厳密に選ぶコスト</p>
                </div>
                <div class="abc-card p-4 rounded-xl">
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-sm font-bold text-sky-400">視点 (俯瞰)</span>
                        <span id="vC-val" class="text-xs font-mono">Normal</span>
                    </div>
                    <input type="range" id="slider-C" min="0" max="2" step="0.1" value="1" class="w-full h-2 bg-slate-700 rounded-lg appearance-none slider-thumb">
                    <p class="text-[10px] text-slate-500 mt-2">全体を見渡して行き過ぎを防ぐ</p>
                </div>
            </div>
        </div>

        <!-- Dashboard / Info -->
        <div class="flex flex-col gap-4">
            <div class="abc-card p-5 rounded-2xl flex-grow">
                <h2 class="text-sm font-bold mb-4 flex items-center gap-2">
                    <span class="w-2 h-2 bg-yellow-400 rounded-full"></span>
                    現在の状態
                </h2>
                
                <div class="space-y-6">
                    <!-- Progress Bar -->
                    <div>
                        <div class="flex justify-between text-[10px] mb-1">
                            <span>探索の負荷 (RuinScore)</span>
                            <span id="ruin-pct">0%</span>
                        </div>
                        <div class="w-full h-3 bg-slate-800 rounded-full overflow-hidden">
                            <div id="ruin-bar" class="h-full bg-gradient-to-r from-emerald-500 to-rose-500 transition-all duration-300" style="width: 0%"></div>
                        </div>
                    </div>

                    <!-- Logs -->
                    <div id="log-container" class="text-xs space-y-2 h-40 overflow-y-auto pr-2 custom-scrollbar text-slate-400">
                        <div>シミュレーター準備完了</div>
                        <div>「探索開始」を押して動きを確認してください。</div>
                    </div>

                    <button id="search-btn" class="w-full py-4 bg-sky-600 hover:bg-sky-500 rounded-xl font-bold transition-all transform active:scale-95 shadow-lg shadow-sky-900/20">
                        ターゲットを探索
                    </button>
                    
                    <button id="reset-btn" class="w-full py-2 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded-xl text-xs transition-all">
                        木を再生成
                    </button>
                </div>
            </div>

            <!-- Theory Tip -->
            <div class="bg-sky-900/20 border border-sky-500/30 p-4 rounded-2xl">
                <h3 class="text-xs font-bold text-sky-300 mb-1 italic">ABCロジックのヒント</h3>
                <p id="hint-text" class="text-[11px] leading-relaxed text-sky-100/70">
                    「俯瞰」が強すぎると、「勢い」が死んで探索が止まります（Zero状態）。逆に「勢い」と「審判」が強すぎると、計算が暴走します（Runaway）。
                </p>
            </div>
        </div>
    </div>

    <script>
        // --- Core Logic (ABC Model v3.2.0 based) ---
        const state = {
            vA: 1.0, vB: 1.0, vC: 1.0,
            dA: 0.1, dB: 0.1, dC: 0.1,
            stateA: 'Normal', stateB: 'Normal', stateC: 'Normal',
            ruinScore: 0,
            isSearching: false
        };

        const treeData = {
            nodes: [],
            links: [],
            root: null
        };

        const config = {
            nodeCount: 15,
            padding: 40,
            nodeRadius: 18
        };

        // --- BST Utils ---
        class Node {
            constructor(val, x, y, depth) {
                this.val = val;
                this.x = x;
                this.y = y;
                this.depth = depth;
                this.left = null;
                this.right = null;
                this.id = Math.random().toString(36).substr(2, 9);
            }
        }

        function generateBST() {
            const values = Array.from({length: config.nodeCount}, () => Math.floor(Math.random() * 100));
            values.sort((a, b) => a - b); // Use sorted for a balanced-ish tree start
            
            treeData.nodes = [];
            treeData.links = [];
            
            function build(arr, x, y, xStep, depth) {
                if (arr.length === 0) return null;
                const mid = Math.floor(arr.length / 2);
                const node = new Node(arr[mid], x, y, depth);
                treeData.nodes.push(node);
                
                const nextY = y + 70;
                const nextXStep = xStep * 0.5;
                
                node.left = build(arr.slice(0, mid), x - xStep, nextY, nextXStep, depth + 1);
                node.right = build(arr.slice(mid + 1), x + xStep, nextY, nextXStep, depth + 1);
                
                if (node.left) treeData.links.push({from: node, to: node.left});
                if (node.right) treeData.links.push({from: node, to: node.right});
                
                return node;
            }

            const container = document.getElementById('canvas-container');
            const w = container.clientWidth;
            treeData.root = build(values, w / 2, 50, w / 4, 0);
            renderTree();
        }

        function renderTree() {
            const nodesLayer = document.getElementById('nodes-layer');
            const linksLayer = document.getElementById('links-layer');
            nodesLayer.innerHTML = '';
            linksLayer.innerHTML = '';

            treeData.links.forEach(link => {
                const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                line.setAttribute("x1", link.from.x);
                line.setAttribute("y1", link.from.y);
                line.setAttribute("x2", link.to.x);
                line.setAttribute("y2", link.to.y);
                line.setAttribute("stroke", "#334155");
                line.setAttribute("stroke-width", "2");
                line.className.baseVal = "path-line";
                linksLayer.appendChild(line);
            });

            treeData.nodes.forEach(node => {
                const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
                g.setAttribute("transform", `translate(${node.x}, ${node.y})`);
                g.className.baseVal = "node";
                g.id = `node-${node.id}`;

                const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
                circle.setAttribute("r", config.nodeRadius);
                circle.setAttribute("fill", "#1e293b");
                circle.setAttribute("stroke", "#64748b");
                circle.setAttribute("stroke-width", "2");

                const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
                text.textContent = node.val;
                text.setAttribute("text-anchor", "middle");
                text.setAttribute("dy", "5");
                text.setAttribute("fill", "#f8fafc");
                text.setAttribute("font-size", "12px");
                text.setAttribute("font-weight", "bold");

                g.appendChild(circle);
                g.appendChild(text);
                nodesLayer.appendChild(g);
            });
        }

        // --- Simulation Logic ---
        function updateABC() {
            // Velocity Mapping
            state.vA = parseFloat(document.getElementById('slider-A').value);
            state.vB = parseFloat(document.getElementById('slider-B').value);
            state.vC = parseFloat(document.getElementById('slider-C').value);

            // Simple State Logic (v3.2.0 inspired)
            // C -> A Suppression (TR-1)
            if (state.vC > 1.6 && state.vA < 0.8) {
                state.stateA = 'Zero';
                document.getElementById('vA-val').innerText = '停止(Zero)';
                document.getElementById('vA-val').className = 'text-xs font-mono text-blue-400';
            } else if (state.vA > 1.6) {
                state.stateA = 'Runaway';
                document.getElementById('vA-val').innerText = '暴走(Runaway)';
                document.getElementById('vA-val').className = 'text-xs font-mono text-orange-400';
            } else {
                state.stateA = 'Normal';
                document.getElementById('vA-val').innerText = '正常(Normal)';
                document.getElementById('vA-val').className = 'text-xs font-mono text-emerald-400';
            }

            // B Status
            if (state.vB > 1.6) {
                state.stateB = 'Runaway';
                document.getElementById('vB-val').innerText = '過負荷(Runaway)';
                document.getElementById('vB-val').className = 'text-xs font-mono text-rose-400';
            } else {
                state.stateB = 'Normal';
                document.getElementById('vB-val').innerText = '正常(Normal)';
                document.getElementById('vB-val').className = 'text-xs font-mono text-emerald-400';
            }

            // RuinScore calculation (Simplified v3.2.0 §5)
            // R = max(A, B, C) where A/B/C has internal penalty
            let rA = (state.stateA === 'Runaway' ? 2 : (state.stateA === 'Zero' ? 3 : 0)) + state.vA;
            let rB = (state.stateB === 'Runaway' ? 2 : 0) + state.vB;
            let rC = state.vC * 1.5;
            
            state.ruinScore = Math.max(rA, rB, rC);
            const ruinPct = Math.min(100, (state.ruinScore / 6) * 100);
            
            document.getElementById('ruin-bar').style.width = `${ruinPct}%`;
            document.getElementById('ruin-pct').innerText = `${Math.round(ruinPct)}%`;
            
            const label = document.getElementById('ruin-label');
            if (ruinPct > 70) {
                label.style.opacity = '1';
                label.classList.add('pulse');
            } else {
                label.style.opacity = '0';
                label.classList.remove('pulse');
            }
        }

        async function startSearch() {
            if (state.isSearching) return;
            state.isSearching = true;
            
            const target = treeData.nodes[Math.floor(Math.random() * treeData.nodes.length)].val;
            addLog(`探索開始: [${target}] を探します...`);
            
            const pointer = document.getElementById('pointer');
            pointer.classList.remove('hidden');
            
            let current = treeData.root;
            
            while (current) {
                // Update pointers
                pointer.style.left = `${current.x - 20}px`;
                pointer.style.top = `${current.y - 20}px`;
                
                // Highlight node
                const nodeEl = document.getElementById(`node-${current.id}`);
                nodeEl.querySelector('circle').setAttribute('stroke', '#fbbf24');
                nodeEl.querySelector('circle').setAttribute('stroke-width', '4');

                // ABC Effect on delay
                // A (High) = Speed up, B (High) = Slow down, C (High) = Stability
                let baseDelay = 800;
                if (state.stateA === 'Zero') {
                    addLog("!! 勢いが消失 (Zero)。探索がストップしました。");
                    break;
                }
                
                let speedFactor = state.vA;
                let costFactor = state.vB;
                let delay = baseDelay / (speedFactor + 0.1) * (costFactor + 0.5);
                
                // RuinScore effect (Jitter/Error)
                if (state.ruinScore > 4.5) {
                    addLog("!! 負荷過多。判断が乱れています。");
                    delay += Math.random() * 500;
                }

                await new Promise(r => setTimeout(r, delay));

                if (current.val === target) {
                    addLog(`見つかりました: [${target}]`);
                    nodeEl.querySelector('circle').setAttribute('fill', '#059669');
                    break;
                } else if (target < current.val) {
                    addLog(`[${target}] < [${current.val}] -> 左へ`);
                    current = current.left;
                } else {
                    addLog(`[${target}] > [${current.val}] -> 右へ`);
                    current = current.right;
                }

                if (!current) {
                    addLog("見つかりませんでした。");
                }
            }
            
            state.isSearching = false;
        }

        function addLog(msg) {
            const container = document.getElementById('log-container');
            const div = document.createElement('div');
            div.className = "border-l-2 border-slate-700 pl-2 animate-in fade-in slide-in-from-left-2 duration-300";
            div.innerText = msg;
            container.prepend(div);
        }

        // --- Event Listeners ---
        document.getElementById('slider-A').addEventListener('input', updateABC);
        document.getElementById('slider-B').addEventListener('input', updateABC);
        document.getElementById('slider-C').addEventListener('input', updateABC);
        
        document.getElementById('search-btn').addEventListener('click', () => {
            if (!state.isSearching) {
                renderTree(); // Clear highlights
                startSearch();
            }
        });

        document.getElementById('reset-btn').addEventListener('click', () => {
            generateBST();
            addLog("木を新しく作り直しました。");
        });

        window.addEventListener('resize', generateBST);

        // Init
        window.onload = () => {
            generateBST();
            updateABC();
        };

    </script>
</body>
</html>