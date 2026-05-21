---
name: ux-collective-study-group
description: UX collective勉強会の情報収集と学習ノート生成を行うスキル。直近の勉強会の議事録・文字起こしを取得し、スプレッドシートから記事情報を取得して、記事ごとの学習ノートMDファイルを生成する。note記事の生成はux-collective-noteスキルが担う。
auto_activate: true
activation_phrases:
  - "UX collective勉強会のまとめを作って"
  - "UX collectiveのまとめを作って"
  - "勉強会のまとめノートを作って"
  - "UX collective勉強会のノートを作って"
  - "勉強会の情報を集めて"
---

# UX Collective Study Group Note Skill

## 1. 概要 (Overview)

UX collective勉強会（毎週水曜12:00〜）の学習ノートを自動生成します。
議事録・文字起こしを取得し、記事ごとに以下の構成でMDファイルを作成します。

- 記事の内容
- 過去の学びのつながり（読書会・勉強会フォルダからの関連学び）
- 参加メンバーの発言
- 自分の学び（記入欄のみ用意）

## 2. 実行ステップ (Process)

### Step 1: 前回の勉強会日時を確認

以下の2つのソースを確認し、直近のUX collective勉強会の日時を特定する。

**A. Google Calendar（Geminiメモ優先）**
- Google Calendar MCP（`gcal_list_events`または`gcal_search_events`）で「UX collective」または「UX DAYS TOKYO」のイベントを検索
- 直近の開催日時を取得する

**B. Circleback（補完）**
- `mcp__claude_ai_Circleback__SearchMeetings`で「UX collective」を検索
- Google Calendarで見つからない場合はCirclebackを確認

**C. フォルダ確認（最終手段）**
- `/Users/takahashi_yuya/workspace/private/読書会・勉強会/UX collective勉強会/` の最新フォルダ（MMDD形式）を確認し、日付を推定

### Step 2: 議事録・文字起こしを取得

以下の優先順位で取得する。

1. **勉強会フォルダ内のファイルを先に確認**
   - `/Users/takahashi_yuya/workspace/private/読書会・勉強会/UX collective勉強会/{MMDD}/` フォルダが存在するか確認
   - `gemini_memo.md`、`transcript.md`、`memo*.md` が既にある場合はそれを使用

2. **Google Calendar Geminiメモ（推奨）**
   - `gemini_memo.md` 内のGoogle DocsリンクがあればGoogle Workspace CLIで取得
   - Geminiメモには参加者の発言・議論の詳細が含まれる

3. **Circleback議事録（補完）**
   - `mcp__claude_ai_Circleback__SearchMeetings` で該当日時の会議を検索
   - `mcp__claude_ai_Circleback__GetTranscriptsForMeetings` で文字起こしを取得

### Step 3: スプレッドシートから記事タイトルとリンクを取得

以下のスプレッドシートにアクセスし、該当日付の記事情報を取得する。

**スプレッドシートURL:**
```
https://docs.google.com/spreadsheets/d/1aE-9DbB2R11BuEr5pPI7wOk6zzg83Nvldb5OE-70gy4/edit?gid=0#gid=0
```

- Google Workspace CLI（Google Sheets）で対象行を取得
- 日付列から該当日を特定し、記事タイトルとURLを2件取得
- 取得できない場合は議事録・文字起こしから記事タイトルを推定

### Step 4: 日付フォルダを確認・作成

- パス: `/Users/takahashi_yuya/workspace/private/読書会・勉強会/UX collective勉強会/{MMDD}/`
- MMDD形式: 4月8日 → `0408`、3月11日 → `0311`
- フォルダが既に存在する場合はそのまま使用（上書きしない）

### Step 5: 記事ごとにMDファイルを生成

1記事につき1つのMDファイルを作成する（通常2記事分）。

**ファイル名:** `article{N}_{MMDD}.md`（例: `article1_0408.md`、`article2_0408.md`）

**既存ファイルがある場合:** 上書きせず、ユーザーに確認する。

---

## 3. 出力フォーマット (Output Format)

各MDファイルは以下の構成で生成する。

```markdown
# {記事タイトル}

**URL:** {記事URL}
**勉強会日:** {YYYY年M月D日}

---

## 記事の内容

{議事録・文字起こしをもとに、記事の主要な主張・フレームワーク・事例をまとめる。
箇条書きより段落で書くことを優先する。}

---

## 過去の学びのつながり

{`/Users/takahashi_yuya/workspace/private/読書会・勉強会/` 以下のフォルダ（他の勉強会・読書会）を確認し、
テーマや概念が重なる過去の学びがあれば記載する。
関連がなければこのセクションは「（特になし）」とする。無理に記載しない。}

---

## 参加メンバーの発言

{議事録・文字起こしから、参加者の発言・気づき・疑問を抜き出す。
発言者名がわかる場合は「鈴木さん：」のように明記する。}

---

## 自分の学び

<!-- ここに記入 -->

```

---

## 4. 参照フォルダ構造

```
/Users/takahashi_yuya/workspace/private/読書会・勉強会/
├── UX collective勉強会/
│   ├── 0218/            ← MMDD形式
│   ├── 0304/
│   ├── 0311/
│   ├── 0318/
│   └── {MMDD}/          ← 今回生成するフォルダ
├── 12歳から知っておきたいAI/  ← 過去の学びの参照先
└── greg ワークショップ/       ← 過去の学びの参照先
```

## 5. 注意事項

- 「過去の学びのつながり」は、無理やり関連付けない。明確なつながりがある場合のみ記載する。
- 参加メンバーの発言は、議事録に明記されている内容のみ記載する。推測・補完はしない。
- 「自分の学び」セクションは記入欄のみ用意し、AIは埋めない。
- 文体は「です・ます」調を使わず、箇条書きや体言止めでまとめる（メモ形式）。

---

## 6. 次のステップ

学習ノート生成が完了したら、ユーザーが各ファイルの「自分の学び」セクションに振り返りを記入する。
その後、`ux-collective-note` スキルを呼び出すとnote.com向け記事を生成できる。
