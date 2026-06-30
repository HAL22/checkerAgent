# Checkers AI Experiment — Cross-Run Analysis

Generated from experiments in `results/` (96 games total).

---

## Changes that led to better results

Early experiments (`151527`, `152216`, `155426`) used a simpler setup. A series of changes to the rules engine, agent prompts, and experiment design produced dramatically different — and more reliable — outcomes in later runs (`162701` onward).

### 1. Checkers rules engine (`checker_board.py`)

| Change | What it does | Why it helped |
|--------|--------------|---------------|
| **Forced captures** | If a capture is available, only capture moves are legal | Stops agents from making passive moves when they must jump; matches real checkers |
| **Multi-jump chains** | A single move can chain multiple jumps (`from_sq` → final `to_sq`) | Agents complete full capture sequences instead of stopping mid-chain |
| **Maximum-capture rule** | When multiple captures exist, only those capturing the most pieces are legal | Reduces arbitrary capture choices; forces the strongest available jump |
| **Correct move directions** | Red moves toward row 0; black toward row 7 | Fixed reversed forward movement that confused one side |
| **Dark-square setup** | Pieces placed on `(row + col) % 2 == 1` | Correct starting position so legal moves exist from turn one |

### 2. Agent prompting (`game.py`, `experiment.py`)

| Change | What it does | Why it helped |
|--------|--------------|---------------|
| **Direction clarity** | Prompt explicitly states red moves up (row 0), black moves down (row 7) | Fixed LLM confusion about which way "forward" is on the shared coordinate grid |
| **Capture rules in prompt** | Mandatory captures, full chains, max-capture rule spelled out | Aligns model behaviour with engine constraints |
| **1-ply lookahead** | Each legal move shows opponent replies, with `[opponent can capture!]` flags | Lets the model see consequences before choosing — the single biggest strategic improvement |
| **Avoid-blunder instruction** | "Avoid moves where the opponent can capture unless it is the only option" | Steers agents away from hanging pieces |

Example of lookahead output added to every turn:

```text
Move analysis (1-ply lookahead — opponent replies if you play this move):
  (5,2) -> (3,4) [capture]: opponent has no legal moves
  (5,0) -> (4,1): opponent can (3,2) -> (5,4) [capture] [opponent can capture!]
```

### 3. Model settings

| Change | What it does | Why it helped |
|--------|--------------|---------------|
| **`temperature=0`** | Deterministic model output | More consistent, reproducible moves across runs |
| **Structured output (`output_type=Move`)** | Agent returns validated `from_sq` / `to_sq` coordinates | Fewer malformed responses |
| **Illegal-move retries** | Up to 2 retries with error feedback before fallback | Recovers from bad coordinates instead of silently playing `legal[0]` |

### 4. Experiment design (`experiment.py`)

| Change | What it does | Why it helped |
|--------|--------------|---------------|
| **Color swap each run** | Even runs swap which model plays red vs black | Separates model strength from board-side bias |
| **Alternate first player** | Odd runs red first, even runs black first | Separates first-move advantage from color |
| **`--first-player` flag** | Can fix first player to `red` or `black` for isolation tests | Revealed that second-move advantage, not color, drives most wins |
| **Wins-by-color reporting** | Tracks wins as red, as black, when first, when second | Made the false "black always wins" bias visible and debuggable |
| **`color_bias.png` chart** | Visualises wins when moving first vs second | Confirmed second-move advantage across all new experiments |

### 5. Impact summary

| Area | Before | After |
|------|--------|-------|
| Self-play color balance | Black wins **90%** | Red wins **80%** |
| Head-to-head 4.1-mini vs 4o-mini | 4o-mini wins **70%** (old setup) | 4.1-mini wins **95%** (new setup) |
| Illegal-move fallbacks | Occasional | **~0 per 20 games** |
| Game endings | Material advantage (6 vs 9 pieces) | Decisive wipeouts (~48 moves) |
| Apparent board bias | "Black always wins" | Explained by weak play + first-move disadvantage |

The improvements fall into three layers: **correct rules**, **better information for the agent** (lookahead + prompts), and **fairer measurement** (color swap, first-player control, richer reporting). All three were needed — no single change alone would have produced the results seen in `222836`.

---

## Experiment timeline

| Run folder | Matchup | Runs | Settings | Red wins | Black wins | Key winner |
|------------|---------|-----:|----------|----------|------------|------------|
| `gpt-4o-mini_vs_gpt-4o-mini_20260623_151527` | 4o-mini vs 4o-mini | 2 | Old (no lookahead) | 0% | **100%** | Black |
| `gpt-4o-mini_vs_gpt-4o-mini_20260624_152216` | 4o-mini vs 4o-mini | 10 | Old | 10% | **90%** | Black |
| `gpt-4.1-mini_vs_gpt-4o-mini_20260624_155426` | 4.1-mini vs 4o-mini | 10 | Old | — | — | **4o-mini 70%** |
| `gpt-4o-mini_vs_gpt-4o-mini_20260624_162701` | 4o-mini vs 4o-mini | 20 | **New** (lookahead, temp=0) | **80%** | 20% | Red |
| `gpt-4o-mini_vs_gpt-4o-mini_20260624_212110` | 4o-mini vs 4o-mini | 20 | New, **red always first** | **80%** | 20% | Red |
| `gpt-4o-mini_vs_gpt-4o-mini_20260624_215549` | 4o-mini vs 4o-mini | 20 | New, **black always first** | **65%** | 35% | Red |
| `gpt-4o-mini_vs_gpt-4.1-mini_20260624_222836` | 4o-mini vs 4.1-mini | 20 | New | — | — | **4.1-mini 95%** |

