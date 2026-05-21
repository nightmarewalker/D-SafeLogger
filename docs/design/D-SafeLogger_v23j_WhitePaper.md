<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2026 D-SafeLogger contributors
-->

# D-SafeLogger v23j アーキテクチャ分析ホワイトペーパー

> Python 標準ライブラリ `logging` 互換ロギング基盤の仕様・設計思想・性能・エコシステム上の位置に関する客観的言語化と評価

---

## 文書情報

| 項目 | 内容 |
|---|---|
| 文書バージョン | 1.0 |
| 発行日 | 2026-05-09 |
| 対象ライブラリ | **D-SafeLogger v23j** |
| pyproject バージョン | `0.2.1` |
| import name | `dsafelogger` |
| distribution name | `d-safelogger` |
| ライセンス | Apache License 2.0 |
| 対応 Python | `>=3.11`（CPython 3.13 / 3.14 free-threaded build を含む） |
| 対応 OS | Windows / macOS / Linux |
| ランタイム依存 | **なし**（標準ライブラリのみ） |
| 一次ソース確認日 | 2026-05-09 |

---

## 概要 (Executive Summary)

本ホワイトペーパーは、Python 標準ライブラリ `logging` の上に構築されたロギング基盤 **D-SafeLogger v23j** 時点の現行アーキテクチャを対象とし、その仕様・設計思想・機能・性能・エコシステム上の位置を整理・評価したものである。

### プロダクトの位置づけ

D-SafeLogger は **「stdlib `logging` を置き換えず拡張する、ランタイム外部依存ゼロの本番運用を意識したロギング基盤」** である。`logging.setLoggerClass()` による drop-in 拡張を採り、既存の `logging.getLogger()` / `logger.info()` 呼び出しサイトを変更せず、SQLAlchemy / Django 等の第三者 `logging` ベースライブラリも改修なしで本ライブラリの設定フローに参加する。

### アーキテクチャ上の主要軸

| 軸 | 設計内容 |
|---|---|
| **3 層設定パイプライン** | 環境変数 > INI/dict > 引数の厳格マージ + Fail-Fast |
| **Capture / Transport / Sink 3 層** | single/multiprocess を貫いて責務境界不変 |
| **Append-Only ルーティング** | active log file を rename/truncate せず、書き込み時点で出力先を切り替える。Windows の rename 失敗と POSIX 系の旧FD継続書き込み問題を回避（9 routing modes） |
| **正式 multiprocess API（`dsafelogger.mp`）** | parent-side Writer + worker attach/detach + control plane ACK |
| **分類済み配送状態 counters** | `accepted` / `delivered` / `KnownRejected` / `KnownDropped` / `UnexplainedLost` / `partial_delivered` / `overload_shed` + `writer_reject` 6 内訳 |
| **完全性検証** | SHA-256 サイドカー（`sha256sum -c` 互換）+ マニフェスト |
| **Vendor-Agnostic コア** | OpenTelemetry 等のベンダー import なし |
| **No-Copy Snapshot** | `MappingProxyType` ベースの O(1) 参照渡し |
| **絶対防衛線 4 定数** | 3.0s / 5.0s / 10.0s / queue maxsize warning 100000 |
| **PEP 703 free-threaded 対応** | GIL 非依存の明示ロック化を仕様で宣言 |

### 公開ベンチマーク観測値

公開ベンチマーク（`BENCHMARK.md` および `benchmarks/summary/manifest.json` 選定セッション）に記載された確定値:

- **単一プロセス async**（Python 3.14 / GIL=on）: text **51,554 msg/s, p50 16.7 µs** / JSON **52,081 msg/s, p50 16.7 µs**
- **単一プロセス cell-winners**: throughput 1 位 **8/16**、p50 1 位 **12/16**
- **マルチプロセス integrity**: 3 backend × 96 raw runs で missing=0 / duplicates=0 / JSON parse failure=0 / route mismatch=0
- **マルチプロセス resilience**: D-SafeLogger は 12/12 行で配送状態をベンチマーク定義に基づき分類・説明（stdlib / loguru は `observability_gap`）

### エコシステム上の位置

主要 8 プロジェクト（stdlib `logging` / Loguru / structlog / picologging / Eliot / Logbook / logfire / OpenTelemetry SDK）の一次ソース比較（2026-05-09 時点）から、本一次ソース調査範囲では次の組み合わせを同時に満たす Python ライブラリは観測されなかった:

> **「stdlib 拡張型 × ピュア Python × ランタイム依存ゼロ × append-only routing × 完全性検証 × parent-side multiprocess Writer × 分類済み配送状態 counters × free-threaded 明示対応 × 3 層設定パイプライン」**

これは特定の運用要件（Windows サーバ運用 / 監査・コンプライアンス / マルチプロセス監査 / サプライチェーンセキュリティ重視 / Free-threaded 移行検討 / stdlib コンサバ）への明確に差別化された選択肢として位置づけられる。

### 本書のスコープ

本ホワイトペーパーは以下のスコープに従って記述されている:

1. **対象は v23j 時点の現行アーキテクチャ**: 改善提案・課題管理・将来ロードマップは扱わない。issue tracker / roadmap の代替ではない。
2. **競合情報の取扱**: 公開一次ソースで確認できる事実を優先し、確認できない事項は断定しない。
3. **OSS 公開時の位置づけ整理**: 採用率・人気・反響の予測は行わず、公開資料から確認できる設計上の位置づけに限定する。
4. **参照ポリシー**: 公開設計書（`docs/design/`）を一次設計書として使用。private planning materials は参照対象から除外する。

---

## 目次

### [第 1 章 設計思想とコンセプト](#第-1-章-設計思想とコンセプト)
- 1.1 D-SafeLogger とは何か
- 1.2 設計原則（design philosophy）
- 1.3 アーキテクチャ的優位点の総覧
- 1.4 特徴と差別化
- 1.5 設計上の特徴
- 1.6 一次資料から見た位置づけ
- 1.7 本章のまとめ

### [第 2 章 仕様と設計](#第-2-章-仕様と設計)
- 2.1 全体アーキテクチャ
- 2.2 公開 API 構造
- 2.3 3 層設定管理パイプライン
- 2.4 Capture 層
- 2.5 Transport 層
- 2.6 Sink 層
- 2.7 ファイル完全性検証
- 2.8 マルチプロセス対応（`dsafelogger.mp`）
- 2.9 過負荷時ポリシー（Overload Policy）と Survival-first 方針
- 2.10 並行安全性と free-threaded 対応
- 2.11 設計上の特徴（仕様レベル）
- 2.12 仕様・設計の整理
- 2.13 本章のまとめ

### [第 3 章 ユーザビリティ](#第-3-章-ユーザビリティ)
- 3.1 公開 API のサーフェス
- 3.2 最小コードからのスケール
- 3.3 3 層設定パイプラインの運用
- 3.4 INI / dict 設定
- 3.5 examples 17 種の構成
- 3.6 CLI ツール `dsafelogger`
- 3.7 stdlib `logging` からの移行
- 3.8 multiprocess 利用
- 3.9 third-party との共存
- 3.10 ドキュメント体系
- 3.11 設計書 §5.6 の Zero Dependency 一貫性
- 3.12 設計上の特徴（ユーザビリティレベル）
- 3.13 ユーザビリティ観点の整理
- 3.14 本章のまとめ

### [第 4 章 セキュリティ](#第-4-章-セキュリティ)
- 4.1 Safe の 6 軸とセキュリティの位置づけ
- 4.2 サプライチェーンセキュリティ（Zero Dependency）
- 4.3 起動時セキュリティ（Startup Safety / Fail-Fast）
- 4.4 機密情報マスキング
- 4.5 ファイル完全性検証
- 4.6 並行・マルチプロセス安全性
- 4.7 失敗の可視化（Failure Observability）
- 4.8 ロギング系の悪用パスの遮断
- 4.9 第三者ライブラリとの境界
- 4.10 設計上の特徴（セキュリティレベル）
- 4.11 セキュリティ観点の整理
- 4.12 本章のまとめ

### [第 5 章 機能別詳細分析](#第-5-章-機能別詳細分析)
- 5.0 章の構成
- 5.1 Append-Only ルーティング機能群
- 5.2 世代管理（purge / archive）と自己修復性
- 5.3 external rotation との共存と `ReopenLogFiles()`
- 5.4 ファイル完全性検証（SHA-256 / マニフェスト）
- 5.5 構造化ログと Formatter 個別指定
- 5.6 コンテキスト管理（contextualize / FrozenContext）
- 5.7 カスタムログレベル（register_level）
- 5.8 コンソールカラー出力
- 5.9 async transport（QueueTransport）
- 5.10 5 状態ライフサイクル
- 5.11 `dsafelogger.mp` Writer runtime
- 5.12 `dsafelogger.mp` log plane / control plane
- 5.13 `dsafelogger.mp` 配送状態 counters
- 5.14 `dsafelogger.mp` bounded shutdown と flush 戦略
- 5.15 TrackedQueue（v23h）
- 5.16 環境変数による運用制御
- 5.17 INI / dict 設定の精緻
- 5.18 CLI ツール `dsafelogger`
- 5.19 free-threaded 対応
- 5.20 diagnose（変数自動展開）
- 5.21 sens_kws マスキング
- 5.22 機能別の整理
- 5.23 本章のまとめ

### [第 6 章 競合プロジェクト比較](#第-6-章-競合プロジェクト比較)
- 6.1 本章のスコープと方針
- 6.2 比較対象プロジェクトの一次ソース確認
- 6.3 軸 1: ランタイム外部依存
- 6.4 軸 2: stdlib `logging` との関係
- 6.5 軸 3: ファイル出力・ルーティング
- 6.6 軸 4: 構造化ログ・コンテキスト管理
- 6.7 軸 5: マルチプロセス対応
- 6.8 軸 6: 完全性検証 / 監査機能
- 6.9 軸 7: free-threaded Python（PEP 703）対応
- 6.10 軸 8: 配送状態の観測性
- 6.11 軸 9: 設定管理パイプライン
- 6.12 ライブラリ別の最新状況サマリ
- 6.13 競合エコシステムの構図
- 6.14 競合比較の整理
- 6.15 本章のまとめ

### [第 7 章 OSS 公開時の位置づけ](#第-7-章-oss-公開時の位置づけ)
- 7.1 本章のスコープと方針
- 7.2 セグメント 1: サプライチェーンセキュリティ重視層
- 7.3 セグメント 2: Windows サーバ運用層
- 7.4 セグメント 3: 監査・コンプライアンス層
- 7.5 セグメント 4: Free-threaded 移行検討層
- 7.6 セグメント 5: stdlib コンサバ層
- 7.7 セグメント 6: multiprocess 監査層
- 7.8 セグメント間の重複と交差
- 7.9 国内 vs 海外のエコシステム差
- 7.10 OSS 配布上の技術的構造
- 7.11 位置づけの整理
- 7.12 OSS 公開時の位置づけの整理
- 7.13 本章のまとめ

### [第 8 章 総合評価](#第-8-章-総合評価)
- 8.1 本章のスコープ
- 8.2 観測事実の集約
- 8.3 アーキテクチャ的価値の整理
- 8.4 設計姿勢の一貫性
- 8.5 エコシステム上の位置
- 8.6 ベンチマーク観測事実の集約
- 8.7 ドキュメント・運用構造の集約
- 8.8 客観的位置づけ
- 8.9 本章のまとめ
- 8.10 本レポートの限界

### [付録 A. 参照ポリシー](#付録-a-参照ポリシー)
### [付録 B. 一次ソース一覧（2026-05-09 時点）](#付録-b-一次ソース一覧2026-05-09-時点)
### [付録 C. 用語集](#付録-c-用語集)
### [付録 D. 文書作成について](#付録-d-文書作成について)

---

## 凡例

本ホワイトペーパーで使用する記法・略号:

| 記法 | 意味 |
|---|---|
| `§N.M` | 本ホワイトペーパー内の章節参照（例: §2.8 はマルチプロセス対応） |
| 設計書 §N | `docs/design/D_SafeLogger_Specification_v23j_full.md` の章 |
| 詳細設計書 §N | `docs/design/D-SafeLogger_DetailedDesign_v23j.md` の章 |
| ◎ | primary strength / 設計の中心 |
| ○ | supported out of the box |
| △ | 公式の設定・アダプターで限定的に対応 |
| — | ライブラリ機能として未提供 |
| ※n | 条件・範囲の説明あり |
| out | 責務範囲外（未提供ではなく意図的に範囲外） |

---

## 第 1 章 設計思想とコンセプト

### 1.1 D-SafeLogger とは何か

#### 1.1.1 一文定義

D-SafeLogger は、**Python 標準ライブラリ `logging` の上に構築された、ランタイム外部依存ゼロの本番運用を意識したロギング基盤**である。

- import 名: `dsafelogger`
- distribution 名: `d-safelogger`
- ライセンス: Apache License 2.0
- 対象 Python: 3.11 以上（CPython 3.13 以上の **free-threaded build** を設計対象に含む）
- 対象 OS: Windows / macOS / Linux
- ランタイム依存: なし（Python 標準ライブラリのみ）
- 型情報: `py.typed` を同梱。CI では `mypy` / `pyright` / typing smoke test / `pyright --verifytypes` 100% public type completeness gate を検証する

#### 1.1.2 ポジショニング

公式設計書 §1 では、本モジュールの位置づけを次のように規定している。

> 本モジュールは、`D` によって提供される様々な Python エコシステム（D-Settings, DPySide, D-MessageRouter 等）の全プロジェクトで共通利用する、軽量・高速・高機能なロギング基盤である。**単体で OSS として公開する前提だが、広く普及させる目的よりも、「D エコシステム」の共通基盤として運用することを最優先とする**。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §1）

これは、ライブラリの設計判断が「広範な人気獲得」よりも「D エコシステム内基盤としての堅牢性・運用整合性」に優位を置くことを意味する。設計判断の優先順位が公開時点から明示されている点で、汎用的フロントエンドライブラリ（Loguru / structlog 等）とはポジショニングが異なる。

加えて、設計書は本ライブラリの絶対条件として以下を掲げている。

- **標準 logging の呼び出しモデルを維持すること**を絶対条件とする。
- それを満たした上で、**サードパーティ製ライブラリとは異なる方向性の診断・運用制御能力**を提供する。
- **Windows 環境で発生しやすいアクティブログファイルの rename 失敗を回避する堅牢性**を提供する。
- 上記すべてを **外部依存ゼロ** で実現する。

「Safe」というプロダクト名接頭辞は、これらが組み合わさった「安全性・堅牢性」の概念を象徴する語として、設計書 §1 で明示的に意味づけられている。

#### 1.1.3 公開ナラティブにおける Safe の 6 軸

`README.md` Overview 節は、Safe の概念を 6 つの運用次元として整理している（要旨）。

| 軸 | 公開ナラティブ要旨（README） |
|---|---|
| **Startup safety** | 不正設定・矛盾オプション・書き込み不能な出力先は **setup 時に失敗**する。壊れたロギング構成のままアプリケーションを実運用に投入させない |
| **File safety** | ルーティング層は active log file を rename/truncate せず、**次の出力先を開くことで切り替える**。Windows でアクティブログが rename できない典型障害に加え、POSIX 系で rename 成功後も writer が旧FDへ書き続けるログ世代管理上の不整合を避け、SHA-256 サイドカーと任意マニフェストにより事後検証可能 |
| **Record / context safety** | request ID / user ID / job ID 等のコンテキストを **producer 側で hand-off 時に snapshot** する。listener と Writer は live `contextvars` に依存しない。センシティブキーワードのマスキングは Writer 側で適用 |
| **Operational control** | 環境変数で診断・ルーティング・ハッシュ・ログレベル・queue/timeout を **再ビルドや編集なしに上書き**できる |
| **Concurrency / multiprocess safety** | multiprocess worker は共有ログファイルを**直接開かない**。parent 側 Writer が sink を所有し、IPC 経由で record を受理。bounded queue と explicit timeout により host process に無制限待機を発生させない |
| **Failure observability** | 配送失敗を `KnownRejected` / `KnownDropped` / `UnexplainedLost` として**分類**する。ログ欠損を「ファイル上の見えない隙間」ではなく、counters と shutdown summary として **describable** にする |

これらの 6 軸は、後続章（§4 セキュリティ、§5 機能別詳細）で個別の機能設計と直接結びつく。

---

### 1.2 設計原則（design philosophy）

公開設計書 §1 は、本プロジェクトの設計判断を貫く 5 つの原則を明文化している。

#### 1.2.1 Reroute, don't rotate

ファイルの rename / truncate を避け、**append-only のまま routing 境界で出力先を切り替える**。

標準 `logging.handlers.RotatingFileHandler` 系は、active log file の rename を前提とする。Windows では、active handle を保持したファイルの rename / 削除が `PermissionError` を引き起こすことが典型的であり、ローテーション操作そのものが失敗として表面化しやすい。

一方、POSIX 系では open 中のファイルを rename しても、既存 file descriptor は旧実体を指し続ける。この性質は atomic replace や設定ファイル更新では有用である。しかし active log stream の世代管理では、rename 操作が成功したことと、writer が期待した新世代へ移ったことは同一ではない。外部 rotator が `app.log` を `app.log.1` に rename し、新しい `app.log` を作成しても、writer が旧FDを保持していればログは旧世代へ流れ続ける。

したがって、D-SafeLogger が避けるのは Windows 固有の rename 失敗だけではない。active log file を後から動かし、その後の signal / reopen 成功にログ世代管理を委ねる設計そのものを避けている。

D-SafeLogger はこの操作自体を採らず、routing 境界で **新しいファイル名を append-only に open し、以後の record をそこへ送る**。active file は writer が所有する sink として扱い、close 済みのファイルだけを archive / retention / integrity verification の対象にする。

#### 1.2.1.1 External rotation is coordination, not logging

外部ログローテーションは、Unix 系運用における標準的な手順として扱われることが多い。典型的には、外部プロセスが active log file を rename し、新しいファイルを作成し、アプリケーションへ signal を送り、アプリケーション側で sink を reopen する。

しかし、これは「active file を後から動かす設計」を支える調整処理であり、ログ出力そのものの中核ではない。

ログ出力に必要なのは、各 record について意図した出力先を決め、そこへ append することである。ロギング層が書き込み時点で正しい出力先を決定できるなら、active file の rename、外部プロセスからの signal、reopen 成功への依存は不要になる。

D-SafeLogger の append-only routing は、この調整処理をより精緻に実装するのではなく、調整処理が必要になる前提をログ書き込み経路から外す設計である。

#### 1.2.2 Fail before it breaks

曖昧な欠損よりも、**明示的な counters / warnings / bounded shutdown を優先する**。

- 設定の不整合・書き込み不可・型不正は `ConfigureLogger()` 起動時に例外送出（Fail-Fast）。
- multiprocess の配送失敗は **silent drop ではなく**分類カウンタに計上。
- 通常終了時は `daemon=True` を最終ガードに留め、queue drain → bounded worker join → handler close の順序を明示的に管理する。

#### 1.2.3 Start quick, ship as-is

`ConfigureLogger()` と `GetLogger()` で**最小設定を小さく**保つ。

- 公開 API の入口は 2 関数。最小コードは 3 行。
- 同じ設定セットが、scratch から本番までスケールする（後段の §1.4 INI/dict/env 参照）。

#### 1.2.4 Zero external runtime dependencies

ランタイム依存を構造的に排除する。**開発・ベンチ依存は専用 dependency group に限定**する。

- `pyproject.toml` の依存ゼロは「supply-chain risk gating」を構造的に保証する。
- `dev` / `benchmark` / `optional_integration` の dependency group は**インストール時には不要**。

#### 1.2.5 Be honest about multiprocess behavior

`dsafelogger.mp` は**あらゆる障害下での完全永続化を主張しない**。価値は配送状態を観測可能にすることである。

- `accepted` / `delivered` / `KnownRejected` / `KnownDropped` / `UnexplainedLost` / `partial` の counters と shutdown summary により、異常時のログ欠損を**説明可能な状態**として外部化する。
- この姿勢は `BENCHMARK.md` の「What Not To Claim」節（multiprocess logging が record loss を不可能にすると主張しないこと）にも一貫している。

---

### 1.3 アーキテクチャ的優位点の総覧

公式設計書 §2 は、v23j アーキテクチャ全体を 19 項目の優位点として列挙している。観測可能な事実を整理すると以下のように分類できる。

#### 1.3.1 「依存しない」構造

| 項目 | 設計書の規定 |
|---|---|
| Zero Dependency | 標準ライブラリのみで構成。サプライチェーンリスクをゼロにする |
| Vendor-Agnostic 原則（v20） | コアモジュール（`src/dsafelogger/`）にベンダー固有の import（OpenTelemetry 等）やデータ参照を**一切含めない**。OTel 等のベンダー統合は Formatter 差し込み・`contextualize()` 注入・`examples/` のサンプルとして提供 |
| Free-threaded Python Ready | `_configure_state` / `_active_pipeline` / `_active_workers` / `_custom_levels` 等の共有状態を**明示ロック**で保護。`list` / `dict` の実装依存の原子性に依存しない |

#### 1.3.2 「壊さない」I/O

| 項目 | 設計書の規定 |
|---|---|
| Append-Only ルーティング | active log file を rename/truncate せず、出力先ファイル名を動的に決定する Append-Only モデル。Windows 特有のファイルロック競合による `PermissionError` と、POSIX 系での旧FD継続書き込みによる世代不整合を**構造的に回避**、ファイル操作を O(1) に抑制 |
| Fire-and-Forget 非同期パージ | 世代管理（古いファイルの削除・アーカイブ）は出力先切り替え時のみ使い捨ての別スレッドで実行。Windows のロック等で失敗しても**次回切り替えで自動リトライ**（self-healing） |
| ファイル完全性検証 | 切り替え時に SHA-256 ハッシュを別スレッド生成。`sha256sum -c` 互換のサイドカーとマニフェストにより改竄検知・転送検証・ファイル消失検知 |

#### 1.3.3 「黙って劣化しない」初期化

| 項目 | 設計書の規定 |
|---|---|
| Fail-Fast 初期化検証 | 起動時にディレクトリ作成可否・パーミッション・ディスク容量をテスト。INI の不正値も**サイレントフォールバックせず即座に例外** |
| 安全を担保する環境変数オンリー設定（`diagnose`） | 例外時の `f_locals` 自動展開機能は**環境変数からのみ**有効化可能。INI からも引数からも設定不可（聖域）。コードへの「戻し忘れ」事故を構造的に排除 |
| 並行安全性の強化（v21） | `ConfigureLogger` の `_do_configure()` 全体を `_lifecycle_lock` 保持下で実行。`GetLogger` は `'configuring'` 状態を検出して構造待機。初期化中の中途状態読み取りを並行安全に防止 |

#### 1.3.4 「説明可能にする」観測性

| 項目 | 設計書の規定 |
|---|---|
| Async Mode | `Transport` 抽象（`DirectTransport` / `QueueTransport`）を介した同期・非同期 I/O の統一制御。producer 側で context / 必要時の診断情報を snapshot し、thread 境界を越えても意味論が崩れない hand-off |
| 内部 3 層パイプライン Capture / Transport / Sink | Capture（ログ生成）・Transport（転送）・Sink（出力）の 3 層モデル。logging 互換は Capture 層、routing / hash / manifest / reopen / purge は Sink/Writer 側の責務 |
| Safe Shutdown | 通常終了時は queue drain → bounded worker join → handler close の順序を明示的に管理。`daemon=True` は異常終了時の backstop に限定 |
| 分類済み配送状態（multiprocess） | `accepted` / `delivered` / `KnownRejected` / `KnownDropped` / `UnexplainedLost` の counters と shutdown summary を外部化 |

#### 1.3.5 「拡張するが置き換えない」標準互換

| 項目 | 設計書の規定 |
|---|---|
| Drop-in Replacement | `logging.setLoggerClass()` により標準 `logging.Logger` を継承した独自クラスを返す。SQLAlchemy や Django 等の標準ロギング対応ライブラリへ**ハックなしにシームレスに注入可能** |
| 関心の分離 | 初期設定（Configure）と利用（GetLogger）を明確に分離 |
| 3 層設定管理パイプライン | 環境変数 > INI/dict > 引数の厳格マージ。INI/dict はモジュール別レベル・出力先・ルーティングをセクションとして記述可能 |
| Formatter 個別指定（v20） | `file_fmt` / `console_fmt` でファイル出力とコンソール出力に**個別の Formatter** を指定可能。従来の `fmt` 全体デフォルトとの後方互換を維持 |
| 非破壊 level 表示解決（v21） | レベル略称変換と ANSI カラー付与は表示用 proxy で解決。`record.levelname` は変更しない。`%` / `{}` / `$` の全 style で同一意味論 |

#### 1.3.6 「ローカルで完結する」拡張機能

| 項目 | 設計書の規定 |
|---|---|
| JSONL 構造化ログ | Append-Only アーキテクチャを保ったまま 1 行 1 JSON への切り替え |
| Contextualize | `contextvars` を活用し、特定スコープ内の全ログに識別子を自動付与。スレッド・asyncio タスク間で独立分離 |
| カスタムログレベル | `register_level()` により標準 5 段階に加え任意の数値位置にカスタムレベルを差し込み可能。3 文字略称・ANSI カラー・便利メソッドの一括登録を `ConfigureLogger` 前の単一呼び出しで完結。**ビルトイン 5 段階は不可侵** |
| カラーパレット設定 | `[global]` セクションで `color_{略称}` キーにより ANSI カラーを変更可能。第 2 層（INI/dict）専用 |
| No-Copy Snapshot（v20） | `contextvars.ContextVar[MappingProxyType]` による immutability 保証で async モードの snapshot / hand-off を O(1) 参照渡しに最適化。mutable 値は Fail-Fast で拒否 |
| module-specific path の Transport 完全統合（v21） | `is_async=True` の意味論を root 経路だけでなく module-specific path 経路にも一貫適用 |

---

### 1.4 特徴と差別化

#### 1.4.1 「拡張する」と「置き換える」の設計軸

公開ナラティブ（README "Why D-SafeLogger?" 節）は、本ライブラリの方向性を次のように対比している。

> D-SafeLogger extends the standard logging path rather than replacing it: you keep using `logging.getLogger()` and existing `logger.info()` call sites, and the library adds safe local-file output on top — append-only routing, fail-fast configuration, SHA-256 sidecars, sensitive-data masking, environment-driven operational control, and a parent-side multiprocess Writer.
> （`README.md` "Why D-SafeLogger?" 節より引用）

ここから導かれる差別化は次の 3 点である:

1. **API レベルの差別化なし、設計レベルの差別化のみ**: 既存 `logging.getLogger()` / `logger.info()` の呼び出しサイトはそのまま動作する。
2. **追加機能はファイル出力境界より下**: append-only ルーティング・SHA-256 サイドカー・マスキング・環境変数オーバーライド・parent 側 Writer は、すべて「stdlib `logging` Handler/Formatter の入口より下」で動く。
3. **既存の logging エコシステムが共参加可能**: SQLAlchemy / Django 等が `logging.getLogger()` で取得した logger は、本ライブラリの設定フローに自動的に乗る。

#### 1.4.2 structlog との共存（置換ではない）

README は structlog との関係を明示的に「置換ではなく共存」と規定している。

> If you already use `structlog` as a structured-logging frontend, D-SafeLogger coexists rather than replaces. `structlog` builds the event dictionary; D-SafeLogger handles file output, routing, sidecars, masking, and operational control.
> （`README.md` "Why D-SafeLogger?" 節より引用）

これは **「フロントエンド（イベントの構造化）」と「バックエンド（ファイル出力・整合性・運用制御）」を異なる責務として扱う**設計姿勢の表明である。`examples/16_structlog_coexistence.md` には 2 つの統合パターンが提供されている。

#### 1.4.3 Loguru / structlog 系との設計軸の違い

公開 README に掲載されている Feature Comparison 表（`stdlib logging` / `loguru` / `structlog` / D-SafeLogger）から、各ライブラリの設計上の軸が観測できる。

| 設計軸 | 各ライブラリの位置（README 表より） |
|---|---|
| **stdlib `logging` API 互換** | stdlib ◎ / loguru △※2 / structlog △※3 / D-SafeLogger ◎ |
| **既存 `logger.info()` 呼び出しサイト保持** | stdlib ◎ / loguru △※2 / structlog △※3 / D-SafeLogger ◎ |
| **第三者ライブラリの `logging.getLogger()` 参加** | stdlib ◎ / loguru △※2 / structlog △※3 / D-SafeLogger ◎ |
| **ランタイム外部依存ゼロ** | stdlib ◎ / loguru — / structlog — / D-SafeLogger ◎ |
| **集中設定（handler/formatter wiring 置換）** | stdlib △※1 / loguru ◎ / structlog △※3 / D-SafeLogger ◎ |
| **rename/truncate なし append-only ファイルルーティング** | stdlib —※5 / loguru —※6 / structlog —※3 / D-SafeLogger ◎ |
| **SHA-256 サイドカー / manifest** | stdlib — / loguru — / structlog —※3 / D-SafeLogger ◎ |
| **fail-fast 設定検証** | stdlib △※4 / loguru △※4 / structlog △※4 / D-SafeLogger ◎ |
| **parent 側 Writer によるマルチプロセス出力** | stdlib —※10 / loguru —※9 / structlog —※3 / D-SafeLogger ◎ |
| **配送状態アカウンティング（multiprocess）** | stdlib — / loguru — / structlog — / D-SafeLogger ◎ |

> 凡例: ◎ = primary strength / 設計の中心、○ = supported out of the box、△ = 公式の設定・アダプターで限定的に対応、— = ライブラリ機能として未提供、※n = 条件・範囲の説明あり

この表の注記は、公開 README の Feature Comparison 注記に従う。特に `—※n` は「任意のアプリケーション実装を足しても不可能」という意味ではなく、そのライブラリ自身の組み込み責務ではないことを示す。Loguru の rotation / retention / compression と `enqueue=True` は標準機能として認めるが、append-only ルーティング、parent 側 Writer 所有、配送状態アカウンティングとは等価ではない。structlog は構造化 logging のフロントエンドとして扱い、ファイル lifecycle、完全性 sidecar、multiprocess sink semantics は backend またはアプリケーション側の責務として扱う。

差別化軸として読み取れるのは次の組み合わせである:

- **stdlib 互換 ◎ × 外部依存ゼロ ◎** の両立: stdlib 自身を除き、表内で D-SafeLogger のみが両者で ◎ を持つ。
- **append-only ルーティング ◎ / SHA-256 サイドカー ◎ / fail-fast 設定検証 ◎ / parent 側 multiprocess Writer ◎ / 配送状態アカウンティング ◎** の **5 軸が同時に ◎**: README 表内の他 3 ライブラリは、この組み合わせを組み込み設計の中心としては扱っていない。

これらは「Loguru / structlog のように logging を再設計するのではなく、logging を維持しながら出力境界より下を強化する」設計軸の帰結である。

#### 1.4.4 非目標（non-goals）

README の "Compatibility / Non-goals" 節は、本ライブラリの**意図しない領域**を明示している。

> D-SafeLogger is not a log shipper, metrics pipeline, distributed tracing backend, or access-control system. Use tools such as Fluent Bit, Vector, Filebeat, OpenTelemetry Collector, or a tracing backend for those roles.
> （`README.md` "Compatibility / Non-goals" 節より引用）

これは「アプリケーションプロセス内のロギング基盤」という責務範囲を、observability スタック全体から明示的に切り分けるための境界線である。

---

### 1.5 設計上の特徴

公開設計書および公開ナラティブから、設計判断の通底する姿勢として以下が観測される。これらは本レポートの後続章で個別機能の評価軸として再利用する。

#### 1.5.1 「事故パターンを構造的に成立させない」

`diagnose` を環境変数のみに限定する規定（設計書 §4.4）は、その典型である。

- コードに `diagnose=True` と書ける手段が存在しない → 「コードに書いて戻し忘れる」事故パターンが**通常の利用経路では成立しない**。
- INI もバージョン管理に乗るリスクがあるため除外 → 「git commit で本番混入」事故パターンも遮断。
- 本番有効化はインフラ層（環境変数）の明示操作に限定。

同様の姿勢は次にも観測される:

- `_lifecycle_lock` 配下での `_do_configure()` 実行（§2 並行安全性の強化）→ 初期化中の半完了状態の読み取りを構造的に排除。
- mutable 値の `contextualize()` への TypeError/ValueError → 共有 snapshot に対する意図しない副作用を**開発時に確実に検知**。
- `ConfigureLogger` の初期化失敗時 Fail-Fast → 「設定が反映されていないのに動いて見える」障害パターンを排除。

#### 1.5.2 「観測できない欠損を作らない」

multiprocess 配送の `KnownRejected` / `KnownDropped` / `UnexplainedLost` 分類（§1.2.5、§1.3.4）は、その代表である。

- 「配送失敗を起こさない」ではなく「配送失敗を**説明可能にする**」ことを設計目標としている。
- これは `BENCHMARK.md` の "What Not To Claim" 節での「multiprocess logging が record loss を不可能にすると主張しない」「sink outage / worker crash / hard process termination が impossible になると主張しない」と一貫している。

#### 1.5.3 「標準のセマンティクスを壊さない」

非破壊 level 表示解決（§1.3.5、v21 改訂）は、その典型である。

- レベル略称表示のために `record.levelname` を改変しない。
- `copy.copy(record)` や try/finally による一時差し替えにも依存しない。
- 表示用 proxy / 局所マッピングで解決し、共有 `LogRecord` の意味論を保つ。
- `logging.Formatter` が許容する `%` / `{}` / `$` の全 style で同一の意味論を保証。

これは「stdlib `logging` の上に build された他ライブラリ・他コードが、本ライブラリの存在で前提を崩されないこと」を構造的に保証する姿勢である。

#### 1.5.4 「拡張は ConfigureLogger 前に閉じる」

`register_level()` の規定（§2、§1.3.6）は、その例である。

- カスタムログレベルの登録は **`ConfigureLogger()` の前に**単一呼び出しで完結。
- 3 層設定管理パイプライン（env > INI > 引数）の評価より前に確定するため、レベル名解決の順序が**初期化フロー上一意**に決まる。
- ビルトイン 5 段階は不可侵として保護される。

これは「拡張ポイントを設けるが、初期化境界を越えて動的変更を許さない」という制限の置き方である。

---

### 1.6 一次資料から見た位置づけ

本章で確認した資料から、v23j 時点の設計の到達点として次のように整理できる。

1. **位置づけは「stdlib `logging` の拡張」であり「再設計」ではない**: drop-in 拡張・既存呼び出しサイト保持・第三者 logging ライブラリの共参加が同時に ◎ である構成は、README Feature Comparison 表内では D-SafeLogger と stdlib `logging` のみが両立している。
2. **依存ゼロは「特徴」ではなく「絶対条件」として規定されている**: 設計書 §1 が「外部依存ゼロで実現する」と絶対条件として明記し、§2 で Vendor-Agnostic 原則をコアモジュールから OTel 等のベンダー import を排除する形で具体化している。これは個別機能の判断ではなく、ライブラリ全体の整合制約として運用されている。
3. **「Safe」は単一概念ではなく 6 軸の運用次元として展開されている**: README の Overview 節は startup safety / file safety / record・context safety / operational control / concurrency・multiprocess safety / failure observability の 6 軸を明示し、各軸が後続の個別機能設計に対応する。
4. **設計書 §2 の 19 項目は「依存しない／壊さない／黙って劣化しない／説明可能にする／拡張するが置き換えない／ローカルで完結する」の 6 群に整理可能**: 表面的に分散して見える 19 個の優位点は、§1.3.1〜§1.3.6 のように一貫した設計姿勢から導かれる。
5. **multiprocess 機能の主張は raw throughput ではなく観測性に置かれている**: `BENCHMARK.md` および設計書 §2 ともに、`dsafelogger.mp` の価値を Writer-owned sinks と分類済み配送状態の観測可能性として記述しており、raw throughput では先行を主張していない。
6. **拡張は初期化境界の前に閉じる**: `register_level()` を `ConfigureLogger` 前に限定し、`diagnose` を環境変数限定とし、INI 設定値を Fail-Fast 検証する一連の規定は、初期化境界を越える動的変更を構造的に許さない設計判断として一貫している。
7. **structlog / Loguru との関係は競合ではなく責務分離**: README "Why D-SafeLogger?" 節および Feature Comparison 表は、stdlib 互換 × 外部依存ゼロ × append-only ルーティング × SHA-256 サイドカー × parent 側 multiprocess Writer の組み合わせを D-SafeLogger 固有の軸として位置づけており、structlog の構造化フロントエンド・Loguru の DX 最適化とは設計軸が交差しない。

---

### 1.7 本章のまとめ

D-SafeLogger v23j の設計思想は、次の 3 つに集約される:

1. **「拡張する。置き換えない」**: stdlib `logging` の API・呼び出しサイト・第三者統合を維持したまま、ファイル出力境界より下で safety を強化する。
2. **「依存ゼロ。聖域あり。」**: ランタイム外部依存・ベンダー固有 import をコアから排除し、`diagnose` 等の事故誘発設定を構造的に隔離する。
3. **「失敗を不可能にしない。説明可能にする。」**: 配送失敗・shutdown 異常・初期化矛盾を黙って劣化させず、counters / 例外 / shutdown summary によって外部化する。

これらの思想は次章「2. 仕様と設計」で具体的アーキテクチャ（3 層設定パイプライン・Capture/Transport/Sink・Append-Only ルーティング・`dsafelogger.mp` Writer）として実装される。

---

> **本章の主な参照資料**: `docs/design/D_SafeLogger_Specification_v23j_full.md` §1, §2 / `README.md` Overview, "Why D-SafeLogger?", Feature Comparison, Compatibility/Non-goals 節 / `README_ja.md` 同節 / `LICENSE` / `pyproject.toml`
> 本書は現行 v23j アーキテクチャの説明と評価を目的とし、改善提案・課題管理・将来ロードマップは扱わない。

## 第 2 章 仕様と設計

### 2.1 全体アーキテクチャ

#### 2.1.1 物理モジュール構成

詳細設計書 §1 が定義する v23j のモジュール構成は次の通り（パッケージ名 `dsafelogger`）。

```text
dsafelogger/
  __init__.py          # single-process 公開 API (ConfigureLogger, GetLogger, register_level, ReopenLogFiles)
  _logger.py           # DSafeLogger クラス（logging.Logger 拡張）
  _handler.py          # AppendOnlyFileHandler
  _async.py            # DSafeQueueHandler / DSafeQueueListener / safe shutdown
  _formatter.py        # DSafeFormatter, DiagnosticFormatter, StructuredFormatter
  _writer_formatter.py # Writer runtime で使用する formatter spec 解決 helper
  _color.py            # ColorStreamHandler, ANSI カラーマッピング, Windows VT100 有効化
  _routing.py          # RoutingStrategy 群（ファイル名決定ロジック）
  _sink.py             # FileSink / ConsoleSink / SinkGroup（writer-side sink graph の中心抽象）
  _purge.py            # PurgeWorker（削除）/ ArchiveWorker（ZIP 圧縮）
  _transport.py        # single-process Transport 抽象（DirectTransport / QueueTransport）
  _pipeline.py         # single-process ResolvedConfig / PipelineBuilder / Pipeline
  _context.py          # contextvars ベースのコンテキスト管理（FrozenContext）
  _levels.py           # カスタムログレベル登録・管理
  _integrity.py        # 完全性検証（compute_sha256, write_sidecar, append_manifest, HashWorker）
  _env_parser.py       # 環境変数パーサ
  _ini_loader.py       # INI ファイルローダー
  _constants.py        # 定数定義
  _validator.py        # Fail-Fast パーミッション・ディスク容量検証
  _cli.py              # dsafelogger CLI エントリポイント
  mp/
    __init__.py        # multiprocess 公開 API
  _mp_protocol.py      # BootstrapContext / LogEvent / ControlRequest / ControlAck
  _mp_attach.py        # AttachCurrentProcess / DetachCurrentProcess / GetWorkerInitializer
  _mp_runtime.py       # Writer runtime / active client registry / shutdown / reopen / counters
  _mp_control.py       # control plane request/ack helpers
  _mp_queue.py         # TrackedQueue（log plane 用）
```

各モジュールは `_` で始まる private プレフィックスにより、公開 API の入口を `__init__.py` と `mp/__init__.py` の 2 ファイルに局在化させる構造である。

#### 2.1.2 内部 3 層パイプライン: Capture / Transport / Sink

設計書 §11.3 と §2 の規定により、本ライブラリの内部アーキテクチャは Capture（ログ生成）／ Transport（転送）／ Sink（出力）の 3 層に明示分離されている。

| 層 | single-process | multiprocess |
|---|---|---|
| **Capture** | `DSafeLogger` / `logging.setLoggerClass()` / `contextualize()` / `diagnose` snapshot / route 解決 | 同左（client 側） |
| **Transport** | `DirectTransport` / `QueueTransport` | client 側 process-local async queue（必要時）+ log plane `multiprocessing.Queue` への hand-off |
| **Sink / Runtime** | `FileSink` / `ConsoleSink` / routing / hash / manifest / reopen | Writer runtime 内に集約: routing / file open/close / hash / manifest / archive / purge / reopen / shutdown / control plane |

設計書 §11.3 は次の境界規定を明記している。

> multiprocess 版でも `logging` 互換は Capture 層の責務であり、Writer 側で `LogRecord` の Capture 意味論（logger 階層評価、`propagate` 判定、level 判定、`f_locals` 収集）を再実行してはならない。Writer 側は `LogEvent` を受け取り、route に従って sink 群へ dispatch するだけである。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.3）

これは「single-process と multiprocess の差分は Transport 境界のみであり、Capture / Sink の責務境界は変えない」という設計姿勢の明文化である。

#### 2.1.3 v23 系の Writer 不変条件

設計書 §12.1 は v23 系で崩さない不変条件を 9 項目で固定している。

| 項目 | 不変条件 |
|---|---|
| Writer ownership | file sink / routing / hash / manifest / archive / purge / reopen は Writer が一元所有 |
| Writer drain | Writer log plane は **single serial drain** を基本とする |
| Writer write | file への write は **O_APPEND またはそれと等価な append-only 操作**を維持 |
| Writer 並列化 | v23 系の改善対象に含めない |
| file write | 同一 log family / route / file への並列 write を行わない |
| append-only routing | rename/truncate に依存しない routing 方針を維持 |
| Capture / Transport / Sink | 3 層分離を維持し、責務を混在させない |
| logging 互換 | `logging.setLoggerClass()` による Drop-in Replacement を維持 |
| Zero dependency | 外部依存を追加せず、標準ライブラリのみを使用 |
| fail-safe | silent loss / silent hang / silent fallback を避ける |

設計書は併せて § 12.2 で v23 系で**やらないこと**も明示する: Writer 並列化／ flush 契約弱体化／ append-only 意味論変更／ benchmark 駆動の unsafe optimization ／公開 JSON schema の破壊的変更／ silent drop / fallback。**改善方向の境界線そのものが仕様**として宣言されている。

---

### 2.2 公開 API 構造

設計書 §10 が公開 API を列挙する。single-process 版（`dsafelogger`）と multiprocess 版（`dsafelogger.mp`）は **入口 namespace を分離**し、関数名のみ `ConfigureLogger` / `GetLogger` / `ReopenLogFiles` を共有する。

#### 2.2.1 single-process API（`dsafelogger`）

| API | 種別 | 主要契約 |
|---|---|---|
| `ConfigureLogger(default_level, log_path, pg_name, env_prefix, config_file, config_dict, is_async, backup_count, archive_mode, routing_mode, interval, max_bytes, max_lines, max_count, suffix_digits, console_out, structured, fmt, file_fmt, console_fmt, datefmt, enable_hash, manifest_path, sens_kws, sens_kws_replace) -> None` | 起動時 1 回 | 5 状態冪等管理。`unconfigured` / `auto` / `explicit` / `configuring` / `shutting_down`。auto-fire を許容（`GetLogger()` 先行時の暗黙初期化） |
| `GetLogger(name='') -> logging.Logger` | 任意回 | 標準 `logging.getLogger()` をラップ。ルートロガー取得は `name=''`。未初期化時は **auto-fire** によるデフォルト初期化を許容 |
| `register_level(name, value, abbreviation, color='') -> None` | 起動前 0+ 回 | `ConfigureLogger()` の **前に**呼ぶ。`shutting_down` 中は `RuntimeError` |
| `ReopenLogFiles() -> None` | 任意回 | `routing_mode='none'` でない sink が active なら `ValueError`。external rotation 共存専用 |

#### 2.2.2 multiprocess API（`dsafelogger.mp`）

| API | 種別 | 主要契約 |
|---|---|---|
| `ConfigureLogger(...) -> object` | 起動時 1 回 | single-process 引数に加え、`worker_model='process'\|'pool'\|'executor'`, `mp_context`, `ipc_log_timeout=0.5`, `ipc_log_queue_maxsize`, `ipc_client_queue_maxsize`, `writer_flush_batch` を持つ。**opaque で picklable な `ctx` を返す** |
| `AttachCurrentProcess(ctx) -> None` | 各 worker 起動時 | `ctx` 検証 → `ATTACH` request → `protocol_version` / `registry_hash` 照合 → `logging.setLoggerClass()` の process-local 適用 |
| `DetachCurrentProcess() -> None` | shutdown 時 | `DETACH` control request 送信 → 成功 ACK 後に process-local state 破棄 |
| `GetLogger(name='') -> logging.Logger` | 任意回 | **auto-fire しない**。未 attach 時は `RuntimeError`（attach 忘れを Fail-Fast 検知） |
| `GetWorkerInitializer(ctx) -> tuple[Callable, tuple]` | Pool/Executor 連携 | `Pool(initializer=..., initargs=...)` / `ProcessPoolExecutor(initializer=..., initargs=...)` へそのまま渡せる |
| `ReopenLogFiles() -> None` | 任意回 | control plane を使う**同期 API**。ACK timeout は内部定数 `CONTROL_PLANE_ACK_TIMEOUT_SEC=5.0` |

#### 2.2.3 single / multiprocess の差分

設計書 §10 と §11.18 は次の差分を明示する。

| 観点 | single-process | multiprocess |
|---|---|---|
| auto-fire | 許容 | **禁止**（attach 忘れを Fail-Fast 検知） |
| `GetLogger()` 未初期化時 | デフォルト引数で初期化 | `RuntimeError` |
| `ConfigureLogger()` 2 回目 | 状態によって No-Op or 旧 Pipeline 停止＋再初期化 | **`RuntimeError`**（同一 process 内の 2 重起動禁止） |
| `ReopenLogFiles()` | 同期的に file handle を reopen | control plane へ control request → ACK 待機 |
| `worker_model` / `mp_context` | 概念なし | 公開引数として明示 |

---

### 2.3 3 層設定管理パイプライン

設計書 §3 が定義する。設定の来源を以下の 3 層に分離し、**上位層が下位層を常に上書きする厳格なマージ順序**を定義する。

```text
第1層: 環境変数（最優先 / 緊急オーバーライド）
  ↓ 上書き
第2層: INI ファイルまたは辞書（運用ベースライン）
  ↓ 上書き
第3層: ConfigureLogger 引数（デフォルト / シンプル用途）
```

#### 2.3.1 各層の役割

| 層 | 役割 | 入口 |
|---|---|---|
| 第 3 層 | 引数（デフォルト / 小規模スクリプト用） | `ConfigureLogger(default_level=..., log_path=..., ...)` |
| 第 2 層 | INI ファイル または `config_dict`（運用ベースライン） | `config_file='./config/logging.ini'` または `config_dict={'global': {...}, 'dsafelogger:mod': {...}}` |
| 第 1 層 | 環境変数（緊急オーバーライド） | `D_LOG_LEVEL=WARNING` 等（プレフィックスは `env_prefix` で変更可能） |

#### 2.3.2 マージ評価の具体例

設計書 §3.3 の例:

```python
# 第3層: 引数
ConfigureLogger(default_level='DEBUG', log_path='./logs', routing_mode='daily')
```

```ini
; 第2層: INI
[global]
default_level = INFO
backup_count = 30
```

```bash
# 第1層: 環境変数
D_LOG_LEVEL=WARNING
```

マージ結果:
- `default_level` = `WARNING`（環境変数が最終決定）
- `log_path` = `./logs`（INI に記載なし、引数が維持）
- `routing_mode` = `daily`（INI に記載なし、引数が維持）
- `backup_count` = `30`（INI が引数のデフォルト値を上書き）

#### 2.3.3 環境変数（第 1 層）の項目

設計書 §4 の全環境変数:

| 環境変数 | 用途 | 有効値 |
|---|---|---|
| `{prefix}_LEVEL` | グローバルデフォルトレベル | `DEBUG` 〜 `CRITICAL` + 登録済みカスタムレベル名 |
| `{prefix}_MODULES` | モジュール別レベル/出力先 | `MOD:LEVEL[,...]` または `MOD:LEVEL:PATH[,...]` |
| `{prefix}_DIAGNOSE` | 診断モード | `"1"` のみ有効 |
| `{prefix}_CONSOLE` | コンソール出力強制制御 | `"1"/"0"`, `"true"/"false"` |
| `{prefix}_COLOR` | カラー出力強制制御 | `"1"/"0"`, `"true"/"false"` |
| `{prefix}_CONFIG` | INI ファイルパス上書き | ファイルパス |
| `{prefix}_HASH` | ハッシュ生成有効化 | `"1"/"0"`, `"true"/"false"` |
| `{prefix}_MANIFEST` | マニフェストファイルパス上書き | ファイルパス |
| `{prefix}_IPC_LOG_TIMEOUT` | mp 版 log plane 送信待機時間 | 正の浮動小数点秒数 |
| `{prefix}_IPC_LOG_QUEUE_MAXSIZE` | mp 版 log plane queue 容量 | 正の整数 |
| `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` | mp 版 process-local async queue 容量 | 正の整数 |
| `{prefix}_WRITER_FLUSH_BATCH` | mp 版 Writer flush batch サイズ | 正の整数 |
| `NO_COLOR` | カラー出力強制無効化 | 設定されていれば（業界標準、`env_prefix` 影響を受けない） |

設計書は次の「聖域」を明示する:

- **`diagnose` は環境変数のみ**: INI からも引数からも設定不可。設計書 §4.4 は「コードに `diagnose=True` と書ける手段が存在しない」「INI もバージョン管理リスクがあり除外」と理由を明文化。
- **`sens_kws` / `sens_kws_replace` も環境変数からの設定は非対応**: §3.4 でセンシティブキーワードの意図しない変更を防止する設計判断と説明。
- **`file_fmt` / `console_fmt` も環境変数では非対応**: Formatter インスタンスは環境変数で表現不可能なため。

#### 2.3.4 INI / `config_dict`（第 2 層）

設計書 §5 の規定:

- INI: `configparser.ConfigParser(interpolation=None)` で初期化（`%` エスケープ不要）。`[global]` セクションと `[dsafelogger:モジュール名]` セクションを定義。
- `config_dict`: `dict[str, dict[str, str]]` 型。INI と完全に同一の型変換・バリデーションパイプラインを通すため、**全ての値は文字列**として指定（`int`/`bool` 直接指定は `TypeError`、Fail-Fast）。
- `config_file` と `config_dict` は **排他**（両方指定で `ValueError`）。
- `[global]` セクションのキーは `ConfigureLogger` 引数と 1 対 1 対応。`color_{略称}` キーは第 2 層専用（環境変数・引数からは非対応）。
- 未知キー: stderr 警告 + 無視（Fail-Fast ではない）
- 未知セクション: stderr 警告 + 無視
- 既知キーの型変換失敗: **Fail-Fast**（`ValueError`）
- `[dsafelogger:]`（モジュール名空）: `ValueError`

#### 2.3.5 設計判断: 多層パイプラインの厳格マージ

設計書 §3 は「ConfigureLogger 引数より INI が、INI より環境変数が常に優先する」マージ順序を、**サイレントフォールバックを許さない原則**と組み合わせて運用している。

- 引数値で動かしたい開発者は INI を置かない。
- 運用で挙動を変えたい運用者は INI を置く。
- 緊急時に変えたいオペレータは環境変数を置く。
- どの層でも「型不正は Fail-Fast」「未知キーは警告のみ」という線が引かれる。

これは「設定変更箇所が一意に決まる（誰が変えたかを追跡可能）」設計姿勢の帰結である。

---

### 2.4 Capture 層

#### 2.4.1 `DSafeLogger`

詳細設計書 §2 が規定する。`DSafeLogger` は `logging.Logger` を継承し、`contextualize()` メソッドを追加するクラス。

```python
class DSafeLogger(logging.Logger):
    def contextualize(self, **kwargs) -> AbstractContextManager:
        ...
```

- 標準 `logging.Logger` の API は完全に維持される（`pytest` の `caplog` フィクスチャ・`SMTPHandler` 等の標準ハンドラもそのまま機能）。
- `logging.setLoggerClass(DSafeLogger)` を `ConfigureLogger()` 内部で呼び、**以降の `logging.getLogger()` 呼び出しが `DSafeLogger` インスタンスを返す**ようにする。
- multiprocess 版では `AttachCurrentProcess()` も process-local に `setLoggerClass()` を再適用する（fork 継承後の child でも process-local thread / transport 再生成と組み合わせて成立）。

#### 2.4.2 5 状態の初期化フロー

設計書 §9.2 が定義する状態遷移:

| 現在 | イベント | 遷移先 |
|------|---------|--------|
| `unconfigured` | `ConfigureLogger()` | `configuring` |
| `unconfigured` | `GetLogger()` 先行 | `configuring` (auto-fire) |
| `configuring` | 正常完了 | `explicit` or `auto` |
| `configuring` | 例外発生 | `unconfigured` (rollback) |
| `configuring` | 同一 thread 再入 | No-Op return |
| `auto` | `ConfigureLogger()` | `configuring`（旧 Pipeline 停止 → 再初期化） |
| `auto` | `_shutdown()` | `shutting_down` |
| `explicit` | `ConfigureLogger()` | **No-Op return** |
| `explicit` | `_shutdown()` | `shutting_down` |
| `shutting_down` | 完了 | `unconfigured` |
| `shutting_down` | `ConfigureLogger()` | No-Op |

`_lifecycle_lock` は `RLock` で実装される。同一 thread の再入は No-Op、別 thread は lock acquire 待機後に状態を再評価する。例外発生時は `try/finally` により `configuring` のまま残らないことを保証する。

#### 2.4.3 Formatter 群

詳細設計書 §4 が規定する 4 系統:

| クラス | 役割 |
|---|---|
| `DSafeFormatter` | テキスト出力（デフォルトフォーマット）。`%` / `{}` / `$` の全 style に対応 |
| `StructuredFormatter` | JSON Lines 出力。`contextualize()` 情報をトップレベルフィールドへ |
| `DiagnosticFormatter` | `diagnose=True` 時のテキスト出力。`f_locals` を展開 |
| `DiagnosticStructuredFormatter` | `diagnose=True` かつ `structured=True`。`f_locals` を JSON `locals` フィールドへ |

デフォルトフォーマット文字列:

```text
%(asctime)s.%(msecs)03d [%(levelname)-3s][%(filename)s:%(lineno)s:%(funcName)s] %(message)s
```

- 日時形式: `%Y-%m-%d %H:%M:%S`
- レベル略称: `DBG` / `INF` / `WAR` / `ERR` / `CRI`（および `register_level()` 登録済みカスタムレベル）

#### 2.4.4 LogRecord の非破壊取り扱い

設計書 §9.7 と詳細設計書 §4 が必須実装パターンとして規定する。

> `logging.LogRecord` は全ハンドラ間で同一インスタンスが共有される。Formatter や Handler が `record.levelname`、`record.msg` 等の属性を直接書き換えると、後続のハンドラに破壊的な副作用が伝播する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §9.7）

実装パターンは「表示用 proxy」によって解決される。

```python
class DisplayRecordProxy:
    def __init__(self, original: logging.LogRecord, overrides: dict[str, object]):
        self.__dict__ = original.__dict__.copy()
        self.__dict__.update(overrides)


class DSafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        display_level = self.LEVEL_MAP.get(record.levelname, record.levelname)
        display_record = DisplayRecordProxy(record, {'levelname': display_level})
        return super().format(display_record)
```

設計書 §2 v21 改訂で次の規定が追加されている。

- `record.levelname` を変更しない。
- `copy.copy(record)` や try/finally による一時差し替えに依存しない。
- ANSI カラー付与も同一 proxy 経路で解決する。

#### 2.4.5 レベル名略称マッピング

設計書 §9.8 が定める。

- 略称変換は **Formatter の責務範囲内で完結**する局所マッピングで実行。
- `logging.addLevelName()` によるグローバルなレベル名上書きは**使わない**（プロセスグローバル副作用を避けるため。第三者ライブラリのテスト独立性を保つ）。
- ただし `register_level()` 内部では `logging.addLevelName(value, name)` を呼ぶ。これは `logger.log(value, msg)` / `isEnabledFor(value)` の正常動作に必要な数値→名前マッピングであり、略称変換とは別。
- `LEVEL_MAP` / `COLOR_MAP` はクラス変数ではなく **インスタンス変数**として、Formatter 初期化時にビルトイン 5 段階とカスタムレベルの統合マップを構築する。

#### 2.4.6 カスタムログレベル

設計書 §9.9 が定める `register_level()`:

| 規約 | 内容 |
|---|---|
| 呼び出し順序 | `register_level()`（任意回数）→ `ConfigureLogger()`（1 回）→ `GetLogger()`（任意回数） |
| 後続呼び出し | `ConfigureLogger()` 後の `register_level()` は `RuntimeError`。`shutting_down` 中も `RuntimeError` |
| ビルトイン保護 | 値 10/20/30/40/50、名 DEBUG/INFO/WARNING/ERROR/CRITICAL、略称 DBG/INF/WAR/ERR/CRI の上書きは `ValueError` |
| 便利メソッド | `register_level('TRACE', value=5, ...)` → `DSafeLogger` クラスに `logger.trace()` メソッドを動的追加。既存メソッド名と衝突する場合はスキップ |
| 3 層パイプラインとの整合 | 引数 / INI / 環境変数の全層でカスタムレベル名が使用可能になる |
| spawn 再 import | 同一定義（name/value/abbreviation/color 完全一致）の再登録は冪等 no-op。不一致再登録は `RuntimeError` |

---

### 2.5 Transport 層

#### 2.5.1 `DirectTransport` / `QueueTransport`

詳細設計書 §15a が規定する。Transport 層は Capture と Sink の間を結ぶ抽象。

| Transport | 用途 | 動作 |
|---|---|---|
| `DirectTransport` | `is_async=False` 時 | Capture 側で生成された LogRecord を、同期的に Sink へ渡す |
| `QueueTransport` | `is_async=True` 時 | Capture 側で context/diagnose snapshot を行い、queue 経由で listener thread に hand-off |

#### 2.5.2 Async hand-off の意味論

設計書 §9.3 と §11.17:

- `is_async=True` 時、producer thread 側で:
  - `contextualize()` 情報を `LogRecord` の private 属性 (`_ds_context`) へスナップショット
  - `diagnose=True` かつ `exc_info` ありの場合のみ `f_locals` をマスク済み repr スナップショットに変換 (`_ds_diag_frames`)
- consumer thread 側では live `contextvars` を参照せず、producer 側 snapshot を優先使用。
- multiprocess 版で `is_async=True` を併用すると **process-local async queue + multiprocess log queue + Writer dispatch の二重キューイング**になる。通常は `is_async=False` で十分。

#### 2.5.3 No-Copy Snapshot（FrozenContext）

設計書 §9.5 と §2 v20 改訂:

- `contextvars.ContextVar[MappingProxyType]` を採用（v20 で `ContextVar[dict]` から変更）。
- `MappingProxyType` の immutability により、async mode の snapshot 取得・consumer 側参照を **O(1) 参照渡し**で実現。
- ただし `contextualize()` 入口での新 MappingProxyType 生成は O(n)。O(1) になるのは hand-off のみ。
- **mutable 値の Fail-Fast**: `contextualize(**kwargs)` の値が list / dict / set 等の mutable 型である場合、`TypeError` または `ValueError` を送出。これにより O(1) 参照渡しによる意図しない副作用を開発時に確実に検知。
- **MappingProxyType の制限**: トップレベルキー操作のみ保護。値が mutable な場合は内容変更を防げない（仕様上の明記）。

#### 2.5.4 `DSafeQueueHandler.prepare()` の完全オーバーライド

設計書 §9.3:

- D-SafeLogger の queue hand-off は stdlib `QueueHandler.prepare()` を**そのまま使わず**、`super().prepare()` も呼ばない**完全オーバーライド**とする。
- これにより Python 3.11 / 3.13 / 3.14 間の stdlib 差異を意味論から切り離す。

#### 2.5.5 module-specific path の Transport 完全統合

設計書 §2 v21 改訂:

- `is_async=True` の意味論を root 経路だけでなく module-specific path 経路にも一貫適用。
- `Pipeline` は `module_transports: dict[str, Transport]` を保持し、`stop()` 時に全 Transport を構造的に停止する。

---

### 2.6 Sink 層

#### 2.6.1 `AppendOnlyFileHandler`

詳細設計書 §6 が規定する。`logging.FileHandler` を継承し、Append-Only モデルでファイル書き込みを担う。

- `RoutingStrategy` から「次に書くべきファイル名」を受け取る。
- 切り替え判断は emit の直前に毎回問い合わせる。
- 切り替え時は旧ストリームを `close` し、新名のファイルを `open`（rename しない）。
- `_ds_required: bool = True`（クラス属性、v23h）。required sink として delivered 判定の対象。
- `_lock` の二重化を避けるため、独立した `self._lock` は v21 で廃止し、親クラス `logging.Handler` の `acquire()` / `release()` API に統一（二重 lock オーバーヘッド排除）。
- multiprocess 経路では `stream_flush_on_emit=False` に設定され、Writer が batch / per-message を統一制御する。

#### 2.6.2 `RoutingStrategy`

詳細設計書 §5 と設計書 §7.3 が規定する。各モードに対応する Strategy クラスが存在する。

| モード | サフィックス | 用途 |
|---|---|---|
| `none` | なし（`{pg_name}.log`） | 単一ファイル追記。external rotation 共存対象 |
| `daily` | `YYYYMMDD` | 日付変更時に切り替え |
| `hourly` | `YYYYMMDD_HH` | 毎正時に切り替え |
| `min_interval` | `YYYYMMDD_HHMM` | 指定分間隔（60 を割り切る整数のみ） |
| `startup_interval` | `YYYYMMDD_HHMMSS` | 起動時刻基点。`interval` は文字列指定（`'12h'` / `'1d'`）も受付 |
| `size` | 連番（`suffix_digits` 桁） | サイズ閾値で切り替え |
| `count` | 連番 | 行数閾値で切り替え |
| `cyclic_weekday` | `sun` / `mon` / `tue` ... | 曜日サイクル（世代管理対象外、上書き） |
| `cyclic_month` | `01` 〜 `12` | 月サイクル（同上） |

`size` / `count` の `max_count` 指定の有無で動作が分岐する:

- `max_count` 指定あり → サイクリック上書きモード（世代管理対象外）。
- `max_count` 指定なし → 上限到達エラーモード。`suffix_digits` の最大値（3 桁なら `.999`）まで単調増加し、限界で `OverflowError` を送出してアプリを停止。`backup_count > 0` または `archive_mode=True` は設計意図が矛盾するため、`ConfigureLogger()` 時に Fail-Fast（`ValueError`）。

#### 2.6.3 `ColorStreamHandler`

詳細設計書 §12 が規定する。

- `_ds_required = False`（best-effort sink）。
- ANSI カラーコードは略称化済みの表示用レベル値に対して付与。
- `record.levelname` を直接変更しない（§9.7 非破壊取り扱い遵守）。
- Windows 向けには初期化時に `os.system("")` で VT100 を有効化。
- `COLOR_MAP` はインスタンス変数として、`register_level()` 登録済みカスタムレベルのカラーも統合。
- カラー制御の優先順位（§4.5）:
  1. `NO_COLOR` 設定 → 強制無効
  2. `{prefix}_COLOR` 設定 → その値に従う
  3. 両者未設定 → `sys.stderr.isatty()` で自動判定

#### 2.6.4 `FileSink` / `ConsoleSink` / `SinkGroup`

詳細設計書 §1 と §15a:

- writer-side sink graph の中心抽象。
- single-process では `_pipeline.py` が `SinkGroup` を組み立てる。
- multiprocess では Writer runtime が同等の構造を組み立てる。
- multiprocess 経路の `_build_writer_sink_groups`（`mp/__init__.py`）が `stream_flush_on_emit=False` を設定し、Writer が flush を統一制御する（§11.27 v23g）。

#### 2.6.5 Sink 分類（required / best-effort）

設計書 §12.3（v23h）:

| handler | `_ds_required` | 意味 |
|---|---|---|
| `AppendOnlyFileHandler` | `True`（既定） | required sink。delivered 判定の対象 |
| `ColorStreamHandler` | `False` | best-effort sink。delivered 判定外、失敗は別計上 |
| 利用者独自の `logging.Handler` 派生 | 属性なし → `True` 扱い | 独自 handler は default required |

per-record 計上規則:

- 全 required handler が成功 → `delivered`（counter 増分なし）
- 全 required handler が失敗 → `_reject_counter += 1`、`writer_sink_reject` または `writer_policy_reject` を増分
- 一部の required handler のみ成功 → `_writer_partial_delivered += 1`（terminal state は `partial_delivered`）
- best-effort handler の失敗 → `_writer_best_effort_failures += 1` のみ（reject_counter への集約なし）

#### 2.6.6 非同期パージ・アーカイブ

詳細設計書 §7 と設計書 §7.5:

- 世代管理（`backup_count > 0`）はファイル切り替え時のみ別スレッド（`PurgeWorker` / `ArchiveWorker`）で実行（Fire-and-Forget）。
- `archive_mode=False` → 古いファイルを `unlink`。`enable_hash=True` の場合は `.sha256` サイドカーも連動削除。
- `archive_mode=True` → ZIP 圧縮して保存。`enable_hash=True` の場合はサイドカーも ZIP に同梱。
- ストレージ枯渇の未然防止: `shutil.disk_usage()` で空き容量を検証し、不足時は処理中止 + 警告。
- 自己修復性: Windows の他プロセスロック等で削除/アーカイブ失敗時は警告のみ出力し、次回切り替えタイミングでリトライ。
- 同一 family の maintenance 直列化: 同一 `directory + pg_name` に属する purge/archive は並列実行しない。

#### 2.6.7 ファイル名フィルタリングの厳密化

設計書 §7.5 の規定:

> 対象ファイルの特定においては、`pg_name` の前方一致による誤マッチ（例: `pg_name='App'` のパターンが `AppServer_*.log` にもマッチする問題）を防止するため、`pg_name` に完全一致するファイル名プレフィックスのみを対象とする厳密なフィルタリングを行うこと。

具体的には、対象ファイルは次のいずれかのパターンに**正確に一致**するもののみ:
- `{pg_name}.log`（NoneStrategy）
- `{pg_name}_{サフィックス}.log`（その他の Strategy）

---

### 2.7 ファイル完全性検証

#### 2.7.1 設計思想

設計書 §7.6:

- **書き込みの都度ではなく、ルーティングによりファイルが切り替わった時点**で SHA-256 ハッシュを生成。
- アクティブファイルにはハッシュが存在しない（中間状態のハッシュには意味がないため）。
- メインスレッド I/O を一切ブロックしない（別スレッド、Fire-and-Forget。ただし safe shutdown では bounded wait の対象）。

#### 2.7.2 サイドカーファイル（`.sha256`）

`sha256sum -c` 互換フォーマット:

```text
a1b2c3d4e5f6789...（64 文字の 16 進 SHA-256）  MyApp_20260328.log
```

- ハッシュとファイル名の区切り: **半角スペース 2 つ**（`sha256sum` 互換）
- ファイル名: **相対パス（ファイル名のみ）** を記載 → ログ一式を別の場所に移動しても検証が壊れない
- 検証: `sha256sum -c MyApp_20260328.log.sha256`

#### 2.7.3 マニフェストファイル

`manifest_path` 指定時に生成される、全ルーティング済みファイルのハッシュ履歴。

```text
[2026-03-28T23:59:59.123] a1b2c3d4e5f6789...  MyApp_20260328.log
[2026-03-29T23:59:59.456] b2c3d4e5f6789a1...  MyApp_20260329.log
```

- 追記（Append）形式。上書きしない。
- タイムスタンプはハッシュが確定した日時。
- 直列化: 同一 `manifest_path` への追記は常に 1 thread ずつ。
- 運用上の価値: ファイル消失検知（マニフェストにありディスクにないファイル）、改竄耐性向上（別ディレクトリ・別権限で保管）、履歴俯瞰。

#### 2.7.4 実行順序とスレッドモデル

| 条件 | 実行方式 |
|---|---|
| `enable_hash=True` かつ non-cyclic かつ `backup_count > 0` | `PurgeWorker` / `ArchiveWorker` 内でハッシュ生成を**先行実行** |
| `enable_hash=True` かつ non-cyclic かつ `backup_count=0` | 独立した `HashWorker` を Fire-and-Forget |
| cyclic 系 routing かつ `enable_hash=True` | `ConfigureLogger()` 時に Fail-Fast（`ValueError`） |
| `enable_hash=False` | 関連処理なし |

`.sha256` サイドカー書き込みは **`os.replace()` による原子的差し替え**を推奨（途中書き込み状態を外部に見せない）。

#### 2.7.5 スコープ外

設計書 §7.6.7 が明示的に除外する項目:

- **HMAC 署名**: 鍵管理という異質な責務を持ち込むため、本ライブラリのスコープ外。署名が必要な用途は本ライブラリのハッシュを入力とする外部ツールに委譲する方針。
- **CLI 検証コマンド**: `sha256sum -c` 互換フォーマット採用により OS 標準コマンドで即座に検証可能なため、専用コマンドは追加しない。

---

### 2.8 マルチプロセス対応（`dsafelogger.mp`）

#### 2.8.1 設計目的（§11.1）

> 複数 process から発生したログを 1 つの Writer runtime へ安全に集約し、single-process 版が既に持つ file pipeline（routing / hash / manifest / archive / purge / reopen）を意味論そのままで再利用すること。

#### 2.8.2 client / Writer モデル（§11.5）

| 用語 | 意味 |
|---|---|
| **client process** | ログ呼び出しを行う process。main も worker も含む |
| **Writer runtime** | file sink 群を所有し、client からのログを最終的に書き出す内部 process |
| **`ctx`** | client process が Writer runtime に参加するための **opaque かつ picklable な bootstrap object** |
| **log plane** | 通常ログ `LogEvent` を client → Writer に運ぶ片方向経路 |
| **control plane** | reopen / detach / stop / status 等の制御メッセージをやり取りする経路 |

Writer runtime はロガー内部の実装要素であり、開発者が直接 `multiprocessing.Process` で起動する対象ではない。開発者が知るべき契約は `ctx` / `AttachCurrentProcess()` / `DetachCurrentProcess()` に限定される。

#### 2.8.3 `ctx` の契約（§11.7）

`ctx` は公開 API 上 **opaque** であり、開発者には queue や pipe の実体を見せない。

`ctx` に必須の情報カテゴリ:
- protocol version
- Writer session identity
- log plane endpoint 参照
- control plane request endpoint 参照
- bootstrap ready / attach 時の `protocol_version` 照合情報
- default queue policy
- resolved config digest
- custom level registry hash
- attach に必要な runtime metadata

5 つの基本契約:
- `ctx` は **opaque**
- `ctx` は **picklable**
- `ctx` は **Writer runtime の lifetime に束縛される**
- `ctx` は `ConfigureLogger()` 生成時に **pickle round-trip 検証**される
- `ctx` には **非 picklable な同期プリミティブ**（`Event` / `Lock` / `Condition`）を含めてはならない

#### 2.8.4 registry hash 照合（§11.7）

| タイミング | 照合内容 |
|---|---|
| Writer bootstrap ready ACK | client が送った registry hash と Writer 側初期 registry を照合 |
| `AttachCurrentProcess(ctx)` 実行時 | 現在 process の registry と `ctx` 内 hash を照合 |

不一致は **`RuntimeError` による Fail-Fast**。hash アルゴリズムは **SHA-256**。

#### 2.8.5 bootstrap payload 構築原則（§11.7）

設計書は Formatter インスタンス pickle 不能問題を構造的に回避する原則を規定する:

- `ctx` に含める設定情報は **生の dict / プリミティブ値のみ**。
- `Strategy` / `Formatter` の**生インスタンスは含めない**。
- Formatter は `kind + constructor args` からなる picklable spec へ正規化する。
- Writer 側で受信した raw config dict / formatter spec から `Strategy` / `Formatter` を再構築する。
- `ResolvedConfig` も pickle 可能な中間表現として定義し、`Strategy` インスタンスを保持しない形に再定義する。

#### 2.8.6 process 間 payload スキーマ（§11.8）

4 種類の payload カテゴリ:

| Payload | 方向 | 主要フィールド |
|---|---|---|
| `ctx` | bootstrap | session id / endpoint / protocol version / digest / registry hash / runtime metadata |
| `LogEvent` | client → Writer | route identity / level / logger name / message / source location / process/thread metadata / `_ds_context` / `_ds_extra` / `_ds_diag_frames` / exception payload |
| `ControlRequest` | client → Writer | request id / client id / command type / command payload / picklable reply endpoint |
| `ControlAck` | Writer → client | request id / success flag / error category / error message / result payload |

**規約**: `LogEvent` の `_ds_context` と `_ds_extra` は常に key として存在し、空は `{}` で表現する。pickle 経由では hasattr による区別が成立しないため、**key 存在で「Capture 側で snapshot 取得済み」を明示**する。

#### 2.8.7 reply endpoint の固定化（§11.8.3）

v22i 固定:
- reply endpoint は per-request の `multiprocessing.Pipe(duplex=False)` による reply path とする。
- Queue を別 Queue の payload として送る Queue-in-Queue 方式は Python の `multiprocessing` 制約上成立しないため**採用しない**。
- Pipe reply endpoint は request/ack 完了後に client / Writer の双方で close されることを前提とする。

#### 2.8.8 log plane / control plane 分離（§11.9）

| Plane | 用途 | Transport | QoS |
|---|---|---|---|
| log plane | 通常ログの片方向 hand-off | bounded `multiprocessing.Queue` | timeout 超過時 drop（visible reject） |
| control plane | reopen / attach / detach / stop / status | 独立した queue + per-request Pipe reply | command 種別ごとに固定 |

control plane の command 種別ごとの QoS（§11.16.3）:
- `ATTACH` / `DETACH` / `STOP`: **drop 不可**
- `REOPEN` / `STATUS`: **ACK 必須**
- `ipc_log_timeout` は control plane には適用しない

設計原則（§11.9）:
- control command を log plane に混在させない
- ACK を log plane に混在させない
- 非 picklable な同期オブジェクトを control payload に含めない
- Pipe send/recv failure は raw `BrokenPipeError` / `EOFError` を外に漏らさず control plane failure として `RuntimeError` 系に正規化

#### 2.8.9 queue capacity と `ipc_log_timeout`（§11.16）

| 設定項目 | 既定値 | 範囲 | 環境変数 |
|---|---|---|---|
| `ipc_log_queue_maxsize` | 10000 | `<=0` で `ValueError`、`>100000` で warning | `{prefix}_IPC_LOG_QUEUE_MAXSIZE` |
| `ipc_client_queue_maxsize` | `ipc_log_queue_maxsize` と同値 | `<=0` で `ValueError` | `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` |
| `ipc_log_timeout` | 0.5 秒 | `<=0` で `ValueError`、`>3.0` で warning + clip | `{prefix}_IPC_LOG_TIMEOUT` |
| `MAX_IPC_LOG_TIMEOUT_SECONDS` | 3.0（内部上限） | フレームワークの絶対防衛線 | — |

> 設計判断: `MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` は通常ログ producer path を過度に長時間 block させない絶対上限。queue 一時飽和からの自然回復を待つには十分に長く、GUI thread や request handler thread を不可逆に固めるほど長くはない上限として採用。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.16.1）

v23h 改訂: 環境変数値が int / float に解釈できない場合は **`ValueError`**（warning + ignore からの fail-fast 化）。

#### 2.8.10 overflow 時のポリシー（§11.16.2）

- `ipc_log_timeout` 超過、または `queue.Full` 時は **record を drop**。
- drop 時は client 側 drop counter を増分。
- 最初の drop 発生時およびその後の要約タイミングで stderr warning。
- silent drop は行わない。

#### 2.8.11 `TrackedQueue`（v23h、§11.16.1）

log plane queue の実装は `multiprocessing.queues.Queue` 派生の `TrackedQueue` を用いる。

- コンストラクタで `super().qsize()` を**例外プローブ**して `NotImplementedError` を捕捉した場合のみ `multiprocessing.Value` カウンタへ自動 fallback。
- OS 名（macOS など）に依存しない判別。未来の or マイナーな未対応プラットフォームでも追加対応なしに正しく動作する。

#### 2.8.12 attach / detach（§11.13、§11.21）

`AttachCurrentProcess(ctx)` の責務:
- `ctx` の検証
- process-local reply endpoint の生成
- ATTACH request の送信
- process-local attach 状態の更新
- `logging.setLoggerClass()` の process-local 適用
- Capture → Writer hand-off の有効化

冪等性:
- same `ctx` への再 attach は no-op（必要なら process-local thread / transport の再生成のみ実施）
- 別 `ctx` への再 attach は `RuntimeError`

`fork` 継承との関係（§11.13.3）:
- POSIX fork では親 process の attach 状態が継承されうる。v22i ではこれを正常ケースとして扱う。
- ただし fork は main thread しか複製しないため、`is_async=True` の process-local pump thread 等は子 process 側で再生成が必要。
- 親側で logger 初期化および attach 完了後に child を fork すること。`ConfigureLogger()` / `AttachCurrentProcess()` 実行中の fork は禁止。
- Writer session が存続している間に限って成立。STOP 受理済み・drain 中・終了済みの場合、子は同一 session を自動 resurrect してはならない。

#### 2.8.13 Drop-in Replacement の multiprocess 版成立条件（§11.14）

- `dsafelogger.mp.ConfigureLogger()` は呼び出し元 process に `logging.setLoggerClass()` を適用。
- `AttachCurrentProcess(ctx)` も attach 対象 process に process-local 再適用。
- attach 完了後の worker process では、`GetLogger()` / `logging.getLogger()` / **第三者ライブラリが内部で呼ぶ `logging.getLogger()`** のいずれも Writer に集約される。

#### 2.8.14 配送状態の用語定義（§12.3）

設計書 §12.3 が階層的に定義する。

**Lifecycle states**:

| 用語 | 定義 |
|---|---|
| `attempted` | user code が logger に渡したログ呼び出し |
| `accepted` | level 判定および client-side filter を通過し、transport が配送責任を引き受けた |
| `enqueued` | accepted log が client-local queue または mp log queue に投入された |
| `delivered_per_sink` | 対象 sink 単位で flush 契約上の完了点を通過 |
| `delivered` | required sink set すべてで `delivered_per_sink` が成立 |

**Terminal states**:

| 用語 | 定義 |
|---|---|
| `rejected` | timeout / closed / invalid state / Writer unavailable 等で配送責任を引き受けなかった |
| `dropped` | accepted 後または local queue 段階で破棄された。silent にしてはならず counter / warning / summary に反映 |
| `writer_reject` | Writer 到達後に route / sink / writer-side policy で配送不能と判定 |
| `partial_delivered` | required sink set の一部のみ到達。silent にしてはならず counter / warning / summary に反映 |
| `unexpected_loss` | accepted されたが、dropped/rejected/writer_reject/partial_delivered として記録されず、shutdown 後にも delivered されない。**設計または実装バグとして扱う** |

**Policy qualifier**:

| 用語 | 定義 |
|---|---|
| `overload_shed` | OOM / 永久 block / 本体巻き込み停止を避けるため、bounded queue / timeout 方針で明示的に捨てた rejected または dropped に付与 |

required sink set は file sink を中心に定義する。console sink は best-effort sink とし、失敗時は warning / counter 対象とするが file delivery の `unexpected_loss` とは分離する。

#### 2.8.15 `writer_reject` の内訳（§12.3）

| 分類 | 定義 |
|---|---|
| `writer_route_reject` | route 解決不能、または route 対象 sink 不在 |
| `writer_reconstruct_reject` | LogEvent の破損 / reconstruct failure（v23h で `writer_event_reject` から分離） |
| `writer_close_marker_reject` | CloseMarker の不正（client_id 欠落 / session mismatch / 未知 client。v23h で分離） |
| `writer_sink_reject` | required sink が存在するが emit / write / flush で失敗（per record） |
| `writer_policy_reject` | required handler の filter または Writer 側 policy で配送拒否 |
| `writer_format_reject` | formatter / JSON encode 不能。v23h では `writer_sink_reject` に畳み込み |
| `writer_best_effort_failures` | best-effort sink（console 等）の emit 失敗。`writer_reject` の terminal state には含めない |

すべてに**専用 counter と stderr warning（rate-limited）**が割り当てられる。silent failure を構造的に許さない。

#### 2.8.16 shutdown ordering と active client registry（§11.21）

`AttachCurrentProcess()` 成功時に Writer は client を **active registry** に登録する。

stop 判定:
1. main 側から stop request を受けたこと
2. active client 数が 0 であること

の両方を満たしたとき shutdown へ進む。

**worker crash 時の registry 整合**:
- worker process が `DETACH` を送らずに終了した場合、active client registry に残存が生じうる。
- shutdown 中の active client 数 0 待ちには **内部 timeout** を設ける。
- timeout 到達時は **stderr warning** を出し、強制 stop へ移行。
- **silent hang を起こしてはならない**。

shutdown ordering:
1. client 側 async queue を drain
2. client から Writer への送信を完了
3. client が detach / close を送信
4. Writer 側が log plane queue を drain
5. Writer 側が sink handlers を close / hash / manifest finalize
6. Writer runtime が終了

#### 2.8.17 Bounded shutdown 契約（v23h、§12.4.1）

正常終了経路の shutdown でも silent hang を起こしてはならない。`mp.ConfigureLogger()` は `atexit` で `_mp_shutdown` → `WriterRuntime.stop()` を呼び出すが、`stop()` は次の bounded 契約に従う:

- `stop(timeout)` は最大 `timeout` 秒（既定 `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0`）だけ `log_thread` / `control_thread` の join を待つ。
- timeout 後に thread が生存していた場合、**stderr に visible warning を出力**する（stuck thread 名を含めて、silent failure にしない）。
- Writer の `log_thread` / `control_thread` は **`daemon=True`** で起動するため、stop() が drain を完了できなかった場合でも Python interpreter は exit できる（process survives 原則）。

```text
bounded wait (≤ timeout) → visible warning (drain incomplete を可視化) → process exits
```

drain 経路に未知の hang が混入した場合でも host process が永久に block することを禁止する。drain 完全性は `stop()` の serial drain ロジックが担保し、daemon フラグは fail-safe な escape のみに用いる。

#### 2.8.18 Writer flush 戦略（v23g、§11.27）

multiprocess 版 Writer の per-message flush は既定動作として維持される（§12.2「flush 契約の弱体化」厳守）。高スループット用途のため、`ConfigureLogger(writer_flush_batch=N)` で batch flush に opt-in できる。

| `writer_flush_batch` | 動作 | 想定用途 |
|---|---|---|
| `1`（既定） | per-message flush。Writer process crash 時の loss なし | 高 durability 要求 |
| `2 – 64` | N 件ごと flush + queue empty 時 idle flush。process crash 時最大 N-1 件 loss 可能性 | スループット優先 |
| `> 64` | 同上、ただし可視性低下リスク高 | 特殊用途 |

環境変数 `{prefix}_WRITER_FLUSH_BATCH` で上書き可能。`<=0` で `ValueError`、`>1024` で warning。`WriterRuntime.__init__` でも `ctx.writer_flush_batch < 1` を `ValueError` として弾く（`BootstrapContext` 直接構築経路の安全網）。

§12.3 用語との対応:
- `writer_flush_batch=1` の場合: dispatch 完了 = `delivered_per_sink` と一致。
- `writer_flush_batch>1` の場合: batch flush 完了点を `delivered_per_sink` の到達点とする。**ユーザーが opt-in した時点で per-message visibility は保証されない**。

multiprocess 経路では Sink（`AppendOnlyFileHandler`）の `stream_flush_on_emit` を Configure 層が `False` に設定し、Writer（`_mp_runtime.py`）が batch / per-message を統一制御する。

#### 2.8.19 `ReopenLogFiles()` は control plane（§11.20）

multiprocess 版での `ReopenLogFiles()` は、attached client process から control request を送信し、ACK を待つ同期 API。

- どの attached client process からでも呼び出し可能
- reopen の直列化責務は Writer 側
- ACK timeout: 内部定数 `CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0`（公開 API シグネチャに timeout 引数を追加しない）

> 設計判断: 5.0 秒の根拠は logrotate / cron 運用での postrotate スクリプト実行時間の典型値（数秒以内）と Writer 側 reopen 処理時間（通常数十 ms）の余裕を加味した値。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.20.3）

#### 2.8.20 mp_context（§11.12）

`mp_context` は Writer runtime と worker process 群が共有すべき `multiprocessing` context。

- 受付型: `None` / `'spawn'` / `'fork'` / `'forkserver'` / `multiprocessing.context.BaseContext`
- 既定解決: `mp_context=None` → **Python 既定の context に委ねる**（ライブラリは OS 判定により独自フォールバックを行わない）
- `mp_context` 指定時は **log/control queue と Pipe reply path の全 IPC primitive 生成に一貫適用**する

> 注意: Python 既定の multiprocessing context は OS および Python バージョン依存。`mp_context=None` のまま移植した場合、start method の差により attach 挙動や初期化要件が変化しうる。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.12）

---

### 2.9 過負荷時ポリシー（Overload Policy）と Survival-first 方針

#### 2.9.1 v23 系の分類（§12.4）

ログ欠損を一律に同じ問題として扱わない。

| 分類 | 扱い |
|---|---|
| `unexpected_loss` | バグ。accepted log が理由なく消えた状態であり、sequence 完全性検証で検出すべき対象 |
| policy-driven `rejected` | 配送責任を引き受ける前に、timeout / closed / writer unavailable 等で拒否した状態。明示記録が必要 |
| policy-driven `dropped` | bounded queue overflow 等で、本体保護のために明示的に捨てた状態。counter / warning / summary が必要 |

#### 2.9.2 既定方針

```text
bounded wait → visible reject/drop → process survives
```

ログを無制限に保持して OOM する、または本体処理を永久 block してサービス停止を招くよりも、**本体プロセスの生存を優先する**方針。

#### 2.9.3 デフォルト禁止事項（§12.4）

| 禁止事項 | 理由 |
|---|---|
| unbounded log queue | Writer 停止や出力先詰まり時の OOM リスク無制限増加 |
| indefinite producer block | GUI / Web handler / worker loop をログ出力で巻き込み |
| silent drop | 運用者がログ欠損を検知できない |
| overflow を `unexpected_loss` と混同 | 設計バグと overload policy の判断を誤る |

設計書は次を明記する:

> strict lossless mode、unbounded queue、OOM リスクを許容するモードを追加する場合は、D-SafeLogger の safety 方針に関わるため、必ずユーザー判断を仰ぐ。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §12.4）

---

### 2.10 並行安全性と free-threaded 対応

#### 2.10.1 共有状態の明示ロック化（§9.2、§2 v21）

設計書は GIL の存在や `list` / `dict` の内部ロックを安全性根拠にしない方針を明記する。

- `_configure_state` / `_active_pipeline` / `_active_workers` / `_custom_levels` は **明示ロック**で保護。
- `ConfigureLogger` の `_do_configure()` 全体を `_lifecycle_lock` 保持下で実行。
- `GetLogger` は `'configuring'` 状態を検出して lock 構造待機。
- `AppendOnlyFileHandler` の独立した `self._lock` を v21 で廃止し、親クラス `logging.Handler` の `acquire()` / `release()` API に統一（二重 lock オーバーヘッド排除）。

#### 2.10.2 cross-thread 安全性（§9.4）

free-threaded build では実行中の他 thread の frame に対する `f_locals` live 参照は unsafe である。

- queue を跨ぐ hand-off が発生する場合は producer thread 側で traceback と `f_locals` を**安全なマスク済み repr スナップショット**に変換。
- consumer thread 側では live 参照を行わない。

フォールバック規則:
1. queue hand-off 済みの診断スナップショットがあればそれを使用
2. 同一 thread 内で `exc_info` が保持されている場合のみ live 参照を許可
3. それ以外は standard traceback のみを出力

#### 2.10.3 thread 境界の意味論（§9.5）

- ユーザーが生成した新規 thread への初期 context 継承は Python 本体仕様に従う。
- D-SafeLogger 自身が生成する内部 thread は、**常に空 `Context` で開始**する。これにより内部 thread への context 漏洩を防ぐ。

---

### 2.11 設計上の特徴（仕様レベル）

本章で確認した資料から、仕様・設計レベルで観測される姿勢を整理する。

#### 2.11.1 「決まる場所を一意にする」マージ順序

3 層設定管理パイプライン（§2.3）は「同じ設定項目を上書きする経路が 3 つあるが、どれが最終決定者かが必ず決まる」構造である。これは Loguru の `add()` のような "configure freely whenever" モデルと対照的に、**どこで設定が決まったかを後から追跡可能**にする。

#### 2.11.2 「責務境界をプロセス境界より硬く保つ」

Capture / Transport / Sink 3 層分離（§2.1.2）は、single-process でも multiprocess でも責務境界を変えない。multiprocess では Transport 境界が IPC を経由するだけで、Capture（`logging` 互換意味論）と Sink（routing / hash / manifest）は同一構造を持つ。これは「multiprocess を special case として扱わない」設計姿勢である。

#### 2.11.3 「失敗を分類する」配送状態

§12.3 の delivery state hierarchy は、ログ欠損を一律「失われた」と扱わず、**6 種類の terminal state**（rejected / dropped / writer_reject / partial_delivered / overload_shed / unexpected_loss）に分類する。`unexpected_loss` のみが「バグ扱い」であり、それ以外は policy 由来で「説明可能な事実」として扱う。

#### 2.11.4 「絶対防衛線を内部定数で固定する」

`MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0`（§2.8.9）、`CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0`（§2.8.19）、`WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0`（§2.8.17）といった**内部 hard limit** を、設計書本文で根拠付きで固定している。これは「ユーザーが任意に大きな値を設定しても、ライブラリ側で host process を不可逆に固める長さは超えない」という構造的保証である。

#### 2.11.5 「opt-in を意味論変更の境界線にする」

`writer_flush_batch=1`（既定）と `writer_flush_batch>1`（opt-in）は、`delivered_per_sink` の到達点の意味を変える（§2.8.18）。ユーザーが opt-in した瞬間に「per-message visibility は保証されない」と仕様で明示する。これは「同一 API で複数の意味論を黙って混在させない」姿勢である。

#### 2.11.6 「standardness を維持するため標準を変えない」

- `addLevelName()` のグローバル副作用は使わない（§2.4.5）
- `record.levelname` を改変しない（§2.4.4）
- `QueueHandler.prepare()` を完全オーバーライドする（stdlib 差異から意味論を切り離す、§2.5.4）
- `multiprocessing.context` のフォールバックをライブラリで強制しない（§2.8.20）

これらは「stdlib の上に builds された他コードや他ライブラリが、本ライブラリの存在で前提を崩されないこと」を構造的に保証する設計姿勢である。

---

### 2.12 仕様・設計の整理

本章で確認した資料から、次のように整理できる。

1. **物理モジュール構成は 25 ファイル + `mp/` namespace に局所化されている**: 公開 API の入口は `__init__.py` と `mp/__init__.py` の 2 ファイルのみであり、それ以外はすべて private（`_` プレフィックス）。これにより public surface area が小さく保たれている。
2. **3 層分離（Capture / Transport / Sink）は single-process と multiprocess を貫く設計上の不変条件として運用されている**: 設計書 §11.3 と §12.1 がこれを Writer 不変条件の 1 項目として明文化し、「multiprocess では Writer 側で Capture 意味論を再実行してはならない」と境界を固定している。
3. **設定マージは 3 層厳格マージ + Fail-Fast の組み合わせ**: 環境変数 > INI/dict > 引数の上書き順序は、サイレントフォールバックを許さない原則（型不正は `ValueError`）と組み合わさっている。これにより「設定が反映されているように見えて反映されていない」状態が構造的に存在しない。
4. **聖域（環境変数のみ設定可）が明示されている**: `diagnose` / `sens_kws` / `sens_kws_replace` / `file_fmt` / `console_fmt` がそれぞれ理由付きで第 1 層・第 3 層・第 2 層への設定経路を遮断している。
5. **配送状態は階層的に 5 + 6 + 1 種類の用語で言語化されている**: Lifecycle states 5（attempted / accepted / enqueued / delivered_per_sink / delivered）、Terminal states 6（rejected / dropped / writer_reject / partial_delivered / unexpected_loss / writer_best_effort_failures は別計上）、Policy qualifier 1（overload_shed）。これらは設計書 §12.3 で公式定義され、各 counter / warning / summary に直接マッピングされる。
6. **`writer_reject` の内訳は v23h で 6 分類 + 1 件分離**: route / reconstruct / close_marker / sink / policy / format に分類され、`writer_event_reject` は `writer_reconstruct_reject` と `writer_close_marker_reject` に分離された。これにより異常事象が同一 counter に畳み込まれず、診断粒度が向上している。
7. **絶対防衛線が 3 つの内部定数で固定されている**: `MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` / `CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0` / `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0`。いずれも「host process を不可逆に固めない」上限として根拠付きで設計書本文に置かれている。
8. **bootstrap payload の picklability 制約はカスタム Formatter まで構造的に貫徹されている**: `ctx` には picklable spec（kind + constructor args）のみが入り、`Strategy` / `Formatter` の生インスタンスは入らない。Writer 側で再構築する設計により、custom Formatter サブクラスや closure 由来の pickle 不能問題を構造的に回避している。
9. **Bounded shutdown 契約は daemon=True との組み合わせで「process exits」を fail-safe として実現している**: `stop(timeout)` の bounded join + visible warning + daemon thread の組み合わせにより、drain 経路に未知の hang が混入しても Python interpreter の exit は保証される。silent hang は構造的に発生しえない。
10. **flush 契約の弱体化は opt-in 限定でのみ許容される**: `writer_flush_batch=1`（既定）の per-message visibility 契約を維持し、`>=2` への移行はユーザーの明示 opt-in と、その時点で per-message visibility が失われる旨の仕様明記を伴う。**「既定では durability を壊さない」境界線が明確**である。
11. **fork / spawn / forkserver の差は `mp_context` で開発者に明示露出されている**: `mp_context=None` の意味は「Python 既定に委ねる」であり、ライブラリが OS 判定を持ち込まない。これは「移植性問題が起きた場合、ライブラリ側で勝手に解決しない」設計姿勢の表明である。
12. **TrackedQueue の native qsize fallback は OS 名に依存しない例外プローブで実装されている（v23h）**: `super().qsize()` を呼んで `NotImplementedError` を捕捉するか否かで判別するため、未来の or マイナーな未対応プラットフォームでも追加対応なしに正しく動作する。

---

### 2.13 本章のまとめ

D-SafeLogger v23j の仕様・設計の到達点は次の 5 点に集約される:

1. **3 層構造（Capture / Transport / Sink）を不変条件として運用する**: single-process でも multiprocess でも責務境界を変えず、multiprocess は Transport 境界が IPC を経由するだけ。
2. **3 層設定パイプライン（環境変数 > INI/dict > 引数）+ Fail-Fast + 聖域**: 設定の上書き経路が一意に決まり、特定設定（diagnose / sens_kws / fmt インスタンス）は経路を遮断する。
3. **配送状態を 5 + 6 + 1 用語で階層化し、`unexpected_loss` のみをバグ扱いとする**: 残り 6 種の terminal state はすべて policy 由来として「説明可能な事実」に分類され、counter / warning / summary に反映される。
4. **絶対防衛線を内部定数で固定し、bounded shutdown を daemon thread で保証する**: host process を不可逆に固めない上限が 3 つの定数で固定されており、shutdown 経路は visible warning + daemon thread の組み合わせで「process exits」を fail-safe として実現する。
5. **opt-in 境界で意味論変更を明示する**: `writer_flush_batch>1` の opt-in は per-message visibility を失う旨を仕様明記し、既定では durability 契約を弱体化させない。

これらの仕様事実は次章「3. ユーザビリティ」で公開 API・INI/dict・環境変数・examples の使用感として、また第 5 章「機能別詳細分析」で個別機能の動作として再評価される。

---

> **本章の主な参照資料**: `docs/design/D_SafeLogger_Specification_v23j_full.md` §3, §4, §5, §6, §7, §9, §10, §11, §12 / `docs/design/D-SafeLogger_DetailedDesign_v23j.md` §1, §2, §4, §5, §6, §7, §8, §11, §15a / `docs/api/dsafelogger*.md` / `src/dsafelogger/` モジュール構成 / `pyproject.toml`
> 本書は現行 v23j アーキテクチャの説明と評価を目的とし、改善提案・課題管理・将来ロードマップは扱わない。

## 第 3 章 ユーザビリティ

### 3.1 公開 API のサーフェス

#### 3.1.1 入口は 2 関数

D-SafeLogger の典型的な利用は、**`ConfigureLogger()` と `GetLogger()` の 2 関数**で完結する。

```python
from dsafelogger import ConfigureLogger, GetLogger

ConfigureLogger(log_path='./logs', pg_name='MyApp')
logger = GetLogger(__name__)
logger.info('Application started')
```

`examples/01_quick_start.md` はこの 3 行を「your first log」として提示する。出力例:

```text
2026-04-03 09:15:22.738 [INF][app.py:4:<module>] Application started
```

設計書 §10.1 が定める通り、`ConfigureLogger()` は 24 個の引数を持つが、**そのすべてに既定値があり、最小利用では `log_path` と `pg_name` の 2 つで足りる**。残りの引数は段階的に付け足していくモデル（§3.2）。

#### 3.1.2 補助 API

| API | 役割 | タイミング |
|---|---|---|
| `contextualize(**kwargs)` | スレッド/asyncio タスク内のログに識別子を自動付与 | 任意のスコープ |
| `register_level(name, value, abbreviation, color)` | カスタムログレベルの登録 | `ConfigureLogger()` の前 |
| `ReopenLogFiles()` | 外部 log rotation 後の再 open | 任意 |

これらはすべて optional であり、**「使わなければ存在しない」**設計（設計書 §9.9 / §15a）。

#### 3.1.3 multiprocess の入口

`dsafelogger.mp` namespace に分離されている（設計書 §11.4）。公開 API は次の 6 関数:

```python
from dsafelogger import mp

ctx = mp.ConfigureLogger(log_path='./logs', pg_name='MPDemo', mp_context=proc_ctx)
mp.AttachCurrentProcess(ctx)         # worker 内で
logger = mp.GetLogger(__name__)
mp.DetachCurrentProcess()            # worker 終了時
mp.ReopenLogFiles()                  # 任意
init_fn, init_args = mp.GetWorkerInitializer(ctx)  # Pool/Executor 連携時
```

設計書 §11.4 は分離の理由を「single-process 版の単純さ（1 回の Configure で完結）と、multiprocess 版の複雑さ（attach 契約・shutdown 同期）を意味論的に混在させない」と説明している。

---

### 3.2 最小コードからのスケール

#### 3.2.1 インクリメンタルな機能追加

`examples/01_quick_start.md` は同一の `ConfigureLogger()` をパラメータ追加だけで段階的に拡張できることを示している。

```python
# ステージ 1: console + file logging
ConfigureLogger(log_path='./logs', pg_name='MyApp')

# ステージ 2: 日次ルーティング
ConfigureLogger(log_path='./logs', pg_name='MyApp', routing_mode='daily')

# ステージ 3: ルーティング + JSON 出力 + 完全性ハッシュ
ConfigureLogger(
    log_path='./logs', pg_name='MyApp',
    routing_mode='daily', structured=True, enable_hash=True,
)
```

各ステージで **`logger.info()` 等の呼び出しサイトは一切変更不要**である。これは README "Why D-SafeLogger?" 節の「extends the standard logging path rather than replacing it」と整合する。

#### 3.2.2 auto-fire（暗黙初期化）

設計書 §9.2 と `examples/01_quick_start.md` GetLogger Auto-Fire 節:

```python
from dsafelogger import GetLogger

logger = GetLogger(__name__)
logger.info('This just works')
```

`ConfigureLogger()` を明示的に呼ばずに `GetLogger()` を呼んだ場合、デフォルト引数で内部的に `ConfigureLogger()` を auto-fire する（状態は `auto` に遷移）。

- 想定用途: notebook、ワンショットスクリプト、簡易 CLI
- 注意: 一度 `auto` に入った後の明示的 `ConfigureLogger()` は**旧 Pipeline 停止 → 再初期化**として正しく動く（明示優先の意味論）
- multiprocess 版（`dsafelogger.mp.GetLogger`）では auto-fire しない（`RuntimeError`）。attach 忘れを Fail-Fast 検知

#### 3.2.3 設計書 §10 が定める引数の段階性

`ConfigureLogger()` の引数を用途グループに整理すると、典型的なスケール経路が見える。

| 用途 | 引数 |
|---|---|
| 最小起動 | `log_path`, `pg_name` |
| 出力レベル制御 | `default_level`, `console_out` |
| ファイル世代管理 | `routing_mode`, `interval`, `max_bytes`, `max_lines`, `max_count`, `suffix_digits`, `backup_count`, `archive_mode` |
| 構造化ログ | `structured` |
| カスタム書式 | `fmt`, `file_fmt`, `console_fmt`, `datefmt` |
| 完全性検証 | `enable_hash`, `manifest_path` |
| 機密マスキング | `sens_kws`, `sens_kws_replace` |
| 設定の外部化 | `config_file`, `config_dict`, `env_prefix` |
| async I/O | `is_async` |
| multiprocess | `worker_model`, `mp_context`, `ipc_log_timeout`, `ipc_log_queue_maxsize`, `ipc_client_queue_maxsize`, `writer_flush_batch` |

設計書 §1.1.2 のポジショニング（D エコシステム共通基盤）と対応して、最小起動から監査・コンプライアンス対応までが**同一 API のパラメータ空間**で表現される構造である。

---

### 3.3 3 層設定パイプラインの運用

#### 3.3.1 役割分担

`examples/02_configuration_guide.md` が示す典型的な役割分担:

| 層 | 役割 | 想定する変更主体 |
|---|---|---|
| 第 3 層: 引数 | 開発者のデフォルト値（fallback） | アプリケーション開発者 |
| 第 2 層: INI / dict | デプロイベースライン（環境ごとに異なる） | DevOps / SRE |
| 第 1 層: 環境変数 | ランタイム上書き（再デプロイなしで変更） | on-call / オペレータ |

このユースケース表は `examples/02_configuration_guide.md` の "The Problem" 節で、3 環境 × 3 設定項目（DEBUG/INFO/WARNING、none/daily14/daily30、color/JSON/JSON+hash）の例として具体化されている。

#### 3.3.2 環境変数による緊急上書き（実例）

`examples/02_configuration_guide.md` および設計書 §4 が示す典型的な運用:

```bash
# 全体レベルを WARNING に
D_LOG_LEVEL=WARNING python app.py

# モジュール別: db を DEBUG、api を ERROR、別ファイルへ
D_LOG_MODULES=myapp.db:DEBUG,myapp.api:ERROR:/var/log/api.log python app.py

# 診断モードを 1 回だけ有効化
D_LOG_DIAGNOSE=1 python app.py

# JSON 出力 + ハッシュ生成を本番でだけ有効化
D_LOG_HASH=true D_LOG_MANIFEST=/var/log/audit/checksums.txt python app.py
```

設計書 §4.2 / §4.3 の規定:
- `{prefix}_LEVEL` はグローバル専用、カンマ区切りは **`ValueError` で `MODULES` への移行を促すエラーメッセージ**
- `{prefix}_MODULES` の個別 `MOD_SPEC` 書式違反は当該要素のみ stderr 警告 + スキップ（他要素の適用は継続）
- `{prefix}_DIAGNOSE` は `"1"` のみ有効。`"true"` / `"yes"` / `"True"` は無効

#### 3.3.3 `env_prefix` による名前空間分離

設計書 §10.1 / §4 / §4.6:

```python
ConfigureLogger(env_prefix='ORDER_LOG', ...)
```

これにより、以降の制御環境変数は `ORDER_LOG_LEVEL` / `ORDER_LOG_MODULES` / `ORDER_LOG_CONFIG` 等になる。同一マシン上で複数の D-SafeLogger インスタンスの環境変数名前空間を分離可能。`NO_COLOR` は業界標準のため、`env_prefix` の影響を受けない（§4.5）。

---

### 3.4 INI / dict 設定

#### 3.4.1 INI テンプレート生成

`examples/02_configuration_guide.md` および `examples/14_cli_operations.md` が示す:

```bash
dsafelogger init > logging.ini
```

設計書 §8.1.1: テンプレートは **標準出力**へ出力し、ファイルパス引数を取らない（リダイレクトでユーザーが保存先を制御）。テンプレートには全設定キーがコメントアウト状態で記載され、各キーの役割とオプション選択肢がインラインコメントで説明される。

#### 3.4.2 モジュール別セクション

`examples/02_configuration_guide.md` および設計書 §5.4 が示す本格運用の例:

```ini
[global]
default_level = INFO
log_path = /var/log/myapp
pg_name = OrderService
routing_mode = daily
backup_count = 30
structured = true
enable_hash = true

[dsafelogger:myapp.db]
level = DEBUG
path = db_queries.log

[dsafelogger:myapp.api]
level = WARNING

[dsafelogger:myapp.tasks]
level = INFO
path = background_tasks.log
```

設計書 §5.4 規定:
- `path` 省略時はグローバル設定（`log_path` / `pg_name`）を継承し、ルーティングは `none` 既定
- `path` 指定時の `routing_mode` 既定は `none`（ローテーション不要のシンプルケース想定）
- `path` 省略時に `routing_mode` 等のルーティング関連キーが指定されると、stderr 警告 + 当該キー無視

#### 3.4.3 `config_dict`（コード内辞書）

設計書 §5.7:

```python
ConfigureLogger(
    config_dict={
        'global': {
            'default_level': 'INFO',
            'log_path': './logs',
            'backup_count': '30',
        },
        'dsafelogger:myapp.db': {
            'level': 'DEBUG',
        },
        'dsafelogger:myapp.api': {
            'level': 'ERROR',
            'path': '/var/log/myapp/api.log',
            'routing_mode': 'size',
            'max_bytes': '10485760',
        },
    }
)
```

- 全ての値は文字列（INI と完全に同一の型変換・バリデーションパイプラインを通すため）
- `int` / `bool` 直接指定は `TypeError`（Fail-Fast）
- `config_file` と `config_dict` は排他（両指定で `ValueError`）
- `examples/02_configuration_guide.md` は「テスト環境やプログラム的に設定を生成するユースケースで特に有用」と説明

#### 3.4.4 INI と環境変数のマージ優先順位

`examples/02_configuration_guide.md` および設計書 §5.5 の例:

```ini
[dsafelogger:myapp.db]
level = DEBUG
path = /var/log/db.log
routing_mode = daily
```

```bash
D_LOG_MODULES=myapp.db:ERROR
```

- `myapp.db` のレベルは `ERROR` に上書き
- 環境変数では `MOD:LEVEL` のみ（パスなし）の指定であるため、INI 側の `path`、`routing_mode` 等は**すべて維持される**
- 環境変数 `{prefix}_MODULES` はレベルと出力先パスのみを上書き対象とし、INI 側のルーティング詳細は影響を受けない

---

### 3.5 examples 17 種の構成

`examples/` 配下の 17 ファイルは、README "Tutorials / Examples" 節で次の読み順に整理されている。

| 番号 | ファイル | テーマ |
|---|---|---|
| 1 | `01_quick_start.md` | Install / configure / first log |
| 2 | `02_configuration_guide.md` | Code / INI/dict / env layers |
| 3 | `03_migration_from_stdlib.md` | Migration from stdlib `logging` |
| 4 | `04_stdlib_ecosystem_coexistence.md` | stdlib-based ecosystem coexistence |
| 5 | `05_windows_service_and_scheduled_batch.md` | Windows service / scheduled batch |
| 6 | `06_web_api_logging.md` | Request-correlated structured logs |
| 7 | `07_long_running_service.md` | Routing / retention / archival |
| 8 | `08_compliance_audit.md` | SHA-256 integrity / audit logs |
| 9 | `09_debugging_production.md` | Diagnostic mode / masking |
| 10 | `10_incident_response_bundle.md` | Incident response bundle |
| 11 | `11_async_performance.md` | Queue-backed async logging |
| 12 | `12_multiprocess_logging.md` | Worker logging through parent-side Writer |
| 13 | `13_external_rotation_reopen.md` | Reopening files after external rotation |
| 14 | `14_cli_operations.md` | `dsafelogger` CLI |
| 15 | `15_opentelemetry_logging.md` | Trace correlation with stdlib instrumentation |
| 16 | `16_structlog_coexistence.md` | structlog 共存（Pattern A/B） |
| 17 | `17_container_collector_coexistence.md` | container / collector coexistence |

README は次の読み順を推奨している:

| 学習パス | 番号 |
|---|---|
| Getting started | 01, 02, 03 |
| stdlib / ecosystem integration | 03, 04, 15, 16 |
| Windows / service operations | 05, 07, 13, 14 |
| Application patterns | 06, 10, 11, 17 |
| Audit / incident response | 08, 09, 10 |
| Multiprocess logging | 12 |

01 / 02 は導入チュートリアル、03 以降は具体的な scenario guides として位置づけられる。`tests/examples/` の runnable scenario tests は 03-17 を対象にし、01 / 02 は個別 scenario ではなく導入説明として扱う。

最も厚い 12（multiprocess）と 03（stdlib 移行）に紙幅が割かれている点が、本プロダクトの想定読者層（既存 stdlib `logging` ベースのアプリ + 監査 / multiprocess 運用）を反映している。

#### 3.5.1 学習パス別の特徴

##### Getting started（01 / 02 / 03）

- **01**: 最小 3 行の起動例から段階的に機能を足す導入。`logger.debug` 〜 `logger.critical` の全 5 段階の出力例。
- **02**: 3 層パイプラインの役割分担（dev / staging / prod）を 3 × 3 表で具体化。
- **03**: stdlib `basicConfig` / `TimedRotatingFileHandler` / `dictConfig` からの 3 つの移行パターンを before/after で提示（§3.7 で詳述）。

##### stdlib / ecosystem integration（03 / 04 / 15 / 16）

- **03**: stdlib `logging` からの移行。既存の `logger.info()` 呼び出しサイトを変えず、setup code を D-SafeLogger に寄せる。
- **04**: stdlib logging ecosystem との共存。SQLAlchemy / Django / requests / boto3 などの既存 logger を集約する。
- **15**: OpenTelemetry trace correlation。OTel SDK の logging exporter ではなく、`contextualize(trace_id=..., span_id=...)` による extra フィールド注入。
- **16**: structlog 共存。Pattern A（structlog で JSON、D-SafeLogger で human text の dual stream）と Pattern B（structlog で event 組み立て → D-SafeLogger で routing/出力の pipeline）の 2 方式。

##### Windows / service operations（05 / 07 / 13 / 14）

- **05**: Windows service / scheduled batch。append-only 出力により Windows の rename / file lock 問題を避ける運用例。
- **07**: 長期稼働サービス向け。daily routing + retention + archive を組み合わせる。
- **13**: 外部ローテーター（logrotate 等）との共存。`routing_mode='none'` でのみ正式サポート。
- **14**: CLI ツール 3 コマンド（init / ls / tail -f）の使い方。

##### Application patterns（06 / 10 / 11 / 17）

- **06**: Web API 想定。request_id / user_id などを `contextualize()` で付与する構造化ログ例。
- **10**: Incident response bundle。構造化ログ、診断出力、ハッシュ、manifest を収集する手順。
- **11**: `is_async=True` による queue-backed 非同期 hand-off。
- **17**: container / collector coexistence。外部 collector に転送を任せながらローカル JSONL を保持する。

##### Audit / incident response（08 / 09 / 10）

- **08**: SHA-256 サイドカー / マニフェスト / `sha256sum -c` 互換検証 / 監査ログ向け運用例。
- **09**: production debugging。`D_LOG_DIAGNOSE=1` の使用法と sens_kws マスキングの実例。
- **10**: Incident response bundle。異常時の evidence collection を具体化する。

##### Multiprocess logging（12）

- **12**: 438 行と全 examples で最大。Process / Pool / Executor の 3 パターン、Windows spawn 規則、attach/detach lifecycle、environment knobs、failure mode 一覧、shutdown summary 解釈。

---

### 3.6 CLI ツール `dsafelogger`

#### 3.6.1 提供される 3 つのコマンド

設計書 §8 と `examples/14_cli_operations.md`:

| コマンド | 役割 |
|---|---|
| `dsafelogger init` | INI 設定ファイルのテンプレートを **標準出力**に出力 |
| `dsafelogger ls [log_dir]` | 指定ディレクトリ内の D-SafeLogger ファイルをパースし、プログラム名でグループ化して一覧表示 |
| `dsafelogger tail -f <log_dir> <pg_name> [options]` | 指定プログラムの最新ログファイルを自動判定して追随 |

#### 3.6.2 「最新ファイルを自動判定して追随」する `tail -f` の意義

設計書 §8 冒頭:

> Append-Only ルーティングは致命的なファイルロックを回避する長所を持つ反面、「書き込み先のファイル名が動的に変わるため、常に同じ `app.log` を `tail -f` できない」という弱点を持つ。これを克服するため、専用の CLI ユーティリティ群をパッケージに同梱する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §8）

CLI の役割は **Append-Only モデルの運用上の弱点を補完する**位置づけであり、ライブラリ本体の一部として提供される。

> 透過的なファイル追随: 出力中に元アプリケーション側でログの「日跨ぎ」等によりファイルが切り替わった場合でも、CLI がそれを動的に検知し、透過的に `tail` 先を新ファイルへ差し替えて出力を継続し続ける。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §8.1）

#### 3.6.3 リダイレクトを前提とした `init` の設計

設計書 §8.1: `init` がファイルパス引数を取らず標準出力に流す設計の意図は次の通り。

- 既存ファイルの上書き確認等の複雑さを回避
- パイプ・リダイレクトとの組み合わせを容易にする
- `dsafelogger init | less`（中身を確認）/ `dsafelogger init > logging.ini`（保存）が同等の自然さで成立

#### 3.6.4 コマンド名のハイフン省略

設計書 §8.1: PyPI パッケージ名 `d-safelogger` からハイフンを除外した `dsafelogger` を採用。シェルでのタイピング時のハイフン省略を優先した命名判断。import 名 `dsafelogger` と一致しているため、Python と CLI で同じ名前を覚えれば良い設計。

---

### 3.7 stdlib `logging` からの移行

#### 3.7.1 3 つの典型的移行パターン

`examples/03_migration_from_stdlib.md` が示す before/after:

##### Pattern 1: `basicConfig` → `ConfigureLogger`

| Before（stdlib） | After（D-SafeLogger） |
|---|---|
| 11 行（`basicConfig` + 2 handler 設定） | 4 行（`ConfigureLogger` + `GetLogger`） |

得られるもの: source location（`[file:line:func]`）、ミリ秒タイムスタンプ、自動ディレクトリ作成、ANSI 色、全 logger で一貫したフォーマット。

##### Pattern 2: `TimedRotatingFileHandler` → `routing_mode`

| Before（stdlib） | After（D-SafeLogger） |
|---|---|
| 16 行（`os.makedirs` + handler + suffix + formatter + addHandler + setLevel） | 7 行 |

得られるもの: append-only 戦略（midnight rename なし、Windows ロック問題なし）、SHA-256 オプション、自動 purge / archive。

##### Pattern 3: `dictConfig` → `config_dict`

stdlib `dictConfig` の `version: 1` / `handlers` / `formatters` / `root` の 4 階層構造から、`config_dict={'global': {...}, 'dsafelogger:mod': {...}}` の 2 階層に整理される。

#### 3.7.2 既存呼び出しサイトの保持

`examples/03_migration_from_stdlib.md` の冒頭:

> Your existing `logger.info()` calls don't change. Your third-party libraries keep logging normally. Only the setup code changes — typically from 10-20 lines to 1-3 lines.
> （`examples/03_migration_from_stdlib.md`）

これは設計書 §1（Drop-in Replacement）と整合する。`logging.setLoggerClass()` を `ConfigureLogger()` 内部で呼ぶことにより、移行後も `logging.getLogger(__name__)` を直接呼ぶ既存コードや SQLAlchemy / Django 等のサードパーティが**コード変更なしに本ライブラリの設定フローに乗る**。

#### 3.7.3 移行コストの観測事実

`examples/03_migration_from_stdlib.md` 内で示される具体的な比較:

- `basicConfig` 移行: **11 → 4 行**（約 64% 減）
- `TimedRotatingFileHandler` 移行: **16 → 7 行**（約 56% 減）
- `dictConfig` 移行: 4 階層 → 2 階層（`global` + `dsafelogger:モジュール名`）

この削減は構文的な短縮ではなく、**handler / formatter / setLevel の手動配線が `ConfigureLogger()` のパラメータに集約される**設計の帰結である。

---

### 3.8 multiprocess 利用

#### 3.8.1 3 つの worker_model

`examples/12_multiprocess_logging.md` および設計書 §11.11:

| Pattern | 対応する `worker_model` | 推奨用途 |
|---|---|---|
| **Pattern A: `multiprocessing.Process`** | `'process'`（既定） | lifecycle を明示したい場合。Windows での挙動が最もわかりやすい |
| **Pattern B: `multiprocessing.Pool`** | `'pool'` | 既存コードが Pool ベース |
| **Pattern C: `concurrent.futures.ProcessPoolExecutor`** | `'executor'` | Future ベース運用 |

`ThreadPoolExecutor` は対象外（スレッド並列は single-process 版の責務）。

#### 3.8.2 Pattern A の典型コード

`examples/12_multiprocess_logging.md` Section 5:

```python
import multiprocessing
from dsafelogger import mp


def worker(log_ctx, worker_id: int) -> None:
    mp.AttachCurrentProcess(log_ctx)
    try:
        logger = mp.GetLogger("jobs.worker")
        with logger.contextualize(worker=worker_id):
            logger.info("worker started")
            # ... work ...
            logger.info("worker finished")
    finally:
        mp.DetachCurrentProcess()


def main() -> None:
    proc_ctx = multiprocessing.get_context("spawn")

    log_ctx = mp.ConfigureLogger(
        log_path="./logs",
        pg_name="MPDemo",
        routing_mode="daily",
        structured=True,
        mp_context=proc_ctx,
    )

    processes = [
        proc_ctx.Process(target=worker, args=(log_ctx, i))
        for i in range(4)
    ]
    # ...
```

#### 3.8.3 attach/detach lifecycle の説明責任

`examples/12_multiprocess_logging.md` Section 3 は、Writer が保証するもの・しないものを明示している。

> The Writer does not guarantee:
> - That every record survives a hard process termination, an OS crash, or power loss.
> - That records lost before the runtime accepts them ... are recovered.
> - That `UnexplainedLost` is always zero. The whole point of that counter is that some abnormal scenarios cannot be classified more precisely; the value is making them visible rather than silent.
> - That records are never dropped under backpressure. ... but they are counted as `KnownDropped`, not silent loss.
> （`examples/12_multiprocess_logging.md` Section 3）

これは README の "What Not To Claim" 節（BENCHMARK.md）および設計書 §1.2.5（Be honest about multiprocess behavior）と一貫した説明である。**ドキュメント側でも保証範囲を明示する姿勢**が貫かれている。

#### 3.8.4 Windows spawn 規則の事前ガイダンス

設計書 §11.12 と `examples/12_multiprocess_logging.md`:

- `mp_context=None` は Python 既定の context に委ねる（ライブラリが OS 判定で独自フォールバックしない）
- spawn worker の bootstrap では、モジュールトップレベルの `register_level()` が再実行されることがあり、**同一定義の再登録は冪等 no-op として許容**される（設計書 §10.3 spawn worker 再 import ルール）
- `examples/12_multiprocess_logging.md` は `if __name__ == "__main__":` ガードと `mp_context=multiprocessing.get_context("spawn")` の明示を Windows 用ガイドとして提示

---

### 3.9 third-party との共存

#### 3.9.1 structlog 共存（`examples/16_structlog_coexistence.md`）

2 パターンが定義されている:

| Pattern | 設計概念 | 用途 |
|---|---|---|
| **Pattern A: Dual Stream** | structlog で JSON、D-SafeLogger で human text の **責務分離** | log aggregator（Datadog/Elastic）に native JSON を流しつつ、ディスクには人間可読テキストも残したい |
| **Pattern B: Unified Output** | structlog で event 組み立て → D-SafeLogger で **routing / formatting / rotation を一元化**するパイプライン | structlog の `bind()` API を使いつつ、出力経路を D-SafeLogger に委ねる |

#### 3.9.2 OpenTelemetry trace correlation（`examples/15_opentelemetry_logging.md`）

D-SafeLogger 自体は OTel SDK に依存しない（Vendor-Agnostic、設計書 §2）。`examples/15_opentelemetry_logging.md` が示す統合パターン:

- `contextualize(trace_id=..., span_id=...)` で current span の ID をコンテキストに注入
- 出力は構造化 JSON（`structured=True`）として、`trace_id` / `span_id` がトップレベルフィールドに現れる
- OTel collector / log shipper 側で trace correlation を解決

これは README "Compatibility / Non-goals" 節（D-SafeLogger は log shipper / metrics pipeline / distributed tracing backend ではない）と整合する。

#### 3.9.3 stdlib logging サードパーティとの共参加

設計書 §1 と README "Why D-SafeLogger?":

- `logging.setLoggerClass()` により、SQLAlchemy / Django / requests / boto3 等の `logging.getLogger()` 利用ライブラリは**改修なしで**本ライブラリの設定フローに乗る
- `examples/03_migration_from_stdlib.md` は「Your third-party libraries keep logging normally」と明示

---

### 3.10 ドキュメント体系

#### 3.10.1 公開ドキュメントの 5 軸

`README.md`、公開設計書、運用ガイドから、本プロジェクトの公開ドキュメントは次の 5 軸に整理されている。

| 軸 | 文書 | 役割 |
|---|---|---|
| 入口 | `README.md` / `README_ja.md` | overview + feature comparison + tutorial pointer |
| 学習 | `examples/01_*.md`〜`examples/17_*.md`（17 ファイル） | tutorial / scenario guide |
| 設計 | `docs/design/*v23j*.md`（3 ファイル） | 基本設計・詳細設計・テスト設計 |
| API | `docs/api/dsafelogger*.md` | 自動生成 API リファレンス |
| 運用 | `TESTING.md` / `BENCHMARK.md` / `CONTRIBUTING.md` / `CHANGELOG.md` | 検証・性能・寄稿・履歴 |

#### 3.10.2 docs/api/ の自動生成

公開ドキュメント運用では、生成物の同期確認を次のコマンドで行う:

```bash
# API docs check
uv run python scripts/generate_api_docs.py --check

# public design docs readiness check
uv run python scripts/check_design_docs_sync.py
```

- public API / docstring を変更したら `scripts/generate_api_docs.py` で `docs/api/` を再生成し、`--check` で検証
- 公開設計書は `scripts/check_design_docs_sync.py` で `docs/design/` と内部同期を検証

#### 3.10.3 多言語対応

- README は英語版（`README.md`）と日本語版（`README_ja.md`）の 2 言語対応
- examples / docs/design / docs/api / TESTING / BENCHMARK / CONTRIBUTING / CHANGELOG は英語のみ

#### 3.10.4 BENCHMARK.md の運用境界

`BENCHMARK.md` Maintenance Model 節は、benchmark runner と公開 analysis の境界を明示している。

- `benchmarks/results/<session>/` は実行ごとの完全な事実
- `benchmarks/summary/manifest.json` は公開・代表 session の固定表
- `benchmarks/summary/*.md` は manifest から生成される
- `BENCHMARK.md` は手動編集の解釈

これにより「最後に実行した benchmark が自動的に公開代表結果へ昇格する事故」を回避する設計（`BENCHMARK.md` Maintenance Model 節）。

---

### 3.11 設計書 §5.6 の Zero Dependency 一貫性

設計書 §5.6 が定める INI パーサー実装方針:

> 外部ライブラリ（D-Settings 等）を使わず、標準ライブラリの `configparser.ConfigParser(interpolation=None)` を用いた専用の極小 INI ローダーを D-SafeLogger 内部に内包する。
>
> 設計根拠: DRY 原則（コードの重複排除）よりも、基盤ライブラリとしての「完全なポータビリティ（外部依存ゼロ）」を優先するための明確なトレードオフ。ロガーは全プロジェクトの最下層に位置する基盤であり、他の D エコシステムライブラリ（D-Settings 等）が D-SafeLogger に依存する可能性がある。循環依存を避けるためにも、ロガー自身は外部に一切依存してはならない。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §5.6）

ユーザビリティの観点では、「INI 設定が使える」と「外部依存ゼロ」の両方が同時に成立する点が観測事実として記録される。

---

### 3.12 設計上の特徴（ユーザビリティレベル）

#### 3.12.1 「最初の 3 行を変えなくても本番までスケールする」

`ConfigureLogger()` の 26 引数はすべて既定値を持ち、`log_path` / `pg_name` の 2 つで最小起動が成立する。同じ関数のパラメータに `routing_mode='daily'` / `structured=True` / `enable_hash=True` / `manifest_path=...` を順次足すだけで監査・コンプライアンス対応まで到達できる構造。**最小起動と本番運用が同じ API のパラメータ空間で表現されている**。

#### 3.12.2 「変更主体ごとに層を割り当てる」

3 層パイプラインは「誰が変えるか」を層ごとに分けている: 開発者は引数、DevOps は INI、オペレータは環境変数。これは「設定変更の追跡可能性」と「再デプロイなしの runtime 上書き」を両立させる設計姿勢である。

#### 3.12.3 「移行のコストは設定行数で観測可能」

`examples/03_migration_from_stdlib.md` は stdlib からの移行を**呼び出しサイトを変えずに**実現する具体例として提示している。setup コードの行数削減（`basicConfig` 11→4 行、`TimedRotatingFileHandler` 16→7 行）は、handler / formatter / setLevel の手動配線が `ConfigureLogger()` パラメータに集約される設計の帰結であり、構文的短縮ではない。

#### 3.12.4 「third-party との関係は置き換えではなく共存」

structlog 共存 2 パターン、OpenTelemetry trace correlation、stdlib logging サードパーティの自動共参加。いずれも「他のフレームワークを排除しない」「他のフレームワークの責務に踏み込まない」設計姿勢で統一されている。

#### 3.12.5 「Append-Only の運用上の弱点を CLI で補完する」

Append-Only ルーティングが `tail -f app.log` を成立させない弱点を、`dsafelogger tail -f` の透過的ファイル切り替え追随で補完。**機能の理論的長所と運用上の使い勝手を別個に評価し、両方を本体に同梱する**姿勢。

#### 3.12.6 「失敗の境界を文書側でも明示する」

`examples/12_multiprocess_logging.md` Section 3 の「Writer does not guarantee」リスト、`BENCHMARK.md` の「What Not To Claim」リストは、ドキュメント上で**保証しない範囲を能動的に列挙する**姿勢の表れ。「過剰に期待されないことで、適切に使われる」設計判断。

---

### 3.13 ユーザビリティ観点の整理

本章で確認した資料から、次のように整理できる。

1. **最小起動コードは 3 行**: `ConfigureLogger(log_path=..., pg_name=...)` + `GetLogger(__name__)` + `logger.info(...)`。これは README "Quick Start" 節と `examples/01_quick_start.md` の両方で明示されている。
2. **公開 API の入口は 2 関数**: `ConfigureLogger()` と `GetLogger()` で典型利用が完結。補助 API（`contextualize` / `register_level` / `ReopenLogFiles`）は optional であり「使わなければ存在しない」モデル。
3. **26 引数のすべてに既定値がある**: 設計書 §10.1。最小起動と本番監査運用が同一 API のパラメータ空間で表現される。
4. **stdlib 移行は呼び出しサイト不変**: `examples/03_migration_from_stdlib.md` の 3 パターンはすべて、setup コード行数を 50–60% 削減し、`logger.info()` 呼び出しサイトを変更しない。
5. **3 層パイプラインは変更主体に対応**: 引数（開発者）/ INI または dict（DevOps）/ 環境変数（オペレータ）の対応が `examples/02_configuration_guide.md` 内で明示されている。
6. **CLI ツールが本体に同梱されている**: `dsafelogger init` / `ls` / `tail -f` の 3 コマンド。Append-Only モデルの運用上の弱点を構造的に補完する位置づけ。
7. **examples 17 ファイルが学習パスとして整理されている**: README の 6 学習パス（getting started / stdlib and ecosystem integration / Windows and service operations / application patterns / audit and incident response / multiprocess）でグルーピング。最大は 12_multiprocess（438 行）で、想定読者層を反映。
8. **multiprocess は専用 namespace（`dsafelogger.mp`）で 3 worker_model（process / pool / executor）に対応**: `examples/12_multiprocess_logging.md` が 438 行で 3 パターンの実コード・lifecycle・failure mode 一覧・shutdown summary 解釈を網羅。
9. **third-party 共存は 2 軸で文書化**: structlog（dual stream / unified output の 2 パターン）、OpenTelemetry（contextualize ベースの trace_id 注入）。stdlib logging サードパーティ（SQLAlchemy / Django 等）は `logging.setLoggerClass()` により改修なしで参加。
10. **保証しない範囲が能動的に列挙されている**: `examples/12_multiprocess_logging.md` Section 3 と `BENCHMARK.md` の "What Not To Claim" 節。`UnexplainedLost` の意味（無音化を防ぐための counter）まで明文化。
11. **多言語対応は README の 2 言語のみ**: `README.md` 英語版と `README_ja.md` 日本語版。examples / 設計書 / API リファレンス / 運用ガイドは英語のみ。
12. **API ドキュメントは自動生成 + check スクリプトで内部同期**: `scripts/generate_api_docs.py --check` / `scripts/check_design_docs_sync.py` により、API 変更時の docs/api/ と docs/design/ の整合検証が CI 統合可能。

---

### 3.14 本章のまとめ

D-SafeLogger v23j のユーザビリティの到達点は次の 5 点に集約される:

1. **入口は 2 関数（`ConfigureLogger` / `GetLogger`）に集約され、補助 API は optional**: 最小 3 行で起動し、26 引数の段階的追加だけで監査・コンプライアンスまでスケールする。
2. **3 層パイプライン（環境変数 > INI/dict > 引数）が変更主体（開発者 / DevOps / オペレータ）に対応**: `env_prefix` で名前空間を分離し、再デプロイなしの runtime 上書きを構造化している。
3. **stdlib `logging` 移行は呼び出しサイト不変・setup 50–60% 削減**: `basicConfig` / `TimedRotatingFileHandler` / `dictConfig` の 3 パターンが before/after で具体化。SQLAlchemy / Django 等の第三者ライブラリは改修なしで参加。
4. **examples 17 種が学習パスとして整理されている**: 最大は multiprocess で attach/detach lifecycle、failure mode、shutdown summary を網羅。stdlib ecosystem、Windows service、incident response、container collector、structlog、OpenTelemetry 共存は責務分離パターンとして文書化。
5. **CLI ツールが本体同梱で Append-Only モデルの運用補完を担う**: `init` / `ls` / `tail -f` の 3 コマンド。`tail -f` は透過的なファイル切り替え追随により Append-Only の運用上の弱点を構造的に補完する。

これらは次章「4. セキュリティ」で zero-dep（サプライチェーン）/ `diagnose` 聖域 / sens_kws マスキング / SHA-256 完全性等の安全側面として、また第 5 章「機能別詳細分析」で個別機能の動作として再評価される。

---

> **本章の主な参照資料**: `docs/design/D_SafeLogger_Specification_v23j_full.md` §4, §5, §8, §10, §11.4, §11.11, §11.12 / `examples/01_quick_start.md`, `02_configuration_guide.md`, `03_migration_from_stdlib.md`, `04_stdlib_ecosystem_coexistence.md`, `05_windows_service_and_scheduled_batch.md`, `06_web_api_logging.md`, `07_long_running_service.md`, `08_compliance_audit.md`, `09_debugging_production.md`, `10_incident_response_bundle.md`, `11_async_performance.md`, `12_multiprocess_logging.md`, `13_external_rotation_reopen.md`, `14_cli_operations.md`, `15_opentelemetry_logging.md`, `16_structlog_coexistence.md`, `17_container_collector_coexistence.md` / `README.md` / `README_ja.md`
> 本書は現行 v23j アーキテクチャの説明と評価を目的とし、改善提案・課題管理・将来ロードマップは扱わない。

## 第 4 章 セキュリティ

> **本章でいう「セキュリティ」の定義**: 本章で扱うセキュリティは、暗号・認証・アクセス制御に限定しない。サプライチェーン、誤設定、機密情報露出、監査可能性、並行実行時の破綻防止、ログ機構による可用性低下の抑制を含む、運用安全性として扱う。本ライブラリ自体はアクセス制御システム・暗号基盤ではない（README "Compatibility / Non-goals" 節）。
>
> したがって本章で取り上げる Safe の 6 軸は、狭義のセキュリティ機能ではなく、運用安全性・監査性・可観測性・並行安全性を含む広い設計概念である。

### 4.1 Safe の 6 軸とセキュリティの位置づけ

`README.md` Overview 節は、本プロダクトの "Safe" の概念を 6 軸で整理している（再掲）。

| 軸 | セキュリティ観点での位置づけ |
|---|---|
| **Startup safety** | 不正設定・書き込み不能パスを setup 時に拒否 → 「broken な設定で動いて見える」状態を構造的に排除 |
| **File safety** | rename/truncate を行わない → Windows のアクティブログ rename 不能問題を構造的に回避 + SHA-256 サイドカーで事後検証可能 |
| **Record/context safety** | producer 側で hand-off 時に snapshot → live `contextvars` への依存を排除。Writer 側で sens_kws マスキング適用 |
| **Operational control** | 環境変数で診断・ルーティング・ハッシュを再ビルドなしで上書き可能 |
| **Concurrency/multiprocess safety** | worker は共有ログファイルを直接開かず、parent 側 Writer が sink を所有。bounded queue + explicit timeout で host process への無制限待機を排除 |
| **Failure observability** | `KnownRejected` / `KnownDropped` / `UnexplainedLost` で配送失敗を分類 → silent loss を構造的に許さない |

本章では、これら 6 軸のうちセキュリティの観点で個別評価可能な要素として、(1) サプライチェーン、(2) 起動時セキュリティ、(3) 機密情報マスキング、(4) 完全性検証、(5) 並行・multiprocess 安全性、(6) 失敗可視化、(7) ロギング系の悪用パスの遮断、を順に取り上げる。

---

### 4.2 サプライチェーンセキュリティ（Zero Dependency）

#### 4.2.1 ランタイム依存ゼロ

`pyproject.toml` および設計書 §1 / §2:

> Zero Dependency（外部依存ゼロ）: 標準ライブラリのみで構成。外部依存を構造的に排除し、サプライチェーンリスクをゼロにする。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §2）

設計書 §1 では同条件を「絶対条件」として明記している。

> 「標準ライブラリへの完全な準拠」を絶対条件としつつ、サードパーティ製ライブラリ（Loguru 等）を凌駕する診断能力と、Windows 環境での致命的なファイルロック問題を回避する堅牢性を**外部依存ゼロ**で実現する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §1）

これにより以下が観測可能:

- インストール時に依存パッケージを引かない（`pip install d-safelogger` で完結）
- 依存パッケージの脆弱性発覚時に本ライブラリ側で被弾しない構造
- supply-chain attack（依存パッケージへの不正コミット・乗っ取り）のリスクが、Python 標準ライブラリ自体への攻撃に集約される

#### 4.2.2 Vendor-Agnostic 原則（v20）

設計書 §2:

> コアモジュール（`src/dsafelogger/` 配下）にベンダー固有の import（OpenTelemetry 等）やデータ参照を**一切含めない**。OTel 等のベンダー統合は、`file_fmt` / `console_fmt` によるカスタム Formatter の差し込み、`contextualize()` によるコンテキスト注入、`examples/` 配下のサンプルコードとして提供する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §2）

意義:

- コアコード上に opentelemetry-api / opentelemetry-sdk / その他ベンダー SDK の import が**コアコード上に存在しない**ため、これらの脆弱性が本ライブラリに伝播する経路がない。
- ベンダー統合は examples（ユーザーが任意で取り込むサンプルコード）として分離されており、ライブラリ本体の信頼境界に含まれない。

#### 4.2.3 開発・ベンチ依存の分離

`pyproject.toml` および dependency groups:

- ランタイム依存: なし
- `dev` dependency group: pytest 等のテスト用ツール（インストール時には不要）
- `benchmark` dependency group: ベンチマーク用ツール（インストール時には不要）
- `optional_integration` テスト marker は OpenTelemetry / structlog 等の統合動作確認用（CI では実行されるが、エンドユーザーのインストール時には引かない）

#### 4.2.4 ライセンス

`LICENSE`: Apache License 2.0。OSS 統合時の法的予見性に寄与する。

#### 4.2.5 配布物の最小性

`MANIFEST.in` および `pyproject.toml`:

- import 名 `dsafelogger`（ハイフンなし）/ distribution 名 `d-safelogger`（PyPI 正規化）
- `py.typed` を同梱（型情報の明示）
- wheel は runtime package files のみを含む。sdist は公開検証・再現性のため docs / examples / tests / benchmark summaries / selected benchmark summaries を含む。private planning materials と一時作業ファイルは含めない。

---

### 4.3 起動時セキュリティ（Startup Safety / Fail-Fast）

#### 4.3.1 設計姿勢

設計書 §9.1 と §2:

> Fail-Fast な初期化検証 & ストレージ事前検証: 起動時（`ConfigureLogger` 実行時）に出力先ディレクトリの作成可否やパーミッションを即座にテストし、権限エラーやディスクフルを早期に検知する。INI ファイルの不正値もサイレントフォールバックせず即座に例外を送出する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §2）

**「設定が反映されていないのに動いて見える」**状態を構造的に排除する設計姿勢。

#### 4.3.2 起動時に検証される項目

| 検証項目 | 失敗時の挙動 | 仕様根拠 |
|---|---|---|
| `log_path` ディレクトリのパーミッション | `PermissionError` / `OSError` で Fail-Fast | §9.1 |
| `log_path` ディレクトリのディスク空き容量（テストファイル作成） | 例外で Fail-Fast | §9.1 |
| モジュール別 `path` のパーミッション | Fail-Fast | §9.1 |
| `manifest_path` ディレクトリのパーミッション（指定時） | `PermissionError` で Fail-Fast | §7.6.6 / §9.1 |
| INI の型変換不能（`is_async` / `max_bytes` 等） | `ValueError` で Fail-Fast | §5.3 |
| INI の `[dsafelogger:]`（モジュール名空） | `ValueError` で Fail-Fast | §5.4 |
| `config_file` と `config_dict` の同時指定 | `ValueError` で Fail-Fast | §5.7.3 |
| `routing_mode='size'` で `max_bytes <= 0` | `ValueError` で Fail-Fast | §7.6.6 |
| `routing_mode='count'` で `max_lines <= 0` | `ValueError` で Fail-Fast | §7.6.6 |
| カスタムレベル名がビルトインと衝突 | `ValueError` で拒否 | §9.9.3 |
| `register_level()` を `ConfigureLogger()` 後に呼ぶ | `RuntimeError` | §9.9.2 |
| `config_dict` に文字列以外の値（int/bool 直接指定） | `TypeError` で Fail-Fast | §5.7.1 |
| 環境変数 `{prefix}_IPC_LOG_TIMEOUT` が float 解釈不能（v23h） | `ValueError` | §11.16.1 |
| 環境変数 `{prefix}_IPC_LOG_QUEUE_MAXSIZE` / `IPC_CLIENT_QUEUE_MAXSIZE` が int 解釈不能 | `ValueError` | §11.16.1 |
| 環境変数 `{prefix}_WRITER_FLUSH_BATCH` が int 解釈不能（v23h） | `ValueError` | §11.27 |
| `{prefix}_LEVEL` がカンマ区切り（モジュール別構文） | `ValueError`（`MODULES` への移行を促すメッセージ） | §4.2 |

#### 4.3.3 サイレントフォールバックを許さない原則

設計書 §5.3:

> INI ファイルから読み込んだ文字列値の型変換（`is_async` の bool 化、`max_bytes` の int 化等）やフォーマット違反については、安易にデフォルト値へフォールバックせず、即座に例外を送出して起動を停止させる（Fail-Fast）。デフォルト値へのサイレントフォールバックは「設定が反映されていないのに動いているように見える」という最も危険な障害パターンを生む。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §5.3）

これは、設定誤りが**起動時に表面化する**ことを保証し、デプロイ後に運用フェーズで初めて発覚する「見えない設定不整合」を排除する設計判断である。

#### 4.3.4 v23h での fail-fast 強化

設計書 §11.16.1 / §11.27 の v23h 改訂:

- 環境変数 `{prefix}_IPC_LOG_TIMEOUT` の値が float に解釈できない場合: warning + ignore から **`ValueError` への fail-fast 化**
- 同 `IPC_LOG_QUEUE_MAXSIZE` / `IPC_CLIENT_QUEUE_MAXSIZE`: 同上
- 同 `WRITER_FLUSH_BATCH`: 同上

これは「環境変数値の解釈ミスを silent ignore せず、起動時に明示する」方向への強化である。

---

### 4.4 機密情報マスキング

#### 4.4.1 `diagnose` 聖域化

設計書 §4.4 と `examples/09_debugging_production.md`:

`diagnose` 機能（例外発生時の `f_locals` 自動展開）は次の 3 重ガードで保護される。

| 設定経路 | 可否 |
|---|---|
| **環境変数 `{prefix}_DIAGNOSE=1`** | **唯一の有効化経路** |
| INI / config_dict の `diagnose` キー | **設定不可**（記載されても無視。警告もエラーも出さず、ただの無効キー扱い） |
| `ConfigureLogger()` の引数 | **そもそも引数として存在しない** |

設計書 §4.4 はこの設計判断の理由を次のように明記する。

> ソースコード上に `diagnose=True` と記述する手段が存在しないため、「コードに書いて戻し忘れる」という事故パターンが**通常の利用経路では成立しない**。
>
> INI ファイルはバージョン管理（git）に含まれることが多く、`diagnose = true` がコミットされて本番環境に混入するリスクはコード上の引数と同等である。したがって、INI ファイルからの経路も遮断する。
>
> 本番環境での有効化が必要な場合は、環境変数の設定というインフラ層の操作として明示的に行うこと。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §4.4）

`examples/09_debugging_production.md` は同パターンを「The Sanctuary Pattern」として説明:

> Diagnostic mode is deliberately hard to enable. This is by design — it's a safety mechanism:
> - A developer can't accidentally enable it in code — there is no Python parameter for it.
> - An INI config can't turn it on — the setting is not recognized in config files.
> - **ONLY an operator setting `D_LOG_DIAGNOSE=1` can activate it.**
>
> This prevents the single most common source of credential leaks: "debug mode left on in production." The operator who sets the environment variable knows exactly what they're doing, and they remove it as soon as the debugging session is over.
> （`examples/09_debugging_production.md`）

#### 4.4.2 `"1"` のみが有効値

設計書 §4.4: 環境変数値は `"1"` のみが有効。`"true"` / `"yes"` / `"True"` 等は無効値として扱う。

> `"1"` のみに限定することで、運用環境ごとの真偽値表記差異による意図しない有効化を防ぐ。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §4.4）

これは「複数の真偽値表記を許すことで設定漏れと混入を増やすリスク」を排除する判断である。

#### 4.4.3 sens_kws によるセンシティブキーワードマスキング

設計書 §9.4:

`f_locals` 展開時、変数名にセンシティブ語を含む値は `*** MASKED ***` に置換される。

**ビルトインキーワード（12 語）**（設計書 §9.4 公式定義）:

```text
password, passwd, pass, secret, token, key, api_key, apikey,
auth, credential, private, cert
```

`examples/09_debugging_production.md` の出力例:

```text
--- Local Variables (payment.py:5) ---
  user_id = 42
  api_key = *** MASKED ***
  amount = 15000.0
  token = *** MASKED ***
```

#### 4.4.4 マッチング規則

設計書 §9.4:

- 変数名に対する**部分一致**（大文字小文字不問）で判定
- 例: `password` は `user_password` / `PASSWORD_HASH` / `my_password_field` のいずれにもマッチ

#### 4.4.5 カスタマイズ

設計書 §9.4 と §10.1:

| 設定方法 | 動作 |
|---|---|
| `sens_kws=['ssn', 'credit_card']`（追加） | ビルトイン 12 語 + 追加語の合計でマッチ |
| `sens_kws=['ssn'], sens_kws_replace=True`（置換） | ビルトイン 12 語を破棄し、指定語のみでマッチ |

`sens_kws` / `sens_kws_replace` 両者とも**環境変数からの設定は意図的に非対応**（§3.4 / §4 / §5.3）。設計書はこれを「`diagnose` と同様の聖域的扱い」と説明している（§3.4 注釈）。

> v20 明確化: `sens_kws` / `sens_kws_replace` は環境変数からの設定を意図的に非対応とする。これは `diagnose` と同様の「聖域」的扱いであり、センシティブキーワードの意図しない変更を防止するための設計判断である。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §3.4）

#### 4.4.6 マスキングが適用されない範囲

`examples/09_debugging_production.md` Section "What Is NOT Masked":

- `logger.info(...)` / `logger.error(...)` 等に直接渡したメッセージ本文
- `extra=...` / `contextualize()` / structured JSON 出力で追加したフィールド
- `D_LOG_DIAGNOSE` がオフのときの通常ロギング

> If you place a secret directly in the message body or extra fields, it is logged **as-is**. Keep secrets in variables whose names match your masking rules, or redact them before logging.
> （`examples/09_debugging_production.md`）

これは「マスキングは `diagnose` モードの `f_locals` 経路のみで動作する」境界を明示し、ユーザーが境界を誤認してメッセージ本文に秘密を渡す事故を防ぐためのドキュメント上の警告である。

#### 4.4.7 巨大 repr の抑制と repr 失敗時の扱い

設計書 §9.4:

- 個々のローカル変数の `repr()` は**一定長で打ち切り**、巨大オブジェクトや過度に冗長なデータがログを汚染しないようにする
- `repr()` 自体に失敗した場合も診断ログ全体を壊さず、失敗した旨をプレースホルダとして出力する

これは「攻撃者が誘導する `__repr__` の例外」や「巨大オブジェクトによるログサイズ攻撃」に対する間接的な防御として機能する。

#### 4.4.8 cross-thread 安全性

設計書 §9.4:

> free-threaded build では、実行中の他 thread の frame に対する `f_locals` live 参照は unsafe である。したがって、queue を跨ぐ hand-off が発生する場合は producer thread 側で traceback と `f_locals` を**安全なマスク済み repr スナップショット**に変換し、consumer thread 側では live 参照を行わない。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §9.4）

これは security ではなく correctness の話であるが、free-threaded 環境での「他スレッドの内部状態を意図せず参照してしまう」事故を排除する点で、データ漏洩リスクの低減にもつながる。

---

### 4.5 ファイル完全性検証

#### 4.5.1 サイドカーファイル（`.sha256`）

設計書 §7.6.2 と `examples/08_compliance_audit.md`:

- ルーティングによるファイル切り替え時、書き込み完了ファイルに対して `{元ファイル名}.sha256` を生成
- `sha256sum -c` 互換フォーマット（1 行）:

```text
a1b2c3d4e5f6789...（64 文字の 16 進 SHA-256）  MyApp_20260328.log
```

- ハッシュとファイル名の区切りは**半角スペース 2 つ**（`sha256sum` 互換）
- ファイル名は**相対パス（ファイル名のみ）** → ログ一式を別の場所に移動しても検証が壊れない
- 検証: `sha256sum -c MyApp_20260328.log.sha256`

#### 4.5.2 マニフェストファイル

設計書 §7.6.3 と `examples/08_compliance_audit.md`:

```text
[2026-04-01T23:59:59.999] a1b2c3d4...  AuditService_20260401.log
[2026-04-02T23:59:59.999] e5f6a7b8...  AuditService_20260402.log
```

- 追記（Append）形式。上書きしない。
- タイムスタンプはハッシュが確定した日時（ISO8601 ミリ秒付き）
- 直列化: 同一 `manifest_path` への追記は常に 1 thread ずつ

#### 4.5.3 マニフェストの監査価値

設計書 §7.6.3 が明記する 3 つの運用価値:

> - **ファイル消失の検知**: マニフェストに記載されているがディスク上に存在しないファイルは「削除された」と判定できる。サイドカーファイルのみでは、ファイルとサイドカーが一緒に削除された場合に検知不可能。
> - **改竄耐性の向上**: マニフェストをログ本体とは別ディレクトリ・別権限で保管することで、ログファイルが攻撃者に操作されてもマニフェストとの不整合で検知可能。
> - **履歴の俯瞰**: 過去 N 日分のログが全て揃っているかを、マニフェスト 1 ファイルの行数で即座に確認可能。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §7.6.3）

#### 4.5.4 脅威モデル（保証範囲の明示）

`examples/08_compliance_audit.md` Section "Threat Model and Limitations":

> The sidecar + manifest flow proves that a **completed** log file still matches the recorded SHA-256 digest. It does **not** make local logs tamper-proof by itself.
>
> - If an attacker can rewrite the log file **and** its `.sha256` / `manifest.txt` with the same OS permissions, they can regenerate matching hashes.
> - The **current active log file** is not hashed until rotation/finalization happens.
> - The manifest records operational metadata (when files were finalized), so it needs normal access control just like the logs themselves.
>
> For stronger guarantees, ship sidecars/manifests to an **external append-only or immutable store** (for example S3 Object Lock, WORM storage, or a separate audit system). If you need cryptographic non-repudiation, layer a signing scheme on top.
> （`examples/08_compliance_audit.md`）

これは「保証する範囲」と「保証しない範囲」を**ドキュメント側で能動的に明示する**姿勢の典型である。HMAC 署名や暗号学的非否認性は設計書 §7.6.7 でも明示的にスコープ外と宣言されている。

#### 4.5.5 サイドカー書き込みの原子性

設計書 §7.6.4:

> sidecar 書き込みの原子性: `.sha256` サイドカーは途中書き込み状態を外部へ見せないよう、一時ファイルへ書き込んだ後 `os.replace()` により本命ファイルへ原子的に差し替える方式を推奨する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §7.6.4）

これにより、検証ツール側が「途中書き込みされたサイドカーを参照して検証失敗する」状態を回避する。

#### 4.5.6 cyclic モードでの Fail-Fast

設計書 §7.6.5:

`cyclic_weekday` / `cyclic_month` / `size`/`count` の `max_count` 指定ありモードでは、ファイル名が再利用される。`enable_hash=True` との併用は hash の意味論を保てないため、`ConfigureLogger()` 時に Fail-Fast（`ValueError`）とする。これは誤った監査記録の生成を構造的に防止する設計判断である。

#### 4.5.7 スコープ外（明示）

設計書 §7.6.7:

- **HMAC 署名**: 鍵管理という異質な責務を持ち込むため、本ライブラリのスコープ外。署名が必要な用途は本ライブラリのハッシュを入力とする外部ツールに委譲する方針。
- **CLI 検証コマンド**: `sha256sum -c` 互換フォーマット採用により OS 標準コマンドで即座に検証可能なため、専用コマンドは追加しない。

これは「セキュリティ機能をすべて自前で抱え込まず、責務を OS / 外部ツールに切り分ける」設計姿勢である。

---

### 4.6 並行・マルチプロセス安全性

#### 4.6.1 worker は共有ログファイルを直接開かない

設計書 §11.1 / §11.6 と `examples/12_multiprocess_logging.md`:

> Workers **never** open the shared log files directly. They submit `LogEvent` messages over an IPC queue.
> （`examples/12_multiprocess_logging.md` Section 4）

これにより以下が達成される:

- **複数 process が同一ファイルへ独立に書き込むことによる行混在**を構造的に排除
- **ファイルハンドル独占**が parent 側 Writer に集約され、Windows のファイルロック競合の可能性が排除される
- **routing / hash / manifest の責務が Writer に一元化**されるため、複数 process 間での状態不整合（複数の `.sha256` 生成・複数のマニフェスト更新）が起きない

#### 4.6.2 bounded queue + explicit timeout

設計書 §11.16:

| 設定 | 既定 | 絶対上限（防衛線） |
|---|---|---|
| `ipc_log_queue_maxsize` | 10000 | `>100000` で warning |
| `ipc_log_timeout` | 0.5 秒 | `MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` 秒へ強制 clip |
| ACK timeout | 5.0 秒（`CONTROL_PLANE_ACK_TIMEOUT_SEC`） | 公開 API に timeout 引数を追加しない |
| stop wait timeout | 10.0 秒（`WRITER_STOP_WAIT_TIMEOUT_SEC`） | 公開 API に timeout 引数を追加しない |

これら 4 つの内部定数は「ユーザーが任意に大きな値を設定しても、ライブラリ側で host process を不可逆に固める長さは超えない」という構造的保証である。

設計書 §11.16.1 の防衛線:

> 設計判断: `MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` は、通常ログの producer path を過度に長時間 block させないための絶対上限である。3.0 秒は queue 一時飽和からの自然回復を待つには十分に長く、一方で GUI thread や request handler thread を不可逆に固めるほど長くはない上限として採用する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.16.1）

#### 4.6.3 unbounded queue / 永久 block の禁止

設計書 §12.4:

| 禁止事項 | 理由 |
|---|---|
| unbounded log queue | Writer 停止や出力先詰まり時に OOM リスクが無制限に増える |
| indefinite producer block | GUI / Web handler / worker loop をログ出力で巻き込む |
| silent drop | 運用者がログ欠損を検知できない |
| overflow を `unexpected_loss` と混同 | 設計バグと overload policy の判断を誤る |

これは「ロギング機構自体が DoS の起点にならない」ための制約である。strict lossless mode / unbounded queue / OOM 許容モードの追加は、設計書側で**ユーザー判断を仰ぐ事項**として明示されている（§12.4）。

#### 4.6.4 bootstrap payload の picklability 制約

設計書 §11.7:

- `ctx` には picklable spec（`kind + constructor args`）のみが入る
- `Strategy` / `Formatter` の生インスタンスは入らない
- Writer 側で受信した raw config dict / formatter spec から `Strategy` / `Formatter` を再構築する

これにより、process 境界を越える payload に**任意のコード実行を伴う pickle ペイロード**（`__reduce__` を悪用した RCE）の余地が構造的に減る。allow-list 式の制約により、**標準的な spec 構築経路を外れる payload は受信側で受理されない**。

#### 4.6.5 registry hash 照合（SHA-256）

設計書 §11.7:

- Writer bootstrap ready ACK 時: client が送った registry hash と Writer 側初期 registry を照合
- `AttachCurrentProcess(ctx)` 実行時: 現在 process の registry と `ctx` 内 hash を照合
- いずれの不一致も `RuntimeError` による Fail-Fast
- hash アルゴリズムは SHA-256

これは「異なる Writer session に誤って attach する」「異なる levels registry を持つ client/Writer 間の意味論不整合」を起動境界で検出する仕組みである。

#### 4.6.6 control plane の error normalization

設計書 §11.9:

> Pipe send/recv failure は raw `BrokenPipeError` / `EOFError` のまま外へ漏らさず、control plane failure として `RuntimeError` 系へ正規化する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.9）

これは「内部実装由来の例外（`BrokenPipeError` 等）が API 境界の外側に漏れて、ユーザーコードが内部実装に依存する例外ハンドラを書く」事故を防ぐ。例外型を契約に固定することで、内部実装変更時の互換性を保つ。

#### 4.6.7 同一 process 内 2 回目 `mp.ConfigureLogger()` の禁止

設計書 §10.5 / §11.23:

> 同一 process で 2 回目の `dsafelogger.mp.ConfigureLogger()` は `RuntimeError`
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §10.5）

これは「同一 process に 2 つの Writer runtime / 2 種の `ctx` が共存する」事故を構造的に排除する。

#### 4.6.8 fork 継承後の child 専用 client identity

設計書 §11.13.3 / §11.21.1:

> POSIX `fork` では親 process の attach 状態が継承されうる。v22i ではこれを正常ケースとして扱う。ただし `fork` は main thread しか複製しないため、`is_async=True` で使う process-local pump thread 等は子 process 側で再生成が必要である。
>
> child は親の client identity を再利用してはならない。同一 Writer session であることを確認した上で、child 専用の process-local client identity を確立し、Writer active client registry へ登録してから logging を再開する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.13.3）

これは「fork 後 child が親の identity をそのまま使い続けることで、Writer 側 active client registry の整合が崩れる」事故を防ぐ規約である。

#### 4.6.9 Writer session 終了後の resurrect 禁止

設計書 §11.13.3:

> 境界条件: 上記の fork 継承 child 再登録は、元の Writer session が存続している間に限って成立する。親/Writer 側が `STOP` 受理済み・drain 中・終了済みの場合、子 process は同一 session を**自動 resurrect してはならない**。この場合の後続 `emit()` は通常の Writer unavailable 経路（drop + stderr warning）で扱い、継続運用は保証しない。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.13.3）

これは「Writer 終了後に child が暗黙に再起動する」予期しない resurrect を防ぐ規約である。

---

### 4.7 失敗の可視化（Failure Observability）

#### 4.7.1 silent drop / silent hang / silent fallback の禁止

設計書 §12.1（Writer 不変条件）:

> fail-safe: silent loss、silent hang、silent fallback を避ける
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §12.1）

これは v23 系全体を通じて Writer 不変条件として運用される。silent failure を許さない原則がライブラリ全体に適用される。

#### 4.7.2 配送状態の分類

設計書 §12.3 が定める 6 種の terminal state（再掲、§2.8.14 で詳述）:

| 用語 | セキュリティ観点での意味 |
|---|---|
| `rejected` | timeout / closed / writer unavailable で配送拒否。明示記録 |
| `dropped` | bounded queue overflow 等で本体保護のため明示破棄。counter / warning / summary に反映 |
| `writer_reject` | Writer 到達後の route / sink / policy 拒否（6 内訳: route / reconstruct / close_marker / sink / policy / format） |
| `partial_delivered` | required sink set の一部のみ到達。silent にしない |
| `unexpected_loss` | accepted されたが理由なく消えた → **設計または実装バグとして扱う** |
| `overload_shed` | bounded queue / timeout 方針による明示破棄に付与する qualifier |

`unexpected_loss` のみを「バグ扱い」とすることで、**残り 5 種は policy 由来の説明可能な事実**として扱える設計。

#### 4.7.3 stderr warning の rate-limited 出力

設計書 §12.3 / §11.22:

- すべての `writer_reject` 内訳に**専用 counter と stderr warning（rate-limited）**が割り当てられる
- 最初の drop 発生時およびその後の要約タイミングで stderr warning（§11.16.2）

rate limiting により「異常事象の連発で stderr 自体がログ汚染源になる」リスクが軽減される。

#### 4.7.4 Writer exit code

設計書 §11.22.4:

> 正常終了は exit code 0。異常終了は非 0。親 / 呼び出し元 process は、Writer exit code が非 0 の場合 stderr warning を出す。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.22.4）

これにより、Writer の異常終了が監視システム側（systemd 等）から検出可能になる。

#### 4.7.5 Bounded shutdown 契約（v23h）

設計書 §12.4.1:

```text
bounded wait (≤ timeout) → visible warning (drain incomplete を可視化) → process exits
```

drain 経路に未知の hang が混入した場合でも host process が永久に block することを禁止する。daemon=True と組み合わせて「process exits」を fail-safe として実現する。

セキュリティ観点では、「DoS 状況下でもログ機構が host process を巻き込んで停止させない」ことに相当する。

#### 4.7.6 worker crash 時の registry timeout

設計書 §11.21.2:

> worker process が `DETACH` を送らずに終了した場合、Writer の active client registry に残存が生じうる。shutdown 中の active client 数 0 待ちには内部 timeout を設ける。timeout 到達時は stderr warning を出し、強制 stop へ移行する。silent hang を起こしてはならない。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.21.2）

これは「worker crash により shutdown が永久に進まない」事故を timeout で打ち切る規約。silent hang を強制 stop + warning に変換する。

---

### 4.8 ロギング系の悪用パスの遮断

#### 4.8.1 `pg_name` のサニタイズ

設計書 §7.1:

> `pg_name` のサニタイズ規則: `pg_name` に OS のファイル名禁止文字（`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`）が含まれていた場合、それらは `_` に置換して使用する。これは Fail-Fast で弾くのではなく、ログ基盤として起動阻害を避けつつ安全なファイル名を生成するための仕様である。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §7.1）

これにより、`pg_name` 経由でのパス traversal や OS 固有の特殊ファイル名注入が構造的に発生しない。

#### 4.8.2 ファイル名フィルタリングの厳密化

設計書 §7.5:

> 対象ファイルの特定においては、`pg_name` の前方一致による誤マッチ（例: `pg_name='App'` のパターンが `AppServer_*.log` にもマッチする問題）を防止するため、`pg_name` に完全一致するファイル名プレフィックスのみを対象とする厳密なフィルタリングを行うこと。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §7.5）

これは「同一ディレクトリに別アプリのログが存在する場合に、世代管理が他アプリのファイルを誤って削除する」事故を排除する規約である。

#### 4.8.3 自己修復性とロック競合

設計書 §7.5 / §2:

> Fire-and-Forget 非同期パージと自己修復性: 世代管理（古いファイルの削除やアーカイブ）は出力先切り替え時のみ使い捨ての別スレッドで行う。万一 Windows のファイルロック等でパージに失敗しても、次回の切り替えタイミングで自動的に自己修復（リトライ）を行う。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §2）

セキュリティ観点では、「他プロセス（監視ツール等）がログファイルを開いている状態で、本ライブラリが強制的にロックを奪う / 強制削除する」挙動を取らないことを意味する。

#### 4.8.4 ログファイル名は「アプリケーションが選択する固定名」

設計書 §7.1: 出力ファイル名は `{log_path}/{pg_name}` をベースとし、ルーティングモードに応じて固定パターンのサフィックスが付与される。**ユーザー入力（リクエストパラメータ等）が直接ファイル名に注入される経路は存在しない**。

#### 4.8.5 INI / 環境変数の値が任意コード実行に至らない

設計書 §5.3 / §4: INI および環境変数の値はすべて文字列として読み込まれ、規定された型変換（int / bool / str）のみが適用される。eval / exec 経路や YAML の `!!python/object` 等の任意オブジェクト復元経路は存在しない。

#### 4.8.6 Vendor-Agnostic コアの帰結

設計書 §2 / §11.7: コアモジュールにベンダー固有 import がなく、bootstrap payload も `kind + constructor args` の picklable spec に限定されるため、攻撃者が悪意ある Formatter / Strategy インスタンスを注入する経路（pickle ペイロード経由の任意オブジェクト復元）が構造的に減る。

---

### 4.9 第三者ライブラリとの境界

#### 4.9.1 stdlib `logging` のグローバル状態への影響を最小化

設計書 §9.8:

> `logging.addLevelName()` によるグローバルなレベル名上書きは**使用しない**。
>
> 設計根拠: `addLevelName()` は `logging` モジュールのプロセスグローバルな状態を変更するため、同一プロセス内の全てのロガー（サードパーティライブラリ含む）に影響を及ぼす。D-SafeLogger の略称変換は自身の Formatter の責務範囲内で完結すべきであり、グローバルな副作用を避けることで、テストの独立性とサードパーティライブラリとの共存性を保つ。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §9.8）

セキュリティ観点では、「ライブラリの存在自体が同一プロセス内の他ライブラリの動作を変えてしまう」副作用が抑えられる。

#### 4.9.2 `LogRecord` の非破壊取り扱い

設計書 §9.7（再掲、§2.4.4 で詳述）:

`logging.LogRecord` は全ハンドラ間で同一インスタンスが共有される。本ライブラリは `record.levelname` や `record.msg` を改変せず、表示用 proxy で解決する。

セキュリティ観点では、「本ライブラリが改変した `LogRecord` を後続ハンドラ（third-party の `SMTPHandler` 等）が受け取って意図と異なる挙動をする」事故を防ぐ。

#### 4.9.3 internal thread の空 Context 開始

設計書 §9.5:

> D-SafeLogger 自身が生成する内部 thread は、常に空 `Context` で開始する。これにより内部 thread への context 漏洩を防ぐ。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §9.5）

これは「ユーザーの request context（user_id 等）が本ライブラリの内部 thread に漏洩し、後続のログにユーザーが意図しない context が混入する」事故を排除する規約である。

---

### 4.10 設計上の特徴（セキュリティレベル）

#### 4.10.1 「事故パターンを構造的に成立させない」

`diagnose` 環境変数限定（§4.4.1）、`sens_kws` の聖域化（§4.4.5）、`pg_name` のサニタイズ（§4.8.1）、ファイル名フィルタリングの厳密化（§4.8.2）、同一 process 内 2 回目 mp.ConfigureLogger() 禁止（§4.6.7）。これらに共通するのは「コード/設定/入力からの誤った経路を**そもそも存在させない**」設計姿勢である。

#### 4.10.2 「保証範囲を能動的に明示する」

`examples/08_compliance_audit.md` の Threat Model セクション、設計書 §7.6.7 の HMAC スコープ外宣言、`examples/12_multiprocess_logging.md` Section 3 の "Writer does not guarantee" リスト、`BENCHMARK.md` の "What Not To Claim"。これらは**できないこと・しないこと**をドキュメント上で先行宣言する姿勢の表れ。「過剰な期待による誤用」を防ぐ。

#### 4.10.3 「絶対防衛線を内部定数で固定する」

`MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` / `CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0` / `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0`。host process を不可逆に固める長さの上限を、ユーザーが上書き不能な内部定数で固定する。「DoS 起点にならない」ことを構造的に保証する設計判断。

#### 4.10.4 「責務を OS / 外部ツールに切り分ける」

HMAC 署名は外部ツールに委譲（§7.6.7）、サイドカー検証は `sha256sum -c` を使う（§7.6 / §8）、external rotation は logrotate との共存（`examples/13_external_rotation_reopen.md`）。**セキュリティ機能のすべてを自前で抱え込まず、OS / 外部ツールが既に提供する機構を活用する**姿勢。

#### 4.10.5 「異常を分類する」

silent loss を `accepted / rejected / dropped / writer_reject / partial_delivered / unexpected_loss / overload_shed` などの分類済み counters で記録する（§12.3、§4.7.2）。**「ログが消えた」を一律「失敗」として扱わず、policy 由来か bug 由来かを構造的に区別する**設計姿勢。`unexpected_loss` のみが「バグ」として扱われ、残りは説明可能な事実として運用される。

#### 4.10.6 「グローバル状態への副作用を最小化する」

`addLevelName()` を使わず Formatter 内で局所解決（§4.9.1）、内部 thread を空 Context で開始（§4.9.3）、`record.levelname` を改変しない（§4.9.2）。**ライブラリの存在が同一プロセス内の他コンポーネントに対して中立であろうとする**姿勢。

---

### 4.11 セキュリティ観点の整理

本章で確認した資料から、次のように整理できる。

1. **ランタイム外部依存ゼロが「絶対条件」として明文化されている**: 設計書 §1 が「外部依存ゼロで実現する」と絶対条件として宣言し、Vendor-Agnostic 原則（§2）でコアモジュールからベンダー import を構造的に排除している。サプライチェーン経路で攻撃者が経由できる第三者依存が存在しない。
2. **起動時に検証される項目は 16 項目以上**: log_path / モジュール別 path / manifest_path のパーミッション、INI 型変換、INI セクション規則、`config_file`/`config_dict` 排他、routing_mode 別の閾値、カスタムレベル名衝突、`register_level()` 呼び出し順序、各環境変数の解釈可否（v23h で fail-fast 化）が起動時に検証され、不正は例外で起動を停止する。
3. **`diagnose` は環境変数のみ・`"1"` のみ・3 重ガードで保護されている**: コード経路（引数なし）、設定ファイル経路（INI で記載されても無視）、真偽値表記揺れ（`"true"` 等は無効）の 3 重で「うっかり本番混入」を構造的に排除している。
4. **`sens_kws` / `sens_kws_replace` も同種の聖域として環境変数からの設定を遮断**: センシティブキーワードの意図しない変更を防止する設計判断として明文化されている（§3.4 v20 明確化）。
5. **マスキングのビルトインキーワードは 12 語**: `password` / `passwd` / `pass` / `secret` / `token` / `key` / `api_key` / `apikey` / `auth` / `credential` / `private` / `cert`（設計書 §9.4）。部分一致（大文字小文字不問）でマッチ。
6. **マスキング適用範囲がドキュメント側で明示されている**: `f_locals` 経路のみ動作し、`logger.info()` メッセージ本文 / `extra` / `contextualize` / 通常ロギングは対象外であることを `examples/09_debugging_production.md` が能動的に警告している。
7. **完全性検証は `sha256sum -c` 互換 + ファイル名相対パス**: OS 標準コマンドで検証可能。ログ一式を別の場所に移動しても検証が壊れない設計。サイドカーは `os.replace()` による原子的書き込み。
8. **完全性検証の脅威モデル境界がドキュメント上で明示されている**: HMAC 署名は明示的にスコープ外（§7.6.7）。攻撃者が同一権限でファイル＋サイドカー＋マニフェストを書き換え可能であれば改竄検知できないことが `examples/08_compliance_audit.md` Threat Model セクションで明記されている。
9. **絶対防衛線が 4 つの内部定数で固定されている**: `ipc_log_timeout` の上限 3.0 秒（`MAX_IPC_LOG_TIMEOUT_SECONDS`）、ACK timeout 5.0 秒、stop wait 10.0 秒、`ipc_log_queue_maxsize` warning 閾値 100000。host process を不可逆に固めない上限がユーザー上書き不能な定数で固定。
10. **bootstrap payload は picklable spec のみ**: `Strategy` / `Formatter` の生インスタンスは `ctx` に含まれず、`kind + constructor args` のみが渡される。allow-list 式により悪意ある pickle ペイロードの受理経路が構造的に減る。
11. **registry hash 照合は SHA-256 で 2 タイミング実行**: Writer bootstrap ready ACK 時と `AttachCurrentProcess(ctx)` 実行時。不一致は `RuntimeError` で Fail-Fast。
12. **silent loss / silent hang / silent fallback は v23 系不変条件として禁止されている**: 配送状態は分類済み counters として記録され、`unexpected_loss` のみが「バグ扱い」。それ以外は policy 由来の説明可能な事実。
13. **bounded shutdown 契約（v23h）により host process の永久 block を構造的に禁止**: `bounded wait (≤ timeout) → visible warning → process exits`。daemon=True と組み合わせて「process exits」を fail-safe として実現。
14. **`pg_name` のサニタイズ規則と厳密ファイル名フィルタリングがファイル経路の悪用を排除**: OS のファイル名禁止文字を `_` に置換、`pg_name` の前方一致による誤マッチを防止する完全一致フィルタリング。
15. **stdlib のグローバル状態への副作用が最小化されている**: `addLevelName()` を使わず Formatter 内で局所解決、内部 thread を空 Context で開始、`record.levelname` を改変しない。同一プロセス内の他ライブラリ・他コードに対して中立性を保つ。
16. **同一 process 内 2 回目の `mp.ConfigureLogger()` は `RuntimeError`**: 同一 process に複数 Writer runtime / 複数 `ctx` が共存する事故を構造的に排除。
17. **fork 継承後の child は親 client identity を再利用しない**: child 専用 client identity を Writer active client registry に登録する規約により、fork 後の registry 整合が保たれる。Writer session 終了後の resurrect は禁止。
18. **control plane の例外は `RuntimeError` 系に正規化される**: `BrokenPipeError` / `EOFError` 等の内部実装由来例外が API 境界の外側に漏れず、ユーザーコードの例外ハンドラが内部実装に依存しない。
19. **ライセンスは Apache 2.0**: 商用利用・改変・再配布が許諾され、特許条項により利用者の予見性が確保されている。

---

### 4.12 本章のまとめ

D-SafeLogger v23j のセキュリティの到達点は次の 5 点に集約される:

1. **サプライチェーン経路を構造的に排除する**: ランタイム外部依存ゼロ + Vendor-Agnostic コアにより、第三者依存経由の脆弱性伝播経路が存在しない。Apache 2.0 ライセンスにより法的予見性も確保。
2. **「うっかり本番混入」を構造的に禁止する**: `diagnose` は環境変数 `"1"` のみで有効化、`sens_kws` も聖域として環境変数遮断、INI 型不正は Fail-Fast。「コードに書いて戻し忘れ」「設定ミスがサイレントに動作」が起こり得ない。
3. **保証範囲と非保証範囲をドキュメント側で能動的に明示する**: HMAC スコープ外、`UnexplainedLost` の意味、Writer が保証しないこと、What Not To Claim が `examples/` と `BENCHMARK.md` で先行宣言されている。
4. **ロギング機構が DoS 起点にならない設計を構造的に保証する**: bounded queue + 4 つの内部定数（3.0 / 5.0 / 10.0 秒、100000 maxsize warning）で host process を不可逆に固めない。daemon=True と bounded shutdown で「process exits」を fail-safe として実現。
5. **異常を分類し、silent failure を許さない**: 分類済み配送状態 counters（`unexpected_loss` のみがバグ扱い）+ `writer_reject` 6 内訳 + rate-limited stderr warning + Writer exit code により、異常事象が監視可能な事実として外部化される。

これらは次章「5. 機能別詳細分析」で個別機能（Append-Only / async transport / multiprocess 配送状態 / SHA-256 等）の動作として、また第 7 章「OSS 公開時の位置づけ」で監査・コンプライアンス層・サプライチェーン重視層への技術的価値として再評価される。

---

> **本章の主な参照資料**: `docs/design/D_SafeLogger_Specification_v23j_full.md` §1, §2, §4.4, §6, §7.1, §7.5, §7.6, §9.1, §9.4, §9.5, §9.7, §9.8, §10.1, §10.5, §11.1, §11.6, §11.7, §11.9, §11.13, §11.16, §11.21, §11.22, §11.23, §12.1, §12.3, §12.4, §12.4.1 / `README.md` Overview, Main Features 節 / `examples/08_compliance_audit.md` / `examples/09_debugging_production.md` / `examples/12_multiprocess_logging.md` / `examples/13_external_rotation_reopen.md` / `LICENSE` / `pyproject.toml` / `MANIFEST.in`
> 本書は現行 v23j アーキテクチャの説明と評価を目的とし、改善提案・課題管理・将来ロードマップは扱わない。

## 第 5 章 機能別詳細分析

### 5.0 章の構成

本章は v23j の主要機能を**個別に**取り上げ、各機能の (a) 設計目的、(b) 動作仕様、(c) 技術的特性 を整理する。前章までで複数の文脈に跨って言及した機能も、ここで「機能単位」の視点から再度言語化する。

| 節 | 機能群 |
|---|---|
| 5.1 | Append-Only ルーティング機能群（9 モード） |
| 5.2 | 世代管理（purge / archive）と自己修復性 |
| 5.3 | external rotation との共存と `ReopenLogFiles()` |
| 5.4 | ファイル完全性検証（SHA-256 / マニフェスト） |
| 5.5 | 構造化ログと Formatter 個別指定 |
| 5.6 | コンテキスト管理（contextualize / FrozenContext） |
| 5.7 | カスタムログレベル（register_level） |
| 5.8 | コンソールカラー出力 |
| 5.9 | async transport（QueueTransport） |
| 5.10 | 5 状態ライフサイクル |
| 5.11 | `dsafelogger.mp` Writer runtime |
| 5.12 | `dsafelogger.mp` log plane / control plane |
| 5.13 | `dsafelogger.mp` 配送状態 counters |
| 5.14 | `dsafelogger.mp` bounded shutdown と flush 戦略 |
| 5.15 | TrackedQueue |
| 5.16 | 環境変数による運用制御 |
| 5.17 | INI / dict 設定の精緻 |
| 5.18 | CLI ツール |
| 5.19 | free-threaded 対応 |
| 5.20 | diagnose（変数自動展開） |
| 5.21 | sens_kws マスキング |
| 5.22 | 機能別の整理 |
| 5.23 | 本章のまとめ |

---

### 5.1 Append-Only ルーティング機能群

#### 5.1.1 設計目的

設計書 §7.2:

> **歴史的背景**: リネーム方式は「現在のログは常に `app.log`」という単純さから普及したが、ファイルロックが掛かる **Windows 環境では、別の監視ツール等がファイルを開いているだけでリネームが Permission Error となり、バックエンドサービスごとダウンさせる致命的欠陥** を抱えている。
>
> **技術的優位点**: D-SafeLogger は **Append-Only（一切のリネームを行わず、最初から日付や連番を付与したファイルへストリームを切り替えるのみ）** をアーキテクチャの前提とし、このロック問題を O(1) で完全に排除している。同様の思想は Logback や Log4j2 等の特定オプションにも見られるが、これをデフォルトの核とした設計は Python エコシステムには存在しない。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §7.2）

#### 5.1.2 9 つの routing モード

詳細設計書 §5.2 が定めるサフィックス規則:

| `routing_mode` | サフィックス形式 | 例 | 切り替え契機 | 世代管理対象 |
|---|---|---|---|---|
| `none` | なし | `Default.log` | 切り替えなし | — |
| `daily` | `_YYYYMMDD` | `Default_20260328.log` | 日付変更 | ○ |
| `hourly` | `_YYYYMMDD_HH` | `Default_20260328_14.log` | 毎正時 | ○ |
| `min_interval` | `_YYYYMMDD_HHMM` | `Default_20260328_1430.log` | 指定分間隔（60 を割り切る整数） | ○ |
| `startup_interval` | `_YYYYMMDD_HHMMSS` | `Default_20260328_143005.log` | 起動時刻基点の指定間隔 | ○ |
| `size` | `_NNN`（連番） | `Default_000.log` | `max_bytes` 超過 | ○（max_count 指定なし時のみ） |
| `count` | `_NNN`（連番） | `Default_000.log` | `max_lines` 超過 | ○（同上） |
| `cyclic_weekday` | `_ddd`（曜日略称） | `Default_thu.log` | 曜日変更 | ×（上書き、対象外） |
| `cyclic_month` | `_MM`（月番号） | `Default_03.log` | 月変更 | ×（同上） |

#### 5.1.3 RoutingStrategy 抽象基底クラス

詳細設計書 §5.1:

```python
class RoutingStrategy(ABC):
    @abstractmethod
    def get_current_path(self) -> Path: ...
    @abstractmethod
    def should_switch(self, record: logging.LogRecord) -> bool: ...
    def advance(self) -> None: ...        # ファイル切り替え後の状態更新
    def on_emit(self) -> None: ...        # v22h: レコード正常書き込み後 hook
    def is_cyclic(self) -> bool: ...      # サイクリックモードか
```

各 Strategy（`NoneStrategy` / `DailyStrategy` / `HourlyStrategy` / `MinIntervalStrategy` / `StartupIntervalStrategy` / `SizeStrategy` / `CountStrategy` / `CyclicWeekdayStrategy` / `CyclicMonthStrategy`）はこの基底を継承し、サフィックス決定と切り替え判定を実装する。

#### 5.1.4 size / count モードの分岐

設計書 §7.3.4: `max_count` の指定有無で動作目的が分岐する。

| `max_count` | 動作モード | 用途 |
|---|---|---|
| 指定あり | サイクリック上書き | ディスク満杯防止、限定領域内でのログ循環 |
| 指定なし（None） | 上限到達エラー | 「ログの欠損や意図しない上書きを絶対に防ぎたい」厳格システム |

上限到達エラーモードの動作:

- 連番は `suffix_digits` の最大値（3 桁なら `.999`）まで単調増加。
- 限界到達時にファイル切り替え時に **`OverflowError`** を送出してアプリ実行を停止。
- `backup_count > 0` または `archive_mode=True` は設計意図が矛盾するため、`ConfigureLogger()` 時に Fail-Fast（`ValueError`）。

これは「容量設計ミスを起動継続させず、停止させる」設計姿勢の典型である。

#### 5.1.5 min_interval の制約

設計書 §7.3.2: `min_interval` モードでは `interval` は数値のみ（単位: 分）で、**60 を割り切れる数のみ**指定可能（`{1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60}`）。これは「正時に揃う切り替えタイミング」を保証するための制約である。

#### 5.1.6 startup_interval の柔軟な単位指定

設計書 §7.3.3: `startup_interval` モードでは `interval` に整数のほか、`'12h'` / `'1d'` のような文字列指定も受け付ける。サフィックスは切り替え瞬間の絶対日時（`YYYYMMDD_HHMMSS`）を採用する。

#### 5.1.7 ベースファイル名の決定とサニタイズ

設計書 §7.1:

- 基本構成: `{log_path}/{pg_name}` + サフィックス + `.log`
- `log_path` ディレクトリ不在時は `os.makedirs` で自動生成
- `pg_name` のサニタイズ: OS のファイル名禁止文字（`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`）は `_` に置換（Fail-Fast ではなく、起動阻害を避けつつ安全なファイル名を生成）

#### 5.1.8 機能観察

- routing mode は**起動時に固定**され、runtime 中の動的変更は想定外。
- `none` を含めて 9 モードは `routing_mode` 引数で選択し、INI / 環境変数（モジュール別）でも上書き可能。
- 実装上は `should_switch()` を emit 直前に毎回呼ぶ pull 型の判定モデル。time-based モードでは現在時刻を都度評価する単純な実装（詳細設計書 §5.4–§5.6）。

---

### 5.2 世代管理（purge / archive）と自己修復性

#### 5.2.1 切り替えフロー（設計書 §7.5）

```text
1. Handler が Strategy に「切り替え必要か」を問い合わせ
2. 必要なら旧ストリームを close、新名のファイルを open（rename しない）
3. enable_hash=True なら HashWorker または PurgeWorker/ArchiveWorker 内で SHA-256 を生成
4. 世代管理対象なら同系統ログファイルをディレクトリ内ソートし、backup_count 超過分を特定
5. archive_mode=False → unlink、True → ZIP 化（.sha256 サイドカーも連動）
6. 失敗時は警告のみ出して次回切り替えタイミングに自己修復を委ねる
7. 同一 family の maintenance を直列化
```

#### 5.2.2 archive_mode の挙動

設計書 §7.5:

| `archive_mode` | 古いファイル処理 | サイドカーの扱い |
|---|---|---|
| `False`（既定） | `unlink` | `.sha256` サイドカーも連動削除 |
| `True` | ZIP 化 | `.sha256` サイドカーも ZIP に同梱、元ファイル削除 |

**ストレージ枯渇の未然防止**: ZIP 化処理開始前に `shutil.disk_usage()` で空き容量を検証し、不足時は処理中止 + コンソール警告。

#### 5.2.3 PurgeWorker / ArchiveWorker / HashWorker

詳細設計書 §7 / §15.5:

- すべて `threading.Thread` 派生（`daemon=True`）
- ファイル切り替え時のみ起動（Fire-and-Forget）
- safe shutdown 時は bounded wait の対象として join される
- 失敗時は stderr 警告のみで処理継続（自己修復）

#### 5.2.4 同一 family の直列化

設計書 §7.5:

> 同一 family の maintenance 直列化: 同一の `directory + pg_name` に属する purge/archive は並列実行させない。重複削除・重複 ZIP 化・競合警告の多発を避けるため、同一 family の maintenance は key 単位に直列化する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §7.5）

これは「複数の routing mode が同一の `pg_name` プレフィックスを共有する設定」での競合を排除する規約である。

#### 5.2.5 ファイル名フィルタリングの厳密化

設計書 §7.5: `pg_name` の前方一致による誤マッチ（例: `'App'` のパターンが `AppServer_*.log` にもマッチ）を防止するため、対象ファイルは次のいずれかに**正確に一致**するもののみ:

- `{pg_name}.log`（NoneStrategy）
- `{pg_name}_{サフィックス}.log`（その他の Strategy）

#### 5.2.6 max_count 指定時の世代管理対象外

設計書 §7.3.4 / §7.5:

- `size` / `count` の `max_count` 指定あり（サイクリック）→ ファイル名再利用のため**世代管理対象外**
- `cyclic_weekday` / `cyclic_month` → 同上
- これは「履歴を残さない」モードであり、世代管理の意味論と矛盾するため

#### 5.2.7 機能観察

- 世代管理は ON/OFF ではなく `backup_count > 0`（保持数）で表現される。
- archive_mode により「削除する代わりに圧縮保存する」が独立に切り替え可能。
- 自己修復性により「他プロセスがロック中で削除失敗」状態が永続的な障害にならない。

---

### 5.3 external rotation との共存と `ReopenLogFiles()`

D-SafeLogger は external rotation を完全否定しない。既存運用との共存のため、`routing_mode='none'` に限定して `ReopenLogFiles()` を提供する。

ただし、これは互換経路であり、D-SafeLogger の中心設計ではない。中心設計は、active log file を外部から rename / truncate せず、ロギング層が書き込み時点で出力先を決める append-only routing である。

`ReopenLogFiles()` は、外部 rotator が active file を動かした後に sink を再接続するための明示的な API である。これは既存運用との接続点であり、D-SafeLogger が最も安全な通常経路として推奨するものではない。

#### 5.3.1 設計目的

設計書 §7.3.1 と `examples/13_external_rotation_reopen.md`:

Linux/Unix 系で `logrotate` 等の外部ローテーターと共存する場合、本ライブラリは `routing_mode='none'` のみを正式サポートする。外部側が rename + create を実行した後、アプリケーション側が `ReopenLogFiles()` を明示呼び出しして新しい inode を再 open する。

#### 5.3.2 制約

設計書 §7.3.1:

> `daily` / `hourly` / `min_interval` / `startup_interval` / `size` / `count` / cyclic 系など D-SafeLogger 自身がファイル切替を担う routing と、外部ローテーション運用は混在させない。`ReopenLogFiles()` は writer-side のいずれかの file sink が `routing_mode != 'none'` の場合 `ValueError` を送出する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §7.3.1）

#### 5.3.3 single / multiprocess の差

設計書 §10.4 / §11.20:

| バージョン | 動作 |
|---|---|
| single-process | 同期的に file handle を reopen |
| multiprocess | control plane へ control request → ACK を待機（`CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0` 秒） |

multiprocess 版の ACK timeout の設計判断（§11.20.3）:

> 5.0 秒の根拠は logrotate / cron 運用での postrotate スクリプト実行時間の典型値（数秒以内）と、Writer 側での reopen 処理時間（通常数十 ms）の余裕を加味した値である。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.20.3）

#### 5.3.4 ネットワーク・仮想・揮発性ファイルシステムでの境界条件

ローカル POSIX ファイルシステムでは、外部 rename が成功しても writer が旧FDへ書き続ける、という形で問題が見えにくくなる。一方、NFS / SMB / CIFS / FUSE / クラウド同期フォルダ / コンテナ bind mount などでは、active log file を外部から rename / unlink する運用の失敗モードがより表面化しやすい。

NFS では、open 中ファイルの unlink が `.nfsXXXX` 形式の silly rename として現れる場合がある。client / server の挙動、cache 状態、削除競合、crash、reconnect によって、削除済みのはずのファイルが残る、容量が戻らない、`ESTALE` が返る、cleanup が失敗するといった現象が起き得る。

SMB / CIFS では、Windows 系の共有・lock・oplock / cache の影響を受ける場合がある。FUSE、クラウド同期フォルダ、コンテナ bind mount でも、rename / unlink / cache / durability semantics がローカル ext4 / xfs 等と一致するとは限らない。

また、D-MemFS 等の in-memory / virtual file system を active log の一次出力先にする場合は、rename / unlink よりも、耐久性、quota、process lifetime、明示的な export / flush の責務が主な論点になる。高速性や隔離性があっても、監査証跡としての一次保存先にするには別途の永続化戦略が必要である。

したがって、D-SafeLogger は「任意のファイルシステム上の active log を完全に安全化する」とは主張しない。D-SafeLogger が構造的に避けるのは、active file を外部から rename / truncate し、その後の signal / reopen に依存する設計である。堅牢性・監査性を重視する構成では、active log は耐久性のあるローカルファイルシステムへ出力し、close 済みの routed file だけを NFS / SMB / クラウド同期先 / アーカイブストレージへ転送する構成が望ましい。

#### 5.3.5 機能観察

- `routing_mode='none'` を明示的に「外部ローテーション共存モード」として位置づけている設計。
- 内部 routing と外部 rotation の混在を `ValueError` で拒否することにより、運用上の混乱（誰がローテーションを担うかの不明瞭化）を構造的に排除。
- `ReopenLogFiles()` は external rotation との互換経路であり、D-SafeLogger の中心的な file lifecycle ではない。
- NFS / SMB / FUSE / in-memory filesystem 等の特殊な出力先については、append-only routing が全てのファイルシステム固有リスクを消すわけではない。堅牢性を重視する場合は、active log を耐久性のあるローカルファイルシステムへ書き、close 済みファイルだけを外部ストレージへ転送する。

---

### 5.4 ファイル完全性検証（SHA-256 / マニフェスト）

#### 5.4.1 設計概要

第 4 章 §4.5 で要旨を述べたが、ここでは詳細設計書 §15 の実装レベルを取り上げる。

#### 5.4.2 ハッシュ計算の実装

詳細設計書 §15.2:

```python
def compute_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(65536)  # 64KB チャンク
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()
```

- 大容量ファイル対応のためチャンク読み（64KB 単位）。
- 標準ライブラリ `hashlib` のみ使用（zero-dep 維持）。

#### 5.4.3 サイドカー書き込みの原子性

詳細設計書 §15.3:

```python
def write_sidecar(file_path: Path, hash_value: str | None = None) -> None:
    if hash_value is None:
        hash_value = compute_sha256(file_path)
    sidecar_path = file_path.with_suffix(file_path.suffix + '.sha256')
    temp_path = sidecar_path.with_suffix(sidecar_path.suffix + '.tmp')
    temp_path.write_text(
        f'{hash_value}  {file_path.name}\n',
        encoding='utf-8',
    )
    os.replace(temp_path, sidecar_path)
```

- `.sha256.tmp` に書き込み → `os.replace()` で原子的に差し替え。
- 二重計算防止のため `hash_value` を引数で受け取れる（Purge/Archive Worker 内での先行計算を再利用）。

#### 5.4.4 マニフェスト追記の lock 順序

詳細設計書 §15.4:

```python
def append_manifest(file_path, manifest_path, hash_value=None):
    ...
    lock = _get_manifest_lock(manifest_path.resolve())
    # Lock ordering: family_lock -> manifest_lock (never reverse)
    # Do NOT acquire family maintenance lock while holding this lock
    with lock:
        with open(manifest_path, 'a', encoding='utf-8') as f:
            f.write(entry)
```

- 同一 `manifest_path` への追記は key 単位 lock で**直列化**（マニフェスト行の破損や行単位競合を防止）。
- lock ordering 規則: `family_lock → manifest_lock`（逆順禁止）。デッドロック回避のために設計上明記されている。
- ディレクトリは `parents=True, exist_ok=True` で自動生成。

#### 5.4.5 HashWorker の実装

詳細設計書 §15.5:

```python
class HashWorker(threading.Thread):
    def __init__(self, file_path, manifest_path=None):
        super().__init__(daemon=True, name=f'HashWorker-{file_path.name}')
        self._file_path = file_path
        self._manifest_path = manifest_path

    def run(self) -> None:
        try:
            def _run_body() -> None:
                write_sidecar(self._file_path)
                if self._manifest_path is not None:
                    append_manifest(self._file_path, self._manifest_path)
            _run_in_empty_context(_run_body)
        except OSError as e:
            print(f'[D-SafeLogger] Hash generation failed for ...', file=sys.stderr)
        finally:
            _unregister_worker(self)
```

注目すべき点:

- `_run_in_empty_context()` を使い、内部 thread が**親の context を継承しない**ことを保証（設計書 §9.5 の規約）。
- 失敗時は警告のみで継続（パージの自己修復性と同様）。
- thread 名にファイル名を含めるため、stuck thread を診断時に識別しやすい。

#### 5.4.6 実行順序の優先制御

設計書 §7.6.4:

| 条件 | 実行方式 |
|---|---|
| `enable_hash=True` かつ non-cyclic かつ `backup_count > 0` | PurgeWorker/ArchiveWorker 内でハッシュ生成を**先行実行** |
| `enable_hash=True` かつ non-cyclic かつ `backup_count=0` | 独立した `HashWorker` を Fire-and-Forget |
| cyclic 系 routing かつ `enable_hash=True` | `ConfigureLogger()` 時に Fail-Fast（`ValueError`） |

「ハッシュはパージより先に必ず確定する」という順序保証が設計書レベルで明記されている。

#### 5.4.7 機能観察

- HMAC 署名・CLI 検証コマンドは設計書 §7.6.7 で明示的にスコープ外。
- `sha256sum -c` 互換フォーマット採用により OS 標準ツールで検証可能。
- マニフェストにより「ファイル消失」も検知できる（サイドカーのみでは検知不可能）。

---

### 5.5 構造化ログと Formatter 個別指定

#### 5.5.1 デフォルトフォーマット

設計書 §6.1:

```text
%(asctime)s.%(msecs)03d [%(levelname)-3s][%(filename)s:%(lineno)s:%(funcName)s] %(message)s
```

- 日時形式: `%Y-%m-%d %H:%M:%S`
- レベル名略称: `DBG` / `INF` / `WAR` / `ERR` / `CRI`（および `register_level()` 登録済みカスタムレベルの 3 文字略称）
- Contextualize 情報はメッセージ末尾に `[task_id:42 worker:db_sync]` 形式で付加

#### 5.5.2 構造化ログ（JSON Lines）

設計書 §6.4: `ConfigureLogger(structured=True)` で 1 行 1 JSON への切り替え。Append-Only アーキテクチャと**完全に直交**するため、ルーティングや世代管理は変更なくそのまま動作する。

`structured=True` 時の規約:

- `contextualize()` で付与されたコンテキストはトップレベルフィールドとして出力
- `fmt` / `file_fmt` / `console_fmt` への文字列指定および Formatter インスタンス指定との同時指定は **`ValueError`**（排他指定違反）

#### 5.5.3 Formatter 個別指定（v20 新機能）

設計書 §6.3:

```python
ConfigureLogger(
    file_fmt=StructuredFormatter(),
    console_fmt='%(levelname)s %(message)s',
)
```

解決優先度:

```text
file_fmt が指定 → ファイル Sink に使用
file_fmt が None または空文字列 → fmt にフォールバック
fmt も None → デフォルトフォーマット
（console_fmt も同様）
```

- `fmt` は既存の全体デフォルト Formatter（後方互換維持）
- `file_fmt` / `console_fmt` は `str` または `logging.Formatter` インスタンス
- INI / config_dict でも対応キーを設定可能（§5.3）
- 環境変数からの設定は非対応（Formatter インスタンスは環境変数で表現不可能なため）
- `file_fmt` / `console_fmt` を指定しなければ v18 と完全に同一の動作（非破壊的変更）

#### 5.5.4 4 つの Formatter 系統

詳細設計書 §4:

| クラス | 役割 |
|---|---|
| `DSafeFormatter` | テキスト出力（デフォルトフォーマット）。`%` / `{}` / `$` の全 style 対応 |
| `StructuredFormatter` | JSON Lines。`contextualize()` 情報をトップレベルへ。`extra` 属性は vendor-neutral なものを JSON へ出力（標準 `LogRecord` キーと内部 `_ds_*` 属性は除外） |
| `DiagnosticFormatter` | `diagnose=True` 時のテキスト出力。`f_locals` を展開 |
| `DiagnosticStructuredFormatter` | `diagnose=True` かつ `structured=True`。`f_locals` を JSON `locals` フィールドへ |

#### 5.5.5 multiprocess 版の Formatter spec

詳細設計書 §15a.5.2a:

multiprocess 版では Formatter インスタンスが pickle 不能な場合があるため、`kind + constructor args` の picklable spec として渡す。

```python
class FormatterSpec(TypedDict, total=False):
    kind: Literal[
        'logging.Formatter',
        'DSafeFormatter',
        'DiagnosticFormatter',
        'StructuredFormatter',
        'DiagnosticStructuredFormatter',
    ]
```

設計書 §10.5 規定:

> multiprocess 版の `fmt` / `file_fmt` / `console_fmt` は single-process 版と同じ型面を許容するが、process 境界で freeze / 再構築を許可するのは **`logging.Formatter` 本体および D-SafeLogger 組み込み Formatter 本体** のインスタンスに限る。
>
> 上記 allow-list 以外の custom formatter instance（custom subclass を含む）は `TypeError` とし、Writer 側では `kind + constructor args` からなる picklable spec だけを受け渡す。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §10.5）

#### 5.5.6 機能観察

- 構造化ログとカスタムフォーマットは排他（同一機能を別経路で実現することによる意味論衝突を回避）。
- Formatter 個別指定により、ファイル（観測ツール向け JSON）とコンソール（人間可読テキスト）を異なる形式で同時出力可能。
- multiprocess 経由でも custom Formatter は allow-list に従って制約され、pickle 不能問題が構造的に回避される。

---

### 5.6 コンテキスト管理（contextualize / FrozenContext）

#### 5.6.1 設計目的

設計書 §2 / §9.5:

- スレッドだけでなく asyncio タスク間でも独立分離するコンテキスト管理。
- producer 側で hand-off 時に snapshot し、consumer 側 / Writer 側は live `contextvars` を参照しない。
- async / multiprocess 経由の hand-off コストを **O(1) 参照渡し**に抑制（v20 No-Copy Snapshot）。

#### 5.6.2 FrozenContext の実装

設計書 §9.5:

- `contextvars.ContextVar[MappingProxyType]` を採用（v20 で `ContextVar[dict]` から変更）。
- `MappingProxyType` の immutability により snapshot は O(1) 参照渡し。
- `contextualize()` 入口での新 MappingProxyType 生成は O(n)。

#### 5.6.3 mutable 値の Fail-Fast 拒否

設計書 §2:

> `contextualize()` の kwargs には **immutable な値（str, int, float, tuple 等）のみを渡すこと**。contextualize() に渡された kwargs の値が list, dict, set 等の代表的な mutable オブジェクトであった場合、TypeError または ValueError を送出する (Fail-Fast)。これにより、O(1) 参照渡しによる意図しない副作用を開発時に確実に検知する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §2）

注釈: `MappingProxyType` はトップレベルキー操作のみ保護し、値が mutable（list, dict 等）の場合は内容変更を防げない。これは仕様上の明示。

#### 5.6.4 sync mode と async mode の hand-off 規則

設計書 §9.5:

- **sync mode**: Formatter が `contextvars` から直接取得（サードパーティ標準 Logger への透過性のため）
- **async mode**: consumer thread 側の `contextvars` を信頼せず、producer thread 側で `LogRecord` へ付与した `FrozenContext` 参照を優先

#### 5.6.5 thread 境界の意味論

設計書 §9.5:

- ユーザーが生成した新規 thread への初期 context 継承は Python 本体仕様に従う
- D-SafeLogger 自身が生成する内部 thread は**常に空 `Context` で開始**する → 内部 thread への context 漏洩を防止

#### 5.6.6 context snapshot fallback の正確化（v21）

設計書 §2:

Formatter での context 返却を `getattr(record, '_ds_context', None) or get_context()` パターンから `hasattr` ベース分岐に変更:

- `_ds_context` 属性が存在する場合は**空の `MappingProxyType` でも authoritative な snapshot として扱う**
- Transport を経由しない直接呼び出し時のみ `get_context()` にフォールバック

これは「IPC 経由で空 context が来た場合に、Writer 側で live context を勝手に参照する」事故を防ぐ。

#### 5.6.7 multiprocess 規約: `_ds_context` / `_ds_extra` の常在

設計書 §11.8.2:

> `_ds_context` と `_ds_extra` は常に key として存在し、空は `{}` で表現する。
>
> 補足: この常在規約は v21 で確立した hasattr ベースの context snapshot fallback を IPC 境界で維持するために必要な規約である。pickle 経由で `LogEvent` を受け取った Writer 側では hasattr による区別が成立しないため、key 存在で「Capture 側で snapshot 取得済み」であることを明示し、Writer 側で live context 参照が発生しないことを保証する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.8.2）

#### 5.6.8 機能観察

- `contextualize()` のスコープを抜けると Token による状態巻き戻しが行われる（標準的な ContextVar 巻き戻しパターン）。
- `examples/06_web_api_logging.md` は request_id / user_id 等を `contextualize()` で attach する典型パターンを提示。
- structured=True と組み合わせると、context フィールドが JSON トップレベルに出る。

---

### 5.7 カスタムログレベル（register_level）

#### 5.7.1 機能仕様

設計書 §9.9:

```python
register_level(name='TRACE', value=5, abbreviation='TRC', color='\033[90m')
```

- `name`: レベル名（例: TRACE）
- `value`: ログレベル数値（標準 5 段階以外）
- `abbreviation`: 3 文字略称（例: TRC）
- `color`: ANSI カラーコード

#### 5.7.2 呼び出し順序の強制

設計書 §9.9.2:

```text
register_level()    ← 任意回数（0回でもよい）
     ↓
ConfigureLogger()   ← 1回のみ
     ↓
GetLogger()         ← 任意回数
```

`ConfigureLogger()` 後の `register_level()` は `RuntimeError`。`shutting_down` 状態も同様に拒否（terminating 中の追加登録は shared state を不安定化させるため）。

#### 5.7.3 ビルトインレベルの保護

設計書 §9.9.3: 以下の操作は全て `ValueError` として拒否:

- ビルトイン値（10, 20, 30, 40, 50）の上書き
- ビルトイン名（DEBUG, INFO, WARNING, ERROR, CRITICAL）の上書き
- ビルトイン略称（DBG, INF, WAR, ERR, CRI）の上書き

#### 5.7.4 3 層パイプライン全層との整合

設計書 §9.9.4: `register_level('TRACE', ...)` 後は次の全層で `'TRACE'` が使用可能になる:

- 引数: `ConfigureLogger(default_level='TRACE', ...)`
- INI: `default_level = TRACE` または `[dsafelogger:mod]` の `level = TRACE`
- 環境変数: `D_LOG_LEVEL=TRACE` または `D_LOG_MODULES=mymod:TRACE`

未登録のレベル名を指定した場合は Fail-Fast バリデーションにより `ValueError`。

#### 5.7.5 便利メソッドの動的生成

設計書 §9.9.5:

- `register_level('TRACE', value=5, ...)` → `DSafeLogger` に `logger.trace(msg)` メソッドが動的追加
- 既存メソッド名（`logger.info()` 等）と衝突する場合は便利メソッドの追加はスキップ（`logger.log(value, msg)` は使用可能）
- mypy / pyright で型エラーになるため、`logger.log(VALUE, msg)` の使用または `# type: ignore[attr-defined]` の付与をドキュメントに記載

#### 5.7.6 spawn worker での再 import ルール

設計書 §10.3:

- spawn worker の bootstrap では、モジュールトップレベルの `register_level()` が再実行されることがある
- **同一定義**（name / value / abbreviation / color が完全一致）の再登録は**冪等 no-op**として許容
- **不一致再登録**は registry divergence とみなし `RuntimeError`

これにより、モジュールトップレベルに `register_level()` を書く通常の記述スタイルを spawn 環境でも維持できる。

#### 5.7.7 multiprocess registry hash 照合

設計書 §11.7: registry hash（SHA-256）は `ctx` に含められ、Writer bootstrap ready ACK 時と `AttachCurrentProcess(ctx)` 実行時に照合される。不一致は `RuntimeError` で Fail-Fast。

#### 5.7.8 機能観察

- 拡張は `ConfigureLogger` 前に閉じる（初期化境界を越える動的変更を許さない）。
- ビルトインレベルは「不可侵の聖域」として保護。
- spawn 再 import の冪等扱いにより、Python 標準のモジュールロード規則と整合。

---

### 5.8 コンソールカラー出力

#### 5.8.1 設計目的

設計書 §9.6: コンソール出力先のデフォルトは `sys.stderr`。ANSI カラーコードは略称化済みの表示用レベル値に対して付与する。Windows 向けには初期化時に `os.system("")` で VT100 を有効化。

#### 5.8.2 LEVEL_MAP / COLOR_MAP のインスタンス変数化

設計書 §9.8 / §9.9.6:

- `DSafeFormatter.LEVEL_MAP` および `ColorStreamHandler.COLOR_MAP` は**クラス変数ではなくインスタンス変数**として、Formatter 初期化時にビルトイン 5 段階 + カスタムレベルの統合マップを構築。
- これにより同一プロセス内で複数の Formatter インスタンスが異なるレベル登録状態を持ちうる。

#### 5.8.3 カラーパレット設定（INI / dict 専用）

設計書 §9.6 / §5.3:

- ビルトイン 5 段階のカラーパレットは INI / config_dict の `[global]` セクションで `color_{略称の小文字}` キーにより変更可能（例: `color_dbg = 36`、`color_inf = 32`、`color_war = 33`、`color_err = 31`、`color_cri = 1;31`）。
- 値は ANSI SGR パラメータの数値部分（例: `36`、`1;31`、`38;5;208`）。
- カスタムレベルのカラーも同一の命名規則で上書き可能。
- 環境変数・引数からの設定は意図的に非対応（**第 2 層専用**）。

#### 5.8.4 カラーパレットのマージ順序

設計書 §9.6:

```text
(1) ビルトインデフォルト
  → (2) register_level() 指定カラー
    → (3) INI/辞書の color_{略称} キー（最終上書き）
```

#### 5.8.5 `color_{略称}` キーのバリデーション

設計書 §5.3:

- **未知略称**: `color_` の後ろの部分が有効な略称（ビルトイン + カスタムレベル）に一致しない場合、stderr 警告 + キー無視
- **不正文字**: 値に `0-9` と `;` 以外の文字が含まれている場合、stderr 警告 + キー無視
- **空文字列**: 有効。該当レベルのカラー化を無効化
- いずれも Fail-Fast ではなく警告 + スキップで処理継続（他の有効なカラー設定の適用は妨げない）

#### 5.8.6 カラー制御の優先順位

設計書 §4.5:

```text
1. NO_COLOR が設定されていれば、値を問わず常にカラー無効
2. NO_COLOR 未設定で {prefix}_COLOR が設定されていれば、その値に従う
3. 両者とも未設定の場合は、sys.stderr.isatty() でTTY判定して自動決定
```

`NO_COLOR` は業界標準（https://no-color.org/）であり、`env_prefix` の影響を受けない唯一の環境変数。

#### 5.8.7 機能観察

- カラーパレット設定が第 2 層専用（環境変数・引数で設定不可）なのは設計上の意図的な制限。色設定は「組織内の標準テーマ」として INI で管理する想定。
- `color_dbg = ` のような空文字列で個別レベルのカラーを無効化できる柔軟性。
- ColorStreamHandler は `_ds_required = False`（best-effort sink）であり、失敗しても `_writer_best_effort_failures` に計上されるのみ（`reject_counter` には集約されない）。

---

### 5.9 async transport（QueueTransport）

#### 5.9.1 アーキテクチャ

詳細設計書 §15a.3:

```python
class QueueTransport(Transport):
    def __init__(self, handlers, **kwargs):
        self._queue = queue.Queue(-1)
        self._queue_handler = DSafeQueueHandler(self._queue, **kwargs)
        self._listener = DSafeQueueListener(self._queue, *handlers)

    def start(self):
        self._listener.start()

    def stop(self, timeout):
        return self._listener.stop_with_timeout(timeout)

    def get_root_handlers(self):
        return [self._queue_handler]

    def get_sink_handlers(self):
        return list(self._listener.handlers)
```

#### 5.9.2 DSafeQueueHandler の完全オーバーライド

設計書 §9.3:

- D-SafeLogger の queue hand-off は stdlib `QueueHandler.prepare()` をそのまま使わず、`super().prepare()` も呼ばない**完全オーバーライド**
- 理由: Python 3.11 / 3.13 / 3.14 間の stdlib 差異を意味論から切り離すため

producer thread 側の責務:

- `contextualize()` 情報を `LogRecord` の private 属性 `_ds_context` へ snapshot
- `diagnose=True` かつ `exc_info` ありの場合のみ `f_locals` をマスク済み repr スナップショットに変換 (`_ds_diag_frames`)
- 通常ログでは copy + context snapshot の軽量 hand-off

#### 5.9.3 安全な終了の保証レベル

設計書 §9.3:

- **ログ本体の flush**: 最優先。通常終了時は queue drain が成功した限り、shutdown 開始前に受理済みの queued log record の出力完了を目指す。
- **housekeeping (hash / purge / archive)**: best-effort。bounded wait を行うが、timeout 時は warning を出して終了を優先。

#### 5.9.4 推奨終了順序

設計書 §9.3:

```text
1. 状態遷移と参照退避
2. queue drain
3. worker join
4. handler flush/close
```

特に worker join より先に listener を停止する。listener が最後の queued record を処理する過程で rollover を起こし、新しい worker を起動しうるため。

#### 5.9.5 daemon=True の位置づけ

設計書 §9.3:

> daemon thread は shutdown 時に abrupt に停止しうるため、通常終了時の安全性根拠にはしない。`daemon=True` は異常終了時の backstop にとどめる。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §9.3）

#### 5.9.6 timeout の分離

設計書 §9.3:

shutdown では queue drain timeout と worker join timeout を分離する。late finalization により `join()` が継続不能な場合は warning に degrade し、終了を優先。

#### 5.9.7 module-specific path の Transport 完全統合（v21）

設計書 §2:

- `is_async=True` の意味論を root 経路だけでなく module-specific path 経路にも一貫適用
- `Pipeline` は `module_transports: dict[str, Transport]` を保持し、`stop()` 時に全 Transport を構造的に停止
- module logger への handler attach は `pipeline.get_module_handler()` を経由

#### 5.9.8 機能観察

- `is_async=True` は GUI スレッド・request handler スレッドが I/O blocking しない用途で有効。
- `examples/11_async_performance.md` が典型用途を示す（高スループット）。
- multiprocess 版で `is_async=True` を併用すると process-local async queue + multiprocess log queue + Writer dispatch の二重キューイング（§11.17）。

---

### 5.10 5 状態ライフサイクル

#### 5.10.1 状態定義

設計書 §9.2:

| 状態 | 意味 |
|---|---|
| `unconfigured` | 初期状態 |
| `auto` | `GetLogger()` 先行で auto-fire 初期化された状態 |
| `explicit` | アプリケーションコードから明示的に `ConfigureLogger()` が呼ばれた状態 |
| `configuring` | `ConfigureLogger` 実行途中の内部状態（`_lifecycle_lock` 保持下） |
| `shutting_down` | `_shutdown()` 実行途中の内部状態 |

#### 5.10.2 状態遷移表（再掲）

設計書 §9.2:

| 現在 | イベント | 遷移先 |
|------|---------|--------|
| `unconfigured` | `ConfigureLogger()` | `configuring` |
| `unconfigured` | `GetLogger()` 先行 | `configuring` (auto-fire) |
| `configuring` | 正常完了 | `explicit` or `auto` |
| `configuring` | 例外発生 | `unconfigured` (rollback) |
| `configuring` | 同一 thread 再入 | No-Op return |
| `auto` | `ConfigureLogger()` | `configuring`（旧 Pipeline 停止 → 再初期化） |
| `auto` | `_shutdown()` | `shutting_down` |
| `explicit` | `ConfigureLogger()` | **No-Op return** |
| `explicit` | `_shutdown()` | `shutting_down` |
| `shutting_down` | 完了 | `unconfigured` |
| `shutting_down` | `ConfigureLogger()` | No-Op |

#### 5.10.3 並行安全性の規約

設計書 §9.2:

- `_lifecycle_lock` は `RLock`。同一 thread の再入は No-Op、別 thread は lock acquire 待機後に状態を再評価。
- `configuring` 中の例外処理: `try/finally` により `_configure_state` が `configuring` のまま残ることを防止。
- `configuring` 中の `GetLogger`: 別 thread では初期化完了まで待機、同一 thread の再入のみ既存 logger 返却で短絡。
- `shutting_down` 中の `ConfigureLogger`: 新規初期化を行わず、No-Op または明示的拒否。
- `shutting_down` 中の `register_level()`: `RuntimeError`。

#### 5.10.4 v21 改訂

設計書 §2 v21 改訂:

- `ConfigureLogger` の `_do_configure()` 全体を `_lifecycle_lock` 保持下で実行。
- `GetLogger` は `'configuring'` 状態を検出して lock 構造待機を行う。
- 初期化中の中途状態読み取りを並行安全に防止。

#### 5.10.5 機能観察

- 5 状態 + RLock により、auto-fire / 明示初期化 / 再初期化 / shutdown が単一の状態機械で表現される。
- `auto` → `explicit` の昇格（明示優先）は許容されるが、`explicit` の再 `ConfigureLogger()` は No-Op（既知の挙動として保証）。
- multiprocess 版（`mp.ConfigureLogger`）は同一 process 内 2 回目を **`RuntimeError`** とし、single-process より厳格。

---

### 5.11 `dsafelogger.mp` Writer runtime

#### 5.11.1 Writer runtime の責務

設計書 §11.5 / §11.6:

- file sink 群を所有
- log plane queue から `LogEvent` を受信
- route に応じて sink group を選択
- control plane から `ATTACH` / `DETACH` / `REOPEN` / `STOP` / `STATUS` を受信
- file switch / routing / hash / manifest / purge / archive
- reopen / shutdown の直列化
- active client 数と stop 要求に基づいて安全終了

#### 5.11.2 Writer runtime は内部実装

設計書 §11.5:

> Writer runtime はロガー内部の実装要素であり、開発者が明示的に `multiprocessing.Process` / `subprocess.Popen` 等を使って直接起動する対象ではない。開発者が知るべき契約は `ctx`、`AttachCurrentProcess()`、`DetachCurrentProcess()` に限定する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.5）

#### 5.11.3 protocol payload（詳細設計書 §15a.5.1）

```python
@dataclass(frozen=True)
class BootstrapContext:
    protocol_version: int
    session_id: str
    writer_pid: int
    log_queue: multiprocessing.Queue
    control_queue: multiprocessing.Queue
    resolved_config: dict[str, object]
    resolved_config_digest: str
    registry_hash: str
    log_queue_maxsize: int
    ipc_log_timeout: float
    overflow_policy: Literal['drop']
```

#### 5.11.4 LogEvent の構造

```python
class LogEvent(TypedDict):
    name: str
    levelno: int
    levelname: str
    pathname: str
    filename: str
    module: str
    lineno: int
    funcName: str
    msg: str
    created: float
    msecs: float
    relativeCreated: float
    process: int
    processName: str
    thread: int
    threadName: str
    _ds_route: str
    _ds_context: dict[str, Any]
    _ds_exc_text: str | None
    _ds_diag_frames: list[dict[str, Any]] | None
    _ds_extra: dict[str, Any]
```

#### 5.11.5 `_serialize_record()` / `_reconstruct_record()` の責務分離

詳細設計書 §15a.5.2:

- `LogEvent` は client 側 Capture 境界で確定する
- `_ds_context` と `_ds_extra` は常に key を持ち、空は `{}` とする
- diagnose snapshot は client 側で確定し、Writer 側で live traceback / live context を再評価しない
- `_reconstruct_record()` は `logging.makeLogRecord()` を使って sink dispatch 用 `LogRecord` を復元するだけであり、**logger 階層評価や level 判定は再実行しない**

これは「Capture 意味論は Capture 層の責務」という設計書 §11.3 の規定の実装上の現れである。

#### 5.11.6 機能観察

- Writer runtime は内部 process として実装され、`multiprocessing.Process` で起動。
- ファイル所有・routing・hash・manifest・purge・archive・reopen のすべてが Writer に集約される。
- worker process は IPC で `LogEvent` を送るのみで、ファイル操作を行わない（§4.6.1）。

---

### 5.12 `dsafelogger.mp` log plane / control plane

#### 5.12.1 log plane

設計書 §11.9.1:

- client → Writer の片方向
- payload は `LogEvent`
- internal transport は **bounded `multiprocessing.Queue`**（v23h: `TrackedQueue` 派生）
- ファイル書き込み経路の主経路

#### 5.12.2 control plane

設計書 §11.9.2:

- `reopen` / `attach` / `detach` / `stop` / `status` を扱う
- request / ACK を持つ
- `ReopenLogFiles()` は control plane を使う**同期 API**
- ACK は **per-request の `multiprocessing.Pipe(duplex=False)` reply path** で返される（§11.8.3）
- command 種別ごとに異なる QoS を持つ

#### 5.12.3 command 種別ごとの QoS

設計書 §11.16.3:

| command | QoS |
|---|---|
| `ATTACH` / `DETACH` / `STOP` | **drop 不可** |
| `REOPEN` / `STATUS` | **ACK 必須** |
| `LOG` の overflow 方針は control plane command へ適用しない |

#### 5.12.4 設計原則

設計書 §11.9:

- control command を通常ログ queue に混在させない
- ACK を log plane に混在させない
- 非 picklable な同期オブジェクトを control payload に含めない
- Queue を別 Queue の payload として送らない（Queue-in-Queue 方式は Python `multiprocessing` 制約上成立しないため不採用）
- Pipe send/recv failure は raw `BrokenPipeError` / `EOFError` のまま外へ漏らさず、control plane failure として `RuntimeError` 系へ正規化

#### 5.12.5 ControlRequest の構造

詳細設計書 §15a.5.1:

```python
class ControlRequest(TypedDict):
    request_id: str
    client_id: str
    command: Literal['ATTACH', 'DETACH', 'REOPEN', 'STOP', 'STATUS']
    reply_to: Any  # multiprocessing.connection.Connection (Pipe send end)
    payload: dict[str, Any]
```

#### 5.12.6 機能観察

- log plane と control plane の分離は「ACK timeout・request 直列化・QoS・エラー伝達が通常ログとは異なる意味論を持つため」（§11.9）の理由付き設計判断。
- per-request Pipe による reply path は Queue-in-Queue 方式の代替として固定（§11.8.3）。

---

### 5.13 `dsafelogger.mp` 配送状態 counters

#### 5.13.1 配送状態の階層構造（再掲、§2.8.14）

設計書 §12.3:

**Lifecycle states**: attempted → accepted → enqueued → delivered_per_sink → delivered

**Terminal states**: rejected / dropped / writer_reject / partial_delivered / unexpected_loss / writer_best_effort_failures（別計上）

**Policy qualifier**: overload_shed

#### 5.13.2 sink 分類による per-record 計上規則（v23h、§12.3）

各 handler は `_ds_required: bool` クラス属性で required / best-effort を区別する。

| handler | `_ds_required` | 意味 |
|---|---|---|
| `AppendOnlyFileHandler` | `True`（既定） | required sink。delivered 判定の対象 |
| `ColorStreamHandler` | `False` | best-effort sink。delivered 判定外、失敗は別計上 |
| 利用者独自の `logging.Handler` 派生 | 属性なし → `True` 扱い | 独自 handler は default required |

per-record 計上規則:

- 全 required handler が成功 → `delivered`（counter 増分なし）
- 全 required handler が失敗 → `_reject_counter += 1`、`writer_sink_reject` または `writer_policy_reject` を増分（双方の原因が混在する record では両方を increment）
- 一部の required handler のみ成功 → `_writer_partial_delivered += 1`（terminal state は `partial_delivered` であり、`writer_sink_reject` / `writer_policy_reject` は increment しない）
- best-effort handler の失敗 → `_writer_best_effort_failures += 1` のみ（`reject_counter` への集約なし）

#### 5.13.3 partial_delivered の成立条件

設計書 §12.3:

> partial_delivered と単一 handler route: `partial_delivered` は required sink set 内で「成功と失敗が混在した」状態を示す terminal state である。required sink set が 1 個（典型的な `root` route や module route の file 単一構成）のときは partial の概念が成立しないため、counter は常に 0 のままである。partial が観測されるのは、利用者が同一 route に複数の required handler を登録した構成に限られる。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §12.3）

#### 5.13.4 writer_reject の 6 内訳（v23h）

設計書 §12.3:

| 分類 | 定義 |
|---|---|
| `writer_route_reject` | route 解決不能、または route 対象 sink 不在 |
| `writer_reconstruct_reject` | LogEvent の破損 / reconstruct failure（v23h で `writer_event_reject` から分離） |
| `writer_close_marker_reject` | CloseMarker の不正（client_id 欠落 / session mismatch / 未知 client、v23h で分離） |
| `writer_sink_reject` | required sink が存在するが emit / write / flush で失敗（per record） |
| `writer_policy_reject` | required handler の filter または Writer 側 policy で配送拒否（per record） |
| `writer_format_reject` | formatter / JSON encode 不能（v23h では `writer_sink_reject` に畳み込み） |

すべてに**専用 counter と stderr warning（rate-limited）**が割り当てられる。

#### 5.13.5 client 側 drop counter

設計書 §11.22.1: 次のような事象で client 側 counter を増分:

- log queue `put()` timeout / `queue.Full`
- attach 不在での送信失敗
- control plane 送信失敗に伴う command failure

#### 5.13.6 Writer 側 drop / reject counter

設計書 §11.22.2: 次のような事象で Writer 側 counter を増分:

- protocol failure
- route failure（unknown route は reject counter 増分 + stderr warning。root への暗黙フォールバックは禁止）
- sink failure に伴う discard

#### 5.13.7 出力先とタイミング

設計書 §11.22.3:

- 少なくとも stderr warning により可視化
- shutdown 時には summary を出す
- public getter API は v22h 基本設計の必須要件としない

#### 5.13.8 Writer exit code

設計書 §11.22.4:

- 正常終了は exit code 0
- 異常終了は非 0
- 親 / 呼び出し元 process は、Writer exit code が非 0 の場合 stderr warning を出す

#### 5.13.9 機能観察

- 配送失敗の分類粒度が高く、運用時にどの段階で失敗したかを特定可能。
- silent drop / silent loss が許されないため、すべての異常事象が counter または warning に出る。
- `unexpected_loss` のみが「バグ扱い」として区別される。

---

### 5.14 `dsafelogger.mp` bounded shutdown と flush 戦略

#### 5.14.1 Bounded shutdown 契約（v23h、§12.4.1）

`mp.ConfigureLogger()` は `atexit` で `_mp_shutdown` → `WriterRuntime.stop()` を呼び出す。`stop()` は次の bounded 契約に従う:

- `stop(timeout)` は最大 `timeout` 秒（既定 `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0`）だけ `log_thread` / `control_thread` の join を待つ
- timeout 後に thread が生存していた場合、stderr に visible warning を出力（stuck thread 名を含めて、silent failure にしない）
- Writer の `log_thread` / `control_thread` は **`daemon=True`** で起動するため、stop() が drain を完了できなかった場合でも Python interpreter は exit できる（process survives 原則）

```text
bounded wait (≤ timeout) → visible warning (drain incomplete を可視化) → process exits
```

#### 5.14.2 shutdown ordering

設計書 §11.21.3:

```text
1. client 側 async queue を drain
2. client から Writer への送信を完了
3. client が detach / close を送信
4. Writer 側が log plane queue を drain
5. Writer 側が sink handlers を close / hash / manifest finalize
6. Writer runtime が終了
```

#### 5.14.3 stop 判定

設計書 §11.21.2:

Writer は次の両条件を満たしたとき shutdown へ進む:
1. main 側から stop request を受けたこと
2. active client 数が 0 であること

main process の shutdown helper は、Writer thread の join 待機に入る前に**自 process client の detach を完了**させなければならない。

#### 5.14.4 worker crash 時の registry 整合

設計書 §11.21.2:

- worker process が `DETACH` を送らずに終了した場合、Writer の active client registry に残存が生じうる
- shutdown 中の active client 数 0 待ちには内部 timeout を設ける
- timeout 到達時は stderr warning を出し、強制 stop へ移行
- silent hang を起こしてはならない
- 定期的な liveness probe による能動的残存検知は将来拡張とし、基本設計の必須要件とはしない

#### 5.14.5 flush 戦略（v23g、§11.27）

| `writer_flush_batch` | 動作 | 想定用途 |
|---|---|---|
| `1`（既定） | per-message flush。Writer process crash 時の loss なし | 高 durability 要求 |
| `2 – 64` | N 件ごと flush + queue empty 時 idle flush。process crash 時最大 N-1 件 loss 可能性 | スループット優先 |
| `> 64` | 同上、ただし可視性低下リスク高 | 特殊用途 |

環境変数 `{prefix}_WRITER_FLUSH_BATCH` で上書き可能。`<= 0` で `ValueError`、`> 1024` で warning。`WriterRuntime.__init__` でも `ctx.writer_flush_batch < 1` を `ValueError` として弾く（`BootstrapContext` 直接構築経路の安全網）。

#### 5.14.6 §12.3 用語との対応

設計書 §11.27:

- `writer_flush_batch=1` の場合: dispatch 完了 = `delivered_per_sink` と一致
- `writer_flush_batch>1` の場合: batch flush 完了点を `delivered_per_sink` の到達点とする。**ユーザーが opt-in した時点で per-message visibility は保証されない**

#### 5.14.7 Writer による Sink flush 制御の責務分担

設計書 §11.27:

multiprocess 経路では、Sink（`AppendOnlyFileHandler`）の `stream_flush_on_emit` を Configure 層（`mp/__init__.py` の `_build_writer_sink_groups`）が `False` に設定し、Writer（`_mp_runtime.py`）が batch / per-message を統一制御する。

#### 5.14.8 機能観察

- 既定では durability を弱化させない（`writer_flush_batch=1`）。
- opt-in 時は per-message visibility が保証されない旨を仕様で明示し、契約を明確化。
- daemon=True と bounded join により「process exits」を fail-safe として実現。

---

### 5.15 TrackedQueue（v23h）

#### 5.15.1 設計目的

設計書 §11.16.1:

log plane queue の実装は `multiprocessing.queues.Queue` 派生の `TrackedQueue` を用いる。

#### 5.15.2 native qsize fallback の実装

> コンストラクタで `super().qsize()` を**例外プローブ**して `NotImplementedError` を捕捉した場合のみ `multiprocessing.Value` カウンタへ自動 fallback する。OS 名（macOS など）には依存しない判別であるため、未来の or マイナーな未対応プラットフォームでも追加対応なしに正しく動作する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §11.16.1）

#### 5.15.3 機能観察

- macOS など `Queue.qsize()` が `NotImplementedError` を返すプラットフォームで、`Value` カウンタによる qsize 提供にシームレスに切り替わる。
- OS 名による分岐ではなく動作プローブによる判別なので、未来のプラットフォームに対する移植耐性が高い。

---

### 5.16 環境変数による運用制御

#### 5.16.1 環境変数の全一覧（再掲、§2.3.3）

| 環境変数 | 用途 | 有効値 |
|---|---|---|
| `{prefix}_LEVEL` | グローバルデフォルトレベル | `DEBUG` 〜 `CRITICAL` + 登録済みカスタムレベル名 |
| `{prefix}_MODULES` | モジュール別レベル/出力先 | `MOD:LEVEL[,...]` または `MOD:LEVEL:PATH[,...]` |
| `{prefix}_DIAGNOSE` | 診断モード | `"1"` のみ有効 |
| `{prefix}_CONSOLE` | コンソール出力強制制御 | `"1"/"0"`, `"true"/"false"` |
| `{prefix}_COLOR` | カラー出力強制制御 | `"1"/"0"`, `"true"/"false"` |
| `{prefix}_CONFIG` | INI ファイルパス上書き | ファイルパス |
| `{prefix}_HASH` | ハッシュ生成有効化 | `"1"/"0"`, `"true"/"false"` |
| `{prefix}_MANIFEST` | マニフェストファイルパス上書き | ファイルパス |
| `{prefix}_IPC_LOG_TIMEOUT` | mp 版 log plane 送信待機時間 | 正の浮動小数点秒数 |
| `{prefix}_IPC_LOG_QUEUE_MAXSIZE` | mp 版 log plane queue 容量 | 正の整数 |
| `{prefix}_IPC_CLIENT_QUEUE_MAXSIZE` | mp 版 process-local async queue 容量 | 正の整数 |
| `{prefix}_WRITER_FLUSH_BATCH` | mp 版 Writer flush batch サイズ | 正の整数 |
| `NO_COLOR` | カラー出力強制無効化 | 設定されていれば（業界標準、`env_prefix` 影響を受けない） |

#### 5.16.2 静的反映原則

設計書 §4 冒頭:

> 本章の環境変数は、**プロセス稼働中に動的反映されるものではない**。変更を反映するには、対象プロセスの再起動、または `ConfigureLogger` が再実行される初期化経路が必要である。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §4）

#### 5.16.3 各環境変数の特殊規約

| 環境変数 | 特殊規約 |
|---|---|
| `{prefix}_LEVEL` | カンマ区切りはエラー（`MODULES` への移行を促すメッセージ）|
| `{prefix}_MODULES` | 個別 `MOD_SPEC` 書式違反は当該要素のみ stderr 警告 + スキップ（他要素は適用継続） |
| `{prefix}_DIAGNOSE` | `"1"` のみ有効。`"true"` 等は無効値として扱う |
| `{prefix}_CONFIG` | `config_file` だけでなく `config_dict` も上書き |
| `{prefix}_IPC_LOG_TIMEOUT` | v23h で fail-fast 化（解釈不能値で `ValueError`） |
| `{prefix}_IPC_LOG_QUEUE_MAXSIZE` / `IPC_CLIENT_QUEUE_MAXSIZE` | 同上 |
| `{prefix}_WRITER_FLUSH_BATCH` | 同上 |
| `NO_COLOR` | `env_prefix` の影響を受けない唯一の環境変数（業界標準） |

#### 5.16.4 機能観察

- `NO_COLOR` の業界標準への準拠は、本ライブラリが「自前の規格を作らず、既存標準に乗る」姿勢を示す。
- v23h での fail-fast 化は「環境変数値の解釈ミスを silent ignore せず、起動時に明示する」方向の強化。

---

### 5.17 INI / dict 設定の精緻

#### 5.17.1 INI パーサー実装方針

設計書 §5.6:

- 標準ライブラリ `configparser.ConfigParser(interpolation=None)` を用いた専用の極小 INI ローダーを内包
- 外部ライブラリ（D-Settings 等）に依存しない
- `interpolation=None` により `%` エスケープを不要にする（フォーマット文字列を直接書ける）

#### 5.17.2 セクション規則

設計書 §5.4 / §5.6:

| セクション | 用途 |
|---|---|
| `[global]` | グローバル設定 |
| `[dsafelogger:モジュール名]` | モジュール別設定 |
| その他の未知セクション | stderr 警告 + 無視 |
| `[dsafelogger:]`（モジュール名空） | `ValueError`（Fail-Fast） |

#### 5.17.3 オプショナルキーの空値処理

設計書 §5.3:

- `max_count =`（空値）は「キー不在」と同等（`None`）として扱う
- `fmt =` / `file_fmt =` / `console_fmt =` / `datefmt =` のオプショナル書式キーの空値も「未指定」として扱い、通常のフォールバック規則へ委ねる

#### 5.17.4 未知キーの扱い

設計書 §5.3:

- `[global]` セクションの未知キー: stderr 警告 + 無視（既存有効キーの型変換エラーとは異なり、起動停止しない）
- `color_` プレフィックスのキーはパターンベースで認識（固定キー一覧に含まれない）

#### 5.17.5 `config_dict` の文字列強制

設計書 §5.7.1:

> 全ての値は文字列型: INIファイルから読み込んだ場合と完全に同一の型変換・バリデーションパイプラインを通すため、辞書内の全ての値は文字列として指定する。`int` や `bool` を直接渡すことは `TypeError` となる（Fail-Fast）。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §5.7.1）

これにより、INI と dict のどちらを使用しても**型変換・バリデーションのコードパスが完全に統一**される。

#### 5.17.6 排他制約

設計書 §5.7.3:

```python
# OK: config_file のみ
ConfigureLogger(config_file='./config/logging.ini')

# OK: config_dict のみ
ConfigureLogger(config_dict={'global': {'default_level': 'DEBUG'}})

# NG: 両方指定 → ValueError
ConfigureLogger(config_file='./logging.ini', config_dict={'global': {'default_level': 'DEBUG'}})
```

#### 5.17.7 `{prefix}_CONFIG` との関係

設計書 §5.7.3 / §4.6:

- `{prefix}_CONFIG` 設定時は `config_file` と `config_dict` の双方を上書きし、環境変数で指定された INI ファイルが第 2 層として使用される
- この場合、`config_file` と `config_dict` の排他チェックは行われない（環境変数が全てに優先するため）

#### 5.17.8 機能観察

- INI と dict が同一バリデーションパイプラインを通る設計により、ユーザーが「dict だと型変換されるかも」と誤解する余地がない。
- `interpolation=None` により `%(asctime)s` 等のフォーマット文字列を `%%` エスケープなしに記述可能。

---

### 5.18 CLI ツール `dsafelogger`

#### 5.18.1 提供される 3 コマンド（再掲、§3.6）

設計書 §8 と詳細設計書 §13:

| コマンド | 役割 |
|---|---|
| `dsafelogger init` | INI 設定ファイルのテンプレートを標準出力に出力 |
| `dsafelogger ls [log_dir]` | 指定ディレクトリ内の D-SafeLogger ファイルをパースして一覧表示 |
| `dsafelogger tail -f <log_dir> <pg_name> [options]` | 指定プログラムの最新ログファイルを自動判定して追随 |

#### 5.18.2 コマンド名のハイフン省略

設計書 §8.1: PyPI パッケージ名 `d-safelogger` からハイフンを除外した `dsafelogger` を採用。シェルでのタイピング時のハイフン省略を優先した命名判断。

#### 5.18.3 init の標準出力モデル

設計書 §8.1.1:

```bash
# テンプレートを生成してファイルに保存
dsafelogger init > ./config/logging.ini

# 中身を確認してから保存
dsafelogger init | less
```

ファイルパスを引数に取らず、シェルリダイレクトでユーザーが保存先を自由に制御する設計。

#### 5.18.4 tail の透過的ファイル切り替え

設計書 §8.1:

> 透過的なファイル追随: 出力中に元アプリケーション側でログの「日跨ぎ」等によりファイルが切り替わった場合でも、CLI がそれを動的に検知し、透過的に `tail` 先を新ファイルへ差し替えて出力を継続し続ける。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §8.1）

これは Append-Only モデルの運用上の弱点（`tail -f app.log` が成立しない）を CLI 側で補完する設計判断。

#### 5.18.5 機能観察

- CLI は本体に同梱され、別パッケージとして配布されない。
- `init` のリダイレクト前提モデルにより、上書き確認等の対話処理を排除。
- `tail` の透過的追随により Append-Only の運用ハードルを下げる。

---

### 5.19 free-threaded 対応

#### 5.19.1 設計目的

設計書 §1 / §2:

- 通常 build に加えて Python 3.13 以上の **free-threaded build** を設計対象に含める
- 実装は 3.14 専用 API に依存せず、3.11+ で統一可能な方式を採用

#### 5.19.2 共有状態の明示ロック化

設計書 §2 / §9.2:

> `_configure_state`、`_active_pipeline`、`_active_workers`、`_custom_levels` 等の共有状態は GIL の存在を前提にせず、明示ロックにより保護する。`list` / `dict` の実装依存の原子性には依存しない。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §2）

#### 5.19.3 cross-thread 安全性

設計書 §9.4:

> free-threaded build では、実行中の他 thread の frame に対する `f_locals` live 参照は unsafe である。したがって、queue を跨ぐ hand-off が発生する場合は producer thread 側で traceback と `f_locals` を**安全なマスク済み repr スナップショット**に変換し、consumer thread 側では live 参照を行わない。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §9.4）

#### 5.19.4 thread 境界の意味論

設計書 §9.5:

- ユーザーが生成した新規 thread への初期 context 継承は Python 本体仕様に従う
- D-SafeLogger 自身が生成する内部 thread は常に空 `Context` で開始 → 内部 thread への context 漏洩を防ぐ

#### 5.19.5 並行安全性の強化（v21）

設計書 §2 v21 改訂:

- `ConfigureLogger` の初期化処理（`_do_configure()`）全体を `_lifecycle_lock` 保持下で実行
- `GetLogger` は `'configuring'` 状態を検出して lock 構造待機を行う
- `AppendOnlyFileHandler` の独立した `self._lock` を廃止し、親クラス `logging.Handler` の lock API（`self.acquire()/release()`）に統一することで二重 lock オーバーヘッドを排除

#### 5.19.6 機能観察

- GIL の存在を前提にしない明示ロック設計により、free-threaded build での共有状態破壊を構造的に排除。
- `f_locals` の repr 済み snapshot 化により、free-threaded build での他 thread frame への live 参照リスクを排除。
- 内部 thread の空 Context 開始により、ユーザーの request context が内部 thread に漏洩する事故を排除。

---

### 5.20 diagnose（変数自動展開）

#### 5.20.1 機能仕様

設計書 §9.4:

- `{prefix}_DIAGNOSE=1` 環境変数が設定されたときのみ有効
- 例外ログに対して専用フォーマッタが適用され、`f_locals` を展開記録
- `structured=True` かつ `{prefix}_DIAGNOSE=1` の場合、`f_locals` 情報は JSON オブジェクトの `locals` フィールドとして包含出力

#### 5.20.2 聖域化（再掲、§4.4.1）

- INI からの設定は無視される（警告もエラーも出さない、ただの無効キー扱い）
- `ConfigureLogger()` の引数として存在しない
- `"1"` のみが有効値（`"true"` / `"yes"` / `"True"` 等は無効）

#### 5.20.3 lazy path

設計書 §9.3 / §9.4:

- diagnose 用の重い `repr()` 展開は `diagnose=True` かつ `exc_info` ありの場合にのみ producer thread 側で実行
- 通常ログでは copy + context snapshot の軽量 hand-off

#### 5.20.4 巨大 repr の抑制

設計書 §9.4:

- 個々のローカル変数の `repr()` は一定長で打ち切り
- `repr()` 自体に失敗した場合も診断ログ全体を壊さず、失敗した旨をプレースホルダとして出力

#### 5.20.5 フォールバック規則

設計書 §9.4:

formatter は次の順序でフォールバック:
1. queue hand-off 済みの診断スナップショットがあればそれを使用
2. 同一 thread 内で `exc_info` が保持されている場合のみ live 参照を許可
3. それ以外は standard traceback のみを出力

#### 5.20.6 機能観察

- 診断機能を「開発時の便利機能」ではなく「本番時の運用ツール」として位置づけている（環境変数のみ有効化、運用者の意図的な操作）。
- repr 失敗・巨大オブジェクトに対する防御的実装。
- async / multiprocess 経由でも repr 済み snapshot で hand-off するため、free-threaded 環境での安全性を保つ。

---

### 5.21 sens_kws マスキング

#### 5.21.1 機能仕様（再掲、§4.4）

設計書 §9.4:

- `f_locals` 展開時、変数名にセンシティブ語を含む値は `*** MASKED ***` に置換
- ビルトイン 12 語: `password`, `passwd`, `pass`, `secret`, `token`, `key`, `api_key`, `apikey`, `auth`, `credential`, `private`, `cert`
- 部分一致（大文字小文字不問）

#### 5.21.2 カスタマイズ

| 設定方法 | 動作 |
|---|---|
| `sens_kws=['ssn', 'credit_card']`（追加） | ビルトイン 12 語 + 追加語 |
| `sens_kws=['ssn'], sens_kws_replace=True`（置換） | ビルトイン破棄、指定語のみ |

#### 5.21.3 環境変数からの非対応

設計書 §3.4:

> `sens_kws` / `sens_kws_replace` は環境変数からの設定を意図的に非対応とする。これは `diagnose` と同様の「聖域」的扱いであり、センシティブキーワードの意図しない変更を防止するための設計判断である。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §3.4）

#### 5.21.4 マスキング適用範囲（再掲、§4.4.6）

`examples/09_debugging_production.md`:

マスキングは **`f_locals` 経路のみ**で動作する。次は対象外:
- `logger.info(...)` 等のメッセージ本文
- `extra=...` / `contextualize()` / structured JSON 出力で追加したフィールド
- `D_LOG_DIAGNOSE` がオフのときの通常ロギング

#### 5.21.5 機能観察

- マスキング機能は diagnose モード専用（通常ログでは動作しない）。
- 「秘密はメッセージ本文ではなく変数名にマスキング規則に該当する名前を付けて保持する」という運用パターンが前提。
- 環境変数からの聖域化により、本番でのキーワードの意図しない変更を構造的に排除。

---

### 5.22 機能別の整理

本章で確認した資料から、次のように整理できる。

1. **Append-Only ルーティングは 9 モード**: `none` / `daily` / `hourly` / `min_interval` / `startup_interval` / `size` / `count` / `cyclic_weekday` / `cyclic_month`。サフィックス規則と切り替え契機が `RoutingStrategy` 抽象基底クラスを介して統一実装されている。
2. **size / count は max_count の有無で目的が分岐**: 指定あり = サイクリック上書き（ディスク満杯防止）、指定なし = 上限到達 `OverflowError` でアプリ停止（厳格システム）。「容量設計ミスを起動継続させない」設計判断。
3. **min_interval は 60 を割り切る整数のみ**: `{1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60}` 分のみ受け付け、正時に揃う切り替えタイミングを保証する制約。
4. **世代管理は `backup_count` で表現、archive_mode で削除/圧縮を独立切り替え**: `Fire-and-Forget` 別スレッド + 自己修復性（次回切り替えタイミングでリトライ）。
5. **同一 family の maintenance は直列化**: `directory + pg_name` 単位で並列実行を禁止。重複削除・重複 ZIP 化・競合警告を排除。
6. **`pg_name` ファイル名フィルタリングは完全一致**: `{pg_name}.log` または `{pg_name}_{サフィックス}.log` のみが対象。前方一致による誤マッチ（別アプリのファイル削除）を構造的に排除。
7. **external rotation 共存は `routing_mode='none'` のみ**: 内部 routing と外部 rotation の混在を `ValueError` で拒否し、責務境界を明確化。
8. **完全性検証は SHA-256 + チャンク 64KB 読み + `os.replace()` 原子的書き込み**: 標準ライブラリ `hashlib` のみ使用（zero-dep 維持）、サイドカー書き込みは原子的。
9. **マニフェスト追記は key 単位 lock で直列化、lock ordering は `family_lock → manifest_lock`**: デッドロック回避規則が設計上明記されている。
10. **HashWorker は `_run_in_empty_context` で実行**: 親の context を継承しないことを保証。内部 thread の空 Context 開始原則と整合。
11. **Formatter は 4 系統 + 個別指定**: `DSafeFormatter` / `StructuredFormatter` / `DiagnosticFormatter` / `DiagnosticStructuredFormatter`、および `file_fmt` / `console_fmt` の個別指定。multiprocess 版では allow-list 式の `kind + constructor args` spec へ正規化。
12. **`structured=True` と `fmt`/`file_fmt`/`console_fmt` 文字列指定は排他**: 同時指定で `ValueError`（同一機能の二重実装による意味論衝突を回避）。
13. **`contextualize()` は `MappingProxyType` ベースの O(1) 参照渡し**: mutable 値は Fail-Fast 拒否。`hasattr` ベース fallback により IPC 境界での `_ds_context` 常在規約と整合。
14. **`register_level()` は `ConfigureLogger` 前限定、ビルトイン 5 段階は不可侵**: spawn 再 import の同一定義は冪等 no-op、不一致は `RuntimeError`。
15. **カラーパレットは INI/dict 専用（環境変数・引数で設定不可）**: マージ順序は `ビルトイン → register_level → INI` の 3 段階。`color_{略称}` キーの未知略称・不正文字は警告 + スキップ。
16. **`is_async=True` の意味論は root と module-specific path に一貫適用（v21）**: `Pipeline.module_transports` で全 Transport を構造的に停止。
17. **5 状態ライフサイクル + `RLock`**: `unconfigured` / `auto` / `explicit` / `configuring` / `shutting_down`。例外時の rollback は `try/finally` で保証。
18. **`dsafelogger.mp` は Capture / Transport / Sink 3 層を維持**: Writer 側で Capture 意味論（logger 階層評価、level 判定、`f_locals` 収集）を再実行しない規約が明文化されている。
19. **log plane / control plane は完全分離、reply path は per-request Pipe**: Queue-in-Queue 方式は Python `multiprocessing` 制約上不採用。
20. **配送状態は分類済み counters + writer_reject 6 内訳**: silent loss は `unexpected_loss` のみがバグ扱い。残りは policy 由来として説明可能。すべてに rate-limited stderr warning。
21. **bounded shutdown は 4 つの内部定数で防衛**: `MAX_IPC_LOG_TIMEOUT_SECONDS=3.0` / `CONTROL_PLANE_ACK_TIMEOUT_SEC=5.0` / `WRITER_STOP_WAIT_TIMEOUT_SEC=10.0` / `ipc_log_queue_maxsize` warning 閾値 100000。
22. **`writer_flush_batch=1`（既定）は per-message visibility、`>=2` opt-in は visibility 失効を仕様明記**: 既定で durability 弱化させない契約。
23. **TrackedQueue の native qsize fallback は OS 名非依存**: `super().qsize()` の例外プローブで判別。未来のプラットフォームに対する移植耐性。
24. **環境変数は静的反映のみ**: プロセス稼働中に動的反映されない（`ConfigureLogger` 再実行が必要）。`NO_COLOR` のみ業界標準として `env_prefix` 影響を受けない。
25. **INI / `config_dict` は同一バリデーションパイプラインを通る**: `config_dict` の値はすべて文字列強制（`int` / `bool` 直接指定は `TypeError`）。
26. **CLI 3 コマンドは Append-Only モデルの運用補完**: `init` の標準出力モデル、`tail` の透過的ファイル切り替え追随。
27. **free-threaded 対応は GIL 非依存の明示ロック + repr 済み snapshot**: 共有状態を明示ロック保護、`f_locals` を producer thread で repr 済み snapshot 化、内部 thread は空 Context で開始。
28. **diagnose / sens_kws / file_fmt / console_fmt は環境変数で設定不可（聖域）**: それぞれ理由付きで設計書本文に明記。

---

### 5.23 本章のまとめ

D-SafeLogger v23j の機能群は、次の 5 つの機能カテゴリに整理できる:

1. **ファイル I/O 系**: 9 種の Append-Only routing / 世代管理 + archive / external rotation 共存 / SHA-256 完全性検証。Windows ファイルロック問題を構造的に回避し、`sha256sum -c` 互換で監査ワークフローと統合する。
2. **ログ生成・表示系**: 4 系統の Formatter / `file_fmt` / `console_fmt` 個別指定 / `contextualize` (FrozenContext) / `register_level` / カラーパレット / diagnose / sens_kws マスキング。LogRecord 非破壊取り扱いと表示用 proxy により stdlib 互換性を維持する。
3. **並行・非同期系**: `is_async` (QueueTransport) / 5 状態ライフサイクル / free-threaded 対応 / 内部 thread の空 Context 開始 / `_lifecycle_lock` (RLock)。GIL 非依存の明示ロックで共有状態を保護する。
4. **マルチプロセス系**: Writer runtime / `ctx` bootstrap / log plane and control plane / 分類済み配送状態 counters / writer_reject 6 内訳 / bounded shutdown / flush 戦略 / TrackedQueue / registry hash 照合 / active client registry。silent loss を構造的に許さない。
5. **設定・運用系**: 3 層パイプライン (env > INI/dict > 引数) / 環境変数 13 種 / `NO_COLOR` 業界標準 / CLI 3 コマンド (`init` / `ls` / `tail -f`) / examples 17 種。変更主体ごとに層を割り当て、CLI で Append-Only モデルの運用補完を担う。

これら機能群はすべて「依存しない／壊さない／黙って劣化しない／説明可能にする／拡張するが置き換えない」の 5 群（§1.3）に対応しており、第 1 章で抽出した設計思想と機能実装の対応関係が確認できる。

---

> **本章の主な参照資料**: `docs/design/D_SafeLogger_Specification_v23j_full.md` §1, §2, §3, §4, §5, §6, §7, §8, §9, §10, §11, §12 / `docs/design/D-SafeLogger_DetailedDesign_v23j.md` §1, §2, §4, §5, §6, §7, §8, §11, §12, §13, §14, §15, §15a, §16, §17, §18, §19 / `docs/api/dsafelogger*.md` / `src/dsafelogger/` モジュール構成 / `examples/01_*.md`〜`examples/17_*.md`
> 本書は現行 v23j アーキテクチャの説明と評価を目的とし、改善提案・課題管理・将来ロードマップは扱わない。

## 第 6 章 競合プロジェクト比較

### 6.1 第 6 章のスコープと方針

#### 6.1.1 比較対象

本章では、現代の Python アプリケーションにおいて選定候補となりうる主要ロギングライブラリを次の 8 件で確定し、一次ソースで仕様事実を確認した上で D-SafeLogger v23j との差分を整理する。

| # | プロジェクト | 入手 PyPI バージョン | 一次ソース確認日 |
|---|---|---|---|
| 1 | **stdlib `logging`** | Python 3.14（公式 docs） | 2026-05-09 |
| 2 | **Loguru** | 0.7.3 (2024-12-06 release) | 2026-05-09 |
| 3 | **structlog** | 25.5.0 (2025-10-27 release) | 2026-05-09 |
| 4 | **picologging** (Microsoft) | 0.9.3 (PyPI metadata) / 0.9.4 (GitHub release 2024-09-13) | 2026-05-09 |
| 5 | **Eliot** | 1.18.0 (2026-05-07 release) | 2026-05-09 |
| 6 | **Logbook** | 1.9.2 | 2026-05-09 |
| 7 | **logfire** (Pydantic) | 4.32.1 | 2026-05-09 |
| 8 | **OpenTelemetry Python SDK (Logs)** | opentelemetry-sdk 1.41.1 | 2026-05-09 |

#### 6.1.2 比較軸

D-SafeLogger v23j のアーキテクチャ特性に基づいて、次の 9 軸で各ライブラリを比較する。

| 軸 | 観点 |
|---|---|
| ランタイム外部依存 | サプライチェーン経路の本数 |
| stdlib `logging` との関係 | drop-in 拡張 / 並走 / 置換 / OTel ブリッジ |
| ファイル出力・ルーティング | rename 方式 / append-only / external rotation 共存 |
| 構造化ログ・コンテキスト管理 | JSON / contextvars / processor chain |
| マルチプロセス対応 | enqueue / parent Writer / 配送状態 |
| 完全性検証 / 監査機能 | SHA-256 / マニフェスト / 改竄検知 |
| free-threaded Python 対応 | PEP 703 への対応 |
| 配送状態の観測性 | counters / 分類 / shutdown summary |
| 設定管理パイプライン | env / INI / 引数 |

#### 6.1.3 評価方針

- **事実の引用源**: 各プロジェクトの PyPI / GitHub / 公式 docs / PEP からの直接抜粋を脚注または本文中に明記する。
- **主観評価の排除**: 「速い / 遅い」「人気がある / ない」などの主観評価は記載しない。GitHub stars 等の数値は事実として引用するが、優劣の判断には用いない。
- **責務軸の差異の明示**: 比較表では「未提供」を意味する `—` と「責務範囲外」を意味する `out` を区別する（OTel が file rotation を扱わないのは「未実装」ではなく「責務範囲外」のため）。

---

### 6.2 比較対象プロジェクトの一次ソース確認

#### 6.2.1 stdlib `logging`（Python 3.14）

**出典**: `docs.python.org/3/library/logging.html`、`docs.python.org/3/library/logging.handlers.html`、`docs.python.org/3/howto/logging-cookbook.html`、PEP 282、Python 3.13 What's New。

主要事実:
- 4 コンポーネント構成: `Logger` / `Handler` / `Filter` / `Formatter`
- `RotatingFileHandler` および `TimedRotatingFileHandler` は **rename 方式**でローテーション
- `WatchedFileHandler` は公式に「Windows では適切でない」と明記:
  > "This handler is not appropriate for use under Windows, because under Windows open log files cannot be moved or renamed - logging opens the files with exclusive locks."
  > （`docs.python.org/3/library/logging.handlers.html` WatchedFileHandler 節）
- マルチプロセスへの公式見解は次の通り:
  > "Although logging is thread-safe, and logging to a single file from multiple threads in a single process is supported, logging to a single file from multiple processes is not supported, because there is no standard way to serialize access to a single file across multiple processes in Python."
  > （`docs.python.org/3/howto/logging-cookbook.html`）
- 推奨パターン: `QueueHandler` + `QueueListener` を別プロセスで運用、または `SocketHandler` 経由で listener へ送信。
- Python 3.13 では `logging` モジュール自体への変更は無し。free-threaded build は別軸での影響あり。

#### 6.2.2 Loguru 0.7.3

**出典**: `pypi.org/pypi/loguru/json`、`github.com/Delgan/loguru`、`loguru.readthedocs.io`。

主要事実:
- ライセンス: MIT
- Python 要件: `>=3.5, <4.0`
- ランタイム依存: `colorama>=0.3.4`（Windows のみ）、`aiocontextvars>=0.2.0`（Python <3.7）、`win32-setctime>=1.0.0`（Windows のみ）
- 最新 release: 0.7.3（2024-12-06）
- GitHub stars: 23.9k（2026-05-09 時点）
- 自己主張: "Python logging made (stupidly) simple"
- 機能: `enqueue=True` による thread-safe / multiprocess-safe、coroutine sink での async logging、file rotation（size/time）、retention、compression、JSON、`@logger.catch`、`diagnose=True`
- マーケティング上の主張: "10x faster than standard Python logging"

#### 6.2.3 structlog 25.5.0

**出典**: `pypi.org/pypi/structlog/json`、`www.structlog.org`、`github.com/hynek/structlog`。

主要事実:
- ライセンス: MIT OR Apache-2.0
- Python 要件: `>=3.8`
- ランタイム依存: `typing-extensions`（Python <3.11 のみ）
- 最新 release: 25.5.0（2025-10-27）
- 自己主張: "Simple. Powerful. Fast. Pick three."
- 位置づけ: stdlib `logging` を置換せず、独立して動作するか stdlib に **forward** する（公式 docs より）
- 機能: processor chains、`bind()` による context 構築、`contextvars` ネイティブ対応、JSON / logfmt / colorized console
- 公式 docs に**ファイルローテーション・完全性検証・マルチプロセス特化機能の言及なし**

#### 6.2.4 picologging 0.9.3 / 0.9.4

**出典**: `pypi.org/pypi/picologging/json`、`github.com/microsoft/picologging`、`microsoft.github.io/picologging/`。

主要事実:
- ライセンス: MIT
- Python 要件: `>=3.7`
- ランタイム依存: なし（dev extras のみ）
- 開発ステータス: Beta（PyPI classifier `Development Status :: 4 - Beta`）
- 最新 GitHub release: 0.9.4（2024-09-13）
- 提供元: Microsoft
- 自己主張: stdlib `logging` の drop-in replacement、4–10x（リポジトリ README は最大 17x）の高速化を C 拡張で実現
- 公式リポジトリは "This project is in beta. There are some incomplete features." と明記
- **free-threaded（No-GIL）対応の言及は GitHub README にも公式 docs にも観測されない**（2026-05-09 時点）

#### 6.2.5 Eliot 1.18.0

**出典**: `pypi.org/pypi/eliot/json`、`eliot.readthedocs.io`、`github.com/itamarst/eliot`。

主要事実:
- ライセンス: Apache 2.0
- Python 要件: `>=3.10.0`
- ランタイム依存: `zope.interface`、`pyrsistent (>=0.11.8)`、`boltons (>=19.0.1)`、`orjson`（CPython のみ）
- 最新 release: 1.18.0（2026-05-07）
- 自己主張: "Logging library that tells you why it happened"
- 位置づけ: causal action chain（因果連鎖）。actions が他の actions を spawn し、succeed / fail で完結するモデル。
- stdlib `logging` との統合あり（Integrating and Migrating Existing Logging セクション）
- async（asyncio / Trio / Twisted）対応。Spanning Processes and Threads ドキュメントあり

#### 6.2.6 Logbook 1.9.2

**出典**: `pypi.org/pypi/Logbook/json`、`logbook.readthedocs.io`、`github.com/getlogbook/logbook`。

主要事実:
- ライセンス: BSD-3-Clause
- Python 要件: `>=3.9`
- ランタイム依存: `typing-extensions>=4.14.0`
- 自己主張: "A logging replacement for Python"
- 機能: 多数の Handler 系（StreamHandler / file-based / ticketing）、Stack-based architecture、Custom processors、stdlib logging compatibility、queue support
- ドキュメント自体が "Feedback is appreciated. The docs here only show a tiny, tiny feature set and can be incomplete." と注記

#### 6.2.7 logfire 4.32.1（Pydantic）

**出典**: `pypi.org/pypi/logfire/json`、`github.com/pydantic/logfire`、`pydantic.dev/docs/logfire/`。

主要事実:
- ライセンス: MIT
- Python 要件: `>=3.9`
- ランタイム依存: 8 パッケージ（`executing`、`opentelemetry-exporter-otlp-proto-http<1.41.0,>=1.39.0`、`opentelemetry-instrumentation>=0.41b0`、`opentelemetry-sdk<1.41.0,>=1.39.0`、`protobuf>=4.23.4`、`rich>=13.4.2`、`tomli>=2.0.1` (Python <3.11)、`typing-extensions>=4.1.0`）
- 自己主張: "An observability platform built on the same belief as our open source library — that the most powerful tools can be easy to use."
- 位置づけ: **Hosted SaaS observability platform**（SDK は OSS、UI と backend は専有。"Logfire SDKs are open source, and you can use them to export data to any OTel-compatible backend"）
- Enterprise self-host は有償ライセンス
- OTel 互換 + Python-centric（FastAPI / Pydantic 統合・LLM telemetry）

#### 6.2.8 OpenTelemetry Python SDK 1.41.1

**出典**: `pypi.org/pypi/opentelemetry-sdk/json`、`opentelemetry.io/docs/specs/otel/logs/`、`opentelemetry.io/docs/languages/python/instrumentation/`、`github.com/open-telemetry/opentelemetry-python`。

主要事実:
- ライセンス: Apache-2.0
- Python 要件: `>=3.9`
- ランタイム依存: `opentelemetry-api==1.41.1`、`opentelemetry-semantic-conventions==0.62b1`、`typing-extensions>=4.5.0`
- 公式 logs 仕様（`opentelemetry.io/docs/specs/otel/logs/`）の方針:
  > "We embrace existing logging solutions and make sure OpenTelemetry works nicely with existing logging libraries."
  > （OpenTelemetry Logs Specification）
- Python 統合: `LoggingHandler` を stdlib `logging` の handler として登録するブリッジ方式。`logging.basicConfig(handlers=[handler], level=logging.INFO)` で stdlib 経由のログを OTel log records に変換する。
- ファイル出力・ローテーション・完全性検証は **責務範囲外**（emission / export に特化）

#### 6.2.9 PEP 703 / Free-threaded Python の現状

**出典**: `peps.python.org/pep-0703/`、`docs.python.org/3/whatsnew/3.13.html`。

主要事実:
- PEP 703 は **2023-10-24 に Accepted**
- 対象: Python 3.13+（`--disable-gil` build flag）
- ロールアウト方針: "the rollout be gradual and break as little as possible, and that we can roll back any changes that turn out to be too disruptive."
- 含意: GIL に暗黙的に依存している共有可変状態を持つライブラリは、**明示的な locking が必要**。`list` / `dict` の暗黙的スレッド安全性に依存できない。
- ランタイム制御: `PYTHON_GIL` 環境変数、`Py_mod_gil` モジュールスロット

---

### 6.3 軸 1: ランタイム外部依存

各プロジェクトのランタイム外部依存数（インストール時に同時インストールされるパッケージ）を一次ソース（PyPI metadata）から整理する。

| プロジェクト | ランタイム依存数 | 内訳 |
|---|---:|---|
| **D-SafeLogger v23j** | **0** | なし（標準ライブラリのみ） |
| stdlib `logging` | 0 | （Python 標準ライブラリ自体） |
| Loguru 0.7.3 | 3（条件付き） | `colorama` (Windows)、`aiocontextvars` (<3.7)、`win32-setctime` (Windows) |
| structlog 25.5.0 | 1（条件付き） | `typing-extensions` (<3.11) |
| picologging 0.9.3 | 0 | なし |
| Eliot 1.18.0 | 4 | `zope.interface`、`pyrsistent`、`boltons`、`orjson` |
| Logbook 1.9.2 | 1 | `typing-extensions>=4.14.0` |
| logfire 4.32.1 | 8 | OpenTelemetry 系 3、`executing`、`protobuf`、`rich`、`tomli` (<3.11)、`typing-extensions` |
| OpenTelemetry SDK 1.41.1 | 3 | `opentelemetry-api`、`opentelemetry-semantic-conventions`、`typing-extensions` |

#### 6.3.1 観察事実

- **完全な依存ゼロ（条件付きを含めて 0）**は本一次ソース調査の範囲では D-SafeLogger と picologging の 2 件のみ。
- structlog / Logbook の `typing-extensions` 依存は**条件付き**（古い Python のみ）。
- Loguru の Windows 専用依存（`colorama` / `win32-setctime`）は Windows 上のみ実体としてインストールされる。
- logfire の 8 依存は OpenTelemetry スタック全体を引き連れる構造であり、サプライチェーンの広さが他プロジェクトと比較して目立つ。

#### 6.3.2 D-SafeLogger の独自性

D-SafeLogger は設計書 §1 が**ランタイム外部依存ゼロを「絶対条件」**として宣言しており、依存ゼロは個別機能の判断ではなくアーキテクチャ全体の制約として運用される（§4.2.1）。Vendor-Agnostic 原則によりベンダー固有 import もコアモジュールから構造的に排除される（§4.2.2）。picologging は依存ゼロだが、**C 拡張ベース**であるため `cibuildwheel` / native build chain への依存が間接的に発生する（PyPI からの wheel 配布で隠蔽されているが、source build 時には現れる）。

---

### 6.4 軸 2: stdlib `logging` との関係

各ライブラリが stdlib `logging` に対してどの位置を取るかを整理する。

| プロジェクト | スタンス | 観測根拠 |
|---|---|---|
| **D-SafeLogger** | **drop-in 拡張**（`logging.setLoggerClass()` で `DSafeLogger` を返す） | 設計書 §2、§9.2 |
| stdlib `logging` | （基準） | — |
| Loguru | **置換**（独自の `logger` シングルトン） | Loguru README "One and only one logger" |
| structlog | **並走 or forward**（独立動作 or stdlib へ転送） | structlog 公式 docs |
| picologging | **drop-in 置換**（同 API、C 拡張で高速化） | picologging README "drop-in replacement" |
| Eliot | **並走**（stdlib との integration あり） | Eliot docs "Integrating and Migrating Existing Logging" |
| Logbook | **置換**（stdlib 互換の handler は提供） | Logbook docs |
| logfire | **OTel ブリッジ**（stdlib logging を OTel に変換） | logfire docs / OTel LoggingHandler |
| OpenTelemetry Python | **OTel ブリッジ**（`LoggingHandler` で stdlib を OTel に変換） | OTel Python instrumentation docs |

#### 6.4.1 観察事実

- D-SafeLogger と picologging は両者とも「stdlib `logging` の drop-in 互換」を主張するが、**目的が異なる**:
  - D-SafeLogger: append-only ルーティング・完全性検証・multiprocess Writer 等の**設計上の差別化**を加える
  - picologging: 同一 API のまま **C 拡張で高速化**する（機能は stdlib と同等）
- Loguru / Logbook は独自シングルトン / handler で**置換**を志向。既存の `logger.info()` 呼び出しサイトは置換時に書き換えが必要（または adapter）。
- structlog は**フロントエンド**（イベント辞書の組み立て）を担い、出力は stdlib に forward することも可能。
- logfire / OpenTelemetry は **emission ブリッジ**であり、stdlib logging のログを OTLP に転送する経路を提供する。

#### 6.4.2 D-SafeLogger の独自性

D-SafeLogger は `logging.setLoggerClass()` を `ConfigureLogger()` 内部で呼び、SQLAlchemy / Django 等の `logging.getLogger()` を使う第三者ライブラリも**改修なしで本ライブラリの設定フローに乗る**。これは picologging も同等だが、D-SafeLogger は加えて append-only / 完全性検証 / multiprocess Writer を提供する。Loguru / Logbook の置換型と異なり、既存 `logger.info()` 呼び出しサイトを変更しない（`examples/03_migration_from_stdlib.md`、§3.7）。

---

### 6.5 軸 3: ファイル出力・ルーティング

| プロジェクト | rename 方式 / append-only | external rotation 共存 |
|---|---|---|
| **D-SafeLogger** | **append-only**（rename を行わない） | `routing_mode='none'` + `ReopenLogFiles()` で正式サポート |
| stdlib `logging` | **rename 方式**（RotatingFileHandler / TimedRotatingFileHandler） | `WatchedFileHandler`（Windows 不可） |
| Loguru | rotation あり（rename ベース） | 機能ドキュメントに external rotation 共存の正式 API は観測されない |
| structlog | ファイル出力は stdlib にフォワード | （stdlib に依存） |
| picologging | stdlib 互換（rename 方式） | （stdlib に依存） |
| Eliot | ファイル出力は外部接続経由が中心 | — |
| Logbook | rotation あり | — |
| logfire | **責務範囲外**（OTel exporter 経由） | out |
| OpenTelemetry Python | **責務範囲外**（emission のみ） | out |

#### 6.5.1 観察事実: rename 方式の OS 別失敗モード

`docs.python.org/3/library/logging.handlers.html` は次の制約を明記している:

> "This handler is not appropriate for use under Windows, because under Windows open log files cannot be moved or renamed - logging opens the files with exclusive locks - and so there is no need for such a handler."
> （Python 公式 docs `logging.handlers` WatchedFileHandler 節）

これは `WatchedFileHandler`（外部 rotator が rename した後を inode で検知するハンドラ）に関する記述だが、**「Windows ではアクティブログを別プロセスから rename できない」**という OS 制約自体が明文化されている点が重要である。

rename ベースのローテーションは、OS ごとに異なる失敗モードを持つ。

Windows では、Python 公式 documentation が `WatchedFileHandler` について「open log files cannot be moved or renamed」と説明している通り、active log file の移動・rename がファイルロックにより失敗し得る。この場合、ローテーション操作は即時失敗として表面化する。

POSIX 系では、状況は逆である。`rename()` は open 中のファイルに対しても成功しやすく、既存 file descriptor は旧実体を指し続ける。このため、外部 rotator から見ると rotation は成功したように見える。しかし writer が旧FDを保持している限り、ログストリームは新しい active file ではなく、rename 後の旧世代へ流れ続ける。

つまり、Windows では rename 方式の失敗がファイル操作として表面化しやすい。一方、POSIX 系ではファイル操作としては成功したまま、ログ出力が旧ファイルへ流れ続けることがある。この違いは、POSIX 系の方が安全であることを意味しない。むしろ、監視対象のファイルに新規 record が入らない、圧縮・削除対象のファイルへ追記される、容量が解放されない、事後調査時に世代境界がずれる、といった形で遅れて発見される可能性がある。

#### 6.5.2 観察事実: stdlib のマルチプロセス制限

`docs.python.org/3/howto/logging-cookbook.html` は次のように明記している:

> "Logging to a single file from multiple processes is not supported, because there is no standard way to serialize access to a single file across multiple processes in Python."
> （Python 公式 logging cookbook）

これに対する公式の推奨パターンは `QueueHandler` + `QueueListener` の別プロセス運用、または `SocketHandler` 経由である。

#### 6.5.3 D-SafeLogger の独自性

D-SafeLogger の append-only ルーティング（設計書 §7.2）は、stdlib の rename 方式が抱える OS 別の失敗モードを**設計レベルで構造的に回避する**。

> 同様の思想は Logback や Log4j2 等の特定オプションにも見られるが、これをデフォルトの核とした設計は **Python エコシステムには存在しない**。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §7.2）

本一次ソース調査の範囲（stdlib / Loguru / structlog / picologging / Eliot / Logbook / logfire / OTel）でも、**append-only ルーティングをコアアーキテクチャに据えたプロジェクトは観測されない**。Loguru の rotation 機能は file rename を伴う一般的方式である（`loguru.readthedocs.io` rotation 節）。

---

### 6.6 軸 4: 構造化ログ・コンテキスト管理

| プロジェクト | 構造化ログ | contextvars サポート | コンテキスト管理 API |
|---|---|---|---|
| **D-SafeLogger** | `structured=True` で JSON Lines | `ContextVar[MappingProxyType]`（FrozenContext） | `contextualize(**kwargs)` |
| stdlib `logging` | △（`extra=` + custom Formatter） | △（手動） | `LoggerAdapter` / `extra=` |
| Loguru | ○（`serialize=True` で JSON） | ○ | `logger.bind()` / `logger.contextualize()` |
| structlog | ◎（中心機能、processor chain） | ◎（`contextvars` ネイティブ） | `bind()` / `bind_contextvars()` |
| picologging | △（stdlib 互換） | △（手動） | `LoggerAdapter` |
| Eliot | ◎（action tree、JSON） | ○（async / contextvars） | `start_action()` |
| Logbook | ○（custom processor） | △ | `Processor` |
| logfire | ◎（OTel attributes） | ○（OTel context） | `with logfire.span()` |
| OpenTelemetry Python | ○（OTel log records、attributes） | ○（OTel context） | `with tracer.start_as_current_span()` |

#### 6.6.1 観察事実: structlog の役割

`www.structlog.org` は次のように主張する:

> "structlog leans on functions that take and return dictionaries hidden behind familiar APIs."

structlog の中心は **processor chain** であり、bound logger に kwargs を bind しながら処理する。`bind_contextvars()` で `contextvars` ネイティブ対応も提供される。出力形式は JSON / logfmt / colorized console から選択。

#### 6.6.2 観察事実: Eliot の causal chain

`eliot.readthedocs.io` の主張:

> "actions can spawn other actions, and eventually they either succeed or fail. The resulting logs tell you the story of what your software did: what happened, and what caused it."

これは「孤立した event を出力する」一般的ロギングと異なる。action の親子関係をトレース可能にする設計。

#### 6.6.3 D-SafeLogger の独自性

D-SafeLogger の `contextualize()` は次の特徴を持つ:

- `MappingProxyType` による immutable snapshot で **O(1) 参照渡し**（§5.6.2）
- mutable 値の Fail-Fast 拒否（§5.6.3）
- multiprocess 経由でも `_ds_context` 常在規約により Capture 側 snapshot を Writer 側で保持（§5.6.7）

structlog の processor chain は構造化ログのフロントエンド機能として遥かに強力だが、**「ファイル出力境界より下」の責務を持たない**。D-SafeLogger は structlog と共存可能であり（`examples/16_structlog_coexistence.md`、§3.9.1）、責務軸が交差しない設計になっている。

---

### 6.7 軸 5: マルチプロセス対応

| プロジェクト | マルチプロセス機能 | 配送状態の観測 |
|---|---|---|
| **D-SafeLogger** | `dsafelogger.mp`: parent-side Writer が file sink を所有、worker は IPC で `LogEvent` 送信、`ATTACH`/`DETACH`/`STOP`/`REOPEN`/`STATUS` の control plane を分離 | `accepted`/`delivered`/`KnownRejected`/`KnownDropped`/`UnexplainedLost`/`partial_delivered` の 6 階層 + `writer_reject` 6 内訳 |
| stdlib `logging` | 公式に「multiprocess 単一ファイル書き込みは未サポート」、推奨は QueueHandler + QueueListener の別プロセス運用 | — |
| Loguru | `enqueue=True` でマルチプロセス対応 | — |
| structlog | （stdlib に依存） | — |
| picologging | stdlib 互換 | — |
| Eliot | "Spanning Processes and Threads" のドキュメントあり | — |
| Logbook | queue support | — |
| logfire | OTel exporter に集約 | — |
| OpenTelemetry Python | OTel exporter に集約 | — |

#### 6.7.1 観察事実: Loguru の `enqueue=True`

Loguru の README は "Thread-safe and multiprocess-safe with enqueue support" と明示する。`logger.add(..., enqueue=True)` でマルチプロセス対応を有効化する設計。

#### 6.7.2 観察事実: stdlib の公式推奨

stdlib `logging` は公式 cookbook 上で次のように推奨する:

> "When deploying web applications using Gunicorn or uWSGI (or similar), multiple worker processes are created to handle client requests. In such environments, **avoid creating file-based handlers directly in your web application**. Instead, use a `SocketHandler` to log from the web application to a listener in a separate process."
> （Python 公式 logging cookbook）

これは「マルチプロセスでファイル出力を本気でやるなら、別プロセスを建てて socket / queue で送れ」という指示であり、D-SafeLogger の `dsafelogger.mp` の Writer-owned sinks モデルと**方向性が一致する**。差分は「公式が DIY を推奨するパターンを、ライブラリとして本体提供するかどうか」。

#### 6.7.3 D-SafeLogger の独自性

D-SafeLogger の multiprocess 機能は次の点で観測可能な差別化を持つ（§2.8、§5.11–§5.14）:

1. **Writer-owned sinks**: file sink・routing・hash・manifest・purge・archive・reopen のすべてが Writer に集約される。worker は IPC で `LogEvent` を送るのみ。
2. **log plane / control plane の完全分離**: 通常ログと制御コマンドが別 queue で運ばれ、ACK は per-request `Pipe(duplex=False)` reply path。
3. **分類済み配送状態 counters**: `attempted` / `accepted` / `enqueued` / `delivered_per_sink` / `delivered` の lifecycle に加え、6 種の terminal state（`rejected` / `dropped` / `writer_reject` / `partial_delivered` / `unexpected_loss` / `writer_best_effort_failures`）+ `overload_shed` qualifier。
4. **bounded shutdown 契約（v23h）**: `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0` 秒の bounded join + visible warning + daemon thread で「process exits」を fail-safe として実現。
5. **`writer_reject` の 6 内訳**（v23h）: route / reconstruct / close_marker / sink / policy / format。

本一次ソース調査の範囲では、**他のいずれのプロジェクトも、配送失敗をこのレベルの粒度で分類する公開仕様を持たない**。Loguru の `enqueue=True` はマルチプロセス安全な hand-off を提供するが、配送状態 counters の階層的分類は公開ドキュメントに観測されない。OpenTelemetry の log records は exporter 側の retry / queue を持つが、これは「配送失敗を分類する」設計ではなく、「OTLP backend に送る」設計である。

---

### 6.8 軸 6: 完全性検証 / 監査機能

| プロジェクト | SHA-256 サイドカー | マニフェスト | 改竄検知 |
|---|---|---|---|
| **D-SafeLogger** | ◎（`enable_hash=True`、`sha256sum -c` 互換、相対パス） | ◎（`manifest_path` 指定、追記、別ディレクトリ保管推奨） | サイドカー + マニフェストの不整合検出 |
| stdlib `logging` | — | — | — |
| Loguru | — | — | — |
| structlog | — | — | — |
| picologging | — | — | — |
| Eliot | — | — | — |
| Logbook | — | — | — |
| logfire | — | — | — |
| OpenTelemetry Python | — | — | — |

#### 6.8.1 観察事実

本一次ソース調査の範囲では、**SHA-256 サイドカーやマニフェストファイルをライブラリ機能として提供しているプロジェクトは D-SafeLogger 以外に観測されない**。Loguru / Logbook / Eliot / structlog / picologging のいずれも、PyPI summary・GitHub README・公式 docs のいずれにも完全性検証機能の言及がない。OTel は「emission / export」の責務範囲のため、ファイル整合性は責務外（外部 collector / storage 側が担う）。

#### 6.8.2 D-SafeLogger の独自性

D-SafeLogger の完全性検証機能は次の特徴を持つ（§4.5、§5.4）:

- **`sha256sum -c` 互換フォーマット**: OS 標準コマンドで検証可能（独自検証ツールを作らない）
- **相対パス記載**: ログ一式を別の場所に移動しても検証が壊れない
- **マニフェストによるファイル消失検知**: サイドカーのみでは「ファイル + サイドカーが一緒に削除」を検知できないが、別ディレクトリ保管マニフェストで検知可能
- **`os.replace()` による原子的書き込み**: 検証ツールが途中書き込み状態を参照する事故を回避
- **HMAC は意図的にスコープ外**: 鍵管理という別責務を持ち込まないため

これは「監査・コンプライアンス（HIPAA / SOC 2 / PCI-DSS / FedRAMP）」用途を `examples/08_compliance_audit.md` で明示的に想定している設計の帰結である。

---

### 6.9 軸 7: free-threaded Python（PEP 703）対応

PEP 703 は **2023-10-24 に Accepted**。Python 3.13 から `--disable-gil` build で利用可能。GIL に暗黙的に依存しているライブラリは明示的 locking が必要になる。

| プロジェクト | free-threaded 対応の言及 |
|---|---|
| **D-SafeLogger** | **設計書 §1 / §2 で対象 build として明示**。共有状態を明示ロックで保護、`list` / `dict` の暗黙原子性に依存しない |
| stdlib `logging` | Python 3.13/3.14 で `logging` モジュール自体に直接の対応変更は無し。free-threaded build 自体は別軸で進行中 |
| Loguru | 公式リポジトリ・PyPI summary・docs に free-threaded 対応の言及は本調査範囲では観測されない |
| structlog | 公式 docs に free-threaded 対応の言及は本調査範囲では観測されない |
| picologging | C 拡張ベース。**`Py_mod_gil` への対応や free-threaded ビルド対応の言及は GitHub README にも公式 docs にも観測されない**（2026-05-09 時点） |
| Eliot | docs に free-threaded 対応の言及は本調査範囲では観測されない |
| Logbook | docs に free-threaded 対応の言及は本調査範囲では観測されない |
| logfire | OTel SDK 依存。OTel Python 側の対応に従う |
| OpenTelemetry Python | OTel コミュニティでの対応進行中。SDK 1.41 系の段階で free-threaded build を本流サポートする旨の公式宣言は本調査範囲では未確認 |

#### 6.9.1 観察事実

`peps.python.org/pep-0703/` および `docs.python.org/3/whatsnew/3.13.html` は次の点を明確化している:

- C 拡張は `Py_mod_gil` モジュールスロットで GIL 互換性を宣言する必要がある
- `list` / `dict` の暗黙的スレッド安全性に依存している Python レベルのライブラリも、明示的ロックの導入が必要
- ロールアウトは段階的（"the rollout be gradual and break as little as possible"）

ピュア Python ライブラリ（structlog / Logbook / Loguru / Eliot 等）にとっては「実装変更を加えれば free-threaded で動く」が、**ライブラリ側で自覚的に free-threaded を設計対象として宣言しているケースは本一次ソース調査範囲では D-SafeLogger 以外に観測されない**。

picologging は C 拡張ベースのため `Py_mod_gil` 対応が必要だが、現時点の GitHub README には対応宣言が観測されない（最新 release は 2024-09-13、PEP 703 Accepted 後）。

#### 6.9.2 D-SafeLogger の独自性

設計書 §1 が次のように明記している:

> 通常 build に加えて **Python 3.13 以上の free-threaded build** を設計対象に含める。ただし、実装は 3.14 専用 API に依存せず、3.11+ で統一可能な方式を採用する。
> （`docs/design/D_SafeLogger_Specification_v23j_full.md` §1）

設計書 §2 / §9.2 / §9.4 / §9.5 が、共有状態の明示ロック化、`list` / `dict` の暗黙原子性非依存、`f_locals` の repr 済み snapshot 化、内部 thread の空 Context 開始を**仕様レベルで規定**している。これは PEP 703 の「明示的 locking が必要」要件への対応として一貫している。

`TESTING.md` は free-threaded build 向けの手動テスト手順として次のコマンドを掲載している:

```bash
PYTHON_GIL=0 uvx --python cpython-3.13+freethreaded --from pytest pytest tests -v
```

free-threaded build は設計対象に含まれ、手動テスト手順が文書化されている。通常の GitHub Actions matrix は CPython 3.11〜3.14 regular build を対象とする。

---

### 6.10 軸 8: 配送状態の観測性（再掲、§6.7.3）

これは **D-SafeLogger に固有の軸**として整理する。本一次ソース調査の範囲では、他のいずれのプロジェクトも配送失敗をこのレベルの粒度で分類する公開仕様を持たない。

D-SafeLogger の配送状態階層（§5.13）:

```text
Lifecycle: attempted → accepted → enqueued → delivered_per_sink → delivered
Terminal:  rejected | dropped | writer_reject | partial_delivered | unexpected_loss | writer_best_effort_failures
Qualifier: overload_shed
```

`writer_reject` 6 内訳: `writer_route_reject` / `writer_reconstruct_reject` / `writer_close_marker_reject` / `writer_sink_reject` / `writer_policy_reject` / `writer_format_reject`（v23h）。

すべてに**専用 counter と stderr warning（rate-limited）**が割り当てられ、shutdown summary に集約される（§4.7）。

#### 6.10.1 stdlib との対比

stdlib `logging` には、配送失敗を区別する公式 counter は存在しない。`Handler.handleError()` でハンドラ内エラーを処理するが、これは stderr に traceback を出すだけ（`docs.python.org/3/library/logging.html` Handler.handleError）。`logging.raiseExceptions` flag の制御も同様で、配送失敗の分類・記録は提供されない。

#### 6.10.2 OTel exporter との対比

OpenTelemetry Python の `BatchLogRecordProcessor` は queue + retry / drop 動作を持つが、これは「OTLP backend に最終的に届ける」ための retry queue であり、本ライブラリのような「配送失敗を policy 由来 / バグ由来に分類する」設計ではない。

---

### 6.11 軸 9: 設定管理パイプライン

| プロジェクト | 環境変数 | INI / dict | 引数 | マージ規則の明文化 |
|---|---|---|---|---|
| **D-SafeLogger** | ◎（`{prefix}_*` 13 種、`NO_COLOR` 業界標準） | ◎（INI と `config_dict`、同一バリデーションパイプライン） | ◎（26 引数、Fail-Fast） | ◎（環境変数 > INI/dict > 引数の厳格マージを設計書 §3 で明文化） |
| stdlib `logging` | △（`logging.basicConfig()` の `LOGLEVEL`、`PYTHONLOGGING` 等の限定的サポート） | ○（`fileConfig` / `dictConfig`） | ○ | △（マージ規則の体系化なし） |
| Loguru | △（個別の env 解釈） | △ | ◎（`logger.add()` の引数） | △ |
| structlog | △ | △（`structlog.configure()`） | ◎ | △ |
| picologging | stdlib 互換 | stdlib 互換 | stdlib 互換 | stdlib に依存 |
| Eliot | △ | △ | ◎ | △ |
| Logbook | △ | ○ | ◎ | △ |
| logfire | OTel 環境変数群 | logfire `pyproject.toml` 設定 | ◎ | OTel/logfire 独自 |
| OpenTelemetry Python | OTel 標準環境変数（`OTEL_*`） | △ | ◎ | OTel spec に依存 |

#### 6.11.1 観察事実

stdlib `logging` の `dictConfig` / `fileConfig` は強力だが、**「環境変数 > INI > 引数」の体系的マージ規則をライブラリ側で提供している事例**は本調査範囲では D-SafeLogger 以外に観測されない。

OTel の `OTEL_*` 環境変数群は OpenTelemetry 仕様として広範に存在するが、これは「OTel SDK に対する設定」であり、stdlib logging との 3 層パイプラインを構築するものではない。

#### 6.11.2 D-SafeLogger の独自性

D-SafeLogger の 3 層パイプラインは次の点で観測可能な差別化を持つ（§3.3、§5.16、§5.17）:

- **環境変数 > INI/dict > 引数**の厳格な上書き順序を設計書 §3 で明文化
- INI と `config_dict` が**同一バリデーションパイプライン**を通る（dict も全値文字列強制で `int` / `bool` 直接指定は `TypeError`）
- 各層に**変更主体**を割り当てる運用モデル（引数 = 開発者、INI = DevOps、環境変数 = オペレータ）
- 聖域（`diagnose` / `sens_kws` / `file_fmt` / `console_fmt`）が設定経路を遮断
- `env_prefix` で名前空間を分離可能

---

### 6.12 ライブラリ別の最新状況サマリ

| 項目 | D-SafeLogger v23j | stdlib `logging` | Loguru 0.7.3 | structlog 25.5.0 | picologging 0.9.3 | Eliot 1.18.0 | Logbook 1.9.2 | logfire 4.32.1 | OTel SDK 1.41.1 |
|---|---|---|---|---|---|---|---|---|---|
| 最新 release 日 | （v23j / 0.2.1、本レポート時点） | Python 3.14 | 2024-12-06 | 2025-10-27 | 2024-09-13（GitHub） | 2026-05-07 | — | （4.32.1） | （1.41.1） |
| ライセンス | Apache 2.0 | PSF | MIT | MIT or Apache-2.0 | MIT | Apache 2.0 | BSD-3-Clause | MIT | Apache-2.0 |
| Python 要件 | >=3.11 | （Python 自体） | >=3.5,<4 | >=3.8 | >=3.7 | >=3.10.0 | >=3.9 | >=3.9 | >=3.9 |
| ランタイム依存数 | **0** | 0 | 3（条件付き） | 1（条件付き） | 0 | 4 | 1 | 8 | 3 |
| stdlib 互換 | drop-in 拡張 | — | 置換 | 並走 / forward | drop-in 置換 | 並走 | 置換（互換あり） | OTel ブリッジ | OTel ブリッジ |
| append-only routing | ◎ | — | — | — | — | — | — | out | out |
| 完全性検証（SHA-256） | ◎ | — | — | — | — | — | — | — | out |
| マルチプロセス機能 | parent-side Writer + 分類済み配送状態 counters | 公式は QueueHandler + 別 listener 推奨（DIY） | `enqueue=True` | （stdlib 経由） | （stdlib 経由） | あり（Spanning Processes） | queue support | OTel exporter | OTel exporter |
| 配送状態分類 | 分類済み counters + writer_reject 6 内訳 | — | — | — | — | — | — | OTel retry queue | OTel retry queue |
| 構造化ログ | ◎（JSON Lines） | △ | ○（serialize） | ◎（中心機能） | △ | ◎（action tree） | ○ | ◎（OTel） | ○（OTel） |
| contextvars サポート | ◎（FrozenContext） | △ | ○ | ◎ | △ | ○ | △ | ○ | ○ |
| free-threaded 対応宣言 | ◎（設計書で明示） | △ | — | — | — | — | — | — | — |
| 3 層設定パイプライン | ◎（明文化） | △（dictConfig） | △ | △ | stdlib 互換 | △ | △ | OTel 環境変数 | OTel 標準 |

---

### 6.13 競合エコシステムの構図

#### 6.13.1 設計軸ごとの "champion" の分散

| 軸 | 観測される champion |
|---|---|
| 開発者体験（DX） | Loguru |
| 構造化ログのフロントエンド | structlog |
| 既存 stdlib の高速化 | picologging |
| causal action chain | Eliot |
| 観測 SaaS 統合 | logfire |
| 標準的な observability 規格 | OpenTelemetry |
| append-only ルーティング・完全性検証・分類済み配送状態 | **D-SafeLogger** |

各プロジェクトが**異なる設計軸を champion している**構図が観測される。**直接 1 対 1 で機能が重なる競合は、本一次ソース調査の範囲では存在しない**。

#### 6.13.2 「stdlib を置換するか・拡張するか」の境界

stdlib `logging` をどう扱うかで 3 つの流派が観測される:

1. **置換型**（独自 logger を中心とする）: Loguru / Logbook
2. **並走型**（stdlib と並んで動く、または bridge する）: structlog / Eliot / logfire / OpenTelemetry
3. **拡張型**（`setLoggerClass()` で stdlib に住み、機能を追加する）: **D-SafeLogger** / picologging

D-SafeLogger と picologging は**同じ拡張型**だが、目的が異なる:
- picologging: 機能は同じ、**速度を改善する**（C 拡張）
- D-SafeLogger: API は同じ、**設計レベルの差別化**を加える（append-only / 完全性検証 / multiprocess Writer / 配送状態分類）

#### 6.13.3 「観測性スタックの中での位置」

OpenTelemetry の logs spec が宣言する次の方針:

> "We embrace existing logging solutions and make sure OpenTelemetry works nicely with existing logging libraries."
> （OpenTelemetry Logs Specification、`opentelemetry.io/docs/specs/otel/logs/`）

これは「ロギングライブラリは置換しない」という OTel コミュニティのスタンス。logfire / OTel Python は stdlib `logging` の上に bridge を被せる方式である。

D-SafeLogger は stdlib `logging` の入口を維持するため、**OTel ブリッジ（`LoggingHandler`）と直接共存可能**である（`examples/15_opentelemetry_logging.md`）。`structured=True` + `contextualize(trace_id=..., span_id=...)` で trace correlation を実現する設計（§3.9.2）。

#### 6.13.4 「マルチプロセス × ローカルファイル出力」の空白地帯

stdlib 公式 cookbook が「マルチプロセスでファイル出力をするなら別プロセスを建てて socket / queue で送れ」と推奨するパターンを、ライブラリとして本体に同梱しているのは、本一次ソース調査の範囲では D-SafeLogger と Loguru（`enqueue=True`）の 2 件である。差分:

- Loguru: thread-safe / multiprocess-safe な enqueue を提供。`logger.add()` の単一 API に集約。
- D-SafeLogger: parent-side Writer + worker attach/detach の明示モデル。分類済み配送状態 counters。control plane 分離。bounded shutdown 契約。

「ローカルファイル出力 × multiprocess × 配送状態の説明可能性」を同時に満たすライブラリは、本調査範囲では D-SafeLogger 以外に観測されない。

#### 6.13.5 「サプライチェーン重視」の 2 系統

ランタイム依存ゼロを満たすのは D-SafeLogger と picologging の 2 件。差分:

- picologging: C 拡張（native build chain への間接依存、wheel 配布で隠蔽）
- D-SafeLogger: ピュア Python（`hashlib` / `multiprocessing` / `configparser` 等の標準ライブラリのみ）

「ピュア Python × ランタイム依存ゼロ × stdlib 拡張」は D-SafeLogger 固有の組み合わせ。

---

### 6.14 競合比較の整理

本章で確認した一次ソースから、次のように整理できる。

1. **直接競合は観測されない**: 各主要ロギングライブラリ（stdlib / Loguru / structlog / picologging / Eliot / Logbook / logfire / OTel）は異なる設計軸を champion しており、D-SafeLogger と機能が完全に重複するプロジェクトは本一次ソース調査範囲では存在しない。
2. **依存ゼロは picologging との 2 件のみ**: 本調査範囲では Loguru（3 条件付き）/ structlog（1 条件付き）/ Eliot（4）/ Logbook（1）/ logfire（8）/ OpenTelemetry SDK（3）の依存数と比較して、D-SafeLogger と picologging のみが完全な依存ゼロ。ピュア Python に限定すれば D-SafeLogger 単独。
3. **append-only ルーティングは Python エコシステムに先行例なし**: 設計書 §7.2 が主張する通り、本調査範囲でも append-only routing をコアアーキテクチャに据えたプロジェクトは観測されない。Logback / Log4j2 では options として存在するが、Python では D-SafeLogger が初出と観測される。
4. **stdlib 公式が「Windows でのアクティブログ rename 不能」を明文化**: `docs.python.org/3/library/logging.handlers.html` が WatchedFileHandler 節で明記している既知制約。D-SafeLogger の append-only 設計はこの公式制約への直接的応答として位置づけられる。
5. **stdlib 公式が「multiprocess 単一ファイル書き込み未サポート」を明文化**: cookbook が QueueHandler + QueueListener の別プロセス運用を推奨している。D-SafeLogger の `dsafelogger.mp` は同方向性（Writer-owned sinks + IPC）をライブラリ本体として提供する。
6. **分類済み配送状態 counters は他プロジェクトに先行例なし**: `accepted` / `delivered` / `KnownRejected` / `KnownDropped` / `UnexplainedLost` / `partial_delivered` の分類と `writer_reject` 6 内訳は、本一次ソース調査範囲では他プロジェクトに観測されない。OpenTelemetry の retry queue や Loguru の enqueue は配送 mechanism を提供するが、配送失敗の分類仕様ではない。
7. **完全性検証（SHA-256 サイドカー + マニフェスト）は他プロジェクトに先行例なし**: 本調査範囲では D-SafeLogger 以外に SHA-256 サイドカー・マニフェスト機能をライブラリ機能として提供するプロジェクトは観測されない。`sha256sum -c` 互換フォーマットの採用により OS 標準コマンドで検証可能な点も独自。
8. **free-threaded 対応の明示宣言は本調査範囲で D-SafeLogger 単独**: PEP 703 は 2023-10-24 Accepted、Python 3.13 から `--disable-gil` build 提供開始。Loguru / structlog / Eliot / Logbook / picologging / logfire / OpenTelemetry のいずれも公式 docs / GitHub README に free-threaded 対応の明示宣言が観測されない（2026-05-09 時点）。
9. **3 層設定パイプライン（環境変数 > INI/dict > 引数）の体系的マージ規則を明文化したプロジェクトは本調査範囲で D-SafeLogger 単独**: stdlib の `dictConfig` / `fileConfig` は強力だが、層間マージの体系規則は提供しない。OTel の `OTEL_*` 環境変数は SDK 設定範囲に限定される。
10. **OTel ブリッジ層との共存可能性**: D-SafeLogger は `logging.setLoggerClass()` で stdlib `logging` の入口を維持するため、OpenTelemetry Python の `LoggingHandler` と直接共存可能。これは Loguru / Logbook の置換型と異なる位置づけ。
11. **structlog との責務分離**: structlog がフロントエンド（イベント辞書組み立て）を担い、D-SafeLogger がバックエンド（ファイル出力 / routing / 完全性 / multiprocess）を担う組み合わせが `examples/16_structlog_coexistence.md` で 2 パターン提示されている。
12. **logfire / OTel との比較は責務軸が異なる**: logfire と OpenTelemetry Python は emission / export を担い、ファイル出力やローテーションは責務外。D-SafeLogger との競合関係ではなく、補完関係（trace_id 注入による correlation）。
13. **picologging との比較は目的軸が異なる**: 両者とも stdlib 互換だが、picologging は速度差別化（C 拡張で 4–17x）、D-SafeLogger は設計差別化（append-only / 完全性 / multiprocess Writer）。共存可能で機能的衝突なし。
14. **Loguru は GitHub stars 23.9k**（2026-05-09 時点）: 本調査対象内で最も多い stars 数。ただし stars は知名度の指標であり、本ライブラリとの設計軸の比較には用いない（評価方針 §6.1.3）。
15. **release 活動の最新性**: Eliot（2026-05-07）、structlog（2025-10-27）、Loguru（2024-12-06）、picologging（2024-09-13）。すべて活発に維持されている。Logbook の最新 release 日は本調査範囲で明示確認できず。

---

### 6.15 本章のまとめ

D-SafeLogger v23j のエコシステム上の位置は次の 5 点に集約される:

1. **直接競合はなく、設計軸が固有である**: append-only routing × 完全性検証 × multiprocess Writer × 分類済み配送状態 counters × free-threaded 対応 × 3 層設定パイプライン × ピュア Python 依存ゼロ の組み合わせは、本一次ソース調査範囲では他プロジェクトに観測されない。
2. **stdlib 拡張型のうち、機能差別化型は D-SafeLogger のみ**: picologging は同じ拡張型だが「速度差別化」が目的。Loguru / Logbook の置換型、structlog / Eliot / logfire / OTel の並走/ブリッジ型と異なるニッチを占める。
3. **stdlib 公式の既知制約への直接応答**: Windows でのアクティブログ rename 不能、multiprocess 単一ファイル未サポート、これら 2 つは Python 公式 docs 自身が明文化している制約であり、D-SafeLogger の append-only ルーティング・parent-side Writer はこれらへの直接応答。
4. **OpenTelemetry / structlog / logfire との関係は競合ではなく共存**: OTel ブリッジ・structlog 共存（2 パターン）・logfire は OTel exporter 経由、いずれも `examples/` で integration patterns が提示されている。
5. **PEP 703 への明示対応宣言は本調査範囲で D-SafeLogger 単独**: 共有状態の明示ロック化、`f_locals` の repr 済み snapshot 化、内部 thread の空 Context 開始 が仕様レベルで規定されている。

これらは次章「7. OSS 公開時の位置づけ」で**ポジショニング論理**として、サプライチェーン重視層 / Windows 運用層 / 監査層 / free-threaded 移行層 / stdlib コンサバ層 / multiprocess 監査層 への適合度として再評価される。

---

> **本章の主な参照資料**: D-SafeLogger 公開資料: `docs/design/D_SafeLogger_Specification_v23j_full.md` §1, §2, §3, §7.2, §11, §12 / `README.md` / `BENCHMARK.md` / `examples/08_compliance_audit.md` / `examples/15_opentelemetry_logging.md` / `examples/16_structlog_coexistence.md`. 一次ソース: `pypi.org/pypi/loguru/json` / `pypi.org/pypi/structlog/json` / `pypi.org/pypi/picologging/json` / `pypi.org/pypi/eliot/json` / `pypi.org/pypi/Logbook/json` / `pypi.org/pypi/logfire/json` / `pypi.org/pypi/opentelemetry-sdk/json` / `docs.python.org/3/library/logging.html` / `docs.python.org/3/library/logging.handlers.html` / `docs.python.org/3/howto/logging-cookbook.html` / `docs.python.org/3/whatsnew/3.13.html` / `peps.python.org/pep-0703/` / `github.com/Delgan/loguru` / `github.com/microsoft/picologging` / `www.structlog.org` / `eliot.readthedocs.io` / `logbook.readthedocs.io` / `pydantic.dev/docs/logfire/` / `github.com/pydantic/logfire` / `opentelemetry.io/docs/specs/otel/logs/` / `opentelemetry.io/docs/languages/python/instrumentation/`. 確認日: 2026-05-09。
> 本書は現行 v23j アーキテクチャの説明と評価を目的とし、改善提案・課題管理・将来ロードマップは扱わない。private planning materials は参照対象から除外している。

## 第 7 章 OSS 公開時の位置づけ

### 7.1 本章のスコープと方針

#### 7.1.1 本章のスコープ

本章は、OSS 公開時に本ライブラリのアーキテクチャ特性が、観測可能なエコシステム要件・運用パターンに対してどう適合するかを論理的に整理する。採用率・人気・反響の予測は行わず、公開資料から確認できる設計上の位置づけに限定する。

これを踏まえ、本章は次の方針で記述する:

| 含めるもの | 含めないもの |
|---|---|
| アーキテクチャ特性（既存章で観測した事実） | 「人気が出る」「広く採用される」等の予測 |
| エコシステム要件・運用パターン（一次ソースで確認可能なもの） | 「素晴らしい」「優れている」等の賛辞 |
| 特性と要件の適合関係（論理的対応） | 「日本では受けるが海外では…」のような根拠不在の地域論 |
| 観測可能なセグメント別の技術的価値 | 採用率・普及度の数値予測 |

#### 7.1.2 評価軸の定義

本章の評価は次の論理構造で記述する:

```text
[観測されたアーキテクチャ特性] × [観測されたエコシステム要件・運用パターン]
  ↓
適合する場合: その特性がそのセグメントに対してどのような技術的価値を提供できるか
適合しない場合: そのセグメントの要件と本ライブラリの責務範囲が交差しない理由
```

すなわち「届きうる層」と「届かない層」の両方を**論理として**記述し、どちらにも価値判断を加えない。

#### 7.1.3 想定セグメントの選定根拠

第 1〜6 章で確認した本ライブラリのアーキテクチャ特性を網羅するため、次の 6 セグメントを選定する。各セグメントは「特定の運用要件・技術要件を持つ開発者・組織のグループ」として定義され、アーキテクチャ特性のいずれかの軸が直接対応する。

| セグメント | 対応する D-SafeLogger 特性 |
|---|---|
| サプライチェーンセキュリティ重視層 | ランタイム外部依存ゼロ + Vendor-Agnostic + Apache 2.0 |
| Windows サーバ運用層 | Append-Only ルーティング + Windows rename 問題回避 |
| 監査・コンプライアンス層 | SHA-256 サイドカー + マニフェスト + `sha256sum -c` 互換 |
| Free-threaded 移行検討層 | PEP 703 明示対応 + 共有状態の明示ロック化 |
| stdlib コンサバ層 | drop-in 拡張 + 既存 `getLogger()` 呼び出しサイト保持 |
| multiprocess 監査層 | parent-side Writer + 分類済み配送状態 counters + bounded shutdown |

これらは独立したセグメントではなく**重なりうる**（例: 監査・コンプライアンス層は Windows サーバ運用層と重なることが多い）。本章は各セグメントを独立に評価したうえで、§7.9 で重複・交差・国内外差を整理する。

---

### 7.2 セグメント 1: サプライチェーンセキュリティ重視層

#### 7.2.1 セグメントの観測される要件

このセグメントは次のような運用要件を持つ:

- インストール時の依存パッケージ数を最小化したい（CVE 露出面の縮小）
- 依存パッケージのライセンス互換性を組織のポリシーに合わせる必要がある
- 依存パッケージの更新影響を継続的に追跡する必要がある（SBOM / OSV など）
- 依存パッケージの乗っ取り（typosquatting / 悪意あるメンテナ交代）リスクを構造的に減らしたい

#### 7.2.2 D-SafeLogger の対応する特性

第 4 章 §4.2、第 6 章 §6.3 で確認した事実:

- **ランタイム外部依存ゼロ**を「絶対条件」として設計書 §1 で宣言
- **Vendor-Agnostic 原則**: コアモジュール（`src/dsafelogger/`）にベンダー固有の import がコアコード上に存在しない（OpenTelemetry 等を含む）
- **ライセンス**: Apache License 2.0
- **配布物**: wheel は `src/dsafelogger/` の runtime package files のみを含む。sdist は docs / examples / tests / benchmark summaries / selected benchmark summaries を含み、private planning materials と一時作業ファイルは含めない。
- **`py.typed` 同梱**: 型情報の明示

#### 7.2.3 適合関係

このセグメントが本ライブラリに見出しうる技術的価値は次のように観測できる:

1. **追加 CVE 露出面が（理論上）ゼロ**: 本ライブラリ自体の脆弱性以外に新規の CVE 経路が増えない。Loguru / structlog / Eliot / Logbook / logfire / OpenTelemetry SDK のすべてに条件付きまたは無条件のランタイム依存があり（§6.3）、それらに比してサプライチェーン経路の本数が少ない。
2. **ライセンス互換性のチェック単位が 1 つ**: Apache 2.0 のみ。MIT / BSD-3-Clause / OPL 等の組み合わせ管理が不要。
3. **SBOM 生成時の項目が最小**: 自動 SBOM ツール（CycloneDX / SPDX）の出力に追加項目を増やさない。
4. **サードパーティ乗っ取りリスクがない**: 依存パッケージのメンテナ交代・悪意ある更新が本ライブラリ経由で混入する経路が存在しない。
5. **OSV / GHSA スキャンの hit がライブラリ自体に集中**: `pip-audit` / `safety` などの脆弱性スキャナの結果を本ライブラリ自体に絞り込める。

#### 7.2.4 適合しない場合の論理

本セグメントの要件が満たされない条件は次の通り:

- **「Pydantic / OpenTelemetry エコシステム前提でロギング統合したい」**ニーズには直接適合しない（logfire / OTel SDK のほうが直接的）。ただし `examples/15_opentelemetry_logging.md` の `contextualize(trace_id=...)` パターンで間接統合は可能（§3.9.2）。
- **「単一の依存パッケージから多機能を引きたい」**ニーズには適合しない。本ライブラリは責務範囲を狭く定義しており、observability 全体（traces / metrics / logs）を扱わない（README "Compatibility / Non-goals" 節）。

#### 7.2.5 位置づけ

本ライブラリは「依存ゼロ × ピュア Python × stdlib 拡張」という組み合わせを満たす点で、本一次ソース調査範囲では picologging（C 拡張）以外に直接の同等品が観測されない（§6.3.1）。これは「依存を増やさずにロギングを強化したい」要件に対する**他ライブラリとは異なる設計軸を持つ選択肢**として位置づけられる。

---

### 7.3 セグメント 2: Windows サーバ運用層

#### 7.3.1 セグメントの観測される要件

このセグメントは次のような運用要件を持つ:

- Windows Server 上で常駐サービスを運用する
- アンチウイルス / バックアップツール / 監視エージェントが同時にログファイルを開く環境
- アクティブログファイルの rename / move / delete が `PermissionError` で失敗する場面に遭遇する
- デフォルトの stdlib `RotatingFileHandler` / `TimedRotatingFileHandler` で midnight rotation が失敗するインシデントを経験している

#### 7.3.2 stdlib 公式の既知制約

`docs.python.org/3/library/logging.handlers.html` が明示する制約:

> "This handler is not appropriate for use under Windows, because under Windows open log files cannot be moved or renamed - logging opens the files with exclusive locks."
> （`logging.handlers` WatchedFileHandler 節）

この制約は WatchedFileHandler に関する記述だが、**Windows 上のアクティブログファイルが他プロセスから rename できない**という OS 制約自体が公式に明文化されている。

#### 7.3.3 D-SafeLogger の対応する特性

第 5 章 §5.1、第 6 章 §6.5 で確認した事実:

- **Append-Only ルーティング**: rename / truncate を行わず、出力先ファイル名を切り替えで世代管理する設計（設計書 §7.2）
- **9 routing modes**: `daily` / `hourly` / `min_interval` / `startup_interval` / `size` / `count` / `cyclic_weekday` / `cyclic_month` / `none`、いずれも append-only
- **自己修復性**: パージ失敗時は次回切り替えタイミングでリトライ
- **`pg_name` のサニタイズ規則**: Windows のファイル名禁止文字（`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`）を `_` に置換
- **CLI ツール `dsafelogger tail -f`**: 透過的なファイル切り替え追随（Append-Only モデルの運用補完）

#### 7.3.4 適合関係

このセグメントが本ライブラリに見出しうる技術的価値は次のように観測できる:

1. **Windows ロック競合に起因する rename failure が発生しない**: 設計レベルで rename 操作を採らないため、stdlib 公式が明文化している制約自体に直面しない。
2. **アンチウイルス / バックアップツールとの共存**: 他プロセスがログファイルを開いていても、ログ出力は新名のファイルに切り替わるため影響を受けない。
3. **midnight rotation 失敗インシデントが構造的に消える**: `routing_mode='daily'` での切り替えは新ファイルを open するだけで、旧ファイルへの rename を行わない。
4. **`tail -f` の運用上の弱点を CLI が補完**: ファイル名が動的に変わる Append-Only モデルの弱点を、`dsafelogger tail -f` の透過的追随で補完（設計書 §8.1）。

#### 7.3.5 適合しない場合の論理

- **「単一固定ファイル名（`app.log`）で運用したい」**ニーズには `routing_mode='none'` が対応するが、その場合は append-only の長所（rename 競合の回避）の必要性自体が薄い（rotation 自体が発生しないため）。
- **「Linux 専用環境で `logrotate` を運用したい」**ニーズには `routing_mode='none'` + `ReopenLogFiles()` で対応する。ただし Linux/POSIX では rename がファイル操作として成功しやすい一方、writer が旧FDへ書き続ける場合があるため、active file を外部から動かす運用では §5.3.4 の境界条件を確認する必要がある。

#### 7.3.6 位置づけ

stdlib 公式が明文化している Windows rename 不能制約に対し、Python エコシステムでこれを設計の中核として解決するライブラリは本一次ソース調査範囲では本ライブラリ以外に観測されない（§6.5.3）。Java では Logback / Log4j2 が同等の append-only オプションを提供するが、Python では本ライブラリが先行する。

---

### 7.4 セグメント 3: 監査・コンプライアンス層

#### 7.4.1 セグメントの観測される要件

このセグメントは次のような運用要件を持つ:

- 規制業種（医療 HIPAA、金融 SOC 2 / PCI-DSS、政府 FedRAMP 等）で稼働するアプリケーション
- ログファイルの改竄検知が監査要件として求められる
- ログファイルの欠損検知が監査要件として求められる
- 検証手段が標準的（OS 標準コマンド / 業界標準フォーマット）であることが望ましい
- 機密情報（API キー、トークン、パスワード）がログに混入しない仕組みが求められる

#### 7.4.2 D-SafeLogger の対応する特性

第 4 章 §4.4、§4.5、第 5 章 §5.4、第 5 章 §5.21 で確認した事実:

- **SHA-256 サイドカー** (`{元ファイル名}.sha256`): `sha256sum -c` 互換フォーマット、相対パス記載、`os.replace()` による原子的書き込み
- **マニフェストファイル** (`manifest_path`): タイムスタンプ付き追記、別ディレクトリ・別権限で保管推奨、ファイル消失検知
- **chunk 64KB 読み**: 標準ライブラリ `hashlib` のみ使用
- **`diagnose` の聖域化**: 環境変数 `D_LOG_DIAGNOSE=1` のみで有効化、INI / 引数からは設定不可
- **`sens_kws` ビルトイン 12 語のマスキング**: `f_locals` 展開時の変数名部分一致でマスク
- **HMAC・CLI 検証コマンドはスコープ外として明示**: 設計書 §7.6.7

`examples/08_compliance_audit.md` の冒頭は次の通り規定する:

> In regulated industries — healthcare (HIPAA), finance (SOC 2, PCI-DSS), government (FedRAMP) — proving that logs haven't been tampered with isn't optional.
> （`examples/08_compliance_audit.md`）

#### 7.4.3 適合関係

このセグメントが本ライブラリに見出しうる技術的価値は次のように観測できる:

1. **OS 標準コマンドで検証可能**: `sha256sum -c` 互換フォーマットの採用により、`coreutils` の `sha256sum` または PowerShell の `Get-FileHash` で検証可能。独自検証ツールを監査対象に含める必要がない。
2. **ファイル相対パス記載によりログ移送に強い**: ログ一式を別の場所（監査用 WORM ストレージ等）に移送しても検証が壊れない。
3. **マニフェストによるファイル消失検知**: サイドカー単独では検知不可能な「ファイル + サイドカーが一緒に削除」パターンを、別ディレクトリ・別権限のマニフェストとの不整合で検知できる。
4. **`diagnose` の構造的封じ込め**: 「debug mode を本番に残してしまう」パターンを構造的に排除（コードに `diagnose=True` と書ける手段が存在しない、INI からも設定不可、`"1"` のみが有効値）。
5. **マスキングのカスタマイズ可能性**: `sens_kws` 追加で組織固有のセンシティブキーワード（`ssn`、`credit_card`、`account_number` 等）を追加可能。
6. **脅威モデルの境界がドキュメントで明示**: 攻撃者が同一権限でファイル + サイドカー + マニフェストを書き換え可能な場合は改竄検知できないことが `examples/08_compliance_audit.md` Threat Model セクションで明文化されており、過剰な期待による誤用を防ぐ。

#### 7.4.4 適合しない場合の論理

- **「暗号学的非否認性（HMAC 署名 / デジタル署名）が監査要件」**の場合は本ライブラリのスコープ外。設計書 §7.6.7 が明示的に除外している。本ライブラリのハッシュを入力とする外部署名ツール（D エコシステムの別ライブラリ等）に責務を委譲する方針。
- **「アクティブログファイルの完全性も保証したい」**ニーズには適合しない。本ライブラリのハッシュは「書き込み完了したファイル」のみが対象（§5.4 ハッシュは中間状態に意味がないため）。
- **「ログを WORM ストレージにリアルタイム書き込みしたい」**場合は、本ライブラリは local file 出力までを担当し、shipping は外部ツール（Fluent Bit / Vector / Filebeat 等）に委譲する設計（README "Compatibility / Non-goals" 節）。

#### 7.4.5 位置づけ

本一次ソース調査範囲では、SHA-256 サイドカーやマニフェストをライブラリ機能として提供する Python プロジェクトは観測されない（§6.8.1）。OpenTelemetry / logfire は emission / export を担うが、ファイル整合性は責務範囲外。Loguru / structlog / Eliot / Logbook / picologging のいずれも公式 docs に完全性検証機能の言及がない。本ライブラリは「ローカルファイル監査」というニッチに直接対応する技術的選択肢として位置づけられる。

---

### 7.5 セグメント 4: Free-threaded 移行検討層

#### 7.5.1 セグメントの観測される要件

このセグメントは次のような技術要件を持つ:

- PEP 703 Accepted（2023-10-24）以降、`--disable-gil` build を試験的または本番採用
- 共有可変状態を持つライブラリの GIL 非依存対応を確認する必要がある
- C 拡張を含むライブラリの `Py_mod_gil` 対応を確認する必要がある
- `list` / `dict` の暗黙的スレッド安全性に依存しない実装を求める

#### 7.5.2 PEP 703 の現状

`peps.python.org/pep-0703/` の主要事実（§6.9）:

- 2023-10-24 Accepted
- Python 3.13+ で `--disable-gil` build flag により利用可能
- ロールアウト方針: "the rollout be gradual and break as little as possible"
- ランタイム制御: `PYTHON_GIL` 環境変数、`Py_mod_gil` モジュールスロット

#### 7.5.3 D-SafeLogger の対応する特性

第 5 章 §5.19、第 6 章 §6.9 で確認した事実:

- 設計書 §1 が **Python 3.13 以上の free-threaded build を設計対象として明示**
- 設計書 §2 が「`_configure_state`、`_active_pipeline`、`_active_workers`、`_custom_levels` 等の共有状態は GIL の存在を前提にせず、明示ロックにより保護する。`list` / `dict` の実装依存の原子性には依存しない」と規定
- v21 改訂で `ConfigureLogger` 全体を `_lifecycle_lock` 保持下で実行
- `f_locals` を producer thread でマスク済み repr スナップショットに変換（cross-thread 安全性、§9.4）
- 内部 thread を空 `Context` で開始（§9.5）
- ピュア Python 実装のため `Py_mod_gil` 対応（C 拡張側）の必要がない
- `TESTING.md` に手動テスト手順掲載: `PYTHON_GIL=0 uvx --python cpython-3.13+freethreaded --from pytest pytest tests -v`

#### 7.5.4 適合関係

このセグメントが本ライブラリに見出しうる技術的価値は次のように観測できる:

1. **PEP 703 採用時の追加対応コストがゼロ**: 既に明示ロックで保護されているため、`--disable-gil` build に切り替えても本ライブラリ起因の race condition リスクが構造的に低い。
2. **ピュア Python 実装のため C 拡張対応が不要**: `Py_mod_gil` モジュールスロットの対応・wheel ビルドの再構成・C extension の重新検証が不要。picologging のような C 拡張ライブラリと比較してコスト構造が異なる。
3. **free-threaded build の手動テスト手順が文書化されている**: 通常 CI matrix は CPython 3.11〜3.14 regular build を対象とし、free-threaded build は `TESTING.md` の手順で検証する。
4. **共有状態の明示ロック化が設計判断として宣言されている**: ロックの設計意図がドキュメント化されているため、free-threaded 環境での保守時に意図を追跡可能。

#### 7.5.5 適合しない場合の論理

- **「free-threaded build に興味がない、GIL 有効環境のみで十分」**な層には、本特性は直接的価値を提供しない。ただしこの場合でも、明示ロック化は free-threaded だけでなく通常 build でも race condition リスクを下げる方向で機能する（中立的）。
- **「自前 C 拡張で高速化が必須」**な層には picologging のほうが目的に合致する（速度差別化）。本ライブラリと picologging は責務軸が異なるため共存可能（§6.13.2）。

#### 7.5.6 位置づけ

本一次ソース調査範囲では、Loguru / structlog / Eliot / Logbook / picologging / logfire / OpenTelemetry の公式 docs / GitHub README に free-threaded 対応の明示宣言が観測されない（§6.9.1、2026-05-09 時点）。本ライブラリが PEP 703 Accepted 後、設計対象として明示宣言している点は、本調査範囲内では特異な位置づけである。

これは「PEP 703 を採用検討する組織が、ロギング層で先行的に対応するライブラリを探している」要件に対する**他ライブラリとは異なる設計軸を持つ選択肢**として観測される。ただし、PEP 703 のロールアウトは段階的（"gradual and break as little as possible"）であり、現時点で free-threaded build を本番採用する組織の数は限定的と考えられる（このセグメントの規模は本章では予測しない）。

---

### 7.6 セグメント 5: stdlib コンサバ層

#### 7.6.1 セグメントの観測される要件

このセグメントは次のような運用要件・志向を持つ:

- 既存コードベースが `import logging` / `logging.getLogger(__name__)` を中心に書かれている
- SQLAlchemy / Django / Flask / requests / boto3 等の `logging.getLogger()` ベースのサードパーティを多用
- 「ロギングフレームワークを置き換える」コストを払いたくない
- 標準ライブラリの使い方 / 慣習を維持したい
- 公式の `dictConfig` / `fileConfig` 構造への親和性を維持したい

#### 7.6.2 D-SafeLogger の対応する特性

第 1 章 §1.4、第 3 章 §3.7、第 6 章 §6.4 で確認した事実:

- **`logging.setLoggerClass()` による drop-in 拡張**: 既存の `logging.getLogger()` / `logger.info()` 呼び出しサイトを変更しない
- **第三者ライブラリの自動共参加**: SQLAlchemy / Django 等が `logging.getLogger()` で取得した logger は本ライブラリの設定フローに乗る
- **`config_dict` は INI と同一バリデーション**: 公式 `dictConfig` とは構造が異なるが、INI 互換のシンプルな 2 階層構造（`global` + `dsafelogger:モジュール名`）
- **既存呼び出しサイト保持**: `examples/03_migration_from_stdlib.md` で 3 移行パターン（basicConfig / TimedRotatingFileHandler / dictConfig）を提示、いずれも `logger.info()` 呼び出しサイトは変更不要
- **setup コード行数 50–60% 削減**: handler / formatter / setLevel の手動配線が `ConfigureLogger()` パラメータに集約

#### 7.6.3 適合関係

このセグメントが本ライブラリに見出しうる技術的価値は次のように観測できる:

1. **既存コードベースを書き換えずに機能追加可能**: append-only routing / 完全性検証 / 環境変数オーバーライド / multiprocess Writer を、`logger.info()` の呼び出しサイトを変更せずに追加できる。
2. **第三者ライブラリのログも統一管理**: SQLAlchemy のクエリログ / Django の middleware ログ / requests のリトライログ等が、本ライブラリの routing / 完全性検証の対象に含まれる（共通の `logging.getLogger()` を使うため）。
3. **stdlib API の意味論が壊されない**: `record.levelname` を改変しない、`addLevelName()` のグローバル副作用を使わない、`QueueHandler.prepare()` 完全オーバーライドで stdlib 差異から意味論を切り離す（§4.9、§5.4.4）。第三者の `SMTPHandler` / `pytest caplog` 等も意図通り動作する。
4. **学習コストが低い**: 公開 API の入口は `ConfigureLogger()` と `GetLogger()` の 2 関数。最小コードは 3 行（§3.1–§3.2）。

#### 7.6.4 適合しない場合の論理

- **「Loguru / structlog の API（`logger.bind()` / `logger.add()`）を使いたい」**ニーズには適合しない。本ライブラリは置換型ではない。ただし structlog との共存は `examples/16_structlog_coexistence.md` で 2 パターン提示されている（§3.9.1）。
- **「stdlib `logging` の dictConfig の細かいフィルタ・カスタムハンドラ構造を維持したい」**場合は、本ライブラリの `config_dict` の 2 階層構造とは粒度が異なるため、移行時に構造変換が必要。

#### 7.6.5 位置づけ

本ライブラリは picologging と同じ「stdlib 拡張型」だが、目的が異なる（§6.13.2）:
- picologging: 機能は同じ、速度を改善
- D-SafeLogger: API は同じ、設計レベルの差別化を加える

「stdlib `logging` の API を維持したまま、ファイル出力境界より下を強化したい」という要件に対しては、本一次ソース調査範囲では本ライブラリ以外に直接対応する選択肢が観測されない。Loguru / Logbook は置換型、structlog は並走型、logfire / OTel はブリッジ型のため、設計軸が交差しない。

---

### 7.7 セグメント 6: multiprocess 監査層

#### 7.7.1 セグメントの観測される要件

このセグメントは次のような運用要件を持つ:

- 複数 worker process（Gunicorn / uWSGI / Celery / multiprocessing.Pool / ProcessPoolExecutor 等）からのロギングを集約したい
- worker process が共有ログファイルを直接開かない構成にしたい（Windows ロック / Linux file descriptor 競合の回避）
- バックプレッシャー時のログ欠損を「無音の隙間」ではなく counter / warning として可視化したい
- worker crash 時の shutdown 動作が予測可能であることを求める
- shutdown summary により異常事象の事後解析を可能にしたい

#### 7.7.2 stdlib 公式の見解

`docs.python.org/3/howto/logging-cookbook.html` の明文化（§6.5.2 再掲）:

> "Logging to a single file from multiple processes is not supported, because there is no standard way to serialize access to a single file across multiple processes in Python."
>
> "When deploying web applications using Gunicorn or uWSGI (or similar), multiple worker processes are created to handle client requests. In such environments, **avoid creating file-based handlers directly in your web application**. Instead, use a `SocketHandler` to log from the web application to a listener in a separate process."

これは「マルチプロセスでファイル出力する場合、別プロセス listener が必要」という公式推奨。

#### 7.7.3 D-SafeLogger の対応する特性

第 2 章 §2.8、第 5 章 §5.11–§5.14、第 6 章 §6.7 で確認した事実:

- **parent-side Writer による sink ownership**: file sink・routing・hash・manifest・purge・archive・reopen のすべてが Writer に集約
- **worker は IPC で `LogEvent` を送信のみ**: 共有ログファイルを直接開かない（§4.6.1）
- **log plane / control plane の完全分離**: 通常ログと制御コマンドが別 queue、ACK は per-request `Pipe(duplex=False)`
- **分類済み配送状態 counters**: lifecycle 5 + terminal 6 + qualifier 1
- **`writer_reject` の 6 内訳**（v23h）: `writer_route_reject` / `writer_reconstruct_reject` / `writer_close_marker_reject` / `writer_sink_reject` / `writer_policy_reject` / `writer_format_reject`
- **shutdown summary**: 全 counter を集約して shutdown 時に出力
- **bounded shutdown 契約**（v23h）: `bounded wait (≤ 10 秒) → visible warning → process exits`、daemon=True で physical 保証
- **active client registry + worker crash timeout**: worker crash 時の registry 残存を timeout で打ち切る（silent hang を起こさない）
- **3 worker_model 対応**: `process` / `pool` / `executor`（`ProcessPoolExecutor` のみ、`ThreadPoolExecutor` は対象外）
- **fork 継承後の child 専用 client identity**: 親の identity を再利用しない規約
- **registry hash 照合（SHA-256）**: Writer bootstrap ready ACK 時と attach 時の 2 タイミング

#### 7.7.4 適合関係

このセグメントが本ライブラリに見出しうる技術的価値は次のように観測できる:

1. **stdlib 公式の推奨構造をライブラリ本体で提供**: 「別プロセス listener + IPC」という公式推奨パターンを DIY せずに利用できる。
2. **配送失敗の説明可能性**: bounded queue の overflow / Writer crash / sink failure / route 解決不能 / policy reject 等が分類済み counters + 6 内訳として記録される。「ログが消えた」を一律ではなく、policy 由来 / バグ由来 / 未知に分類して扱える。
3. **`unexpected_loss` のみがバグ扱い**: 残り 6 種は policy 由来として運用上説明可能であり、「accepted log が理由なく消えた状態」のみが alarm 対象になる粒度が定義されている。
4. **Windows 環境での worker からのファイル直接アクセスがない**: parent Writer のみが file を保持するため、worker から見た Windows ロック競合は発生しない（worker は IPC のみを使うため）。
5. **bounded shutdown による host process survival 保証**: drain 経路に未知の hang が混入しても、`WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0` 秒の bounded join + visible warning + daemon thread で host process は exit する。
6. **Writer exit code の非ゼロ通知**: 監視システム（systemd / Kubernetes liveness probe 等）から Writer の異常終了を検出可能。
7. **`examples/12_multiprocess_logging.md` の 438 行ガイド**: Process / Pool / Executor の 3 パターン、Windows spawn 規則、attach/detach lifecycle、failure mode 一覧、shutdown summary 解釈を網羅。

#### 7.7.5 適合しない場合の論理

- **「raw multiprocess throughput が最優先」**なニーズには適合しない。`BENCHMARK.md` および §C.3 で確認した通り、raw multiprocess throughput では stdlib logging が先行する（D-SafeLogger sync は stdlib sync の 63–75%）。本ライブラリの multiprocess 価値は raw throughput ではなく、Writer-owned sinks + 配送状態の観測性。
- **「remote aggregation / network protocol で集約したい」**ニーズはスコープ外（設計書 §11.2、Out-of-scope: remote aggregation / network protocol）。ローカル単一ホスト内の集約に限定。
- **「Writer 並列化で fan-in scalability を改善したい」**ニーズはスコープ外（v23 系不変条件、§12.1）。Writer 単独所有による安全性と衝突しやすいため、別途ユーザー判断を仰ぐ事項として明示。

#### 7.7.6 位置づけ

本一次ソース調査範囲では、配送失敗を分類済み counters / warning / shutdown summary に反映する Python ロギングライブラリは本ライブラリ以外に観測されない（§6.7.3、§6.10）。Loguru の `enqueue=True` はマルチプロセス安全な hand-off を提供するが、配送状態の分類は提供しない。OpenTelemetry の retry queue は OTLP backend への retry mechanism であり、配送失敗の分類仕様ではない。

「ローカルファイル出力 × multiprocess × 配送状態の説明可能性」を同時に満たすライブラリは、本調査範囲では本ライブラリが固有の選択肢として観測される（§6.13.4）。

---

### 7.8 セグメント間の重複と交差

これら 6 セグメントは独立ではなく、運用上は重なりやすい。

| 重なる組合せ | 観測される代表的なユースケース |
|---|---|
| サプライチェーン × stdlib コンサバ | 政府・公共系・規制業種で、依存パッケージの追加を最小化したいシステム |
| Windows × 監査・コンプライアンス | 規制業種の Windows サーバ運用（金融・保険のクライアント端末監査等） |
| Windows × multiprocess 監査 | Windows Server 上の Gunicorn for Windows / Celery worker 構成 |
| 監査・コンプライアンス × multiprocess 監査 | 監査要件のあるバッチ処理基盤、ETL pipeline、複数 worker でのログ集約 |
| Free-threaded × stdlib コンサバ | PEP 703 採用検討中のバックエンド開発者で既存 stdlib `logging` 構成を維持したい |
| サプライチェーン × Free-threaded | C 拡張依存を避けつつ free-threaded 移行する組織 |

これらの重なりは「アーキテクチャ特性が複数の運用要件に同時対応する」構造を示しているのみで、各セグメントの規模や採用率を予測するものではない。

---

### 7.9 国内 vs 海外のエコシステム差

#### 7.9.1 評価方針の再確認

OSS 公開時には国内・海外双方からの評価軸が想定されるが、本書は**主観的な人気予測は記載しない**。本節では「観測可能なエコシステム特性の地域差」と「本ライブラリのアーキテクチャ特性のどの軸がその差に対応するか」のみを記述する。

#### 7.9.2 観測可能なエコシステム特性の地域差

以下は技術コミュニティ・運用環境の**観測可能な傾向**であり、本ライブラリの優劣判断には用いない。

| 観点 | 観測される地域差 | 本ライブラリの対応軸 |
|---|---|---|
| Windows サーバの業務システム比率 | 国内では国内向け業務 SaaS / オンプレ業務システムでの Windows Server 採用が比較的多い傾向（公的統計の範囲ではエンタープライズ用途比率が高い）。海外は Linux 主体だが Windows 採用組織も存在 | Append-Only ルーティング（§7.3） |
| 監査・コンプライアンス要件の地域別フレームワーク | 国内: 金融庁規則、個人情報保護法、医療情報ガイドライン等。海外: HIPAA / SOC 2 / PCI-DSS / FedRAMP / GDPR 等。**いずれもログの完全性・改竄検知を要件に含むケースが存在** | SHA-256 サイドカー + マニフェスト（§7.4） |
| 日本語ドキュメント需要 | 国内は日本語ドキュメントへの親和性が高い | `README_ja.md` あり、設計書本体も日本語 |
| OSS への組織的貢献文化 | 海外（特に米欧）は OSS PR / Issue の活発度が高い傾向。国内は increasing だが歴史的に小さい | （ライブラリ側の対応軸は中立） |
| OpenTelemetry エコシステム採用 | グローバルで急速に広がる傾向。国内・海外で時間差はあるが採用方向は同じ | OTel ブリッジとの共存（§7.6） |
| サプライチェーンセキュリティ意識 | 海外はサプライチェーン攻撃事例（SolarWinds 等）以降、米国 Executive Order 14028 等の規制で要件化が進む。国内も SBOM 提供が経産省「サイバー・フィジカル・セキュリティ対策フレームワーク」等で言及 | 依存ゼロ × Apache 2.0（§7.2） |

#### 7.9.3 国内に対する論理的対応

国内における運用環境特性（Windows 業務システム比率、日本語ドキュメント親和性、規制業種のオンプレ運用）と本ライブラリの特性軸の対応:

- **Append-Only ルーティング × Windows Server 採用組織**: §7.3 で確認した stdlib 公式既知制約への直接応答。
- **SHA-256 完全性 × 国内規制業種（金融・医療・公共）**: §7.4 で確認した監査ログ要件への対応。`sha256sum -c` 互換と OS 標準コマンドでの検証可能性は、国内オンプレ運用での「外部ツール導入を最小化したい」要件と対応する。
- **`README_ja.md` + 日本語設計書**: 設計書（`docs/design/D_SafeLogger_Specification_v23j_full.md`）が日本語で記述されており、設計判断の文脈を母語で参照できる点は、国内開発者にとって学習コストが下がる方向で機能する。

これらは「国内で人気が出る」予測ではなく、「国内に観測される運用要件パターンに対して特性が対応する」論理的対応の整理である。

#### 7.9.4 海外に対する論理的対応

海外における技術コミュニティ特性（Linux 主体、OpenTelemetry エコシステム広がり、OSS 貢献活発度、サプライチェーン規制要件化）と本ライブラリの特性軸の対応:

- **依存ゼロ × Apache 2.0 × サプライチェーン規制要件**: §7.2 で確認した SBOM / Executive Order 14028 / NIST SSDF 等の文脈に対する対応。
- **OpenTelemetry ブリッジとの共存 × OTel エコシステム広がり**: §7.6 で確認した `LoggingHandler` 経由の trace correlation。
- **PEP 703 free-threaded 対応 × 海外コミュニティの先行採用傾向**: §7.5 で確認した PEP 703 Accepted 後の対応宣言。
- **`README.md`（英語）+ examples 英語**: 設計書本体は日本語だが、examples 17 ファイルと README は英語で記述されている。
- **monorepo / 大規模 microservice 構成 × multiprocess 監査**: §7.7 で確認した parent-side Writer + 分類済み配送状態 counters は、海外で典型的な大規模 microservice 構成での観測性要件と対応する。

ただし、海外コミュニティでは Loguru / structlog / OpenTelemetry Python のすでに確立した選択肢が広く認知されているため、本ライブラリが直接的な置換候補として位置づけられるよりは、「特定の運用要件（Windows・監査・依存ゼロ）を持つ subset 組織での選択肢」として位置づけられると論理的に推定される。

#### 7.9.5 国内・海外で共通する論理対応

| 共通要件 | 本ライブラリの対応 |
|---|---|
| 規制業種の改竄検知要件 | SHA-256 サイドカー + マニフェスト |
| サプライチェーン要件の増加 | 依存ゼロ + Apache 2.0 + Vendor-Agnostic |
| stdlib `logging` ベースの既存資産保護 | drop-in 拡張（`setLoggerClass`） |
| OpenTelemetry エコシステム共存 | `contextualize(trace_id=...)` + `LoggingHandler` 共存 |
| free-threaded 移行検討 | 明示ロック化 + ピュア Python |

これらの共通対応軸は地域差を持たず、本ライブラリの特性が地域横断的に届きうる軸として観測される。

---

### 7.10 OSS 配布上の技術的構造

本ライブラリの OSS 公開上の構造特性を整理する（マーケティング的位置づけではなく、配布物の技術的構造）。

#### 7.10.1 配布形態

`pyproject.toml` および `MANIFEST.in` から確認できる事実:

- **distribution name**: `d-safelogger`（PyPI 正規化）
- **import name**: `dsafelogger`（ハイフンなし）
- **配布対象**: wheel は `src/dsafelogger/` 配下の runtime package files。sdist は公開検証・再現性のため docs / examples / tests / benchmark summaries / selected benchmark summaries を含む。
- **同梱物**: `py.typed` 型情報、CLI エントリポイント `dsafelogger`
- **ランタイム依存**: なし
- **Python 要件**: `>=3.11`

#### 7.10.2 ドキュメント体系（再掲、§3.10）

- README: 英語版（`README.md`）+ 日本語版（`README_ja.md`）
- examples: 17 ファイル（英語）
- 設計書: `docs/design/` 3 ファイル（基本設計・詳細設計・テスト設計）
- API リファレンス: `docs/api/`（自動生成）
- 運用ガイド: `TESTING.md` / `BENCHMARK.md` / `CONTRIBUTING.md` / `CHANGELOG.md`

#### 7.10.3 品質ゲート

`TESTING.md` および公開検証手順:
- v23j ローカル検証（Python 3.14.3 / Windows）: **658 passed, 3 skipped**（収集 661、`uv run pytest tests -v`）
- skipped 数は OS 依存。fork E2E は POSIX-only、Windows spawn E2E は Windows-only であるため、CI matrix では OS により skipped 数が変動し得る。
- カバレッジ: terminal total **87%**, XML line-rate **88.97%**, branch-rate **81.46%**
- multiprocess tests / OTel・structlog coexistence tests は公式品質ゲートに含まれる
- 型検証: `mypy src` / `pyright src` / `pyright tests/typing_smoke` / built wheel に対する `pyright --verifytypes dsafelogger --ignoreexternal` 100% completeness gate を公開前検証に含める。smoke test ディレクトリは標準ライブラリ `typing` shadow を避けるため `tests/typing_smoke/` とする。
- free-threaded build テスト: `PYTHON_GIL=0 uvx --python cpython-3.13+freethreaded --from pytest pytest tests -v`

#### 7.10.4 リリース管理

公開検証手順:
- 公開設計書は `scripts/check_design_docs_sync.py` で内部同期検証
- API ドキュメントは `scripts/generate_api_docs.py --check` で検証
- ベンチマーク選定セッションは `benchmarks/summary/manifest.json` で固定（最後に実行した benchmark が自動的に公開代表結果へ昇格する事故を回避）
- `BENCHMARK.md` は手動編集の解釈であり、benchmark runner からは再生成されない

#### 7.10.5 公開時のステータス

公開前レビュー記録（2026-05-07 時点）:
- 現在の公開対象バージョン: `0.2.1`
- 最新公開前レビュー結果: **GO-with-fixes**
- 公開前必須修正項目（release blocker）が列挙されている

これらは「整備されたリリース運用フロー」が存在することを示すが、本章ではそれを「人気が出る根拠」とはせず、配布物の技術的構造としてのみ記録する。

---

### 7.11 位置づけの整理

#### 7.11.1 「届きうる層」の整理

本章で論じた 6 セグメントへの適合関係を集約すると、本ライブラリは次の 4 つの軸に**他ライブラリとは異なる設計軸を持つ選択肢**として位置づけられる:

1. **「stdlib 拡張型 × ピュア Python × 依存ゼロ × append-only」**: 本一次ソース調査範囲で他に観測されない組み合わせ。
2. **「parent-side Writer × 配送状態の階層的分類」**: stdlib 公式が推奨する別プロセス listener パターンを、配送状態 counters と合わせて本体提供する組み合わせ。
3. **「SHA-256 サイドカー × マニフェスト × `sha256sum -c` 互換」**: ライブラリ機能としての完全性検証は本調査範囲で他に観測されない。
4. **「PEP 703 明示対応 × 共有状態の明示ロック化」**: 公式 docs での対応宣言は本調査範囲で他に観測されない。

これら 4 軸はすべて「特定の運用要件を持つ subset 組織」への対応であり、Loguru / structlog のような「広範な開発者にとっての DX 改善」軸とは設計目的が異なる。

#### 7.11.2 「届きにくい層」の整理

次の運用要件・志向を持つ層には、本ライブラリは設計目的上届きにくい:

| 層 | 理由 |
|---|---|
| 「ロガー API を完全に再設計してほしい」DX 重視層 | 本ライブラリは drop-in 拡張型であり、API は stdlib 維持。Loguru / Logbook のほうが目的に合致 |
| 「速度のみを最優先」する層 | C 拡張による高速化を提供しない。picologging のほうが目的に合致 |
| 「remote aggregation / 分散ロギング backend」を求める層 | 設計書 §11.2 で明示的にスコープ外 |
| 「Pydantic / OpenTelemetry SaaS 統合観測性」を求める層 | logfire のほうが目的に合致 |
| 「event 因果連鎖を中心としたロギングモデル」を求める層 | Eliot のほうが目的に合致 |

これらの層との関係は競合ではなく、**設計軸が交差しない**という観測である。

#### 7.11.3 「共存しうる層」の整理

本ライブラリは次のライブラリと**共存可能**な構造を持つ:

| 共存先 | 共存パターン |
|---|---|
| structlog | Pattern A: dual stream（structlog で JSON、本ライブラリで human text）/ Pattern B: unified output（structlog で event 組み立て → 本ライブラリで routing） |
| OpenTelemetry Python | `LoggingHandler` を `setLoggerClass()` 後の logger に attach + `contextualize(trace_id=..., span_id=...)` |
| logrotate（外部 rotator） | `routing_mode='none'` + `ReopenLogFiles()` |
| pytest caplog | stdlib `logging` 互換のため標準的 fixture が動作 |
| SQLAlchemy / Django / Flask / 第三者ライブラリ | `setLoggerClass()` により自動共参加 |

「置換ではなく共存」を志向する設計姿勢（§1.4.4 / §3.9）は、既存エコシステムへの干渉を最小化する方向で機能する。

#### 7.11.4 ポジショニング論理の集約

以上を集約すると、本ライブラリの OSS 公開上の論理的位置づけは次のように整理できる:

- **広範な人気を狙う設計ではない**: 設計書 §1 自身が「広く普及させる目的よりも、D エコシステムの共通基盤として運用することを最優先とする」と明記している。
- **特定の運用要件への適合度が高い**: Windows サーバ運用 / 監査・コンプライアンス / multiprocess 監査 / サプライチェーンセキュリティ重視 / free-threaded 移行検討 / stdlib コンサバの 6 セグメントが論理的対応軸を持つ。
- **既存エコシステムとの共存を志向**: stdlib 拡張型として動作し、structlog / OpenTelemetry / 第三者ライブラリと並走可能。
- **責務範囲を狭く定義**: log shipper / metrics pipeline / distributed tracing backend / access control system はスコープ外（README 明示）。
- **失敗の境界をドキュメントで明示**: HMAC スコープ外、`UnexplainedLost` の意味、Writer 保証範囲、What Not To Claim が能動的に列挙されている。

---

### 7.12 OSS 公開時の位置づけの整理

本章で参照した観測事実から、次のように整理できる。本ライブラリのアーキテクチャ特性が現代の Python エコシステム上どの軸に技術的価値を提供しうるかという論理的整理である。

1. **6 セグメントへの論理的対応軸を持つ**: サプライチェーンセキュリティ重視層 / Windows サーバ運用層 / 監査・コンプライアンス層 / Free-threaded 移行検討層 / stdlib コンサバ層 / multiprocess 監査層。各軸は本ライブラリの個別アーキテクチャ特性に直接対応する。
2. **4 軸で他ライブラリとは異なる設計軸を持つ選択肢として観測される**: 「stdlib 拡張型 × ピュア Python × 依存ゼロ × append-only」「parent-side Writer × 配送状態階層分類」「SHA-256 サイドカー × マニフェスト × `sha256sum -c` 互換」「PEP 703 明示対応 × 共有状態明示ロック化」。本一次ソース調査範囲で、これら 4 軸を同時に満たすプロジェクトは観測されない。
3. **5 つの層に対しては設計目的上届きにくい**: DX 完全再設計層 / 速度最優先層 / 分散ロギング backend 求める層 / SaaS 統合観測性層 / event 因果連鎖層。これらは競合ではなく設計軸が交差しないため、本ライブラリは候補として位置づけられにくい。
4. **5 つのライブラリ・運用構成と共存可能**: structlog（2 パターン）/ OpenTelemetry Python（`LoggingHandler` + `contextualize`）/ logrotate（`routing_mode='none'` + `ReopenLogFiles`）/ pytest caplog / SQLAlchemy・Django 等の第三者ライブラリ。
5. **国内・海外で共通する適合軸**: 規制業種の改竄検知要件 / サプライチェーン要件の増加 / stdlib `logging` ベース既存資産保護 / OpenTelemetry エコシステム共存 / free-threaded 移行検討。地域差を持たず、本ライブラリの特性が地域横断的に届きうる軸。
6. **国内特有の対応軸**: Windows 業務システム比率 / 規制業種オンプレ運用 / 日本語ドキュメント親和性。設計書本体が日本語で記述されている点は国内開発者の学習コストを下げる方向で機能する。
7. **海外特有の対応軸**: PEP 703 先行採用傾向 / Executive Order 14028 等のサプライチェーン規制要件化 / 大規模 microservice 構成。examples / README 英語、Apache 2.0、依存ゼロが対応軸。
8. **設計目的が「広範な普及」ではないことが明示されている**: 設計書 §1 は「広く普及させる目的よりも、D エコシステムの共通基盤として運用することを最優先とする」と宣言しており、これは「特定の運用要件を持つ subset 組織への対応」を優先する設計姿勢として観測される。
9. **失敗の境界を能動的に明示するドキュメント運用**: `examples/08_compliance_audit.md` の Threat Model / `examples/12_multiprocess_logging.md` の Writer does not guarantee / `BENCHMARK.md` の What Not To Claim / 設計書 §7.6.7 の HMAC スコープ外宣言 / 設計書 §11.2 の remote aggregation スコープ外宣言。これらは「過剰な期待による誤用を防ぐ」運用姿勢として一貫している。
10. **品質ゲートの透明性**: Python 3.14.3 / Windows で 658 passed / 3 skipped（収集 661）、カバレッジ 87% terminal、free-threaded build テスト手順、`scripts/check_design_docs_sync.py` および `scripts/generate_api_docs.py --check` による内部同期検証、`benchmarks/summary/manifest.json` による benchmark セッション固定。skipped 数は OS 依存で変動し得る。これらは導入候補ライブラリの評価時に観測可能な品質指標として記録される。
11. **配布構造の明確性**: wheel は runtime package files のみを含み、`py.typed` を同梱する。sdist は公開検証・再現性のため docs / examples / tests / benchmark summaries / selected benchmark summaries を含む。private planning materials と一時作業ファイルは含めない。
12. **competitor との関係は競合ではなく責務分離**: structlog（フロントエンド）/ OTel（emission）/ Loguru（DX 置換）/ picologging（速度差別化）/ logfire（SaaS）/ Eliot（causal）は責務軸が異なり、本ライブラリと共存または並走する。Loguru の 23.9k stars 等の知名度指標は、設計軸の比較とは独立した文脈である。

---

### 7.13 本章のまとめ

D-SafeLogger v23j の OSS 公開時の位置づけについて、論理的に整理できる位置づけは次の 5 点に集約される:

1. **直接競合は本一次ソース調査範囲で観測されないが、これは「広範な人気が出る」予測ではない**。設計目的が「特定の運用要件を持つ subset 組織への対応」に置かれているため、Loguru / structlog のような DX 改善軸とは設計軸が異なる。
2. **6 セグメント（サプライチェーン / Windows / 監査 / Free-threaded / stdlib コンサバ / multiprocess 監査）が論理的対応軸**。これらは独立ではなく重なる構造を持つ。
3. **国内・海外の共通対応軸は 5 つ**: 規制業種改竄検知 / サプライチェーン要件 / stdlib 既存資産保護 / OpenTelemetry 共存 / free-threaded 移行検討。地域差を持たない軸として観測される。
4. **5 つの層には設計目的上届きにくい**: DX 完全再設計 / 速度最優先 / 分散 backend / SaaS 観測性 / event 因果連鎖。これらは競合ではなく交差しない設計軸である。
5. **5 つのライブラリ・運用構成と共存可能**: structlog / OpenTelemetry / logrotate / pytest caplog / 第三者 stdlib `logging` ライブラリ。「置換ではなく共存」を志向する設計姿勢の帰結。

これらは次章「8. 総合評価」で、本レポート全体の客観事実を踏まえた最終的な技術的位置づけとして集約される。

---

> **本章の主な参照資料**: 第 1〜6 章で参照した内容のみ。新規の一次ソースは追加していない。`docs/design/D_SafeLogger_Specification_v23j_full.md` §1, §2, §11.2, §12.1 / `README.md` Compatibility/Non-goals 節 / `BENCHMARK.md` What Not To Claim 節 / `examples/08_compliance_audit.md` Threat Model セクション / `examples/12_multiprocess_logging.md` Section 3 / 第 6 章で確認した一次ソース全件。

## 第 8 章 総合評価

### 8.1 本章のスコープ

本章は、第 1〜7 章で個別に整理した観測事実を**集約**して、現行 v23j アーキテクチャの**到達点**として記述可能な位置づけを示す。

#### 8.1.1 本書のスコープ再確認

本ホワイトペーパー全体のスコープを再掲する:

1. **改善提案・課題管理・将来ロードマップは扱わない**: 本書は v23j 時点の現行アーキテクチャの説明と評価を目的とし、issue tracker / roadmap の代替ではない。
2. **競合情報の取扱**: 公開一次ソースで確認できる事実を優先し、確認できない事項は断定しない。
3. **OSS 公開時の位置づけ整理**: 採用率・人気・反響の予測は行わず、公開資料から確認できる設計上の位置づけに限定する。

本章はこのスコープを継承し、**到達点の整理**のみを行う。

#### 8.1.2 集約の構造

```text
[観測事実]（第 1–7 章）
   ↓
[アーキテクチャ的価値の集約]（§8.3）
[設計姿勢の一貫性]（§8.4）
[エコシステム上の位置]（§8.5）
[ベンチ観測事実の集約]（§8.6）
[ドキュメント・運用構造の集約]（§8.7）
   ↓
[客観的位置づけ]（§8.8）
[本レポートの限界]（§8.10）
```

---

### 8.2 観測事実の集約

各章で整理した観測事実を 1 行ずつに集約する。

#### 8.2.1 第 1 章「設計思想とコンセプト」からの集約

- **位置づけ**: stdlib `logging` を**置き換えず拡張する**、ランタイム外部依存ゼロの本番運用を意識したロギング基盤
- **対象 Python**: 3.11 以上、CPython 3.13/3.14 free-threaded build を設計対象に含む
- **設計目的**: D エコシステム共通基盤として運用することを最優先（広範な普及は副次）
- **Safe の 6 軸**: startup / file / record・context / operational / concurrency・multiprocess / failure observability
- **5 設計原則**: Reroute, don't rotate / Fail before it breaks / Start quick, ship as-is / Zero external runtime dependencies / Be honest about multiprocess behavior
- **アーキテクチャ優位点 19 項目**は「依存しない／壊さない／黙って劣化しない／説明可能にする／拡張するが置き換えない／ローカルで完結する」の 6 群に整理可能

#### 8.2.2 第 2 章「仕様と設計」からの集約

- **物理モジュール構成**: 25 ファイル + `mp/` namespace、公開 API の入口は `__init__.py` と `mp/__init__.py` の 2 ファイルのみ
- **3 層内部アーキテクチャ**: Capture（logging 互換）/ Transport（hand-off）/ Sink（routing/hash/manifest）。single/multiprocess で責務境界不変
- **v23 系不変条件 9 項目**: Writer ownership / Writer drain / append-only routing / Capture-Transport-Sink / logging 互換 / Zero dependency / fail-safe ほか
- **3 層設定パイプライン**: 環境変数 > INI/dict > 引数の厳格マージ + Fail-Fast + 聖域（diagnose/sens_kws/fmt インスタンス）
- **配送状態の 5+6+1 用語階層**: Lifecycle 5 / Terminal 6 / Policy qualifier 1。`unexpected_loss` のみがバグ扱い
- **絶対防衛線 4 つ**: `MAX_IPC_LOG_TIMEOUT_SECONDS=3.0`, `CONTROL_PLANE_ACK_TIMEOUT_SEC=5.0`, `WRITER_STOP_WAIT_TIMEOUT_SEC=10.0`, `ipc_log_queue_maxsize` warning 閾値 100000

#### 8.2.3 第 3 章「ユーザビリティ」からの集約

- **最小起動コードは 3 行**: `ConfigureLogger(...)` + `GetLogger(...)` + `logger.info(...)`
- **26 引数すべてに既定値**: 最小起動と本番監査運用が同一 API のパラメータ空間で表現
- **stdlib 移行**: setup コード行数 50–60% 削減、呼び出しサイト不変、SQLAlchemy/Django 等の第三者ライブラリは改修なしで参加
- **3 層パイプライン × 変更主体**: 引数（開発者）/ INI（DevOps）/ 環境変数（オペレータ）
- **examples 17 ファイル**: 6 学習パス（getting started / stdlib and ecosystem integration / Windows and service operations / application / audit and incident response / multiprocess）に分類
- **CLI 3 コマンド**: `init` / `ls` / `tail -f`（透過的ファイル切り替え追随で Append-Only 弱点を補完）
- **multiprocess 利用は 3 worker_model**: process / pool / executor（ProcessPoolExecutor のみ）
- **third-party との共存**: structlog 2 パターン / OpenTelemetry trace correlation / stdlib サードパーティ自動共参加

#### 8.2.4 第 4 章「セキュリティ」からの集約

- **サプライチェーン経路を構造的に排除**: ランタイム外部依存ゼロ + Vendor-Agnostic コア（OTel 等のベンダー import なし）+ Apache 2.0
- **起動時に検証される項目 16 以上**: パーミッション / ディスク容量 / 型変換 / カスタムレベル衝突 / 環境変数解釈（v23h で fail-fast 化）
- **`diagnose` 3 重ガード**: コード経路（引数なし）/ 設定ファイル経路（INI 無視）/ 真偽値表記（"1" のみ）
- **`sens_kws` 聖域 + 12 ビルトイン語**: 環境変数からの設定不可、`f_locals` 経路のみ動作（`logger.info()` メッセージ本文は対象外と明示）
- **完全性検証**: SHA-256 サイドカー（`sha256sum -c` 互換、相対パス）+ マニフェスト + `os.replace()` 原子的書き込み
- **脅威モデル境界の能動的明示**: HMAC スコープ外、`UnexplainedLost` の意味、Writer does not guarantee リスト
- **bounded shutdown 契約（v23h）**: bounded wait → visible warning → process exits（daemon=True で physical 保証）

#### 8.2.5 第 5 章「機能別詳細分析」からの集約

- **Append-Only ルーティング 9 モード**: `none` / `daily` / `hourly` / `min_interval` / `startup_interval` / `size` / `count` / `cyclic_weekday` / `cyclic_month`
- **`size` / `count` の `max_count` 分岐**: 指定あり = サイクリック上書き / 指定なし = 上限到達 `OverflowError` でアプリ停止
- **世代管理 + 自己修復性**: `backup_count > 0` で別スレッド purge/archive、失敗時は次回切り替えタイミングでリトライ
- **完全性検証の lock ordering**: `family_lock → manifest_lock`（逆順禁止）。HashWorker は `_run_in_empty_context` で実行
- **5 状態ライフサイクル + RLock**: unconfigured / auto / explicit / configuring / shutting_down
- **multiprocess Writer**: ファイル所有・routing・hash・manifest・purge・archive・reopen を一元集約
- **分類済み配送状態 counters + writer_reject 6 内訳**（v23h）: route / reconstruct / close_marker / sink / policy / format
- **TrackedQueue（v23h）**: OS 名非依存の例外プローブで native qsize fallback
- **free-threaded 対応**: GIL 非依存の明示ロック + `f_locals` repr 済み snapshot + 内部 thread の空 Context 開始

#### 8.2.6 第 6 章「競合プロジェクト比較」からの集約

- **直接競合は本一次ソース調査範囲で観測されない**: stdlib / Loguru / structlog / picologging / Eliot / Logbook / logfire / OpenTelemetry のいずれとも設計軸が完全には交差しない
- **依存ゼロは 2 件のみ**: D-SafeLogger と picologging。**ピュア Python に限定すれば D-SafeLogger 単独**
- **append-only ルーティング**: Python エコシステムに先行例なし（Logback / Log4j2 では options として存在）
- **完全性検証（SHA-256 サイドカー + マニフェスト）**: 本一次ソース調査範囲で他プロジェクトに観測されない
- **分類済み配送状態 counters**: 本一次ソース調査範囲で他プロジェクトに観測されない
- **PEP 703 free-threaded 対応の明示宣言**: 本一次ソース調査範囲で D-SafeLogger 単独
- **3 層設定パイプラインの体系的マージ規則**: 本一次ソース調査範囲で D-SafeLogger 単独
- **stdlib 公式が明文化している既知制約への直接応答**: Windows rename 不能（`logging.handlers` WatchedFileHandler 節）/ multiprocess 単一ファイル未サポート（cookbook）

#### 8.2.7 第 7 章「OSS 公開時の位置づけ」からの集約

- **6 セグメントへの論理的対応軸**: サプライチェーン重視 / Windows サーバ運用 / 監査・コンプライアンス / Free-threaded 移行検討 / stdlib コンサバ / multiprocess 監査
- **4 軸で他ライブラリとは異なる設計軸を持つ選択肢**: 「stdlib 拡張 × ピュア Python × 依存ゼロ × append-only」/ 「parent-side Writer × 分類済み配送状態 counters」/ 「SHA-256 サイドカー × マニフェスト × `sha256sum -c` 互換」/ 「PEP 703 明示対応 × 共有状態明示ロック化」
- **5 つの層には設計目的上届きにくい**: DX 完全再設計 / 速度最優先 / 分散ロギング backend / SaaS 観測性 / event 因果連鎖
- **5 つの構成と共存可能**: structlog / OpenTelemetry / logrotate / pytest caplog / 第三者 stdlib `logging` ライブラリ
- **国内・海外の共通対応軸 5 つ**: 規制業種改竄検知 / サプライチェーン要件 / stdlib 既存資産保護 / OpenTelemetry 共存 / free-threaded 移行検討

---

### 8.3 アーキテクチャ的価値の整理

第 1〜7 章で観測した特性を、**アーキテクチャ的価値の単位**として 7 つに整理する。これは個別機能の列挙ではなく、機能群が組み合わさることで成立する価値の単位である。

#### 8.3.1 価値 1: stdlib `logging` の拡張点として安定する

`logging.setLoggerClass()` を介した drop-in 拡張、`addLevelName()` の不使用、`record.levelname` の不変化、`QueueHandler.prepare()` の完全オーバーライド、`logging.LogRecord` の非破壊取り扱い。これらが組み合わさることで、**既存 stdlib `logging` ベースの資産が本ライブラリの存在で前提を崩されない**。

#### 8.3.2 価値 2: ファイル境界より下を強化する

Append-Only ルーティング、9 モードの routing strategy、世代管理 + 自己修復性、完全性検証、external rotation 共存。これらは「stdlib `logging` の handler 入口より下のレイヤ」を担い、**呼び出しサイトを変えずに本番運用機能を追加**する。

#### 8.3.3 価値 3: 失敗を分類し、説明可能にする

分類済み配送状態 counters、`writer_reject` 6 内訳、rate-limited stderr warning、Writer exit code、shutdown summary、bounded shutdown 契約。これらは**ログ欠損を「無音の隙間」ではなく「説明可能な事実」**に変換する。`unexpected_loss` のみがバグ扱いとして区別される設計は、運用上の alarm 粒度を明確化する。

#### 8.3.4 価値 4: 事故パターンを構造的に成立させない

`diagnose` 3 重ガード、`sens_kws` 聖域、`pg_name` サニタイズ、ファイル名厳密フィルタリング、INI 型変換 Fail-Fast、5 状態ライフサイクル、`mp.ConfigureLogger()` 同一 process 2 回目の `RuntimeError`、registry hash SHA-256 照合、bootstrap payload の picklable spec 限定。これらは**「うっかり混入」「設定ミス」「ID 流用」等の事故パターンを設計レベルで成立させない**。

#### 8.3.5 価値 5: 絶対防衛線で host process を守る

`MAX_IPC_LOG_TIMEOUT_SECONDS = 3.0` / `CONTROL_PLANE_ACK_TIMEOUT_SEC = 5.0` / `WRITER_STOP_WAIT_TIMEOUT_SEC = 10.0` / `ipc_log_queue_maxsize` warning 閾値 100000。これらの内部定数は**ユーザーが上書き不能**であり、ロギング機構が host process を不可逆に固める長さの上限を構造的に保証する。daemon=True と組み合わせて「process exits」がfail-safe として実現される。

#### 8.3.6 価値 6: 責務範囲を狭く、外部ツールに切り分ける

HMAC は外部ツールに委譲、サイドカー検証は `sha256sum -c` を使う、external rotation は `logrotate` との共存、log shipping は Fluent Bit / Vector / Filebeat に委譲、distributed tracing backend はスコープ外。**ライブラリが抱え込むべき責務と、OS / 外部ツールに委譲すべき責務の境界が能動的に引かれている**。

#### 8.3.7 価値 7: 拡張するが置き換えない

structlog 共存（2 パターン）、OpenTelemetry trace correlation（`contextualize` + `LoggingHandler`）、stdlib サードパーティ自動共参加、内部 thread の空 Context 開始、`addLevelName()` 不使用。これらは**他のフレームワーク・他のコードに対して中立**であろうとする設計姿勢の組み合わせとして観測される。

---

### 8.4 設計姿勢の一貫性

第 1〜7 章で個別に観測した「設計姿勢」を集約すると、以下 8 軸が**ライブラリ全体を貫いて一貫**して観測される。

| 軸 | 内容 | 観測される箇所 |
|---|---|---|
| **構造的に排除** | 「事故パターンを構造的に成立させない」 | `diagnose` 引数なし / sens_kws 環境変数なし / pg_name サニタイズ / 5 状態ライフサイクル / mp 2 回目 `RuntimeError` |
| **責務分離** | 「責務境界をプロセス境界より硬く保つ」 | Capture/Transport/Sink 3 層分離 / single-mp で責務不変 / Writer 側で Capture 意味論を再実行しない |
| **失敗分類** | 「異常を分類し silent failure を許さない」 | 分類済み配送状態 counters / writer_reject 6 内訳 / rate-limited warning / shutdown summary |
| **絶対防衛線** | 「ユーザーが上書き不能な内部定数で host process を守る」 | 4 つの timeout / queue size 定数 / daemon=True backstop |
| **opt-in 境界の明示** | 「同一 API で意味論を黙って混在させない」 | `writer_flush_batch>=2` で per-message visibility 失効を仕様明記 |
| **境界の能動的明示** | 「保証範囲・非保証範囲をドキュメントで先行宣言」 | HMAC スコープ外 / `UnexplainedLost` の意味 / Writer does not guarantee / What Not To Claim |
| **standardness 維持** | 「stdlib のセマンティクスを壊さない」 | addLevelName() 不使用 / record.levelname 不変化 / QueueHandler.prepare() 完全オーバーライド |
| **責務委譲** | 「ライブラリで抱え込まず OS・外部ツールに切り分ける」 | HMAC 外部委譲 / `sha256sum -c` 互換 / logrotate 共存 / log shipping は外部 |

これら 8 軸は v23j 単版の偶然ではなく、設計書 §1 の絶対条件（「標準ライブラリへの完全な準拠」「外部依存ゼロ」）と §12.1 の Writer 不変条件（「silent loss/hang/fallback を避ける」）から導かれる**設計判断の系**として観測される。

---

### 8.5 エコシステム上の位置

第 6 章および第 7 章の整理から、本ライブラリのエコシステム上の位置を 4 つの命題で集約する。

#### 8.5.1 命題 1: 直接競合は観測されない

主要 8 プロジェクト（stdlib / Loguru / structlog / picologging / Eliot / Logbook / logfire / OpenTelemetry SDK）の各設計軸を一次ソースで確認した結果、本ライブラリと**機能・責務軸が完全に重なるプロジェクトは観測されない**。各プロジェクトは異なる軸（DX / 構造化フロントエンド / 速度差別化 / causal chain / SaaS 統合 / 標準観測性）を champion している。

#### 8.5.2 命題 2: 本ライブラリは「stdlib 拡張型 × 機能差別化」のニッチを占める

picologging は同じ「stdlib 拡張型」だが速度差別化、本ライブラリは設計差別化（append-only / 完全性検証 / multiprocess Writer / 配送状態分類）。Loguru / Logbook は置換型、structlog は並走型、logfire / OTel はブリッジ型のため、本ライブラリの位置は本一次ソース調査範囲で固有である。

#### 8.5.3 命題 3: stdlib 公式の既知制約への直接応答である

`docs.python.org/3/library/logging.handlers.html` の WatchedFileHandler 節（Windows rename 不能）と、`docs.python.org/3/howto/logging-cookbook.html`（multiprocess 単一ファイル未サポート、QueueListener 別プロセス推奨）は、Python 公式 docs 自身が明文化している制約と推奨。本ライブラリの append-only ルーティングと parent-side Writer はこれらへの**直接応答**として位置づけられる。

#### 8.5.4 命題 4: 競合ではなく共存を志向する

structlog（2 パターンで共存）/ OpenTelemetry Python（`LoggingHandler` 経由）/ logrotate（`routing_mode='none'` + `ReopenLogFiles()`）/ pytest caplog（stdlib 互換）/ 第三者 `logging.getLogger()` ライブラリ（`setLoggerClass` で自動共参加）。これらは**いずれも併用可能**な構造を持ち、設計姿勢として「置き換えではなく共存」が一貫している。

---

### 8.6 ベンチマーク観測事実の集約

`BENCHMARK.md` および `benchmarks/summary/` の選定セッションから、本ライブラリの性能特性を客観的に整理する。**評価ではなく観測値の集約**である。

#### 8.6.1 単一プロセス async（Python 3.14 / GIL enabled、選定セッション）

- text: **51,554 msg/s**, p50 **16.7 µs**, p99 **39.6 µs**
- JSON: **52,081 msg/s**, p50 **16.7 µs**, p99 **36.8 µs**

#### 8.6.2 単一プロセス cell-winners（16 セル）

- D-SafeLogger async が throughput 1 位 8/16
- D-SafeLogger async が p50 1 位 12/16
- D-SafeLogger async は D-SafeLogger sync を全 16 cell で throughput / p50 ともに上回る

#### 8.6.3 マルチプロセス integrity profile

- 3 backend（D-SafeLogger / stdlib logging / loguru）× 96 raw runs で missing=0 / duplicates=0 / JSON parse failure=0 / route mismatch=0
- 正常条件下で 3 backend すべてが期待 record を欠損なく配送

#### 8.6.4 マルチプロセス performance profile

- D-SafeLogger sync は stdlib logging sync の **63–75%** スループット（`root_p8` で 75%）
- すべての throughput cell で stdlib logging が 1 位
- D-SafeLogger は raw multiprocess throughput では先行しない（仕様上の差として明記）

#### 8.6.5 マルチプロセス resilience profile

- D-SafeLogger は 12/12 summary 行で classified loss/reject/drop fields を生成
- D-SafeLogger は 12/12 summary 行を分類・説明
- stdlib logging / loguru rows は `observability_gap` でマーク（契約上分類できない）

#### 8.6.6 What To Claim / What Not To Claim（`BENCHMARK.md`）

公開ベンチ分析が能動的に列挙する境界:

**What To Claim**:
- D-SafeLogger has zero runtime dependencies
- D-SafeLogger provides append-only file handling without rename/truncate rotation
- D-SafeLogger supports structured JSON logging and stdlib-compatible logger integration
- D-SafeLogger async is competitive in single-process logging and leads several low-latency cells
- D-SafeLogger multiprocess mode centralizes sink ownership in a Writer runtime
- D-SafeLogger multiprocess resilience profiling exposes classified delivery-state counters

**What Not To Claim**:
- Do not claim D-SafeLogger is always the fastest backend
- Do not claim D-SafeLogger multiprocess mode beats stdlib logging on raw throughput
- Do not claim multiprocess logging can never lose records under operational failure
- Do not claim sink outage, worker crash, or hard process termination is made impossible
- Do not mix diagnostic benchmark results with normal logging throughput results

**観察**: ベンチ性能を主張する範囲・しない範囲がドキュメント側で**能動的に列挙**されており、過剰主張を避ける運用姿勢が一貫している。

---

### 8.7 ドキュメント・運用構造の集約

#### 8.7.1 ドキュメント体系

| 軸 | 文書 | 行数（参考） |
|---|---|---|
| 入口 | `README.md` / `README_ja.md` | 各 217 行 |
| 学習 | `examples/01_*.md`〜`examples/17_*.md` | 17 ファイル |
| 設計 | `docs/design/D_SafeLogger_Specification_v23j_full.md` | 2,477 行 |
| 設計 | `docs/design/D-SafeLogger_DetailedDesign_v23j.md` | 4,258 行 |
| 設計 | `docs/design/D-SafeLogger_TestDesign_v23j.md` | 135 行 |
| API | `docs/api/dsafelogger*.md` | 自動生成 |
| 運用 | `TESTING.md` / `BENCHMARK.md` / `CONTRIBUTING.md` / `CHANGELOG.md` | — |

#### 8.7.2 品質ゲート

- 公式テスト baseline: 658 passed / 3 skipped（収集 661、`uv run pytest tests -v`、Python 3.14.3 / Windows）。fork E2E は POSIX-only、Windows spawn E2E は Windows-only のため、OS によって skipped 数は変動し得る。
- カバレッジ: terminal total 87%, XML line-rate 88.97%, branch-rate 81.46%
- multiprocess tests / OTel・structlog coexistence tests は公式品質ゲートに含まれる
- 型検証: `mypy src` / `pyright src` / `pyright tests/typing_smoke` / built wheel に対する `pyright --verifytypes dsafelogger --ignoreexternal` 100% completeness gate を公開前検証に含める
- free-threaded build テスト手順あり（`PYTHON_GIL=0 uvx ...`）
- `scripts/check_design_docs_sync.py` および `scripts/generate_api_docs.py --check` で内部同期検証
- `benchmarks/summary/manifest.json` で公開代表セッションを固定

#### 8.7.3 リリース運用

- distribution name: `d-safelogger`（PyPI 正規化）
- import name: `dsafelogger`
- ライセンス: Apache License 2.0
- `py.typed` 同梱
- `pyproject.toml` ランタイム依存ゼロ
- wheel は `src/dsafelogger/` 配下の runtime package files のみを含む
- sdist は docs / examples / tests / benchmark summaries / selected benchmark summaries を含み、private planning materials と一時作業ファイルは含めない
- 公開対象バージョン: 0.2.1
- 最新公開前レビュー結果: GO-with-fixes（2026-05-07）

#### 8.7.4 ドキュメント運用の特徴

- 多言語: README は日英 2 言語、設計書本体は日本語、examples / API / 運用ガイドは英語
- BENCHMARK.md は手動編集（runner からの自動再生成を禁止することで「最後の benchmark が自動昇格する事故」を回避）
- 公開検証は `TESTING.md`、benchmark 解釈は `BENCHMARK.md`、寄稿手順は `CONTRIBUTING.md` に分離されている

---

### 8.8 客観的位置づけ

本レポート全体の観測事実から、客観的に記述可能な位置づけを 10 項目に集約する。

#### 8.8.1 アーキテクチャ的位置づけ

1. **「stdlib 拡張型 × ピュア Python × ランタイム依存ゼロ × append-only routing × 完全性検証 × parent-side multiprocess Writer × 分類済み配送状態 counters × free-threaded 明示対応 × 3 層設定パイプライン」の組み合わせを満たすライブラリは、本一次ソース調査範囲で観測されない**。
2. **設計目的が「広範な普及」ではなく「特定の運用要件への適合」に置かれている**: 設計書 §1 が「広く普及させる目的よりも、D エコシステムの共通基盤として運用することを最優先とする」と明示し、§11.2 の multiprocess スコープ規定で remote aggregation / network protocol を明示的に除外する。これは subset 組織への対応を優先する設計姿勢として一貫する。
3. **直接の機能競合は観測されないが、これは「最強である」ことを意味しない**: 各主要競合（Loguru / structlog / picologging / Eliot / logfire / OpenTelemetry）は異なる軸を champion しており、責務軸が交差しないため共存可能。本ライブラリは「特定軸の champion」として位置づけられる。

#### 8.8.2 設計姿勢の一貫性

4. **8 軸の設計姿勢がライブラリ全体を貫いて一貫している**: 構造的に排除 / 責務分離 / 失敗分類 / 絶対防衛線 / opt-in 境界の明示 / 境界の能動的明示 / standardness 維持 / 責務委譲。これらは v23j 単版の偶然ではなく、設計書 §1 の絶対条件と §12.1 の Writer 不変条件から導かれる設計判断の系として観測される。
5. **保証範囲と非保証範囲がドキュメント上で能動的に明示されている**: HMAC スコープ外、`UnexplainedLost` の意味、Writer does not guarantee、What Not To Claim の各セクションは「過剰な期待による誤用を防ぐ」運用姿勢として観測される。

#### 8.8.3 stdlib 公式制約への対応

6. **stdlib 公式が明文化している既知制約に直接応答する設計**: Windows でのアクティブログ rename 不能（`logging.handlers` WatchedFileHandler 節）と multiprocess 単一ファイル未サポート（cookbook）に対し、append-only ルーティングと parent-side Writer がそれぞれ直接的応答として機能する。

#### 8.8.4 ベンチマーク観測事実の整理

7. **単一プロセス async の選定セッション数値**: Python 3.14 / GIL enabled で text 51,554 msg/s, p50 16.7 µs / JSON 52,081 msg/s, p50 16.7 µs。16 cell 中 throughput 1 位 8/16、p50 1 位 12/16。
8. **マルチプロセス raw throughput では stdlib logging が先行**: `root_p8` で D-SafeLogger は stdlib の 63–75%。これは仕様上の固定費（IPC + Writer dispatch）を反映する設計上の差として `BENCHMARK.md` で明示。本ライブラリの multiprocess 価値は raw throughput ではなく、配送状態の観測性。
9. **マルチプロセス resilience profile で 12/12 行を分類・説明**: stdlib / loguru は `observability_gap` でマーク。配送状態の説明可能性が本ライブラリ固有の観測性として記録されている。

#### 8.8.5 ドキュメント・品質運用

10. **品質ゲートと内部同期検証スクリプトが整備されている**: Python 3.14.3 / Windows で 658 passed / 3 skipped（収集 661）、カバレッジ 87%、`mypy` / `pyright` / typing smoke / `pyright --verifytypes` 100% completeness gate、`scripts/check_design_docs_sync.py` と `scripts/generate_api_docs.py --check` による内部同期検証、`benchmarks/summary/manifest.json` による公開代表セッション固定。skipped 数は OS 依存で変動し得る。これらは導入候補ライブラリの評価時に観測可能な品質指標として記録される。

---

### 8.9 本章のまとめ

D-SafeLogger v23j は次の総合像として整理できる:

1. **アーキテクチャ的価値の単位は 7 つに集約される**: stdlib 拡張点として安定する / ファイル境界より下を強化する / 失敗を分類し説明可能にする / 事故パターンを構造的に成立させない / 絶対防衛線で host process を守る / 責務範囲を狭く外部ツールに切り分ける / 拡張するが置き換えない。
2. **8 軸の設計姿勢がライブラリ全体を貫いて一貫している**: 構造的に排除 / 責務分離 / 失敗分類 / 絶対防衛線 / opt-in 境界の明示 / 境界の能動的明示 / standardness 維持 / 責務委譲。
3. **エコシステム上の位置は 4 命題に集約される**: 直接競合は観測されない / stdlib 拡張型 × 機能差別化のニッチを占める / stdlib 公式の既知制約への直接応答 / 競合ではなく共存を志向。
4. **ベンチマーク観測事実は raw throughput ではなく観測性に主張軸が置かれる**: 単一プロセス async は競争力ある数値、multiprocess は raw throughput では stdlib に劣るが配送状態の説明可能性で固有の観測性を提供。
5. **ドキュメント・運用構造は内部同期検証と境界の能動的明示で整備されている**: 公開設計書 + 自動生成 API + 多言語 README + manifest 固定 benchmark + 品質ゲートのテストマトリックス + 型検証 gate。

これらは設計書 §1 の絶対条件「標準ライブラリへの完全な準拠を絶対条件としつつ、サードパーティ製ライブラリ（Loguru 等）を凌駕する診断能力と、Windows 環境での致命的なファイルロック問題を回避する堅牢性を外部依存ゼロで実現する」が、v23j 時点で**仕様・設計・実装・テスト・ドキュメント・ベンチマークの全層で一貫した形に到達している**ことを示す観測事実の集約である。

---

### 8.10 本レポートの限界

本レポートには次の限界がある。これらは本レポートの不備ではなく、評価方針上**意図的に範囲外**とした項目である。

#### 8.10.1 評価しない項目

- **ライブラリの普及予測・人気予測**: 本書は採用率・人気・反響の予測を行わない。
- **改善提案・課題の指摘**: 本書は v23j 時点の現行アーキテクチャの説明と評価を目的とし、issue tracker / roadmap の代替ではない。
- **採用率の予測**: 同上。
- **GitHub stars / PyPI download 数の優劣比較**: 知名度指標は事実として引用したが、設計軸の比較には用いていない。

#### 8.10.2 一次ソース確認の範囲

- 競合分析（第 6 章）は **2026-05-09 時点**の PyPI / GitHub / 公式 docs / PEP の確認に基づく。各プロジェクトの今後の更新により状況は変動しうる。
- 特に PEP 703 free-threaded 対応は段階的なロールアウト中であり、今後 6 ヶ月〜 2 年で他ライブラリの対応宣言が増える可能性がある（本章では予測しない）。

#### 8.10.3 本レポートが扱わない技術領域

- **本ライブラリのコード品質の細部**: 個別関数の実装品質や bug 有無は別途のコードレビュー領域であり、本レポートは公開設計書・公開ベンチ・examples・公開 API ドキュメントの観測事実に限定している。
- **特定 OS / 特定 Python バージョン固有の挙動詳細**: 公開資料に明記されている範囲のみを扱った。
- **将来バージョンの設計予測**: 現行 v23j アーキテクチャを所与とする方針のため、v24+ の方向性は扱わない。

#### 8.10.4 本レポートのスコープ確認

- 本書は **D-SafeLogger v23j アーキテクチャの整理・評価** を目的とし、(a) 改善提案・課題管理を含めず、(b) 競合情報は公開一次ソースで確認できる事実に限定し、(c) 採用率・人気・反響の予測を行わない方針で記述している。
- すべての章で private planning materials を不参照とし、`docs/design/` を一次設計書として使用した。

---

> **本章の主な参照資料**: 本書第 1〜7 章で参照した内容のみ。新規の一次ソースは追加していない。


---

## 付録 A. 参照ポリシー

本ホワイトペーパーは下記の参照ポリシーに従って作成されている。

### A.1 参照可（公式・公開対象）

| 区分 | パス |
|---|---|
| 公開 README | `README.md` / `README_ja.md` |
| 公開ベンチ分析 | `BENCHMARK.md` |
| 公開ベンチ生データ | `benchmarks/summary/*.md`, `benchmarks/summary/manifest.json`, `benchmarks/results/<selected>/summary.{md,json}` |
| 公開設計書 | `docs/design/D_SafeLogger_Specification_v23j_full.md`（2,477 行） |
| 公開設計書 | `docs/design/D-SafeLogger_DetailedDesign_v23j.md`（4,258 行） |
| 公開設計書 | `docs/design/D-SafeLogger_TestDesign_v23j.md`（135 行） |
| 公開 API ドキュメント | `docs/api/dsafelogger*.md` |
| 公開ガイド | `TESTING.md` / `CONTRIBUTING.md` / `CHANGELOG.md` |
| ライセンス | `LICENSE`（Apache License 2.0） |
| メタデータ | `pyproject.toml`, `MANIFEST.in`, `uv.lock` |
| 公開 examples | `examples/01_*.md` 〜 `examples/17_*.md`（17 ファイル） |
| 実装本体 | `src/dsafelogger/*.py`（25 ファイル + `mp/`） |
| 公開テスト | `tests/test_*.py` |

### A.2 参照不可（非公式 / 削除扱い）

- private planning materials
- `BENCHMARK_anomaly_*.md` / `BENCHMARK_legacy_*.md`（旧バージョンの退避ファイル）
- `*.zip` / `_*_extracted/`（スクラッチ・展開ディレクトリ）
- `App.log` / `dist/` / `src/D_SafeLogger.egg-info/`（実行時/ビルド成果物）

### A.3 一次ソース照合方針（第 6 章）

競合プロジェクトの最新仕様・状況については、`WebFetch` / `WebSearch` で次の一次ソースを取得し、URL を本文中に明記している（確認日 2026-05-09）:

- **PyPI** (`pypi.org/project/<name>/`): 最新バージョン・依存関係・メタデータ
- **GitHub**: README・最終リリース日・Issue 状況
- **公式 docs** (Read the Docs / 各プロジェクト公式)
- **PEP** (`peps.python.org/pep-XXXX/`): 仕様事項
- **CPython doc** (`docs.python.org/3/library/logging.html` 他)

一次ソースで裏取りできない主張は採用していない。

---

## 付録 B. 一次ソース一覧（2026-05-09 時点）

第 6 章で参照した一次ソース URL を一括で列挙する。

### B.1 D-SafeLogger 公開資料

- `docs/design/D_SafeLogger_Specification_v23j_full.md`
- `docs/design/D-SafeLogger_DetailedDesign_v23j.md`
- `docs/design/D-SafeLogger_TestDesign_v23j.md`
- `docs/api/dsafelogger*.md`
- `README.md` / `README_ja.md`
- `BENCHMARK.md`
- `TESTING.md` / `CONTRIBUTING.md` / `CHANGELOG.md`
- `examples/01_*.md` 〜 `examples/17_*.md`
- `LICENSE` / `pyproject.toml` / `MANIFEST.in`

### B.2 PyPI（パッケージメタデータ）

- `pypi.org/pypi/loguru/json` — Loguru 0.7.3 (2024-12-06)
- `pypi.org/pypi/structlog/json` — structlog 25.5.0 (2025-10-27)
- `pypi.org/pypi/picologging/json` — picologging 0.9.3
- `pypi.org/pypi/eliot/json` — Eliot 1.18.0 (2026-05-07)
- `pypi.org/pypi/Logbook/json` — Logbook 1.9.2
- `pypi.org/pypi/logfire/json` — logfire 4.32.1
- `pypi.org/pypi/opentelemetry-sdk/json` — OpenTelemetry SDK 1.41.1

### B.3 公式ドキュメント

- `docs.python.org/3/library/logging.html` — Python 3.14 logging モジュール
- `docs.python.org/3/library/logging.handlers.html` — handlers（WatchedFileHandler の Windows 制約等）
- `docs.python.org/3/howto/logging-cookbook.html` — multiprocess 推奨パターン
- `docs.python.org/3/whatsnew/3.13.html` — Python 3.13 What's New
- `loguru.readthedocs.io/en/stable/index.html` — Loguru 公式 docs
- `www.structlog.org` — structlog 公式 docs
- `eliot.readthedocs.io/en/stable/` — Eliot 公式 docs
- `logbook.readthedocs.io/en/stable/` — Logbook 公式 docs
- `microsoft.github.io/picologging/` — picologging 公式 docs
- `pydantic.dev/docs/logfire/` — logfire 公式 docs
- `opentelemetry.io/docs/specs/otel/logs/` — OpenTelemetry Logs Specification
- `opentelemetry.io/docs/languages/python/instrumentation/` — OpenTelemetry Python instrumentation

### B.4 GitHub リポジトリ

- `github.com/Delgan/loguru` — Loguru
- `github.com/hynek/structlog` — structlog
- `github.com/microsoft/picologging` — picologging
- `github.com/itamarst/eliot` — Eliot
- `github.com/getlogbook/logbook` — Logbook
- `github.com/pydantic/logfire` — logfire
- `github.com/open-telemetry/opentelemetry-python` — OpenTelemetry Python SDK

### B.5 PEP

- `peps.python.org/pep-0703/` — PEP 703: Making the Global Interpreter Lock Optional in CPython（Accepted 2023-10-24）

---

## 付録 C. 用語集

本ホワイトペーパーで頻出する D-SafeLogger 固有の用語を整理する。

### C.1 アーキテクチャ

| 用語 | 意味 |
|---|---|
| **Capture / Transport / Sink 3 層** | 内部アーキテクチャの責務分離。Capture = ログ生成（logging 互換）、Transport = 転送、Sink = 出力（routing/hash/manifest） |
| **Append-Only ルーティング** | rename / truncate を行わず、新ファイル名を open することで世代を切り替える方式 |
| **Drop-in Replacement** | `logging.setLoggerClass()` により標準 `logging.Logger` を本ライブラリの `DSafeLogger` で置き換える、API 互換の差し替え方式 |
| **Vendor-Agnostic 原則** | コアモジュール（`src/dsafelogger/`）にベンダー固有 import を含めない設計原則 |

### C.2 並行・マルチプロセス

| 用語 | 意味 |
|---|---|
| **`dsafelogger.mp`** | マルチプロセス公開 API namespace |
| **client process** | ログ呼び出しを行う process（main / worker 両方を含む） |
| **Writer runtime** | file sink を所有する内部 process。client から IPC で `LogEvent` を受信 |
| **`ctx`** | client が Writer に attach するための opaque かつ picklable な bootstrap object |
| **log plane** | 通常ログ `LogEvent` を運ぶ片方向経路（`multiprocessing.Queue` ベース） |
| **control plane** | reopen / attach / detach / stop / status を扱う request/ack 経路 |
| **active client registry** | Writer 側で管理する attach 中の client process 一覧 |
| **TrackedQueue** | log plane queue 実装。`super().qsize()` 例外プローブによる native fallback（v23h） |

### C.3 配送状態（§12.3）

| 用語 | 意味 |
|---|---|
| `attempted` | user code が logger に渡したログ呼び出し |
| `accepted` | level 判定および client filter を通過し、transport が配送責任を引き受けた |
| `enqueued` | accepted log が queue に投入された |
| `delivered_per_sink` | 対象 sink で flush 契約の完了点を通過 |
| `delivered` | required sink set すべてで `delivered_per_sink` 成立 |
| `rejected` | 配送責任を引き受ける前に拒否（timeout / closed / writer unavailable 等） |
| `dropped` | accepted 後または local queue 段階で破棄（counter / warning / summary に反映） |
| `writer_reject` | Writer 到達後に route / sink / writer-side policy で配送不能と判定 |
| `partial_delivered` | required sink set の一部のみ到達 |
| `unexpected_loss` | accepted されたが理由なく消えた状態。**設計または実装バグとして扱う** |
| `overload_shed` | bounded queue / timeout 方針による明示破棄に付与する qualifier |

### C.4 内部定数（絶対防衛線）

| 定数 | 値 | 意味 |
|---|---|---|
| `MAX_IPC_LOG_TIMEOUT_SECONDS` | 3.0 秒 | log plane queue への送信待機の絶対上限 |
| `CONTROL_PLANE_ACK_TIMEOUT_SEC` | 5.0 秒 | control plane ACK wait の上限 |
| `WRITER_STOP_WAIT_TIMEOUT_SEC` | 10.0 秒 | shutdown 時の log_thread / control_thread join の bounded wait |
| `ipc_log_queue_maxsize` warning 閾値 | 100000 | これを超える指定で stderr warning（初期化は継続） |

### C.5 5 状態ライフサイクル

| 状態 | 意味 |
|---|---|
| `unconfigured` | 初期状態 |
| `auto` | `GetLogger()` 先行で auto-fire 初期化された状態 |
| `explicit` | アプリケーションコードから明示的に `ConfigureLogger()` が呼ばれた状態 |
| `configuring` | `ConfigureLogger` 実行途中の内部状態（`_lifecycle_lock` 保持下） |
| `shutting_down` | `_shutdown()` 実行途中の内部状態 |

### C.6 Safe の 6 軸（README）

| 軸 | 内容 |
|---|---|
| **Startup safety** | 不正設定・書き込み不能パスを setup 時に拒否 |
| **File safety** | rename/truncate を行わない append-only ルーティング + SHA-256 サイドカー |
| **Record / context safety** | producer 側 hand-off 時の snapshot、Writer 側の sens_kws マスキング |
| **Operational control** | 環境変数による再ビルドなしの上書き |
| **Concurrency / multiprocess safety** | parent-side Writer が sink を所有、bounded queue + explicit timeout |
| **Failure observability** | `KnownRejected` / `KnownDropped` / `UnexplainedLost` の分類 |

---

## 付録 D. 文書作成について

本ホワイトペーパーは、`README.md` / `README_ja.md`、公開設計書（`docs/design/`）、テスト、`examples/`、`BENCHMARK.md`、`benchmarks/summary/` のベンチマーク成果物、`pyproject.toml` 等のパッケージメタデータといった公開一次ソースをもとに、AI 支援による分析を用いて作成した。

最終的な内容は project maintainer が確認・採用したものであり、仕様・挙動・検証結果の正本は次の成果物である:

- ソースコード: `src/dsafelogger/`
- テスト: `tests/`
- 公開設計書: `docs/design/D_SafeLogger_Specification_v23j_full.md` / `D-SafeLogger_DetailedDesign_v23j.md` / `D-SafeLogger_TestDesign_v23j.md`
- 公開ベンチマーク成果物: `BENCHMARK.md`、`benchmarks/summary/*.md`、`benchmarks/results/<selected>/`
- 公開 API リファレンス: `docs/api/`

本書とこれら正本との間に齟齬がある場合は、正本が優先する。

### Document Provenance (English)

This whitepaper was prepared with AI-assisted analysis based on the public project sources, including `README.md` / `README_ja.md`, the public design documents under `docs/design/`, the test suite, the `examples/` directory, `BENCHMARK.md`, the benchmark artifacts under `benchmarks/summary/`, and package metadata such as `pyproject.toml`.

The final content was reviewed and accepted by the project maintainer. The source code, tests, design documents, and benchmark artifacts remain the source of truth. In case of any discrepancy between this whitepaper and those primary artifacts, the primary artifacts take precedence.

---

## 文書終端

本書は D-SafeLogger v23j 時点の現行アーキテクチャの整理・評価である。

- **改善提案は含まない**: 本書は v23j 時点のアーキテクチャ説明・評価を目的とし、issue tracker / roadmap の代替ではない。
- **競合情報は公開一次ソースに基づく**: 一次ソース確認は 2026-05-09 時点。今後の更新により状況は変動しうる。
- **採用率・人気・反響の予測は行わない**: 設計上の位置づけ整理に限定する。

将来バージョン（v24+）の設計予測、個別関数の実装品質審査、特定 OS / Python バージョン固有の挙動詳細は本書のスコープ外である。

---

> 本ホワイトペーパーは Apache License 2.0 の下で公開される。本ライブラリ自体のライセンスと同一である。
> © 2026 D-SafeLogger contributors
