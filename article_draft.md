# Let Them Play Checkers

*Can large language models play a game of checkers? What happens when you pit two AI agents against each other — and how do you even measure who's winning?*

---

## 1. Why I built this

I wanted a practical way to learn **Pydantic AI** — how agents work, how structured outputs fit in, and what it actually feels like to wire an LLM into a loop that does something repeatable.

Checkers felt like the right testbed: the rules are simple enough to encode in Python, but the game still demands lookahead, forced captures, and multi-jump chains. The question I cared about wasn't "can AI beat a human at checkers" — it was narrower and more interesting:

> **Can generative models, given a board and a list of legal moves, pick reasonable ones? And can we measure that reliably?**

That led to a small project with three parts:

- **`checker_board.py`** — a Pydantic-backed rules engine (board state, legal moves, captures)
- **`game.py`** — a FastAPI backend with two agents playing step-by-step, plus a frontend to watch
- **`experiment.py`** — a batch runner that plays *n* games, keeps score, and writes charts and reports

Along the way, the experiment taught me more about **how to evaluate agents** than about checkers itself.

---

## 2. How the experiment works

### The agent loop

Each turn, an agent receives a text description of the board, a list of legal moves, and a 1-ply analysis of what the opponent could do in reply. It must return a structured `Move`:

```python
class Coord(BaseModel):
    row: int = Field(ge=0, le=7)
    col: int = Field(ge=0, le=7)

class Move(BaseModel):
    from_sq: Coord
    to_sq: Coord
```

The agent is created with Pydantic AI's `output_type=Move`, so the model's response is validated before it hits the board:

```python
red_agent = Agent(
    model=OpenAIChatModel(model_name="gpt-4.1-mini", settings={"temperature": 0}),
    system_prompt=f"{SYSTEM_PROMPT} You play as red (r/R).",
    output_type=Move,
    model_settings={"temperature": 0},
)
```

Each game loop is straightforward: read the board, ask the agent for a move, validate it, apply it, switch turns, repeat until someone wins.

### What the agent sees

The board is rendered as ASCII with row/column labels. Red moves toward row 0 (top); black toward row 7 (bottom). Legal moves are listed explicitly, and each move includes a **1-ply lookahead** — a simulation of the opponent's possible replies:

```text
Legal moves:
  (5,2) -> (3,4) [capture]
  (5,0) -> (4,1)

Move analysis (1-ply lookahead — opponent replies if you play this move):
  (5,2) -> (3,4) [capture]: opponent has no legal moves
  (5,0) -> (4,1): opponent can (3,2) -> (5,4) [capture] [opponent can capture!]
```

This lookahead is computed by copying the game state, applying the candidate move, and reading the opponent's legal moves — no LLM involved in the simulation itself:

```python
def _opponent_replies_after(self, move: Move) -> list[Move]:
    trial = self.model_copy(deep=True)
    trial.make_move(move)
    return trial.get_valid_moves()
```

### The rules engine

The engine enforces American checkers rules:

- **Forced captures** — if a jump is available, non-capture moves are illegal
- **Multi-jump chains** — a single `Move` goes from start square to the final landing square of a full chain
- **Maximum-capture rule** — when multiple captures exist, only those taking the most pieces are legal

```python
def get_valid_moves(self, color: Color | None = None) -> list[Move]:
    # ... collect captures and simple moves ...
    if captures:
        max_captures = max(self.capture_count(move) for move in captures)
        return [move for move in captures if self.capture_count(move) == max_captures]
    return simple
```

The game engine validates every move. If the agent returns something illegal, it gets up to two retries with feedback before falling back to the first legal move.

### Running experiments

```bash
python experiment.py --runs 20 --red-model gpt-4o-mini --black-model gpt-4.1-mini
```

Each experiment:

