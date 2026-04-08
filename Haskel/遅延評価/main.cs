// Program.cs
// 遅延評価がわかるサンプル
//
// 実行:
//   dotnet run
//
// 見どころ:
// 1. IEnumerable は必要になるまで処理されない
// 2. yield return で遅延実行できる
// 3. Take で必要な分だけ取り出せる
// 4. Haskellほど「言語全体が遅延」ではないが、かなり近い感覚を作れる

using System;
using System.Collections.Generic;
using System.Linq;

class Program
{
    static void Main()
    {
        Console.WriteLine("=== C# 遅延評価サンプル ===");

        Console.WriteLine("\n1. IEnumerable を定義しただけではまだ実行されない");
        var sequence = GetNumbersWithLog().Select(x =>
        {
            Console.WriteLine($"計算しています: {x}");
            return x * 2;
        });

        Console.WriteLine("sequence を作った");
        Console.WriteLine("まだ foreach や ToList をしていないので、ここでは実行されない");

        Console.WriteLine("\n2. Take(3) して初めて必要な分だけ実行される");
        foreach (var x in sequence.Take(3))
        {
            Console.WriteLine($"結果: {x}");
        }

        Console.WriteLine("\n3. もう一度列挙すると、もう一度最初から実行される");
        foreach (var x in sequence.Take(2))
        {
            Console.WriteLine($"結果: {x}");
        }

        Console.WriteLine("\n4. 無限列っぽいものも、Take すれば扱える");
        foreach (var x in InfiniteNumbers().Select(x => x * 2).Take(10))
        {
            Console.WriteLine(x);
        }
    }

    // --------------------------------------------------
    // 1) yield return で遅延生成
    // --------------------------------------------------
    static IEnumerable<int> GetNumbersWithLog()
    {
        Console.WriteLine("GetNumbersWithLog 開始");

        for (int i = 1; i <= 5; i++)
        {
            Console.WriteLine($"yield: {i}");
            yield return i;
        }

        Console.WriteLine("GetNumbersWithLog 終了");
    }

    // --------------------------------------------------
    // 2) 無限列
    // --------------------------------------------------
    static IEnumerable<int> InfiniteNumbers()
    {
        int i = 1;
        while (true)
        {
            yield return i;
            i++;
        }
    }
}