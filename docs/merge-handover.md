# Vendor/SHI 統合作業 引継ぎ

最終更新: 2026-09-04

この文書は、別PCまたは別のCopilotチャットで統合作業を再開するための入口である。
作業を始める前に本書を読み、判断・実装・検証が進んだら同じ作業内で更新すること。

関連文書:

- [error_list.txt](error_list.txt): NSW/vendor と SHI のエラー実装分担
- [error-handling-review-ledger.md](error-handling-review-ledger.md): 過去のエラー処理レビュー記録
- [動作確認・性能測定手順.md](動作確認・性能測定手順.md): 実機確認と性能測定

## 1. 統合の前提

### 1.1 ソースの位置

現在確認した配置は次のとおり。

- 統合先/vendor最新版: このリポジトリ (`local_pipe2`)
- SHI最新版: `${HOME}/argus_pipe_filter`

別PCではSHI側の配置が異なる可能性がある。比較コマンドでは固定絶対パスを埋め込まず、例えば次を設定する。

```bash
export SHI_REPO="$HOME/argus_pipe_filter"
```

### 1.2 基準コミット

2026-09-03時点で確認した基準:

- vendor: `62dfe7d289c6c607ff0330ba9ae2146cdf982344`
  - `Initial import from NSWargus_synchro_2026_0825`
- SHI: `2283a0a68f512d7595fb81032925630f07f1b522`
  - `負荷低減モード実装.点群上限の変更.`

作業再開時は両方のHEADを確認し、変わっていれば本節を更新する。

```bash
git log -1 --format='%H %ad %s' --date=iso
git -C "$SHI_REPO" log -1 --format='%H %ad %s' --date=iso
```

### 1.3 履歴と差分の性質

両リポジトリはGit上の共通履歴を持っていない。2026-09-03時点の概算では、生成物等を除外しても変更191ファイル、片側だけに存在するファイル45件、合計236件の差分がある。

エラー処理の分担開始時点では、ユーザー側とvendor側で基本的な枠組みを共有していた。双方の `shared_errors.py` にエラー番号と名称を定義し、`action_errors.py`、`state_errors.py` などにも担当実装を追加する前の基本メソッドや空実装を置いた状態から、それぞれの担当範囲を別々に実装している。

このため、エラー定義、診断クラス、JSONパラメータが片側にだけ存在するdiffを、もう片側が意図的に削除・拒否した証拠とは扱わない。原則として共通スケルトンから担当側だけが書き加えた結果と解釈し、履歴、`docs/error_list.txt` の担当、呼出し元、実装内容を確認して採否を判断する。特にvendor側に名称、空メソッド、JSON雛形が残り、SHI側に具体的な判定・ログ・runtime接続がある場合は、SHI担当機能の移植候補として優先的に検討する。

一部には、担当外のエラーであってもスケルトンを超えて実装を進めたように見える箇所があり得る。その場合も、原則として `docs/error_list.txt` 上の担当者が作成した実装を正とし、担当外側の実装だけを根拠に上書きしない。両側に実装がある場合は、先に担当、判定条件、パラメータ、ログ、runtime接続、テストを比較して、担当実装を欠落なく移植する。

したがって、次を禁止する。

- `git merge --allow-unrelated-histories` を主たる統合手段にする
- ディレクトリ単位でSHI版をvendor版へ上書きする
- 大規模コミットをそのままcherry-pickする
- ファイル全体を採用してからvendorの変更を戻す

SHI側は参照専用とし、vendor版へ機能単位で再移植する。

## 2. 基本方針

### 2.1 設計上の優先順位

ソフトウェア全体のアーキテクチャ、起動、停止、再起動、プロセス管理、動作モード遷移、性能最適化はvendor方式を優先する。

特に以下は保護領域とする。

- `argus_bootfig_jetson.sh`
- `argus_bootfig.sh`
- `argus_synchro/__main__.py` のメインループとモード遷移
- `argus_synchro/SystemMonitor/`
- `ProcessManager` / `ProcessActivator`
- `StatusMMAP` / `ArgusInfoMMAP`
- CPU affinity、プロセス起動順、停止順、再起動条件
- `operation_mode` の切替方式
- C++/Python境界と共有メモリABI

保護領域を絶対に変更しないという意味ではない。SHI機能を接続する場合も、vendorの制御フローを土台に最小変更で行う。

### 2.2 config差分

通常の設定値差分は統合作業の優先度を下げる。ただし、次はコード契約なので無視しない。

- 新しい設定キーを読むコードと設定スキーマの整合
- `ErrorConfig` の診断パラメータ
- 機種別ファイルの必須キー
- `operation_mode` と起動時リセット方針
- CPU affinityなどvendorの性能・起動設計に関係する値

SHI版 `startup_reset_policy.py` は起動時に `operation_mode=0` を設定するが、vendor版は前回モード継続を意図している。現時点ではvendor方針を採用する。

### 2.3 採否ラベル

各機能を次のいずれかに分類する。

- `vendor-keep`: vendor版を維持
- `manual-port`: SHIの要求・振る舞いをvendor構造へ再実装
- `shi-adopt`: 独立性が高くSHI実装をほぼそのまま採用可能
- `drop`: vendorに同等以上の実装がある、または旧設計のため不採用
- `decision-needed`: 要件または責任分界の確認が必要

### 2.4 ログ実装の維持方針

既存ログの基本的な呼出し方と責任分界はvendor方式を優先する。SHI側の書き方へ統一すること自体を目的に変更しない。

SHI担当エラーについては、SHI側の完成した判定ロジック、状態遷移、設定パラメータ、ログ内容を尊重する。一方、検出からログ出力までの責務分担と基本構造はvendor方式へ変更して統合する。具体的には、観測値と例外の取得は所有process、診断の登録と例外分類は `SharedErrors`、有効化・判定・状態遷移・ログ文面・logger所有は各診断クラス、出力選択は共通 `log_output()` の責務とする。processや `SharedErrors` がDレベルのログ文面を直接組み立てて出力するSHI実装は、そのまま採用しない。

命名、クラス構成、引数形式、ログ記述など、上記の責務分担に必須ではない追加統一は機能マージと同時に広げず、マージ完了後の別レビューで相談して決める。

特に次を原則として維持する。

- `log_output()` を通す共通dispatch
- `ResultDiagnosis` による発生・復帰状態の指定
- `StateErrorDIndex` / `ModuleErrorIndex` によるエラー種別の指定
- 診断クラスが持つloggerと `_error_log_output()` の責任
- processから診断へ渡す既存の文脈引数

ログ洪水抑止などの追加要件は、可能な限り診断クラス内部へ実装し、process側のvendor呼出し形式を維持する。既存ログだけでは不足するデバッグ情報や終了理由などを追加する場合はこの限りではないが、既存ログ経路の置換とは分けてレビューし、既存ログを失わないことをテストする。

## 3. 最初に扱う領域: ファイルI/Oエラー

