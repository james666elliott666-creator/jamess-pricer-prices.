# James’s Pricer — public price updater

Prepared for `james666elliott666-creator/jamess-pricer-prices.`.

This folder contains public product information only. **Do not upload your app HTML, customer records, quote backups or the complete setup ZIP to this repository.**

## Status

- Repository created; upload awaits GitHub connection permissions. Live testing is still outstanding.
- Initial feed contains nine prices checked from supplier pages during preparation. The remaining app prices stay at their bundled values until verified.
- Full catalogue run, GitHub download and Android APK tests are outstanding.

## Activate

1. Create the public repository `jamess-pricer-prices.` under the account above, with default branch `main`.
2. Upload the contents of this folder, including `.github/workflows/prices.yml`.
3. In Actions, open **Update City Plumbing prices**, then **Run workflow**.
4. Confirm the run finishes and inspect `check-report.json`. Failed products retain their previous values and require review if persistent.
5. Confirm `https://raw.githubusercontent.com/james666elliott666-creator/jamess-pricer-prices./main/prices.json` is available.
6. Build the separate prepared HTML into the APK. It needs internet access and permission to fetch HTTPS data from its local WebView origin. If the builder blocks that, its settings or native wrapper must be adjusted.
7. Tap Materials → Update now. Close and reopen in flight mode, and verify saved prices and quotes.

The workflow is scheduled for Mondays at 05:23 UTC. GitHub can delay scheduled jobs. Only standard Linux runners are used. Keep paid services disabled. GitHub may pause scheduled workflows in inactive public repositories; successful report commits normally maintain activity, but monitor Actions failures and the app’s freshness indicator.

## Behaviour

The updater reads the public page data, matches the exact product code, checks pack quantities where supplied and uses explicit VAT-inclusive GBP prices. Quantity-one promotions can apply; bulk prices are not applied to single quantities. Large changes, conflicting prices, missing products or changed packs are held for review. Page structure changes can require maintenance.

The app downloads only the public feed; it does not send properties, customer details or quotes. The cache is separate from the quote database. Existing quotes and saved room radiator snapshots retain their original prices. Re-adding a radiator from a saved room currently uses that room’s saved price; automatic repricing of existing room selections is not included.

The app checks on launch and reconnection (at most once per hour within a session), plus a manual Update now button. Download failures leave existing prices intact. The supplier checker updates the feed weekly; opening the app does not scrape the supplier.

## Local checker

Python 3.12, no third-party packages:

```sh
python update_prices.py
```

Use `--limit 5 --output /tmp/pricer-check` for a small isolated test. Every successful run updates `prices.json`; all failures preserve the existing feed and produce a failing exit status. Individual failures appear in `check-report.json`.
