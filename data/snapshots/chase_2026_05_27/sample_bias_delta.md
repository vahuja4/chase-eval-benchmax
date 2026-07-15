# Sample bias delta: biased 500K vs EXACT

## 1. spec≥0.1 share

- Biased (500K sample): 102 / 500,000 = 0.000204 (0.0204%)
- EXACT: 6,749 / 133,662,146 = 0.000050 (0.0050%)
- Ratio (exact/biased): 0.25x

### spec≥0.1 by stratum

- credit_cards: 256 / 79,824 = 0.3207%
- cross_domain: 1,121 / 36,913,847 = 0.0030%
- education_center: 5,372 / 96,668,475 = 0.0056%

## 2. Bridge-type mix

| Bridge type | Biased share | EXACT share | EXACT count |
|-------------|:-----------:|:-----------:|------------:|
| defines_uses | 91.2% | 86.8% | 345,329,975 |
| condition_consequence | 6.2% | 11.1% | 44,282,108 |
| hyperlink | 2.6% | 2.0% | 8,053,447 |

## 3. condition→consequence chain share

- 3-hop: 657,399 / 3,320,908 = 19.7958%
- 4-hop: 37,783,320 / 130,341,238 = 28.9880%
- Overall: 38,440,719 / 133,662,146 = 28.7596%
- Biased (500K sample): ~14.6%

## 4. Cross-domain share

- EXACT: 36,913,847 / 133,662,146 = 27.6%
- Biased (500K sample): ~27.6%

## 5. THE KEY CELL — spec≥0.1 AND has_cc

| Stratum | Hop | Count |
|---------|:---:|------:|
| credit_cards | 3 | 44 |
| credit_cards | 4 | 59 |
| cross_domain | 3 | 126 |
| cross_domain | 4 | 230 |
| education_center | 3 | 655 |
| education_center | 4 | 1,483 |

**Total spec≥0.1 AND has_cc: 2,597**
