-- Main.hs
-- map と fold を一緒に理解するサンプル

module Main where

main :: IO ()
main = do
    putStrLn "=== Haskell map / fold サンプル ==="

    let numbers = [1,2,3,4]

    -- ----------------------------------------
    -- map: 各要素を2倍にする
    -- ----------------------------------------
    let doubled = map (*2) numbers
    putStrLn ("map (*2) [1,2,3,4] = " ++ show doubled)

    -- ----------------------------------------
    -- fold: 合計を求める
    -- ----------------------------------------
    let total = foldl (+) 0 numbers
    putStrLn ("foldl (+) 0 [1,2,3,4] = " ++ show total)

    -- ----------------------------------------
    -- 組み合わせ：map → fold
    -- ----------------------------------------
    let result = foldl (+) 0 (map (*2) numbers)
    putStrLn ("sum (map (*2) numbers) = " ++ show result)

    -- ----------------------------------------
    -- 別の例：文字列結合
    -- ----------------------------------------
    let wordsList = ["Hello", " ", "World"]
    let sentence = foldl (++) "" wordsList
    putStrLn ("文字列結合 = " ++ sentence)
