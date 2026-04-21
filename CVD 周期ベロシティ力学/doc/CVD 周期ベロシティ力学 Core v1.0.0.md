# 周期ベロシティ力学フレームワーク（CVD Framework）設計書 v1.0.0

---

## 1. 概要

本設計書は、「周期ベロシティ力学（CVD）」をプロダクトへ組み込むための汎用フレームワーク仕様である。
本フレームワークは、以下の3要素を統合し、リアルタイム制御を可能にする：

* **状態** (Drive / Rest)
* **ベロシティ** (段階的量子化および変化率)
* **周期** (時間構造)

本仕様では、決定論的な状態管理（Zero-Lock）、位相分離モデル、パラメータの動的遷移（モーフィング）、および長期稼働における精度保証を規定し、高度なリズム制御を実現する。

---

## 2. システム構成

```
[CVD Core Engine]
    ├── Time Manager（位相積分型時間管理・dt制限・精度保護・ゼロ除算ガード）
    ├── Parameter Morpher（時間独立型補間・指数減衰・位相最短経路補間）
    ├── Wave Generator（波形生成：sin/saw/tri・出力値のウェーブモーフィング）
    ├── Phase Resolver（位相積算・周波数変更時の連続性保持・累積誤差リセット）
    ├── Delta Calculator（rawベロシティに基づく変化率算出・スパイク除去フィルタ）
    ├── Velocity Quantizer（可変ステップ量子化・Easing）
    ├── State Resolver（D/R境界判定・ヒステリシス制御・エッジ検出）
    ├── Disturbance Handler（外乱エンベロープ・最短位相復帰・フレームレート独立型）
    ├── Action & Edge Dispatcher（コマンド出力・チャタリング防止・遷移トリガー）
    └── State Serializer（内部状態の保存・復元・永続化支援）
```


---

## 3. データモデル

### 3.1 状態構造

```json
{
  "normalized_time": 0.0,    // 0.0–1.0で循環
  "actual_phase": 0.0,       // 回復処理を反映した実効位相
  "absolute_cycle_count": 0, // 累積周期数（精度管理用）
  "state": "D",              // "D" (Drive) または "R" (Rest)
  "velocity_level": 0,       // 量子化されたレベル
  "normalized_velocity": 0.0,// 量子化前の正規化ベロシティ
  "velocity_delta": 0.0,     // 平滑化された変化率
  "morphing_active": false,
  "is_disturbed": false
}
```


---

### 3.2 コンフィグ

```json
{
  "cycle": 1.2,
  "min_cycle": 0.01,         // 計算破綻防止用の最小周期制限
  "amplitude": 1.0,
  "waveform": "sine",
  "waveform_transition_k": 5.0, // 波形クロスフェード速度係数
  "easing": "ease-in-out",
  "morph_k": 5.0,            // パラメータモーフィング収束速度係数
  "rest_ratio": 0.4,         // 1周期におけるRestの割合
  "velocity_steps": 10,      // 量子化レベル数
  "hysteresis_width": 0.02,  // 境界判定の不感帯幅
  "damping_k": 0.1,          // 外乱からの復帰強度係数
  "sync_factor": 0.05,
  "dt_limit": 0.1,           // Δtの許容上限
  "dt_min": 0.001,           // デルタ計算用の最小Δt
  "low_power_mode": true
}
```


---

## 4. API仕様

### 4.1 初期化・基本制御

* `init(config) -> CVDInstance`
* `update(Δt) -> { state, velocity_level, velocity_delta, edge_events }`
    * 入力 $\Delta t$ は `dt_limit` でクランプされ、内部計算に利用される。
* `getState() -> FullState`

### 4.2 動的パラメータ変更

* `requestParam(new_config)`
    * 目標値をセットし、時間独立な補間式に基づき `cycle`, `amplitude`, `rest_ratio` 等を遷移させる。
    * `waveform` の変更時は、旧波形と新波形の出力を `waveform_transition_k` でウェーブモーフィングする。

### 4.3 同期・シーク

* `seekPhase(target_normalized_time)`
    * 現状の位相から目標位相まで、最短経路（時計回り/反時計回り）を選択してモーフィングを行う。

### 4.4 外乱入力

* `applyImpulse(force, decay_rate)`
    * 瞬発的な外乱を与え、指数減衰モデルに基づき `actual_phase` を理想状態へ復帰させる。

### 4.5 シリアライズ

* `serialize() -> string`
    * 現在の位相、累積周期、モーフィング途中の目標値を含む全状態を書き出す。
* `deserialize(data)`
    * 書き出されたデータから状態を復元し、不連続なジャンプを最小限に抑えて再開する。

---

## 5. ステートマシンと判定境界

### 5.1 状態判定（Hysteresis適用）

`normalized_time` ($t$) と `rest_ratio` ($R_r$)、`hysteresis_width` ($W_h$) に基づき、チャタリングを防止して判定する。

