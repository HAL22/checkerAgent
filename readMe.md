Agents playing checkers

# Agents playing checkers

Two [Pydantic AI](https://ai.pydantic.dev/) agents play American checkers against each other. A Pydantic rules engine (`checker_board.py`) owns the board state and move validation; the agents only propose moves.

## Prerequisites

- Python 3.10+
- An OpenAI API key

## Setup

```bash
cd checkers
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-...
```

Both `game.py` and `experiment.py` load this file automatically.

## Run the web UI

Start the FastAPI server and open the board in your browser:

```bash
python game.py
```

Then visit [http://127.0.0.1:8001](http://127.0.0.1:8001).

The UI lets you:

- **Start Game** — reset the board
- **Next Move** — ask both agents to play one ply (red, then black if the game continues)
- **Auto Play** — step through moves automatically until someone wins
- **Reset** — clear the board without reloading the page

The default model in `game.py` is `gpt-4o-mini` with `temperature=0`. Change the model in `game.py` if you want a different player.

### API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/state` | Current board, turn, legal moves, move history |
| `POST` | `/api/reset` | Start a new game |
| `POST` | `/api/step` | Play one agent move for the side to move |

## Run experiments

`experiment.py` plays many games in batch, records wins/losses, and writes charts plus a markdown report under `results/`.

```bash
# Self-play: same model on both sides (default 10 games)
python experiment.py

# Head-to-head with more games
python experiment.py --runs 20 --red-model gpt-4.1-mini --black-model gpt-4o-mini

# Always let red move first (useful for isolating first-move effects)
python experiment.py --runs 20 --first-player red

# Always let black move first
python experiment.py --runs 20 --first-player black
```

### CLI options

| Flag | Default | Description |
|------|---------|-------------|
| `--runs` | `10` | Number of games to simulate |
| `--red-model` | `gpt-4o-mini` | Model playing red |
| `--black-model` | `gpt-4o-mini` | Model playing black |
| `--first-player` | `alternate` | `alternate`, `red`, or `black` |

Each run creates a timestamped folder under `results/`, for example:

```
results/gpt-4.1-mini_vs_gpt-4o-mini_20250630_143022/
  report.md        # summary table and per-game log
  results.png      # win/loss bar chart
  color_bias.png   # wins by color and move order
```

`results/` is gitignored; copy anything you want to keep elsewhere.

## Project layout

```
checker_board.py   # Rules engine: GameState, Move, legal moves, captures
game.py            # FastAPI backend + agent loop for the web UI
experiment.py      # Batch runner, charts, and reports
frontend/          # Static HTML/CSS/JS board UI
article_draft.md   # Long-form write-up of the project and findings
EXPERIMENT_ANALYSIS.md  # Notes across experiment runs
results/           # Experiment output (generated, not committed)
```

## Rules implemented

- 8×8 American checkers on dark squares
- Red moves toward row 0; black toward row 7
- Kings move and capture in all four diagonal directions
- Forced captures, multi-jump chains as a single move, and maximum-capture rule
- Agents receive the board, legal moves, and 1-ply lookahead hints; illegal proposals are retried, then fall back to the first legal move

## Further reading

- [`article_draft.md`](article_draft.md) — motivation, architecture, and experiment discussion
- [`EXPERIMENT_ANALYSIS.md`](EXPERIMENT_ANALYSIS.md) — cross-run analysis and model comparisons
