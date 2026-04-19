---
name: article-creator
description: UX用語の解説記事をWeb検索→執筆→ファクトチェック→WordPress下書き投稿まで一気通貫で実行するスキル。article-creationプロジェクトのDifyパイプラインをClaude上で再現する。
---

# article-creator スキル

指定されたUX用語の解説記事を生成し、WordPressに下書きとして投稿する。
Difyパイプライン（01〜10）に相当する処理をClaude上で完結させる。

## 引数

```
/article-creator <topic> [context="..."] [difficulty=0.5] [it=0.5]
```

| 引数 | 必須 | 説明 |
|---|---|---|
| `topic` | 必須 | 記事にするUX用語（例: `メンタルモデル`） |
| `context` | 任意 | 同名異義の場合などに文脈を補足（例: `context="認知心理学の観点から"`） |
| `difficulty` | 任意 | 記事の難易度 0.0（中学生）〜 1.0（専門教授）、default 0.5 |
| `it` | 任意 | ITリテラシー前提 0.0（一般ユーザー）〜 1.0（熟練エンジニア）、default 0.5 |

## 事前設定（初回のみ）

`/Users/takahashi_yuya/workspace/private/article-creation/.env` を作成する。
`.env` が存在しない、または必須キーが空の場合はユーザーに作成を促して中断する。

```
WP_SITE_URL=https://example.com
WP_USER=your-wp-username
WP_APP_PASS=xxxx xxxx xxxx xxxx xxxx xxxx
WP_POST_TYPE=posts
```

`WP_APP_PASS` はWordPress管理画面の「ユーザー → プロフィール → アプリケーションパスワード」で発行する。
スペース区切りの形式で保存してよい（使用時にスペースを除去する）。

---

## 実行手順

### Step 0: 設定読み込みと重複チェック

1. `/Users/takahashi_yuya/workspace/private/article-creation/.env` を Read ツールで読み込む
2. `WP_SITE_URL` / `WP_USER` / `WP_APP_PASS` / `WP_POST_TYPE` を変数に格納する
   - `WP_POST_TYPE` が未設定の場合は `posts` をデフォルト値とする
3. WP REST APIで同名記事の存在を確認する：

```
GET {WP_SITE_URL}/wp-json/wp/v2/{WP_POST_TYPE}?search={topic}&per_page=5&status=publish,draft
Authorization: Basic base64({WP_USER}:{WP_APP_PASS_NO_SPACES})
```

既存記事が見つかった場合はタイトルとURLを表示し、続行するか確認を求める。

---

### Step 1: Web検索による情報収集

以下の観点でWebSearchを実行する（**最低3つの異なる信頼できる情報源**を参照すること）。

- `{topic}` の定義と概要（日本語・英語両方で検索）
- 語源・提唱者・提唱年・所属機関・提唱の背景
- UXデザイン/プロダクト開発の実務での活用事例
- 類似用語・混同されやすい概念との違い

`context` が指定された場合はその文脈に合致する意味に絞る。
検索しても信頼できる情報源が3つ見つからない場合は、その旨を記録して続行する。

---

### Step 2: 記事初稿生成

収集した情報をもとに以下の構成・ルールで記事を生成する。

#### 難易度パラメータの適用

- `difficulty`: {difficulty}
  - 0.0 = 中学生レベル（専門用語なし、身近な例え話中心）
  - 1.0 = 専門教授レベル（学術的定義・厳密性・背景理論まで網羅）
- `it`: {it}
  - 0.0 = 一般ユーザー（「サーバー」「UI」「API」等も噛み砕く）
  - 1.0 = 熟練エンジニア・研究者（実装詳細・業界標準用語を多用）

#### 文体ルール

- 「だ・である」調（常体）で統一する
- 箇条書きだけの羅列にしない。各セクションは必ず文章（段落）で構成し、論理的なつながりを持たせる
- 箇条書きは項目列挙・手順を示す場合のみ限定的に使用する
- 見出し・箇条書きの先頭に連番（「1. 」「2. 」）は付けない
- 見出しは15文字程度で内容を要約した具体的な表現にする
  - NG: 「特徴とメリット」「具体的な手順」
  - OK: 「主観的な使いやすさを数値で示す」「共通言語化で合意形成を促す」
- 「〜とは」で始まる見出し禁止
- 人名（日本人以外）は英語表記の直後に `¥カタカナ¥` でルビを付与する
  - 例: `Herbert¥ハーバート¥ A¥エー¥. Simon¥サイモン¥`

#### 出力フォーマット（Markdown）

```markdown
## 記事タイトル
{用語名}（{英語名}）

## 最小限の説明
{トピックを平易な言葉で15〜20文字程度で定義。名詞で終わる。例: 〜なフレームワーク}

-- wp分割ライン--

{導入リード文: 用語の定義と最大の価値・結論を3〜4行の文章で簡潔にまとめる。太字は使わない}

## {定義や本質を表す見出し（15文字程度）}
{「〜とは」は避けた見出し。類似用語との違いや概念を平易な言葉で文章形式で説明}

## 語源・提唱者
{誰がいつ提唱したか、どのような背景・課題感からその概念が生まれたのかを物語るように文章で記述}

## {提供価値や解決する課題を表す見出し（15文字程度）}
{「特徴とメリット」は不可。この手法を使うことで得られる「状態」や「解決策」を見出しにする}

## {実践方法や仕組みを表す見出し（15文字程度）}
{「具体的な手順」は不可。アクションの内容が伝わる見出し。実務での実施フローを文章で記述}

## {具体的な活用法を表す見出し（15文字程度）}
{具体的な活用方法・現場で使えるシーンを1つだけ。読者が利用するイメージがわくように}

## 関連用語
- {関連用語1}
- {関連用語2}
- {関連用語3}
```