1. Plays *n* full games between two models
2. **Swaps colors** on even runs (so model A isn't always red)
3. **Alternates first player** (odd runs red first, even runs black first)
4. Writes `report.md`, `results.png`, and `color_bias.png` to `results/`

For isolation tests, you can fix who moves first:

```bash
python experiment.py --runs 20 --first-player red    # always red opens
python experiment.py --runs 20 --first-player black  # always black opens
```

### Watching it live

The FastAPI backend (`game.py`) serves a frontend at `http://127.0.0.1:8001`. You can step through moves one at a time or auto-play and watch the board update. Same agents, same rules — just visualised instead of batched.

---

## 3. Results

Over **96 games** across seven experiment runs, a clear before/after story emerged.

### Early runs (broken methodology)

| Experiment | Setup | Result |
|------------|-------|--------|
| 4o-mini self-play (2 runs) | No lookahead, no temp=0 | Black wins **100%** |
| 4o-mini self-play (10 runs) | Forced captures only | Black wins **90%** |
| 4.1-mini vs 4o-mini (10 runs) | Old setup | **4o-mini wins 70%** |

At this point it looked like black had a permanent advantage, and `gpt-4.1-mini` was the weaker model. Both conclusions turned out to be wrong.

### After improvements (lookahead, temp=0, retries, fairer design)

| Experiment | Setup | Result |
|------------|-------|--------|
| 4o-mini self-play (20 runs) | Full new stack | Red wins **80%** |
| 4o-mini self-play, red always first (20 runs) | Isolation test | Red wins **80%** |
| 4o-mini self-play, black always first (20 runs) | Isolation test | Red wins **65%** |
| **4.1-mini vs 4o-mini (20 runs)** | Full new stack | **4.1-mini wins 95%** |

The headline result from the final head-to-head:

| Model | Wins | As red | As black |
|-------|-----:|-------:|---------:|
| **gpt-4.1-mini** | **19 / 20** | 10 | 9 |
| gpt-4o-mini | 1 / 20 | 1 | 0 |

`gpt-4.1-mini` won from both colors. `gpt-4o-mini` won once — a 79-move game as red — and was shut out as black entirely.

Illegal-move fallbacks dropped to roughly **zero per 20 games**. Games became shorter and more decisive (~48 moves vs early ~75-move material endings).

---

## 4. Discussion

### The second move wins — not black

The most surprising finding wasn't about models at all. It was about **turn order**.

In the final head-to-head experiment:

| | Wins when moving **first** | Wins when moving **second** |
|--|---------------------------|----------------------------|
| Red | 1 | **10** |
| Black | 0 | **9** |

Across every new experiment, the side moving **second** won the vast majority of games. The first player opens the game; the second player responds to a position that already has a weakness in it.

This explains the early "black always wins" result. In alternate-first runs, black often moved second when red opened. It looked like a color bias on the board. It was really a **first-move disadvantage** combined with weak play from agents that couldn't see consequences.

### Why the better model performs better

Under the improved setup, `gpt-4.1-mini` didn't just win more — it won **from both sides** (10 as red, 9 as black). `gpt-4o-mini` went 1–0 split by color.

The likely reasons:

1. **Better instruction following** — picking from a legal-move list with capture annotations sounds easy, but it requires matching coordinates precisely and respecting chain rules. Structured output + retries help, but the model still has to choose *which* legal move.

2. **Using the lookahead** — the prompt includes opponent replies for every candidate move. A stronger model is more likely to avoid lines tagged `[opponent can capture!]`. Weaker models still pick those moves.

3. **Long-horizon consistency** — checkers games run 40–80 moves. Small mistakes compound. A model that blunders once in the opening gives the opponent a line that forced captures then exploit.

The old experiment had 4.1-mini losing 70% to 4o-mini. That was measured **before** lookahead and fairer design. Methodology matters as much as model choice.

### Why we filter to capture moves — and why the model couldn't do it alone

Early on, legal moves included both quiet steps and captures. The model frequently chose a passive move when a capture was available — a basic rules violation in real checkers.

We tried solving this with prompt instructions alone ("captures are mandatory"). It helped, but not enough. Agents still drifted toward safe-looking non-capture moves, especially when the capture line looked tactically unclear.

So we moved the rule into the **engine**:

```python
if captures:
    max_captures = max(self.capture_count(move) for move in captures)
    return [move for move in captures if self.capture_count(move) == max_captures]
    # simple (non-capture) moves are never returned when captures exist
```

**Why couldn't the model pick captures from a mixed list?**

Several reasons, none of which are really about checkers:

- **The list doesn't explain consequences.** A capture at `(5,2) -> (3,4)` and a quiet move at `(5,0) -> (4,1)` look like equally valid coordinate pairs. Without lookahead, there's no signal that one is forced by the rules and the other hangs a piece.

- **LLMs don't reliably enforce game rules.** They approximate. "Captures are mandatory" is a soft constraint in a prompt; `if captures: return captures` is a hard constraint in code. For any rule that must never be broken, the engine should own it.

- **Filtering narrows the decision space.** Once only captures are legal, the model chooses *which* capture (and with max-capture enforced, often there's only one). That's a much easier task than "figure out the rules and then pick the best move."

This is a general lesson for agent design: **give the model decisions, not rule enforcement.**

### Other insights

**Apparent board bias was a measurement artifact.** Black winning 90% of early games wasn't a bug in the board setup. It was weak agents plus second-move advantage plus no lookahead. Fix the information available to the agent, and the "bias" flips entirely.

**Temperature matters for experiments.** Setting `temperature=0` made runs reproducible. When you're comparing models across 20 games, you want variance from *play*, not from sampling noise.

**Games got sharper.** Forced captures + max-capture + lookahead produced wipeouts in ~48 moves instead of slow material grinds ending 6–9. Mistakes get punished immediately, which makes differences between models visible faster.

**Small samples mislead.** Two games where black wins both feels conclusive. It isn't. Ten games with the wrong setup reversed the model ranking. Twenty games with the right setup made the ranking clear. For agent benchmarks, design the experiment before trusting the numbers.

---

## 5. Closing remarks

This project started as a way to learn Pydantic AI. It ended up as a lesson in **how to build and evaluate agents** — not just how to call an API.

The takeaways I'd carry to the next project:

1. **Own the rules in code.** Don't ask the LLM to enforce captures, legality, or turn order. Give it a curated action space.
2. **Give the model context, not just state.** The single biggest improvement was 1-ply lookahead — showing consequences, not just positions.
3. **Design experiments to isolate variables.** Color swap, first-player alternation, and wins-by-color reporting turned a confusing "black always wins" story into a clear "second move wins" finding.
4. **Compare models under the same information.** A model that looks weaker in one setup can dominate in another. The setup is part of the benchmark.
5. **Structured output + retries + temperature=0** are table stakes for any agent that acts in a loop.

Can generative AI play checkers? Yes — well enough to finish games, respect forced captures (with engine help), and show measurable skill differences between models. Can it play checkers *well*? Not by human standards. There's no deep search, no endgame tablebase, no multi-move planning. It's one ply of lookahead and a prayer.

But for learning how agents work — how to prompt them, constrain them, measure them, and debug them when the numbers don't make sense — checkers was enough.

---

*Full experiment data and analysis: `results/EXPERIMENT_ANALYSIS.md`*

*Run your own:*

```bash
python experiment.py --runs 20 --red-model gpt-4o-mini --black-model gpt-4.1-mini
python game.py  # then open http://127.0.0.1:8001
```
