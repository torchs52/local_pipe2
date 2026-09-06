# 校正サブシステム統合方針

最終更新: 2026-09-06

## 1. 目的と結論

SHI版の校正アルゴリズムを、vendor版の起動・終了・process管理・同期入力・MMAP境界へ機能単位で統合する。SHI版ファイルやコミットの一括採用は行わない。

責務ごとの基準は次のとおり。

| 責務 | 基準 | 統合方法 |
|---|---|---|
| 起動、終了、再起動、process activation、動作モード遷移 | vendor | `vendor-keep` |
| 校正用FIFOの生成、consumer契約、同期失敗時のframe破棄 | vendor | `vendor-keep` |
| 2D-3D、3D-3D、2D-3D診断の数理・判定ロジック | SHI | vendor lifecycle内へ`manual-port` |
| `settings.ini`、校正MMAP、Godot UIの値・並び・型 | 既存外部契約 | byte互換を保つ`shared-contract` |
| CE006～CE010、CE014、D-level、module error | `error_list.txt`の所掌 | 診断種別ごとに個別判断 |
| 評価用simulation、自動終了、debug出力 | 製品要件と分離 | 既定OFF、必要なものだけ個別採否 |

### 1.1 `ctrl/`配下の記述方針

`argus_synchro/calibration_mat_generator_modules/ctrl/`配下では、処理の意味と外部契約が同じであれば、SHI版のクラス分割、処理順、命名、データ表現、コメントを可能な限り維持する。vendorコードへ意味だけを再実装して書き換えることを既定としない。

SHI版から記述を変えるのは、次のいずれかを具体的に説明できる場合に限る。

- vendorのprocess lifecycle、FIFO、MMAP、エラーdispatchへ接続するために必要
- 明らかな重複、到達不能処理、過大なdebug/simulation処理を除去できる
- correctness、型安全性、資源解放、性能上の問題をテストで示せる
- vendor側の共有部品を使わないと、同じ責務が二重実装になる

単なる好み、整形、命名統一を理由にSHI版を広く書き換えない。冗長性を整理する場合も、先にSHI版と同じ振る舞いをテストで固定し、変更範囲と理由をファイル別のレビュー記録へ残す。

## 2. 保護するvendor境界

次はSHI版で置き換えず、必要な接続点だけを追加する。

- `argus_synchro/__main__.py`のCALIB起動・停止・モード遷移
- `argus_synchro/process/calib_process.py`のprocess lifecycle、dispatcher順、shutdown
- `argus_synchro/process/calib_fifo_process.py`のセンサ入力所有、厳密同期、同期失敗時の非送信
- `argus_synchro/message/calib_fifo_message.py`の`FIFOData`形式
- `argus_synchro/calibration_mat_generator_modules/boss/`のサブモードinstance所有
- vendorの起動時`operation_mode`継続方針
- `SharedErrors`、`log_output()`、`ResultDiagnosis`を使う診断dispatch

サブモードflagが複数同時に真の場合、現行dispatcherは3D-3D、2D-3D、2D-3D診断、waitの順に選ぶ。この優先順位は現状互換として維持する。ただしUI側で排他にするのか、process側で不正組合せを拒否するのかは外部UI仕様を確認して別途決める。

## 3. 共有契約

### 3.1 settings

外部UIは`General.operation_mode`と`CalibMode`を書き換える。少なくとも次のキー名、型、意味を変えない。

- `isRunning3D3Dcalib`
- `isRunning2D3Dcalib`
- `cameraID`
- `start2D3DCalibCalc`
- `isRunning2D3Dcheck`
- `start2D3DCheckCalc`
- `isRunningInterfaceDebug`

`config/settings.ini`は運転時に更新される契約ファイルであり、SHI版による一括上書きを禁止する。

`settings.ini`の監視は動作モードにかかわらず常時維持する。校正モードでも
`General.operation_mode`と`CalibMode`の変更を反映する必要があるため、監視対象から
外してはならない。機種別の校正設定ファイルを監視する場合は、`settings.ini`の監視を
置き換えず追加で登録する。

### 3.2 MMAP / Godot UI

`mmap_assign.json`のaddress、field順、幅、および既存の数値はABIとして固定する。内部で`IntEnum`を使う場合もMMAPへは既存の整数値を書き込む。

`status_calibcommon`は0: inactive、1: running/setup、2: calculating、3: completedの値を維持する。`currentmode`、`currentcamera`、`errors_calibcommon`、カメラ別校正状態・校正要否状態も、Godot UIとの往復試験なしに値を変更しない。

