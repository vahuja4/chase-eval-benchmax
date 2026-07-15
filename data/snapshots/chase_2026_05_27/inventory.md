# Corpus Inventory: chase_2026_05_27

## Basics
- Snapshot id: chase_2026_05_27
- Crawl date range: 2026-05-29 to 2026-05-29
- Total pages (all): 306
- Informative pages: 290
- No-info pages (excluded from chunking): 16
- Total chunks (after dedup and boilerplate decisions): 3089

## Page-level

### Stratum distribution (informative pages only)

| Stratum | Pages | % |
|---------|------:|----:|
| education_center | 233 | 80.3% |
| credit_cards | 17 | 5.9% |
| personal_banking | 29 | 10.0% |
| mortgage | 5 | 1.7% |
| auto | 2 | 0.7% |
| investing | 2 | 0.7% |
| customer_service | 2 | 0.7% |

### Sub-stratum within education_center

| Sub-stratum | Pages | % |
|-------------|------:|----:|
| basics | 104 | 44.6% |
| rewards_benefits | 73 | 31.3% |
| credit_building | 18 | 7.7% |
| chase_cards | 10 | 4.3% |
| budgeting_saving | 9 | 3.9% |
| mortgage_education | 8 | 3.4% |
| credit_score | 6 | 2.6% |
| general | 3 | 1.3% |
| student | 1 | 0.4% |
| interest_apr | 1 | 0.4% |

### Sub-stratum within credit_cards

| Sub-stratum | Pages | % |
|-------------|------:|----:|
| general | 7 | 41.2% |
| freedom | 7 | 41.2% |
| sapphire | 3 | 17.6% |

### Sub-stratum within personal_banking

| Sub-stratum | Pages | % |
|-------------|------:|----:|
| checking | 17 | 58.6% |
| digital_payments | 6 | 20.7% |
| fees | 3 | 10.3% |
| savings | 2 | 6.9% |
| general | 1 | 3.4% |

### Sub-stratum within mortgage

| Sub-stratum | Pages | % |
|-------------|------:|----:|
| general | 2 | 40.0% |
| buying | 2 | 40.0% |
| refinance | 1 | 20.0% |

### Sub-stratum within auto

| Sub-stratum | Pages | % |
|-------------|------:|----:|
| loans | 1 | 50.0% |
| electric | 1 | 50.0% |

### Sub-stratum within investing

| Sub-stratum | Pages | % |
|-------------|------:|----:|
| athlete | 1 | 50.0% |
| education | 1 | 50.0% |

### Sub-stratum within customer_service

| Sub-stratum | Pages | % |
|-------------|------:|----:|
| tips | 1 | 50.0% |
| help | 1 | 50.0% |

### Page token statistics (informative pages)

- Min: 260
- P25: 753
- Median: 1016
- P75: 1273
- P90: 1624
- Max: 3686

## Chunk-level

### Chunk distribution by stratum

| Stratum | Chunks | % | Avg per page |
|---------|-------:|----:|-------------:|
| education_center | 2178 | 70.5% | 9.3 |
| credit_cards | 417 | 13.5% | 24.5 |
| personal_banking | 328 | 10.6% | 11.3 |
| mortgage | 78 | 2.5% | 15.6 |
| auto | 36 | 1.2% | 18.0 |
| investing | 34 | 1.1% | 17.0 |
| customer_service | 18 | 0.6% | 9.0 |

### Chunk token statistics

- Min: 20
- P25: 50
- Median: 80
- P75: 132
- P90: 197
- Max: 400

### Dedup and boilerplate summary

- Raw chunks (pre-dedup): 3169
- After exact-hash dedup: 3092
- Boilerplate decisions:
  - Dropped: 3
  - Kept-flagged (is_boilerplate=true): 0
  - Kept-clean: 3089
- Final chunks.jsonl row count: 3089

### Occurrence-count distribution