SHI側では多くのファイル読取箇所へエラー処理が追加されている。変更は複数process、校正処理、logger、起動処理へ広がっており、ファイル単位・コミット単位の採用には向かない。

最初は、各読取箇所ではなく共通診断契約から統合する。

### 3.1 エラー分類

例外型だけで分類してはいけない。例えば `FileNotFoundError` / `OSError` は、読取対象によりCE005、CE013、汎用Dレベルのいずれにもなり得る。パスと操作対象を知る所有側が分類する。

| 読取・書込対象 | 原則の分類 |
|---|---|
| 必須設定ファイル | CE005 設定ファイル欠損/破損 |
| 機体モデル | CE004 機体モデルファイル欠損/破損 |
| センサ校正データ | CE006 |
| カメラ校正データ | CE007-CE010 |
| mmap | CE011 |
| AIモデル | CE013 |
| ログ出力 | CE015 ログファイルI/Oエラー |
| ファイル入力データ、非重要補助ファイル | Dレベル `FILE_IO_ERROR` |

同じ例外を複数箇所で同じI/O診断へ二重計上しない。固有エラーに分類できるものは、汎用 `FILE_IO_ERROR` より固有エラーを優先する。SHI実装では、I/O診断後に再送出された例外を外側のモジュールエラーとして記録する場合がある。これは同じ診断の二重計上ではなくモジュール境界の可観測性として現状維持し、変更する場合は別の設計判断とする。

### 3.2 最初の実装単位

最初のPR/差分は次だけに限定する。

1. `StateErrorDIndex.FILE_IO_ERROR`
2. `FileIoErrorParameters`
3. `FileIoError`
4. `SharedErrors.state_errors_D` への登録
5. 必要最小限の `error_config.json` 項目
6. index、検出、ログ引数、無効化を確認する単体テスト

この段階では各 `open()` やprocessへ接続しない。

SHI側の `FileIoError` は、概ね次の契約を持つ。

- 用途: 重要設定以外のファイル読取エラー
- `detect_error(has_file_io_error: bool)`
- ログ文脈: `path`, `operation`, `error_detail`
- Dレベルとして警告ログを記録

この契約をvendor側の現在の `StateErrorDiagnosisD` APIと照合し、戻り値・復帰・イベント通知をテストで確定してから呼出し側へ広げる。

### 3.3 最初の縦方向接続

共通基盤の次は、周辺監視モードのLiDARファイル入力を候補とする。

- providerをスタブ化して `OSError` を発生させる
- process境界でパスと操作名を付けて `FILE_IO_ERROR` を記録する
- vendor本来の再送出・継続・停止動作を変えない
- 正常入力時の戻り値とheartbeatを変えない
- 校正モードや実機LiDAR入力へ影響させない

これを統合パターンとして、カメラ、CAN/IMU、補助ファイルへ展開する。

### 3.4 例外境界のルール

- 全ての `open()` を機械的に囲まない
- パスと操作内容が分かる最も近い所有境界で捕捉する
- 内側で診断・記録して再送出した例外を、外側で再度同じI/O診断へ計上しない
- 再送出後のモジュールエラーログはSHIの既存構造を維持し、抑止は別の設計判断とする
- `except Exception` を一律にI/Oエラーへ分類しない
- `KeyboardInterrupt` や正常なプロセス停止をエラーにしない
- 診断追加によってvendorのリトライ、再起動、モード遷移を変えない
- エラー発生時に未初期化変数を後続処理で参照しない

## 4. 推奨統合順

1. vendor正常系の基準測定
2. ファイルI/Oエラー分類表と共通診断の単体テスト
3. 汎用 `FILE_IO_ERROR` 基盤
4. 周辺監視のLiDARファイル入力1経路
5. カメラ、CAN/IMUなど通常運転の残りのファイル入力
6. process初期化時のJSON/CSV読取
7. CE004、CE006-CE010、CE013など対象固有のI/O処理
8. CE015 logger処理
9. 校正サブシステム
10. 起動・モード遷移を含む統合テスト
11. Jetson実機での正常系、異常系、性能確認

`calibration_mat_generator_modules/` は後段にする。SHIコミット `9432a4f` はI/O処理と校正アルゴリズム変更が19ファイルに混在し、コミットごとの採用に向かない。

CE015はlogger内部で扱う。ログ書込失敗時に同じファイルloggerへエラーを書こうとすると再帰するため、汎用I/Oとは別のレビュー・テスト単位にする。

## 5. SHI側で確認済みの主な機能変更

エラー処理以外にも、少なくとも次が存在する。

- 負荷低減モード
- ファイル入力のループ・終了制御
- 校正状態遷移と校正結果診断
- 設定ファイル検証
- 機種別設定
- CANデコーダ分離
- LiDAR復号高速化
- TensorRT関連変更
- ICP状態管理
- 2D-3D / 3D-3D校正修正

これらをエラー処理の付随差分として一括採用しない。各機能を独立した台帳行とPRに分ける。

SHI側だけで確認されたテスト:

- `test_accumulate_points.py`
- `test_calibration3d3d_error_completion.py`
- `test_reduced_load_mode.py`
- `test_surround_file_input_loop.py`

テストファイルもそのままコピーせず、vendor側APIと期待仕様を確認してから移植する。

## 6. 最低限の検証ゲート

各作業単位で、可能な限り次を順に実施する。

1. 対象診断または対象processの狭い単体テスト
2. 変更Pythonファイルの構文・型チェック
3. 関連する既存テスト
4. `git diff --check`
5. 正常系の起動・停止
6. 影響する場合はモード遷移試験
7. 性能に触れた場合は変更前後の測定

モード遷移では最低限、次を確認する。

- `operation_mode=0` での起動
- `operation_mode=1` での起動
- 周辺監視から校正
- 校正から周辺監視
- 繰返し遷移
- 遷移中の設定再読込
- 子プロセスが残留しないこと
- CE014の検出と復帰
- 再起動後のモードがvendor仕様どおりであること

## 7. ビルドに関する既知事項

`make install` はPython 3.12を使用する。

2026-09-03に、コピー元で生成された `argus_synchro_lib/build/**/CMakeCache.txt` が旧絶対パス `/mnt/nvme/NSWargus_synchro_2026_0825/...` を保持し、別配置でCMakeが失敗する問題を確認した。

対応:

- `argus_synchro_lib/build` を削除して再構成すると解消する
- `Makefile` に、`CMAKE_HOME_DIRECTORY` が現配置と異なる場合だけbuildを削除する前処理を追加済み

確認結果:

- `make install` 成功
- `argus_synchro==2026.8.25` インストール成功
- `argus_synchro_lib==2026.8.25` ビルド・インストール成功
- `import argus_synchro_lib.controller` 成功
- `/dev/shm/status.mmap` は4バイトで作成

## 8. 作業ツリーの取扱い

作業ツリーがdirtyでも、担当外の変更を戻さない。

2026-09-03の確認時点では、少なくとも次が存在した。

