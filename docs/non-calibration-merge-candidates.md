# 校正関連以外のマージ候補

調査日: 2026-09-06

## 1. 調査範囲

- 統合先: vendor `4ccd66c` (`local_pipe2`)
- 比較元: SHI `2283a0a` (`${HOME}/argus_pipe_filter`)
- SHIの2026-08-25以降の非mergeコミットと、既存台帳で未確認だった性能・配布関連コミットを確認した。
- 校正処理、校正設定、ICP、LiDAR位置ずれ検出は対象外とした。
- 診断、CAN、ファイル入力ループなど、統合台帳で `verified` の機能は再候補化していない。

## 2. マージ候補

| ID | 優先度 | 機能 | SHI根拠 | 現状と推奨 | 主な検証 |
|---|---|---|---|---|---|
| M-047 | 高 | TensorRTキャッシュ・入力名・provider選択の堅牢化 | `ecbc79f`、現行 `detect2d.py` | vendorは入力名を `images` に固定し、モデルと設定が異なるengineを同じディレクトリへ保存する。SHIのモデル固有入力名、モデルhash・設定hash別cache、利用可能providerだけの選択をvendor構造へ分割移植する。CPU sessionによる入力名取得の起動コストは測定する。 | helper単体、複数モデル/複数batchのcache分離、TensorRT実機、CUDA/CPU fallback、CE013 |
| M-048 | 高 | 負荷低減中の蓄積deque上限保証 | SHI現行 `AccumulatePoints.py`、由来 `ccae2a1` | vendorはappend前にtrimするため、処理終了時に設定上限を1フレーム超え得る。append後にもtrimし、通常/負荷低減それぞれで実効上限を保証する。既存M-006の局所補完として扱う。 | `accumulate_point()`の連続呼出しで通常/低減上限、モード切替、最新フレーム保持 |
| M-049 | 高・要判断 | 点群メッセージ上限 20,000→40,000 | SHI `2283a0a`、`message/input_message.py`、`argus_synchro_lib/.../pcd.h` | vendorはPython/C++とも20,000、SHIは40,000。vendorの負荷低減点数閾値は40,000基準なので、20,000で切られた入力では点数条件に到達できない。`PcdData::SIZE`はstatic定数なので構造体自体のABI変更ではないが、Python共有messageとC++ detect3dの固定容量契約が変わる。両側を同時変更・再ビルドし、共有メモリ量、Visual、処理時間を実測して採否を決める。 | Python/C++定数一致、共有message、detect3d、Visual、メモリ量、FPS、Jetson実機 |
| M-050 | 中 | MID360点群復号のNumPyベクトル化 | SHI `5265abb`、現行 `device/lidar/mid360_points.py` | vendorは96点をPython loopで復号し、SHIはstructured dtypeと`np.frombuffer()`を使う。復号部分だけを移植し、M-035で確定した`perf_counter()` heartbeatと`last_quality_degraded`契約はvendor版を維持する。 | 合成packetの座標・reflect・timestamp一致、短packet、通信品質診断、実機packet rate |
| M-051 | 中・要判断 | 既定YOLOモデルを`new_bench_full_20260625.onnx`へ変更 | SHI `9d5c72f` | モデルファイル自体は両repoで同一hashだが、vendor機種別settingsは主に`damoyolo_large.onnx`を選択している。精度・速度・TensorRT engine生成時間の承認後に機種別設定を変更する。ローカル`settings.ini`は一括上書きしない。 | 機種別精度、batch 1/2/3、FPS、GPU memory、初回build/再起動時間 |
| M-052 | 中・要確認 | SCX3500可視化CAD資産 | SHI `6699794` | SHIにSCX3500の上下部OBJ/MTL 4ファイルがありvendorにはない。現行コードに固定ファイル名参照はないため、Godot/機種profileがこの配置規約を使うことを確認して資産単位で採用する。 | SCX3500 profile生成、OBJ/MTL読込、Godot表示、配布物への同梱 |
| M-053 | 低・要判断 | 負荷低減閾値と切替ログ | SHI `2283a0a` | SHIは点数閾値を40,000の90/80%から40/30%へ変更し、復帰判定と蓄積バッファ切替ログを追加する。閾値は製品チューニングなので自動移植しない。M-049決定後に実機測定で決め、ログ追加は独立して採用可能。 | 閾値境界、ヒステリシス、ログ量、通常/熱抑制/処理遅延条件 |
| M-054 | 高・要判断 | MMAP二重バッファ切替時の次バッファ予約 | SHI `d9ba78b`, `655aaaf`、`argus_synchro_lib/cpp/src/clsmmap/ClsMMap.cpp` | vendorは現在mapの`IsWriting`を解除してindexを進め、次回`begin_frame()`まで次mapを予約しない。SHIはindex切替直後に次mapの`IsWriting=1`を設定する。readerとの競合窓を閉じる意図だが、MMAP handshakeとGodot readerの期待を含むため、保護領域としてプロトコル試験後に判断する。 | writer/reader並行試験、初回frame、map切替、reader停止・遅延、Godot実機 |
| M-055 | 高 | UI MMAPのoctotree点数を空データ時にも確定書込み | SHI `d9ba78b`、`argus_synchro_lib/cpp/src/ui_interface/ui_interface.cpp` | vendorは点数をentity loop内で書くため、全entityが空だと予約領域へ0を書かず、値が残る可能性がある。SHI同様に合計点数の書込みをloop外へ移す。 | 空octotree、1/複数entity、前frame非空→現frame空、MMAP読戻し |
| M-056 | 中 | UI MMAP詳細ログのdebug化 | SHI `d9ba78b`、`argus_synchro_lib/cpp/src/ui_interface/ui_interface.cpp` | vendorは座標・画像・点群などフレーム単位の詳細をinfoで大量出力する。SHIは大半をdebugへ下げる。機能変更と混ぜず、運用ログ要件を確認して独立移植する。 | info/debug時のログ量、FPS、障害解析に必要な主要ログの残存 |
| M-057 | 低 | `setup.py`のpackage/extension名整合 | SHI `7f34907`、`argus_synchro_lib/setup.py` | vendorのlegacy `setup()`はpackageとextensionを`octotree`とする一方、CMake出力名と`pyproject.toml`は`argus_synchro_lib`。現行`make install`は成功済みだが、setup.py直接buildやwheel作成経路では不整合になり得る。利用経路を確認して修正する。 | `pip wheel`、editable/install、生成so名、`import argus_synchro_lib.controller` |