| occurrence_count | Chunks |
|------------------|-------:|
| 1 | 3029 |
| 2 | 55 |
| 3 | 5 |
| 4-5 | 0 |
| 6-9 | 0 |
| 10-19 | 0 |
| 20+ | 0 |

## Content density diagnostics

### Classifier results overview

| Label | high | medium | low | total | % |
|-------|-----:|-------:|----:|------:|----:|
| informational | 2422 | 315 | 0 | 2737 | 88.6% |
| marketing | 271 | 81 | 0 | 352 | 11.4% |

is_low_info chunks (marketing AND confidence != low): 352 (11.4%)

### is_low_info by stratum

| Stratum | Total chunks | Low-info | % |
|---------|-------------:|---------:|----:|
| education_center | 2178 | 125 | 5.7% |
| credit_cards | 417 | 106 | 25.4% |
| personal_banking | 328 | 62 | 18.9% |
| mortgage | 78 | 25 | 32.1% |
| auto | 36 | 14 | 38.9% |
| investing | 34 | 15 | 44.1% |
| customer_service | 18 | 5 | 27.8% |

### Classifier samples (calibration signal)

**marketing, confidence=high** (271 total)

- `c_00009_00` [credit_cards] reason="It is a promotional headline highlighting a bonus offer and product name without substantive details."
  Earn 125,000 strikethrough150,000 points # Chase Sapphire Reserve® Credit Card
- `c_00002_18` [auto] reason="The chunk is primarily promotional copy encouraging users to shop for and finance a vehicle, with only light feature mention."
  $278,908 Find your next ride with Chase ## Find your next ride with Chase Shop for and finance an EV online using live inventory from the Chase network of dealers across the country. You can filter by price, model, features and more.
- `c_00150_08` [education_center] reason="It mainly promotes Shop and Earn with persuasive value language rather than providing detailed facts or instructions."
  ## The bottom line By simply accessing the Shop and Earn portal and navigating to a site where you’d like to make a purchase, you can earn rewards. As a savvy consumer and Chase cardmember, you may want to explore the wide range of perks that come wi
- `c_00093_03` [credit_cards] reason="The chunk is primarily promotional, emphasizing rewards and encouraging users to find a card."
  ### Same rewards You still earn rewards as you do today for purchases ## Don’t have a Chase credit card? Find a card that fits your needs.
- `c_00084_01` [personal_banking] reason="The chunk is primarily promotional value messaging highlighting benefits without detailed product terms or instructions."
  ## Power up your teen’s financial journey ### $0 Monthly Service Fee - Let your teen manage money with confidence with a $0 Monthly Service Fee. - Have peace of mind with no overdraft fees.
- `c_00012_01` [personal_banking] reason="It is a promotional value statement with no specific details beyond a generic ease-of-use claim."
  ### Autosave It's easy to save when linked to a Chase checking account.Same page link to footnote reference3
- `c_00007_71` [credit_cards] reason="The chunk is mostly promotional headings and offer language without substantive product details."
  $0† ### New Cardmember Offer ### Annual Fee ## Instacart Mastercard® ### New Cardmember Offer
- `c_00007_40` [credit_cards] reason="This is a promotional offer headline emphasizing bonus points to entice applications rather than provide detailed product information."
  ### New Cardmember Offer ## World of Hyatt Credit Card Earn up to 60,000 Bonus Points after qualifying purchases
- `c_00284_08` [investing] reason="This is promotional copy encouraging engagement without providing specific product facts or instructions."
  ## Be part of our community ### Investing insights ## Investing insights Stay in The Know by exploring articles and videos on market trends, research and financial planning.
- `c_00004_01` [credit_cards] reason="Promotional offer copy dominates, highlighting a signup bonus to encourage applying for the card."
  ### New Cardmember Offer Earn $750 cash back ## Ink Business Unlimited® Credit Card after you spend $6,000 on purchases in the first 3 months after account opening.

**informational, confidence=high** (2422 total)