- `Makefile`: CMakeキャッシュ再配置対策（今回追加）
- `config/settings.ini`: 既存の変更。由来未確認のため戻さない
- `docs/error-handling-review-ledger.md`: 未追跡
- `docs/error_list.txt`: 未追跡

別チャットのCopilotは、作業開始時に `git status --short` を確認し、既存変更をユーザー変更として扱うこと。

## 9. 統合台帳

各作業開始時に行を追加し、完了時に判断、実装先、検証結果を更新する。

| ID | 機能・論点 | SHI根拠 | 分類 | 状態 | 実装先 | 検証・備考 |
|---|---|---|---|---|---|---|
| M-001 | 起動・プロセス・モード遷移骨格 | vendor最新版 | vendor-keep | decided | `__main__.py`, `SystemMonitor/`, boot scripts | vendor制御を基準にする |
| M-002 | 汎用Dレベル `FILE_IO_ERROR` | SHI `a487f5f` ほか | manual-port | verified | `state_d_errors.py`, `shared_errors.py`, tests | index末尾へ追加、専用テスト6件pass |
| M-003 | 周辺監視LiDARファイル入力I/O | SHI `points_process.py` | manual-port | verified | vendor `points_process.py`, tests | ファイル入力時だけ診断、元例外を再送出、専用テスト2件pass |
| M-004 | CE015ログファイルI/O | SHI logger/action diagnosis | manual-port | verified | `common/app_logger.py`, action diagnosis, `__main__.py`, tests | handler callbackで検知し、同一signatureの連続計上を抑止 |
| M-005 | 校正サブシステムのI/O境界 | SHI `9432a4f` | decision-needed | deferred | calibration modules | 校正全体を後段で扱い、ユーザー側アルゴリズム変更の採用方針と合わせて判断する |
| M-006 | 負荷低減モード | SHI `2283a0a` | manual-port | verified | vendor reduced-load制御/accumulation/tests | vendor閾値を維持し、モード別deque実効上限だけを追加 |
| M-007 | ファイル入力ループ | SHI `e2362ec` ほか | manual-port | verified | app config/process/provider/tests | 周辺監視のcamera/LiDAR/CAN/GetDataを終了frame後に開始frameへ同期して戻す。校正・実機入力は対象外 |
| M-008 | 周辺監視カメラ動画入力I/O | SHI `image_process.py` | manual-port | verified | vendor `image_process.py`, tests | 動画open/initだけを診断、専用テスト2件pass |
| M-009 | カメラJSON読取検証 | SHI `image_process.py` | drop | verified | docs/固有CE設計 | SHIの汎用FILE_IO事前検証は不採用。通常設定はCE005、fisheyeはCE007-CE010で別途接続する |
| M-010 | 重要度D状態診断のエッジ化 | SHI `error_diagnosis.py` | shi-adopt | verified | vendor D基底, tests | vendor index/APIを維持し、DETECTION/KEEPING/RECOVERY/NORMALを返す |
| M-011 | モジュール例外traceback | vendor `state_d_errors.py` | vendor-keep | verified | module error classes, tests | vendorの `exc_info=True` で実ファイルへのtraceback出力を確認 |
| M-012 | 継続モジュール例外の時間間引き | SHI `_ModuleError` | manual-port | verified | error config/module errors/tests | 全16種へ展開。vendorのprocess呼出し、index、引数、ログ文面を維持 |
| M-012a | カメラ継続モジュール例外の時間間引き | SHI `_ModuleError` | manual-port | verified | camera error config/module error/image process/tests | 同一signatureを60秒間抑止し、初回・変更時はtraceback、時間経過後は要約 |
| M-012b | LiDAR継続モジュール例外の時間間引き | SHI `_ModuleError` | manual-port | verified | lidar error config/module error/points process/tests | vendorのlog_output契約を維持し、同一signatureを時間間引き |
| M-012c | 蓄積継続モジュール例外の時間間引き | SHI `_ModuleError` | manual-port | verified | storage error config/accumulation module error/tests | processを変更せず、vendorのlog_output契約内で時間間引き |
| M-012d | 既存設定6種のmodule error時間間引き | SHI `_ModuleError` | manual-port | verified | CAN/2D-3D/3D検知/人検知/衝突/校正 | vendor直接継承を維持し、D基底の既定間引き判断を利用 |
| M-012e | vendor追加7種のmodule error時間間引き | M-012共通契約 | manual-port | verified | IMU/AppManager/Main/PointsRefine/Visual/LiDAR Shift/GetData | vendor直接継承を維持し、省略可能な設定型を追加 |
| M-013 | process終了時の診断情報 | SHI process `finally` | manual-port | verified | visual/process base | 校正を対象外とし、vendorの終了処理を残して観測ログだけを追加 |
| M-013a | Visual終了時のactivator状態ログ | SHI `VisualProcess._loop()` | manual-port | verified | vendor `visual_process.py`, tests | vendorの終了フラグ・既存終了ログを維持して観測ログだけを追加 |
| M-013b | message flow停止開始processログ | SHI `ProcessBase._unsubscribe()` | manual-port | verified | vendor `process.py`, tests | logger初期化前を許容し、既存flow停止処理を維持 |
| M-014 | ログローテーション後のgzip圧縮失敗診断 | SHI `LogCompressionFailure` / logger callback | manual-port | verified | logger/D診断/AppManager/tests | 未圧縮backupを保持し、CE015へ重複計上しない |
| M-015 | ログレコード時刻逆行診断 | SHI `LogTimeReversal` / logger callback | manual-port | verified | logger/D診断/AppManager/tests | 許容秒を超える逆行を共有イベントとして診断 |
| M-016 | CANサブシステムの混合統合 | SHI `47ada36` ほか | decision-needed | deferred | CAN sensor/file/config/diagnosis/tests | vendorとSHI双方に必要な実装があり、全体diffと実機仕様を確認して一括判断する |
| M-017 | DレベルLidarデータ欠落 | SHI `a487f5f` / `docs/error_list.txt` | manual-port | verified | D診断/Points/shared errors/config/tests | 接続エラー中を除外し、0より多く閾値未満の点群をエッジ診断する |
| M-018 | DレベルAI推論結果異常 | SHI `a487f5f` / `docs/error_list.txt` | manual-port | verified | D診断/ObjectDetect/shared errors/config/tests | 推論結果内容を検査し、推論例外時はDログ後に空検出へフォールバックする |
| M-019 | Dレベルモニタ接続エラー | `docs/error_list.txt` | decision-needed | deferred | なし | SHI側も未実装のためスキップ |
| M-020 | Dレベル検知対象エラー | `docs/error_list.txt` | decision-needed | deferred | なし | SHI側も未実装のためスキップ |
| M-021 | Dレベル連続リトライ上限超過 | `docs/error_list.txt` | decision-needed | deferred | なし | SHI側も未実装のためスキップ |
| M-022 | CE013 AIモデルロード失敗/破損 | SHI `4b4674c` / `docs/error_list.txt` | manual-port | verified | action diagnosis/ObjectDetect/tests | SHIの例外分類とフォールバックを維持し、CE013ログはvendor責務分担どおり診断クラスが出力する |
| M-023 | SE039 アプリケーションマネージャー未応答 | SHI `4b4674c` / `docs/error_list.txt` | manual-port | verified | state diagnosis/shared heartbeat/AppManager/ErrorMonitor/tests | SHIのheartbeat判定を維持し、ErrorMonitorからvendorの共通ログdispatchへ接続する |

