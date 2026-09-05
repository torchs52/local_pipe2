# Vendor/SHI 統合作業 引継ぎ

最終更新: 2026-09-06

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
- `StatusMMAP`
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

### 2.5 経過時間のクロック

プロセス・センサーの死活、接続停止、復帰確認、timeout、deadlineなど、経過時間で決まる判定にはOSの絶対時刻を使用しない。`time.monotonic()` または `time.perf_counter()` を使用し、共有heartbeatの書込側と比較側は同じAPIへ揃える。`time.time()` と `datetime.now()` は、人向けの表示日時、ファイル名、永続化する実時刻など絶対時刻そのものが必要な用途に限定する。

通常運転の現行区分は次のとおり。

- Camera/CAN/LiDAR/IMU/LiDAR shiftのheartbeatとAppManager接続診断: `time.perf_counter()`
- GetData/ObjectDetect/PointsRefine/VisualとAppManagerのprocess heartbeat: `time.monotonic()`
- MonitorArgus heartbeatファイルとAppManager診断: `time.perf_counter()`
- StatusMMAP鮮度、process停止deadline、ログ継続時間、tegrastats無出力timeout: `time.monotonic()`

### 2.6 メンテナンスモードに限定した採用方針

この節は統合全体の方針変更ではなく、メンテナンスモードの実装だけに適用する例外方針である。メンテナンスモードは工場出荷時だけでなく、市場でのサービス作業中にも使用する製品仕様上の正式名称である。2.1のvendorアーキテクチャ優先、`docs/error_list.txt`の実装分担、機能単位で移植する原則は引き続き維持する。

SHI側の`in_factory`を使った制御は、工場出荷時またはサービス作業中に一部の重要度Aエラーが発生することを抑止するための必須要件として採用する。この要件を成立させるために必要な範囲では、SHI担当エラーだけでなくvendor担当エラーにも最小限の編集を加える。ソース構造や記述方法をSHI実装と一致させることは目的とせず、vendorの所有境界と制御方式へ適合させる。

