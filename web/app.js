const form = document.querySelector('#download-form');
const urlInput = document.querySelector('#url');
const quality = document.querySelector('#quality');
const submit = document.querySelector('#submit');
const preview = document.querySelector('#preview');
const previewPanel = document.querySelector('#preview-panel');
const previewTitle = document.querySelector('#preview-title');
const previewData = previewPanel.querySelector('dl');
const previewNote = document.querySelector('#preview-note');
const previewWarning = document.querySelector('#preview-warning');
const panel = document.querySelector('#status-panel');
const statusText = document.querySelector('#status');
const progress = document.querySelector('#progress');
const save = document.querySelector('#save');
const saveHelp = document.querySelector('#save-help');
const api = (window.MIQUEMI_API || '').replace(/\/$/, '');
let releaseAt = 0;
let waitTimer;
let downloading = false;
let previewing = false;
let selectionRevision = 0;

function syncActions() {
  submit.disabled = downloading || previewing || releaseAt > Date.now();
  preview.disabled = downloading || previewing;
  preview.textContent = previewing ? 'Consultando…' : 'Ver duración y peso';
  if (releaseAt <= Date.now()) submit.querySelector('span').textContent = 'Preparar descarga';
}

function invalidateSelection() {
  selectionRevision += 1;
  previewPanel.hidden = save.hidden = saveHelp.hidden = true;
  if (!downloading) panel.hidden = true;
}

function selection() {
  return { url: urlInput.value.trim(), format: new FormData(form).get('format'), quality: quality.value };
}

function setQualityOptions() {
  const audio = new FormData(form).get('format') === 'audio';
  const options = audio
    ? [['best', 'Mejor calidad disponible'], ['192', 'MP3 a 192 kbps'], ['128', 'MP3 a 128 kbps'], ['96', 'MP3 a 96 kbps']]
    : [['best', 'Mejor calidad disponible'], ['1080', 'Preferir 1080p'], ['720', 'Preferir 720p'], ['480', 'Preferir 480p']];
  quality.replaceChildren(...options.map(([value, label]) => new Option(label, value)));
  quality.value = 'best';
  document.querySelector('#quality-help').textContent = 'La mejor calidad viene seleccionada. Puedes elegir menos calidad para un archivo más pequeño.'
    + (audio ? '' : ' Si el sitio no ofrece esa resolución o una menor, se usa la menor disponible.');
}

form.querySelectorAll('[name="format"]').forEach(input => input.addEventListener('change', () => {
  setQualityOptions();
  invalidateSelection();
}));
urlInput.addEventListener('input', invalidateSelection);
quality.addEventListener('change', invalidateSelection);
setQualityOptions();

function renderLimits(limits) {
  document.querySelector('#limits-summary').textContent =
    `Hasta ${limits.maxMinutes} min · ${limits.maxMB} MB por archivo · Uno a la vez`;
  document.querySelector('#limits-availability').textContent =
    `${limits.availableFiles} de ${limits.maxFiles} lugares disponibles. Cada enlace dura ${limits.fileMinutes} minutos.`;
  clearInterval(waitTimer);
  releaseAt = limits.retryAfter ? Date.now() + limits.retryAfter * 1000 : 0;
  const wait = document.querySelector('#limit-wait');
  wait.hidden = !releaseAt;
  syncActions();
  if (!releaseAt) return;
  const tick = () => {
    const seconds = Math.max(0, Math.ceil((releaseAt - Date.now()) / 1000));
    const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    wait.textContent = `Límite de archivos alcanzado. Puedes preparar otro video o audio en ${clock}.`;
    submit.querySelector('span').textContent = `Disponible en ${clock}`;
    if (!seconds) {
      clearInterval(waitTimer);
      releaseAt = 0;
      wait.textContent = 'Ya puedes intentar preparar otro video o audio.';
      document.querySelector('#limits-availability').textContent = 'Venció un enlace anterior. El cupo se comprueba al preparar la descarga.';
    }
    syncActions();
  };
  tick();
  waitTimer = setInterval(tick, 1000);
}

function show(message, kind = 'working') {
  panel.hidden = false;
  panel.dataset.kind = kind;
  statusText.textContent = message;
  progress.hidden = kind !== 'working';
  if (kind === 'working') progress.removeAttribute('value');
}

