# CHAT TATTUN — Nationwide Hotel Catalog

全国の**実在する宿泊施設**を収録するための公開プロジェクトです。

- データ: [Overture Maps Places](https://docs.overturemaps.org/guides/places/) の lodging 分類
- 地域: 日本国内の宿泊施設のみ
- 正確な収録軒数は取得後の `site/catalog-info.json` に自動記録します
- 厚生労働省の約5.3万施設という統計は**宿泊許可の統計**であり、Overtureとの件数一致は保証されません
- 名称、位置情報、住所、登録Webサイトを使用。設備、写真、料金、営業状況、掲載サイトが公式かどうかは未確認
- 無関係な施設・重複する宿の混入可能性があります

## 施設の実際の掲載画像

- 検索カードは `site/website-preview-photos.json` を読み、施設ごとに対応する登録サイトの画像URLを表示します。AI生成写真や別施設の代用写真は表示しません。
- 登録サイトのページタイトルと宿泊施設名を照合し、Open Graph代表画像、またはページ中のトップ／スライダー画像を探索します。取得元ページへのリンクも付けています。
- [Discover hotel photos from registered websites](../../actions/workflows/collect-official-photo-metadata.yml) が一回最大8,000施設の未調査・再調査対象を処理し、毎日継続して結果を保存します。調査済みの状態は `site/photo-scan-state.json` に記録します。
- 宿の登録サイトURLがない施設、画像の外部表示を禁止しているサイト、施設名が一致しないサイトについては、画像の表示を保証できません。画像が表示できない場合は登録サイトへのリンクを出します。
- 画像URLの発見・表示は、画像の転載許諾の取得を意味しません。正式公開で画像を再配布・保存する場合は、施設の許可または利用できるライセンスを確認してください。

## 取得手順

[Actions → Fetch real Japan lodging catalog](../../actions/workflows/import-lodging.yml) を開き「Run workflow」を押すと、実データを取得し `site/hotels.json` と `site/catalog-info.json` に保存します。初回セットアップでは push 時にも起動するよう設定しています。

取得後は `site/index.html` で検索するか、Actions の artifact にある `chat-tattun-website` をNetlifyへアップロードしてください。

## 重要な表示ルール

データが未取得の間は「0件／未取得」と表示し、ダミーのホテルを数に含めません。登録Webサイトが宿の公式サイトだとは限りません。