状態は `pending`, `in-review`, `implemented`, `verified`, `deferred`, `rejected` を使用する。

### 2026-09-03 M-002実施記録

- vendor側には `FileIoErrorParameters` と `config/error_config.json` の `file_io_error` が既に存在した。
- 欠けていた `StateErrorDIndex.FILE_IO_ERROR`、`FileIoError`、`SharedErrors.state_errors_D` の登録を追加した。
- 既存Dレベルindex 0-6は変更せず、`FILE_IO_ERROR` を末尾のindex 7へ追加した。
- 診断入力はbool 1要素、ログ文脈は `path`, `operation`, `error_detail` の文字列3要素とした。
- `tests/test_file_io_error_diagnosis.py`: 6 passed。
- Pylanceで新規テストのエラーなし。実装ファイルの残存指摘は既存コードに限られる。
- `tests/test_shared_err_config.py` は2件失敗。テストが旧属性 `camera0_connection_error` を参照する既存不整合で、M-002とは無関係のため変更していない。
- 次はM-003として、周辺監視LiDARファイル入力の例外1経路だけを接続する。

### 2026-09-03 M-003実施記録

- `PointsProviderProcess._err_config_load()` で `FILE_IO_ERROR` の設定を反映するようにした。
- `_provider.get_accum_points()` の `OSError`, `ValueError`, `TypeError` をファイル入力時だけ `FILE_IO_ERROR` として記録する。
- ファイル入力の読取成功時は `errors_diagnosis(False)` で診断状態を正常へ戻し、後続の再発を新しい発生エッジとして扱えるようにする。
- ログ文脈はLiDARファイルパス、`read file-input LiDAR point cloud`、例外型とメッセージ。
- 診断後もvendor/SHIの既存制御どおり元例外を再送出する。実機入力時はFILE_IO_ERRORへ分類しない。
- SHI側でもFILE_IO_ERRORは `state_errors_D_ex` に含まれず、再送出後に外側のLiDARモジュールエラーが記録され得る。これは現状維持した。
- `tests/test_points_file_io_error.py`: 2 passed。
- M-002とM-003の専用テスト合計: 8 passed。
- `points_process.py` のPylance残存1件は既存の `NDArray | None` に関する指摘で、今回の変更箇所ではない。
- 次のM-008はカメラの `_update()` ではなく、`_change_device()` 内の `Mcde7000File` 作成と `init_capture()` が所有する動画入力初期化を対象とする。
- SHIの `_check_camera_json_file()` は同じファイルにあるが、校正データと通常設定の固有エラー分類が必要なためM-009へ分離する。

### 2026-09-03 M-008実施記録

- `CameraProviderProcess._err_config_load()` で `FILE_IO_ERROR` の設定を反映するようにした。
- `_change_device()` のファイル入力分岐で、`Mcde7000File` 作成と `init_capture()` の `OSError`, `RuntimeError`, `ValueError`, `TypeError` を `FILE_IO_ERROR` として記録する。
- 動画capture初期化成功時は `errors_diagnosis(False)` で診断状態を正常へ戻す。
- ログ文脈はカメラ動画パス、`read file-input camera video`、例外型とメッセージ。
- 診断後は元例外を再送出する。provider生成、SHIライブラリ実機、MCDE7000実機の分岐は変更していない。
- `tests/test_camera_file_io_error.py`: 動画open失敗とcapture初期化失敗の2件がpass。
- カメラJSON読取検証は取り込まず、M-009の分類判断として残した。

### 2026-09-03 M-009判断記録

- SHIの `_check_camera_json_file()` は通常カメラ設定JSONとfisheye校正JSONを同じ `FILE_IO_ERROR` として事前検証する。
- CE005 `CONFIG_FILE_MISSING` は設定ファイルの欠損/破損を扱い、I/O、Unicode decode、config parse系例外を対象とする既存の固有診断である。
- CE007～CE010 `CAMERA_N_CALIB_DATA_INVALID` は各カメラの校正データ不正を扱う固有診断である。現状の `detect_error()` は未実装のため、例外・構造・数値のどこまでを不正とするかを先に定義する必要がある。
- 固有CEを汎用Dレベルより優先する方針に従い、SHIの汎用FILE_IO事前検証は移植しない。
- 通常カメラ設定JSONは既存CE005の発生トリガーへ追加する作業、fisheye校正JSONはCE007～CE010の診断契約を実装する作業として分離する。
- M-008の動画入力ファイルは設定・校正データではなく運転入力なので、引き続き `FILE_IO_ERROR` とする。

### 2026-09-03 重要度D・モジュール例外の全体方針

- `StateErrorDIndex`、`ModuleErrorIndex`、`state_errors_D`、`state_errors_D_ex`、`module_errors` の登録順と呼出し区分はvendorを正とする。
- SHI独自のindex再編や、通常診断・例外分類・モジュール例外の区分変更は移植しない。
- 状態を継続評価する重要度D診断は、発生時 `DETECTION`、継続時 `KEEPING`、消失時 `RECOVERY`、正常継続時 `NORMAL` を返し、ログは発生・消失エッジだけにする。
- エッジ状態は診断インスタンス単位で保持される。同一process内で1つの診断インスタンスを複数の独立入力へ使う場合、入力ごとの状態を区別できないため、必要なら呼出しキー別状態を持つ診断として個別設計する。
- vendorのモジュールエラー `_error_log_output()` は例外型・メッセージと `exc_info=True` を使い、各processの `except` 節内から同期的に呼ばれている。実ファイルログにもtracebackが出るため、この部分はvendor実装を維持する。
- SHIの `_ModuleError.log_exception()` は、初回または例外signature変更時にtracebackを出し、同一signature継続時は設定間隔ごとの要約ログに抑える。これはログ洪水対策として有効だが、`ongoing_log_interval_sec` の設定追加と全モジュールcatchの変更が必要なためM-012へ分離する。
- SHIのfinally変更は一様ではない。特に `VisualProcess` は終了理由ログを追加する一方でvendorの終了フラグ更新を置換しているため、そのまま移植しない。vendorの終了処理を残したまま、process名・activator・restart要求などの観測ログだけをM-013で候補ごとに追加する。

### 2026-09-03 M-010/M-011実施記録

