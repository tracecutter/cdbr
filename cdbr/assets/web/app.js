const form = document.querySelector('#solver-form');
const input = document.querySelector('#photo');
const dropZone = document.querySelector('#drop-zone');
const emptyState = document.querySelector('#empty-state');
const previewState = document.querySelector('#preview-state');
const previewImage = document.querySelector('#preview-image');
const fileFallbackMessage = document.querySelector('#file-fallback-message');
const fileFallback = document.querySelector('#file-fallback');
const workingState = document.querySelector('#working-state');
const workingMessage = document.querySelector('#working-message');
const resultState = document.querySelector('#result-state');
const resultImage = document.querySelector('#result-image');
const resultKicker = document.querySelector('#result-kicker');
const resultDetail = document.querySelector('#result-detail');
const downloadResult = document.querySelector('#download-result');
const errorState = document.querySelector('#error-state');
const errorMessage = document.querySelector('#error-message');
const retakeTips = document.querySelector('#retake-tips');
const gameWorkspace = document.querySelector('#game-workspace');
const scannerWorkspace = document.querySelector('#scanner-workspace');
const idleWorkspace = document.querySelector('#idle-workspace');
const playWorkspace = document.querySelector('#play-workspace');
const creatorWorkspace = document.querySelector('#creator-workspace');
const showGameButton = document.querySelector('#show-game');
const showScannerButton = document.querySelector('#show-scanner');
const showCreatorButton = document.querySelector('#show-creator');
const puzzleShell = document.querySelector('#puzzle-shell');
const puzzleBoardWrap = document.querySelector('#puzzle-board-wrap');
const alphabetTop = document.querySelector('#alphabet-top');
const alphabetBottom = document.querySelector('#alphabet-bottom');
const vowelRail = document.querySelector('#vowel-rail');
const solverProgress = document.querySelector('#solver-progress');
const solverProgressTitle = document.querySelector('#solver-progress-title');
const solverProgressDetail = document.querySelector('#solver-progress-detail');
const referenceGrid = document.querySelector('#reference-grid');
const gameKeyboard = document.querySelector('#game-keyboard');
const gameStatus = document.querySelector('#game-status');
const gameGuidance = document.querySelector('#game-guidance');
const gameTitle = document.querySelector('#game-title');
const fileMeta = document.querySelector('#file-meta');
const solveButton = document.querySelector('#solve-button');
const scanActions = document.querySelector('.scan-actions');
const reviewState = document.querySelector('#review-state');
const reviewCells = document.querySelector('#review-cells');
const reviewClues = document.querySelector('#review-clues');
const reviewCellGroup = document.querySelector('#review-cell-group');
const reviewClueGroup = document.querySelector('#review-clue-group');
const reviewGuidance = document.querySelector('#review-guidance');
const finishReview = document.querySelector('#finish-review');
const blankPuzzleShell = document.querySelector('#blank-puzzle-shell');
const playPuzzleShell = document.querySelector('#play-puzzle-shell');
const creatorPuzzleShell = document.querySelector('#creator-puzzle-shell');
const blankReferenceGrid = document.querySelector('#blank-reference-grid');
const creatorForm = document.querySelector('#creator-form');
const creatorProgress = document.querySelector('#creator-progress');
const creatorProgressKicker = document.querySelector('#creator-progress-kicker');
const creatorProgressTitle = document.querySelector('#creator-progress-title');
const creatorProgressDetail = document.querySelector('#creator-progress-detail');
const publishCreated = document.querySelector('#publish-created');
const cancelCreated = document.querySelector('#cancel-created');
const puzzleNumber = document.querySelector('#puzzle-number');
const puzzlePickerStatus = document.querySelector('#puzzle-picker-status');
const startPuzzleButton = document.querySelector('#start-puzzle');
const randomPuzzleButton = document.querySelector('#random-puzzle');
const checkGameButton = document.querySelector('#check-game');
const hintDialog = document.querySelector('#hint-dialog');
const hintDialogTitle = document.querySelector('#hint-dialog-title');
const hintDialogAnswer = document.querySelector('#hint-dialog-answer');
const hintDialogDetail = document.querySelector('#hint-dialog-detail');
const hintDialogWarning = document.querySelector('#hint-dialog-warning');
const hintDialogAccept = document.querySelector('#hint-dialog-accept');

let previewUrl;
let resultUrl;
let selectedFile;
let stageTimer;
let scanJob;
let game;
let selectedSymbol;
let draftLetter;
let solving = false;
let solverStatusTimer;
let generationJob;
let generationPoll;
let revealed = new Map();
let entrySources = new Map();
let originalHints = new Set();
let incorrectSymbols = new Set();
let boardScale = 1;
let pinchStartDistance;
let pinchStartScale = 1;

const workingStages = [
  'Finding the puzzle grid…',
  'Reading the numbered cells…',
  'Checking the reference clues…',
  'Preparing your review…',
];

