from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from checker_board import Color, GameState, Move

load_dotenv(Path(__file__).resolve().parent / ".env")

RESULTS_DIR = Path(__file__).resolve().parent / "results"

SYSTEM_PROMPT = (
    "You are a checkers player. You are given the board state, legal moves, and 1-ply "
    "lookahead showing opponent replies. Pick the best legal move and return it as "
    "from_sq/to_sq coordinates. Avoid moves where the opponent can capture unless it "
    "is the only option. Coordinates use row 0 at the top and col 0 at the left. "
    "Red (r/R) moves toward row 0 (up). Black (b/B) moves toward row 7 (down). "
    "Men move diagonally forward one square, or jump to capture. "
    "Kings (R/B) move diagonally in any direction and can also jump to capture. "
    "Captures are mandatory when available. Multi-jump chains must capture the maximum "
    "number of pieces — return the full chain as from_sq to the final to_sq."
)

MAX_MOVES_PER_GAME = 200
MAX_MOVE_RETRIES = 2
MODEL_SETTINGS = {"temperature": 0}

FirstPlayerMode = Literal["alternate", "red", "black"]


@dataclass
class RunResult:
    run_number: int
    winner: str
    winner_model: str
    red_model: str
    black_model: str
    first_player: str
    colors_swapped: bool
    move_count: int
    red_pieces: int
    black_pieces: int
    red_illegal_moves: int = 0
    black_illegal_moves: int = 0


@dataclass
class ExperimentResult:
    model_a: str
    model_b: str
    first_player_mode: FirstPlayerMode
    runs: list[RunResult] = field(default_factory=list)

    @property
    def red_wins(self) -> int:
        return sum(1 for run in self.runs if run.winner == "red")

    @property
    def black_wins(self) -> int:
        return sum(1 for run in self.runs if run.winner == "black")

    @property
    def draws(self) -> int:
        return sum(1 for run in self.runs if run.winner == "draw")

    @property
    def model_a_wins(self) -> int:
        return sum(1 for run in self.runs if run.winner_model == self.model_a)

    @property
    def model_b_wins(self) -> int:
        return sum(1 for run in self.runs if run.winner_model == self.model_b)

    @property
    def total_red_illegal(self) -> int:
        return sum(run.red_illegal_moves for run in self.runs)

    @property
    def total_black_illegal(self) -> int:
        return sum(run.black_illegal_moves for run in self.runs)

    def model_wins_as_red(self, model: str) -> int:
        return sum(
            1 for run in self.runs
            if run.winner == "red" and run.red_model == model
        )

    def model_wins_as_black(self, model: str) -> int:
        return sum(
            1 for run in self.runs
            if run.winner == "black" and run.black_model == model
        )

    def color_wins_when_first(self, color: str) -> int:
        return sum(
            1 for run in self.runs
            if run.winner == color and run.first_player == color
        )

    def color_wins_when_second(self, color: str) -> int:
        return sum(
            1 for run in self.runs
            if run.winner == color and run.first_player != color
        )


def create_agent(model_name: str, color: Color) -> Agent:
    side = "red (r/R)" if color == Color.RED else "black (b/B)"
    return Agent(
        model=OpenAIChatModel(model_name=model_name, settings=MODEL_SETTINGS),
        system_prompt=f"{SYSTEM_PROMPT} You play as {side}.",
        output_type=Move,
        model_settings=MODEL_SETTINGS,
    )


def run_agent_move(
    agent: Agent,
    game: GameState,
    message_history: list,
) -> tuple[list, bool]:
    """Run agent and apply move. Returns updated history and whether a fallback was used."""
    prompt = game.board_to_string()
    for attempt in range(MAX_MOVE_RETRIES + 1):
        result = agent.run_sync(prompt, message_history=message_history)
        message_history = result.all_messages()
        try:
            game.make_move(result.output)
            return message_history, attempt > 0
        except ValueError as exc:
            if attempt == MAX_MOVE_RETRIES:
                legal = game.get_valid_moves()
                if not legal:
                    raise
                game.make_move(legal[0])
                return message_history, True
            prompt = (
                f"{game.board_to_string()}\n\n"
                f"Your move {result.output} was illegal: {exc}\n"
                "Pick a different move from the legal moves list."
            )
    raise RuntimeError("unreachable")


def determine_winner(game: GameState) -> str:
    if game.red_pieces > game.black_pieces:
        return "red"
    if game.black_pieces > game.red_pieces:
        return "black"
    return "draw"


def resolve_first_player(mode: FirstPlayerMode, run_index: int) -> Color:
    if mode == "red":
        return Color.RED
    if mode == "black":
        return Color.BLACK
    return Color.BLACK if run_index % 2 == 0 else Color.RED


