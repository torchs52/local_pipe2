# Vendor/SHI 統合作業 引継ぎ

最終更新: 2026-09-08

この文書は、別PCまたは別のCopilotチャットで統合作業を再開するための入口である。
作業を始める前に本書を読み、判断・実装・検証が進んだら同じ作業内で更新すること。

関連文書:

- [error_list.txt](error_list.txt): NSW/vendor と SHI のエラー実装分担
- [error-handling-review-ledger.md](error-handling-review-ledger.md): 過去のエラー処理レビュー記録
- [non-calibration-merge-candidates.md](non-calibration-merge-candidates.md): 校正関連以外の未統合候補と優先順位
- [calibration-merge-plan.md](calibration-merge-plan.md): 校正サブシステムの責務分界、統合順、検証ゲート
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
| M-005 | 校正サブシステム統合方針 | 現行SHI / vendor / ユーザー要件 | manual-port | in-review | `docs/calibration-merge-plan.md` | vendor lifecycleを維持し、SHIアルゴリズムを責務単位で移植する。実装はM-058～M-067へ分割 |
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
| M-016 | CANサブシステムの混合統合 | SHI `47ada36`, `9febde3`, `079b822`, `a487f5f` ほか | manual-port | verified | CAN sensor/file/config/diagnosis/tests | vendorの入力I/OとNSW所掌診断を維持し、共通decoder、機種別map、SHI所掌FILE_IO_ERRORを移植。候補設定はmap内コメントで保持 |
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
| M-031 | SHI担当だが未実装のCE003・CE007～CE010・SE036 | ユーザー確認 / 当時のSHI | decision-needed | verified | M-070へCE007～CE010を移管 | 後日のSHI再監査でCE007～CE010の基本検証実装を確認したためM-070で導入。CE003・SE036は引き続きdeferred |
| M-032 | SE040・SE041 IMU接続エラー | 現行SHI / `docs/error_list.txt` | manual-port | verified | state diagnosis/shared heartbeat/IMU/AppManager/tests | 実データheartbeatを5秒監視し、1秒以内の連続受信を5秒確認して復帰する |
| M-033 | SE001・SE002 LiDAR接続エラー | 現行SHI / `docs/error_list.txt` | manual-port | verified | state diagnosis/Points/AppManager/tests | 実点群heartbeatを5秒監視し、1秒以内の連続受信を5秒確認して復帰する |
| M-034 | 死活・経過時間クロック監査 | vendor通常運転経路 | vendor-keep | verified | sensor/process heartbeat/StatusMMAP/停止deadline/tests | 絶対時刻依存を除去し、書込側と比較側のclock APIを統一する |
| M-035 | SE008・SE009 LiDAR通信品質低下 | 現行SHI / `docs/error_list.txt` | manual-port | verified | MID360 device/provider/shared/Points/AppManager/state diagnosis/tests | packet連番欠落・点数低下イベントの3秒継続で検出し、正常5秒で復帰する |
| M-036 | SE014・SE015 LiDAR通信品質エラー | 現行SHI / `docs/error_list.txt` | manual-port | verified | state diagnosis/AppManager/tests | SE008/009 ONを30秒確認して検出し、OFFを30秒/60秒確認してerror/failsafe復帰する |
| M-037 | SE020・SE021 LiDARデータ不正 | 現行SHI / `docs/error_list.txt` | manual-port | verified | MID360 provider/shared/Points/AppManager/state diagnosis/tests | filter前のXYZ原点点割合70%以上を3秒確認して検出し、30%未満を3秒/5秒確認してerror/failsafe復帰する |
| M-038 | CE006 センサ校正データ不正（基本健全性） | 現行SHI / `docs/error_list.txt` | manual-port | verified | action diagnosis/validator/load_config/tests | CSVの存在・読込・4x4形状・有限値を起動時に検査。参照差分・校正生成結果判定はM-069で追加 |
| M-039 | メンテナンスモード中の指定エラー抑制 | 現行SHI `in_factory` / ユーザー要件 | manual-port | verified | runtime policy/対象診断/AppManager・起動経路/tests | SHI指定のCE001/002/012、SE001/002/007/026/035/037/039だけを抑制し、重要度A全体へは適用しない |
| M-040 | File watch設定再読込の一時失敗リトライ | 現行SHI `file_watch.py` / ユーザー要件 | manual-port | verified | file watch/CE005/tests | atomic save中の一時欠損・書込み途中を3回、0.2秒間隔で再試行し、全失敗時だけCE005へ渡す。起動時の無限再試行は維持する |
| M-041 | 自動校正ファイル入力の軽量終了制御 | 現行SHI `__main__.py` / ユーザー要件 | manual-port | verified | main/ProcessActivator/closables/tests | CALIBかつFile Inputの反復評価だけActivator停止と通信資源解放を行い、実機CALIBとSCRUTは量産向け停止・強制終了診断を維持する |
| M-042 | 起動時ログ診断parameter初期化 | 実機起動ログ / vendor起動順 | vendor-fix | verified | main/log diagnosis/tests | logger callback登録前にログ圧縮・時刻逆転診断を初期化し、起動直後のAttributeErrorを防ぐ |
| M-046 | エラーMMAP更新停止 | 実機起動ログ / SHI parameter定義 | manual-port | verified | error config/SE039/SE042/tests | 欠落していた診断閾値を復元し、ErrorMonitorのAttributeError終了とAppManagerの反復例外を防ぐ |
| M-047 | TensorRT cache・入力名・provider選択の堅牢化 | SHI `ecbc79f` / 現行 `detect2d.py` | manual-port | verified | `detect2d.py`, tests | モデル固有入力名、モデル/config別cache、provider fallbackを移植。Jetson Orinでbatch 3 engine新規生成、cache再利用、CUDA Graph・I/O Binding推論を確認 |
| M-048 | 負荷低減中の蓄積deque上限保証 | SHI現行 `AccumulatePoints.py` | manual-port | verified | `AccumulatePoints.py`, tests | append後にもmode別上限へtrimし、通常/負荷低減とも最新frameを保持して返却dequeの実効上限を保証 |
| M-049 | 点群メッセージ上限20,000→40,000 | SHI `2283a0a` | manual-port | verified | Python/C++ PcdData、detect3d、Visual | 認識精度確保のためPython/C++容量を40,000へ統一。40,000点の共有slot往復、一括build、extension import成功 |
| M-050 | MID360点群復号のNumPyベクトル化 | SHI `5265abb` | manual-port | verified | `device/lidar/mid360_points.py`, tests | structured dtypeと`np.frombuffer()`で96点を一括復号し、M-035の`perf_counter()`と公開property契約を維持。短packetは明示拒否 |
| M-051 | 新YOLOモデルの機種別既定化 | SHI `9d5c72f` | decision-needed | pending | 機種別settings、性能試験 | `settings.ini`と`calib_settings.ini`は新モデルへ変更し、通常AppImage起動でTensorRT cache再利用まで確認済み。残件は機種別settingsへの横展開と精度・FPS・GPU memoryの製品承認 |
| M-052 | SCX3500可視化CAD資産 | SHI `6699794` | shi-adopt | verified | `config/crane3d/visualize/SCX3500-3/` | 現行manifestでは未参照だが今後の利用に備え、SHIの上部・下部OBJ/MTL 4ファイルを原本どおり取り込み |
| M-053 | 負荷低減閾値・切替ログ | SHI `2283a0a` | manual-port | verified | reduced load/PointsRefine/tests | 40,000点契約に対して開始40%・復帰30%を採用。現在modeは毎frame、deque詳細はmode変化時だけ出力し、境界と5frame継続を検証 |
| M-054 | MMAP二重バッファ切替時の次バッファ予約 | SHI `d9ba78b`, `655aaaf` | manual-port | verified | lib `clsmmap/ClsMMap.cpp`、Godot reader、tests | index切替直後に次mapを`IsWriting=1`へ予約。実MMAP protocol試験と実AppImage reader並行試験で2面の交互利用を確認 |
| M-055 | UI MMAP octotree点数の確定書込み | SHI `d9ba78b` | manual-port | verified | lib `ui_interface.cpp`, tests | 合計点数の書込みをentity loop外へ移し、全entity空時も0を確定。非空frame後の空frameを実MMAPから読戻して1→0を確認 |
| M-056 | UI MMAP詳細ログのdebug化 | SHI `d9ba78b` | manual-port | verified | lib `ui_interface.cpp`, performance tests | フレーム単位のアドレス・座標・画像・点群詳細をdebugへ変更。実機runで対象詳細INFO 0件、サマリINFO 807件を確認 |
| M-057 | legacy setupのpackage/extension名整合 | SHI `7f34907` | manual-port | verified | lib `setup.py`, package tests | distribution/extension名を`argus_synchro_lib`へ統一。wheel生成・installとextension import、metadata `2026.8.25`を確認 |
| M-058 | 校正settings/MMAP/FIFO契約固定 | vendor現行 / Godot UI契約 | vendor-keep | verified | config schema, facade, FIFO, contract tests | settings 8項目、mode値、FIFO 4要素順、MMAP header、共通field書込順を固定。関連回帰20件pass |
| M-059 | 2D-3D校正診断UI結果・設定schema | SHI `7f58643`, `fc7f75e` | manual-port | verified | diagnosis, app config, facade, tests | UI enum・reason code変換、設定schema、facade validationを移植し、新producerとの同時切替を確認 |
| M-060 | 2D-3D校正診断アルゴリズム | SHI `d60c83d` ほか / 現行SHI | manual-port | verified | `calibcheck2d3d`, `SceneDesc`, `YOLOadapter`, tracking, tests | scene/tracking/score診断とcamera slotを保持するactive YOLO adapterをvendor lifecycleへ接続し、three-way確認済み |
| M-061 | 通常2D-3D校正アルゴリズム | 現行SHI | manual-port | verified | calibration2d3d, progress/correspondence/tracking, tests | FILE_IO、file-end一回完了、100点gate、進捗再計算、camera別center-Z補正、UI/AI診断を接続し、three-way確認済み |
| M-062 | 3D-3D校正アルゴリズム・エラー完了 | SHI `b64f6f9` / 現行SHI | manual-port | verified | calibration3d3d, lidar calibration, tests | 生成行列のCE006検証、UI error/status/yaw、matrix/profile/angle FILE_IOを接続。高度な参照差分はM-069で追加 |
| M-063 | 校正capture・厳密同期 | vendor / 現行SHI | vendor-keep | verified | calib FIFO/data capture, tests | `MessageFlow`は単一consumerのためCALIB/SCRUT専用flowを維持。同期成立frameだけをcamera/LiDAR/CAN/ref_t順で渡す契約を確認 |
| M-064 | 校正wait・facade・MMAP接続 | vendor / SHI `fc7f75e`, `d9edbc0` | manual-port | verified | wait app, facade, mmap contract tests | enum・校正要否status直書きとSHIのwait dummy設定・送信を移植し、Vendor lifecycleとMMAP ABIを維持してthree-way確認済み |
| M-065 | 校正エラー処理接続 | `docs/error_list.txt` / 現行SHI | manual-port | verified | calibration process/modules/diagnosis/tests | FILE_IO D有効化とstartup/runtime fallback、3D-3D UI error状態、profiler防御、失敗後post抑止をVendor lifecycleへ接続しthree-way確認済み |
| M-066 | 校正設定validation・機種別設定 | SHI現行 calibration validator / machine profile | manual-port | verified | calibration config validation/machine profile/file watch/tests | SHI validatorと機種別校正設定を移植。CALIB中も`settings.ini`監視を常時維持し、機種別校正INI監視を追加。関連14件pass |
| M-067 | 校正三者差分ビューア導入 | `local_pipe` `origin/vendor-20260817-integration:scripts/three_way_review.py` | manual-port | verified | `scripts/three_way_review.py`, tests | vendor/SHIのrepoとrefを個別指定し、統合working treeと比較する。別repo・片側限定ファイルの専用テスト2件pass |
| M-068 | Vendor/SHI最終残差監査 | SHI `2283a0a` / 統合working tree | vendor-keep | verified | source/config差分、SHI非merge commit、統合台帳 | SHI限定14ファイルを全件分類。実行経路に未分類の機能差分なし。M-051の製品評価とM-054のGodot並行試験だけを残す |
| M-069 | CE006 理想行列差分判定 | 現行SHI / ユーザー要件 | manual-port | verified | calibration validator/action diagnosis/startup/3D-3D/tests | 並進・回転・円形grid上の最大XY変位を理想行列と比較。対象・参照件数を明示検証し、SHIの`zip()`による切捨ては不採用 |
| M-070 | CE007～CE010 カメラ校正データ診断枠 | 現行SHI / ユーザー要件 | manual-port | verified | camera validator/action diagnosis/startup/error config/tests | fisheye JSONと外部行列の構造・形状・有限値を共通診断化。理想差分parameterはstub。camera 3はpath契約未定義をCE010として明示発報 |
| M-071 | 校正MMAP次バッファ予約 | M-054 / ユーザー要件 | manual-port | verified | calibration facade/contract tests | 校正modeでもindex切替直後に次mapを`IsWriting=1`へ予約し、通常UI MMAPと同じ競合窓対策を適用 |
| M-072 | 負荷低減閾値ratio設定化 | ユーザー要件 / M-053 | manual-port | verified | AppConfig/settings/file watch/reduced load/tests | 40,000点capacityを維持し、開始0.4・復帰0.3を共通settingsへ追加。起動時と設定再読込成功時に16,000/12,000へ反映 |
| M-073 | エラー構造・全JSON schema監査 | 現行Vendor/SHI | vendor-keep | verified | shared errors/error config/JSON/tests | enum/tuple整合を固定し、ErrorConfig全62キー・全dataclass fieldをJSONへ明示。LiDAR/IMUのSHI個別parameter対Vendor N共有は要判断差分として維持 |

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

