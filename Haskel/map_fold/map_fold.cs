// Program.cs
// Select / Aggregate を使って map / fold を再現

using System;
using System.Linq;

class Program
{
    static void Main()
    {
        Console.WriteLine("=== C# map / fold (LINQ) サンプル ===");

        var numbers = new[] {1, 2, 3, 4};

        // ----------------------------------------
        // map: 各要素を2倍にする
        // ----------------------------------------
        var doubled = numbers
            .Select(x => x * 2);

        Console.WriteLine("Select(x => x * 2) = [" + string.Join(", ", doubled) + "]");

        // ----------------------------------------
        // fold: 合計を求める
        // ----------------------------------------
        var total = numbers
            .Aggregate(0, (acc, x) => acc + x);

        Console.WriteLine("Aggregate sum = " + total);

        // ----------------------------------------
        // 組み合わせ：map → fold
        // ----------------------------------------
        var result = numbers
            .Select(x => x * 2)
            .Aggregate(0, (acc, x) => acc + x);

        Console.WriteLine("sum of doubled = " + result);

        // ----------------------------------------
        // 別の例：文字列結合
        // ----------------------------------------
        var words = new[] {"Hello", " ", "World"};

        var sentence = words
            .Aggregate("", (acc, x) => acc + x);

        Console.WriteLine("文字列結合 = " + sentence);
    }
}
