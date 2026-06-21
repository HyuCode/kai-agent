# TASK: <一言でゴール>（例: fix(cli): save_config_value が model=str でクラッシュする）

TEST_SCOPE: tests/hermes_cli/

<!--
  これはタスク雛形。1ファイル=1タスク。コピーして loop/tasks/<your-task>.md を作り、
  `loop/loop.sh loop/tasks/<your-task>.md` で回す。
  TEST_SCOPE: は verify.sh に渡すテストパス（狭いほど速い）。フルなら tests/。
-->

## 背景 / 症状

<バグなら再現条件・期待挙動・実際の挙動。機能追加なら何を・なぜ。>

## 受け入れ条件（このタスク固有の Done）

- [ ] <観測可能な条件1。例: 失敗する再現テストを追加し、修正後にパスする>
- [ ] <観測可能な条件2>
- [ ] `loop/verify.sh` が ✅ ALL GREEN
- [ ] スコープ外の変更が無い

## ヒント / 関連ファイル（任意）

- <関係しそうなファイルパスや関数名。Maker の探索を短縮する>

## スコープ外（やらないこと）

- <混ぜてはいけない変更>
