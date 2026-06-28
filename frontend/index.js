const API = "/api";

const boardEl = document.getElementById("board");
const turnBadge = document.getElementById("turn-badge");
const redCount = document.getElementById("red-count");
const blackCount = document.getElementById("black-count");
const moveCount = document.getElementById("move-count");
const statusMessage = document.getElementById("status-message");
const moveHistoryEl = document.getElementById("move-history");
const btnStart = document.getElementById("btn-start");
const btnStep = document.getElementById("btn-step");
const btnAuto = document.getElementById("btn-auto");
const btnReset = document.getElementById("btn-reset");

let autoPlayTimer = null;
let currentState = null;

function pieceInfo(char) {
  if (char === "r") return { color: "red", king: false };
  if (char === "R") return { color: "red", king: true };
  if (char === "b") return { color: "black", king: false };
  if (char === "B") return { color: "black", king: true };
  return null;
}

function renderBoard(state) {
  boardEl.innerHTML = "";
  const last = state.last_move;

  for (let row = 0; row < 8; row++) {
    for (let col = 0; col < 8; col++) {
      const square = document.createElement("div");
      const isDark = (row + col) % 2 === 1;
      square.className = `square ${isDark ? "dark" : "light"}`;
      square.dataset.row = row;
      square.dataset.col = col;

      if (last) {
        if (last.from_row === row && last.from_col === col) {
          square.classList.add("highlight-from");
        }
        if (last.to_row === row && last.to_col === col) {
          square.classList.add("highlight-to");
        }
      }

      const label = document.createElement("span");
      label.className = "coord-label";
      label.textContent = `${row},${col}`;
      square.appendChild(label);

      const pieceChar = state.squares[row][col];
      const info = pieceInfo(pieceChar);
      if (info) {
        const piece = document.createElement("div");
        piece.className = `piece ${info.color}${info.king ? " king" : ""}`;
        square.appendChild(piece);
      }

      boardEl.appendChild(square);
    }
  }
}

function renderHistory(state) {
  moveHistoryEl.innerHTML = "";
  state.move_history.forEach((move, index) => {
    const li = document.createElement("li");
    const player = index % 2 === 0 ? "red" : "black";
    li.className = player;
    li.textContent = `${index + 1}. (${move.from_row},${move.from_col}) → (${move.to_row},${move.to_col})`;
    moveHistoryEl.appendChild(li);
  });
}

function renderState(state) {
  currentState = state;

  turnBadge.textContent = state.turn;
  turnBadge.className = `badge ${state.turn}`;

  redCount.textContent = `Red: ${state.red_pieces}`;
  blackCount.textContent = `Black: ${state.black_pieces}`;
  moveCount.textContent = `Move #${state.move_count}`;

  if (state.game_over) {
    statusMessage.className = "status-message winner";
    statusMessage.textContent = state.winner
      ? `${state.winner.charAt(0).toUpperCase() + state.winner.slice(1)} wins!`
      : "Game over — draw";
    stopAutoPlay();
    btnStep.disabled = true;
    btnAuto.disabled = true;
  } else if (state.move_count === 0) {
    statusMessage.className = "status-message";
    statusMessage.textContent = `${state.turn} to move`;
    btnStep.disabled = false;
    btnAuto.disabled = false;
  } else {
    statusMessage.className = "status-message";
    statusMessage.textContent = `${state.turn} to move`;
    btnStep.disabled = false;
    btnAuto.disabled = false;
  }

  renderBoard(state);
  renderHistory(state);
}

async function api(path, method = "GET") {
  const response = await fetch(`${API}${path}`, { method });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "Request failed");
  }
  return response.json();
}

async function startGame() {
  stopAutoPlay();
  btnStart.disabled = true;
  statusMessage.textContent = "Starting game…";
  try {
    const state = await api("/reset", "POST");
    renderState(state);
    btnStart.disabled = false;
  } catch (err) {
    statusMessage.textContent = err.message;
    btnStart.disabled = false;
  }
}

async function stepGame() {
  btnStep.disabled = true;
  statusMessage.textContent = "AI is thinking…";
  try {
    const state = await api("/step", "POST");
    renderState(state);
  } catch (err) {
    statusMessage.textContent = err.message;
    btnStep.disabled = !currentState?.game_over;
  }
}

function stopAutoPlay() {
  if (autoPlayTimer) {
    clearInterval(autoPlayTimer);
    autoPlayTimer = null;
  }
  btnAuto.textContent = "Auto Play";
}

function toggleAutoPlay() {
  if (autoPlayTimer) {
    stopAutoPlay();
    return;
  }

  btnAuto.textContent = "Stop";
  autoPlayTimer = setInterval(async () => {
    if (!currentState || currentState.game_over) {
      stopAutoPlay();
      return;
    }
    await stepGame();
  }, 1200);
}

btnStart.addEventListener("click", startGame);
btnStep.addEventListener("click", stepGame);
btnAuto.addEventListener("click", toggleAutoPlay);
btnReset.addEventListener("click", startGame);

api("/state")
  .then(renderState)
  .catch(() => {
    statusMessage.textContent = "Could not reach server. Run: python game.py";
  });