M-039で現行SHIの参照箇所を確認し、CE001、CE002、CE012、SE001/SE002、SE007、SE026、SE035、SE037、SE039だけを抑制対象とした。SE039は重要度BだがSHIで明示されているため対象に含む。メンテナンスモード中は新規検出とcounter・状態更新を抑制し、切替時に既存エラー状態を強制clearせず通常の復帰条件へ委ねる。重要度A全体への自動適用は行わない。

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
| M-005 | 校正サブシステムのI/O境界・設定検証 | SHI `9432a4f` ほか | decision-needed | deferred | calibration modules/config validation | SHIのcalib settings validatorを含む校正全体を後段で扱い、ユーザー側アルゴリズム変更の採用方針と合わせて判断する |
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
| M-024 | SE042 ログ出力停止 | SHI `4b4674c` / `docs/error_list.txt` | manual-port | verified | state diagnosis/AppManager/tests | ログファイルのmtime/sizeを監視し、判定とログはvendorの診断共通経路へ委譲する |
| M-025 | SE037 周辺監視モジュール未応答 | SHI `4b4674c` / `docs/error_list.txt` | manual-port | verified | state diagnosis/shared heartbeat/4 processes/AppManager/tests | GetData/ObjectDetect/PointsRefine/Visualの個別heartbeatを監視し、vendorの共通ログdispatchへ接続する |
| M-026 | CE005 設定ファイル欠損/破損 | SHI `4b4674c` / `docs/error_list.txt` | manual-port | verified | action diagnosis/load_config/tests | SHIの例外分類とcounter間引きを維持し、ログはvendor責務分担どおり診断クラスへ委譲する |
| M-027 | CE005 settings値域・型検証 | SHI `a487f5f`, `e2362ec` | manual-port | verified | config validation/common paths/tests | SHIのsettings規則とstrict/normalize方針を維持し、設定スキーマの責務としてconfig層へ配置する |
| M-028 | CE004 機体モデルファイル欠損/破損 | SHI `4b4674c` / `docs/error_list.txt` | manual-port | verified | action diagnosis/PointsRefine/Visual/tests | SHIの例外分類を維持し、ログは診断クラスへ委譲、vendorの起動失敗制御へ元例外を再送出する |
| M-029 | CE011 MMAP read/writeエラー | SHI `4b4674c` / `docs/error_list.txt` | manual-port | verified | action diagnosis/ErrorMonitor/Visual/main/tests | SHIの例外分類と境界別の継続・再送出を維持し、ログは診断クラスへ委譲する |
| M-030 | CE012 再起動ループ検出 | SHI `4b4674c` / `docs/error_list.txt` | manual-port | verified | action diagnosis/error config/main/FILE_IO_ERROR/tests | `uptime_state.json` の直近5回を600秒窓で評価し、履歴異常はFILE_IO_ERRORへ委譲する |
| M-031 | SHI担当だが未実装のCE003・CE007～CE010・SE036 | ユーザー確認 / 現行SHI | decision-needed | deferred | なし | 共通スケルトンから推測実装せず、SHI側で仕様・実装が確定するまで移植対象外とする |
| M-032 | SE040・SE041 IMU接続エラー | 現行SHI / `docs/error_list.txt` | manual-port | verified | state diagnosis/shared heartbeat/IMU/AppManager/tests | 実データheartbeatを5秒監視し、1秒以内の連続受信を5秒確認して復帰する |
| M-033 | SE001・SE002 LiDAR接続エラー | 現行SHI / `docs/error_list.txt` | manual-port | verified | state diagnosis/Points/AppManager/tests | 実点群heartbeatを5秒監視し、1秒以内の連続受信を5秒確認して復帰する |
| M-034 | 死活・経過時間クロック監査 | vendor通常運転経路 | vendor-keep | verified | sensor/process heartbeat/StatusMMAP/停止deadline/tests | 絶対時刻依存を除去し、書込側と比較側のclock APIを統一する |
| M-035 | SE008・SE009 LiDAR通信品質低下 | 現行SHI / `docs/error_list.txt` | manual-port | verified | MID360 device/provider/shared/Points/AppManager/state diagnosis/tests | packet連番欠落・点数低下イベントの3秒継続で検出し、正常5秒で復帰する |
| M-036 | SE014・SE015 LiDAR通信品質エラー | 現行SHI / `docs/error_list.txt` | manual-port | verified | state diagnosis/AppManager/tests | SE008/009 ONを30秒確認して検出し、OFFを30秒/60秒確認してerror/failsafe復帰する |
| M-037 | SE020・SE021 LiDARデータ不正 | 現行SHI / `docs/error_list.txt` | manual-port | verified | MID360 provider/shared/Points/AppManager/state diagnosis/tests | filter前のXYZ原点点割合70%以上を3秒確認して検出し、30%未満を3秒/5秒確認してerror/failsafe復帰する |
| M-038 | CE006 センサ校正データ不正（基本健全性） | 現行SHI / `docs/error_list.txt` | manual-port | verified | action diagnosis/validator/load_config/tests | CSVの存在・読込・4x4形状・有限値を起動時に検査。参照差分・校正生成結果判定はM-005と一緒に保留する |
| M-039 | メンテナンスモード中の指定エラー抑制 | 現行SHI `in_factory` / ユーザー要件 | manual-port | verified | runtime policy/対象診断/AppManager・起動経路/tests | SHI指定のCE001/002/012、SE001/002/007/026/035/037/039だけを抑制し、重要度A全体へは適用しない |
| M-040 | File watch設定再読込の一時失敗リトライ | 現行SHI `file_watch.py` / ユーザー要件 | manual-port | verified | file watch/CE005/tests | atomic save中の一時欠損・書込み途中を3回、0.2秒間隔で再試行し、全失敗時だけCE005へ渡す。起動時の無限再試行は維持する |
| M-041 | 自動校正ファイル入力の軽量終了制御 | 現行SHI `__main__.py` / ユーザー要件 | manual-port | verified | main/ProcessActivator/closables/tests | CALIBかつFile Inputの反復評価だけActivator停止と通信資源解放を行い、実機CALIBとSCRUTは量産向け停止・強制終了診断を維持する |
| M-042 | 起動時ログ診断parameter初期化 | 実機起動ログ / vendor起動順 | vendor-fix | verified | main/log diagnosis/tests | logger callback登録前にログ圧縮・時刻逆転診断を初期化し、起動直後のAttributeErrorを防ぐ |

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
- AppManagerは各 `_update()` の先頭でmonotonic heartbeatを更新して開始済み状態にし、起動待機中と正常停止後は `is_started=False` とする。ErrorMonitorは開始済みの場合だけ診断し、意図的な未起動・停止をSE039へ誤分類しない。
- LiDAR、Camera、IMUがlifecycleフラグとheartbeatを同じ共有オブジェクトに持つvendor既存パターンへ合わせ、AppManagerも共有実体を1個にした。ErrorMonitorが設定ロード前から起動するため `SharedErrors` が `SharedAppManagerExcept` を先行生成し、通常起動時の `SharedExcepts` へ同じインスタンスを注入する。`SharedErrors.AppMan_ex` と `SharedExcepts.AppMan_ex` は別名参照だが同一実体であり、前者をErrorMonitor、後者を既存process lifecycleが使用する。単体利用時は省略可能引数により従来どおり `SharedExcepts` が生成する。
- SHI担当実装どおり、heartbeat変化が0.01秒未満の状態が設定秒継続した場合、またはheartbeatが設定秒以上後退した場合に検出する。新しいheartbeatが現在時刻から設定秒以内ならエラーとフェイルセーフを復帰する。
- SHI固有の広域 `DiagnosisRuntimePolicy` は複数の未統合診断と起動制御へ影響するため今回持ち込まず、SE039に必要な起動状態ガードだけを共有AppManager状態で維持した。
- SHIのErrorMonitorは診断戻り値を破棄していたため、その部分はvendor責務分担へ変更した。ErrorMonitorは観測値を渡し、診断クラスが状態とログ文面を所有し、戻り値は共通 `log_output()` へdispatchする。
- `tests/test_application_manager_not_responding.py` で停滞、時刻後退、復帰、引数、ログ、共有状態の同一性、AppManager更新、ErrorMonitorの開始状態ガードとdispatchを確認した。専用テストは10 passed、SE042・process管理・設定・error mmapを含む関連テストは30 passed。変更箇所のVS Code診断なし、`compileall` 成功。
- `test_detect2d.py` を除く全体回帰は150 passed、7 xfailed、通常失敗0件。CRLFを考慮したdiff checkも成功した。

### 2026-09-04 M-024実施記録

- SHIコミット `4b4674c` と現行SHIを確認し、SE042の診断ロジックと通常運転のAppManager監視をvendorへ移植した。校正、CAN、logger内部のCE015処理は変更していない。
- `DEFAULT.debug_log` が示す実ログファイルのmtimeまたはsizeが変化した時刻をmonotonic clockで保持し、設定秒以上更新がなければ検出する。ファイルがローテーション等で一時的に見えない場合は最終更新時刻を進めず、停止判定を継続する。
- 更新再開後は、設定された受信間隔内の更新が連続している時間をエラー状態とフェイルセーフ状態で個別に測り、それぞれ設定秒継続した時点で復帰する。システム時刻が後退した場合の経過時間は0秒へ丸める。
- ファイルログが無効な場合は診断対象外とし、現在時刻を正常更新として渡す。これにより設定変更前に検出済みだった状態も共通復帰条件で解消できる。
- SHIのAppManagerは診断前後の共有flagから `ResultDiagnosis` を再計算していたが、vendorの `StateErrorDiagnosisC.errors_diagnosis()` が同じエッジ状態を返すため、その重複は移植しなかった。AppManagerはmtime/size観測だけを所有し、判定、状態、ログ文面、loggerは診断クラス、出力選択は共通 `log_output()` が所有する。
- `tests/test_log_output_stopped.py` で閾値、KEEPING、継続復帰、時刻後退、引数、ログ、ファイル更新・停止・一時欠落・ログ無効時のAppManager配線を確認した。専用テストは9 passed、SE039との組合せは18 passed。変更箇所のVS Code診断なし、`compileall` 成功。
- AppManager共有状態の単一インスタンス化を含め、`test_detect2d.py` を除く全体回帰は160 passed、7 xfailed、通常失敗0件。CRLFを考慮したdiff checkも成功した。

### 2026-09-04 M-025実施記録