- `c_00007_41` [credit_cards] reason="It gives specific reward rates and annual cardmember benefits rather than just promotional slogans."
  ### At A Glance Turn purchases into free nights by earning up to 9X total points per $1 at Hyatt hotels and resorts. Plus, get 1 free night and 5 tier qualifying nights credits toward status each year just for being a cardmember.
- `c_00038_08` [education_center] reason="It provides factual features and explanations of a traditional checking account."
  ### Traditional checking account - Common type of checking account in which you use checks and a debit or ATM card to withdraw money or make transactions, and they typically offer online bill pay options - Offered at most banks and credit unions - Ma
- `c_00098_06` [education_center] reason="It explains eligibility rules, exclusions, and conditions for using Pay Over Time on Amazon."
  ## Who can use Pay Over Time on Amazon? Chase Pay Over Time® at checkout is rolling out in phases and is currently only available on Amazon.com for select Chase cardmembers. When eligible, you’ll see the “Chase Pay Over Time®” option during checkout 
- `c_00105_06` [education_center] reason="It explains a specific credit-card option and its practical implications in factual bullet points."
  ## Consider adding your teen as an authorized user If your child isn’t ready to manage their own credit card, or doesn’t meet the age requirements, adding them as an authorized user can be a helpful alternative. - Shared access: As the primary accoun
- `c_00257_01` [education_center] reason="It explains what credit card rewards are, how they are earned and redeemed, and includes practical details."
  ## What are credit card rewards? Credit card rewards may be earned by spending on your card. Through sign-up bonuses, also known as new cardmember bonuses, and ongoing benefits, you can save up your rewards over time and eventually redeem them for a 
- `c_00007_18` [credit_cards] reason="The chunk provides specific product terms: the APR range and annual fee amount."
  ### APR 19.24%-27.74% variable APR.† ### Annual Fee $229 applied to first billing statement.†
- `c_00292_21` [education_center] reason="It explains specific reasons and benefits of choosing a 15-year mortgage versus a 30-year mortgage."
  ### Why do some people choose a 15-year mortgage instead of a 30-year? Those who take on a 15-year mortgage might do so because they want the financial independence that can come with owning a home sooner. They may also want to save on interest over 
- `c_00091_03` [personal_banking] reason="It provides a specific factual detail about ATM and branch access rather than mainly promotional language."
  ### Access to more than 14,000 ATMs and 5,000 branches Whether you need to visit a branch or an ATM, you can access your money when you need it.
- `c_00286_14` [investing] reason="It explains specific advantages, drawbacks, access, insurance, rates, and possible fees of savings accounts."
  ### Pros and cons of savings accounts Savings accounts remain one of the most common deposit account options, offering security and flexibility for everyday saving. The advantages of savings accounts are numerous: They are often easy to open, are wid
- `c_00206_01` [education_center] reason="It directly answers a product-usage question and provides specific details about rewards ranges."
  ## Can I use my business credit card to buy office supplies? Yes, you can use a business credit card to buy office supplies. Business credit cards could be a great opportunity for you to earn cash back rewards on office supplies and other business-re

*These samples are the primary signal that the classifier from step 1.7 is calibrated correctly.*

## Samples

### 5 random pages per stratum

**education_center**

| page_id | url | title | tokens | chunks |
|---------|-----|-------|-------:|-------:|
| p_00101 | https://www.chase.com/personal/credit-cards/education/basics/cash-back-credit-ca | Breaking Down Cash Back Credit Cards From Chase | Chase | 1079 | 8 |
| p_00159 | https://www.chase.com/personal/credit-cards/education/basics/when-to-use-miles-o | When To Use Miles or Cash For Flights | Chase | 1203 | 10 |
| p_00195 | https://www.chase.com/personal/credit-cards/education/rewards-benefits | Credit Card Rewards and Benefits | Chase | 625 | 6 |
| p_00116 | https://www.chase.com/personal/credit-cards/education/basics/freedom-rise-credit | Freedom Rise Credit Limit Increase | Chase | 1229 | 9 |
| p_00252 | https://www.chase.com/personal/credit-cards/education/rewards-benefits/maximize- | How to Maximize Transferable Credit Card Rewards | Chase | 680 | 6 |

