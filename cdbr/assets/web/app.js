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
const gameWorkspace = document.querySelector('#game-workspace');
const scannerWorkspace = document.querySelector('#scanner-workspace');
const idleWorkspace = document.querySelector('#idle-workspace');
const creatorWorkspace = document.querySelector('#creator-workspace');
const puzzleDesk = document.querySelector('.puzzle-desk');
const showGameButton = document.querySelector('#show-game');
const showScannerButton = document.querySelector('#show-scanner');
const showCreatorButton = document.querySelector('#show-creator');
const puzzleShell = document.querySelector('#puzzle-shell');
const referenceGrid = document.querySelector('#reference-grid');
const gameStatus = document.querySelector('#game-status');
const gameGuidance = document.querySelector('#game-guidance');
const gameTitle = document.querySelector('#game-title');
const blankPuzzleShell = document.querySelector('#blank-puzzle-shell');
const blankReferenceGrid = document.querySelector('#blank-reference-grid');
const creatorForm = document.querySelector('#creator-form');
const creatorProgress = document.querySelector('#creator-progress');
const creatorProgressTitle = document.querySelector('#creator-progress-title');
const creatorProgressDetail = document.querySelector('#creator-progress-detail');
const publishCreated = document.querySelector('#publish-created');
const cancelCreated = document.querySelector('#cancel-created');

let previewUrl;
let resultUrl;
let selectedFile;
let stageTimer;
let game;
let selectedSymbol;
let selectedPuzzleCell;
let generationJob;
let generationPoll;
let revealed = new Map();
let propagated = new Set();

const workingStages = [
  'Finding the puzzle grid…',
  'Reading the numbered cells…',
  'Checking the reference clues…',
  'Cracking the letter code…',
  'Preparing your playable puzzle…',
];

function showMode(mode) {
  idleWorkspace.hidden = true;
  gameWorkspace.hidden = mode !== 'game';
  scannerWorkspace.hidden = mode !== 'scanner';
  creatorWorkspace.hidden = mode !== 'creator';
  showGameButton.classList.toggle('is-active', mode === 'game');
  showScannerButton.classList.toggle('is-active', mode === 'scanner');
  showCreatorButton.classList.toggle('is-active', mode === 'creator');
  puzzleDesk.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderBlankDesk() {
  for (let index = 0; index < 225; index += 1) {
    blankPuzzleShell.append(document.createElement('span'));
  }
  for (let symbol = 1; symbol <= 26; symbol += 1) {
    const cell = document.createElement('span');
    cell.textContent = symbol;
    blankReferenceGrid.append(cell);
  }
}

async function startCorpusGame() {
  game = undefined;
  if (await loadGame()) showMode('game');
}

function renderGame() {
  if (!game) return;
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
        if (propagated.has(symbol)) {
          const letter = document.createElement('strong');
          letter.textContent = revealed.get(symbol);
          cell.append(letter);
          cell.classList.add('is-filled');
        }
        if (selectedPuzzleCell === cell.dataset.position) cell.classList.add('is-selected');
        cell.addEventListener('click', () => {
          selectedPuzzleCell = selectedPuzzleCell === cell.dataset.position ? undefined : cell.dataset.position;
          selectedSymbol = undefined;
          gameGuidance.textContent = selectedPuzzleCell
            ? 'Letter entry comes next. For now, choose hints from the reference grid.'
            : 'Select a numbered reference cell, then click it again to reveal it throughout the puzzle.';
          renderGame();
          renderReference();
        });
      }
      puzzleShell.append(cell);
    });
  });
  const used = new Set(game.used_symbols);
  const known = [...propagated].filter((symbol) => used.has(symbol)).length;
  gameStatus.textContent = `${known} letter${known === 1 ? '' : 's'} known · ${used.size - known} remaining`;
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
    if (revealed.has(symbol)) {
      const letter = document.createElement('strong');
      letter.textContent = revealed.get(symbol);
      cell.append(letter);
      cell.classList.add(propagated.has(symbol) ? 'is-propagated' : 'is-revealed');
    }
    if (selectedSymbol === symbol) cell.classList.add('is-selected');
    cell.addEventListener('click', () => referenceClick(symbol));
    referenceGrid.append(cell);
  });
}

