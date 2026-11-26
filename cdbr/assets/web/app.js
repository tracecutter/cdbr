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
const reviewBoard = document.querySelector('#review-board');
const reviewPhoto = document.querySelector('#review-photo');
const reviewReference = document.querySelector('#review-reference');
const reviewCount = document.querySelector('#review-count');
const reviewEditor = document.querySelector('#review-editor');
const reviewValue = document.querySelector('#review-value');
const reviewValueLabel = document.querySelector('#review-value-label');
const reviewCrop = document.querySelector('#review-crop');
const confirmReviewButton = document.querySelector('#confirm-review');
const reviewError = document.querySelector('#review-error');
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
const puzzleSelect = document.querySelector('#puzzle-select');
const puzzlePickerStatus = document.querySelector('#puzzle-picker-status');
const startPuzzleButton = document.querySelector('#start-puzzle');
const randomPuzzleButton = document.querySelector('#random-puzzle');
const checkGameButton = document.querySelector('#check-game');

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
let solverProgressTimer;
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
  puzzleBoardWrap.setAttribute('aria-busy', 'true');
  document.querySelector('#reveal-all').disabled = true;
  checkGameButton.disabled = true;
  if (game?.solution_status === 'certified') return;
  solverProgressTimer = window.setTimeout(() => {
    solverProgressTitle.textContent = title;
    solverProgressDetail.textContent = detail;
    solverProgress.hidden = false;
    let stage = 0;
    solverStatusTimer = window.setInterval(() => {
      solverProgressDetail.textContent = solvingStages[stage % solvingStages.length];
      stage += 1;
    }, 1800);
  }, 300);
}

function endSolving() {
  window.clearTimeout(solverProgressTimer);
  window.clearInterval(solverStatusTimer);
  solverProgress.hidden = true;
  puzzleBoardWrap.removeAttribute('aria-busy');
  document.querySelector('#reveal-all').disabled = false;
  checkGameButton.disabled = false;
  solving = false;
}