def play_game(
    red_agent: Agent,
    black_agent: Agent,
    *,
    red_model: str,
    black_model: str,
    first_player: Color,
    colors_swapped: bool,
    run_number: int,
) -> RunResult:
    game = GameState.initial()
    game.turn = first_player
    red_history: list = []
    black_history: list = []
    red_illegal = 0
    black_illegal = 0

    while not game.is_game_over() and game.move_count < MAX_MOVES_PER_GAME:
        if game.turn == Color.RED:
            red_history, used_fallback = run_agent_move(red_agent, game, red_history)
            if used_fallback:
                red_illegal += 1
        else:
            black_history, used_fallback = run_agent_move(black_agent, game, black_history)
            if used_fallback:
                black_illegal += 1

    winner = determine_winner(game)
    if winner == "red":
        winner_model = red_model
    elif winner == "black":
        winner_model = black_model
    else:
        winner_model = "draw"

    return RunResult(
        run_number=run_number,
        winner=winner,
        winner_model=winner_model,
        red_model=red_model,
        black_model=black_model,
        first_player=first_player.value,
        colors_swapped=colors_swapped,
        move_count=game.move_count,
        red_pieces=game.red_pieces,
        black_pieces=game.black_pieces,
        red_illegal_moves=red_illegal,
        black_illegal_moves=black_illegal,
    )


def run_experiment(
    model_a: str,
    model_b: str,
    runs: int,
    first_player_mode: FirstPlayerMode,
) -> ExperimentResult:
    agent_a_red = create_agent(model_a, Color.RED)
    agent_a_black = create_agent(model_a, Color.BLACK)
    agent_b_red = create_agent(model_b, Color.RED)
    agent_b_black = create_agent(model_b, Color.BLACK)

    result = ExperimentResult(
        model_a=model_a,
        model_b=model_b,
        first_player_mode=first_player_mode,
    )
    for index in range(1, runs + 1):
        colors_swapped = index % 2 == 0
        first_player = resolve_first_player(first_player_mode, index)

        if colors_swapped:
            red_agent, black_agent = agent_b_red, agent_a_black
            red_model, black_model = model_b, model_a
        else:
            red_agent, black_agent = agent_a_red, agent_b_black
            red_model, black_model = model_a, model_b

        print(
            f"Run {index}/{runs} — red={red_model}, black={black_model}, "
            f"first={first_player.value}, swapped={colors_swapped}"
        )
        run = play_game(
            red_agent,
            black_agent,
            red_model=red_model,
            black_model=black_model,
            first_player=first_player,
            colors_swapped=colors_swapped,
            run_number=index,
        )
        result.runs.append(run)
        print(
            f"  -> {run.winner} ({run.winner_model}) wins | "
            f"{run.move_count} moves | pieces red={run.red_pieces} black={run.black_pieces} | "
            f"illegal red={run.red_illegal_moves} black={run.black_illegal_moves}"
        )

    return result