async function referenceClick(symbol) {
  selectedPuzzleCell = undefined;
  if (revealed.has(symbol)) {
    if (!propagated.has(symbol)) {
      propagated.add(symbol);
      selectedSymbol = undefined;
      gameGuidance.textContent = `${symbol}=${revealed.get(symbol)} has been written throughout the puzzle.`;
    } else {
      selectedSymbol = selectedSymbol === symbol ? undefined : symbol;
      gameGuidance.textContent = `${symbol}=${revealed.get(symbol)} is already on the board.`;
    }
    renderReference();
    renderGame();
    return;
  }
  if (selectedSymbol !== symbol) {
    selectedSymbol = symbol;
    gameGuidance.textContent = `Click ${symbol} again to spend one hint and reveal its letter.`;
    renderReference();
    renderGame();
    return;
  }
  const response = await fetch(`/api/sessions/${game.session_id}/reveal/${symbol}`, { method: 'POST' });
  if (!response.ok) return;
  const hint = await response.json();
  revealed.set(symbol, hint.letter);
  propagated.add(symbol);
  selectedSymbol = undefined;
  gameGuidance.textContent = `${symbol}=${hint.letter} revealed and written throughout the puzzle.`;
  renderReference();
  renderGame();
}

function installGame(prepared) {
  game = prepared;
  gameTitle.textContent = game.title;
  revealed = new Map(Object.entries(game.clues).map(([symbol, letter]) => [Number(symbol), letter]));
  propagated = new Set(revealed.keys());
  selectedSymbol = undefined;
  selectedPuzzleCell = undefined;
  gameGuidance.textContent = 'Select a numbered cell, then click it again to reveal it throughout the puzzle.';
  renderGame();
  renderReference();
}

async function loadGame() {
  const response = game?.session_id
    ? await fetch(`/api/sessions/${game.session_id}`)
    : await fetch('/api/sessions/from-corpus/1', { method: 'POST' });
  if (!response.ok) {
    gameStatus.textContent = 'Puzzle unavailable';
    return false;
  }
  installGame(await response.json());
  return true;
}

showGameButton.addEventListener('click', startCorpusGame);
showScannerButton.addEventListener('click', () => showMode('scanner'));
showCreatorButton.addEventListener('click', () => showMode('creator'));
document.querySelector('#scan-from-game').addEventListener('click', () => showMode('scanner'));
document.querySelector('#reset-game').addEventListener('click', loadGame);
document.querySelector('#reveal-all').addEventListener('click', async () => {
  if (!game || !window.confirm('Reveal the complete puzzle?')) return;
  const response = await fetch(`/api/sessions/${game.session_id}/reveal`, { method: 'POST' });
  if (!response.ok) return;
  const data = await response.json();
  revealed = new Map(Object.entries(data.mapping).map(([symbol, letter]) => [Number(symbol), letter]));
  propagated = new Set(revealed.keys());
  selectedSymbol = undefined;
  gameGuidance.textContent = 'Complete solution revealed.';
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
  publishCreated.hidden = true;
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
  creatorProgressTitle.textContent = job.progress;
  creatorProgressDetail.textContent = `${job.elapsed_seconds}s elapsed`;
  if (job.status === 'complete') {
    const candidate = job.candidate;
    creatorProgressDetail.textContent = `${candidate.black_cells} black cells · ${candidate.clues} clues · certified unique`;
    publishCreated.hidden = false;
    cancelCreated.textContent = 'Discard';
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
  resultState.hidden = true;
  errorState.hidden = true;
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
  clearInterval(stageTimer);
  resultState.hidden = true;
  errorState.hidden = true;
  workingState.hidden = true;
  previewState.classList.remove('is-working');
  previewState.hidden = true;
  emptyState.hidden = false;
  selectedFile = undefined;
  input.value = '';
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

  try {
    const response = await fetch('/api/sessions/from-photo', { method: 'POST', body });
    if (!response.ok) {
      let message = 'Try another image with the complete puzzle in frame.';
      try {
        const data = await response.json();
        if (data.detail) message = data.detail;
      } catch (_) {
        // The friendly fallback is more useful than a response parsing error.
      }
      throw new Error(message);
    }

    installGame(await response.json());
    workingState.hidden = true;
    previewState.classList.remove('is-working');
    selectedFile = undefined;
    input.value = '';
    showMode('game');
  } catch (error) {
    workingState.hidden = true;
    previewState.classList.remove('is-working');
    previewState.hidden = false;
    errorState.hidden = false;
    errorMessage.textContent = error instanceof Error ? error.message : 'Please try another photograph.';
  } finally {
    clearInterval(stageTimer);
  }
});