**credit_cards**

| page_id | url | title | tokens | chunks |
|---------|-----|-------|-------:|-------:|
| p_00003 | https://creditcards.chase.com/balance-transfer-credit-cards/slate | Chase Slate Credit Card | Chase.com | 1374 | 21 |
| p_00008 | https://creditcards.chase.com/rewards-credit-cards/sapphire/preferred | Chase Sapphire Preferred Credit Card | Chase.com | 1891 | 25 |
| p_00268 | https://www.chase.com/personal/credit-cards/freedom | Chase Freedom | Credit Cards | Chase.com | 575 | 13 |
| p_00009 | https://creditcards.chase.com/rewards-credit-cards/sapphire/reserve | Chase Sapphire Reserve Credit Card | Chase.com | 2688 | 42 |
| p_00272 | https://www.chase.com/personal/credit-cards/freedom/rise | Rise | Credit Cards | Chase.com | 2346 | 30 |

**personal_banking**

| page_id | url | title | tokens | chunks |
|---------|-----|-------|-------:|-------:|
| p_00023 | https://www.chase.com/digital/mobile-banking | Mobile banking features with Chase Mobile® App | Chase | 1040 | 16 |
| p_00014 | https://personal.chase.com/personal/secure-banking | Chase Secure Banking | Checking Account With No Overdraft Fe | 2379 | 3 |
| p_00017 | https://www.chase.com/content/chase-ux/en/personal/checking/chasepayin4 | Chase Pay In 4℠ | Split Purchases into 4 Equal Payments | 326 | 7 |
| p_00275 | https://www.chase.com/personal/fees/high-school-checking | Chase High School Checking℠ | Understanding Savings and Chec | 451 | 2 |
| p_00080 | https://www.chase.com/personal/checking/chasepayin4 | Chase Pay In 4℠ | Split Purchases into 4 Equal Payments | 260 | 4 |

**mortgage**

| page_id | url | title | tokens | chunks |
|---------|-----|-------|-------:|-------:|
| p_00288 | https://www.chase.com/personal/mortgage/affordablelending | Affordable low down payment mortgage options | Chase.com | 1232 | 24 |
| p_00301 | https://www.chase.com/personal/mortgage/refinance/equity | Home Equity Line of Credit (HELOC) & Cash-Out Refinance | Ch | 1452 | 13 |
| p_00289 | https://www.chase.com/personal/mortgage/education/financing-a-home/how-mortgage- | Mortgage Calculator | Chase | 709 | 8 |
| p_00300 | https://www.chase.com/personal/mortgage/mortgage-purchase/first-time-homebuyer/m | Mortgage Loan Options for Home Buyers | Chase | 782 | 15 |
| p_00299 | https://www.chase.com/personal/mortgage/mortgage-purchase/first-time-homebuyer | First-Time Home Buyer: Information & Resources | Chase | 678 | 18 |

**auto**

| page_id | url | title | tokens | chunks |
|---------|-----|-------|-------:|-------:|
| p_00002 | https://autofinance.chase.com/electric-vehicles/explore-vehicles | Chase Auto EV Financing | Chase | 1035 | 20 |
| p_00001 | https://autofinance.chase.com/auto-finance/auto-loans | Chase Auto | Shop for a car | dealer inventory | Chase.com | 861 | 16 |

**investing**

| page_id | url | title | tokens | chunks |
|---------|-----|-------|-------:|-------:|
| p_00284 | https://www.chase.com/personal/investments/athlete | Athlete Center of Excellence: Take Control of Your Financial | 557 | 11 |
| p_00286 | https://www.chase.com/personal/investments/learning-and-insights/article/money-m | Money Market Accounts vs. Savings Accounts: What’s the Diffe | 2177 | 23 |