const solvingStages = [
  'Checking the crossing words.',
  'Consulting the British English lexicon.',
  'Testing the strongest candidates.',
];

function beginSolving(title, detail) {
  solving = true;
  solverProgressTitle.textContent = title;
  solverProgressDetail.textContent = detail;
  solverProgress.hidden = false;
  puzzleBoardWrap.setAttribute('aria-busy', 'true');
  document.querySelector('#reveal-all').disabled = true;
  checkGameButton.disabled = true;
  let stage = 0;
  window.clearInterval(solverStatusTimer);
  solverStatusTimer = window.setInterval(() => {
    solverProgressDetail.textContent = solvingStages[stage % solvingStages.length];
    stage += 1;
  }, 1800);
}

function endSolving() {
  window.clearInterval(solverStatusTimer);
  solverProgress.hidden = true;
  puzzleBoardWrap.removeAttribute('aria-busy');
  document.querySelector('#reveal-all').disabled = false;
  checkGameButton.disabled = false;
  solving = false;
}

function previewReferenceHint(symbol, hint) {
  const letter = hint?.letter;
  const certified = hint?.solution_status === 'certified';
  hintDialogTitle.textContent = letter ? `Hint for number ${symbol}` : `No hint yet for number ${symbol}`;
  hintDialogAnswer.textContent = letter ? `${symbol} = ${letter}` : '';
  hintDialogAnswer.classList.toggle('is-empty', !letter);
  hintDialogDetail.textContent = letter
    ? 'The current solution supports this reference-grid letter.'
    : 'The puzzle is not fully solved, and the current partial solution does not know this letter.';
  hintDialogWarning.textContent = letter && !certified
    ? 'Caveat solver: the puzzle is not complete, so this best guess may be wrong.'
    : letter
      ? 'This letter comes from a complete, uniquely certified solution.'
      : 'I cannot give you a hint yet. Add a few letters and ask again; each entry narrows the search.';
  hintDialogAccept.hidden = !letter;
  return new Promise((resolve) => {
    hintDialog.addEventListener('close', () => resolve(letter && hintDialog.returnValue === 'accept'), { once: true });
    hintDialog.showModal();
  });
}

function showMode(mode) {
  document.body.dataset.mode = mode;
  idleWorkspace.hidden = mode !== 'idle';
  playWorkspace.hidden = mode !== 'play';
  gameWorkspace.hidden = mode !== 'game';
  scannerWorkspace.hidden = mode !== 'scanner';
  creatorWorkspace.hidden = mode !== 'creator';
  showGameButton.classList.toggle('is-active', mode === 'play' || mode === 'game');
  showScannerButton.classList.toggle('is-active', mode === 'scanner');
  showCreatorButton.classList.toggle('is-active', mode === 'creator');
}

function renderBlankDesk() {
  for (let index = 0; index < 225; index += 1) {
    blankPuzzleShell.append(document.createElement('span'));
    playPuzzleShell.append(document.createElement('span'));
    creatorPuzzleShell.append(document.createElement('span'));
  }
  for (let symbol = 1; symbol <= 26; symbol += 1) {
    const cell = document.createElement('span');
    cell.textContent = symbol;
    blankReferenceGrid.append(cell);
  }
}

async function showPuzzlePicker() {
  showMode('play');
  const response = await fetch('/api/puzzles');
  if (!response.ok) return;
  const catalog = await response.json();
  const serials = catalog.puzzles.map((puzzle) => puzzle.serial);
  puzzlePickerStatus.textContent = serials.length
    ? `Available book numbers: ${serials.join(', ')}`
    : 'No published puzzles are available yet.';
}

async function startCorpusGame(puzzleId) {
  game = undefined;
  if (await loadGame(puzzleId)) {
    puzzlePickerStatus.textContent = '';
    showMode('game');
  } else {
    puzzlePickerStatus.textContent = `Puzzle ${puzzleId} is not in the current collection.`;
  }
}

function letterFor(symbol) {
  return selectedSymbol === symbol && draftLetter ? draftLetter : revealed.get(symbol);
}

function sourceFor(symbol) {
  return selectedSymbol === symbol && draftLetter ? 'preview' : entrySources.get(symbol);
}

function usedLetters() {
  const letters = new Set(revealed.values());
  if (draftLetter) letters.add(draftLetter);
  return letters;
}

function renderAlphabetRail(container, letters) {
  const used = usedLetters();
  container.replaceChildren();
  [...letters].forEach((letter) => {
    const item = document.createElement('span');
    item.textContent = letter;
    item.className = 'alphabet-letter';
    if (used.has(letter)) item.classList.add('is-used');
    item.setAttribute('aria-label', `${letter}, ${used.has(letter) ? 'used' : 'available'}`);
    container.append(item);
  });
}