- SHIコミット `4b4674c` と現行SHIを確認し、SE037の診断ロジックとGetData、ObjectDetect、PointsRefine、Visualの4process heartbeat監視をvendorへ移植した。校正processとCANは対象外である。
- 各processは起動完了時と主要処理の正常完了時にmonotonic heartbeatを更新する。入力待ち、入力診断でのスキップ、例外処理中は更新しないため、単にloopが回っているだけの状態を健康扱いしない。
- ObjectDetectとPointsRefineは従来 `Scruti_ex` を共有していたが、個別の未応答を識別するためSHIと同じく `ObjDet_ex`、`PointsRefine_ex` を追加した。既存の終了判定、モードリセット、状態表示、closeにも両共有状態を追加し、process lifecycleを欠落させない。
- heartbeat初期値はSHIの0.0ではなく、vendorの既存死活監視と同じ `INVALID_TIMESTAMP=-1.0` とした。AppManagerは未起動値を経過時間一覧の-1.0として診断へ渡し、全対象が未起動の場合は検出しない。
- SHI担当実装どおり、起動済み対象のいずれかが5秒を超えて未更新なら検出し、全対象が閾値内へ戻ればエラーとフェイルセーフを復帰する。最大経過秒を検出ログへ出力する。
- SHIでは閾値を診断parameterに持ちながらprocessから重複して渡していたため、vendor責務分担へ合わせて診断クラスがparameterを所有し、processは経過秒一覧だけを渡す。SHIのAppManagerで欠けていた診断戻り値の受取りと `log_output()` 呼出しも追加した。
- SHI固有の `DiagnosisRuntimePolicy` は広域影響を避けて持ち込んでいない。SE037監視はvendorのSCRUT分岐内だけで実行され、診断自体はidleを立てない。
- `tests/test_surround_monitor_module_not_responding.py` で閾値境界、未起動除外、復帰、入力検証、ログ、個別共有状態、AppManagerの経過時間とdispatchを確認した。専用テストは9 passed、対象process・AI診断・Visual終了・process管理を含む関連テストは39 passed。変更箇所のVS Code診断なし、`compileall` 成功。
- `test_detect2d.py` を除く全体回帰は169 passed、7 xfailed、通常失敗0件。CRLFを考慮したdiff checkも成功した。

### 2026-09-04 M-026実施記録

- SHIコミット `4b4674c` と現行SHIを確認し、CE005の設定ファイル例外分類とcounter間引きをvendorへ移植した。対象はI/O・Unicode・configparser系例外、および `getboolean` / `getint` 等の設定値変換失敗を表す `ValueError` である。非対象例外はCE005へ計上しない。
- 同一の例外型と先頭メッセージが1.0秒未満に反復した場合はcounterを増やさない。例外型またはメッセージが変化した場合、および1.0秒以上経過した場合は再計上する。SHI実装で失敗する空メッセージ例外も安全に分類・出力できるよう補正した。
- SHIの `load_config()` は最大3回失敗後に設定再確認を永久停止するが、これはvendorの復帰優先方針と既存の無限再試行に反するため採用しなかった。校正設定適用と広域 `DiagnosisRuntimePolicy` も、それぞれM-005保留と影響範囲外のため持ち込んでいない。
- `load_config()` は設定取得と例外捕捉だけを所有し、CE005該当時のエラー番号、文面、logger、traceback指定は `ConfigFileMissingDiagnosis.log_output()` が所有する。CE005非該当の起動例外は従来のmain汎用fatalログへ残す。
- 過去の `error-handling-review-ledger.md` は `ValueError` を対象外としていたため、SHI担当の完成実装とowner-first方針に合わせて訂正した。一方、同文書の段階的backoff・ログ間引き仕様は現行vendorコードに反映されておらず、今回のSHI機能移植とは分離して扱う。
- `tests/test_config_file_missing.py` で対象例外、非対象例外、同一signature間引き、signature変更、1秒境界、空メッセージ、診断所有ログ、`load_config()` dispatchを確認した。専用テストは20 passed、設定・共有エラー設定・CE013を含む関連テストは40 passed。変更箇所のVS Code診断なし、`compileall` とCRLF考慮のdiff checkに成功した。
- `test_detect2d.py` を除く全体回帰は189 passed、7 xfailed、通常失敗0件。

### 2026-09-04 M-027実施記録

- SHIコミット `a487f5f` と `e2362ec`、現行SHIを確認し、`settings.ini` の型・上下限・許容値検証規則と `strict` / `normalize` 方針をvendorへ移植した。対象規則はSHI実装と同じで、校正用 `calib_settings.ini` の検証はM-005保留範囲のため含めていない。
- ユーザー確認により、SHI側の校正設定用validatorも必要な機能だが、通常設定のM-027へは追加せずM-005の校正関連として後回しにする。再開時は校正設定の規則、読込・再読込境界、CE005/CE006～CE010との責務分担を校正全体と合わせて確認する。
- SHIでは `common/settings_validation.py` に置かれていたが、このモジュールは設定スキーマと補正方針を所有するため、vendorでは `config/settings_validation.py` に配置した。`common.paths` はINI読込直後にvalidatorを呼ぶだけとし、config packageの既存再exportとの循環を避けるため関数内importとしている。
- `[ConfigValidation] invalid_value_policy` が未指定の場合は `strict` とする。strictでは不正型、上下限外、許容値外を `ConfigValidationError(ValueError)` として送出し、既存CE005の分類・ログ・無限再試行経路へ接続する。normalizeでは不正型をSHI既定値へ、上下限外を境界値へ実行時補正し、補正内容をwarningへ出す。
- section名が壊れた場合、validatorは未知sectionを自動生成せず、その後の `AppConfig` 構築が `NoSectionError` / `NoOptionError` を送出する。これらもM-026でCE005対象済みであり、誤ったsectionを暗黙補完せず設定破損として扱う。
- 現行SHIには専用validatorテストがなかったため、vendor側で上下限、不正型、normalize、読込直後の実行、section名破損からCE005分類までを追加した。現行vendorの `config/*settings*.ini` 12ファイルはすべてstrict規則に適合し、専用テストは6 passed、CE005・AppConfig・共有エラー設定を含む関連テストは35 passed。変更箇所のVS Code診断なし、CRLF考慮のdiff checkに成功した。
- `test_detect2d.py` を除く全体回帰は195 passed、7 xfailed、通常失敗0件。`compileall` も成功した。