SHIの`CameraCalibCheckStatus`はUI向けの校正要否結果であり、重要度A～Dの製品エラーとは別物として扱う。予約値1、6、7は書込み不可のままにし、0、2、3、4、5だけを出力候補とする。

### 3.3 同期入力

周辺監視と元センサmessageを共有する一方、校正processへは`CalibFIFOProcess`で同期が成立したframeだけを渡す。アルゴリズム移植のために生のcamera/LiDAR consumerを各サブモードへ追加しない。

## 4. サブシステム別方針

### 4.1 2D-3D校正診断

最優先のSHIアルゴリズム統合対象とする。現行SHIは約3,009行、vendorは約703行で、SHI側だけに`SceneDesc.py`、`YOLOadapter.py`、校正要否診断クラスがある。単一ファイル差分ではなく次の順に分ける。

1. UI結果enum、reason code 0～11の変換、値域検証
2. `CalibCheck2d3dConf`の製品用設定schemaと入力検証
3. YOLO batch adapterと空結果契約
4. `SceneDesc`のvertical consistency、human-size gate、対応付け
5. 2D/3D tracking recorderと共有tracking interface
6. frame蓄積、品質gate、score、camera別最終判定
7. vendorのpre/app/post/end-wait状態遷移への接続
8. MMAP出力とモード終了
9. FILE_IO、AI推論、invalid data、module errorの接続

SHI追加設定のうち、評価閾値と`eval_frame_stride`はアルゴリズム契約として候補にする。動画、pickle、traceなどのdebug設定は製品ロジックから分離し、既定OFFのまま必要性を判断する。ONNXモデル変更は精度・性能承認が必要な別項目とする。

### 4.2 通常2D-3D校正

SHI版にはcoreだけでなくprogress、correspondence、2D/3D tracking、image preprocessにも差分がある。診断と共有する部品を先にAPI単位で比較し、通常校正の既存結果を変えないことを確認してから採用する。

SHIの終了時計算やファイル入力自動終了はアルゴリズム結果の確定処理とprocess終了制御を分離する。計算結果を失わないfinalizeは採用候補だが、shutdownと再起動要求はvendor方式を維持する。SHIの`Calib2d3dResultDiagnosis`と`CameraCalibrationStatusDiagnosis`は現状DEFAULTを返すスタブなので、完成機能として移植しない。

### 4.3 3D-3D校正

行列生成、LiDAR対応、simulation差分と、エラー完了UI状態を別々に扱う。SHIの異常時完了通知は採用候補だが、例外を握り潰して正常完了に見せない。vendorのprocess例外境界とmodule error経路を維持し、UIへエラー完了状態を送った後の停止動作をテストで固定する。

CE006の参照行列との差分判定と生成直後検証は、対象行列と参照行列の対応をindexで明示してから追加する。`zip()`による件数切捨てや誤対応は持ち込まない。

### 4.4 capture / wait / facade

captureはアルゴリズムではなく同期I/O境界として独立マージ単位にする。timestamp比較、buffer、frame thinning、file input終了条件の差を比較し、clock timeoutはmonotonic clockへ統一する。

wait modeはvendor lifecycleを維持し、診断用に必要なデータ準備と不要なdummy上書き抑止だけを候補にする。facadeのenum化は数値ABIを変えない内部型安全性として採用可能だが、`mmap_assign.json`変更とは分離する。

## 5. エラー処理

| 種別 | 方針 |
|---|---|
| CE006 センサ校正データ不正 | 実装済みの基本健全性を維持。参照差分と生成結果検証は3D-3D単位で追加判断 |
| CE007～CE010 カメラ校正データ不正 | SHI担当だが現行は未完成。仕様と実装が確認できるまで推測実装しない |
| CE014 動作モード遷移エラー | NSW/vendor所有。SHIアルゴリズムから置換しない |
| D-level `FILE_IO_ERROR` | 非重要補助・評価入力を所有境界で分類。CE006～CE010等の固有エラーを優先 |
| AIモデル/推論 | load失敗はCE013候補、結果内容不正はD-level候補。通常運転と校正で二重計上しない |
| calibration module error | vendorの`CALIBRATION_MODULE_ERROR.log_output()`経路を維持 |
| 校正UI status/error | 製品エラーとは別レイヤー。UI状態遷移だけに使用 |

process最外周で`OSError`等を一律`FILE_IO_ERROR`へ変換しない。パスと操作を知る最も近い所有境界で診断し、再送出後に同じI/Oエラーを二重計上しない。