**customer_service**

| page_id | url | title | tokens | chunks |
|---------|-----|-------|-------:|-------:|
| p_00018 | https://www.chase.com/digital/customer-service/helpful-tips/online-banking/mobil | How To Send a Wire Transfer With Mobile Banking  | Chase | 279 | 4 |
| p_00305 | https://www.chase.com/personal/secure-banking/deposit | Secure Banking Benefits and Tools | Chase | 428 | 14 |

### 5 random chunks per stratum

**education_center**

- `c_00060_10` (p_00060, 70t): ## In summary These steps can help you both prepare and follow through with sending money overseas. It may expand your horizons a bit to discover how easily you can send these funds. Whether you’re he
- `c_00170_04` (p_00170, 226t): ## Things to look for when choosing your first credit card When deciding what credit cards to apply for, there are some features you may want to consider: - Low intro APR: A student or starter credit 
- `c_00203_03` (p_00203, 110t): ### Purchase categories Many Chase cards offer the ability to earn accelerated rewards in specific spending categories. For instance, your card might provide 3 points per dollar on dining, 5% cash bac
- `c_00127_07` (p_00127, 83t): ### 5. Be mindful of sign-up offers Many new cardmember offers provide the ability to earn bonus rewards. These offers typically allow you earn additional rewards if you reach a certain spending thres
- `c_00056_08` (p_00056, 57t): ### Bank account alerts Many banks allow customers to set up text or email alerts. These notify you if a large transaction is made on your accounts, or if your balance dips below a certain level. This

**credit_cards**

- `c_00004_02` (p_00004, 32t): ### At A Glance Unlimited 1.5% cash back rewards on every purchase made for your business – with this no annual fee credit card.
- `c_00269_10` (p_00269, 70t): ### Cell Phone Protection Get up to $800 per claim and $1,000 per 12-month period in cell phone protection against covered theft or damage for cell phones listed on your monthly cell phone bill when y
- `c_00006_24` (p_00006, 52t): ## Refer Friends if you already have a Chase Freedom Flex® Card! Earn up to $500 cash back per year. You can earn $50 cash back for each friend who gets any participating Chase Freedom® credit card. C
- `c_00272_22` (p_00272, 271t): ### Improving Credit A higher credit score lets banks know you're financially responsible. This makes it easier to get approved for a new credit card like Freedom Rise℠, which has no annual fee and le
- `c_00007_31` (p_00007, 54t): ### New Cardmember Offer 30,000 Bonus Points ## Marriott Bonvoy Bold® Credit Card Earn 30,000 Bonus Points after spending $1,000 on eligible purchases within 3 months of account opening with the Marri

**personal_banking**

- `c_00012_03` (p_00012, 67t): ### Explore other savings accounts ### Chase Premier SavingsSM Earn Premier relationship rates when you link the account to a Chase Premier Plus CheckingSM or Chase Sapphire® Banking account.Same page
- `c_00021_13` (p_00021, 72t): ### How do I use Paze? To use Paze, select it as a checkout option from participating online merchants’ sites. Activate Paze by accepting the terms of use for Paze and confirming your identity. Eligib
- `c_00012_14` (p_00012, 99t): ### The different types of savings accounts, explained ## What savings accounts does Chase offer? Our savings accounts have different features that may help you determine which account is best for you
- `c_00084_05` (p_00084, 136t): ## Get your teen started with an account Account must be opened in-branch with both the parent/guardian and student present. Schedule a meeting with a banker to open a checking account. Bring these re
- `c_00023_12` (p_00023, 91t): ### How secure is mobile banking? Mobile banking services typically employ numerous security measures to help keep your information safe. At Chase, for example, we use data encryption, secure logins a

**mortgage**