---

### Step 3: ファクトチェックと自動修正

WebSearchを使って以下の事実を検証し、**誤りは自動修正して続行する**。

検証対象：
- 人名の表記・スペル
- 提唱者・提唱年・所属機関
- 数値・統計データ
- 因果関係・歴史的事実の主張

修正した箇所は `[ファクトチェック修正]` としてコンソールに出力する（ユーザーへの確認は不要）。
修正がない場合は「ファクトチェック: 問題なし」と出力する。

---

### Step 4: メタデータ抽出

記事本文から以下を抽出・生成する。

#### カテゴリID（1つだけ選択）

| カテゴリ | ID |
|---|---|
| ツール・フレームワーク・方法論・分類 | 22 |
| テクノロジー・技術 | 418 |
| デザイン・情報設計 | 347 |
| マーケティング・ビジネス | 358 |
| リサーチ・分析・テスト | 369 |
| 心理学・行動経済学・脳科学 | 21 |
| 思考・マインド・バイアス | 20 |
| 組織・ファシリテーション | 262 |

#### 同義語辞書（JSON形式）

記事内の専門用語について、表記ゆれ・英語・正式名称を列挙する。

```json
{
  "記事内の単語A": ["単語A", "正式名称A", "EnglishA"],
  "記事内の単語B": ["単語B", "別名B"]
}
```

---

### Step 5: アイキャッチ用プロンプト生成

以下の手順で画像生成AIへのプロンプトを生成する（実際の画像生成は行わない）。

1. 記事の内容を表す**抽象的な視覚メタファー**を英語で考案する
   - 具体的なUI画面・機器・複雑な機械は禁止
   - 概念を図形・流れ・抽象的な形で表すイメージ
2. 以下のテンプレートの `{ABSTRACT_VISUAL_EN}` を埋める：

```
A flat vector illustration on a solid warm cream beige background #F2F0E6. At the top center, the Japanese text '{TOPIC_JP}' is displayed in bold, dark charcoal, sans-serif font. Below the text, {ABSTRACT_VISUAL_EN}. Minimal corporate art style with thick dark charcoal outlines. Simple geometry, high contrast, no shading. Muted blue and grey palette. The illustration block must preserve an exact 16:10 aspect ratio, even though the final file is 1:1.
```

注意: ダブルクォーテーション（"）禁止。必要な場合はシングルクォーテーション（'）を使用。

---

### Step 6: ローカルMDファイル保存

`drafts/` ディレクトリがなければ作成し、以下のパスに保存する：
`/Users/takahashi_yuya/workspace/private/article-creation/drafts/{topic}.md`

ファイル構成：

```markdown
---
topic: {topic}
en_title: {英語名}
category_id: {ID}
eyecatch_prompt: |
  {Step 5で生成したプロンプト文字列}
synonyms: {同義語JSONのインライン表記}
---

{Step 3完了後の記事本文（Markdown）}
```

---

### Step 7: WordPress REST APIへの下書き投稿

#### 7-1: HTML変換処理

`-- wp分割ライン--` より前の行（記事タイトル・最小限の説明）はWP投稿本文から除外する。
以下の変換ルールを適用してMarkdownをHTMLに変換する：

| Markdown | HTML |
|---|---|
| `## 見出し` | `<h2>見出し</h2>` |
| `### 見出し` | `<h3>見出し</h3>` |
| `**太字**` | `<strong>太字</strong>` |
| `*斜体*` | `<em>斜体</em>` |
| `- リスト項目` | `<ul><li>リスト項目</li></ul>` |
| 段落（空行区切り） | `<p>...</p>` |
| `Text¥カタカナ¥` | `<ruby>Text<rt>カタカナ</rt></ruby>` |

#### 7-2: WP REST APIへのPOST

Bash ツールで curl を使って投稿する。`WP_APP_PASS` はスペースを除去してから使用する。

```bash
WP_AUTH=$(echo -n "{WP_USER}:{WP_APP_PASS_NO_SPACES}" | base64)

curl -s -X POST \
  "{WP_SITE_URL}/wp-json/wp/v2/{WP_POST_TYPE}" \
  -H "Authorization: Basic ${WP_AUTH}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "{topic}（{英語名}）",
    "content": "{HTML変換後の本文}",
    "excerpt": "{最小限の説明}",
    "status": "draft",
    "categories": [{category_id}]
  }'
```

レスポンスのHTTPステータスコードを確認する：
- 201: 成功 → `link` フィールドからWP管理画面URLを取得して報告
- 401: 認証エラー → `.env` の `WP_USER` / `WP_APP_PASS` を確認するよう案内
- 404: エンドポイントエラー → `WP_POST_TYPE` が正しいか確認するよう案内

---

## 完了報告

以下をまとめてユーザーに報告する：

```
記事タイトル  : {topic}（{英語名}）
カテゴリ      : {カテゴリ名}（ID: {ID}）
ファクトチェック修正: {修正箇所のサマリー or "なし"}
ローカルMD    : private/article-creation/drafts/{topic}.md
WP下書きURL   : {WP管理画面のURL}
アイキャッチ用プロンプト:
---
{プロンプト文字列}
---
```