### 2026-09-04 M-028実施記録

- SHIコミット `4b4674c` と現行SHIを確認し、CE004の機体モデルファイル欠損・破損分類をvendorへ移植した。対象は `FileNotFoundError`、`PermissionError`、`IsADirectoryError`、`NotADirectoryError`、`OSError`、`UnicodeDecodeError`、`JSONDecodeError`、`ValueError`、`KeyError`、`RuntimeError` であり、非対象例外はCE004へ計上しない。
- runtime接続は `SubScrutinizer.create_machine_points()` を呼ぶPointsRefineの機体除去初期化、衝突・崖初期化、Visual初期化の3境界に限定した。機体モデル生成後の八分木、崖検出、表示初期化アルゴリズムは変更していない。
- SHIではprocessがCE004ログ文面を直接所有していたが、vendorの責務分担に合わせてエラー番号、文面、logger、traceback指定を `CraneModelFileMissingDiagnosis.log_output()` へ集約した。processは例外分類とログdispatch後に元例外を再送出し、vendor既存のprocess起動失敗・停止制御を維持する。
- M-005の校正設定・校正アルゴリズムとM-016のCAN統合は今回の対象に含めていない。広域の再試行、フォールバック、process lifecycleも追加していない。
- `tests/test_crane_model_file_missing.py` で対象10例外、非対象例外、診断所有ログ、PointsRefine・Visualの分類と再送出を確認した。専用テストは14 passed、既存Visual終了テストを含む関連テストは15 passed。変更箇所のVS Code診断なし、`compileall` 成功。
- `test_detect2d.py` を除く全体回帰は209 passed、7 xfailed、通常失敗0件。

### 2026-09-04 M-029実施記録

- SHIコミット `4b4674c` と現行SHIを確認し、CE011のMMAP read/write例外分類をvendorへ移植した。対象はファイルシステム・mmap I/Oの `OSError`、close済み・無効状態・範囲外を含む `ValueError`、バッファ競合の `BufferError`、C++ writer内部失敗を含む `RuntimeError` であり、非対象例外はCE011へ計上しない。
- runtime接続はErrorMonitorの `ErrorMMapWriter` transaction、Visualの `GodotUIVisualizer` によるGodot UI MMAP初期化、mainのREBOOT/BOOTING status書込みに限定した。Visual初期化では `status.mmap` に加えて通常表示用の `map0.dat` / `map1.dat` も開くため、ログ文脈は個別ファイル名ではなくGodot UI MMAP全体を示す。SHIと同じくErrorMonitorとmainは診断後に次の処理へ継続し、Visual初期化は元例外を再送出してvendorのprocess起動失敗制御へ渡す。
- SHIでは3箇所がCE011ログ文面を直接所有していたが、vendorの責務分担に合わせてエラー番号、文面、logger、traceback指定を `MmapReadWriteErrorDiagnosis.log_output()` へ集約した。process/mainは操作文脈と元例外だけを渡す。
- 保護領域のmain制御フローは維持し、2つの `StatusMMAP.write_status()` を `_write_status_safe()` 呼出しへ置き換えただけに限定した。起動順、2秒待機、モード遷移、再起動条件、MMAP ABIは変更していない。
- `tests/test_mmap_read_write_error.py` で対象4例外、非対象例外、診断所有ログ、ErrorMonitorの継続、Visualの再送出、main status書込みの継続を確認した。専用テストは9 passed、既存ErrorMonitor・Visual・StatusMMAPを含む関連テストは23 passed。変更したCE011箇所、main、ErrorMonitor、テストのVS Code診断なし、`compileall` 成功。Visualには今回の変更箇所以外の既存型指摘が残る。
- `test_detect2d.py` を除く全体回帰は218 passed、7 xfailed、通常失敗0件。

### 2026-09-04 M-030実施記録

- SHIコミット `4b4674c` と現行SHIを確認し、CE012の再起動ループ検出をvendorへ移植した。`last_boots` の先頭から直近5回を評価し、最古と最新の差が600秒以内ならCE012 counterを1回加算してwarningを出力する。5回未満、および600秒を超える場合は検出しない。
- ユーザー確認により、起動履歴は `/var/lib/argus3d/uptime/uptime_state.json` を正とした。vendor側テンプレートに見られる `runtime/runtime_state.json` 候補へは変更せず、SHIの `last_boots[].boot_time_iso` 形式を読み取る。時刻はtimezone付きISO 8601を必須とする。
- 履歴ファイルの欠損、I/O失敗、JSON破損、必須キー・型・時刻形式の不正はCE012へ誤計上せず、既存DレベルFILE_IO_ERRORへパス、操作、例外詳細を渡す。正常読込時はFILE_IO_ERRORを正常状態へ戻してからCE012を評価する。
- mainでは既存の設定・logger登録後に起動履歴を1回評価する。起動順、再起動条件、モード遷移、process lifecycleは変更していない。SHI固有の広域 `DiagnosisRuntimePolicy` とmaintenance時の抑止は持ち込まず、vendorの既存Action Error基底と `is_enabled` を使用した。
- `tests/test_reboot_loop_detected.py` で履歴件数不足、600秒境界、境界超過、診断所有ログ、正常JSONのcounter加算、不正JSON構造のFILE_IO_ERROR委譲を確認した。専用テストは6 passed、FILE_IO_ERROR・共有設定・CE011を含む関連テストは24 passed。変更箇所のVS Code診断なし、`compileall` 成功。
- `test_detect2d.py` を除く全体回帰は224 passed、7 xfailed、通常失敗0件。

### 2026-09-04 M-031確認記録

- ユーザー確認により、CE003（機種情報不一致）、CE007～CE010（カメラ0～3校正データ不正）、SE036（ステータス情報未更新）はSHI担当だがSHI側も未実装である。名称、index、共通スケルトン、JSON雛形だけを根拠に推測実装せず、SHI側で仕様・runtime接続が確定するまで移植対象外とする。
- CE006と校正設定validatorは従来どおりM-005の校正サブシステムと一緒に保留する。LiDAR・IMUの実装済み診断は移植対象として継続する。

### 2026-09-04 M-032実施記録

