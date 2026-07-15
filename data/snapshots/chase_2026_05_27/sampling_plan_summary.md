# Sampling Plan Summary

- Snapshot: chase_2026_05_27
- Schema version: chase_eval_schema_v0.1
- Target size: 150
- Oversample factor: 1.0
- Total entries: 150
- Seed: 42
- Mode: PILOT

## persona

| Value | Schema | Realized | Delta |
|-------|-------:|---------:|------:|
| prospective_customer | 25.00% | 26.00% | +1.00% |
| existing_customer_task | 30.00% | 26.00% | -4.00% |
| problem_state | 15.00% | 18.00% | +3.00% |
| small_business_owner | 10.00% | 12.00% | +2.00% |
| first_time_homebuyer | 10.00% | 9.33% | -0.67% |
| rewards_optimizer | 10.00% | 8.67% | -1.33% |

## answer_type

| Value | Schema | Realized | Delta |
|-------|-------:|---------:|------:|
| factoid | 25.00% | 32.00% | +7.00% |
| yes_no | 8.00% | 10.67% | +2.67% |
| list | 8.00% | 2.67% | -5.33% |
| procedural | 18.00% | 20.00% | +2.00% |
| comparison | 8.00% | 6.67% | -1.33% |
| multi_aspect | 8.00% | 10.00% | +2.00% |
| numeric_computational | 5.00% | 5.33% | +0.33% |
| unanswerable | 20.00% | 12.67% | -7.33% |

## formulation

| Value | Schema | Realized | Delta |
|-------|-------:|---------:|------:|
| natural_question | 50.00% | 52.00% | +2.00% |
| search_query | 25.00% | 23.33% | -1.67% |
| keyword_fragment | 10.00% | 3.33% | -6.67% |
| conversational_mobile | 15.00% | 21.33% | +6.33% |

## linguistic_noise

| Value | Schema | Realized | Delta |
|-------|-------:|---------:|------:|
| clean | 61.00% | 60.67% | -0.33% |
| typos | 15.00% | 15.33% | +0.33% |
| casing_punct | 12.00% | 14.00% | +2.00% |
| mobile_artifacts | 12.00% | 10.00% | -2.00% |

## reasoning_hops

| Value | Schema | Realized | Delta |
|-------|-------:|---------:|------:|
| single_span | 40.00% | 38.67% | -1.33% |
| single_page_synthesis | 25.00% | 23.33% | -1.67% |
| cross_section_same_product | 15.00% | 20.67% | +5.67% |
| multi_concept | 15.00% | 12.00% | -3.00% |
| cross_domain | 5.00% | 5.33% | +0.33% |

## answerability

| Value | Schema | Realized | Delta |
|-------|-------:|---------:|------:|
| answerable | 70.00% | 70.67% | +0.67% |
| unanswerable_out_of_scope | 10.00% | 10.00% | +0.00% |
| unanswerable_plausible_absent | 12.00% | 14.00% | +2.00% |
| stale_trap | 3.00% | 4.00% | +1.00% |
| compliance_sensitive | 5.00% | 1.33% | -3.67% |

## stratum

| Value | Schema | Realized | Delta |
|-------|-------:|---------:|------:|
| credit_cards | 40.00% | 28.00% | -12.00% |
| personal_banking | 25.00% | 26.67% | +1.67% |
| education_center | 15.00% | 15.33% | +0.33% |
| mortgage | 10.00% | 10.67% | +0.67% |
| auto | 4.00% | 2.00% | -2.00% |
| investing | 3.00% | 2.00% | -1.00% |
| customer_service | 3.00% | 2.00% | -1.00% |
| multi | — | 3.33% | — |
| none | — | 10.00% | — |

## Persona-stratum affinity audit

Excludes entries with stratum=none/multi (bypass stratum sampling).

| Persona | Threshold | Affinity set | Eligible n | Realized | Delta |
|---------|----------:|--------------|----------:|--------:|------:|
| first_time_homebuyer | 80% | mortgage, personal_banking | 12 | 91.67% | +11.67% |

## Chunk usage

- Distinct chunks used: 151
- Used exactly once: 139
- Used 2+ times: 12
- Max usage count: 3
- Low-info chunks selected: 12 (7.9% of distinct)

## Multi-concept structural breakdown

| Structure | Count | % |
|-----------|------:|----:|
| Same page, different H2 | 2 | 16.7% |
| Different pages, same sub_stratum | 1 | 8.3% |
| Different pages, different sub_strata | 9 | 75.0% |

## Answerability coverage

| Answerability | Count | With gold chunks | With grounding chunk |
|---------------|------:|-----------------:|---------------------:|
| answerable | 106 | 106 | 0 |
| unanswerable_out_of_scope | 15 | 0 | 0 |
| unanswerable_plausible_absent | 21 | 0 | 21 |
| stale_trap | 6 | 6 | 0 |
| compliance_sensitive | 2 | 0 | 2 |

## Reasoning-hops infeasibility log

- Total hops resamples: 0
- Total entries: 150
- Resample rate: 0.00%

## Affinity activation rate

| Persona | Affinity applied | Fallback | Total |
|---------|----------------:|----------:|------:|
| prospective_customer | 0 | 39 | 39 |
| existing_customer_task | 0 | 39 | 39 |
| problem_state | 0 | 27 | 27 |
| small_business_owner | 0 | 18 | 18 |
| first_time_homebuyer | 9 | 5 | 14 |
| rewards_optimizer | 0 | 13 | 13 |

## Invalid-combination constraint impact

- Invalid fraction of naive joint distribution: 17.7%
- Sampling method: joint distribution over constrained axes (answer_type, reasoning_hops, answerability) — no rejection needed