function renderAlphabet() {
  renderAlphabetRail(alphabetTop, 'ABCDEFGHIJK');
  renderAlphabetRail(alphabetBottom, 'LMNOPQRSTUVWXYZ');
  vowelRail.replaceChildren(document.createElement('span'));
  [...'AEIOU'].forEach((letter) => {
    const item = document.createElement('span');
    item.textContent = letter;
    item.className = 'alphabet-letter';
    if (usedLetters().has(letter)) item.classList.add('is-used');
    item.setAttribute('aria-label', `${letter}, ${usedLetters().has(letter) ? 'used' : 'available'}`);
    vowelRail.append(item);
  });
  vowelRail.append(document.createElement('span'));
}

function playerEntries() {
  return Object.fromEntries(
    [...entrySources.entries()]
      .filter(([, source]) => source === 'player')
      .map(([symbol]) => [symbol, revealed.get(symbol)]),
  );
}

function solveRequest() {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entries: playerEntries() }),
  };
}

function symbolUsing(letter, exceptSymbol) {
  for (const [symbol, value] of revealed.entries()) {
    if (symbol !== exceptSymbol && value === letter) return symbol;
  }
  return undefined;
}

function decorateEntry(cell, symbol) {
  const letter = letterFor(symbol);
  const source = sourceFor(symbol);
  if (letter) {
    const glyph = document.createElement('strong');
    glyph.textContent = letter;
    cell.append(glyph);
    cell.classList.add('is-filled', `is-${source}-entry`);
  }
  if (incorrectSymbols.has(symbol)) cell.classList.add('is-incorrect');
  if (selectedSymbol === symbol) cell.classList.add('is-selected');
}

function commitSelection() {
  if (selectedSymbol === undefined) return;
  if (draftLetter) {
    revealed.set(selectedSymbol, draftLetter);
    entrySources.set(selectedSymbol, 'player');
    incorrectSymbols.delete(selectedSymbol);
  }
  selectedSymbol = undefined;
  draftLetter = undefined;
}

function cancelSelection() {
  selectedSymbol = undefined;
  draftLetter = undefined;
}

function selectSymbol(symbol) {
  if (solving) return false;
  const alreadySelected = selectedSymbol === symbol;
  if (!alreadySelected) commitSelection();
  if (originalHints.has(symbol)) {
    gameGuidance.textContent = `${symbol}=${revealed.get(symbol)} is an original clue and cannot be changed.`;
    renderGame();
    renderReference();
    return false;
  }
  selectedSymbol = symbol;
  if (!alreadySelected) draftLetter = undefined;
  gameGuidance.textContent = `Type a letter for ${symbol}. Enter commits; Escape cancels; Backspace clears your entry.`;
  renderGame();
  renderReference();
  return true;
}

function renderGame() {
  if (!game) return;
  puzzleShell.style.setProperty('--grid-size', game.grid[0].length);
  puzzleShell.replaceChildren();
  game.grid.forEach((row, rowIndex) => {
    row.forEach((symbol, columnIndex) => {
      const cell = document.createElement(symbol === null ? 'span' : 'button');
      cell.className = symbol === null ? 'puzzle-cell is-block' : 'puzzle-cell';
      if (symbol !== null) {
        cell.type = 'button';
        cell.dataset.symbol = symbol;
        cell.dataset.position = `${rowIndex}-${columnIndex}`;
        cell.setAttribute('aria-label', `Puzzle cell ${symbol}`);
        const number = document.createElement('small');
        number.textContent = String(symbol);
        cell.append(number);
        decorateEntry(cell, symbol);
        if (originalHints.has(symbol)) {
          cell.classList.add('is-locked');
          cell.setAttribute('aria-label', `Puzzle cell ${symbol}, original clue ${revealed.get(symbol)}`);
        }
        cell.addEventListener('click', () => {
          selectSymbol(symbol);
        });
      }
      puzzleShell.append(cell);
    });
  });
  const used = new Set(game.used_symbols);
  const known = [...revealed.keys()].filter((symbol) => used.has(symbol)).length;
  gameStatus.textContent = `${known} letter${known === 1 ? '' : 's'} known · ${used.size - known} remaining`;
  renderAlphabet();
}

function renderReference() {
  if (!game) return;
  referenceGrid.replaceChildren();
  game.symbols.forEach((symbol) => {
    const cell = document.createElement('button');
    cell.type = 'button';
    cell.className = 'reference-cell';
    cell.dataset.symbol = symbol;
    if (!game.used_symbols.includes(symbol)) {
      cell.disabled = true;
      cell.classList.add('is-unused');
      cell.setAttribute('aria-label', `Reference symbol ${symbol}, not used in this puzzle`);
    }
    const number = document.createElement('small');
    number.textContent = symbol;
    cell.append(number);
    decorateEntry(cell, symbol);
    if (originalHints.has(symbol)) {
      cell.classList.add('is-locked');
      cell.setAttribute('aria-label', `Reference symbol ${symbol}, original clue ${revealed.get(symbol)}`);
    }
    cell.addEventListener('click', () => referenceClick(symbol));
    referenceGrid.append(cell);
  });
  renderKeyboard();
}

