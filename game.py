from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel

from checker_board import Color, GameState, Move

load_dotenv(Path(__file__).resolve().parent / ".env")

MODEL_SETTINGS = {"temperature": 0}
MAX_MOVE_RETRIES = 2

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

model = OpenAIChatModel(model_name="gpt-4o-mini", settings=MODEL_SETTINGS)

red_agent = Agent(
    model=model,
    system_prompt=f"{SYSTEM_PROMPT} You play as red (r/R).",
    output_type=Move,
    model_settings=MODEL_SETTINGS,
)
black_agent = Agent(
    model=model,
    system_prompt=f"{SYSTEM_PROMPT} You play as black (b/B).",
    output_type=Move,
    model_settings=MODEL_SETTINGS,
)


def run_agent_move(
    agent: Agent,
    game: GameState,
    message_history: list,
) -> tuple[list, Move]:
    prompt = game.board_to_string()
    for attempt in range(MAX_MOVE_RETRIES + 1):
        result = agent.run_sync(prompt, message_history=message_history)
        message_history = result.all_messages()
        try:
            game.make_move(result.output)
            return message_history, result.output
        except ValueError as exc:
            if attempt == MAX_MOVE_RETRIES:
                legal = game.get_valid_moves()
                if not legal:
                    raise
                game.make_move(legal[0])
                return message_history, legal[0]
            prompt = (
                f"{game.board_to_string()}\n\n"
                f"Your move {result.output} was illegal: {exc}\n"
                "Pick a different move from the legal moves list."
            )
    raise RuntimeError("unreachable")


class MoveResponse(BaseModel):
    from_row: int
    from_col: int
    to_row: int
    to_col: int


class GameStateResponse(BaseModel):
    squares: list[list[str]]
    turn: str
    move_count: int
    red_pieces: int
    black_pieces: int
    game_over: bool
    winner: str | None
    last_move: MoveResponse | None
    move_history: list[MoveResponse]
    legal_moves: list[MoveResponse]


class GameSession:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.game = GameState.initial()
        self.red_message_history: list = []
        self.black_message_history: list = []
        self.last_move: Move | None = None
        self.move_history: list[Move] = []

    def _move_to_response(self, move: Move) -> MoveResponse:
        return MoveResponse(
            from_row=move.from_sq.row,
            from_col=move.from_sq.col,
            to_row=move.to_sq.row,
            to_col=move.to_sq.col,
        )

    def _winner(self) -> str | None:
        if not self.game.is_game_over():
            return None
        if self.game.red_pieces > self.game.black_pieces:
            return "red"
        if self.game.black_pieces > self.game.red_pieces:
            return "black"
        return None

    def to_response(self) -> GameStateResponse:
        legal = self.game.get_valid_moves()
        return GameStateResponse(
            squares=[[piece.value for piece in row] for row in self.game.squares],
            turn=self.game.turn.value,
            move_count=self.game.move_count,
            red_pieces=self.game.red_pieces,
            black_pieces=self.game.black_pieces,
            game_over=self.game.is_game_over(),
            winner=self._winner(),
            last_move=self._move_to_response(self.last_move) if self.last_move else None,
            move_history=[self._move_to_response(m) for m in self.move_history],
            legal_moves=[self._move_to_response(m) for m in legal],
        )

    def step(self) -> GameStateResponse:
        if self.game.is_game_over():
            raise ValueError("Game is already over")

        if self.game.turn == Color.RED:
            self.red_message_history, move = run_agent_move(
                red_agent, self.game, self.red_message_history
            )
        else:
            self.black_message_history, move = run_agent_move(
                black_agent, self.game, self.black_message_history
            )

        self.last_move = move
        self.move_history.append(move)
        return self.to_response()


session = GameSession()

app = FastAPI(title="AI Checkers")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/state", response_model=GameStateResponse)
def get_state() -> GameStateResponse:
    return session.to_response()


@app.post("/api/reset", response_model=GameStateResponse)
def reset_game() -> GameStateResponse:
    session.reset()
    return session.to_response()


@app.post("/api/step", response_model=GameStateResponse)
def step_game() -> GameStateResponse:
    try:
        return session.step()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


frontend_dir = Path(__file__).resolve().parent / "frontend"


@app.get("/")
def serve_index() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")


@app.get("/index.css", include_in_schema=False)
def serve_css() -> FileResponse:
    return FileResponse(frontend_dir / "index.css", media_type="text/css")


@app.get("/index.js", include_in_schema=False)
def serve_js() -> FileResponse:
    return FileResponse(frontend_dir / "index.js", media_type="application/javascript")


@app.get("/favicon.ico", include_in_schema=False)
def serve_favicon() -> FileResponse:
    return FileResponse(frontend_dir / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("game:app", host="127.0.0.1", port=8001, reload=True)