- 現行SHIのSE040/SE041を確認し、IMU接続診断をvendorへ移植した。IMU実データ到達時だけmonotonic heartbeatを最大0.5秒間隔で更新し、空ringまたは `TimeoutError` では更新しない。共有heartbeat初期値はvendorの既存死活監視と同じ `INVALID_TIMESTAMP=-1.0` とした。
- 最初の有効heartbeatを基準値として保持した後、前回heartbeatまたは最終heartbeatから5秒以上経過した場合に接続エラーとフェイルセーフを検出する。復帰は1秒以内のheartbeat受信を5秒継続した場合で、初回基準サンプルは確認時間に含めない。
- SHIではIMU0/IMU1の診断クラスが同一実装で重複していたため、vendorの既存index・登録構造を維持し、2indexに登録済みの共通 `ImuNConnectionErrorDiagnosis` へ状態機械を実装した。parameterもvendor既存の共通 `imu_n_connection_error` を両indexで使用する。
- AppManagerはIMUごとの `is_heartbeat_enabled` が有効な場合だけ診断し、有効化時に診断履歴をclearする。SHI側で欠けていた監視有効化は、vendorのCamera/CAN/LiDARと同じくIMU startup完了時に有効、shutdown時に無効とし、起動途中や停止後を誤検出しない。
- `tests/test_imu_connection_error.py` で実データ・空ring・Timeout時のheartbeat、shutdown無効化、初回未更新除外、5秒検出、1秒以内の連続受信による復帰、AppManagerの有効IMUだけへのdispatchを確認した。専用テストは7 passed、共有設定・AppManager関連は29 passed。変更箇所のVS Code診断なし、`compileall` 成功。
- `test_detect2d.py` を除く全体回帰は231 passed、7 xfailed、通常失敗0件。

### 2026-09-04 M-033実施記録

- 現行SHIのSE001/SE002を確認し、LiDAR接続診断をvendorへ移植した。点群取得成功時だけheartbeatを最大0.5秒間隔で更新し、未取得時は更新しない。heartbeatはAppManagerの既存時刻基準と同じ `time.perf_counter()` を使用し、起動時は `INVALID_TIMESTAMP=-1.0`、停止時は監視無効とする既存Points lifecycleを維持した。
- 最初の有効heartbeatを基準値として保持した後、heartbeatの更新間隔または最終heartbeatから5秒以上経過した場合に接続エラーとフェイルセーフを検出する。復帰は1秒以内のheartbeat受信を5秒継続した場合で、センチネルからの初回遷移は確認時間に含めない。
- SHIではLiDAR0/LiDAR1の診断クラスが同一実装で重複していたため、vendorで2indexへ登録済みの共通 `LidarNConnectionErrorDiagnosis` へ状態機械とindex付きログを実装した。parameterもvendor既存の共通 `lidar_n_connection_error` を両indexで使用する。SHI固有のmaintenance抑止は持ち込んでいない。
- AppManagerはLiDARごとの `is_heartbeat_enabled` が有効な場合だけ診断し、有効化時に診断履歴をclearする。vendor既存の5秒経過で `IsDead` を立てる監視は、process生存管理の制御を変えないため残した。SE001/002の状態・ログは新しい共通診断経路が所有する。
- M-032で追加したIMUのindex付きログが参照する引数検証helperの欠落を発見し、LiDAR/IMU共通helperとして補完した。両診断のログ経路を専用テストで実行し、エラー番号とsensor indexを確認した。
- `tests/test_lidar_connection_error.py` と `tests/test_imu_connection_error.py` で初回・センチネル除外、5秒境界、連続受信による復帰、診断所有ログ、AppManagerの有効センサーだけへのdispatchを確認した。専用テストは13 passed、Points・AppManagerを含む関連テストは45 passed。変更箇所のVS Code診断なし、`compileall` 成功。
- `test_detect2d.py` を除く全体回帰は237 passed、7 xfailed、通常失敗0件。

### 2026-09-04 M-034実施記録

- OS絶対時刻が前後へ変更され得る前提で、通常運転のsensor/process heartbeatについて書込側と比較側を対にして監査した。Camera/CAN/LiDAR/LiDAR shiftは `perf_counter` で一致していたが、IMUだけ `monotonic` だったため `perf_counter` へ統一した。AppManager heartbeatと周辺監視4processは `monotonic` の入口・出口で一致し、MonitorArgus heartbeatファイルは `perf_counter` の入口・出口で一致している。
- AppManagerに残っていた旧LiDAR `IsDead` 判定の `time.time()` をheartbeatと同じ `perf_counter()` へ変更した。StatusMMAPの鮮度判定、並列・逐次process停止deadline、tegrastats子processの無出力timeoutは `monotonic()` へ変更した。AppManagerのログ継続時間も表示用 `datetime.now()` から分離し、判定には `monotonic()` を使用する。
- `time.time()` / `datetime.now()` が残る通常運転箇所はCamera/LiDARの表示日時とVisual等の処理時間ログであり、死活・接続判定には使われない。ログファイルmtimeは変化検出だけに使い、停止時間の計測自体はmonotonicである。
- M-005保留中の校正領域には、camera/lidar captureの待機deadline、calibration FIFOの長時間警告などwall clockによる経過時間計測が残る。通常運転の死活判定とは分離されているが、校正統合時にmonotonic化する。
- `tests/test_status_mmap.py` ではwall clockを未来・過去へ大幅に変更しても鮮度判定がmonotonic経過だけに従うことを確認した。`tests/test_elapsed_time_clocks.py` ではprocess停止待ちとtegrastats timeoutのmonotonic利用を確認する。
- クロック専用・接続診断テストは19 passed、AppManager・ErrorMonitor・ProcessManagerを含む関連テストは58 passed。変更箇所のVS Code診断なし、`compileall` と `git diff --check` は成功した。
- `test_detect2d.py` を除く全体回帰は240 passed、7 xfailed、通常失敗0件。

### 2026-09-04 M-035実施記録

