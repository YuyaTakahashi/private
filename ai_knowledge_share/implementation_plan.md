# Dify YAML自動デプロイ実装プラン

Difyのコンソールトークンを使用し、Antigravity（AIエージェント）から直接Difyのワークフロー（YAML）を更新・反映できるようにします。

## プロジェクト構成の変更

### [article-creation]

#### [NEW] [deploy_dify.py](file:///Users/takahashi_yuya/workspace/private/article-creation/scripts/deploy_dify.py)
Dify Console APIを叩いてYAMLファイルをアップロードするスクリプト。

#### [NEW] [.env.local](file:///Users/takahashi_yuya/workspace/private/article-creation/.env.local)
コンソールトークンとApp IDを保存する設定ファイル（`.gitignore`で除外）。

## Proposed Changes

### 1. 認証情報の保存
抽出したトークンとApp IDを `.env.local` に保存します。

### 2. デプロイスクリプトの実装
`scripts/deploy_dify.py` を作成し、DifyのConsole APIに対してYAMLファイルを送信するロジックを実装します。
- エンドポイント: `https://cloud.dify.ai/console/api/apps/import` (または特定アプリ更新用のエンドポイント)
- 認証: `Cookie: __Host-access_token=<TOKEN>` を使用

### 3. XML -> YAML の用語統一
リポジトリ内の用語をXMLからYAMLに統一します（完了済み）。

## Verification Plan

### Automated Tests
1. スクリプトを実行し、Dify上のワークフローがエラーなく更新されることを確認します。
   ```bash
   python3 scripts/deploy_dify.py
   ```

### Manual Verification
1. Difyの管理画面を開き、ワークフローが最後にAntigravityが生成したYAMLの内容と一致しているか目視で確認します。
