# Examples

`sample-output.csv` is a synthetic illustration of the 16-column lead schema the
pipeline appends to a Google Sheet. Every value is fictional: venue names are
obviously made up, phones use the `555-01xx` reserved range, and email domains
end in `.fictional-test`. No real restaurant, person, or credential appears
here.

The 8 rows are arranged to show the full output surface:

- All three tiers (3 HOT, 4 WARM, 1 COOL).
- All three email states (`homepage`, `not_found`, `no_website`).
- One multi-unit row whose `ScoreDetail` ends with `multi_unit_+3`.
- The `ScoreDetail` and `Cuisine` columns contain commas and are CSV-quoted.

| Column | Meaning |
| --- | --- |
| Name | Restaurant name |
| Address | Full formatted address |
| Phone | Local phone from Place Details (may be blank) |
| Email | Best contact email (may be blank) |
| EmailSource | `homepage` / `not_found` / `no_website` |
| Website | Homepage URL (may be blank) |
| GoogleMaps | Google Maps link |
| Rating | 1 to 5 |
| ReviewCount | Total reviews |
| PriceLevel | 0 to 4 |
| Cuisine | Comma-joined parsed place types |
| Score | Final 0 to 13 score |
| Tier | `HOT` / `WARM` / `COOL` |
| MultiUnit | `TRUE` / `FALSE` |
| ScoreDetail | Comma-joined score breakdown labels |
| DateScraped | ISO date (`YYYY-MM-DD`) |
