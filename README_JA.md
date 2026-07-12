# LCE: Lightweight Cognitive Engine

> LLMやツールの前後で、判断・検証・制御を担う実験的Open Coreです。

[English](README.md) | [全体像](OVERVIEW.md) | [最短実行](QUICKSTART.md) | [公開準備](RELEASE_READINESS.md) | [現在の検証状態](CURRENT_STATUS.md)

LCEはLLMではなく、Transformerの置き換えでもありません。LLM、RAG、Web検索、
業務APIなどが生成・取得した候補を、明示的な契約、根拠、権限、状態、traceで扱う
軽量な制御レイヤーです。

```text
入力 -> LCEの方針・根拠・出力契約 -> 必要ならモデル/ツール
     -> LCEの構造・認可・状態・trace検査 -> 結果
```

## 現在できること

- データのみで構成するPack/Profileの読み込みとcontent hash固定
- 限定状態遷移の決定論的trace/replay
- JSON構造出力の検査、限定修復、宣言済み根拠/意図の照合
- 候補、採点、受理済み結果の保証ゲート
- アプリケーションとLLM/RAG/プログラムの間に置けるローカルHTTP Control API
- モデル・ネットワーク不要で動く最小SDKと参照アプリ

## 現在は主張しないこと

- 汎用会話、事実性、汎用推論、LLMとの品質同等性
- 単体20B級の性能
- 第三者Pack配布、任意プラグイン実行、公開サービス、Piの本番運用

## 最短実行

Python 3.11以上で、リポジトリ直下から実行します。

```powershell
py -3.11 examples\quickstart_open_core.py
py -3.11 examples\reference_assurance_gateway.py
```

どちらもモデル、ネットワーク、可変永続化を使いません。期待結果は
[QUICKSTART.md](QUICKSTART.md) にあります。

## APIとして組み込む

アプリケーションがLLMやプログラムの候補をAPIへ渡し、LCEの判断を受け取ってから
次の処理を行えます。

```powershell
python -m lce_validation.api_server --host 127.0.0.1 --port 8789
python examples\api_client_demo.py --base-url http://127.0.0.1:8789
```

APIは `ACCEPT`、`RETURN_TO_MODEL`、`HOLD` を返します。モデルやツールをAPIが勝手に
実行することはありません。詳細は [API.md](API.md) を参照してください。

## ローカルLLMとの組み合わせ

Gemma E4Bとのライブ試験では、LCEがJSONとしては有効でも根拠契約を満たさない
候補を止められることを確認しています。これは構造化出力の限定的な統合証跡であり、
Gemmaの会話品質や事実性を保証するものではありません。

詳細は [Gemma E4B + LCEライブ比較](outputs/gemma4-e4b-lce-ablation-20260712/REPORT_JA.md) を参照してください。
同じ候補を比較する版管理済み参照デモは
[Gemma 4 E4B参照統合](GEMMA4_E4B_REFERENCE.md) を参照してください。

## 最初の公開範囲

最初の公開候補は **v0.1.0-alpha: Experimental Open Core + Reference Pack +
Reference Assurance Gateway** です。公開可否は
[RELEASE_READINESS.md](RELEASE_READINESS.md) の条件で判断します。

本リポジトリはソース公開型ライセンスを採用しています。個人として利用する場合は広範な
利用を許可し、法人・団体としての利用には事前の書面承認が必要です。OSI準拠のOSS
ライセンスではありません。詳細は [LICENSE](LICENSE)、
[法人利用の申請](ORGANIZATIONAL_USE.md)、[LICENSE_POLICY.md](LICENSE_POLICY.md) を参照してください。

## 資料

- [資料索引](DOCUMENTATION_INDEX.md)
- [アーキテクチャと境界](OVERVIEW.md)
- [Open Core SDK](OPEN_CORE_SDK.md)
- [評価方針](EVALUATION_POLICY.md)
- [独立ホールドアウト評価計画](EVALUATION_HOLDOUT_PLAN.md)
- [性能測定の範囲](PERFORMANCE.md)
- [Pack信頼境界](PACK_TRUST.md)
- [貢献方法](CONTRIBUTING.md) / [セキュリティ](SECURITY.md)
