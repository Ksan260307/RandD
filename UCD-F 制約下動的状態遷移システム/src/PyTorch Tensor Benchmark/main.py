import torch
import time

def run_benchmark(N=2048, iterations=5):
    print("--- Starting PyTorch Tensor Benchmark ---")
    print(f"Target Size: {N} x {N} (FP32)")

    # 1回のN x N行列積における浮動小数点演算の総数: 2 * N^3
    operations_per_run = 2 * (N ** 3)
    print(f"Operations per run: {operations_per_run / 1e9:.2f} Giga-FLOPs\n")

    # 1. デバイスの初期化
    if torch.cuda.is_available():
        device = torch.device("cuda")
        device_name = torch.cuda.get_device_name(device)
    elif torch.backends.mps.is_available():
        device = torch.device("mps") # Apple Silicon用
        device_name = "Apple Silicon MPS"
    else:
        device = torch.device("cpu")
        device_name = "CPU"

    print(f"PyTorch Device acquired: {device_name}")

    # 2. データ生成 (Zero-Allocation哲学: デバイス上に直接確保)
    vram_mb = N * N * 4 * 3 / 1024 / 1024
    print(f"Allocating Tensors ({vram_mb:.1f} MB)...")
    
    # WebGPU版に合わせて [-1.0, 1.0] の乱数で初期化
    A = (torch.rand(N, N, dtype=torch.float32, device=device) * 2) - 1.0
    B = (torch.rand(N, N, dtype=torch.float32, device=device) * 2) - 1.0

    # 3. ウォームアップ (GPUコンテキストの初期化オーバーヘッドを排除)
    print("Executing GPU Warm-up...")
    _ = torch.matmul(A, B)
    
    # GPUの非同期実行を完了させるための同期処理
    if device.type == 'cuda':
        torch.cuda.synchronize()
    elif device.type == 'mps':
        torch.mps.synchronize()
    print("Warm-up complete.\n")

    # 4. ベンチマーク・ループ
    print(f"Starting Benchmark ({iterations} iterations)...")
    total_time_ms = 0.0

    for i in range(iterations):
        if device.type == 'cuda':
            # CUDA環境では非同期実行のため、Eventを使った正確なGPU計測が必要
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)
            
            start_event.record()
            _ = torch.matmul(A, B)
            end_event.record()
            
            torch.cuda.synchronize()
            duration_ms = start_event.elapsed_time(end_event)
        else:
            # CPU または MPS
            t0 = time.perf_counter()
            _ = torch.matmul(A, B)
            if device.type == 'mps':
                torch.mps.synchronize()
            t1 = time.perf_counter()
            duration_ms = (t1 - t0) * 1000.0

        total_time_ms += duration_ms
        gflops = (operations_per_run / (duration_ms / 1000.0)) / 1e9

        print(f"  Iter {i + 1}/{iterations} : {duration_ms:.2f} ms | {gflops:.2f} GFLOPS")

    # 5. 結果計算
    avg_time_ms = total_time_ms / iterations
    avg_gflops = (operations_per_run / (avg_time_ms / 1000.0)) / 1e9

    print(f"\n--- Results ---")
    print(f"Average Time : {avg_time_ms:.2f} ms")
    print(f"Average Power: {avg_gflops:.2f} GFLOPS")

if __name__ == "__main__":
    # WebGPU側で実行したサイズに合わせて引数を変更してください
    # (デフォルトは N=2048, iterations=5)
    run_benchmark(N=2048, iterations=5)