# LCE 公開ロードマップ

## v0.1.0-alpha: Experimental Open Core

最初の公開目標は、LLMの代替ではなく、LLM・RAG・ツールの候補を検証する
**Experimental Open Core + Reference Pack + Reference Assurance Gateway** です。

### Phase 1: リリース整合性

この段階は旧ロードマップとの対応では **AB1: 公開契約とガバナンス** を引き継ぐ。

- 公開入口、アーキテクチャ、現在状態、評価規約、リリース判定を同じ境界へ統一する。
- 最終ライセンスを決定し、package metadataと一致させる。
- 新規checkoutでQuickstart、参照アプリ、全テストを再現する。

### Phase 2: Gemma参照統合

- Gemma E4BのモデルID、digest、profile、timeout、契約を固定した参照アプリを追加する。
- `lm_only` / `lm_with_lce` を同じケースで比較し、構造破損、根拠違反、誤停止、修復、遅延を記録する。
- LCEがモデルの会話品質を置き換えるという主張はしない。

### Phase 3: 評価とリリース証跡

- 固定fixtureと独立holdoutを分離し、holdoutの作成者・利用時期・結果を記録する。
- CI、リリースノート、SHA-256、既知の制限、tested adaptersを公開する。

### v0.1.0-alpha のGO条件

1. 最終ライセンスが存在する。
2. 資料の実測値、実行コマンド、非保証が一致する。
3. 2つの依存なし参照アプリとGemma参照統合を再現できる。
4. 固定証跡と独立holdout計画を公開する。
5. 第三者Pack、公開サービス、汎用チャット品質を対象外と明記する。

## v0.2: 信頼できる拡張

v0.2は、署名付きPack、信頼鍵、失効・ロールバック、MySQL Pack Repository、複数の
モデルプロファイル、独立評価台帳を条件とする。これらがそろうまでは第三者Pack配布と
任意プラグイン実行をNO-GOとする。

## 長期研究目標

単体の汎用対話品質や20B級比較は、別の研究トラックである。blind/sealedな日英評価、
知識・対話・推論・コードの分離評価、再現可能なデータlineageがそろうまで公開機能の
品質主張に混ぜない。
