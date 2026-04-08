-- Main.hs
-- 遅延評価がわかるサンプル
--
-- 実行:
--   runhaskell Main.hs
--
-- 見どころ:
-- 1. 必要になるまで計算されない
-- 2. 無限リストが使える
-- 3. take で必要な分だけ取り出せる

module Main where

-- トレース表示のために使う
import Debug.Trace (trace)

-- --------------------------------------------------
-- 1) 計算される瞬間を見せる関数
-- --------------------------------------------------
-- evaluateWithLog 10
-- の値を本当に使うまで、この trace は出ない
evaluateWithLog :: Int -> Int
evaluateWithLog x =
    trace ("計算しています: " ++ show x) (x * 2)

-- --------------------------------------------------
-- 2) 無限リスト
-- --------------------------------------------------
-- [1..] は 1,2,3,4,... と無限に続くリスト
infiniteNumbers :: [Int]
infiniteNumbers = [1..]

-- --------------------------------------------------
-- 3) main
-- --------------------------------------------------
main :: IO ()
main = do
    putStrLn "=== Haskell 遅延評価サンプル ==="

    putStrLn "\n1. 値を定義しただけではまだ計算されない"
    let a = evaluateWithLog 10
    putStrLn "a を定義した"
    putStrLn "まだ a を使っていないので、ここでは計算が走らない"

    putStrLn "\n2. a を使った瞬間に初めて計算される"
    putStrLn ("a = " ++ show a)

    putStrLn "\n3. map しただけでも、必要になるまで全部は計算されない"
    let doubled = map evaluateWithLog [1,2,3,4,5]
    putStrLn "doubled を作った"
    putStrLn "まだ全部は計算されていない"

    putStrLn "\n4. take 3 すると、先頭3つだけ計算される"
    print (take 3 doubled)

    putStrLn "\n5. 無限リストでも、必要な分だけなら扱える"
    print (take 10 infiniteNumbers)

    putStrLn "\n6. 無限リストを map しても、必要な分だけ計算される"
    let doubledInfinite = map (*2) infiniteNumbers
    print (take 10 doubledInfinite)