function showMode(mode) {
  document.body.dataset.mode = mode;
  idleWorkspace.hidden = mode !== 'idle';
  playWorkspace.hidden = mode !== 'play';
  gameWorkspace.hidden = mode !== 'game';
  scannerWorkspace.hidden = mode !== 'scanner';
  reviewState.hidden = mode !== 'review';
  creatorWorkspace.hidden = mode !== 'creator';
  showGameButton.classList.toggle('is-active', mode === 'play' || mode === 'game');
  showScannerButton.classList.toggle('is-active', mode === 'scanner' || mode === 'review');
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

function setPuzzlePickerStatus(message = '') {
  puzzlePickerStatus.textContent = message;
  puzzlePickerStatus.hidden = !message;
}

function setPuzzlePickerBusy(busy) {
  const empty = puzzleSelect.options.length <= 1;
  puzzleSelect.disabled = busy || empty;
  startPuzzleButton.disabled = busy || !puzzleSelect.value;
  randomPuzzleButton.disabled = busy || empty;
}

async function showPuzzlePicker() {
  showMode('play');
  const previous = puzzleSelect.value;
  puzzleSelect.options.length = 1;
  setPuzzlePickerBusy(true);
  setPuzzlePickerStatus('Loading puzzles…');
  try {
    const response = await fetch('/api/puzzles');
    if (!response.ok) throw new Error('Catalog unavailable');
    const { puzzles } = await response.json();
    puzzleSelect.options.length = 1;
    for (const { id, serial, title } of puzzles) {
      puzzleSelect.add(new Option(title, String(id ?? serial)));
    }
    if (puzzles.some(({ id, serial }) => String(id ?? serial) === previous)) puzzleSelect.value = previous;
    setPuzzlePickerStatus(puzzles.length ? '' : 'No published puzzles are available yet.');
  } catch {
    setPuzzlePickerStatus('Could not load the puzzle library. Select Play to try again.');
  } finally {
    setPuzzlePickerBusy(false);
  }
}

async function startCorpusGame(puzzleId) {
  setPuzzlePickerBusy(true);
  setPuzzlePickerStatus();
  game = undefined;
  try {
    if (!await loadGame(puzzleId)) throw new Error('Puzzle unavailable');
    if (document.body.dataset.mode === 'play') showMode('game');
  } catch {
    setPuzzlePickerStatus('Could not open a puzzle. Please try again.');
  } finally {
    setPuzzlePickerBusy(false);
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
  if (!await readyToSolveFromProgress()) return;
  beginSolving('Solving the puzzle…', `Finding a reliable hint for ${symbol}.`);
  let response, hint;
  try {
    response = await fetch(`/api/sessions/${game.session_id}/reveal/${symbol}`, solveRequest());
    hint = await response.json();
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
    gameGuidance.textContent = typeof hint.detail === 'string' ? hint.detail : `No hint available for ${symbol}.`;
    selectedSymbol = undefined;
    renderReference();
    renderGame();
    return;
  }
  game.solution_status = hint.solution_status;
  revealed.set(symbol, hint.letter);
  entrySources.set(symbol, 'solver');
  incorrectSymbols.delete(symbol);
  selectedSymbol = undefined;
  draftLetter = undefined;
  gameGuidance.textContent = hint.solution_status === 'certified'
    ? `${symbol}=${hint.letter} revealed.`
    : `${symbol}=${hint.letter} revealed as a tentative hint. It may be wrong.`;
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

showGameButton.addEventListener('click', () => openWithDictionary(showPuzzlePicker));
startPuzzleButton.addEventListener('click', () => {
  if (puzzleSelect.value) startCorpusGame(puzzleSelect.value);
});
randomPuzzleButton.addEventListener('click', () => startCorpusGame('random'));
puzzleSelect.addEventListener('change', () => setPuzzlePickerBusy(false));
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

showScannerButton.addEventListener('click', () => openWithDictionary(openScanner));
showCreatorButton.addEventListener('click', () => openWithDictionary(openCreator));
document.querySelector('#scan-from-game').addEventListener('click', () => openWithDictionary(openScanner));
document.querySelector('#quit-game').addEventListener('click', () => showMode('idle'));
document.querySelector('#reset-game').addEventListener('click', loadGame);
document.addEventListener('keydown', (event) => {
  if (document.body.dataset.mode !== 'game' || selectedSymbol === undefined || solving) return;
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  const target = event.target;
  if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return;
  if (handleGameKey(event.key)) event.preventDefault();
});
async function checkPlayerEntries(entries) {
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
    return null;
  }
  endSolving();
  if (!response.ok) {
    gameGuidance.textContent = 'I could not obtain a reliable answer for checking yet. Keep playing.';
    return null;
  }
  const result = await response.json();
  game.solution_status = result.solution_status;
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
  return result;
}

async function readyToSolveFromProgress() {
  const entries = playerEntries();
  const count = Object.keys(entries).length;
  if (!count) return true;
  const current = game;
  const result = await checkPlayerEntries(entries);
  if (!result || game !== current) return false;
  if (result.incorrect_symbols.length) return false;
  if (result.checked_symbols.length !== count) {
    gameGuidance.textContent = 'I could not verify every entry yet. Clear any guesses you are unsure of before solving from your progress.';
    return false;
  }
  return true;
}

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
  await checkPlayerEntries(entries);
});
document.querySelector('#reveal-all').addEventListener('click', async () => {
  if (!game || solving || !window.confirm('Reveal the complete puzzle?')) return;
  commitSelection();
  if (!await readyToSolveFromProgress()) return;
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
  game.solution_status = data.solution_status;
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
document.querySelector('#cancel-review').addEventListener('click', () => {
  showMode('scanner');
  chooseAgain();
});
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

let reviewItems = new Map();
let reviewQueue = new Set();
let reviewSelection;
let reviewPreview;
let submittingReview = false;
let checkingDictionary = false;

function paintReview() {
  const selected = reviewItems.get(reviewPreview ?? reviewSelection);
  const match = selected?.symbol ?? (selected ? Number(selected.draft) : 0);
  for (const [key, item] of reviewItems) {
    const number = item.symbol ?? Number(item.draft);
    item.button.classList.toggle('review-pending', reviewQueue.has(key));
    item.button.classList.toggle('review-match', match > 0 && number === match);
    item.button.classList.toggle('review-selected', key === reviewSelection);
    item.button.classList.toggle('review-preview', key === reviewPreview);
    item.button.setAttribute('aria-pressed', String(key === (reviewPreview ?? reviewSelection)));
    item.button.setAttribute('aria-label', `${item.label}, ${item.draft || (item.symbol ? 'blank' : 'unknown')}${reviewQueue.has(key) ? ', needs review' : ''}`);
    item.value.textContent = item.draft || (item.symbol ? '' : '?');
  }
  const count = reviewQueue.size;
  reviewCount.textContent = count ? `${count} cell${count === 1 ? '' : 's'} to check` : 'Review complete';
  finishReview.disabled = submittingReview || count > 0;
}

function selectReview(key, { preview = false } = {}) {
  reviewPreview = preview ? key : undefined;
  if (!preview) reviewSelection = key;
  const item = reviewItems.get(key);
  reviewEditor.dataset.inactive = 'false';
  reviewValue.disabled = preview;
  confirmReviewButton.disabled = preview;
  reviewValueLabel.textContent = preview
    ? `${item.label} · Click again to edit`
    : item.symbol ? `${item.label} (blank if empty)` : `${item.label} (1–26)`;
  reviewValue.value = item.draft;
  reviewValue.maxLength = item.symbol ? 1 : 2;
  reviewValue.inputMode = item.symbol ? 'text' : 'numeric';
  reviewCrop.src = item.image;
  reviewError.hidden = true;
  paintReview();
  if (!preview) {
    reviewValue.focus();
    reviewValue.select();
  }
}

function clearReviewSelection() {
  reviewSelection = undefined;
  reviewPreview = undefined;
  reviewEditor.dataset.inactive = 'true';
  reviewValueLabel.textContent = 'Select a cell to review';
  reviewValue.value = '';
  reviewValue.disabled = true;
  confirmReviewButton.disabled = true;
  reviewCrop.removeAttribute('src');
  reviewError.hidden = true;
}

function confirmReview() {
  if (submittingReview || reviewPreview !== undefined) return;
  const item = reviewItems.get(reviewSelection);
  if (!item) return;
  const value = item.draft.trim().toUpperCase();
  const valid = item.symbol ? /^[A-Z]?$/.test(value) : /^(?:[1-9]|1[0-9]|2[0-6])$/.test(value);
  if (!valid) {
    reviewError.textContent = item.symbol ? 'Enter one letter or leave the clue blank.' : 'Enter a number from 1 to 26.';
    reviewError.hidden = false;
    reviewValue.focus();
    return;
  }
  item.confirmed = value;
  item.draft = value;
  const keys = [...reviewQueue];
  const next = keys[(keys.indexOf(reviewSelection) + 1) % keys.length];
  reviewQueue.delete(reviewSelection);
  if (reviewQueue.size) {
    selectReview(next);
  } else {
    clearReviewSelection();
    paintReview();
    finishReview.focus();
  }
}

function addReviewItem(key, item, container) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = item.symbol ? 'reference-cell' : 'puzzle-cell';
  if (item.symbol) {
    const number = document.createElement('small');
    number.textContent = item.symbol;
    button.append(number);
  }
  const value = document.createElement('strong');
  button.append(value);
  item.button = button;
  item.value = value;
  reviewItems.set(key, item);
  button.addEventListener('click', () => {
    if (submittingReview) return;
    if (key === reviewPreview) {
      if (reviewQueue.size) reviewQueue.add(key);
      selectReview(key);
    } else if (!reviewQueue.size && (key !== reviewSelection || reviewPreview !== undefined)) {
      reviewSelection = undefined;
      selectReview(key, { preview: true });
    } else if (key === reviewSelection) {
      if (reviewPreview === undefined) confirmReview();
      else selectReview(key);
    } else if (reviewQueue.has(key)) {
      selectReview(key);
    } else {
      const selected = reviewItems.get(reviewSelection);
      const number = item.symbol ?? Number(item.draft);
      if (number > 0 && number === (selected?.symbol ?? Number(selected?.draft))) {
        selectReview(key, { preview: true });
      } else {
        selectReview(key);
      }
    }
  });
  container.append(button);
}

function syncReviewPhoto() {
  reviewBoard.classList.toggle('has-scan-photo', reviewPhoto.checked);
}

reviewPhoto.addEventListener('change', syncReviewPhoto);

function showReview(prepared) {
  scanJob = prepared;
  reviewItems = new Map();
  reviewQueue = new Set();
  document.querySelector('#review-guidance').textContent = 'Red outlines mark cells to check. Click a blue match to preview it, then click it again to edit.';
  clearReviewSelection();
  reviewBoard.style.setProperty('--grid-size', prepared.grid[0].length);
  reviewBoard.replaceChildren();
  reviewReference.replaceChildren();
  const flagged = new Map(prepared.review_cells.map((item) => [`${item.row}/${item.column}`, item]));
  const flaggedClues = new Map(prepared.review_clues.map((item) => [item.symbol, item]));
  const base = `/api/scan-jobs/${prepared.job_id}`;
  reviewBoard.style.setProperty('--scan-photo', `url("${base}/grid")`);
  syncReviewPhoto();
  prepared.grid.forEach((values, rowIndex) => values.forEach((number, columnIndex) => {
    if (number === '.') {
      const block = document.createElement('span');
      block.className = 'puzzle-cell is-block';
      reviewBoard.append(block);
      return;
    }
    const row = rowIndex + 1;
    const column = columnIndex + 1;
    const key = `${row}/${column}`;
    const flag = flagged.get(key);
    if (flag) reviewQueue.add(key);
    addReviewItem(key, {
      row, column, label: `Row ${row}, column ${column}`,
      draft: String((flag ? flag.proposed : number) ?? ''),
      image: `${base}/cells/${key}`,
    }, reviewBoard);
    const cell = reviewItems.get(key).button;
    cell.style.setProperty('--scan-x', `${columnIndex * 100 / (values.length - 1)}%`);
    cell.style.setProperty('--scan-y', `${rowIndex * 100 / (prepared.grid.length - 1)}%`);
  }));
  for (let symbol = 1; symbol <= 26; symbol += 1) {
    const key = `clue-${symbol}`;
    const flag = flaggedClues.get(symbol);
    if (flag) reviewQueue.add(key);
    addReviewItem(key, {
      symbol, label: `Reference ${symbol}`,
      draft: (flag ? flag.proposed : prepared.clues[symbol]) ?? '',
      image: `${base}/clues/${symbol}`,
    }, reviewReference);
  }
  showMode('review');
  const first = reviewQueue.values().next().value;
  if (first !== undefined) selectReview(first);
  else paintReview();
}

reviewValue.addEventListener('input', () => {
  const item = reviewItems.get(reviewSelection);
  if (!item) return;
  item.draft = reviewValue.value.toUpperCase();
  reviewQueue.add(reviewSelection);
  reviewError.hidden = true;
  paintReview();
});
document.querySelector('#review-edit-form').addEventListener('submit', (event) => {
  event.preventDefault();
  confirmReview();
});

const scanSolveDialog = document.querySelector('#scan-solve-dialog');
const scanSolveTitle = document.querySelector('#scan-solve-title');
const scanSolveMessage = document.querySelector('#scan-solve-message');
const scanSolveProgress = document.querySelector('#scan-solve-progress');
const scanSolveProgressDetail = document.querySelector('#scan-solve-progress-detail');
const keepSearchingButton = document.querySelector('#keep-searching');
let nextScanSearchRound;

async function finishScanReview(checkSolution, searchRound = 0) {
  if (!scanJob || submittingReview || reviewQueue.size) return;
  const job = scanJob;
  const cells = [];
  const clues = [];
  for (const item of reviewItems.values()) {
    if (item.confirmed === undefined) continue;
    if (item.symbol) clues.push({ symbol: item.symbol, letter: item.confirmed });
    else cells.push({ row: item.row, column: item.column, value: Number(item.confirmed) });
  }
  submittingReview = true;
  reviewError.hidden = true;
  paintReview();
  let progressTimer;
  try {
    if (checkSolution) {
      let stage = 0;
      scanSolveProgressDetail.textContent = solvingStages[stage];
      scanSolveProgress.hidden = false;
      reviewBoard.setAttribute('aria-busy', 'true');
      progressTimer = window.setInterval(() => {
        stage = (stage + 1) % solvingStages.length;
        scanSolveProgressDetail.textContent = solvingStages[stage];
      }, 1800);
    }
    const response = await fetch(`/api/scan-jobs/${job.job_id}/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cells, clues, check_solution: checkSolution, search_round: searchRound }),
    });
    const data = await response.json();
    scanSolveProgress.hidden = true;
    if (scanJob !== job || document.body.dataset.mode !== 'review') return;
    if (response.status === 409 && data.detail?.code === 'scan_solve_check') {
      nextScanSearchRound = data.detail.next_search_round;
      const canKeepSearching = Number.isInteger(nextScanSearchRound);
      keepSearchingButton.hidden = !canKeepSearching;
      if (data.detail.status === 'no_complete_solution') {
        scanSolveTitle.textContent = 'Check the scan?';
        scanSolveMessage.textContent =
          'The search finished without finding a solution in the current dictionary. Check that the numbers and starting clues match the photo.';
        document.querySelector('#review-guidance').textContent =
          'Compare the scanned numbers with the board, especially 1s and 4s, and 6s and 8s.';
      } else if (canKeepSearching) {
        scanSolveTitle.textContent = 'Keep looking?';
        scanSolveMessage.textContent = 'I ran out of time. I can search longer, or you can start playing.';
      } else if (data.detail.status === 'unavailable') {
        scanSolveTitle.textContent = 'Couldn’t check the scan';
        scanSolveMessage.textContent = 'You can review the board again or start playing.';
      } else {
        scanSolveTitle.textContent = 'Search limit reached';
        scanSolveMessage.textContent = 'The search stopped before finding a complete solution. You can review the board or start playing.';
      }
      scanSolveDialog.returnValue = '';
      scanSolveDialog.showModal();
      if (canKeepSearching) keepSearchingButton.focus();
      return;
    }
    if (!response.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the reviewed cells and try again.');
    }
    installGame(data);
    scanJob = undefined;
    selectedFile = undefined;
    input.value = '';
    showMode('game');
  } catch (error) {
    if (scanJob !== job || document.body.dataset.mode !== 'review') return;
    reviewError.textContent = error instanceof Error ? error.message : 'The puzzle could not be opened.';
    reviewError.hidden = false;
  } finally {
    window.clearInterval(progressTimer);
    scanSolveProgress.hidden = true;
    reviewBoard.removeAttribute('aria-busy');
    submittingReview = false;
    paintReview();
  }
}

const dictionaryDialog = document.querySelector('#scan-dictionary-dialog');
const dictionaryStatus = document.querySelector('#scan-dictionary-status');
const loadDictionaryButton = document.querySelector('#load-scan-dictionary');
const cancelDictionaryButton = document.querySelector('#cancel-scan-dictionary');
const dictionaryChoice = document.querySelector('#scan-dictionary-choice');

let dictionaryDestination;
const dictionaryPrompt = 'Load the selected dictionary to continue.';

async function openWithDictionary(openWorkspace) {
  if (checkingDictionary || dictionaryDialog.open) return;
  checkingDictionary = true;
  const startingMode = document.body.dataset.mode;
  let loaded = false;
  try {
    const response = await fetch('/api/scan-dictionary', { cache: 'no-store' });
    loaded = response.ok && (await response.json()).loaded;
  } catch {
    // The dialog lets the player retry loading if the status request failed.
  } finally {
    checkingDictionary = false;
  }
  if (document.body.dataset.mode !== startingMode) return;
  if (loaded) {
    openWorkspace();
  } else {
    dictionaryDestination = openWorkspace;
    dictionaryStatus.textContent = dictionaryPrompt;
    dictionaryDialog.showModal();
  }
}

finishReview.addEventListener('click', () => finishScanReview(true));
dictionaryDialog.addEventListener('close', () => {
  dictionaryDestination = undefined;
});
cancelDictionaryButton.addEventListener('click', () => dictionaryDialog.close());
dictionaryDialog.addEventListener('cancel', event => {
  if (loadDictionaryButton.disabled) event.preventDefault();
});
document.querySelector('#scan-dictionary-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (loadDictionaryButton.disabled) return;
  loadDictionaryButton.disabled = true;
  cancelDictionaryButton.disabled = true;
  dictionaryChoice.disabled = true;
  const label = dictionaryChoice.labels[0].textContent.trim();
  loadDictionaryButton.textContent = 'Loading…';
  dictionaryStatus.textContent = `Preparing ${label}. This may take a few seconds.`;
  try {
    const query = new URLSearchParams({ language: dictionaryChoice.value });
    const response = await fetch(`/api/scan-dictionary?${query}`, { method: 'POST' });
    if (!response.ok || !(await response.json()).loaded) throw new Error('Dictionary unavailable');
    document.querySelector('#footer-dictionary').textContent = label;
    const destination = dictionaryDestination;
    dictionaryDialog.close();
    destination?.();
  } catch {
    dictionaryStatus.textContent = 'Couldn’t load the dictionary. Try again or cancel.';
  } finally {
    loadDictionaryButton.textContent = 'Load Dictionary';
    loadDictionaryButton.disabled = false;
    cancelDictionaryButton.disabled = false;
    dictionaryChoice.disabled = false;
  }
});

scanSolveDialog.addEventListener('close', () => {
  if (scanSolveDialog.returnValue === 'play') {
    finishScanReview(false);
  } else if (scanSolveDialog.returnValue === 'search' && Number.isInteger(nextScanSearchRound)) {
    finishScanReview(true, nextScanSearchRound);
  }
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
    showReview(prepared);
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