async function request(path, options = {}, timeout = 90000) {
  let response;
  try {
    response = await fetch(api + path, {
      ...options,
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(timeout),
      cache: 'no-store',
    });
  } catch {
    throw new Error('No pudimos conectar. Revisa tu internet o intenta de nuevo en un minuto.');
  }
  let data;
  try { data = await response.json(); } catch {
    throw new Error('El servicio no está disponible. Intenta de nuevo en un minuto.');
  }
  if (!response.ok) {
    if (data.limits) renderLimits(data.limits);
    throw new Error(data.error || 'No pudimos preparar el archivo. Intenta con otro enlace.');
  }
  return data;
}

document.querySelector('#paste').addEventListener('click', async () => {
  try {
    urlInput.value = (await navigator.clipboard.readText()).trim();
    invalidateSelection();
    urlInput.focus();
  } catch {
    urlInput.focus();
    show('Mantén presionado el campo del enlace y elige Pegar.', 'info');
  }
});

function previewSize(item) {
  if (!Number.isFinite(item.bytes) || item.bytes <= 0) return 'No informado';
  const megabytes = item.bytes / (1024 * 1024);
  const amount = megabytes >= 1 ? megabytes : item.bytes / 1024;
  const size = new Intl.NumberFormat('es', { maximumFractionDigits: 1 }).format(amount);
  return (item.upperBound ? 'Hasta ≈ ' : item.estimated ? '≈ ' : '') + size + (megabytes >= 1 ? ' MB' : ' KB');
}

function renderPreview(data, selected) {
  previewTitle.textContent = data.title || 'Datos del archivo';
  const seconds = Math.round(data.duration);
  document.querySelector('#preview-duration').textContent = Number.isFinite(data.duration) && data.duration > 0
    ? `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}` : 'No informado';
  document.querySelector('#preview-video').textContent = previewSize(data.video)
    + (data.video.resolution ? ` · ${data.video.resolution}p` : '');
  document.querySelector('#preview-mp3').textContent = previewSize(data.mp3);
  previewNote.textContent = '≈ significa aproximado. El peso final puede variar.'
    + (data.mp3.upperBound ? ' Para MP3 en mejor calidad mostramos una referencia máxima; puede pesar menos.' : '');
  const warnings = [];
  if (data.live) warnings.push('Las transmisiones en vivo no se pueden descargar.');
  if (data.duration > data.limits.maxMinutes * 60) warnings.push(`Supera los ${data.limits.maxMinutes} minutos permitidos. Elige un video más corto.`);
  const active = selected.format === 'audio' ? data.mp3 : data.video;
  if (active.bytes > data.limits.maxMB * 1024 * 1024) warnings.push(`El ${selected.format === 'audio' ? 'MP3' : 'video'} puede superar ${data.limits.maxMB} MB. Elige menos calidad${selected.format === 'video' ? ' o Solo audio' : ''}.`);
  previewWarning.textContent = warnings.join(' ');
  previewWarning.hidden = !warnings.length;
  previewData.hidden = false;
}

preview.addEventListener('click', async () => {
  if (downloading || previewing || !form.reportValidity()) return;
  const selected = selection();
  const revision = selectionRevision;
  previewing = true;
  syncActions();
  previewPanel.hidden = false;
  previewData.hidden = previewWarning.hidden = true;
  previewTitle.textContent = 'Consultando duración y peso. Si el servicio está dormido, puede tardar un minuto.';
  previewNote.textContent = '';
  try {
    const data = await request('/api/preview', { method: 'POST', body: JSON.stringify(selected) }, 150000);
    if (revision === selectionRevision) renderPreview(data, selected);
  } catch (error) {
    if (revision === selectionRevision) {
      previewTitle.textContent = error.message;
      previewNote.textContent = 'Puedes intentar preparar la descarga directamente.';
    }
  } finally {
    previewing = false;
    syncActions();
  }
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (downloading || previewing || releaseAt > Date.now()) return;
  const selected = selection();
  const revision = selectionRevision;
  downloading = true;
  syncActions();
  save.hidden = saveHelp.hidden = true;
  show('Conectando para preparar tu archivo. Si el servicio está dormido, puede tardar un minuto.');
  try {
    const limits = await request('/api/limits');
    renderLimits(limits);
    if (limits.retryAfter) throw new Error('Ya hay tres archivos listos. Abajo puedes ver cuánto falta para preparar otro video o audio.');
    const job = await request('/api/jobs', {
      method: 'POST',
      body: JSON.stringify(selected),
    });
    // ponytail: una descarga por página; sondeo simple para evitar conexiones persistentes.
    for (;;) {
      const result = await request('/api/jobs/' + job.id);
      if (result.state === 'error') throw new Error(result.message);
      if (result.state === 'ready') {
        if (revision !== selectionRevision) {
          show('El archivo anterior quedó listo. Prepara la descarga con tu selección actual.', 'info');
          break;
        }
        show(result.title ? `Listo: ${result.title}` : '¡Tu archivo está listo!', 'ready');
        save.href = api + '/api/files/' + job.id;
        save.setAttribute('download', result.filename);
        save.hidden = saveHelp.hidden = false;
        statusText.focus();
        // El archivo ya está listo; un fallo al consultar el cupo no debe ocultarlo.
        try { renderLimits(await request('/api/limits')); } catch {}
        break;
      }
      show(result.message);
      if (result.progress !== null) progress.value = result.progress;
      await new Promise(resolve => setTimeout(resolve, 1500));
    }
  } catch (error) {
    show(error.message, 'error');
    statusText.focus();
  } finally {
    downloading = false;
    syncActions();
  }
});