def save_chart(result: ExperimentResult, output_path: Path) -> None:
    same_model = result.model_a == result.model_b
    if same_model:
        labels = [f"{result.model_a}\n(red wins)", f"{result.model_a}\n(black wins)", "Draw"]
        values = [result.red_wins, result.black_wins, result.draws]
    else:
        labels = [f"{result.model_a}\n(wins)", f"{result.model_b}\n(wins)", "Draw"]
        values = [result.model_a_wins, result.model_b_wins, result.draws]

    colors = ["#e74c3c", "#34495e", "#95a5a6"]
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, values, color=colors, edgecolor="white", linewidth=1.5)
    ax.set_ylabel("Games won")
    ax.set_title(
        f"Model results — {result.model_a} vs {result.model_b}\n"
        f"{len(result.runs)} runs | first player: {result.first_player_mode} | temperature=0",
        fontsize=11,
        fontweight="bold",
    )
    ax.set_ylim(0, max(values + [1]) * 1.15)

    for bar, value in zip(bars, values):
        if value > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.1,
                str(value),
                ha="center",
                va="bottom",
                fontweight="bold",
            )

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def save_color_chart(result: ExperimentResult, output_path: Path) -> None:
    labels = ["Red wins", "Black wins"]
    values = [result.red_wins, result.black_wins]
    first_values = [
        result.color_wins_when_first("red"),
        result.color_wins_when_first("black"),
    ]
    second_values = [
        result.color_wins_when_second("red"),
        result.color_wins_when_second("black"),
    ]

    x = range(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar([i - width / 2 for i in x], first_values, width, label="Won when moving first", color="#3498db")
    ax.bar([i + width / 2 for i in x], second_values, width, label="Won when moving second", color="#9b59b6")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Games won")
    ax.set_title(
        "Color bias analysis\n"
        f"Total: red {result.red_wins} — black {result.black_wins}",
        fontweight="bold",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def save_report(
    result: ExperimentResult,
    chart_path: Path,
    color_chart_path: Path,
    output_path: Path,
) -> None:
    total = len(result.runs)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    same_model = result.model_a == result.model_b

    lines = [
        "# Checkers AI Experiment Report",
        "",
        f"Generated: {timestamp}",
        "",
        "## Settings",
        "",
        "| Setting | Value |",
        "|---------|-------|",
        f"| Model A | `{result.model_a}` |",
        f"| Model B | `{result.model_b}` |",
        f"| Total runs | {total} |",
        f"| First player mode | `{result.first_player_mode}` |",
        "| Color swap | even runs swap red/black models |",
        "| Temperature | 0 |",
        "| Lookahead | 1-ply opponent replies in prompt |",
        "| Illegal moves | retry up to 2 times, then fallback |",
        "| Rules | forced captures, max-capture chains |",
        "",
        "## Summary",
        "",
    ]

    if same_model:
        lines.extend([
            "| Outcome | Count | % |",
            "|---------|------:|--:|",
            f"| Red wins | {result.red_wins} | {result.red_wins / total * 100:.1f}% |",
            f"| Black wins | {result.black_wins} | {result.black_wins / total * 100:.1f}% |",
            f"| Draws | {result.draws} | {result.draws / total * 100:.1f}% |",
        ])
    else:
        lines.extend([
            "| Outcome | Model | Count | % |",
            "|---------|-------|------:|--:|",
            f"| Model A wins | {result.model_a} | {result.model_a_wins} | {result.model_a_wins / total * 100:.1f}% |",
            f"| Model B wins | {result.model_b} | {result.model_b_wins} | {result.model_b_wins / total * 100:.1f}% |",
            f"| Draws | — | {result.draws} | {result.draws / total * 100:.1f}% |",
        ])

    lines.extend([
        "",
        f"| Red illegal-move fallbacks | {result.total_red_illegal} |",
        f"| Black illegal-move fallbacks | {result.total_black_illegal} |",
        "",
        "## Color bias analysis",
        "",
        "| Metric | Count |",
        "|--------|------:|",
        f"| Red wins (total) | {result.red_wins} |",
        f"| Black wins (total) | {result.black_wins} |",
        f"| Red wins when moving first | {result.color_wins_when_first('red')} |",
        f"| Red wins when moving second | {result.color_wins_when_second('red')} |",
        f"| Black wins when moving first | {result.color_wins_when_first('black')} |",
        f"| Black wins when moving second | {result.color_wins_when_second('black')} |",
        "",
        "## Wins by model and color",
        "",
        "| Model | Wins as red | Wins as black |",
        "|-------|------------:|--------------:|",
        f"| {result.model_a} | {result.model_wins_as_red(result.model_a)} | {result.model_wins_as_black(result.model_a)} |",
        f"| {result.model_b} | {result.model_wins_as_red(result.model_b)} | {result.model_wins_as_black(result.model_b)} |",
        "",
        "## Charts",
        "",
        f"![Model results]({chart_path.name})",
        "",
        f"![Color bias]({color_chart_path.name})",
        "",
        "## Per-run results",
        "",
        "| Run | Red model | Black model | First | Swapped | Winner | Moves | "
        "Red left | Black left | Red illegal | Black illegal |",
        "|----:|-----------|-------------|-------|---------|--------|------:|"
        "---------:|-----------:|-------------:|--------------:|",
    ])

    for run in result.runs:
        lines.append(
            f"| {run.run_number} | {run.red_model} | {run.black_model} | {run.first_player} | "
            f"{'yes' if run.colors_swapped else 'no'} | {run.winner} | {run.move_count} | "
            f"{run.red_pieces} | {run.black_pieces} | {run.red_illegal_moves} | "
            f"{run.black_illegal_moves} |"
        )

    output_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run checkers AI experiments")
    parser.add_argument("--runs", type=int, default=10, help="Number of games to simulate")
    parser.add_argument("--red-model", default="gpt-4o-mini", help="Model A")
    parser.add_argument("--black-model", default="gpt-4o-mini", help="Model B")
    parser.add_argument(
        "--first-player",
        choices=["alternate", "red", "black"],
        default="alternate",
        help="Who moves first: alternate each run, always red, or always black",
    )
    args = parser.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = RESULTS_DIR / f"{args.red_model}_vs_{args.black_model}_{stamp}".replace("/", "-")
    output_dir.mkdir()

    result = run_experiment(
        args.red_model,
        args.black_model,
        args.runs,
        args.first_player,
    )

    chart_path = output_dir / "results.png"
    color_chart_path = output_dir / "color_bias.png"
    report_path = output_dir / "report.md"
    save_chart(result, chart_path)
    save_color_chart(result, color_chart_path)
    save_report(result, chart_path, color_chart_path, report_path)

    print()
    print("Experiment complete")
    if result.model_a == result.model_b:
        print(f"  Red wins:   {result.red_wins}")
        print(f"  Black wins: {result.black_wins}")
    else:
        print(f"  {result.model_a} wins: {result.model_a_wins}")
        print(f"  {result.model_b} wins: {result.model_b_wins}")
    print(f"  Draws: {result.draws}")
    print(f"  Red wins when first:  {result.color_wins_when_first('red')}")
    print(f"  Red wins when second: {result.color_wins_when_second('red')}")
    print(f"  Black wins when first:  {result.color_wins_when_first('black')}")
    print(f"  Black wins when second: {result.color_wins_when_second('black')}")
    print(f"  Illegal fallbacks — red: {result.total_red_illegal}, black: {result.total_black_illegal}")
    print(f"  Chart:       {chart_path}")
    print(f"  Color chart: {color_chart_path}")
    print(f"  Report:      {report_path}")


if __name__ == "__main__":
    main()
