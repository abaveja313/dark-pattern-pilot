# Dark Patterns Study - Analysis Report

## Descriptive Statistics

| model                       | condition         |    mean |       sd |   median |   iqr |   n |
|:----------------------------|:------------------|--------:|---------:|---------:|------:|----:|
| anthropic/claude-haiku-4.5  | AVERAGE_CONSUMER  | 3.44444 | 0.881917 |        4 |     1 |   9 |
| anthropic/claude-haiku-4.5  | CONSUMER_ADVOCATE | 2.22222 | 0.440959 |        2 |     0 |   9 |
| anthropic/claude-opus-4.6   | AVERAGE_CONSUMER  | 3.66667 | 0.5      |        4 |     1 |   9 |
| anthropic/claude-opus-4.6   | CONSUMER_ADVOCATE | 2       | 0        |        2 |     0 |   9 |
| google/gemini-2.5-flash     | AVERAGE_CONSUMER  | 5       | 0        |        5 |     0 |   8 |
| google/gemini-2.5-flash     | CONSUMER_ADVOCATE | 2.33333 | 0.5      |        2 |     1 |   9 |
| google/gemini-3-pro-preview | AVERAGE_CONSUMER  | 5       | 0        |        5 |     0 |   9 |
| google/gemini-3-pro-preview | CONSUMER_ADVOCATE | 1.33333 | 0.5      |        1 |     1 |   9 |
| openai/gpt-4o-mini          | AVERAGE_CONSUMER  | 5       | 0        |        5 |     0 |   9 |
| openai/gpt-4o-mini          | CONSUMER_ADVOCATE | 3.88889 | 0.333333 |        4 |     0 |   9 |
| openai/gpt-5.2              | AVERAGE_CONSUMER  | 4.55556 | 0.527046 |        5 |     1 |   9 |
| openai/gpt-5.2              | CONSUMER_ADVOCATE | 2.55556 | 0.527046 |        3 |     1 |   9 |

## Between-Condition Tests

| model                       |   test_stat |     p_value |   effect_size_cohens_d |   effect_size_rank_biserial |   p_adjusted |
|:----------------------------|------------:|------------:|-----------------------:|----------------------------:|-------------:|
| anthropic/claude-haiku-4.5  |          69 | 0.00684563  |                1.753   |                   -0.703704 |  0.00684563  |
| anthropic/claude-opus-4.6   |          81 | 0.000111897 |                4.71405 |                   -1        |  0.000223794 |
| google/gemini-2.5-flash     |          72 | 0.000209924 |                7.30297 |                   -1        |  0.000314887 |
| google/gemini-3-pro-preview |          81 | 0.000111897 |               10.3709  |                   -1        |  0.000223794 |
| openai/gpt-4o-mini          |          81 | 7.03107e-05 |                4.71405 |                   -1        |  0.000223794 |
| openai/gpt-5.2              |          81 | 0.000265532 |                3.79473 |                   -1        |  0.000318639 |

## Effect Sizes (Cohen's d with 95% Bootstrap CI)

| model                       |   cohens_d |   ci_lower |   ci_upper |
|:----------------------------|-----------:|-----------:|-----------:|
| anthropic/claude-haiku-4.5  |    1.753   |   0.745356 |    5.33333 |
| anthropic/claude-opus-4.6   |    4.71405 |   0        |    8.01388 |
| google/gemini-2.5-flash     |    7.30297 |   6.35085  |   11.8673  |
| google/gemini-3-pro-preview |   10.3709  |   9.01135  |   16.4992  |
| openai/gpt-4o-mini          |    4.71405 |   0        |    4.71405 |
| openai/gpt-5.2              |    3.79473 |   3.29983  |    5.54348 |

## Dose-Response Trend Test

- Spearman rho = nan
- p-value = nan
- N = 0

## Anchoring Effect

| model                       |   mean_shift |   p_value |   effect_size |
|:----------------------------|-------------:|----------:|--------------:|
| anthropic/claude-haiku-4.5  |         2    |     0.5   |           1   |
| anthropic/claude-opus-4.6   |         1.5  |     0.5   |           1   |
| google/gemini-2.5-flash     |         0    |   nan     |         nan   |
| google/gemini-3-pro-preview |         0    |   nan     |         nan   |
| openai/gpt-4o-mini          |        -0.75 |     0.375 |           0.6 |
| openai/gpt-5.2              |         0    |   nan     |         nan   |

## Awareness-Action Gap

| model                       |   n_with_tactics |   n_gap |   gap_percentage |
|:----------------------------|-----------------:|--------:|-----------------:|
| anthropic/claude-haiku-4.5  |               18 |       6 |          33.3333 |
| anthropic/claude-opus-4.6   |               18 |       6 |          33.3333 |
| google/gemini-2.5-flash     |               17 |       8 |          47.0588 |
| google/gemini-3-pro-preview |               18 |       9 |          50      |
| openai/gpt-4o-mini          |               17 |      16 |          94.1176 |
| openai/gpt-5.2              |               18 |       9 |          50      |

## Provider Differences (Kruskal-Wallis)

- H statistic = 14.8160
- p-value = 0.0006

## Reasoning vs Fast Models

- U statistic = 1181.0000
- p-value = 0.1083
