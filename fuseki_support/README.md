# Fuseki Support

## 概要

このリポジトリは以下を提供します。

- `fuseki_export.py`: Apache Jena Fuseki の全データセット/全グラフを CSV と Excel にエクスポート
- `fuseki_migrate.py`: Fuseki の全データセット定義と全グラフデータをバックアップし、別Fusekiへ復元
- `web/`: CSV を木構造（graph > subject > object）で表示するブラウザアプリ

## エクスポート（CSV / Excel）

PowerShell から実行:

```powershell
uv run python .\fuseki_export.py --base-url http://127.0.0.1:3030 --out-dir .\out
```

特定のデータセットだけ対象にする場合:

```powershell
uv run python .\fuseki_export.py --dataset pd3_data --dataset other_ds
```

カンマ区切りでも指定できます:

```powershell
uv run python .\fuseki_export.py --datasets pd3_data,other_ds
```

注意:

- Fuseki が Windows 側で動いていて WSL から実行する場合、`127.0.0.1` ではなく Windows ホスト IP を指定してください。
- 出力ファイルは `out/` に CSV と XLSX の両方が生成されます。

## Fuseki 丸ごと移行（バックアップ/復元）

`fuseki_migrate.py` は以下を対象に保存/復元します。

- データセット一覧（`/$/datasets`）
- 各データセットの管理情報（取得できる範囲）
- 既定グラフと全Named GraphのRDFデータ（N-Triples）

### バックアップ

全データセットを保存:

```powershell
uv run python .\fuseki_migrate.py backup --base-url http://127.0.0.1:3030 --out-dir .\backup
```

対象データセットを限定:

```powershell
uv run python .\fuseki_migrate.py backup --dataset pd3_data --dataset other_ds --out-dir .\backup
```

### 復元

バックアップを別Fusekiへ復元:

```powershell
uv run python .\fuseki_migrate.py restore --base-url http://127.0.0.1:3030 --backup-dir .\backup
```

既存データセットがある場合の動作:

- `--if-exists skip`（デフォルト）: 既存データセットは再作成せず、そのまま利用
- `--if-exists error`: 既存データセットがあればエラー終了
- `--if-exists replace`: 既存データセットを削除してから再作成

補足:

- 復元時はデフォルトで `--clear-before-load` が有効です（既定/Named Graphをクリアしてから投入）。
- 復元時はデフォルトで `--create-missing` が有効です（不足データセットを作成）。
- Fusekiの構成によっては管理APIの権限やエンドポイント設定が必要です。

## Graph Tree Viewer（Web）

Web アプリを開く方法:

- 直接開く: ブラウザで `web/index.html` を開く
- ローカルサーバーで起動:

```powershell
python -m http.server --directory C:\work_umehara\codex\fuseki_support\web 8000
```

`fuseki_export.py` で出力した CSV を読み込んでください。

機能:

- 木構造表示: `graph > subject > object`
- object ノードに predicate をタグ表示
- object クリックで詳細表示＆ Graph/Subject/Object をコピー
- 検索は AND と除外（`-word`）に対応