function renderKeyboard() {
  if (!gameKeyboard) return;
  const currentLetter = selectedSymbol === undefined ? undefined : draftLetter || revealed.get(selectedSymbol);
  gameKeyboard.querySelectorAll('.keyboard-letter').forEach((button) => {
    const letter = button.dataset.key;
    const owner = symbolUsing(letter, selectedSymbol);
    button.disabled = owner !== undefined;
    button.classList.toggle('is-used', owner !== undefined);
    button.classList.toggle('is-current', letter === currentLetter);
  });
}

function handleGameKey(key) {
  if (document.body.dataset.mode !== 'game' || selectedSymbol === undefined || solving) return false;
  if (/^[a-z]$/i.test(key)) {
    const letter = key.toUpperCase();
    const owner = symbolUsing(letter, selectedSymbol);
    if (owner !== undefined) {
      gameGuidance.textContent = `${letter} is already assigned to ${owner}. Choose an unused letter.`;
      return true;
    }
    draftLetter = letter;
    gameGuidance.textContent = `${selectedSymbol}=${draftLetter} previewed. Enter commits; Escape cancels.`;
  } else if (key === 'Enter') {
    const symbol = selectedSymbol;
    commitSelection();
    gameGuidance.textContent = revealed.has(symbol)
      ? `${symbol}=${revealed.get(symbol)} committed.`
      : `No letter entered for ${symbol}.`;
  } else if (key === 'Escape') {
    cancelSelection();
    gameGuidance.textContent = 'Entry cancelled.';
  } else if (key === 'Backspace') {
    const symbol = selectedSymbol;
    if (!originalHints.has(symbol)) {
      revealed.delete(symbol);
      entrySources.delete(symbol);
      incorrectSymbols.delete(symbol);
      gameGuidance.textContent = `Entry for ${symbol} was cleared.`;
    } else {
      gameGuidance.textContent = `${symbol}=${revealed.get(symbol)} is an original clue and cannot be changed.`;
    }
    cancelSelection();
  } else {
    return false;
  }
  renderGame();
  renderReference();
  return true;
}

gameKeyboard.querySelectorAll('.keyboard-row').forEach((row) => {
  [...row.dataset.letters].forEach((letter) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'keyboard-letter';
    button.dataset.key = letter;
    button.textContent = letter;
    button.setAttribute('aria-label', `Enter ${letter}`);
    row.insertBefore(button, row.querySelector('.keyboard-command'));
  });
});
gameKeyboard.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-key]');
  if (button && !button.disabled) handleGameKey(button.dataset.key);
});

function touchDistance(touches) {
  return Math.hypot(touches[0].clientX - touches[1].clientX, touches[0].clientY - touches[1].clientY);
}

function setBoardScale(scale) {
  boardScale = Math.min(2.5, Math.max(1, scale));
  puzzleShell.style.width = `${boardScale * 100}%`;
}

puzzleBoardWrap.addEventListener('touchstart', (event) => {
  if (event.touches.length !== 2) return;
  pinchStartDistance = touchDistance(event.touches);
  pinchStartScale = boardScale;
}, { passive: true });
puzzleBoardWrap.addEventListener('touchmove', (event) => {
  if (event.touches.length !== 2 || !pinchStartDistance) return;
  event.preventDefault();
  setBoardScale(pinchStartScale * touchDistance(event.touches) / pinchStartDistance);
}, { passive: false });
puzzleBoardWrap.addEventListener('touchend', (event) => {
  if (event.touches.length < 2) pinchStartDistance = undefined;
});

async function referenceClick(symbol) {
  if (solving) return;
  if (originalHints.has(symbol)) {
    selectSymbol(symbol);
    return;
  }
  if (selectedSymbol !== symbol) {
    selectSymbol(symbol);
    return;
  }
  if (draftLetter) {
    commitSelection();
    gameGuidance.textContent = `${symbol}=${revealed.get(symbol)} committed.`;
    renderReference();
    renderGame();
    return;
  }
  beginSolving('Solving the puzzle…', `Finding a reliable hint for ${symbol}.`);
  let response;
  try {
    response = await fetch(`/api/sessions/${game.session_id}/reveal/${symbol}`, solveRequest());
  } catch (_) {
    endSolving();
    selectedSymbol = undefined;
    gameGuidance.textContent = 'I could not reach the solver. Your entries are untouched, so you can keep playing.';
    renderReference();
    renderGame();
    return;
  }
  endSolving();
  if (!response.ok) {
    await previewReferenceHint(symbol);
    gameGuidance.textContent = `The partial solution does not know ${symbol} yet. Your entries are untouched.`;
    selectedSymbol = undefined;
    renderReference();
    renderGame();
    return;
  }
  const hint = await response.json();
  const accepted = hint.solution_status === 'certified'
    ? true
    : await previewReferenceHint(symbol, hint);
  if (!accepted) {
    selectedSymbol = undefined;
    draftLetter = undefined;
    gameGuidance.textContent = `Hint for ${symbol} left unused.`;
    renderReference();
    renderGame();
    return;
  }
  revealed.set(symbol, hint.letter);
  entrySources.set(symbol, 'solver');
  incorrectSymbols.delete(symbol);
  selectedSymbol = undefined;
  draftLetter = undefined;
  gameGuidance.textContent = `${symbol}=${hint.letter} revealed and written throughout the puzzle.`;
  renderReference();
  renderGame();
}