- 現行SHIのSE008/SE009を確認し、LiDAR通信品質低下をvendorへ移植した。MID360 packet headerの `udp_cnt` 欠番、または `dot_num` が設定閾値50未満の場合に品質低下イベントとする。`udp_cnt == 0` はframe境界として連番をresetし、最初のpacketは欠番判定しない。
- MID360 deviceで最後の品質低下イベント時刻を保持し、provider、Points、`SharedLIDExcept` を経由してAppManagerへ渡す。SHIではmonotonic時刻だったが、M-034のclock契約に従い、LiDAR heartbeat・AppManager sensor診断と同じ `time.perf_counter()` へ入口と出口を統一した。OS絶対時刻の変更は判定へ影響しない。
- 直近1秒以内に品質低下イベントがある状態を低下中とし、3秒継続でSE008/SE009のエラー・フェイルセーフを検出する。品質低下イベントがない状態を5秒継続すると復帰する。SHIのLiDAR0/1重複クラスは持ち込まず、vendorで2indexへ登録済みの共通 `LidarNCommQualityDegradedDiagnosis` と共通parameterを使用する。
- AppManagerはSE001/SE002接続エラーがONの場合、下位診断であるSE008/SE009を評価しない。SE014/SE015通信品質エラーはSE008/SE009状態に依存する次段のため、今回接続していない。
- packet品質観測は現行SHIと同じMID360実機経路だけに追加した。OS0128、AIRY96/192、SHI-lib、file inputは対応するpacket情報または観測propertyを持たないため、品質低下イベントを生成しない。
- `tests/test_lidar_comm_quality_degraded.py` で連番、欠番、frame境界、点数閾値、perf_counterイベント、provider/Points伝搬、3秒検出、5秒復帰、index付きログ、SE001排他、AppManager dispatchを確認した。SE001/002・データ欠落を含む縦経路は21 passed、共有設定とPoints既存経路を含む関連テストは30 passed。変更箇所のVS Code診断なし、`compileall` と `git diff --check` は成功した。
- `test_detect2d.py` を除く全体回帰は249 passed、7 xfailed、通常失敗0件。

### 2026-09-04 M-036実施記録

- 現行SHIのSE014/SE015を確認し、LiDAR通信品質エラーをvendorへ移植した。新しいdevice観測値は追加せず、M-035で実装したSE008/SE009の `is_error` を上位診断の入力とする。
- SE008/SE009 ONが30秒継続するとSE014/SE015のエラーとフェイルセーフを検出する。途中でOFFになった場合は検出確認timerをresetする。OFFが30秒継続するとエラー復帰、60秒継続するとフェイルセーフ復帰する。
- SHIのLiDAR0/1重複クラスは持ち込まず、vendorで2indexへ登録済みの共通 `LidarNCommQualityErrorDiagnosis` と共通 `lidar_n_comm_quality_error` parameterを使用する。AppManagerは共有boolが `ctypes.c_byte` 由来のintであることを考慮して明示的にboolへ変換する。
- SE001/SE002接続エラー中は、下位SE008/SE009と同様にSE014/SE015も評価しない。経過時間はAppManagerから渡す `time.perf_counter()` の `now` だけで計測し、OS絶対時刻の変更は判定へ影響しない。
- `tests/test_lidar_comm_quality_error.py` で30秒境界、途中OFFによるtimer reset、30秒/60秒の独立復帰、引数検証、共有値のbool変換、index付きログを確認した。SE001/002・SE008/009を含む集中テストは22 passed、共有設定・AppManager・データ欠落を含む関連テストは42 passed。変更箇所のVS Code診断なし、`compileall` と `git diff --check` は成功した。
- `test_detect2d.py` を除く全体回帰は257 passed、7 xfailed、通常失敗0件。

### 2026-09-04 M-037実施記録

- 現行SHIのSE020/SE021を確認し、LiDARデータ不正をvendorへ移植した。MID360の蓄積frameについて、反射強度による除外前にXYZがすべて0の点の割合を算出し、provider、Points、`SharedLIDExcept` を経由してAppManagerへ渡す。
- 現行SHIでは原点点割合の算出が校正用 `CalibMid360PointCloudProvider` にだけあり、通常用 `Mid360PointCloudProvider` は `last_invalid_ratio` を公開していなかったため、通常運転のSE020/021には値が届かない状態だった。vendorでは両MID360 providerへ同じ割合算出を配置し、通常運転経路を成立させた。MID360以外は今回の観測対象に広げていない。
- 原点点割合が70%以上の状態を3秒継続するとエラーとフェイルセーフを検出する。70%未満で検出確認timerをresetする。復帰は30%未満を必要とし、3秒継続でエラー復帰、5秒継続でフェイルセーフ復帰する。30%ちょうどは復帰条件に含めない。
- SHIのLiDAR0/1重複クラスは持ち込まず、vendorで2indexへ登録済みの共通 `LidarNInvalidDataDiagnosis` と共通 `lidar_n_invalid_data` parameterを使用する。SE001/SE002接続エラー中はSE008/009、SE014/015と同じくSE020/021も評価しない。
- 経過時間はAppManagerから渡す `time.perf_counter()` の `now` だけで計測するため、OS絶対時刻の変更は判定へ影響しない。観測値が正常・異常になった最初の診断呼出し時刻を継続確認の起点とし、診断呼出し間を遡って補完しない。
- `tests/test_lidar_invalid_data.py` で70%検出境界、timer reset、30%復帰境界、3秒/5秒の独立復帰、引数検証、通常MID360 providerのfilter前比率、Points共有転送、SE001排他、AppManager dispatch、index付きログを確認した。専用テストは12 passed、SE001/002・SE008/009・SE014/015を含むLiDAR関連テストは34 passed。変更箇所のVS Code診断なし。
- `test_detect2d.py` を除く全体回帰は269 passed、7 xfailed、通常失敗0件。

### 2026-09-04 M-038検討記録