### 2026-09-06 M-016再開調査

- vendorはCAN全体を一つの入力実装へ統合しているわけではない。`Can`はUDP実機入力、`CanFile`はCSV入力、`ShiLibCan`はSHIライブラリ入力として分離し、`CanDataProviderProcess`が設定に応じて選択する。`Can`と`CanFile`が同じ`can_receiver.py`に置かれているのはファイル配置上の集約であり、I/O責務まで共通化した設計ではない。
- SHI `47ada36`は上記の入力経路分離を維持し、CAN payloadから物理値への変換だけを`can_decoders.py`へ分離した。実機入力は受信CAN ID、ファイル入力は設定した`PGN_Old`/`PGN_New`を使って同じ`CanHandler`とdecoder registryを呼ぶ。この層だけの共通化は、ファイル入力と実機入力の差を無理に隠さないため採用候補とする。
- CAN IDとdecoder選択は`can_id_map.csv`、使用するmapは`CAN.can_id_map_file`で既に設定化されている。機種別settingsは`MachineProfileHandler`により基本`settings.ini`の既存キーを上書きできるため、機種固有のmapファイルを用意し、各機種の`[CAN] can_id_map_file`で選ぶ構成が可能である。CAN IDをproviderやprocessへ追加で埋め込む方式は避ける。
- ただし現行の機種別settingsには`[CAN]`上書きがなく、vendor/SHIとも全機種が共通`can_id_map.csv`を参照している。SHIの200t用CAN ID `18F0E211`と`handle_angle_can_scx2000`はコードに存在するが、現行mapでは`notused)`付きで無効化されている。200t用変換は開始bit 48の16bit値を0.1度単位として読み、符号反転・0～360度正規化を行うが、実フレームと期待角度による確認が必要である。
- 旧CANのoffsetは、現行vendorで実機入力が`current_degree - yaw_offset_deg`、ファイル入力が`current_degree + yaw_offset_deg`である。SHIの共通decoderは両経路を減算へ統一するため、移植すると既存ファイル入力結果が変わる。正しい符号規約を実機仕様または既知データで確定するまで、この部分は共通化しない。
- 最初の実装単位は、入力クラスを統合せず、既存旧CAN・新CAN・レバーのdecoder registry、CAN ID正規化、map検証と単体テストに限定する案とする。200t decoderは数式をテスト可能な独立関数として保持できるが、機種別mapでの有効化は仕様確認後に別単位で行う。

