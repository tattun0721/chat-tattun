# CHAT TATTUN — Nationwide Hotel Catalog

全国の**実在する宿泊施設**を収録するための公開プロジェクトです。

- データ: [Overture Maps Places](https://docs.overturemaps.org/guides/places/) の lodging 分類
- 地域: 日本国内の宿泊施設のみ
- 正確な収録軒数は取得後の `site/catalog-info.json` に自動記録します
- 厚生労働省の約5.3万施設という統計は**宿泊許可の統計**であり、Overtureとの件数一致は保証されません
- 名称、位置情報、住所、登録Webサイトを使用。設備、写真、料金、営業状況、掲載サイトが公式かどうかは未確認
- 無関係な施設・重複する宿の混入可能性があります

## 取得手順

[Actions → Fetch real Japan lodging catalog](../../actions/workflows/import-lodging.yml) を開き「Run workflow」を押すと、実データを取得し `site/hotels.json` と `site/catalog-info.json` に保存します。初回セットアップでは push 時にも起動するよう設定しています。

取得後は `site/index.html` で検索するか、Actions の artifact にある `chat-tattun-website` をNetlifyへアップロードしてください。

## 重要な表示ルール

データが未取得の間は「0件／未取得」と表示し、ダミーのホテルを数に含めません。登録Webサイトが宿の公式サイトだとは限りません。