- `StateErrorDiagnosisD` に直前検出状態を追加し、SHIの発生・消失エッジ判定をvendor基底へ移植した。index、登録順、公開呼出しAPIは変更していない。
- `reset_error()` は直前検出状態を解除し、同じ異常を次回 `DETECTION` として扱う。
- `tests/test_file_io_error_diagnosis.py` で `DETECTION -> KEEPING -> RECOVERY -> NORMAL -> DETECTION` とreset後の再検出を確認した。
- M-003/M-008のFILE_IO経路は成功時にも `False` を診断し、障害解消後の再発検出を可能にした。
- `tests/test_module_error_logging.py` でvendorのカメラモジュールエラーが例外型・本文・tracebackを実ファイルへ出力することを確認した。
- M-011ではproduction codeを変更していない。SHIの `log_exception()` call site置換は行わない。
- M-003/M-008/M-010/M-011の専用テストは12件pass。
- `test_detect2d.py` は実TensorRTモデル実行 `test_damoyolo_onnx_accepts_batch_on_tensorrt[1]` が長時間完了しなかったため、全pytest実行をそこで中止した。
- `test_detect2d.py` を除く初回実行では60 passed、18 failedだった。調査の結果、重要度D変更による回帰ではなくvendorテストと現行vendor契約の不一致だった。
- memory leak 3件は実機入力型に合わせて `ram_used_mb` をintへ修正、monitor 6件は2要素 `ResultDiagnosis` と復帰条件なしのvendor契約へ修正、shared error config 2件は共通名 `camera_n_connection_error` へ修正し、合計11件がpass。
- machine remove 7件は要素単位maskで点群を1次元化するテスト不具合を行単位maskへ修正した。その後、round-cuboid用テスト点群と現行vendor C++判定の不一致が判明したため、理由付き `xfail` として隔離した。C++ production codeは変更していない。
- 修正した4群の結果は12 passed、7 xfailed。関連ファイルのVS Code/Pylance診断なし、`git diff --check` 成功。
- 長時間TensorRT実モデルテストを含む `test_detect2d.py` を除く最終結果は71 passed、7 xfailed、通常失敗0件。

### 2026-09-03 M-012a実施記録

- 全module一括変更は行わず、最初の移植対象を `CameraProviderProcess` の例外経路に限定した。
- `CameraModuleErrorParameters` に `ongoing_log_interval_sec` を既定値60秒で追加した。既存 `error_config.json` では省略可能とし、設定ファイルの更新を必須にしない。
- signatureは例外型と例外メッセージ先頭行の組とする。初回またはsignature変更時は即時にtraceback付きで記録する。
- 同一signatureは設定時間内の再出力を抑止し、設定時間経過後はtracebackなしの要約ログを記録する。待機を延長し続けないよう、最後に実際に出力した時刻をmonotonic時刻で保持する。
- `CameraProviderProcess` はvendor形式の `log_output(ResultDiagnosis.DETECTION, ResultDiagnosis.DETECTION, ModuleErrorIndex.CAMERA_MODULE_ERROR, exception, camera_index)` を維持する。
- 間引き判断は `CameraModuleError._error_log_output()` 内部へ閉じ込め、vendorの共通dispatch、index指定、カメラ番号引数を維持した。
- `tests/test_module_error_logging.py` でvendorの `log_output()` を経由し、初回、時間内抑止、60秒後要約、signature変更を検証した。
- module logging、camera FILE_IO、shared error configの関連テストは8件pass。対象ファイルのVS Code/Pylance診断は0件。
- M-012の他module展開では、各設定型とcatchを個別に確認し、同じ共通契約を適用する。

### 2026-09-04 M-012b実施記録

- `PointsProviderProcess` はvendor形式の `log_output(ResultDiagnosis.DETECTION, ResultDiagnosis.DETECTION, ModuleErrorIndex.LIDAR_MODULE_ERROR, exception, lidar_index)` を使用する。
- 既存catchでは `LidarModuleError._error_log_output()` が要求するLiDAR番号が欠けていたため、呼出し構造を変えず末尾に `self._index` を補った。
- `LidarModuleErrorParameters` に省略可能な `ongoing_log_interval_sec` を既定値60秒で追加した。
- 間引き判断は `LidarModuleError._error_log_output()` 内部へ限定し、初回・signature変更時はtraceback、同一signatureの時間経過後は要約を記録する。
- カメラとLiDARで共通基底への再編は行わず、vendorの既存module errorクラス構造を維持した。
- module logging、LiDAR FILE_IO、shared error configの関連テストは9件pass。対象ファイルのVS Code/Pylance診断は0件。

### 2026-09-04 M-012c実施記録

- `PointsRefineProcess` の蓄積例外経路は、vendor形式の `log_output(ResultDiagnosis.DETECTION, ResultDiagnosis.DETECTION, ModuleErrorIndex.ACCUMULATION_MODULE_ERROR, exception)` をすでに満たすため変更していない。
- `StorageModuleErrorParameters` に省略可能な `ongoing_log_interval_sec` を既定値60秒で追加した。
- 間引き判断は `AccumulationModuleError._error_log_output()` 内部へ限定し、初回・signature変更時はtraceback、同一signatureの時間経過後は要約を記録する。
- 既存module errorクラス構造を維持し、カメラ・LiDARとの共通基底への再編は行っていない。
- module loggingとshared error configの関連テストは7件pass。変更3ファイルのVS Code/Pylance診断は0件。
- PointsRefine／蓄積processの専用テストは見つからないため、process実行を含む回帰は未実施。今回process codeに変更はない。

### 2026-09-04 M-012d/M-012e実施記録

- ユーザー判断により、残りmodule errorは同型のものをまとめて移植した。
- 共通基底への再編はvendorの見た目と責任分界を大きく変えるため不採用とし、全16クラスはvendorどおり `StateErrorDiagnosisD` を直接継承する。
- 当初Camera/LiDAR/Accumulationへ個別実装した状態保持と `_should_log()` は、全moduleで同じ要件であることを確認後、重複を残さず `StateErrorDiagnosisD` の既定実装へ統一した。
- 全16種は、vendorクラス内の差分を抑えるため `StateErrorDiagnosisD` の既定状態フィールドと `_should_log()` を利用する。共通基底の追加や継承関係の変更は行わない。
- 各vendorクラス内に `update()`、`excepts_diagnosis()`、`_error_log_output()`、引数検証、ログ文面、`self._logger.warning()` を残した。`ModuleErrorIndex` とprocess側call siteも維持した。
- M-012dでは既存設定型があるCAN、2D-3D紐づけ、3D物体検知、カメラ人検知、衝突判定、校正の6種へ `ongoing_log_interval_sec` を追加した。
- M-012eではvendor追加のIMU、AppManager、Main、PointsRefine、Visual、LiDAR Shift Monitor、GetDataの7種に明示的なparameter型と `ErrorConfig` 属性を追加した。
- 新設定はすべて既定値60秒で、既存 `error_config.json` では省略可能。既存JSONを使うshared error configテストで後方互換を確認した。
- 全16 module errorが `StateErrorDiagnosisD` を直接継承し、D基底の同じ既定実装により、初回・signature変更時はtraceback、同一signatureの時間経過後は要約を記録する。各module errorクラスには設定反映、抑止時の早期return、既存ログの `exc_info` 切替だけを追加する。
- この統一はSHIのクラス構造や書き方を採用するためではない。vendorの `log_output()`、各module errorの引数検証・ログ文面・`self._logger.warning()` を維持し、追加要件に必須な共通状態と判定だけを既存D基底へ置く最小差分方針である。
- module loggingとshared error configは21件pass。全16クラスの直接継承も構造契約としてテストした。
- module error変更範囲と設定・テストファイルに新規VS Code/Pylance診断はない。`state_d_errors.py` 前半には今回と無関係の既存型指摘が残る。
- 既知の長時間TensorRT実モデルテストを含む `test_detect2d.py` を除く全体回帰は88 passed、7 xfailed、通常失敗0件。7 xfailedと7 warningsは既知のvendor由来。