### 2026-09-06 M-016 decoder共通化

- ユーザー確認により、旧CANのoffset規約は実機・ファイル入力とも`current_degree + yaw_offset_deg`へ統一した。新CANは既存どおり減算とする。
- `device/can/can_decoders.py`へ旧CAN、新CAN、レバー、200t/SCX2000の変換関数と`DECODER_REGISTRY`を追加した。`CanHandler`はCSVに書かれた関数名を`getattr()`で解決せず、registryに登録済みの関数だけを受理する。CAN IDは前後空白、大文字小文字、先頭`0x`を正規化する。
- `CanFile`は独自の変換式を廃止し、mapで選択された`yaw_angle`のCAN IDと正規化済みpayloadを`CanHandler.dispatch()`へ渡す。UDP実機、CSV、SHI-libという入力クラスの分離と、vendorのprocess/provider切替は変更していない。
- 検討途中で追加した`PGN_Old`/`PGN_New`は最終設計では不要と判断し、`CANConf`と基本settings群から削除した。角度CAN IDを別設定へ重複保持せず、単一の`can_id_map.csv`を正とする。
- 200t/SCX2000 decoderはSHI候補式を独立実装し、byte 6–7のlittle endian 16bit値を0.1度単位として変換後、方向反転して0～360度へ正規化する単体テストを追加した。ただし現行`can_id_map.csv`には追加せず、製品経路では無効のままとした。実フレームと期待角度、offset適用順を確認してから機種別mapで有効化する。
- `can_id_map.csv`はヘッダー付き`crane_model,can_id,signal_type,decoder`の4列形式とした。`*`は全機種共通、機種固有行は同じCAN IDまたは同じsignal typeの共通行を置換する。これにより同じCAN IDでも機種ごとに通常・反転decoderを選択でき、別CAN IDへの角度信号切替も可能である。
- `CanHandler`生成時に既存`AppConfig.UI_IF.crane_model`を明示的に渡す。Providerは固定CAN IDではなく`DecodedCanMessage.signal_type`で値を更新する。UDP、CSV、SHI-libの全入力経路が同じmapとdecoder registryを使用する。
- 起動時に必須列、対象機種行、CAN ID重複、decoder名、signal type、`yaw_angle`がちょうど1件であることを検証する。現在対応するsignal typeは`yaw_angle`と`lever_pressure`であり、新しいCAN情報を追加するときはmap、decoder、Provider/Messageの型と利用先を同時に拡張する。
- 現行mapはSHI側のコメントアウトされていない設定を正として、`SCX900-3`にnew CAN角度`18FFD1D1`とlever`18FC4401`を明示している。旧CAN、反転new CAN、200t decoderは先頭`#`の候補行として残し、CSV readerの`comment="#"`で実行対象外にする。候補を有効化するときは`#`を外して対象機種を指定し、同じ機種の`yaw_angle`有効行を1件だけにする。
- 専用テスト`tests/test_can_decoders.py`は18件成功。全体回帰は`322 passed, 7 xfailed`（`tests/test_detect2d.py`除外）だった。
- `docs/error_list.txt`の分担表では、CAN heartbeat/通信品質/不正データ/yaw angle診断（SE007、SE026～SE029）はNSW所掌である。これらはSHI差分の移植対象とせず、vendor実装を正として維持する。200tは有効化待ちの残件ではなく、map内のコメント候補設定として保持する。

### 2026-09-06 M-016 File I/O診断

- `docs/error_list.txt`でSHI所掌となっているDレベル`FILE_IO_ERROR`だけをCANへ追加した。SHI `a487f5f`のCAN差分を確認し、`_err_config_load()`で診断設定を更新する。
- file-input CAN CSVの起動時読込、通常ループのファイル切替、校正時のファイル切替を`CanDataProviderProcess`の共通診断境界へ揃えた。読込・デコードに関係する`OSError`、`UnicodeError`、`ValueError`、`TypeError`、`KeyError`ではpath/operation/detailを記録して元例外を再送出し、成功時は復帰判定を更新する。
- `can_id_map_file`はファイル入力データではなく必須設定ファイルとして扱う。mapの読込・列構造・機種行・CAN ID重複・decoder・signal type検証の失敗は、実際のmap pathと元例外を保持する`CanIdMapError`へ変換し、CSV/UDP/SHI-libの全入力方式でCE005へ記録して再送出する。file-input CAN CSVの`FILE_IO_ERROR`へ誤って入力CSV path付きで計上しない。
- CAN module error、heartbeat、通信品質、不正データ、yaw angle診断はNSW所掌のvendor実装を変更していない。SHI `a487f5f`のmodule例外ログ変更も、vendor側に既存の診断・ログ処理があるため追加移植しない。
- 専用テスト`tests/test_can_file_io_error.py`で起動時と再読込時の検知、元例外再送出、成功時復帰、map errorのCE005分類と`FILE_IO_ERROR`非計上を確認する。`tests/test_can_decoders.py`ではmap pathと元例外の保持を確認する。

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
- 純粋なファイル検証は、LiDARとcameraのvalidatorを統一的に扱う`diagnosis/calib_matrix_validator.py`へ置く。現時点ではLiDAR validatorを実装し、camera validatorはスタブ段階のため後続移植とする。`SensorCalibDataInvalidDiagnosis`が有効化、parameter、CE006 counter、先頭issueと総issue数を含むログを所有し、複数issueがあっても一回の起動時検査につきcounterは一回だけ増加する。
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

### 2026-09-06 M-046実施記録

- 実機ログと`/dev/shm`のMMAP内時刻を照合した。周辺監視`map0.dat`/`map1.dat`は05:16:41まで更新された一方、エラー処理`err0.dat`/`err1.dat`は05:15:21で停止しており、UIの60秒未更新検出はエラー処理MMAP側と判断した。
- 同時刻に`ApplicationManagerNotRespondingParameters.error_threshold_sec`欠落によりErrorMonitorが`AttributeError`で終了した。AppManager側でも`LogOutputStoppedParameters.error_threshold_sec`欠落が反復発生していた。
- SHI側に存在するSE039の`error_threshold_sec=5.0`と、SE042の検出5秒・error/failsafe復帰確認5秒・復帰受信間隔1秒を`ErrorConfig`のparameter dataclassへ復元した。vendor既存のMMAP writer、process制御、一覧外の例外処理は変更していない。
- 実際の`ErrorConfig()`および`error_config.json`読込経路でparameterが利用できる回帰テストを追加した。SE039・SE042・MMAP診断の集中テストは30 passed。

