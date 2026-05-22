# 1-5: 基本的な全件・条件絞り込み
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM products"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM orders"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT id, name FROM users WHERE age >= 30"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT name, price FROM products WHERE stock > 10"}'

# 6-10: LIMIT / OFFSET 制御
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users LIMIT 3"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users LIMIT 2 OFFSET 2"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT name FROM products LIMIT 1"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM orders LIMIT 5 OFFSET 0"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users WHERE status = ''Active'' LIMIT 2"}'

# 11-15: ORDER BY (並び替え)
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users ORDER BY age ASC"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users ORDER BY age DESC"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM products ORDER BY price DESC"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM products ORDER BY stock ASC"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users WHERE status = ''Active'' ORDER BY id DESC LIMIT 3"}'

# 16-20: BETWEEN / LIKE / IN 構文
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users WHERE age BETWEEN 25 AND 35"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM products WHERE price BETWEEN 100 AND 500"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users WHERE name LIKE ''%a%''"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users WHERE name LIKE ''J%''"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users WHERE status IN (''Active'') "}'

# 21-25: GROUP BY / HAVING / CASE 文
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT status, COUNT(id) AS total FROM users GROUP BY status"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT status, AVG(age) AS avg_age FROM users GROUP BY status"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT status, COUNT(id) AS total FROM users GROUP BY status HAVING COUNT(id) > 1"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT name, CASE WHEN age >= 30 THEN ''Adult'' ELSE ''Young'' END AS generation FROM users"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT name, CASE WHEN stock = 0 THEN ''Out of Stock'' ELSE ''Available'' END AS item_status FROM products"}'

# 26-35: INSERT句によるデータ追加
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO users (id, name, age, status) VALUES (11, ''Kevin'', 33, ''Active'')"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO users (id, name, age, status) VALUES (12, ''Leo'', 19, ''Active'')"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO users (id, name, age, status) VALUES (13, ''Mona'', 45, ''Inactive'')"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO users (id, name, age, status) VALUES (14, ''Nat'', 26, ''Active'')"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO users (id, name, age, status) VALUES (15, ''Oscar'', 29, ''Active'')"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO products (id, name, price, stock) VALUES (106, ''Quantum Case'', 50, ''200'')"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO products (id, name, price, stock) VALUES (107, ''Laser Mouse'', 150, ''15'')"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO orders (order_id, user_id, product_id, amount) VALUES (1006, 5, 102, 1)"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO orders (order_id, user_id, product_id, amount) VALUES (1007, 11, 106, 2)"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO users (id, name, age, status) VALUES (16, ''Peggy'', 31, ''Active'')"}'

# 36-45: UPDATE句によるデータ更新
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"UPDATE users SET age = 26 WHERE id = 1"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"UPDATE users SET status = ''Inactive'' WHERE id = 2"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"UPDATE users SET age = age + 1 WHERE status = ''Active''"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"UPDATE products SET price = 1600 WHERE id = 101"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"UPDATE products SET stock = stock - 1 WHERE id = 103"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"UPDATE products SET stock = 50 WHERE stock = 0"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"UPDATE orders SET amount = 10 WHERE order_id = 1001"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"UPDATE users SET name = ''Alice M.'' WHERE id = 1"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"UPDATE users SET status = ''Active'' WHERE age < 30"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"UPDATE products SET price = price * 0.9 WHERE price > 500"}'

# 46-50: 複合更新確認用の追加データ投入
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO users (id, name, age, status) VALUES (17, ''Quinn'', 22, ''Active'')"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO users (id, name, age, status) VALUES (18, ''Rose'', 28, ''Active'')"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO products (id, name, price, stock) VALUES (108, ''Holo-Stand'', 80, 50)"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"UPDATE users SET age = 40 WHERE name = ''Rose''"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"UPDATE products SET stock = 100 WHERE id = 108"}'

