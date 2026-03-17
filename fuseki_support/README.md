# Fuseki Support

## 概要

このリポジトリは以下を提供します。

- `fuseki_export.py`: Apache Jena Fuseki の全データセット/全グラフを CSV と Excel にエクスポート
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