### 2026-09-06 M-005検討記録

- 校正をprocess lifecycle、同期入力、通常2D-3D、3D-3D、2D-3D診断、wait、MMAP/UI、エラー、設定schemaへ分解した。起動・終了・再起動・モード遷移はvendor、数理と判定ロジックはSHIを基準にする。
- 2D-3D診断はSHI約3,009行、vendor約703行で、SHI側だけに`SceneDesc.py`、`YOLOadapter.py`、校正要否結果診断がある。単一ファイル置換ではなくM-059、M-060として契約、設定、scene、tracking、score、状態遷移を段階移植する。
- `ctrl/`配下は、処理の意味と外部契約が同じならSHIのクラス分割、処理順、命名、データ表現を優先する。vendor境界への接続、明確な冗長性、correctness・型・性能上の理由がある箇所だけ変更し、その理由とテストを記録する。
- `operation_mode`と`CalibMode`、同期済み`FIFOData`、校正MMAPのfield順・幅・数値を共有契約として先に固定する。SHIのUI向け校正status/errorは重要度A～Dの製品エラーと分離する。
- CE006の基本健全性は既存実装を維持する。参照差分と生成直後検証は3D-3D単位、CE007～CE010は完成仕様確認後、CE014はvendor所有として扱う。最外周でI/O例外を一律分類せず、対象を知る所有境界で固有CEを優先する。
- 詳細を`docs/calibration-merge-plan.md`へ記録し、実装項目をM-058～M-067へ分割した。最初のアルゴリズム実装は行わず、settings/MMAP/FIFO契約テストから開始する。
- M-060～M-062の完了時はvendorとSHIの基準commit、および統合版のHEADとdirty状態を固定する。`scripts/three_way_review.py`へvendor/SHIのrepoとrefを個別指定して変更ファイルの三者差分を確認する。三者レビュー完了前に`verified`へしない。

### 2026-09-06 M-067実施記録

- `local_pipe`をfetchし、remote branch `origin/vendor-20260817-integration`の`scripts/three_way_review.py`を統合先へ移植した。元版の行整列、差分色分け、同期スクロール、差分移動、文字サイズ、折返しを維持した。
- 今回の配置に合わせ、vendorとSHIのrepo path・Git refを個別指定し、統合版はworking treeを直接読むCLIへ変更した。列名は`Vendor`、`SHI`、`Integration`とし、HTMLへ各repo、ref、解決commit hash、統合側のdirty状態を表示する。
- SHI側だけに存在し、統合側へ未移植のファイルもレビューできるよう、統合側の欠損を空列として表示する。出力先は既存運用と同じ`.merge_review/three-way/`を既定とする。
- `tests/test_three_way_review.py`で3つの独立Git repo、全列で異なる内容、HTML escape、commit表示、統合dirty表示、統合側欠損ファイルを確認し2 passed。実SHIの`SceneDesc.py`でもHTML生成を確認し、Ruffは成功した。

### 2026-09-06 M-058実施記録

- SHIアルゴリズム移植前の保護契約として、`tests/test_calibration_contracts.py`を追加した。`settings.ini`の`operation_mode`と`CalibMode` 7項目、`OPERATION_MODE`と`CalibMode`の数値を固定した。
- 校正同期FIFOは型aliasだけでなく`CalibFIFOProcess._update()`を同期成功stubで実行し、camera、LiDAR、CAN、`ref_t`の4要素順と値を固定した。productionコードは変更していない。
- 校正MMAPは`mmap_assign.json`の0～14 byte headerと、facadeがその直後へ書く`is_end_calmode`、`status_calibcommon`、`currentmode`、`currentcamera`、`errors_calibcommon`の型・順序をmock writerで固定した。
- 専用5件、設定validation・app config・自動校正終了を含む関連回帰20件がpassした。Ruff、Python構文、VS Code診断、`git diff --check`も成功した。

### 2026-09-06 M-059部分実施記録

- SHIの`diagnosis/calibcheck2d3d_result_diagnosis.py`を記述変更なしで移植した。UI値は校正不要0、書込禁止1、校正必要2、データ不足3、人未検出4、人検知品質不良5、予約6～7とする。
- MMAPへ書込可能な0、2、3、4、5のvalidationと、reason code 1～11から判定不能理由への変換、reason 0の校正要否判定を25件で確認した。SHI productionファイルとの`diff -u`は差分なし、three-way HTMLも生成済みである。
- SHIの`CalibCheck2d3dConf`へ追加された判定、tracking、debug、評価traceの20項目と、その補間元となる`z_height`、`z_height_withmargin`を移植した。debug機能は全て無効を既定とし、ONNXモデルはvendorの`damoyolo_tinynasL45_L_3.onnx`を維持した。
- 設定schema専用3件、M-058/M-059関連37件がpassした。変更sliceのRuff、Python compile、VS Code診断、`git diff --check`も成功した。legacy app config全体のRuff既存診断はHEADとworking treeの双方70件で、新規診断はない。
- vendor旧coreは0、1、3を出力し、SHI新契約では1が書込禁止である。M-060の最初のsliceでproducerとfacadeを同時に切り替え、M-059を`verified`とした。

### 2026-09-06 M-060部分実施記録

- vendor旧score判定の意味をSHIの`CameraCalibCheckStatusDiagnosis`入力へ変換した。十分かつOKはreason 0・acceptable、十分かつNGはreason 0・not acceptable、データ不足はreason 1とし、UI出力を0、2、3へ切り替えた。
- facadeのdebug上書き、setter、MMAP writerもSHI enum・validatorへ同時に切り替えた。`ng`は2、`ok`は0、`un`は3となり、禁止値1はsetterとwriterの双方で拒否する。
- status接続専用3件、M-058～M-060関連40件がpassした。変更sliceのRuff、Python compile、VS Code診断、`git diff --check`も成功した。legacy coreのRuff既存診断はHEADとworking treeの双方31件、facadeは71件から70件となった。
- SHIの`SceneDesc.py`と`YOLOadapter.py`を追加した。Sceneは改行正規化後にSHI版と内容差分なしで、projection、人寸法gate、camera slot保持をhardware不要テストで固定した。YOLO adapterはまだactive detectorへ接続せず、vendor承認済みONNXモデル設定を維持している。
- 2D/3D tracking metadataへ`frame_ix_lastmove`を追加し、停止frameでは更新せず移動frameだけ更新することを確認した。2D workarea LUTの既定値はSHIの修正を反映した。
- 現行vendor `dataproc()`が生成する3D bboxとYOLO結果をSHI形式の`frame_info`へ記録し、3D/2D bboxログvalidationを接続した。reason 2は全camera、reason 3はcamera別にactiveとなった。
- SHIのcalibcheck専用2D/3D SORT recorder、tracking選別、validationを移植した。SHI 3D recorderに残っていた開発者環境の絶対パスは採用せず、vendor設定のcamera別workarea LUTへ接続した。保存済み推論結果をpost処理で再走査し、reason 4は全camera、reason 5はcamera別にactiveとなった。ONNXモデル経路は変更していない。
- post lifecycle stubを含むM-058～M-060関連54件がpassした。追加・更新テストのRuff、production/test compile、VS Code診断、`git diff --check`も成功した。production core全体のRuffはHEAD 31件に対して47件で、増分はSHI互換のclass/method名、SHI閾値のliteral、評価factoryのprivate state設定、import順である。`ctrl/`のSHI表現を優先し、このsliceでは機械的renameを行っていない。
- SHIの3D bbox camera projection、画角内判定、bbox交差・中心差gate、Scene評価、frame時系列対応、legacy-like/strict hit-rate統計、threshold判定を移植した。reason 9は画角内3D対象なし、reason 10は2D/3D共通frameなし、reason 11は共通frameがあっても有効scoreなしとしてactiveになった。
- `data_evaluation_process()`をpost lifecycleの正式経路へ接続し、旧score fallbackを外した。camera別の先行reason 3/5は保持し、正常cameraだけ後段評価結果で更新する。result fileも同じreason/resultから`Unknown`、`OK`、`NG`を出力する。
- reason 6～8はSHI coreでも説明とmappingだけがあり、実際の代入箇所はない。仕様を推測せず予約状態を維持する。M-060は実機入力での評価確認と最終three-way reviewまで`in-review`を維持する。
- projection、Scene matching、reason 9～11、camera別reason保持、post送信順を含むM-058～M-060関連64件がpassした。追加・更新テストのRuff、production/test compile、Pylance syntax、VS Code診断、`git diff --check`も成功した。production core全体のRuff件数は引き続きHEAD 31件、統合版47件である。