### 2026-09-04 M-013a実施記録

- M-012の最終変更はコミット `6339422`（全モジュール共通でmodule error見直し。変更の最小化。）として確定した。
- M-013候補としてVisual、GetData、校正の終了処理だけをvendorとSHIで比較した。
- GetDataの `finally` は両者とも `stack.close()` のみで移植対象となる差分はなかった。
- 校正はSHI側で終了条件と後処理の制御変更を含むため、観測ログだけの最小移植対象にはせず継続レビューとした。
- VisualはSHIにprocess activator、restart要求、入力flow activatorを記録する終了ログがあり、vendorの制御を変えず追加できると判断した。
- vendor既存の `self.sec.Scruti_ex.IsFinished.value = True` と `終了条件に到達.` は順序も含めて維持し、その直前に観測ログだけを追加した。
- `tests/test_visual_process_exit_logging.py` で無効化済みactivatorから即終了させ、詳細ログ、終了フラグ、既存終了ログを確認した。1 passed。

### 2026-09-04 校正領域の統合方針

- 校正関連はファイル間差分が大きく、ユーザー側でアルゴリズム変更が行われているため、通常領域と同じvendor最小差分方針だけでは採否を決めない。
- 校正領域は後回しとし、I/O、終了処理、アルゴリズムを細かく切り離して先行移植しない。校正全体の設計と動作を確認できる段階でまとめて扱う。
- 後段の校正統合では、起動・停止・process管理など全体アーキテクチャはvendorとの整合を確認しつつ、校正処理の内容はユーザー側実装を採用する項目が多くなる前提で比較する。
- M-013の終了時診断情報から校正processを外す。校正の終了処理はM-005を再開した際に、アルゴリズム変更と一緒に判断する。

### 2026-09-04 M-013b実施記録

- 校正を除く残り候補としてAppManagerと共通 `ProcessBase` の終了処理をvendor/SHIで比較した。
- AppManagerの `finally` は両者で同一であり、追加する終了観測ログはなかった。
- SHIの `ProcessBase._unsubscribe()` には、message flowの停止を開始したprocess名を記録するwarningがある。vendorのstartup/loop wait解除と各synchronizer停止は変更せず、その直前に同じログを追加した。
- `stop()` など親process側からlogger初期化前に呼ばれる経路があるため、SHIどおり `getattr(self, "_logger", None)` でログだけを省略可能にした。flow停止は常に実行する。
- `tests/test_process_manager.py` にlogger初期化後と初期化前の2経路を追加し、ログ出力とsynchronizer停止を確認した。2 passed。
- Visual、GetData、AppManager、共通ProcessBaseの比較を完了したため、校正を除くM-013をverifiedとした。
- `test_detect2d.py` を除くM-013完了時の全体回帰は91 passed、7 xfailed、通常失敗0件。変更箇所のVS Code診断なし、`py_compile` と `git diff --check` 成功。

### 2026-09-04 M-004実施記録

- vendorの `AppLogger` / `AppLoggerFactory` 構造とlogger登録・更新順を維持し、SHIの `logging.Handler.handleError()` callback方式だけを移植した。
- 圧縮有効時は既存 `GZipRotatingFileHandler`、無効時はcallback対応の `RotatingFileHandler` subclassで、logging内部が捕捉した `OSError` をCE015診断へ渡す。
- callbackは同じfile loggerへログを出さず、`LogFileIoErrorDiagnosis.excepts_diagnosis()` が共有エラーカウンタだけを更新するため、ログ書込み失敗による再帰を作らない。
- CE015は `OSError` とその派生例外だけを対象とする。同じ例外型・メッセージ先頭行は1秒間カウンタ加算を抑止し、loggingの連続失敗によるカウンタ洪水を防ぐ。
- `__main__.py` は全loggerのfile handler更新後、既存 `ActionErrorIndex.LOG_FILE_IO_ERROR` の診断callbackをfactoryへ登録する。後続のlogger追加・再更新でもcallbackを伝播する。
- SHIに隣接して存在する圧縮失敗専用D診断とログ時刻逆行診断はM-004の対象外とし、今回追加していない。
- `tests/test_app_logger_io_error.py` で圧縮有無の書込み失敗、factory更新後のcallback維持、同一障害の時間抑止、非I/O例外の除外を確認した。5 passed。変更4ファイルのVS Code診断なし。
- `test_detect2d.py` を除く全体回帰は96 passed、7 xfailed、通常失敗0件。`py_compile` と `git diff --check` 成功。

### 2026-09-04 M-014実施記録

- M-004から分離したSHIのログ圧縮失敗専用Dレベル診断を、vendorのD診断構造へ移植した。
- 既存 `StateErrorDIndex` 0～7を変更せず、`LOG_COMPRESSION_FAILURE` を末尾へ追加した。設定parameter、`ErrorConfig.log_compression_failure`、JSON設定はvendor側に既存のものを利用する。
- `GZipRotatingFileHandler` はローテーション後のgzip化だけを `try/except` し、失敗時は専用callbackへ通知する。ローテーション済みの未圧縮ファイルは削除せず、次回処理に備えて残す。
- 圧縮失敗をhandler外へ再送出しないため、M-004のCE015 `handleError()` callbackには重複計上しない。圧縮失敗専用診断も同じfile loggerから直接ログを出さず、共有イベントカウンタだけを更新する。
- AppManagerは設定更新時に診断を更新し、既存 `_update()` の先頭で共有イベントを消費してvendorの `errors_diagnosis()` / `log_output()` 経路から「ログローテーション後の圧縮に失敗しました。」を出力する。
- SHIのcallbackは例外を渡す一方、`report_event()` は引数なしで不整合だったため、vendor側では任意の例外引数を受け取ってイベントだけを計上する契約にした。
- ログ時刻逆行診断は引き続き別の統合項目とし、M-014には含めていない。
- `tests/test_log_compression_failure.py` とM-004テストの組合せは10 passed。新規変更箇所のVS Code診断なし、`git diff --check` 成功。
- AppManager・共有設定を含む関連テストは18 passed。`test_detect2d.py` を除く全体回帰は101 passed、7 xfailed、通常失敗0件。`py_compile` 成功。

