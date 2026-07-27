# Local BM25 search replay parity

## Methodology

Replayed all `queries_used` from `step_2_linking_details.json` files
against the local BM25 index (text-only, Snowball English stemmer,
k1=1.5, b=0.75). Compared returned doc ids (top-10) against the
secondary chunks selected in the original Castform runs.

**Important caveat**: the baseline secondary selections are
post-filtered (400-char minimum, same-file exclusion, dedup,
Jaccard coherence >= 0.15, diversity cap). Hit-rate therefore
understates raw retrieval parity — a miss may mean the local index
retrieved the doc but the linker's downstream filters excluded it,
or the original run's filters selected a different chunk from the
same query results.

Text-only indexing is a provisional choice. If parity is weak,
text + page_title + heading_path indexing should be compared.

## Summary

- **Total linking records with queries**: 49
- **Total queries replayed**: 109
- **Unique secondary doc ids (baseline)**: 70
- **Hits (doc id in local top-10)**: 70
- **Hit rate**: 100.0%
- **Average rank when found**: 3.6

## Per-record detail

| Task ID | Source | Queries | Original docs | Hits | Misses |
|---------|--------|---------|---------------|------|--------|
| iter_3_00004 | natural_multihop | 1 | p_00196 | p_00196 | — |
| iter_3_00003 | natural_multihop | 1 | p_00133 | p_00133 | — |
| iter_3_00002 | natural_multihop | 3 | p_00063 | p_00063 | — |
| iter_2_00004 | natural_multihop | 2 | p_00126 | p_00126 | — |
| iter_2_00003__regen_01 | natural_multihop | 1 | p_00196 | p_00196 | — |
| iter_1_00004 | natural_multihop | 1 | p_00126 | p_00126 | — |
| iter_1_00003 | natural_multihop | 1 | p_00171 | p_00171 | — |
| iter_0_00004__regen_01 | natural_multihop | 2 | p_00147 | p_00147 | — |
| iter_4_00000__regen_01 | natural_multihop | 1 | p_00133 | p_00133 | — |
| iter_0_00003__regen_01 | natural_multihop | 1 | p_00182 | p_00182 | — |
| iter_0_00004__regen_01 | natural_multihop_batch4 | 3 | p_00097, p_00118 | p_00097, p_00118 | — |
| iter_4_00001 | natural_multihop_batch4 | 1 | p_00222 | p_00222 | — |
| iter_3_00004__regen_01 | natural_multihop_batch4 | 3 | p_00037 | p_00037 | — |
| iter_3_00003__regen_01 | natural_multihop_batch4 | 3 | p_00121 | p_00121 | — |
| iter_10_00000 | natural_multihop_batch4 | 1 | p_00084 | p_00084 | — |
| iter_5_00000__regen_01 | natural_multihop_batch4 | 3 | p_00215, p_00266 | p_00215, p_00266 | — |
| iter_12_00000 | natural_multihop_batch4 | 1 | p_00131 | p_00131 | — |
| iter_2_00003 | natural_multihop_batch4 | 1 | p_00010 | p_00010 | — |
| iter_2_00004__regen_01 | natural_multihop_batch4 | 3 | p_00181, p_00185 | p_00181, p_00185 | — |
| iter_1_00004__regen_01 | natural_multihop_batch4 | 3 | p_00098, p_00143 | p_00098, p_00143 | — |
| iter_1_00003__regen_01 | natural_multihop_batch4 | 3 | p_00064 | p_00064 | — |
| iter_0_00003__regen_01 | natural_multihop_batch4 | 3 | p_00220 | p_00220 | — |
| iter_4_00000__regen_01 | natural_multihop_batch4 | 1 | p_00099 | p_00099 | — |
| iter_3_00002__regen_01 | natural_multihop_batch4 | 3 | p_00116, p_00185 | p_00116, p_00185 | — |
| iter_6_00000__regen_01 | natural_multihop_batch4 | 3 | p_00095, p_00096 | p_00095, p_00096 | — |
| iter_7_00000__regen_01 | natural_multihop_batch4 | 3 | p_00229 | p_00229 | — |
| iter_8_00000__regen_01 | natural_multihop_batch4 | 1 | p_00109 | p_00109 | — |
| iter_5_00001__regen_01 | natural_multihop_batch4 | 4 | p_00092 | p_00092 | — |
| iter_9_00000__regen_01 | natural_multihop_batch4 | 3 | p_00128, p_00229 | p_00128, p_00229 | — |
| iter_13_00000__regen_01 | natural_multihop_batch4 | 3 | p_00201, p_00221 | p_00201, p_00221 | — |
| iter_11_00000__regen_01 | natural_multihop_batch4 | 3 | p_00206, p_00252 | p_00206, p_00252 | — |
| iter_15_00000__regen_01 | natural_multihop_batch4 | 3 | p_00187, p_00251 | p_00187, p_00251 | — |
| iter_16_00000__regen_01 | natural_multihop_batch4 | 2 | p_00293, p_00301 | p_00293, p_00301 | — |
| iter_17_00000__regen_01 | natural_multihop_batch4 | 3 | p_00150, p_00200 | p_00150, p_00200 | — |
| iter_0_00004 | retrieval_filtered_batch3 | 1 | p_00092 | p_00092 | — |
| iter_1_00002__regen_01 | retrieval_filtered_batch3 | 2 | p_00049, p_00062 | p_00049, p_00062 | — |
| iter_1_00003__regen_01 | retrieval_filtered_batch3 | 3 | p_00196, p_00272 | p_00196, p_00272 | — |
| iter_0_00003__regen_01 | retrieval_filtered_batch3 | 3 | p_00131, p_00227 | p_00131, p_00227 | — |
| iter_3_00002__regen_01 | retrieval_filtered_batch3 | 3 | p_00144, p_00169 | p_00144, p_00169 | — |
| iter_2_00002__regen_01 | retrieval_filtered_batch3 | 1 | p_00225 | p_00225 | — |
| iter_2_00001__regen_01 | retrieval_filtered_batch3 | 3 | p_00225 | p_00225 | — |
| iter_4_00000__regen_01 | retrieval_filtered_batch3 | 1 | p_00251 | p_00251 | — |
| iter_5_00000 | retrieval_filtered_batch3 | 1 | p_00094 | p_00094 | — |
| iter_5_00001__regen_01 | retrieval_filtered_batch3 | 3 | p_00301 | p_00301 | — |
| iter_6_00000__regen_01 | retrieval_filtered_batch3 | 3 | p_00072, p_00164 | p_00072, p_00164 | — |
| iter_8_00000__regen_01 | retrieval_filtered_batch3 | 2 | p_00102, p_00249 | p_00102, p_00249 | — |
| iter_7_00000__regen_01 | retrieval_filtered_batch3 | 3 | p_00138, p_00190 | p_00138, p_00190 | — |
| iter_7_00001__regen_01 | retrieval_filtered_batch3 | 3 | p_00181, p_00219 | p_00181, p_00219 | — |
| iter_9_00000__regen_01 | retrieval_filtered_batch3 | 3 | p_00150, p_00202 | p_00150, p_00202 | — |