### 2026-09-07 M-060 three-way目視レビュー

- `calibcheck2d3d/SceneDesc.py`: `SHI維持`として確認済み。
- `calibcheck2d3d/YOLOadapter.py`: `SHI維持`として確認済み。
- `calibration2d3d/track_main/detect3D/person_tracker_SORT_3d/__init__.py`: `SHI維持`として確認済み。
- `calibration2d3d/track_main/interface_definition.py`: `冗長性整理（機能はSHI維持）`として確認済み。SHIとの差は`Todo`から`TODO`へのコメント表記変更と、`tracking3d_dataclass.__init__`末尾の不要な`pass`削除のみ。
- `diagnosis/calibcheck2d3d_result_diagnosis.py`: `SHI維持`として確認済み。
- `facade/__init__.py`: レビューで判明した未移植箇所を復元した。`CalibrationCommonStatus`、初期値定数、校正要否statusの初期値`UNKNOWN_INSUFFICIENT_DATA`、decimal error・数値status・欠損yaw許容・適用ログを含むSHIのdummy data処理を反映し、現行のMMAP書込み可能値検証を維持した。復元後の再レビュー待ち。
- `config/app_config_calibration.py`: SHIの`bbox_center3d_z_ratio_area_xmin/xmax/ymin/ymax`、2D/3Dの`trackresult_use_lastmove_ix`、6個の`axis_gridpoints_*`を型定義とreaderへ追加した。さらにINIの未収容実パラメータである`z_height`、`z_height_withmargin`、LiDARの`dev_str`、`enable_bbox_shapefilter`を追加し、`placeholder`もINIから読むようにした。directory rootは`resolve_ini_roots()`、個別pathキーは補間後のlistとして既に収容されるため二重保持せず、`DEBUG_REF`は手動切替用の候補値として扱う。
- `config/calib_settings.ini`: `mmap_dir`は統合版の`/dev/shm`を維持し、それ以外のSHIと共通する明示キーはSHI値へ統一した。ONNXモデルも`new_bench_full_20260625.onnx`へ同期した。DEFAULT継承を除く構造比較で、SHIとの差が`mmap_dir`だけであることを確認した。
- 設定回帰は11 passed、Python compile、VS Code診断、`git diff --check`が成功した。Ruff全体実行は同モジュール既存の命名・全角句読点違反を報告したが、今回の追加行に新規違反はない。固定vendor/SHI commitを使って両設定ファイルのthree-way HTMLを再生成済み。再レビュー待ち。
- `calibcheck2d3d/__init__.py`: 診断用2D/3D recorderで欠落していたSHIの評価LUTと作業領域LUTの分離、評価値min/max更新、2D bboxの累積`xymin`/`xymax`更新、`reset()`とperson検出状態を復元した。3D距離maxはSHIの`min()`誤記を採用せず、統合版の正しい`max()`を維持した。関連45件がpassし、Python compile、VS Code診断、`git diff --check`も成功した。
- レビュー済み`YOLODamoBatchAdapter`をactive `dataproc()`へ接続した。camera入力を設定camera数の固定長配列として扱い、中間camera欠損時も後続cameraの推論結果を元のslotへ保持する。欠損slotは空bboxとしてUI・評価・recorderへ渡し、範囲外cameraと欠損frameの描画をskipする。AIモデルload失敗・推論結果診断を含むM-060関連61件がpassした。
- 残りのM-060対象ファイルは未確認。確認状況は`.merge_review/three-way-reviewed/review-status.md`で管理する。

### 2026-09-07 M-061部分実施記録

- `calibration2d3d_class`にSHIのFILE_IO reporterを追加し、通常2D-3D校正の進捗領域JSON、postprocess行列CSV、初期vector JSON、camera mask画像、bbox mask画像の読込境界までcallbackを接続した。診断は`(path, operation, "ExceptionType: detail")`を記録し、元例外を再送出するためvendor lifecycleと停止条件は変更しない。
- SHIの`correspondence_class_optmethod.reset()`は例外時に未定義のローカル`file_io_error_reporter`を参照していたため、その誤記は採用せずbase instanceに保持したcallbackを使用した。mask画像の読込失敗は`assert`または`cv2.resize(None)`ではなく、診断可能な`OSError`へ統一した。
- FILE_IO専用7件、校正保護契約・設定読込を含む関連21件がpassした。Python compile、VS Code診断、import順Ruff、`git diff --check`も成功した。対象モジュール全体のRuffはlegacy命名・型注釈など既存違反を報告するため、この単位では変更していない。

### 2026-09-07 M-061～M-064残件完了記録

- M-061はfile input終端時の一回だけの完了処理、最終3D点100点超のgate、進捗0.5未満時の再計算、結果保存、camera別center-Z ratio領域、校正結果/UI statusのenum plumbing、AI model load・推論診断を接続した。固定SHIにない行列determinant、追加PnP収束、独自tracking品質条件は推測移植しない。
- M-062は起動時と生成直後のLiDAR行列を共通`LidarCalibValidator`へ通し、4x4形状と有限値を同じCE006 policyで検査する。SHIの参照行列差分、並進・回転閾値、XY grid検査は、周辺監視モードのフル検証を後段でまとめて移植する計画に従いdeferredとした。
- M-062の生成結果異常・入力診断異常は校正UI共通error 2へ反映し、共通status enumとyawを送る。初期ideal matrix、後段ideal transform、simulation matrix、crane profile JSON、angle CSVのFILE_IO callbackを所有境界へ接続し、元例外の再送出とVendor lifecycleを維持した。
- 生成行列の評価・CE006 counter・共通error logは`SensorCalibDataInvalidDiagnosis.diagnose_matrices()`へ集約した。3D-3D controllerは生成行列を診断へ渡し、返却issuesからUI/処理結果を決めるだけとし、診断ロジックを`ctrl`へ置かない。
- M-063は`MessageFlow.create_consumer()`が2個目のconsumerを拒否するため、CALIBとSCRUTで入力flowを共有する案を不採用とした。各pipelineの専用flow、Vendor `CalibFIFOProcess`、同期不成立frameの非出力、`FIFOData`のcamera/LiDAR/CAN/`ref_t`順を維持した。
- M-064は`CalibrationCommonStatus`、校正要否statusのvalidationと値の直接書込み、MMAP 0～14 byte header、共通field順が既に統合済みであることを確認した。three-wayユーザーレビューに基づき、SHI waitの毎frame dummy設定と送信を維持し、値と送信順をテストで固定した。
- M-060～M-064の集中回帰は106 passed。M-064のfacade/MMAP/waitは15 passed、CE006再検証は12 passed。対象ファイルのPython compile、VS Code診断、`git diff --check`も成功した。
- 固定Vendor `62dfe7d289c6c607ff0330ba9ae2146cdf982344`、固定SHI `2283a0a68f512d7595fb81032925630f07f1b522`との残差を再確認し、M-060～M-064にthree-way目視確認を妨げる具体的な未移植挙動は残っていない。次工程をthree-way最終確認とする。