## 6. 実装順と検証ゲート

1. settings/MMAP/FIFOの契約テストを追加する。
2. UI結果enumとreason code変換を、アルゴリズム非依存の単体として移植する。
3. `CalibCheck2d3dConf`の製品設定だけを追加し、欠損・型・範囲を検証する。
4. `YOLOadapter`と`SceneDesc`を純粋入力で単体検証する。
5. tracking/correspondence共有部品を移植し、通常2D-3Dの回帰を確認する。
6. 2D-3D診断coreをvendorのpre/app/postへ接続する。
7. 通常2D-3D、3D-3Dをそれぞれ独立して統合する。
8. capture、wait、facadeの必要差分だけを統合する。
9. error接続と実機/Godot UI試験を行う。

各段階で最低限、設定読込、正常・不足データ・人未検出・検知品質不良、camera別結果、MMAP byte列、モード開始/計算/完了/待機、例外時のUI状態と製品診断を確認する。最後にファイル入力の再現試験、実センサ同期、全体回帰、Jetson上のFPS・メモリを確認する。

## 7. 三者差分レビュー

校正統合の完了判定では、vendor、SHI、統合版の3者を同時に比較する。比較元が作業中に動かないよう、実装開始時にvendor基準commitとSHI基準commitを記録する。統合版はレビュー対象のworking treeとし、レビュー時のHEADとdirty状態を記録する。

三者表示には、`local_pipe`のremote branch `origin/vendor-20260817-integration`から移植した`scripts/three_way_review.py`を使用する。このビューアはファイル単位のHTMLを生成し、左から`Vendor`、`SHI`、`Integration working tree`を同期表示する。

ビューアはvendorとSHIについてrepo pathとGit refを別々に受け取る。現在のようにSHI版が別リポジトリにあっても、一時refの作成、ブランチcheckout、既存working treeの切替は不要である。レビュー時にはbranch名だけでなく、各refが解決したcommit hashもHTMLへ記録する。

レビューは次の順で行う。

1. `ctrl/`配下の三者で異なるファイルと片側限定ファイルを一覧化する。
2. 対象ファイルごとにthree-way HTMLを生成し、SHIから統合版へ残した記述と変更した記述を確認する。
3. vendorから統合版への差分で、vendor保護境界への変更が必要最小限か確認する。
4. SHIから統合版への差分で、アルゴリズムや処理表現を変更した箇所に理由とテストがあるか確認する。
5. ファイルごとに`SHI維持`、`vendor接続のため変更`、`冗長性整理`、`不採用`のいずれかを記録する。

次の形でファイル単位のHTMLを生成する。

```bash
python scripts/three_way_review.py \
	--integration-repo "$INTEGRATION_REPO" \
	--vendor-repo "$VENDOR_REPO" \
	--vendor-ref "$VENDOR_REF" \
	--shi-repo "$SHI_REPO" \
	--shi-ref "$SHI_REF" \
	argus_synchro/calibration_mat_generator_modules/ctrl/<relative-file>
```

vendor repoを省略した場合はintegration repoを使い、各refの既定値は`HEAD`とする。ただし最終レビューでは再現性のためcommit hashを明示する。統合側にまだ存在しないSHI専用ファイルも、右列を空として表示できる。

HTMLは既存運用に合わせて`.merge_review/three-way/`へ生成し、目視確認済みを`.merge_review/three-way-reviewed/`で管理する。最終レビューでは、三者差分で指摘された変更理由と対応テストを統合台帳へ記録する。三者比較が終わるまでM-060～M-062を`verified`にしない。

## 8. 明示的に採用しないもの

- SHI校正ディレクトリまたはコミットの一括コピー/cherry-pick
- SHIの起動時`operation_mode=0`強制reset
- simulation用path、ローカル評価値、大容量debug出力の製品既定化
- 未実装スタブを完成した診断として接続すること
- `mmap_assign.json`の理由のない変更
- 校正アルゴリズムからprocessを直接終了・再起動する制御

## 9. 着手前に確認が必要な項目

- Godot UIが期待するカメラ別校正要否値0、2、3、4、5と初期値
- 複数サブモードflagが真の場合の正式仕様
- SHI新診断で使用するONNXモデルと精度・性能基準
- SHI追加評価閾値の機種別既定値
- 2D-3D診断の完了条件、再試行条件、結果保持期間
- CE007～CE010の判定仕様とSHI側の完成実装
- 3D-3D参照行列の対象対応と許容閾値