### 2.1 `argus_synchro_lib`監査結果

生成物の`build/`、`install/`、egg-infoを除いて、C++、Python binding、CMake、Conan、package metadataを比較した。

- Python bindingソース、controller、error mmap writer、collision interfaceは両側で同一だった。
- `CMakeUserPresets.json`、CMake package template、Conan profile等の差は実行bitのみで、内容差はなかった。
- ConanのSBOM・dependency reportは実質内容が同じで、改行・生成表現の差だったため移植候補にしない。
- `pyproject.toml`はvendorのversion `2026.8.25`がSHIの`2026.5.29`より新しいためvendorを維持する。
- Eigen `calc_cdist_min()`はvendorが入力をRowMajorへコピーしてKD-treeを構築する実装、SHIがColumnMajorを直接渡す実装である。vendor初期版に含まれる安全側の差分としてvendorを維持し、SHIへ戻さない。
- `ClsMMap.cpp`、`ui_interface.cpp`、`pcd.h`、`setup.py`には実質差があり、M-049とM-054～M-057へ分割した。

## 3. 今回候補にしなかった差分

- `b64f6f9` のCAN設定変更は校正モードの `File_Input` と開始frameを参照する変更であり、校正統合へ含める。通常運転のファイル入力ループはM-007、CAN decoder/I/OはM-016で統合済み。
- `834690d` のLiDARファイル欠損時終了は、現在のM-003 `FILE_IO_ERROR` と再送出経路で置き換え済み。
- `7f34907` のC++ controller、error mmap writer、collision interfaceはvendorと同一内容だった。
- `2283a0a` のAppDir desktop/iconはvendorに存在し、desktop内容も同一だった。
- `manifest.json` はSHIのGodotテンプレートでは参照されるが、vendorの現行UIテンプレート・scriptには参照がないため、現在は移植しない。
- SHI `settings.ini` のデータパス、開始・終了frame、蓄積frame数などはローカル運用値であり、一括移植しない。
- `IsOld` は実機decoder選択には不要だが、ファイル入力CSVの `o_msg` / `n_msg` 選択に使用中のため維持する。
- SHIの負荷低減閾値変更、C++点群上限、モデル既定値は相互に性能へ影響するため、コミット `2283a0a` や `9d5c72f` をそのまま取り込まない。

## 4. 推奨実施順

1. M-048: Python内で閉じる蓄積deque上限保証
2. M-047: TensorRT堅牢化を入力名、cache分離、provider fallbackの小単位で実施
3. M-050: MID360復号だけをベクトル化し、既存診断クロック契約を維持
4. M-049: 40,000点化を実機性能測定込みで判断
5. M-051: 新YOLOモデルの機種別評価後に既定値を判断
6. M-052: SCX3500表示側の参照仕様を確認後に資産追加
7. M-053: M-049の結果を前提に閾値を調整
8. M-054: Godot readerを含むMMAP handshake試験後に判断
9. M-055: 空octotreeの再現テストを先に追加して局所修正
10. M-056: ログ量を測定して独立変更
11. M-057: legacy setup経路の利用有無を確認して修正

各候補は個別の変更・テスト単位とし、SHIコミット全体のcherry-pickやファイル上書きは行わない。