function installGame(prepared) {
  game = prepared;
  gameTitle.textContent = game.title;
  revealed = new Map(Object.entries(game.clues).map(([symbol, letter]) => [Number(symbol), letter]));
  originalHints = new Set(revealed.keys());
  incorrectSymbols = new Set();
  entrySources = new Map([...revealed.keys()].map((symbol) => [symbol, 'original']));
  selectedSymbol = undefined;
  draftLetter = undefined;
  setBoardScale(1);
  gameGuidance.textContent = 'Select any numbered cell and type a letter, or click a reference cell twice for a hint.';
  renderGame();
  renderReference();
}

async function loadGame(puzzleId) {
  const response = game?.session_id
    ? await fetch(`/api/sessions/${game.session_id}`)
    : await fetch(`/api/sessions/from-corpus/${puzzleId ?? '1'}`, { method: 'POST' });
  if (!response.ok) {
    gameStatus.textContent = 'Puzzle unavailable';
    return false;
  }
  installGame(await response.json());
  return true;
}

showGameButton.addEventListener('click', showPuzzlePicker);
startPuzzleButton.addEventListener('click', () => {
  const serial = puzzleNumber.value.trim();
  if (serial) startCorpusGame(serial);
  else puzzlePickerStatus.textContent = 'Enter the puzzle number printed in the book.';
});
randomPuzzleButton.addEventListener('click', () => startCorpusGame('random'));
puzzleNumber.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') startPuzzleButton.click();
});
function abandonGame() {
  if (document.body.dataset.mode !== 'game') return true;
  return window.confirm('Abandon game?');
}

function resetScanner() {
  clearInterval(stageTimer);
  resultState.hidden = true;
  errorState.hidden = true;
  workingState.hidden = true;
  previewState.classList.remove('is-working');
  previewState.hidden = true;
  fileMeta.hidden = true;
  solveButton.hidden = true;
  reviewState.hidden = true;
  scanActions.hidden = false;
  scanJob = undefined;
  emptyState.hidden = false;
  selectedFile = undefined;
  input.value = '';
}

function openScanner() {
  if (!abandonGame()) return;
  game = undefined;
  resetScanner();
  showMode('scanner');
}

function openCreator() {
  if (!abandonGame()) return;
  game = undefined;
  showMode('creator');
}