const toolsPanel = document.querySelector('#tools-panel');
const toolsStatus = document.querySelector('#tools-status');
const verify = document.querySelector('#verify-tools');
const installButtons = [...document.querySelectorAll('[data-install]')];

function renderTools(data) {
  toolsPanel.hidden = !data.local;
  if (!data.local) return;
  document.querySelector('#hosting-quota').textContent = 'Modo local: usa la conexión de esta computadora. No aplica el cupo mensual de Render.';
  document.querySelector('#hosting-help').hidden = true;
  const ytReady = data.ytDlp.installed && data.youtube.installed;
  const ready = ytReady && data.ffmpeg.installed;
  document.querySelector('#tools-badge').textContent = ready ? 'Listas para descargar' : 'Faltan herramientas';
  if (!ready) toolsPanel.open = true;
  document.querySelector('#yt-state').textContent = data.ytDlp.installed ? `Instalado · ${data.ytDlp.version}` : 'No está instalado';
  document.querySelector('#ff-state').textContent = data.ffmpeg.installed ? 'Instalados y funcionando' : 'Falta FFmpeg o ffprobe';
  document.querySelector('#youtube-state').textContent = data.youtube.installed ? 'Soporte de YouTube listo.' : 'Para YouTube falta su motor. El botón de yt-dlp también lo instala.';
  const busy = data.installation.state === 'installing';
  verify.disabled = busy;
  installButtons[0].disabled = busy || ytReady;
  installButtons[0].textContent = ytReady ? 'Disponible' : data.ytDlp.installed ? 'Preparar YouTube' : 'Instalar yt-dlp';
  installButtons[1].disabled = busy || data.ffmpeg.installed;
  installButtons[1].textContent = data.ffmpeg.installed ? 'Disponible' : 'Instalar FFmpeg';
  toolsStatus.textContent = data.installation.message || (ready ? 'Todo listo. Esta página utiliza las herramientas de esta computadora.' : 'Instala lo que falta con los botones de arriba.');
}

async function verifyTools(quiet = false) {
  if (!quiet) toolsStatus.textContent = 'Verificando herramientas…';
  try {
    for (;;) {
      const data = await request('/api/tools');
      renderTools(data);
      if (!data.local || data.installation.state !== 'installing') return data;
      await new Promise(resolve => setTimeout(resolve, 1500));
    }
  } catch (error) {
    if (!quiet) toolsStatus.textContent = error.message;
    verify.disabled = false;
  }
}

async function installTool(tool) {
  verify.disabled = true;
  installButtons.forEach(button => { button.disabled = true; });
  toolsStatus.textContent = 'Preparando instalación…';
  try {
    await request('/api/tools/install', { method: 'POST', body: JSON.stringify({ tool }) });
    await verifyTools();
  } catch (error) {
    await verifyTools(true);
    toolsStatus.textContent = error.message;
    verify.disabled = false;
  }
}

verify.addEventListener('click', () => verifyTools());
installButtons.forEach(button => button.addEventListener('click', () => installTool(button.dataset.install)));
verifyTools(true);