* **Drive (D) への遷移**: $t < (1.0 - R_r) - \frac{W_h}{2}$
* **Rest (R) への遷移**: $t \ge (1.0 - R_r) + \frac{W_h}{2}$

### 5.2 イベント発火条件

| イベント名 | 発火条件 | 用途 |
| :--- | :--- | :--- |
| `onStateChange` | Drive $\leftrightarrow$ Rest の境界通過 | UIの大枠切り替え |
| `onEnterDrive` | $R \to D$ への遷移瞬間 | 踏み込み演出・加速SE |
| `onEnterRest` | $D \to R$ への遷移瞬間 | 摩擦感演出・減速SE |
| `onVelocityCross` | レベル（整数値）の境界通過 | 段階演出の更新 |
| `onDirectionChange` | `velocity_delta` の符号反転 | 動きの切り返し検知 |

---

## 6. 数理モデル

### 6.1 位相積算（Phase Accumulation）

周波数変更時の連続性を維持するため、毎フレームの変位を積算する。
$$\Delta \theta = \frac{\Delta t}{\max(Cycle_{current}, min\_cycle)}$$
$$\theta_{next} = (\theta_{current} + \Delta \theta) \pmod 1$$


長期的な浮動小数点誤差を排除するため、$\theta_{next} < \theta_{current}$ となるラップアラウンド発生時に `absolute_cycle_count` をインクリメントし、必要に応じて位相を厳密な $0.0$ へ補正する。

### 6.2 最短経路モーフィング（Modular Morphing）

位相のモーフィングや外乱復帰において、円環上の最短距離を計算する。
$$Diff_{mod} = ((Phase_{target} - Phase_{current} + 0.5) \pmod 1) - 0.5$$
$$Phase_{next} = Phase_{current} + Diff_{mod} \times (1.0 - \exp(-morph\_k \times \Delta t))$$


### 6.3 ベロシティ・デルタの算出と平滑化

量子化前の `normalized_velocity` ($V_n$) を用い、$\Delta t$ の極小化によるスパイクを防ぐ。
$$V_{\Delta, raw} = \frac{V_n(t) - V_n(t-\Delta t)}{\max(\Delta t, dt\_min)}$$
$$V_{\Delta, smooth} = V_{\Delta, prev} + (V_{\Delta, raw} - V_{\Delta, prev}) \times filter\_alpha$$


---

## 7. アクションマッピング

| 状態 | レベル | デルタ（方向） | アクション例 |
| :--- | :--- | :--- | :--- |
| D | 高 | 正（加速） | **DRIVE_ASCEND**（急上昇） |
| D | 高 | 負（減速） | **DRIVE_DESCEND**（収束） |
| R | 低 | 負（減速） | **REST_SETTLE**（着地） |
| EDGE | - | - | **TRANSITION_IMPACT**（状態境界の衝撃） |
| ANY | 0 | 0 | **IDLE_STABLE**（静止） |

---

## 8. 外乱応答と平滑復帰プロセス

フレームレートに依存しない復帰を実現するため、位相最短経路に対する指数減衰モデルを適用する。
$$Phase_{error} = ((Phase_{ideal} - Phase_{actual} + 0.5) \pmod 1) - 0.5$$
$$Phase_{recovery} = Phase_{error} \times (1.0 - \exp(-damping\_k \times \Delta t))$$
回復プロセス中も `velocity_delta` を継続計算し、復帰時の「勢い」を演出に反映する。

---

## 9. 時間処理と精度管理

1.  **Zero-Lock管理**: `normalized_time` を 1.0 でラップし、周期カウンタと併用して累積誤差を排除する。
2.  **ゼロ除算ガード**: $Cycle$ の入力値が $min\_cycle$ 未満にならないようクランプする。
3.  **dt制限**: $\Delta t > dt\_limit$ の場合、入力を上限値でクランプし、極小時は `dt_min` で計算の安定性を確保する。
4.  **動的スロットリング**: `low_power_mode` 有効時、Rest状態では描画・イベント出力頻度を下げるが、内部位相計算は継続して連続性を維持する。

---

## 10. ログ・KPI設計

* **Morphing Latency**: パラメータ変更リクエストから目標値到達（閾値内）までの実時間。
* **Jitter Rate**: `normalized_time` のリセット時や波形遷移時における出力値の不連続発生率。
* **Sync Drift**: `absolute_cycle_count` に基づく論理時間と実時間の乖離率。

---

## 11. 設計原理

1.  **決定論的状態（Zero-Lock）**: 常に循環を維持し、膠着状態を排除する。
2.  **連続性の保持（Phase Continuity）**: パラメータ変更時も出力の跳躍を許さず、滑らかな遷移を保証する。
3.  **動的質感（Delta）**: 変化の方向性を制御に組み込み、生命感のあるリズムを生成する。
4.  **環境適応（Stability-Aware）**: フレームレート変動や急激な時間変化に対して、物理的な整合性を維持した挙動を提供する。