### 2026-09-04 M-015実施記録

- M-004から分離したSHIのログレコード時刻逆行Dレベル診断を、M-014と同じ共有イベント方式でvendorへ移植した。
- 既存 `StateErrorDIndex` 0～8を変更せず、`LOG_TIME_REVERSAL` を末尾へ追加した。
- 圧縮有効・無効の両file handlerが直前の `LogRecord.created` をhandler単位で保持する。初回recordは比較せず、2件目以降の時刻対だけを診断callbackへ渡す。
- `LogTimeReversalParameters.allowed_backward_sec` はSHIと同じ既定値0.0秒を追加した。JSONキー省略時も既定値を使うため既存設定と互換性がある。
- 診断は `current_time < previous_time - allowed_backward_sec` の場合だけ共有イベントを加算する。AppManagerが周期的に消費し、vendorのDレベル `errors_diagnosis()` / `log_output()` 経路から「ログ記録時刻の逆転を検出しました。」を出力する。
- callbackはfactoryのlogger追加・handler再生成後にも伝播する。console handlerは対象外で、file handlerだけを監視する。
- `tests/test_log_time_reversal.py` で圧縮有無、初回非通知、許容幅、AppManager消費、index登録、factory更新後のcallback維持を確認した。6 passed。M-004/M-014/M-015と共有設定の組合せは19 passed。新規変更箇所のVS Code診断なし。
- `test_detect2d.py` を除く全体回帰は107 passed、7 xfailed、通常失敗0件。`py_compile` と `git diff --check` 成功。

### 2026-09-04 M-006実施記録

- 現行vendorには負荷低減モードの判定、処理速度・点群数・thermal入力、状態更新、voxel size切替がすでに接続されていることを確認した。
- SHIの点群数しきい値40%/30%への変更は実験用であり、ユーザー判断により移植しない。vendorの90%/80%、開始・復帰継続回数、warningログを維持する。
- SHIのうち、負荷低減モードに応じて点群蓄積dequeの実効上限を変更する制御だけを移植した。
- dequeの `maxlen` は生成後に変更できないため、通常・負荷低減の設定値の大きい方を物理上限として初期化する。これにより、どちらの設定値が大きい場合でも対応する。
- `accumulate_point()` の先頭で現在モードの実効上限を選び、上限超過分を最古の履歴から削除する。縮小時は最新履歴を保持し、通常モードへ戻った後は新規フレームにより物理上限まで自然に増加する。
- trimは蓄積済み点群の座標変換・結合より前に行うため、負荷低減へ切り替わったフレームから処理対象履歴数を減らす。
- SHIのPointsRefine切替ログは機能に必須ではなく、vendor差分を抑えるため移植しない。process側の既存 `reduced_load_mode.enabled` 伝搬は変更していない。
- `tests/test_reduced_load_accumulation_buffer.py` で最新履歴保持、通常復帰後の再拡張、通常・負荷低減設定の大きい方を物理上限にすること、0以下の上限拒否を確認した。3 passed。変更箇所のVS Code診断なし。
- 共有設定を含む関連テストは6 passed。`test_detect2d.py` を除く全体回帰は110 passed、7 xfailed、通常失敗0件。`py_compile` と `git diff --check` 成功。

### 2026-09-04 M-007実施記録

- SHIのファイル入力ループから、通常の周辺監視モードに必要なcamera、LiDAR、CAN、GetDataのframe同期だけをvendorへ移植した。校正モードはM-005として引き続き後回しにする。
- `Scrutinizer.file_input_loop` を設定契約へ追加し、追跡対象の5つの `settings*.ini` では `True` にした。`False` の場合は終了frame後にunsubscribeする既存動作を維持する。
- camera、LiDAR、CAN入力processは、`e_frame` のデータを出力してframeが上限を超えた後、次回のprovider読取り前に `s_frame` とファイル位置を戻す。終了frame自体は欠落させない。
- 通常ファイルproviderに不足していた最小の位置変更APIだけを追加した。cameraは動画パスとindex、LiDARはファイルパスと内部参照frameを更新し、既存CAN APIを再利用した。
- GetDataも出力frameを進めた直後に同じ境界で `s_frame` へ戻す。実機入力、およびループ無効のファイル入力では従来どおりunsubscribeする。
- SHIに同居するcamera JSON検証、heartbeat、接続診断、provider fallbackなどの変更は移植していない。vendorのclock、診断、process lifecycle、fallback処理を維持した。
- `tests/test_surround_file_input_loop.py` で3 processの同期リセット、校正除外、ループ無効、GetDataのファイル入力・実機入力を確認した。3 passed。設定テストとの組合せは7 passed。変更箇所のVS Code診断なし。
- 5つの設定ファイルすべてを `AppConfig` で読み込み、`file_input_loop=True` を確認した。`test_detect2d.py` を除く全体回帰は113 passed、7 xfailed、通常失敗0件。`py_compile` 成功。

### 2026-09-04 M-016保留判断

- CANはデコーダ分離だけを独立採用せず、vendorとSHIの全体diffを比較して混合反映する方針とする。ユーザー判断により後回しにした。
- SHIコミット `47ada36` にはセンサ入力とファイル入力のデコーダ共通化、PGN設定、CSV値正規化が混在し、その後もSCX2000、新CAN反転デコーダ、CAN ID正規化、通信診断の変更が追加されている。
- 現行vendorでは旧CANのoffsetがセンサ入力で減算、ファイル入力で加算になっている。どちらを正とするかは実機仕様を含めて確認する必要がある。
- 一度作成したデコーダ分離の未コミット変更と専用テストは取り下げ、vendorの `CanHandler` 実装へ戻した。再開時はsensor/file/config/diagnosisと対応テストを一つの比較単位として扱う。

### 2026-09-04 M-017実施記録

- `docs/error_list.txt` のSHI担当エラーを棚卸しし、CANと校正の保留領域を避けて、独立して接続できるDレベル「Lidarデータ欠落」を最初の対象とした。
- エラー処理は双方が名称、番号、基本メソッド、空実装などの共通スケルトンを持った状態から担当別に実装を進めている。このためvendorに残るparameterとJSON雛形を削除意思とは解釈せず、SHI側の具体的な判定、ログ、runtime接続を移植した。
- `LidarDataMissingParameters.min_point_count` はSHIと同じ100を既定値およびJSONへ追加した。判定もSHIと同じく、LiDAR接続エラー中ではなく `0 < point_count < min_point_count` の場合に検出する。0点は接続系診断に委ねる。
- D indexは既存0～9を変更せず末尾へ追加し、vendorの `StateErrorDiagnosisD` によるDETECTION/KEEPING/RECOVERY/NORMALのエッジ制御と `log_output()` 契約を利用する。
- Pointsは点群取得成功後にLiDAR番号対応の接続エラー状態を参照し、点数とともに診断へ渡す。provider、clock、heartbeat、ファイルI/O診断などの既存制御は変更していない。
- `tests/test_lidar_data_missing.py` で閾値境界、0点除外、接続エラー中の除外、発生・継続・復帰、引数検証、Points配線を確認した。専用テストは6 passed、関連テストは13 passed。変更箇所のVS Code診断なし、`py_compile` 成功。
- `test_detect2d.py` を除く全体回帰は120 passed、7 xfailed、通常失敗0件。`config/error_config.json` は既存CRLFを維持しているため、差分検証は `git -c core.whitespace=cr-at-eol diff --check` を使用する。