- `c_00300_08` (p_00300, 44t): ## Mortgages for higher-priced real estate ### Jumbo loan A jumbo loan is a mortgage for a more expensive property. The maximum amount for a jumbo loan at Chase is $9.5 million.
- `c_00299_14` (p_00299, 36t): ### How to start preapproval for a mortgage Preapproval can save every homebuyer a lot of time and show a seller you're in a financial position to purchase a home.
- `c_00288_20` (p_00288, 38t): ### A beginner's guide to FHA loans An FHA loan could make it easier to realize your dream of homeownership. Read our article to understand how they work and how to get one.
- `c_00299_15` (p_00299, 37t): ### How to lower your down payment While a hefty down payment can be helpful, there are many loans available that allow you to buy a home with no or a low down payment.
- `c_00299_13` (p_00299, 45t): ### Terms to know As you move through closing, you'll come across some financial terms related to your loan. This video breaks down those terms to give you a better understanding of how your loan and 

**auto**

- `c_00001_13` (p_00001, 24t): How old do I need to be to apply for financing? You must be 18 years old or older to apply.
- `c_00002_01` (p_00002, 31t): ## Featured EVs Chase Auto provides EV financing for customers who lease or purchase vehicles through select auto manufacturers. See electric vehicle options featured below.
- `c_00001_04` (p_00001, 29t): Not sure how much you can borrow? ## Not sure how much you can borrow? Get prequalified with no impact to your credit score.
- `c_00001_10` (p_00001, 24t): Can I finance my private party vehicle purchase with Chase? No, Chase doesn't offer financing for private party vehicle purchases.
- `c_00002_18` (p_00002, 53t): $278,908 Find your next ride with Chase ## Find your next ride with Chase Shop for and finance an EV online using live inventory from the Chase network of dealers across the country. You can filter by

**investing**

- `c_00286_04` (p_00286, 50t): ### What is fixed income? ## Get up to $1,000 When you open a J.P. Morgan Self-Directed Investing account, you get a trading experience that puts you in control and up to $1,000 in cash bonus.
- `c_00284_10` (p_00284, 21t): ### Follow us on LinkedIn Get the latest J.P. Morgan Wealth Management updates right in your feed.
- `c_00286_18` (p_00286, 39t): ### Do both types of accounts earn compound interest? Yes, most money market and savings accounts calculate interest on a compound basis – daily, monthly or quarterly – though the frequency can vary b
- `c_00286_13` (p_00286, 145t): ### Pros and cons of money market accounts Money market accounts can be appealing for those who want to earn higher interest while maintaining some level of access to their funds. There are several ad
- `c_00286_06` (p_00286, 37t): ## Key differences between money market accounts and savings accounts Use the following side-by-side comparison of the key features of money market accounts and savings accounts to better understand t

**customer_service**

- `c_00305_13` (p_00305, 20t): No overdraft fees We help you spend only what you have without worrying about overdraft fees.
- `c_00305_03` (p_00305, 26t): ### Spending Planner With Spending Planner, you can spot spending patterns and set budgets for different categories to help you stay on track.
- `c_00305_06` (p_00305, 24t): ### Works for more than paychecks Direct deposit can be used for government benefits, tax refunds, pensions and more.
- `c_00305_09` (p_00305, 38t): ### No fees to send or receive money With Zelle®, send and receive money with people and businesses you know and trust who have an eligible account at a participating U.S. bank.
- `c_00305_08` (p_00305, 36t): ## Chase Secure Banking customers told us they save an average of over $40 a month on fees after opening their account Pay no fees on most everyday transactions. Here’s how:

## Snapshot file inventory

| File | Rows | Size |
|------|-----:|-----:|
| pages.jsonl | 306 | 1.8 MB |
| chunks_raw.jsonl | 3169 | 2.4 MB |
| chunks_dedup.jsonl | 3092 | 2.8 MB |
| chunks.jsonl | 3089 | 3.6 MB |
| info_density_cache.jsonl | 3092 | 834.4 KB |
| boilerplate_review.md | (markdown) | 1.6 KB |
