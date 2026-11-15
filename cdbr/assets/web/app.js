const form = document.querySelector('#solver-form');
const input = document.querySelector('#photo');
const dropZone = document.querySelector('#drop-zone');
const emptyState = document.querySelector('#empty-state');
const previewState = document.querySelector('#preview-state');
const previewImage = document.querySelector('#preview-image');
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

let previewUrl;
let resultUrl;
let selectedFile;
let stageTimer;

const workingStages = [
  'Finding the puzzle grid…',
  'Reading the numbered cells…',
  'Checking the reference clues…',
  'Cracking the letter code…',
  'Writing in the answers…',
];

function humanSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

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
  previewImage.onerror = () => {
    previewImage.hidden = true;
    fileFallback.hidden = false;
  };
}

function chooseAgain() {
  clearInterval(stageTimer);
  resultState.hidden = true;
  errorState.hidden = true;
  workingState.hidden = true;
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

  previewState.hidden = true;
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
    const response = await fetch('/solve', { method: 'POST', body });
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

    const blob = await response.blob();
    revoke(resultUrl);
    resultUrl = URL.createObjectURL(blob);
    resultImage.src = resultUrl;
    downloadResult.href = resultUrl;
    const stem = (selectedFile.name || 'codebreak').replace(/\.[^.]+$/, '');
    downloadResult.download = `${stem}_solved.jpg`;

    const complete = response.headers.get('X-Cdbr-Solution') === 'complete';
    const count = response.headers.get('X-Cdbr-Solutions-Found') || '0';
    resultKicker.textContent = complete ? 'Puzzle solved' : 'Best available answer';
    resultDetail.textContent = complete
      ? `Complete solution · ${count} matching solution${count === '1' ? '' : 's'} found`
      : 'The solver returned its best partial answer. A clearer photograph may improve it.';
    workingState.hidden = true;
    resultState.hidden = false;
    resultState.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    workingState.hidden = true;
    errorState.hidden = false;
    errorMessage.textContent = error instanceof Error ? error.message : 'Please try another photograph.';
  } finally {
    clearInterval(stageTimer);
  }
});
