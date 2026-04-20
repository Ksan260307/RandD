# Triadic Velocity Dynamics（TVD）

## コアロジック設計書 v1.0.0（運用・スケーラブル完全版 / DRFモデル）

---

## 1. 概要

本設計は、三要素 **Drive / Regulation / Field（DRF）** による相関ダイナミクスを、プロダクトの中核ロジックとして長期運用・スケーリング・学習に耐える形で実装するための数理モデルである。

v2.7では以下を実現する：

* 内部状態と外部環境の厳密分離
* 入力の安全な非線形処理
* 可観測性と制御指標の分離
* パラメータ管理の階層化
* 数値計算手法の明示
* ログおよびスケーリング前提の設計

---

## 2. 構造定義（DRF）

* **Drive（D）**：外向きの推進力
* **Regulation（R）**：内向きの制御
* **Field（F_internal）**：内部文脈状態
* **Field_external**：外部環境入力

---

## 3. 状態空間

D, R, F_internal ∈ [0,1]

---

## 4. Field統合

相互作用に使用するFieldは以下で定義：

[
F_{total} = clamp(F_{internal} + F_{external}, 0, 1)
]

---

## 5. 時間スケール

* Δt：固定（推奨 0.1）
* λ_eff：構造的安定性
* ε：動的減衰（ε ≪ λ_eff）

---

## 6. 状態更新モデル

### 6.1 基本式

Dₜ₊₁ = Dₜ + Δt · [ G(vD)(F_total − R) − λ_eff D(1 − D) ] − εD² + α·tanh(Input)
Rₜ₊₁ = Rₜ + Δt · [ G(vR)(D − F_total) − λ_eff R(1 − R) ] − εR²
F_internalₜ₊₁ = F_internalₜ + Δt · [ G(vF)(D − R) − λ_eff F_internal(1 − F_internal) ] − εF_internal²

---

### 6.2 境界制約

```id="d3m8qv"
D = min(1, max(0, D))
R = min(1, max(0, R))
F_internal = min(1, max(0, F_internal))
```

---

## 7. ベロシティ設計

### 7.1 行列形式

X = [D, R, F_internal]

v = v₀ + W_state · X + W_input · Input

---

### 7.2 正規化

v_norm = 1 + 9 · σ(v)

---

### 7.3 制約

* 対角優先
* スパース
* 正則化前提

---

## 8. ゲイン関数

[
G(v) = exp(k · (ṽ − 0.5))
]

ṽ = v_norm / 10

---

## 9. 入力設計

### 9.1 入力範囲

Input ∈ [-1,1]

---

### 9.2 非線形処理

状態直接作用：

[
ΔD = α · tanh(Input)
]

---

### 9.3 入力経路

* ベロシティ経路（構造変化）
* 状態経路（即時反応）

---

## 10. 観測レイヤー

### 10.1 状態観測

```id="7m2f8p"
def observe_state(D, R, F):
    return {
        "D": D,
        "R": R,
        "F": F
    }
```

---

### 10.2 制御観測

```id="a9w1kc"
def observe_control(D, R, F, dD, dR, dF):
    return {
        "drive": D - R,
        "pressure": F,
        "activity": D + R + F,
        "output": tanh((D - R)*(1 + F)),
        "dD": dD,
        "dR": dR,
        "dF": dF
    }
```

---

## 11. 数値積分

### 11.1 デフォルト

* RK2（推奨）

```id="n5x2tp"
method = "RK2"
```

---

### 11.2 代替

* Euler（軽量用途）

---

## 12. パラメータ構造

```id="z1v9kc"
params = {
  "dynamics": {
    "λ_eff": 0.5,
    "ε": 0.01,
    "k": 1.5
  },
  "velocity": {
    "v0": vector,
    "W_state": matrix,
    "W_input": matrix
  },
  "input": {
    "α": 0.1
  }
}
```

---

## 13. ログ設計

```id="x6r2jf"
log = {
  "state": (D, R, F_internal),
  "delta": (dD, dR, dF),
  "input": Input,
  "params": params
}
```

---

## 14. 異常状態

* 発散：状態が上限に張り付き
* 停滞：変化量がほぼゼロ
* 偏り：D ≫ R または R ≫ D

---

## 15. スケーリング

* 各インスタンスは独立
* バッチ処理可能
* 並列更新前提

---

## 16. ドリフト対策

```id="f8y3ps"
if drift_detected:
    reproject_state()
```

---

## 17. 初期化

```id="r4k7xq"
D = 0.5 + noise
R = 0.5 + noise
F_internal = 0.5 + noise
```

---

## 18. 設計原則

1. 内部状態と外部環境を分離する
2. 入力は必ず非線形変換を通す
3. 減衰パラメータの役割を分離する
4. 観測と制御指標を分離する
5. 数値計算手法を明示する
6. ログとデバッグ性を確保する
7. スケーラブル設計を前提とする

---

## まとめ

TVD v2.7（DRFモデル）は、三要素相関ダイナミクスを、理論・実装・運用の全レイヤーで統合した完成系モデルである。

主な特徴：

* Drive / Regulation / Field の意味構造
* 外部環境との安全な統合
* 非対称ゲインによる制御性
* 入力の即時性と構造変化の両立
* 高い可観測性とデバッグ性
* スケーラブルな実装前提

本モデルは、抽象ダイナミクスを実用的なプロダクトエンジンとして運用するための基盤として機能する。
