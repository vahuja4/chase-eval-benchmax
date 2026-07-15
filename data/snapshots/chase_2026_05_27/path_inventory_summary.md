# Path inventory summary

## 1. Graph size

- Nodes: 2313
- Edges: 88456
  - defines_uses: 77226
  - condition_consequence: 7751
  - hyperlink: 3479

## 2. Per-stratum hop counts

| Stratum | 3-hop | 4-hop |
|---------|------:|------:|
| auto | 0 | 0 |
| credit_cards | 11,375 | 68,449 |
| customer_service | 0 | 0 |
| education_center | 2,515,887 | 94,152,588 |
| investing | 0 | 0 |
| mortgage | 0 | 0 |
| personal_banking | 0 | 0 |

## 3. Cross-domain counts

- 3-hop cross-domain: 793,646
- 4-hop cross-domain: 36,120,201
- Cross-domain share: 27.6%

### Cross-domain strata participation

Which strata appear in cross-domain chains (from stored sample):

| Stratum | Appearances | % of cross-domain |
|---------|----------:|------------------:|
| education_center | 108,333 | 100.0% |
| credit_cards | 96,001 | 88.6% |
| personal_banking | 10,075 | 9.3% |
| mortgage | 1,665 | 1.5% |
| auto | 1,665 | 1.5% |
| customer_service | 3 | 0.0% |

## 4. Validity filter impact

(See stdout for rejection counts during enumeration.)

## 5. Bridge-type mix across valid chains

*Based on stored sample of 500,000 out of 133,662,146 total chains.*

- defines_uses: 1,139,541 (91.2%)
- condition_consequence: 77,376 (6.2%)
- hyperlink: 33,083 (2.6%)
- Chains using a hyperlink hop: 33,083

## 6. Bridge specificity distribution

*Based on stored sample of 500,000 chains.*

- Min: 0.001000
- P25: 0.003509
- Median: 0.003509
- P75: 0.005917
- Max: 0.333333

  - >=0.1 (rare entity): 102
  - 0.01–0.1: 56,239
  - 0.001–0.01: 443,659
  - <0.001 (very common): 0

## Stop-condition checks

- 4-hop chain count: 130,341,238 (above 50 threshold)
- Within-stratum chains: 96,748,299 (72%)