### 2026-09-07 M-060～M-064 three-way最終確認

- 固定Vendor、固定SHI、統合working treeのHTMLを対象15ファイルで再生成し、既存レビュー済み9ファイルと合わせて確認した。結果は`.merge_review/three-way-reviewed/review-status.md`へ記録した。
- M-060の大きな構造差はSHIのscene/tracking/score処理をVendor lifecycleへ再配置したもの、M-061は同等アルゴリズムへの診断callback追加、M-062は共通簡易validatorへの接続であり、未移植のblockerではない。M-064のwait dummy設定・送信はthree-wayユーザーレビューに基づきSHIを維持した。
- M-060、M-061、M-062、M-064を`verified`へ更新した。M-063は単一consumer制約と専用flow契約の確認により`vendor-keep / verified`を維持する。

### 2026-09-07 校正上位エラー処理レビュー

- `CalibProcess._err_config_load()`で重要度D `FILE_IO_ERROR`を有効化し、下位data capture・2D-3D・3D-3DのFILE_IO callbackが同じ`SharedErrors`診断へ到達するようにした。
- startupとruntimeの未捕捉I/O例外をprocess境界でFILE_IOへ報告するfallbackを移植した。`OSError.filename`がある場合は実ファイルpathを記録し、ない場合だけ校正INI pathを使用する。下位報告済みの例外はD診断の`KEEPING`契約により重複検出ログを抑制する。
- 3D-3D例外時の共通error 2・unexpected exception・dummy data送信を移植し、loop失敗後は`post_app_loopmain()`を実行しない。status magic numberは`CalibrationCommonStatus`へ置換し、calibcheckは`start2D3DCheckCalc`要求時だけpost計算する。
- processとmanagerのcProfile開始・終了失敗をwarningとして扱い、校正起動・終了処理を継続する。managerの`ser`/`shared_errors`二重引数は既存API互換のため本単位では維持し、重複importだけ除去した。
- `_finalize_calib2d3d_fileend_autoexit()`は下位`calibration2d3d_class.app_loopmain()`の現行確定処理と重複するため移植しない。Vendorの`_unsubscribe()`、shutdown flag、top-level `allow_exit()`による自動終了契約を維持する。
- 新規上位エラー処理3件、校正FILE_IO・自動終了を含む32件、calibcheckを含む65件がpassした。対象のPython compile、重大Ruff、VS Code診断、`git diff --check`も成功した。固定Vendor/SHIとのthree-way HTML 2件を再生成し、ユーザー確認前のため未レビューdirectoryに保持する。

### 2026-09-07 M-048 蓄積deque上限保証

- `accumulate_point()`は処理前にmode別上限へtrimしていたが、最新frame append後は再trimせず、呼出し後のdequeが設定上限を1frame超えていた。SHI現行と同様にpoints/ground双方をappend後にもtrimした。
- 通常modeのpoints/ground上限3/2、負荷低減modeの上限1/1で4frameを連続投入し、毎回上限以内で最新frameが保持されることをテストした。既存buffer切替テストを含む5件がpassした。

### 2026-09-07 M-050 MID360点群復号ベクトル化

- 96点をPython loopと`int.from_bytes()`で復号していた処理を、14 byteのstructured dtypeと`np.frombuffer()`による一括復号へ置換した。little-endian signed XYZ、signed reflect、tag除外、timestampの既存契約を維持する。
- M-035で確定した品質低下時刻の`time.perf_counter()`と`last_quality_degraded` propertyは変更していない。必要な1380 byte未満のpacketは偽の0点へ変換せず、長さを含む`ValueError`で明示拒否する。
- 合成packetの正負XYZ・reflect・timestamp・96x4連続float64配列、短packet、通信品質、不正点群、M-048を含む関連28件がpassした。Python compile、重大Ruff、VS Codeのproduction診断、`git diff --check`も成功した。

### 2026-09-07 M-055・M-057・M-066残件整理

- M-055はoctotree合計点数のMMAP書込みをentity loop外へ移し、UNK/HUMAN/OTHERがすべて空でも予約済み4 byteへ0を書き込むようにした。生成済みflagsによる`ui_interface.cpp`単一object compileは成功した。フルbuildと実MMAP読戻しはC++変更の一括確認へ回す。
- M-057はlegacy `setup.py`のdistribution名とCMake extension名を`octotree`から`argus_synchro_lib`へ統一した。`setup.py --name/--version`は`argus_synchro_lib / 2026.8.25`を返し、CMakeの`${PROJECT_NAME}`出力と一致した。wheel生成はC++一括buildへ回す。
- M-066はcalibration validator、機種別calib設定解決、CALIB中のsettings監視維持、機種別calib INI watcher追加が統合済みであることを確認した。validator・machine profile・reload retryの関連14件とVS Code診断が成功したため`verified`とした。値域の製品仕様確定はマージ欠落ではなく別途仕様管理とする。

### 2026-09-07 M-049・M-053～M-057 C++残件整理と一括build

- M-049は認識精度確保のため、Python/C++の`PcdData.SIZE`を40,000へ統一した。40,000x3の共有slot write/borrowで切捨てがないことを確認し、C++一括build後もextension importに成功した。
- M-053は負荷低減開始を16,000点超、復帰を12,000点未満へ変更した。いずれも5frame継続を維持する。Visualの現在modeログは毎frameのまま、PointsRefineのdeque前後長・mode別上限はmode変化時だけ出力する。閾値境界、継続frame、deque上限、切替ログの関連7件がpassした。
- M-054は`classMMap`を使うUI MMAPとError MMAPが全実設定で2面構成であることを確認した。現mapの`IsWriting`を0にしてindexを切り替えた直後、次mapの`IsWriting`を1へ設定し、次の`begin_frame()`までreaderに取得される競合窓を閉じた。単一objectと一括buildは成功したが、Godot readerとの並行試験は残す。
- M-056はフレームごとのアドレス、座標配列、画像バイト列、点群詳細を`info`から`debug`へ変更した。起動情報、件数、総点数、frame末尾時間などのサマリは`info`に維持した。M-055を含む`ui_interface.cpp`単一objectと一括buildは成功した。実機でのログ量確認は残す。
- M-057は`argus_synchro_lib-2026.8.25-cp312-cp312-linux_aarch64.whl`の生成、install、`argus_synchro_lib.controller` import、distribution metadataを確認して`verified`とした。
- `make install`は成功し、C++ extensionとwheelを再生成した。MMAP例外・校正MMAP ABI・負荷低減を含む関連34件と、M-053専用7件がpassした。M-055の実MMAP読戻し、M-054のGodot reader並行試験、M-056の実機ログ量確認は引き続き残件とする。

### 2026-09-08 M-047 TensorRT実機cache生成

