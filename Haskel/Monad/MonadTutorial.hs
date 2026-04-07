-- MonadTutorial.hs
-- ------------------------------------------------------------
-- Haskellでモナドを理解するための超やさしいサンプル
--
-- ねらい:
-- 1. 「値は書き換えない」を確認する
-- 2. Maybe モナドで「失敗するかもしれない計算」をつなぐ
-- 3. do 記法が何をしているかを見る
--
-- 実行例:
--   runhaskell MonadTutorial.hs
-- または
--   ghc MonadTutorial.hs && ./MonadTutorial
-- ------------------------------------------------------------

module Main where

-- ------------------------------------------------------------
-- 0) まずは「値は変えず、新しい値を作る」感覚
-- ------------------------------------------------------------

plainExample :: IO ()
plainExample = do
    let x = 5
    let y = x + 3
    putStrLn "=== 0) まずは普通の immutable な値 ==="
    putStrLn ("x = " ++ show x)
    putStrLn ("y = x + 3 = " ++ show y)
    putStrLn "x 自体は変わらず、そのまま残る"
    putStrLn ""

-- ------------------------------------------------------------
-- 1) Maybe: 「失敗するかもしれない値」の箱
--
-- Just 10   = 成功して値がある
-- Nothing   = 失敗して値がない
-- ------------------------------------------------------------

safeReciprocal :: Double -> Maybe Double
safeReciprocal x =
    if x == 0
        then Nothing
        else Just (1 / x)

safeSqrt :: Double -> Maybe Double
safeSqrt x =
    if x < 0
        then Nothing
        else Just (sqrt x)

-- bind (>>=) を使って、箱の中身を次の処理へ渡す
-- どこかで Nothing になったら、そこで全体も Nothing になる
pipelineWithBind :: Double -> Maybe Double
pipelineWithBind x =
    Just x
        >>= safeReciprocal
        >>= safeSqrt

-- 同じことを do 記法で書く
pipelineWithDo :: Double -> Maybe Double
pipelineWithDo x = do
    reciprocal <- safeReciprocal x
    result <- safeSqrt reciprocal
    return result

-- ------------------------------------------------------------
-- 2) 「箱を開けて、計算して、新しい箱に入れる」例
-- ------------------------------------------------------------

addThreeInsideMaybe :: Maybe Int -> Maybe Int
addThreeInsideMaybe mx =
    mx >>= (\x -> Just (x + 3))

-- do 記法版
addThreeInsideMaybeDo :: Maybe Int -> Maybe Int
addThreeInsideMaybeDo mx = do
    x <- mx
    return (x + 3)

-- ------------------------------------------------------------
-- 3) main: 画面で挙動を確認
-- ------------------------------------------------------------

main :: IO ()
main = do
    putStrLn "🐵 Haskell でモナドを理解するサンプル"
    putStrLn ""

    plainExample

    putStrLn "=== 1) Maybe は『失敗するかも』を表す箱 ==="
    putStrLn ("safeReciprocal 2   = " ++ show (safeReciprocal 2))
    putStrLn ("safeReciprocal 0   = " ++ show (safeReciprocal 0))
    putStrLn ("safeSqrt 9         = " ++ show (safeSqrt 9))
    putStrLn ("safeSqrt (-1)      = " ++ show (safeSqrt (-1)))
    putStrLn ""

    putStrLn "=== 2) bind (>>=) で処理をつなぐ ==="
    putStrLn "Just x -> safeReciprocal -> safeSqrt"
    putStrLn ("pipelineWithBind 4 = " ++ show (pipelineWithBind 4))
    putStrLn ("pipelineWithBind 0 = " ++ show (pipelineWithBind 0))
    putStrLn ""

    putStrLn "=== 3) do 記法は bind を読みやすくしたもの ==="
    putStrLn ("pipelineWithDo 4   = " ++ show (pipelineWithDo 4))
    putStrLn ("pipelineWithDo 0   = " ++ show (pipelineWithDo 0))
    putStrLn ""

    putStrLn "=== 4) 『値を変える』ではなく『新しい箱を作る』 ==="
    putStrLn ("addThreeInsideMaybe (Just 5) = " ++ show (addThreeInsideMaybe (Just 5)))
    putStrLn ("addThreeInsideMaybe Nothing  = " ++ show (addThreeInsideMaybe Nothing))
    putStrLn ("addThreeInsideMaybeDo (Just 5) = " ++ show (addThreeInsideMaybeDo (Just 5)))
    putStrLn ""

    putStrLn "=== 5) 覚え方 ==="
    putStrLn "モナド = 箱そのもの、というより"
    putStrLn "        『箱に入った値を安全に次の処理へ渡すためのルール』"