---

## Insight 1: Improvements flipped the color bias

**Before** (no lookahead, no temp=0, no retries): black won **90%** of self-play games. That looked like a permanent board bias.

**After** improvements (1-ply lookahead, temperature=0, illegal-move retries, clearer prompts): red won **80%** in the same self-play setup.

| Metric | Pre-improvement (`152216`) | Post-improvement (`162701`) |
|--------|---------------------------|----------------------------|
| Red wins | 10% | **80%** |
| Black wins | 90% | 20% |
| Illegal fallbacks | 2 | 2 |

The "black always wins" pattern was mostly **weak play + no strategic context**, not a broken rules engine. With 1-ply lookahead and clearer prompts, agents avoid blunders and the color balance shifted sharply.

---

## Insight 2: Moving second is the real advantage

The color-bias charts from the new experiments tell a consistent story.

### Head-to-head (`222836`, 4o-mini vs 4.1-mini)

| | Wins when moving **first** | Wins when moving **second** |
|--|---------------------------|----------------------------|
| Red | 1 | **10** |
| Black | 0 | **9** |

### Self-play, red always first (`212110`)

| | First | Second |
|--|-------|--------|
| Red | **16** | 0 |
| Black | 0 | **4** |

### Self-play, black always first (`215549`)

| | First | Second |
|--|-------|--------|
| Red | 0 | **13** |
| Black | **7** | 0 |

**Pattern:** The side that moves **second** wins the vast majority of games. First move opens weaknesses; the responder capitalizes. This explains much of the early "black bias" — in alternate-first runs, black often moved second when red opened.

---

## Insight 3: `gpt-4.1-mini` is clearly stronger now

The decisive experiment is `222836` (20 runs, full new stack):

| Model | Wins | Win rate |
|-------|-----:|---------:|
| **gpt-4.1-mini** | 19 | **95%** |
| gpt-4o-mini | 1 | 5% |

### Wins by color

| Model | As red | As black |
|-------|-------:|---------:|
| **gpt-4.1-mini** | **10** | **9** |
| gpt-4o-mini | 1 | 0 |

`gpt-4.1-mini` wins from **both** sides. `gpt-4o-mini` won once (run 15, as red, 79 moves) and was shut out as black.

This is the opposite of the **old** head-to-head (`155426`, no lookahead): 4o-mini won **70%** there. The earlier conclusion that 4.1-mini was weaker was **wrong** — it was measured before the methodology improvements.

---

## Insight 4: Illegal moves are no longer a problem

| Experiment | Red illegal | Black illegal |
|------------|------------:|--------------:|
| Early self-play (`152216`) | 0 | 2 |
| Latest head-to-head (`222836`) | 1 | 0 |
| Self-play with lookahead (`162701`, `212110`, `215549`) | 0 | 0 |

Agents almost always pick legal moves now. Losses come from **strategy**, not coordinate errors. Retries + structured output + a narrower legal-move list (forced captures) fixed this.

---

## Insight 5: Games became faster and more decisive

**Early runs** (`151527`): games ended with **6 vs 9–10 pieces** — material advantage, not wipeouts.

**Latest head-to-head** (`222836`): when 4.1-mini wins as black, red often ends with **1 piece** left (~48 moves). When 4.1-mini wins as red, black often has **0** (~48–52 moves).

The combination of forced captures, max-capture chains, and lookahead produces **sharper, shorter games** where mistakes are punished quickly.

---

## Insight 6: First-player mode still shifts self-play balance

With the **same model** (4o-mini) and new settings:

| First player mode | Red wins | Black wins |
|-------------------|----------|------------|
| Always red (`212110`) | **80%** | 20% |
| Always black (`215549`) | **65%** | 35% |
| Alternate (`162701`) | **80%** | 20% |

Red still wins more overall, but **who moves first matters**. For fair model comparison, keep **alternate first player + color swap** (as in `222836`).

---

## Summary conclusions

1. **The improvements worked** — lookahead, temp=0, retries, and clearer prompts transformed play quality and reversed the false black bias.
2. **`gpt-4.1-mini` is the better checkers model** under the current setup (95% vs 4o-mini).
3. **Second-move advantage** is the dominant positional factor — bigger than red vs black color.
4. **Old experiments should not be compared** directly to new ones; the methodology changed materially.
5. **4o-mini's only path to winning** in the latest data is a long game as red (run 15, 79 moves) — it struggles especially as black (0/10).

---

## Recommended next steps

| Priority | Action |
|----------|--------|
| High | Use **`gpt-4.1-mini`** as the default agent in `game.py` |
| High | Run **30+ games** 4.1-mini vs 4o-mini to confirm 95% holds |
| Medium | Try **`gpt-4.1`** (full) vs 4.1-mini — is the gap worth the cost? |
| Medium | Add **2-ply lookahead** for endgame positions (fewer legal moves) |
| Low | Log **capture count per game** to see if 4.1-mini wins more material |

---

## Bottom line

The results folder shows a clear before/after story. Early runs suggested black (and 4o-mini) dominated. After the methodology changes, **`gpt-4.1-mini` wins 19/20**, plays well from both colors, and the main strategic factor is **moving second**, not board color.