- `docs/error_list.txt` ではCE006「センサ校正データ不正」はSHI担当である。vendorにはindex、`SensorCalibDataInvalidParameters`、`SensorCalibDataInvalidDiagnosis`、`error_config.json`の雛形があるが、診断は空実装でruntime接続されていない。
- 現行SHIはLiDAR校正CSVについて、存在、読込、4x4形状、有限値を起動時の`load_config()`で検証する。異常時はCE006 counterとログを記録するが、CE005の設定再読込へは流さず起動を継続する。通常運転で実際に校正行列を読む所有箇所は`interface/pcd_calib.py`である。
- 現行SHIは上記に加え、理想位置の参照行列との差分として並進、回転、XY評価グリッド最大変位を検証し、3D-3D校正生成直後にも同じvalidatorを使用する。ただしCE006専用テストは存在しない。
- SHIの起動時validatorは`zip(targets, references)`で対象と参照を対応付ける。`check_lidar2lidar=True`ではLiDAR間行列を先頭のLiDAR-機体参照へ誤対応させ、対象数と参照数が異なる場合は末尾対象を未検査にする可能性がある。この実装をそのまま採用しない。
- 次の独立マージ候補は、通常運転が消費する`CalibrationConf.BothLidars`と`Lidar_calib_files`に対する存在、CSV読込、4x4形状、有限値の基本健全性だけとする。診断クラスがparameter、counter、ログを所有し、`load_config()`はvendorのCE005再試行制御を維持したままCE006を記録する。
- 参照行列との差分判定、閾値、3D-3D校正生成直後の判定は校正アルゴリズムと参照データ対応に依存するため、M-005の採用方針決定まで保留する。基本健全性マージでは`enable_reference_diff_check`等を追加しない。
- 基本健全性を実装する場合の最小受入テストは、正常4x4、欠損、CSV解析不能、不正形状、NaN/inf、無効化、複数対象の全件検査、CE006 index・counter・ログ、CE005へ誤分類せず`load_config()`が継続することとする。

### 2026-09-04 M-038実施記録

- CE006のうち通常運転が消費するLiDAR校正CSVの基本健全性だけをvendorへ移植した。`CalibrationConf.BothLidars`と`Lidar_calib_files`を対象とし、存在・CSV読込可否、4x4形状、有限値を検査する。対象と参照を`zip`しないため、設定された全対象を途中打切りせず検査する。
- 純粋なファイル検証は`diagnosis/lidar_calib_validator.py`へ置き、`SensorCalibDataInvalidDiagnosis`が有効化、parameter、CE006 counter、先頭issueと総issue数を含むログを所有する。複数issueがあっても一回の起動時検査につきcounterは一回だけ増加する。
- `load_config()`はvendorの設定読込とCE005再試行制御を維持し、`SharedAppConfig`読込後にCE006を一回検査する。校正CSV異常はCE006として記録するがCE005へ渡さず、`SharedAppConfigCalibration`読込と起動を継続する。
- 設定には`check_lidar2lidar`、`check_lidar2crane`、`enforce_shape_4x4`、`finite_value_only`だけを追加した。SHIの参照差分parameter、並進・回転・XY変位判定、3D-3D校正生成直後の検証は追加しておらず、M-005の採用方針決定まで保留する。
- `tests/test_sensor_calib_data_invalid.py`と`tests/test_config_file_missing.py`で正常4x4、全対象欠損、解析不能、不正形状、NaN、無効化、全件検査、counter、CE006ログ、CE005非計上、起動継続を確認した。CE006専用・起動統合は26 passed、共有設定は3 passed。新規箇所のVS Code診断なし、残る`action_errors.py`の診断は既存CE012箇所だけである。
- `test_detect2d.py`を除く全体回帰は275 passed、7 xfailed、通常失敗0件。

### 2026-09-04 M-039実施記録

- 現行SHIの`is_suppressed_in_maintenance`参照箇所を確認し、CE001 LiDAR位置ずれ、CE002 要センサ校正、CE012 再起動ループ、SE001/SE002 LiDAR接続、SE007 CAN接続、SE026 旋回角情報、SE035 Monitor未応答、SE037 周辺監視module未応答、SE039 AppManager未応答へ限定して移植した。SE039は重要度BだがSHIの明示対象であるため含めた。
- `DiagnosisRuntimePolicy`がmultiprocessing共有値として`in_factory`を保持し、`SharedErrors`が単一instanceを所有して対象診断へ明示注入する。対象外診断へ自動適用せず、重要度A全体を一律抑止しない。
- 対象診断はメンテナンスモード中の新規検出を`False`とし、counter、error、failsafe、idleを更新しない。メンテナンスモードへの切替時に検出済み状態を強制clearする処理は追加せず、SHIと同じく既存状態は通常の復帰条件へ委ねる。
- 起動時は`load_config()`が`General.in_factory`を共有policyへ反映し、実行中の設定再読込時はAppManagerの`_config_load()`が同じ共有値を更新する。診断instanceを再生成せず切替が反映される。
- `tests/test_maintenance_mode_error_suppression.py`で対象10診断instanceの抑制、counter・状態非更新、通常モードへの動的切替、対象外への非注入、AppManager再読込を確認し12 passed。`tests/test_config_file_missing.py`で起動時同期を含め21 passed。変更箇所の`compileall`は成功し、新規policy、基底、状態診断、共有登録、起動、テストにVS Code診断はない。
- `test_detect2d.py`を除く全体回帰は287 passed、7 xfailed、通常失敗0件。

### 2026-09-04 M-040実施記録

- SHIのFile watch差分を確認し、エディタのatomic saveによる一時renameや書込み途中を設定ファイル破損・欠損として誤確定しない短時間リトライをvendorへ移植した。
- `DebouncedEventHandler.process_event()`だけを対象とし、`SharedAppConfig.write()`を最大3回、0.2秒間隔で再試行する。途中で成功した場合はCE005診断とエラーログを行わず、3回すべて失敗した場合だけ既存の`ConfigFileMissingDiagnosis.excepts_diagnosis()`へ最後の例外を渡す。
- 起動時`load_config()`のリトライは別の制御境界である。vendorの復帰優先方針に従って無限再試行を維持し、SHIの有限リトライ段階は今回移植していない。機体設定・校正設定のFile watch拡張も対象外とした。
- `tests/test_file_watch_reload_retry.py`で2回の一時失敗後の成功、診断・ログ非発生、0.2秒間隔、debounceイベント解放、および3回失敗後だけのCE005 dispatchを確認し2 passed。

### 2026-09-04 M-041実施記録

