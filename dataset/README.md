---
license: other
license_name: gdelt-terms-of-use
license_link: https://www.gdeltproject.org/about.html#termsofuse
language:
  - en
  - multilingual
size_categories:
  - 10K<n<100K
task_categories:
  - text-classification
tags:
  - finance
  - sentiment-analysis
  - news
  - cryptocurrency
  - stocks
  - gdelt
pretty_name: Cheruvo Financial News Sentiment
---

# Cheruvo Financial News Sentiment

25,548 financial news headlines from around the world, matched to 51 stocks and
cryptocurrencies and scored from −1 to +1 from an investor's point of view.
Collected 13 May – 19 September 2026.

**Data from [The GDELT Project](https://www.gdeltproject.org/). Sentiment
scores computed by [Cheruvo](https://cheruvo.com).**

## Why this exists

I spent six weeks testing whether news sentiment predicts price. It does not:
it follows price. That is an assertion you can either believe or check, and a
claim nobody can check is worth very little. This is the file that lets you
check it, including the parts that make my own project look worse.

## What the dataset does not show

Read this before the columns, because it is the part that gets skipped.

Using the stable-period rows of this dataset, on Bitcoin, over 44 usable days
and 5,285 stories: **daily sentiment does not predict the next return at any
horizon tested.** At seven days the Spearman rank correlation is −0.001. Tested
with a permutation test and a block bootstrap over block lengths 2, 3, 5, 7 and
10, reporting the worst block length, with the significance threshold fixed at
0.017 (0.05 across three horizons) before looking at any result.

What does hold is the opposite direction: today's sentiment tracks the price
move of the **previous** two to seven days, rho ≈ 0.61, and that survives the
block bootstrap. On Ethereum the same test fails, but with 926 stories against
Bitcoin's 5,285 that is an underpowered replication rather than a failed one.

So if you are here to build a trading signal, this dataset is evidence against
the thing you are about to try, from the person who collected it. You are very
welcome to show me I got it wrong. That is the point of publishing it.

## Columns

| column | meaning |
|---|---|
| `ticker` | the symbol the story was matched to |
| `data_pubblicazione` | publication timestamp, ISO 8601 with timezone |
| `fonte` | `GDELT · <domain>` |
| `lingua` | source language as declared by GDELT (three-letter code), when present |
| `titolo` | the headline, as the outlet wrote it |
| `url` | link to the original article |
| `sentiment` | −1 to +1, four decimals |
| `origine_punteggio` | `llm` (Groq/Llama), `vader`, or `av` |
| `periodo_raccolta` | which collection regime the row belongs to — see below |

A story that names several tickers appears once per ticker.

## The three collection regimes, and why you must not ignore them

The rows are not homogeneous, and the differences are ours, not the market's.

| regime | dates | rows | rows/day |
|---|---|---|---|
| `pre-riforma` | 13 May – 6 Aug | 3,409 | ~40 |
| `filtro-asimmetrico` | 7 Aug – 15 Aug | 5,048 | ~561 |
| `stabile` | 16 Aug – 19 Sep | 17,091 | ~488 |

**Density.** There is a fourteenfold jump on 7 August. That is the day real
collection started; everything before it is a thin historical backfill. If you
plot story volume over the whole file you will see a wall in early August and
it means nothing about the world.

**Bias.** Until 16 August the relevance filter recognised profits in five
languages and had no word for losses in any of them. Measured at the time, the
stories it discarded averaged −0.095 against +0.084 for the ones it kept. The
sentiment series before that date is **shifted upward by construction.**

I kept those rows rather than deleting them quietly, because a reader who
cannot see what is missing cannot judge it. If you are measuring anything
about sentiment levels or their relationship to prices, use
`periodo_raccolta == "stabile"` and nothing else. Any result that spans 7 or 16
August measures my bug fixes.

## Coverage, including where it is bad

Ten best-covered tickers: BTC-USD (5,705), NVDA (2,577), AAPL (1,382), GOOGL
(1,230), ETH-USD (1,180), XRP-USD (1,150), META (1,053), AMZN (994), MSFT
(917), JPM (786).

Seventeen tickers have fewer than 100 rows across four months. A daily mean
over a handful of articles is an anecdote, and they are thin for **two
different reasons** that should not be confused.

**Not collected.** NFLX (7 rows) was never in the collection vocabulary. Its
handful of rows are rebound mentions: stories gathered for other tickers that
happen to name Netflix. It is not a statement about how much Netflix is in the
news.

**Collected, but the name is an ordinary word.** The rest were searched for and
came back thin, and for many of them the reason is the search term itself:

| ticker | term | rows |
|---|---|---|
| APT-USD | Aptos | 11 |
| NEAR-USD | NEAR | 11 |
| ARB-USD | Arbitrum | 14 |
| MATIC-USD | Polygon | 18 |
| STMMI.MI | STMicroelectronics | 23 |
| LTC-USD | Litecoin | 24 |
| ATOM-USD | Cosmos | 27 |
| DOT-USD | Polkadot | 27 |
| AVAX-USD | Avalanche | 33 |
| UNI-USD | Uniswap | 35 |
| SHIB-USD | Shiba | 48 |
| XLM-USD | Stellar | 64 |
| LINK-USD | Chainlink | 68 |
| SAN.MC | Santander | 80 |
| OP-USD | Optimism | 89 |
| AIR.PA | Airbus | 92 |

*NEAR*, *Cosmos*, *Avalanche*, *Stellar*, *Optimism*, *Polygon* and *Arbitrum*
are English words before they are assets. A headline reading "Fashion Styles
Spur Optimism" is not about a layer-2 network, and the relevance filter
correctly refuses it. So for those coins the honest sentence is not "there is
little news about this asset". It is **"we cannot reliably tell news about this
asset apart from news that uses this word"**, which is a different and more
useful warning.

The European listings (`STMMI.MI`, `SAN.MC`, `AIR.PA`) are thin for a third
reason: GDELT does not index enough European financial press for them.

## How the scores were produced

Headlines are scored by a large language model (Llama via Groq) prompted to
judge the story from an investor's point of view, with VADER as a fallback when
the model is unavailable. `origine_punteggio` records which produced each row.

The prompt was chosen by scoring 50 hand-labelled headlines against the
candidates rather than by reading the outputs and picking the nicer one.

Scores are opinions of a model, not ground truth. Syndicated rewrites of the
same story are deduplicated in the analysis but are present here as separate
rows, since which outlets picked a story up is itself information.

## Licence and attribution

The underlying news metadata comes from The GDELT Project, whose terms permit
unlimited use, including commercial, and explicitly permit redistribution:

> You may redistribute, rehost, republish, and mirror any of the GDELT datasets
> in any form. However, any use or redistribution of the data must include a
> citation to the GDELT Project and a link to this website.

That condition is binding on you too, so if you redistribute this dataset or
anything derived from it, carry the attribution line at the top of this card.

Only GDELT-sourced rows are included. Cheruvo also holds rows from the ECB,
ESMA, SEC EDGAR and Alpha Vantage; those are deliberately **excluded**, because
their licences differ. The ECB and ESMA require modifications to be declared,
and computing a sentiment score is a modification. Alpha Vantage granted
written permission for Cheruvo's own use, which is not a redistribution
licence. Bundling three licences under one attribution line would force you to
trust rather than check.

## Citation

```bibtex
@misc{cheruvo2026sentiment,
  title  = {Cheruvo Financial News Sentiment},
  author = {Santacaterina, Michele},
  year   = {2026},
  note   = {Data from The GDELT Project (https://www.gdeltproject.org/)},
  url    = {https://cheruvo.com}
}
```

The code that produced this file is `backend/esporta_dataset.py` in the Cheruvo
repository, and the test that decides whether a result may be reported is
`backend/verifica_segnale.py`.