### 2026-09-04 M-018実施記録

- `docs/error_list.txt` のSHI担当Dレベル「AI推論結果異常」を通常運転の `ObjectDetectProcess` へ移植した。校正内の2つのAI推論経路はM-005の保留方針に従い対象外とした。
- SHI担当実装どおり、boxesとscoresのNaN/Inf、設定範囲外のscore、0未満またはboxes件数を超える `valid_detects` を異常と判定する。`score_min=0.0`、`score_max=1.0` をparameterとJSONへ追加した。
- 正常に返った推論結果はDレベルのエッジ診断へ渡し、異常の初回だけカメラ番号付きwarningを出す。正常値へ戻ればD基底の状態を復帰させる。
- 推論実行だけを例外境界とし、通常例外はAI推論結果異常として記録した後、`NotAppliedObjDetection` の空検出結果へフォールバックしてframe処理を継続する。歪み補正、入力診断など推論外の例外と、Dレベルで分類されない例外は従来どおり上位へ伝播する。
- SHIでは内容検査用ログ引数がカメラindex、例外分類用が例外オブジェクトであるため、同じ診断クラスの `_error_log_output()` が両方を受けるよう最小限補正した。ログ内容と安全動作はSHI実装を維持した。
- `tests/test_ai_inference_result_error.py` でNaN/Inf、score上下限、valid件数、復帰、例外ログ、process配線、例外時フォールバックを確認した。専用テストは10 passed、共有設定・module errorを含む関連テストは31 passed。変更箇所のVS Code診断なし、`py_compile` とJSONパース成功。
- `test_detect2d.py` を除く全体回帰は130 passed、7 xfailed、通常失敗0件。

### 2026-09-04 SHI担当Dレベル未実装項目

- 「モニタ接続エラー」「検知対象エラー」「連続リトライ上限超過」は、ユーザー確認によりSHI側も未実装である。共通スケルトンやJSON雛形だけを根拠に推測実装せず、M-019～M-021としてスキップする。

### 2026-09-04 M-022実施記録

- SHIコミット `4b4674c` と現行SHIを直接確認し、CE013には診断ロジックと通常運転の `ObjectDetectProcess` 接続が存在することを確認した。校正内のAIモデル読込経路はM-005の保留方針に従い対象外とした。
- SHI担当実装どおり、`FileNotFoundError`、`PermissionError`、`OSError`、`RuntimeError`、`ValueError`、`ImportError`、`ModuleNotFoundError` だけをCE013としてcounterへ加算する。それ以外の例外はCE013へ計上しない。
- モデル生成または設定更新で例外が発生した場合は、SHIと同じく適用中モデルを破棄して `NotAppliedObjDetection` へ切り替え、frame処理を継続する。
- SHIではprocessがCE013ログ文面を直接出力していたため、その部分だけvendor責務分担へ変更した。processは例外を分類して診断へ渡し、`AiModelLoadFailed.log_output()` がエラー番号、文面、loggerを所有する。CE013非該当例外の観測warningは維持した。
- 過去の `error-handling-review-ledger.md` には例外分類を実装済みとする記録があったが、統合開始時のvendorコードはスケルトンへ戻っていた。今回、同文書の確定済み対象例外・counter条件とSHI実装が一致することを確認して復元した。
- `tests/test_ai_model_load_failed.py` で対象7例外、非対象例外、診断所有ログ、対象・非対象それぞれのObjectDetectフォールバックを確認した。専用テストは11 passed、AI推論・action error・共有設定を含む関連テストは47 passed。変更箇所のVS Code診断なし、`compileall` とCRLF考慮のdiff checkに成功した。
- `test_detect2d.py` を除く全体回帰は141 passed、7 xfailed、通常失敗0件。

### 2026-09-04 M-023実施記録

- SHIコミット `4b4674c` と現行SHIを確認し、SE039の診断ロジック、AppManager共有heartbeat、AppManager更新、ErrorMonitor監視を一つの機能単位としてvendorへ移植した。
- AppManagerは各 `_update()` の先頭でmonotonic heartbeatを更新して開始済み状態にし、起動待機中と正常停止後は `is_started=False` とする。ErrorMonitorは開始済みの場合だけ診断するため、意図的な未起動・停止をSE039へ誤分類しない。
- SHI担当実装どおり、heartbeat変化が0.01秒未満の状態が設定秒継続した場合、またはheartbeatが設定秒以上後退した場合に検出する。新しいheartbeatが現在時刻から設定秒以内ならエラーとフェイルセーフを復帰する。
- SHI固有の広域 `DiagnosisRuntimePolicy` は複数の未統合診断と起動制御へ影響するため今回持ち込まず、SE039に必要な起動状態ガードだけを共有AppManager状態で維持した。
- SHIのErrorMonitorは診断戻り値を破棄していたため、その部分はvendor責務分担へ変更した。ErrorMonitorは観測値を渡し、診断クラスが状態とログ文面を所有し、戻り値は共通 `log_output()` へdispatchする。
- `tests/test_application_manager_not_responding.py` で停滞、時刻後退、復帰、引数、ログ、共有状態、AppManager更新、ErrorMonitorの開始状態ガードとdispatchを確認した。専用テストは9 passed、heartbeat診断・process管理・設定・error mmapを含む関連テストは26 passed。変更箇所のVS Code診断なし、`compileall` 成功。
- `test_detect2d.py` を除く全体回帰は150 passed、7 xfailed、通常失敗0件。CRLFを考慮したdiff checkも成功した。

## 10. 次のCopilotへの開始指示

次回は、いきなり全体差分を再探索しない。次の順で開始する。

1. 本書と関連文書を読む
2. 両リポジトリのHEADと `git status --short` を確認する
3. 統合台帳から未処理項目を1件選び、そのvendor側定義、SHI側定義、隣接テストだけを読む
4. M-005校正はユーザー側アルゴリズム変更の採用方針を決めるまで着手しない
5. 最小の単体テストまたは基盤移植を行う
6. 狭いテストを直ちに実行する
7. 本書の台帳と確認結果を更新する

新しい判断が既存記録と矛盾した場合は、古い記録を黙って残さず、理由と日付を添えて本書を更新する。