- Jetson Orin、ONNX Runtime 1.23.2でTensorRT/CUDA/CPU Execution Providerを認識した。設定の既定モデルパス`/home/nvidia/checkpoints/damoyolo_large.onnx`は存在しなかったため、workspace内の`checkpoints/damoyolo_large.onnx`を明示してbatch 3で実行した。settings swapは失敗時・成功時ともbackupから復元された。
- モデルSHA-256先頭16桁`9854feaf385602db`、batch 3・現行TensorRT設定のcache key`config-cd14daaf66da`へ、FP16 SM87 engine 86,753,004 byte、profile 22 byte、timing cache 5,336,127 byteを新規生成した。新規buildは約24分を要した。
- 同じモデル・batchで再実行し、生成物mtimeが変化しないままTensorRT CUDA Graphのcapture/replayとI/O Bindingウォームアップ推論が6.2秒で完了したため、cache再利用を確認した。M-047を`verified`とする。

### 2026-09-08 M-054・M-055 実MMAP試験

- `UI_interface.octotree_info()`と既存public `close_mmap()`をPython bindingへ公開し、製品の書込み処理を実ファイルMMAPに対して直接検証できるようにした。対応するtype stubも更新した。
- M-055は同じbufferへ非空octotree、空octotreeの順で書き、offset 10のlittle-endian int32を実ファイルから読戻して点数が1から0へ上書きされることを確認した。M-055を`verified`とする。
- M-054は2面の`ErrorMMapWriter`で初期切替後のcurrent bufferに`IsReading=1`を設定し、`rotate_if_busy()`直後に旧bufferの`IsWriting=0`と次bufferの`IsWriting=1`を実ファイルから確認した。競合窓を閉じるprotocol条件は検証済みだが、Godot reader実processとの並行試験は残す。
- `tests/test_ui_mmap_octotree_count.py`は2 passed。Ruff、VS Code Python diagnostics、`git diff --check`も成功した。C++ extensionは現在の環境で再buildし、通常wheel install後に新bindingのimportを確認した。

### 2026-09-08 M-052 SCX3500 CAD資産取込み

- SHIコミット`6699794`は`immobile/scx3500_upper.{obj,mtl}`と`mobile/scx3500_bottom.{obj,mtl}`の4ファイルだけを追加しており、manifestや読込コードは変更していない。
- VendorとSHIの`SCX3500-3/vis_machine_info.jsonc`は同一で、既存の`01_upper_part.obj`～`10_Letters.obj`を参照する。SHI repository全体にも追加4ファイル名の参照は存在しない。
- ユーザー方針により、現時点では未参照でも今後使用する資産として4ファイルを原本どおり取り込んだ。上部・下部OBJの頂点・面とMTL参照を確認し、SHI原本とのbyte一致も確認した。M-052を`shi-adopt / verified`とする。

### 2026-09-08 M-068 Vendor/SHI最終残差監査

- SHI基準commitまでの非merge commit一覧をM-001～M-067の根拠へ照合し、後半の機能commitに未分類項目がないことを確認した。
- source/configの相対path一覧を比較した結果、SHI限定は14ファイルだった。`common/settings_validation.py`はVendorの`config/settings_validation.py`、`diagnosis/runtime_policy.py`はVendorの`diagnosis/error_diagnosis.py`へ責務を統合済みである。
- SHIの`detect2d_cpu.py`と`detect2d_jetson-gpu.py`はVendorの統合`detect2d.py`へ置換済みで、M-047の動的入力名、model/config別cache、provider fallbackを含むため機能欠落ではない。
- SHIの`jetson_monitor_helper.py`はSHI自身に呼出し元がなく、Vendorは`jetson_monitor/jm/`の新しいmonitor実装をAppManagerへ接続済みのため移植しない。
- SCX2000専用校正JSON 5件は追加commitに含まれるが、現行SHI・履歴の設定やコードからファイル名参照がない。現行機種別設定はVendorと同じ汎用JSONを参照するため、未使用開発資産として移植しない。
- 残るSHI限定4ファイルはM-052のSCX3500 CAD資産として取込み済みである。以上から、実行経路に台帳未分類の機能差分は残っていない。

### 2026-09-08 M-051 新YOLOモデルcache確認

- `settings.ini`と`calib_settings.ini`が参照する`new_bench_full_20260625.onnx`、batch 3、現行TensorRT設定に対応する`model-24b037ea4f4323a5/config-cd14daaf66da`へengine、profile、timing cacheが生成された。
- batch 3のTensorRT実推論テストは1 passed。推論前後で3 artifactのmtimeが変化しなかったため、新規buildではなく既存cache再利用を確認した。
- 機種別通常settingsへの展開と精度・FPS・GPU memoryの製品評価は引き続きM-051の判断項目とする。

### 2026-09-08 M-056 実機ログ確認

- 2026-09-08 10:58～11:26の実機runログを対象に、camera index・画像size/data・点群member詳細・座標配列などM-056でdebug化したメッセージがINFOへ出ていないことを確認した（対象詳細INFO 0件）。
- octotree合計点数、frame番号、frame末尾時間など維持対象のサマリINFOは807件記録されていた。C++実行テストでも`member_points_num`がDEBUG、`octotree_pcd_num`がINFOであることを固定した。
- 詳細抑止とサマリ保持を実ログで確認できたためM-056を`verified`とする。別系統の「クラスタリングの最大最小」INFOは本項目のMMAP詳細ログではなく、必要なら別のログ量改善として扱う。

### 2026-09-08 M-054 Godot reader並行試験

- `argus_bootfig_jetson.sh appimage`でMain、MonitorArgus、`CraneViewer-aarch64.AppImage`を通常起動し、statusがRUNNING、Visual frameが15209以降へ継続する状態で`/dev/shm/map0.dat`と`map1.dat`を観測した。
- 2秒間に393回flagsを読み、主状態として`map0=(IsWriting=1, IsReading=1), map1=(0,0)`を175回、逆側を169回確認した。reader/writerの切替を12回観測し、両面が交互に予約・読取りされることを確認した。
- 直接protocol試験の旧buffer `IsWriting=0`、次buffer `IsWriting=1`と合わせ、M-054を`verified`とする。
- 試験終了時、Godotとworkerは停止したがMainがSHUTDOWN後も`do_wait`で残留したためSIGTERMで終了した。これはMMAP handshakeとは別の終了処理残件として扱う。

### 2026-09-08 M-069～M-073実施記録

- CE006は理想行列との差を`solve(reference, estimated)`で求め、並進norm、回転角、円形grid上の最大XY変位を設定閾値と比較する。対象と参照の件数不一致もCE006 issueとし、`zip()`の暗黙切捨ては採用しない。
- CE007～CE010はfisheye内部parameterとcamera-LiDAR外部行列の存在、読込、構造、形状、有限値を共通validatorで診断する。camera理想差分はSHI同様stubとし、4台目のpath schemaがない現状ではcamera 3をunsupportedとしてCE010へ発報する。
- 校正MMAPにもM-054と同じ切替直後予約を追加した。負荷低減は40,000点capacityと5frame継続・strict境界を維持し、開始・復帰ratioを共通settings 5種から起動時と再読込時に反映する。機種別parameterには追加しない。
- `shared_err_config.py`はSHIと同一。全error enumと診断tupleの長さは一致する。`ErrorConfig`の62属性に対してJSONは7つのVendor module errorが欠け、11項目がclass既定値へ暗黙依存していたため、既定値を変えず全キー・全fieldを明示して回帰テストを追加した。
- SHIはLiDAR0/1・IMU0/1 parameterを個別に持つ一方、Vendorは`lidar_n_*`・`imu_n_*`を共有する。個別閾値化は設定schemaと運用を変えるため本単位では移植せず、要判断差分として残す。Vendorのheartbeat/lifecycle拡張とSHIの入力health generationも同様に一括置換しない。

