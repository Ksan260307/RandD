// MonadTutorial.cs
// ------------------------------------------------------------
// C#でモナドっぽさを理解するための超やさしいサンプル
//
// ねらい:
// 1. Haskell の Maybe に近い箱を C# で作る
// 2. Select / SelectMany で「箱の中身をつなぐ」感覚を見る
// 3. LINQ の query syntax が Haskell の do 記法に近いと感じる
//
// 実行例:
//   dotnet new console -n MonadDemo
//   このファイルで Program.cs を置き換える
//   dotnet run
// ------------------------------------------------------------

using System;

namespace MonadDemo
{
    // --------------------------------------------------------
    // 0) Maybe<T>
    //
    // HasValue == true なら値あり
    // HasValue == false なら値なし
    //
    // Haskell の
    //   Just x
    //   Nothing
    // に対応するイメージ
    // --------------------------------------------------------
    public readonly struct Maybe<T>
    {
        private readonly T _value;

        public bool HasValue { get; }

        public T Value =>
            HasValue ? _value : throw new InvalidOperationException("値がありません");

        private Maybe(T value)
        {
            _value = value;
            HasValue = true;
        }

        public static Maybe<T> Some(T value) => new Maybe<T>(value);

        public static Maybe<T> None() => default;

        // Select:
        // 箱の中に値があれば変換して、新しい箱に入れる
        public Maybe<TResult> Select<TResult>(Func<T, TResult> mapper)
        {
            if (!HasValue)
                return Maybe<TResult>.None();

            return Maybe<TResult>.Some(mapper(_value));
        }

        // SelectMany:
        // 箱の中に値があれば、「次も Maybe を返す処理」へ渡す
        // これが bind (>>=) にかなり近い
        public Maybe<TResult> SelectMany<TResult>(Func<T, Maybe<TResult>> binder)
        {
            if (!HasValue)
                return Maybe<TResult>.None();

            return binder(_value);
        }

        // LINQ query syntax 用の 3 引数版 SelectMany
        public Maybe<TResult> SelectMany<TIntermediate, TResult>(
            Func<T, Maybe<TIntermediate>> binder,
            Func<T, TIntermediate, TResult> projector)
        {
            if (!HasValue)
                return Maybe<TResult>.None();

            var first = _value;
            var intermediate = binder(first);

            if (!intermediate.HasValue)
                return Maybe<TResult>.None();

            return Maybe<TResult>.Some(projector(first, intermediate.Value));
        }

        public override string ToString()
        {
            return HasValue ? $"Some({_value})" : "None";
        }
    }

    public static class Program
    {
        // --------------------------------------------------------
        // 1) まずは immutable な感覚
        // --------------------------------------------------------
        static void PlainExample()
        {
            const int x = 5;
            int y = x + 3;

            Console.WriteLine("=== 0) まずは普通の immutable っぽい感覚 ===");
            Console.WriteLine($"x = {x}");
            Console.WriteLine($"y = x + 3 = {y}");
            Console.WriteLine("x 自体は変えず、新しい値 y を作っている");
            Console.WriteLine();
        }

        // --------------------------------------------------------
        // 2) Haskell の Maybe に近い処理
        // --------------------------------------------------------
        static Maybe<double> SafeReciprocal(double x)
        {
            if (x == 0)
                return Maybe<double>.None();

            return Maybe<double>.Some(1 / x);
        }

        static Maybe<double> SafeSqrt(double x)
        {
            if (x < 0)
                return Maybe<double>.None();

            return Maybe<double>.Some(Math.Sqrt(x));
        }

        static void Main()
        {
            Console.WriteLine("🐵 C# でモナドっぽさを理解するサンプル");
            Console.WriteLine();

            PlainExample();

            Console.WriteLine("=== 1) Maybe は『失敗するかも』を表す箱 ===");
            Console.WriteLine($"SafeReciprocal(2)  = {SafeReciprocal(2)}");
            Console.WriteLine($"SafeReciprocal(0)  = {SafeReciprocal(0)}");
            Console.WriteLine($"SafeSqrt(9)        = {SafeSqrt(9)}");
            Console.WriteLine($"SafeSqrt(-1)       = {SafeSqrt(-1)}");
            Console.WriteLine();

            Console.WriteLine("=== 2) Select = 箱の中身だけ変換 ===");
            var someFive = Maybe<int>.Some(5);
            var noneInt = Maybe<int>.None();

            Console.WriteLine($"Some(5).Select(x => x + 3) = {someFive.Select(x => x + 3)}");
            Console.WriteLine($"None().Select(x => x + 3)  = {noneInt.Select(x => x + 3)}");
            Console.WriteLine();

            Console.WriteLine("=== 3) SelectMany = 次も Maybe を返す処理につなぐ ===");
            var pipeline1 =
                Maybe<double>.Some(4)
                    .SelectMany(SafeReciprocal)
                    .SelectMany(SafeSqrt);

            var pipeline2 =
                Maybe<double>.Some(0)
                    .SelectMany(SafeReciprocal)
                    .SelectMany(SafeSqrt);

            Console.WriteLine($"Some(4) -> reciprocal -> sqrt = {pipeline1}");
            Console.WriteLine($"Some(0) -> reciprocal -> sqrt = {pipeline2}");
            Console.WriteLine();

            Console.WriteLine("=== 4) LINQ の query syntax は Haskell の do 記法に近い ===");
            var querySyntaxSuccess =
                from reciprocal in SafeReciprocal(4)
                from result in SafeSqrt(reciprocal)
                select result;

            var querySyntaxFail =
                from reciprocal in SafeReciprocal(0)
                from result in SafeSqrt(reciprocal)
                select result;

            Console.WriteLine($"query syntax success = {querySyntaxSuccess}");
            Console.WriteLine($"query syntax fail    = {querySyntaxFail}");
            Console.WriteLine();

            Console.WriteLine("=== 5) 覚え方 ===");
            Console.WriteLine("モナドの大事な点は『値を書き換えること』ではなく、");
            Console.WriteLine("『箱に入った値を、箱のルールに従って次の処理へ渡すこと』");
        }
    }
}
