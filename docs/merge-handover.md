# Vendor/SHI 統合作業 引継ぎ

最終更新: 2026-09-03

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
| M-004 | CE015ログファイルI/O | SHI logger/action diagnosis | manual-port | pending | `common/app_logger.py` ほか | 再帰と重複計上を専用試験 |
| M-005 | 校正サブシステムのI/O境界 | SHI `9432a4f` | manual-port | pending | calibration modules | アルゴリズム変更と分離、後段 |
| M-006 | 負荷低減モード | SHI `2283a0a` | decision-needed | pending | diagnosis/process/accumulation | 性能と復帰条件を別レビュー |
| M-007 | ファイル入力ループ | SHI `e2362ec` ほか | decision-needed | pending | process/provider | モード制御と分離してレビュー |
| M-008 | 周辺監視カメラ動画入力I/O | SHI `image_process.py` | manual-port | verified | vendor `image_process.py`, tests | 動画open/initだけを診断、専用テスト2件pass |
| M-009 | カメラJSON読取検証 | SHI `image_process.py` | drop | verified | docs/固有CE設計 | SHIの汎用FILE_IO事前検証は不採用。通常設定はCE005、fisheyeはCE007-CE010で別途接続する |
| M-010 | 重要度D状態診断のエッジ化 | SHI `error_diagnosis.py` | shi-adopt | verified | vendor D基底, tests | vendor index/APIを維持し、DETECTION/KEEPING/RECOVERY/NORMALを返す |
| M-011 | モジュール例外traceback | vendor `state_d_errors.py` | vendor-keep | verified | module error classes, tests | vendorの `exc_info=True` で実ファイルへのtraceback出力を確認 |
| M-012 | 継続モジュール例外の時間間引き | SHI `_ModuleError` | manual-port | in-review | error config/module errors/process catch | カメラ経路をM-012aで検証済み。他moduleは個別に展開する |
| M-012a | カメラ継続モジュール例外の時間間引き | SHI `_ModuleError` | manual-port | verified | camera error config/module error/image process/tests | 同一signatureを60秒間抑止し、初回・変更時はtraceback、時間経過後は要約 |
| M-013 | process終了時の診断情報 | SHI process `finally` | manual-port | pending | visual/calib/get_dataほか | vendorの終了処理を残し、観測ログだけを候補ごとにレビューする |

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

## 10. 次のCopilotへの開始指示

次回は、いきなり全体差分を再探索しない。次の順で開始する。

1. 本書と関連文書を読む
2. 両リポジトリのHEADと `git status --short` を確認する
3. M-002のvendor側定義、SHI側定義、隣接テストだけを読む
4. `FILE_IO_ERROR` のindex配置と `StateErrorDiagnosisD` 契約について仮説を立てる
5. 最小の単体テストまたは基盤移植を行う
6. 狭いテストを直ちに実行する
7. 本書の台帳と確認結果を更新する

新しい判断が既存記録と矛盾した場合は、古い記録を黙って残さず、理由と日付を添えて本書を更新する。