showScannerButton.addEventListener('click', openScanner);
showCreatorButton.addEventListener('click', openCreator);
document.querySelector('#scan-from-game').addEventListener('click', openScanner);
document.querySelector('#quit-game').addEventListener('click', () => showMode('idle'));
document.querySelector('#reset-game').addEventListener('click', loadGame);
document.addEventListener('keydown', (event) => {
  if (document.body.dataset.mode !== 'game' || selectedSymbol === undefined || solving) return;
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  const target = event.target;
  if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return;
  if (handleGameKey(event.key)) event.preventDefault();
});
checkGameButton.addEventListener('click', async () => {
  if (!game || solving) return;
  commitSelection();
  const entries = playerEntries();
  if (Object.keys(entries).length === 0) {
    incorrectSymbols.clear();
    gameGuidance.textContent = 'Enter at least one letter before checking.';
    renderGame();
    renderReference();
    return;
  }
  beginSolving('Checking your entries…', 'Comparing your letters without revealing the answers.');
  let response;
  try {
    response = await fetch(`/api/sessions/${game.session_id}/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entries }),
    });
  } catch (_) {
    endSolving();
    gameGuidance.textContent = 'I could not check the puzzle. Your entries are untouched.';
    return;
  }
  endSolving();
  if (!response.ok) {
    gameGuidance.textContent = 'I could not obtain a reliable answer for checking yet. Keep playing.';
    return;
  }
  const result = await response.json();
  incorrectSymbols = new Set(result.incorrect_symbols);
  if (result.checked_symbols.length === 0) {
    gameGuidance.textContent = 'No entries could be checked reliably yet. Keep playing.';
  } else if (incorrectSymbols.size === 0) {
    gameGuidance.textContent = 'No mistakes found in the entries I could check.';
  } else {
    gameGuidance.textContent = `${incorrectSymbols.size} incorrect letter${incorrectSymbols.size === 1 ? '' : 's'} highlighted.`;
  }
  renderGame();
  renderReference();
});
document.querySelector('#reveal-all').addEventListener('click', async () => {
  if (!game || solving || !window.confirm('Reveal the complete puzzle?')) return;
  beginSolving('Solving the puzzle…', 'Preparing the best available solution.');
  let response;
  try {
    response = await fetch(`/api/sessions/${game.session_id}/reveal`, solveRequest());
  } catch (_) {
    endSolving();
    gameGuidance.textContent = 'I could not reach the solver. Your entries are untouched, so you can keep playing.';
    return;
  }
  endSolving();
  if (!response.ok) {
    gameGuidance.textContent = 'I could not find a usable solution. Your entries are untouched, so you can keep playing.';
    return;
  }
  const data = await response.json();
  Object.entries(data.mapping).forEach(([symbol, letter]) => {
    const numericSymbol = Number(symbol);
    if (!originalHints.has(numericSymbol)) {
      revealed.set(numericSymbol, letter);
      entrySources.set(numericSymbol, 'solver');
    }
  });
  incorrectSymbols.clear();
  selectedSymbol = undefined;
  draftLetter = undefined;
  if (data.solution_status === 'certified') {
    gameGuidance.textContent = 'Complete, uniquely certified solution revealed.';
  } else if (data.solution_status === 'candidate') {
    gameGuidance.textContent = 'Best complete candidate revealed; uniqueness was not certified.';
  } else if (data.solution_status === 'partial') {
    gameGuidance.textContent = 'Best partial solution revealed. You can keep working from here.';
  } else {
    gameGuidance.textContent = 'No further solution could be found. You can keep playing.';
  }
  renderGame();
  renderReference();
});

function wordsFrom(id) {
  return document
    .querySelector(id)
    .value.split(/[\n,]+/)
    .map((word) => word.trim())
    .filter(Boolean);
}

function resetCreator() {
  window.clearTimeout(generationPoll);
  generationJob = undefined;
  creatorForm.hidden = false;
  creatorProgress.hidden = true;
  creatorProgress.classList.remove('is-complete');
  creatorProgressKicker.textContent = 'Building your puzzle';
  publishCreated.hidden = true;
  publishCreated.textContent = 'Play best now';
  cancelCreated.textContent = 'Cancel';
}

async function pollGenerationJob() {
  if (!generationJob) return;
  const response = await fetch(`/api/generation-jobs/${generationJob}`);
  if (!response.ok) {
    creatorProgressTitle.textContent = 'Generation job expired';
    cancelCreated.textContent = 'Start over';
    return;
  }
  const job = await response.json();
  if (job.candidate && job.status === 'running') {
    const candidate = job.candidate;
    const count = candidate.certified_candidates;
    creatorProgressKicker.textContent = 'Best so far';
    creatorProgressTitle.textContent = `${candidate.black_cells} black cells`;
    creatorProgressDetail.textContent = `${count} certified ${count === 1 ? 'candidate' : 'candidates'} · ${job.remaining_seconds}s remaining · still searching`;
    publishCreated.textContent = 'Play best now';
    publishCreated.hidden = false;
    cancelCreated.textContent = 'Discard and start over';
  } else if (job.progress.includes('fill complete')) {
    creatorProgressTitle.textContent = 'Candidate filled — checking uniqueness';
    creatorProgressDetail.textContent = `${job.elapsed_seconds}s elapsed · search continues until certified`;
  } else {
    creatorProgressTitle.textContent = job.progress;
    creatorProgressDetail.textContent = `${job.elapsed_seconds}s elapsed`;
  }
  if (job.status === 'complete') {
    const candidate = job.candidate;
    creatorProgress.classList.add('is-complete');
    creatorProgressKicker.textContent = 'Puzzle ready';
    creatorProgressDetail.textContent = `${candidate.black_cells} black cells · ${candidate.clues} clues · certified unique`;
    publishCreated.textContent = 'Play this puzzle';
    publishCreated.hidden = false;
    cancelCreated.textContent = 'Discard and start over';
    return;
  }
  if (job.status === 'failed' || job.status === 'cancelled') {
    creatorProgressDetail.textContent = job.error || 'No puzzle was published.';
    cancelCreated.textContent = 'Start over';
    return;
  }
  generationPoll = window.setTimeout(pollGenerationJob, 1000);
}

creatorForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const requiredWords = wordsFrom('#required-words');
  if (!requiredWords.length) return;
  creatorForm.hidden = true;
  creatorProgress.hidden = false;
  creatorProgress.classList.remove('is-complete');
  creatorProgressKicker.textContent = 'Building your puzzle';
  creatorProgressTitle.textContent = 'Starting the generator…';
  creatorProgressDetail.textContent = 'Three clues · British English';
  const response = await fetch('/api/generation-jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      required_words: requiredWords,
      excluded_words: wordsFrom('#excluded-words'),
      minutes: Number(document.querySelector('#generation-minutes').value),
    }),
  });
  if (!response.ok) {
    const error = await response.json();
    creatorProgressTitle.textContent = 'Could not start generation';
    creatorProgressDetail.textContent = error.detail || 'Please review the requested words.';
    cancelCreated.textContent = 'Start over';
    return;
  }
  generationJob = (await response.json()).job_id;
  pollGenerationJob();
});

cancelCreated.addEventListener('click', async () => {
  if (generationJob) {
    await fetch(`/api/generation-jobs/${generationJob}/cancel`, { method: 'POST' });
  }
  resetCreator();
});

publishCreated.addEventListener('click', async () => {
  if (!generationJob) return;
  const response = await fetch(`/api/generation-jobs/${generationJob}/publish`, { method: 'POST' });
  if (!response.ok) return;
  installGame(await response.json());
  window.clearTimeout(generationPoll);
  showMode('game');
});

function humanSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

renderBlankDesk();

function revoke(url) {
  if (url) URL.revokeObjectURL(url);
}

function showSelection(file) {
  selectedFile = file;
  emptyState.hidden = true;
  workingState.hidden = true;
  previewState.hidden = false;
  fileMeta.hidden = false;
  solveButton.hidden = false;
  resultState.hidden = true;
  errorState.hidden = true;
  reviewState.hidden = true;
  scanActions.hidden = false;
  scanJob = undefined;
  document.querySelector('#file-name').textContent = file.name || 'Puzzle photograph';
  document.querySelector('#file-size').textContent = humanSize(file.size);

  revoke(previewUrl);
  previewUrl = URL.createObjectURL(file);
  previewImage.src = previewUrl;
  previewImage.hidden = false;
  fileFallback.hidden = true;
  previewImage.onerror = async () => {
    previewImage.hidden = true;
    fileFallback.hidden = false;
    fileFallbackMessage.textContent = 'Preparing preview…';
    const body = new FormData();
    body.append('photo', file, file.name);
    try {
      const response = await fetch('/api/photo-preview', { method: 'POST', body });
      if (!response.ok || selectedFile !== file) throw new Error('Preview unavailable');
      revoke(previewUrl);
      previewUrl = URL.createObjectURL(await response.blob());
      previewImage.onerror = null;
      previewImage.src = previewUrl;
      previewImage.hidden = false;
      fileFallback.hidden = true;
    } catch (_) {
      fileFallbackMessage.textContent = 'Photo ready';
    }
  };
}

function chooseAgain() {
  resetScanner();
  input.click();
}

input.addEventListener('change', () => {
  if (input.files?.[0]) showSelection(input.files[0]);
});

['dragenter', 'dragover'].forEach((name) => {
  dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.add('is-dragging');
  });
});

['dragleave', 'drop'].forEach((name) => {
  dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.remove('is-dragging');
  });
});

dropZone.addEventListener('drop', (event) => {
  const file = event.dataTransfer?.files?.[0];
  if (file?.type.startsWith('image/') || /\.(heic|heif)$/i.test(file?.name || '')) showSelection(file);
});

document.querySelector('#change-photo').addEventListener('click', chooseAgain);
document.querySelector('#try-again').addEventListener('click', chooseAgain);
document.querySelector('#solve-another').addEventListener('click', chooseAgain);
document.querySelector('#cancel-review').addEventListener('click', chooseAgain);
document.querySelector('#quit-scan').addEventListener('click', () => {
  clearInterval(stageTimer);
  workingState.hidden = true;
  previewState.classList.remove('is-working');
  previewState.hidden = true;
  fileMeta.hidden = true;
  solveButton.hidden = true;
  emptyState.hidden = false;
  errorState.hidden = true;
  reviewState.hidden = true;
  scanActions.hidden = false;
  scanJob = undefined;
  selectedFile = undefined;
  input.value = '';
  showMode('idle');
});

function showReview(prepared) {
  scanJob = prepared;
  reviewCells.replaceChildren();
  reviewClues.replaceChildren();
  prepared.review_clues.forEach((item) => {
    const label = document.createElement('label');
    label.className = 'review-cell review-clue';
    const image = document.createElement('img');
    image.src = item.image;
    image.alt = `Original reference clue for symbol ${item.symbol}`;
    const detail = document.createElement('span');
    const coordinate = document.createElement('strong');
    coordinate.textContent = `Reference ${item.symbol}`;
    const confidence = document.createElement('small');
    confidence.textContent = item.proposed === null
      ? 'Scanner sees a blank cell — confirm or enter a letter'
      : `Scanner suggests ${item.proposed} · ${item.confidence}% agreement`;
    const value = document.createElement('input');
    value.type = 'text';
    value.maxLength = 1;
    value.pattern = '[A-Za-z]';
    value.value = item.proposed ?? '';
    value.dataset.symbol = item.symbol;
    value.autocapitalize = 'characters';
    value.setAttribute('aria-label', `Letter for reference symbol ${item.symbol}`);
    detail.append(coordinate, confidence);
    label.append(image, detail, value);
    reviewClues.append(label);
  });
  prepared.review_cells.forEach((item) => {
    const label = document.createElement('label');
    label.className = 'review-cell';
    const image = document.createElement('img');
    image.src = item.image;
    image.alt = `Original crop at row ${item.row}, column ${item.column}`;
    const detail = document.createElement('span');
    const coordinate = document.createElement('strong');
    coordinate.textContent = `Row ${item.row}, column ${item.column}`;
    const confidence = document.createElement('small');
    confidence.textContent = item.proposed === null
      ? 'No reliable reading'
      : `Scanner suggests ${item.proposed} · ${item.confidence}%`;
    const value = document.createElement('input');
    value.type = 'number';
    value.min = '1';
    value.max = '26';
    value.required = true;
    value.value = item.proposed ?? '';
    value.dataset.row = item.row;
    value.dataset.column = item.column;
    value.setAttribute('aria-label', `Value at row ${item.row}, column ${item.column}`);
    detail.append(coordinate, confidence);
    label.append(image, detail, value);
    reviewCells.append(label);
  });
  reviewClueGroup.hidden = prepared.review_clues.length === 0;
  reviewCellGroup.hidden = prepared.review_cells.length === 0;
  reviewGuidance.textContent = prepared.review_cells.length
    ? `Review ${prepared.review_clues.length} reference candidate${prepared.review_clues.length === 1 ? '' : 's'} and confirm ${prepared.review_cells.length} uncertain numbered cell${prepared.review_cells.length === 1 ? '' : 's'}. Blank reference inputs mean no clue is present.`
    : `Review ${prepared.review_clues.length} reference candidate${prepared.review_clues.length === 1 ? '' : 's'} before playing. Blank inputs mean no clue is present.`;
  scanActions.hidden = true;
  reviewState.hidden = false;
}

async function completeScan(cells, clues) {
  if (!scanJob) return;
  finishReview.disabled = true;
  finishReview.textContent = 'Solving…';
  try {
    const response = await fetch(`/api/scan-jobs/${scanJob.job_id}/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cells, clues }),
    });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || 'The reviewed puzzle could not be solved.');
    }
    installGame(await response.json());
    selectedFile = undefined;
    input.value = '';
    showMode('game');
  } catch (error) {
    errorState.hidden = false;
    errorMessage.textContent = error instanceof Error ? error.message : 'Please check the reviewed cells.';
    retakeTips.hidden = true;
  } finally {
    finishReview.disabled = false;
    finishReview.textContent = 'Confirm and open puzzle';
  }
}