- 校正パラメータや入力ファイルを少しずつ変更し、外部スクリプトから無人で反復起動する校正評価用途をSHIから移植した。適用条件は`app_config.DEFAULT.File_Input`が有効かつ現在または遷移先が`CALIB`の場合だけである。
- 自動校正評価では`ProcessActivator.disable()`と`CompositeClosable.close()`だけを行い、新しい無効状態のActivatorと空のclosablesを返す。呼出し直後の既存`ProcessManager.join()`は維持し、子プロセスの終了を待ってから次へ進む。
- この軽量経路では量産向け`graceful_stop_all()`のterminate/killと`PROCESS_FORCED_TERMINATION`診断を実行しない。実機入力のCALIBとSCRUTでは従来の`stop_calib_pipeline()`または`stop_scrut_pipeline()`を維持する。
- 適用箇所は自動校正パイプラインの起動失敗、SCRUTからファイル入力CALIBへの遷移、ファイル入力CALIBからSCRUTへの遷移である。また、CALIB処理完了時は共有`CalMatGen_ex.IsFinished`を確認してsystem loopを抜け、既存の`ProcessManager.join()`へ進む。その他の終了・再起動制御は変更していない。
- `__main__.py`には、校正条件を変えながら外部スクリプトで無人反復する用途、量産向け`graceful_stop_all()`を避ける理由、軽量停止と`join()`の責務分担、`IsFinished`が実機CALIBと共通の完了通知であることを設計コメントとして残した。終了処理を変更する際は、この用途説明と量産経路の分離を維持する。
- `tests/test_automated_calibration_shutdown.py`でFile Inputとモードの全4組合せ、および軽量停止がActivator停止・通信資源解放だけを行うことを確認し5 passed。量産向け停止基盤を含む集中回帰は10 passed、`test_detect2d.py`を除く全体回帰は294 passed、7 xfailed、通常失敗0件。`compileall`とCRLFを考慮したdiff checkも成功した。

### 2026-09-04 M-042実施記録

- `argus_bootfig_jetson.sh`実行時、Mainが最初の`REBOOT_CODE`ログ出力で`LogTimeReversal.param`未初期化の`AttributeError`により終了する事象を確認した。CE006の校正CSV欠損ログは同時に出ていたが、起動終了の直接原因ではない。
- `LogTimeReversal`と`LogCompressionFailure`はAppManagerの設定読込でupdateされる一方、logger callbackはAppManager起動前に登録される。既存handlerが前回ログ時刻を保持していると最初のログからcallbackが発火するため、`load_err_config()`で両診断を先に初期化するよう起動順を修正した。
- `tests/test_log_time_reversal.py`へcallback発火前の初期化を確認する回帰テストを追加し、ログ診断の集中テストは12 passed。修正後に`argus_bootfig_jetson.sh`を実行し、`INIT`、`REBOOT`、`BOOTING`、`RUNNING`への遷移と13個の処理プロセスおよびUIの起動を確認した。`test_detect2d.py`を除く全体回帰は295 passed、7 xfailed、通常失敗0件。CRLFを考慮したdiff checkも成功した。

### 2026-09-06 M-043実施記録

- 現行SHIで削除済みの補助情報MMAPと参照用CLIをvendorからも削除した。SHIでは`info_mmap.py`が`9432a4f`、`argus_synchro_query.py`が`a487f5f`で削除され、現行ツリーに関連参照がないことを確認した。
- `argus_synchro/SystemMonitor/info_mmap.py`と`argus_synchro/SystemMonitor/argus_synchro_query.py`を削除し、`__main__.py`から`ArgusInfoMMAP`のimportと`argus_info.mmap`初期化を除去した。
- プロセス状態通知に使用する`StatusMMAP`、エラー共有MMAP、Godot UI向けMMAPは別機能であり変更していない。
- main周辺の集中回帰は16 passed、`test_detect2d.py`を除く全体回帰は296 passed、7 xfailed、通常失敗0件。変更箇所の`compileall`とCRLFを考慮したdiff checkも成功した。

### 2026-09-06 M-044実施記録

- SHI `a487f5f`の`MonitorArgus.json`読込エラー診断を、vendorの独立MonitorArgusプロセスへ移植した。MonitorArgus内でローカル`FileIoError`を生成し、`error_config.json`から設定を読み込む。診断設定自体を読めない場合は既定設定を使用する。
- `MonitorArgus.json`の欠損、I/O・文字コード・JSON解析エラー、ルート型不正、`engine`または`appimage`必須キー欠損をDレベル`FILE_IO_ERROR`へパス、操作、例外詳細付きで渡す。従来どおりログ出力後に終了コード1で終了し、起動制御は変更しない。
- `tests/test_monitor_argus_file_io_error.py`で欠損、JSON破損、ルート型不正、必須キー欠損、正常読込を確認し5 passed。

### 2026-09-06 M-045実施記録

- MonitorArgus heartbeatのatomic writeを`_write_heartbeat()`へ分離し、一時ファイル名を作成前に`None`で初期化した。`NamedTemporaryFile()`が作成前に失敗しても未束縛変数を参照せず、元の例外を維持する。
- `os.replace()`失敗時は作成済み一時ファイルを削除し、掃除対象の有無にかかわらず元例外を再送出する。正常時の同一ディレクトリ一時ファイルと`os.replace()`による原子的更新は維持した。
- `tests/test_monitor_argus_heartbeat.py`で一時ファイル作成前失敗、正常置換、置換失敗時の一時ファイル削除を確認し3 passed。M-044、M-045、既存StatusMMAPの集中回帰は12 passed。
- `test_detect2d.py`を除く全体回帰は304 passed、7 xfailed、通常失敗0件。変更箇所のPylance診断なし、`compileall`とCRLFを考慮したdiff checkも成功した。

## 10. 次のCopilotへの開始指示

次回は、いきなり全体差分を再探索しない。次の順で開始する。

1. 本書と関連文書を読む
2. 両リポジトリのHEADと `git status --short` を確認する
3. 統合台帳から未処理項目を1件選び、そのvendor側定義、SHI側定義、隣接テストだけを読む
4. M-005校正はユーザー側アルゴリズム変更の採用方針を決めるまで着手しない
5. 最小の単体テストまたは基盤移植を行う
6. 狭いテストを直ちに実行する
7. 本書の台帳と確認結果を更新する
8. CANと校正の統合後、両リポジトリの残差分を機能単位で再監査する。過去のレビュー台帳で対応済みとされた項目も、現行vendorコードへの実装有無を検索またはテストで再確認し、未移植、vendor維持、意図的な不採用のいずれかを記録する

新しい判断が既存記録と矛盾した場合は、古い記録を黙って残さず、理由と日付を添えて本書を更新する。