### 2026-09-08 M-074 校正MMAP旧エラー領域の0固定

- 校正MMAPの4 byteエラー領域は、エラー通知を専用Error MMAPへ移行したため常に`0`を書く予約領域とした。
- `CalibGodotInterface.error_info()`の呼出しsignatureと4 byteのaddress進行は互換性のため維持し、`SharedExcepts`と従来error codeの値には依存しない。
- 未使用になった`generate_error_code()`を削除した。
- 非ゼロの旧error codeと負荷状態を渡しても`0`を書き、書込addressが4 byte進むことを契約テストで確認した。校正契約テストは11 passed。

### 2026-09-08 M-075 周辺監視MMAP旧エラー領域の0固定

- 周辺監視MMAPの4 byteエラー領域も、エラー通知を専用Error MMAPへ移行したため常に`0`を書く予約領域とした。
- `UI_interface.error_info(int isslow)`の呼出しsignatureと4 byteのaddress進行は互換性のため維持し、負荷低減状態には依存しない。旧`generate_error_code()`は削除した。
- 旧領域へ非ゼロ値を事前設定し、非ゼロの`isslow`を渡しても`0`へ上書きされ、後続の機体角が従来どおりoffset 14へ書かれることを実MMAP契約テストで確認した。周辺監視UI MMAPテストは3 passed。

### 2026-09-08 M-076 Ctrl+C時のErrorMonitor残留修正

- `argus_bootfig_jetson.sh`のcleanupは別sessionのMainへSIGINTを送るが、Mainのsignal handlerは`sys.exit(0)`で通常ループ末尾を飛び越えるため、ErrorMonitor専用`error_activator.disable()`へ到達せずMainが終了待ちに残っていた。
- 汎用`setup_signal_handlers()`へ任意の`shutdown_callback`を追加した。MainではErrorMonitor起動完了後にcallbackを登録し、`ProcessManager.graceful_stop_all()`のdisable、terminate、killと`CompositeClosable.close()`まで完了させる。通常終了も同じhelperを使用する。
- 残留Mainを終了した後も、`multiprocessing.spawn_main`として孤児化したErrorMonitorがError MMAPを書き続ける事象を確認した。追加調査では過去10起動分のErrorMonitorと`resource_tracker`計20件が孤児化しており、local_pipe2のPython完全pathで限定して全件SIGKILLし、MMAP利用者なしを確認した。
- `argus_bootfig_jetson.sh`は起動中に保持する`flock`を追加し、前回のスクリプトまたは子プロセスが残る間は2個目を終了コード1で拒否する。外部lockを保持した実動作試験で、MMAP準備前に「既に起動中です」と終了することを確認した。
- signal callback、StatusMMAP、ProcessManagerの関連テストは10 passed。Python 3.12の既存fork警告7件のみ。シェル構文検査と`git diff --check`も成功した。

### 2026-09-08 M-077 起動画像のstatus表示復元

- `argus_bootfig_jetson.sh`の第2引数で`production|development`を選択する。省略時は従来互換の`development`とする。量産用の`production`はGodotの背面にfehを常時表示し、RUNNING遷移時にも終了しないため、Godotとの切替時にdesktopやfehの縮小animationが露出せず、Godotが異常終了した場合も既に表示済みの起動画面が間断なく現れる。
- `development`は画面操作を妨げないよう1920x1080のサイズ指定で表示し、従来どおりRUNNING遷移時にfehを終了する。起動例は量産が`./argus_bootfig_jetson.sh appimage production`、開発が`./argus_bootfig_jetson.sh appimage development`。
- 1280x800の起動画像を1920x1080画面へ通常windowで表示していた`--geometry`を廃止し、fehのfullscreen、auto-zoom、black image background、hide-pointerを使用する。縦横比の余白を黒で埋め、PC背景とmouse pointerを露出させない。
- `FEH_PID=0`に対する`kill -0`は現在のprocess groupを検査して成功するため、未起動判定として使えなかった。PID 0を明示的に未起動として扱う条件へ修正した。
- cleanupではMainとMonitorArgusを先に停止し、起動画像監視とfehを最後に終了する。停止処理中もdesktopを露出させない。

### 2026-09-09 FILE_IO_ERRORイベント・校正書込み診断

- 重要度Dはシステムを停止させないため、共通`StateErrorDiagnosisD`の`DETECTION`、`KEEPING`、`RECOVERY`契約を維持した。FILE_IOを発生ごとに常に`DETECTION`とする案は、同じ欠損ファイルを周期的に読む経路でログ洪水になるため採用しない。
- `FileIoError`もD共通状態遷移を使用し、最初の障害だけ`DETECTION`としてwarningへ記録し、正常復帰までの後続障害は`KEEPING`としてログを抑止する。正常入力または`reset_error()`後の再発は再度`DETECTION`となる。
- ログレベル、文面、詳細情報は`diagnosis`配下の`FileIoError`が所有する。各I/O所有箇所はpath、operation、元例外を渡すだけとし、ログ出力判断を重複実装しない。
- 2D-3D結果行列のdirectory作成・CSV保存、非同期sensor data pickle保存、PnPのNPY/TXT成果物保存、3D-3D結果行列のdirectory作成・CSV保存を、それぞれpathと`write ...`操作名が分かる所有境界でD診断へ接続した。
- 2D-3D・3D-3D結果保存と非同期pickle wrapperは診断後に元の`OSError`を再送出する。PnP保存は既存どおり例外をwarningへ記録して吸収し、校正制御と停止条件を変更していない。PnP reporterは省略可能引数として追加し、既存呼出しAPIを維持した。
- FILE_IOの初回検出、継続KEEPING、復帰後再発、モジュールログ間引き、2D-3D、3D-3D、data capture、校正process error handlingの関連テストを実行した。変更ファイルのVS Code診断と`git diff --check`も確認した。

### 2026-09-09 M-028 CE004設定配線補完

- SHIの`load_err_config()`は`CRANE_MODEL_FILE_MISSING`を起動時に更新していたが、Vendorのprocess別設定更新へ移した際、実際にCE004を使用するPointsRefineとVisualの`_err_config_load()`から更新が漏れていた。
- 両processで共有設定をCE004診断へ反映し、`CraneModelFileMissingDiagnosis.excepts_diagnosis()`も`is_enabled`を確認するようにした。設定OFFでは対象例外をcounterへ加算・ログ出力せず、元例外を再送出する既存process制御は維持する。
- 専用テストで対象10例外、非対象例外、既定OFF、設定更新、PointsRefine/Visualの設定配線、診断所有ログ、元例外再送出を確認した。

## 10. 次のCopilotへの開始指示

次回は、いきなり全体差分を再探索しない。次の順で開始する。

1. 本書と関連文書を読む
2. 両リポジトリのHEADと `git status --short` を確認する
3. 統合台帳から未処理項目を1件選び、そのvendor側定義、SHI側定義、隣接テストだけを読む
4. 校正へ着手する場合はM-058のsettings/MMAP/FIFO契約テストから開始し、`docs/calibration-merge-plan.md`の順序を守る
5. 最小の単体テストまたは基盤移植を行う
6. 狭いテストを直ちに実行する
7. 本書の台帳と確認結果を更新する
8. CANと校正の統合後、両リポジトリの残差分を機能単位で再監査する。過去のレビュー台帳で対応済みとされた項目も、現行vendorコードへの実装有無を検索またはテストで再確認し、未移植、vendor維持、意図的な不採用のいずれかを記録する

新しい判断が既存記録と矛盾した場合は、古い記録を黙って残さず、理由と日付を添えて本書を更新する。