# 51-55: 通常のDELETEテスト
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"DELETE FROM users WHERE id = 10"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"DELETE FROM products WHERE id = 105"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"DELETE FROM orders WHERE amount = 5"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"DELETE FROM users WHERE status = ''Inactive''"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"DELETE FROM products WHERE price < 150"}'

# 56-62: トランザクション・ロールバックテスト (元に戻るか)
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"BEGIN"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO users (id, name, age, status) VALUES (999, ''Ghost'', 99, ''Active'')"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users WHERE id = 999"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"DELETE FROM users WHERE id = 1"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"ROLLBACK"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users WHERE id = 999"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users WHERE id = 1"}'

# 63-70: トランザクション・コミットテスト (確定されるか)
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"BEGIN"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO users (id, name, age, status) VALUES (20, ''Sam'', 25, ''Active'')"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"UPDATE users SET status = ''Active'' WHERE id = 20"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"DELETE FROM orders WHERE order_id = 1005"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"COMMIT"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users WHERE id = 20"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM orders WHERE order_id = 1005"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"VACUUM"}'

# 71-75: DDL (テーブル作成・削除・初期化)
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"CREATE TABLE analytics (log_id, user_id, action)"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"INSERT INTO analytics (log_id, user_id, action) VALUES (1, 1, ''login'')"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"TRUNCATE TABLE analytics"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM analytics"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"DROP TABLE analytics"}'

# 76-80: テーブル結合 (JOIN)
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT users.name, orders.amount FROM users JOIN orders ON users.id = orders.user_id"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT u.name, o.amount FROM users u INNER JOIN orders o ON u.id = o.user_id"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT u.name, o.amount FROM users u LEFT JOIN orders o ON u.id = o.user_id"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT p.name, o.amount FROM products p JOIN orders o ON p.id = o.product_id"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT u.name, p.name FROM users u JOIN orders o ON u.id = o.user_id JOIN products p ON o.product_id = p.id"}'

# 81-85: サブクエリ (Subquery)
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM products WHERE id IN (SELECT product_id FROM orders WHERE amount > 1)"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users WHERE age > (SELECT AVG(age) FROM users)"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT name FROM users WHERE id = (SELECT user_id FROM orders LIMIT 1)"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM products WHERE price > (SELECT AVG(price) FROM products)"}'

# 86-90: 複雑な結合と集計の組み合わせ
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT u.status, SUM(o.amount) AS total_goods FROM users u JOIN orders o ON u.id = o.user_id GROUP BY u.status"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT p.name, COUNT(o.order_id) AS order_count FROM products p LEFT JOIN orders o ON p.id = o.product_id GROUP BY p.name"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT u.name, SUM(o.amount) FROM users u JOIN orders o ON u.id = o.user_id GROUP BY u.name HAVING SUM(o.amount) >= 1"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"CREATE TABLE backup_users (b_id, b_name)"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"DROP TABLE backup_users"}'

# 91-93: EXPLAIN コマンドによる実行計画の可視化 (SQL拡張 / 専用エンドポイント)
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"EXPLAIN SELECT * FROM users WHERE age >= 25"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"EXPLAIN SELECT u.name, o.amount FROM users u JOIN orders o ON u.id = o.user_id"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/explain -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM products WHERE price > 500"}'

# 94-96: GENERATE コマンドによる10,000件ダミーデータ高速注入 (SQL拡張 / 専用エンドポイント)
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"GENERATE DUMMY FOR users"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"GENERATE DUMMY FOR products"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/generate -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"table":"orders"}'

# 97-100: 物理シミュレーション・遅延パラメータ変更とクリーンアップ
Invoke-RestMethod -Uri http://localhost:8080/api/v1/physics -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"c":299, "d":80, "s":95}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT COUNT(id) AS huge_users FROM users"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"VACUUM"}'
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"SELECT * FROM users LIMIT 1"}'

# データベースを初期状態にリセットする
Invoke-RestMethod -Uri http://localhost:8080/api/v1/query -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"query":"FACTORY RESET"}'