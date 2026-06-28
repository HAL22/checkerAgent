from enum import Enum

from pydantic import BaseModel, Field


class Coord(BaseModel):
    row: int = Field(ge=0, le=7)
    col: int = Field(ge=0, le=7)


class Move(BaseModel):
    from_sq: Coord
    to_sq: Coord


class Color(str, Enum):
    RED = "red"
    BLACK = "black"


class PieceKind(str, Enum):
    EMPTY = "."
    RED_MAN = "r"
    RED_KING = "R"
    BLACK_MAN = "b"
    BLACK_KING = "B"


RED_PIECES = {PieceKind.RED_MAN, PieceKind.RED_KING}
BLACK_PIECES = {PieceKind.BLACK_MAN, PieceKind.BLACK_KING}
KINGS = {PieceKind.RED_KING, PieceKind.BLACK_KING}


class GameState(BaseModel):
    squares: list[list[PieceKind]]
    turn: Color = Color.RED
    move_count: int = 0
    red_pieces: int = 12
    black_pieces: int = 12

    @classmethod
    def initial(cls) -> "GameState":
        state = cls(squares=[[PieceKind.EMPTY for _ in range(8)] for _ in range(8)])
        state._create_board()
        return state

    def _create_board(self) -> None:
        for row in range(8):
            for col in range(8):
                if (row + col) % 2 == 1:
                    if row < 3:
                        self.squares[row][col] = PieceKind.BLACK_MAN
                    elif row > 4:
                        self.squares[row][col] = PieceKind.RED_MAN

    def piece_at(self, row: int, col: int) -> PieceKind | None:
        if not (0 <= row < 8 and 0 <= col < 8):
            return None
        return self.squares[row][col]

    def _is_red(self, piece: PieceKind) -> bool:
        return piece in RED_PIECES

    def _opponents(self, piece: PieceKind) -> set[PieceKind]:
        return BLACK_PIECES if self._is_red(piece) else RED_PIECES

    def _move_directions(self, piece: PieceKind, *, for_capture: bool) -> list[tuple[int, int]]:
        directions = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        if piece in KINGS:
            return directions
        forward = -1 if self._is_red(piece) else 1
        return [(dr, dc) for dr, dc in directions if dr == forward or for_capture]

    def capture_count(self, move: Move) -> int:
        row_dist = abs(move.to_sq.row - move.from_sq.row)
        col_dist = abs(move.to_sq.col - move.from_sq.col)
        if row_dist != col_dist or row_dist < 2:
            return 0
        return row_dist // 2

    def _capture_sequences_from(self, coord: Coord, piece: PieceKind) -> list[Move]:
        opponents = self._opponents(piece)
        jump_dirs = self._move_directions(piece, for_capture=True)
        sequences: list[Move] = []

        def dfs(current: Coord, captured: set[tuple[int, int]]) -> None:
            extended = False
            for dr, dc in jump_dirs:
                mid_row, mid_col = current.row + dr, current.col + dc
                land_row, land_col = current.row + 2 * dr, current.col + 2 * dc
                if (mid_row, mid_col) in captured:
                    continue
                jumped = self.piece_at(mid_row, mid_col)
                if jumped in opponents and self.piece_at(land_row, land_col) == PieceKind.EMPTY:
                    extended = True
                    dfs(Coord(row=land_row, col=land_col), captured | {(mid_row, mid_col)})
            if not extended and (current.row, current.col) != (coord.row, coord.col):
                sequences.append(Move(from_sq=coord, to_sq=current))

        dfs(coord, set())
        return sequences

    def _simple_moves_from(self, coord: Coord, piece: PieceKind) -> list[Move]:
        moves: list[Move] = []
        for dr, dc in self._move_directions(piece, for_capture=False):
            step_row, step_col = coord.row + dr, coord.col + dc
            if self.piece_at(step_row, step_col) == PieceKind.EMPTY:
                moves.append(Move(from_sq=coord, to_sq=Coord(row=step_row, col=step_col)))
        return moves

    def valid_move_from_coord(self, coord: Coord, piece: PieceKind) -> list[Move]:
        if piece == PieceKind.EMPTY:
            return []
        return self._capture_sequences_from(coord, piece) + self._simple_moves_from(coord, piece)

    def get_valid_moves(self, color: Color | None = None) -> list[Move]:
        color = color or self.turn
        pieces = RED_PIECES if color == Color.RED else BLACK_PIECES
        captures: list[Move] = []
        simple: list[Move] = []

        for row in range(8):
            for col in range(8):
                piece = self.squares[row][col]
                if piece not in pieces:
                    continue
                coord = Coord(row=row, col=col)
                captures.extend(self._capture_sequences_from(coord, piece))
                simple.extend(self._simple_moves_from(coord, piece))

        if captures:
            max_captures = max(self.capture_count(move) for move in captures)
            return [move for move in captures if self.capture_count(move) == max_captures]
        return simple

    def _clear_captures_on_path(self, from_sq: Coord, to_sq: Coord) -> None:
        dr = to_sq.row - from_sq.row
        dc = to_sq.col - from_sq.col
        step_r = dr // abs(dr)
        step_c = dc // abs(dc)
        row, col = from_sq.row + step_r, from_sq.col + step_c
        while (row, col) != (to_sq.row, to_sq.col):
            captured = self.squares[row][col]
            if captured in RED_PIECES:
                self.red_pieces -= 1
            elif captured in BLACK_PIECES:
                self.black_pieces -= 1
            self.squares[row][col] = PieceKind.EMPTY
            row += step_r
            col += step_c

    def make_move(self, move: Move) -> None:
        legal_moves = self.get_valid_moves(self.turn)
        if move not in legal_moves:
            raise ValueError(f"Illegal move: {move}")

        from_sq = move.from_sq
        to_sq = move.to_sq
        piece = self.squares[from_sq.row][from_sq.col]
        self.squares[from_sq.row][from_sq.col] = PieceKind.EMPTY

        if self.capture_count(move) > 0:
            self._clear_captures_on_path(from_sq, to_sq)

        if piece == PieceKind.RED_MAN and to_sq.row == 0:
            piece = PieceKind.RED_KING
        elif piece == PieceKind.BLACK_MAN and to_sq.row == 7:
            piece = PieceKind.BLACK_KING

        self.squares[to_sq.row][to_sq.col] = piece
        self.turn = Color.BLACK if self.turn == Color.RED else Color.RED
        self.move_count += 1

    def is_game_over(self) -> bool:
        if self.red_pieces == 0 or self.black_pieces == 0:
            return True
        return not self.get_valid_moves(self.turn)

    def _format_move(self, move: Move) -> str:
        captures = self.capture_count(move)
        label = f"({move.from_sq.row},{move.from_sq.col}) -> ({move.to_sq.row},{move.to_sq.col})"
        if captures > 1:
            return f"{label} [chain x{captures}]"
        if captures == 1:
            return f"{label} [capture]"
        return label

    def _opponent_replies_after(self, move: Move) -> list[Move]:
        trial = self.model_copy(deep=True)
        trial.make_move(move)
        return trial.get_valid_moves()

    def _analyze_move(self, move: Move) -> str:
        replies = self._opponent_replies_after(move)
        if not replies:
            return f"{self._format_move(move)}: opponent has no legal moves"

        shown = replies[:5]
        parts = [self._format_move(reply) for reply in shown]
        suffix = f" (+{len(replies) - 5} more)" if len(replies) > 5 else ""
        captures = [r for r in replies if self.capture_count(r) > 0]
        tag = " [opponent can capture!]" if captures else ""
        return f"{self._format_move(move)}: opponent can {', '.join(parts)}{suffix}{tag}"

    def board_to_string(self, moves: list[Move] | None = None, *, include_analysis: bool = True) -> str:
        if moves is None:
            moves = self.get_valid_moves()

        lines = [
            "Checkers board (row 0 = top, col 0 at left):",
            "Red (r/R) moves toward row 0 (up). Black (b/B) moves toward row 7 (down).",
            "    " + "  ".join(str(c) for c in range(8)),
        ]
        for row, squares in enumerate(self.squares):
            lines.append(
                f"{row} | " + "  ".join(piece.value for piece in squares) + " |"
            )
        lines.extend([
            f"Turn: {self.turn.value} | Move #: {self.move_count}",
            f"Pieces remaining: red={self.red_pieces}, black={self.black_pieces}",
            "Rules: captures are mandatory; multi-jump chains must capture the maximum "
            "number of pieces; return the full chain as from_sq -> final to_sq.",
            "Legend: r/R=red, b/B=black, uppercase=king, .=empty",
            "Legal moves:",
        ])
        if moves:
            for move in moves:
                lines.append(f"  {self._format_move(move)}")
        else:
            lines.append("  (none)")

        if include_analysis and moves:
            lines.append("Move analysis (1-ply lookahead — opponent replies if you play this move):")
            for move in moves:
                lines.append(f"  {self._analyze_move(move)}")

        return "\n".join(lines)
