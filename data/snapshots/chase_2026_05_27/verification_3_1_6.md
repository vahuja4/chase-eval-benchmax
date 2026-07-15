# Verification 3.1.6

## 1. Total reconciliation

- Expected (3.1.5 exact counts): 133,662,146
- 3.1.6 streaming total: 133,662,146
- Match: **PASS**

## 2. Per-stratum counts

| Stratum | Hop | 3.1.5 count | 3.1.6 count | Match |
|---------|:---:|----------:|----------:|:-----:|
| credit_cards | 3 | 11,375 | 11,375 | PASS |
| credit_cards | 4 | 68,449 | 68,449 | PASS |
| cross_domain | 3 | 793,646 | 793,646 | PASS |
| cross_domain | 4 | 36,120,201 | 36,120,201 | PASS |
| education_center | 3 | 2,515,887 | 2,515,887 | PASS |
| education_center | 4 | 94,152,588 | 94,152,588 | PASS |

## 3. EXACT spec≥0.1 count

- Corpus-wide: 6,749
  - credit_cards: 256
  - cross_domain: 1,121
  - education_center: 5,372
- Biased 500K: 102 (compare)

## 4. EXACT cond→conseq chain share

- credit_cards 3-hop: 3,462 / 11,375 = 30.4352%
- cross_domain 3-hop: 132,670 / 793,646 = 16.7165%
- education_center 3-hop: 521,267 / 2,515,887 = 20.7190%
- credit_cards 4-hop: 34,779 / 68,449 = 50.8101%
- cross_domain 4-hop: 9,823,144 / 36,120,201 = 27.1957%
- education_center 4-hop: 27,925,397 / 94,152,588 = 29.6597%

## 5. THE KEY CELL — spec≥0.1 AND has_cc

| Stratum | Hop | Count |
|---------|:---:|------:|
| credit_cards | 3 | 44 |
| credit_cards | 4 | 59 |
| cross_domain | 3 | 126 |
| cross_domain | 4 | 230 |
| education_center | 3 | 655 |
| education_center | 4 | 1,483 |

**Grand total: 2,597**

## 6. Bridge-type mix (exact)

- defines_uses: 345,329,975 (86.8%)
- condition_consequence: 44,282,108 (11.1%)
- hyperlink: 8,053,447 (2.0%)

## 7. Sparse strata check

- All strata have chains
- Strata with 0 within-stratum chains (cross-domain only): ['auto', 'customer_service', 'investing', 'mortgage', 'personal_banking']

## 8. D2: 4-hop reasoning-bearing chains

- 4-hop chains with has_cc=True: 37,783,320

## 9. Stop-condition: supply vs demand

Pilot plan is 150 entries; full plan scales to 3,000.

| Stratum | Pilot demand | Scaled (3K) | C4 spec≥0.1+cc | Cross-domain cc (any spec) | Verdict |
|---------|:---:|:---:|------:|------:|:--|
| auto | 1 | 20 | 0 | 62,995 | OK if spec floor dropped |
| credit_cards | 4 | 80 | 103 | 9,500,087 | OK |
| customer_service | 2 | 40 | 0 | 92 | OK if spec floor dropped |
| education_center | 3 | 60 | 2,138 | 9,955,720 | OK |
| investing | 1 | 20 | 0 | 108 | OK if spec floor dropped |
| mortgage | 1 | 20 | 0 | 63,052 | OK if spec floor dropped |
| personal_banking | 5 | 100 | 0 | 381,612 | OK if spec floor dropped |