finishReview.addEventListener('click', () => {
  const inputs = [...reviewCells.querySelectorAll('input')];
  const clueInputs = [...reviewClues.querySelectorAll('input')];
  if (![...inputs, ...clueInputs].every((item) => item.reportValidity())) return;
  completeScan(inputs.map((item) => ({
    row: Number(item.dataset.row),
    column: Number(item.dataset.column),
    value: Number(item.value),
  })), clueInputs.map((item) => ({
    symbol: Number(item.dataset.symbol),
    letter: item.value.toUpperCase(),
  })));
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!selectedFile) return;

  previewState.hidden = false;
  previewState.classList.add('is-working');
  errorState.hidden = true;
  resultState.hidden = true;
  workingState.hidden = false;
  workingMessage.textContent = workingStages[0];
  let stage = 0;
  stageTimer = window.setInterval(() => {
    stage = Math.min(stage + 1, workingStages.length - 1);
    workingMessage.textContent = workingStages[stage];
  }, 4200);

  const body = new FormData();
  body.append('photo', selectedFile, selectedFile.name);

  let retakeRecommended = false;
  try {
    const response = await fetch('/api/scan-jobs', { method: 'POST', body });
    if (!response.ok) {
      retakeRecommended = response.status === 422;
      let message = 'Try another image with the complete puzzle in frame.';
      try {
        const data = await response.json();
        if (data.detail) message = data.detail;
      } catch (_) {
        // The friendly fallback is more useful than a response parsing error.
      }
      throw new Error(message);
    }

    const prepared = await response.json();
    workingState.hidden = true;
    previewState.classList.remove('is-working');
    scanJob = prepared;
    if (prepared.review_cells.length || prepared.review_clues.length) {
      showReview(prepared);
    } else {
      await completeScan([], []);
    }
  } catch (error) {
    workingState.hidden = true;
    previewState.classList.remove('is-working');
    previewState.hidden = false;
    errorState.hidden = false;
    errorMessage.textContent = error instanceof Error ? error.message : 'Please try another photograph.';
    retakeTips.hidden = !retakeRecommended;
  } finally {
    clearInterval(stageTimer);
  }
});
