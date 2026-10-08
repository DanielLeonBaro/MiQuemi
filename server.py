"""MiQuemi: interfaz estática y una descarga a la vez, sin framework."""
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlsplit
import local_tools

WEB = Path(__file__).parent / 'web'
HOST = os.environ.get('HOST', '127.0.0.1')
SITES = ('youtube.com', 'youtu.be', 'instagram.com', 'facebook.com', 'fb.watch',
         'tiktok.com', 'vimeo.com', 'dailymotion.com', 'dai.ly', 'pinterest.com', 'pin.it')
QUALITIES = {'video': ('best', '1080', '720', '480'), 'audio': ('best', '192', '128', '96')}
ORIGINS = set(filter(None, (x.strip().rstrip('/') for x in os.environ.get('ALLOWED_ORIGINS', '').split(','))))
TTL = 15 * 60
MAX_BYTES = 100 * 1024 * 1024
MAX_DURATION = 20 * 60
MAX_JOBS = 3
JOB_TIMEOUT = 10 * 60
PREVIEW_TIMEOUT = 60
JOBS = {}
LOCK = threading.RLock()
BUSY = threading.Lock()


def validate_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Pega el enlace de un video.')
    value = value.strip()
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').lower()
        valid_port = parsed.port in (None, 443)
    except ValueError:
        raise ValueError('Ese enlace no es válido.') from None
    if (parsed.scheme != 'https' or not valid_port or parsed.username is not None
            or parsed.password is not None or any(ord(c) < 33 for c in value)
            or not any(host == site or host.endswith('.' + site) for site in SITES)):
        raise ValueError('Usa un enlace HTTPS de YouTube, Instagram, Facebook, TikTok, Vimeo, Dailymotion o Pinterest.')
    return value


def ytdlp_base():
    return local_tools.ytdlp_command() + ['--ignore-config', '--no-playlist',
            '--playlist-items', '1', '--use-extractors', 'default,-generic',
            '--no-warnings', '--no-colors', '--socket-timeout', '20',
            '--retries', '2', '--fragment-retries', '2', '--js-runtimes', 'node']


def format_options(kind, quality='best'):
    if kind == 'audio':
        return ['-f', 'ba/b', '-x', '--audio-format', 'mp3', '--audio-quality', '0' if quality == 'best' else quality + 'K']
    args = ['-f', 'bv*+ba/b', '--merge-output-format', 'mp4', '--remux-video', 'mp4']
    if quality != 'best':
        args += ['--format-sort-force', '-S', 'res:' + quality + ',fps']
    return args


def command(url, kind, folder, quality='best'):
    args = ytdlp_base() + ['--no-simulate', '--newline', '--progress',
            '--progress-template', 'download:PROGRESS:%(progress._percent_str)s',
            '--print', 'before_dl:TITLE:%(title)j', '--concurrent-fragments', '1',
            '--max-filesize', str(MAX_BYTES), '--match-filters', f'!is_live & duration <=? {MAX_DURATION}',
            '-o', str(folder / 'archivo.%(ext)s')]
    return args + format_options(kind, quality) + ['--', url]


def positive_number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0 else None


def format_size(info, duration):
    size = positive_number(info.get('filesize'))
    if size:
        return int(size), False
    size = positive_number(info.get('filesize_approx'))
    if size:
        return int(size), True
    rate = positive_number(info.get('tbr')) or ((positive_number(info.get('vbr')) or 0) + (positive_number(info.get('abr')) or 0))
    return (round(rate * 1000 * duration / 8), True) if rate and duration else (None, True)


def preview_data(info, kind, quality='best'):
    while info.get('_type') in ('playlist', 'multi_video'):
        entries = info.get('entries')
        if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
            raise ValueError('No pudimos consultar el primer video de esa publicación. Prueba con su enlace directo.')
        info = entries[0]  # --playlist-items 1 también prepara solo el primer video.
    duration = positive_number(info.get('duration'))
    parts = info.get('requested_formats') or [info]
    sizes = [format_size(part, duration) for part in parts]
    has_video = any(part.get('vcodec') != 'none' for part in parts)
    video_bytes = sum(size for size, _ in sizes) if has_video and all(size is not None for size, _ in sizes) else None
    dimensions = [positive_number(info.get(key)) for key in ('width', 'height')]
    resolution = int(min(dimensions)) if all(dimensions) else None
    audio_quality = quality if kind == 'audio' else 'best'
    rate = 320 if audio_quality == 'best' else int(audio_quality)
    return {'title': str(info.get('title') or '')[:200], 'duration': duration,
            'video': {'bytes': video_bytes, 'estimated': len(parts) > 1 or info.get('ext') != 'mp4' or any(estimated for _, estimated in sizes),
                      'resolution': resolution},
            # ponytail: VBR no tiene peso fijo; 320 kbps es una referencia superior, no el tamaño final.
            'mp3': {'bytes': round(duration * rate * 1000 / 8) if duration else None,
                    'estimated': True, 'upperBound': audio_quality == 'best'},
            'live': bool(info.get('is_live') or info.get('live_status') == 'is_live'),
            'limits': {'maxMinutes': MAX_DURATION // 60, 'maxMB': MAX_BYTES // (1024 * 1024)}}


def preview(url, kind, quality='best'):
    args = ytdlp_base() + format_options('video', quality if kind == 'video' else 'best')
    args += ['--simulate', '--skip-download', '--no-progress', '--dump-single-json', '--', url]
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding='utf-8', errors='replace', start_new_session=(os.name == 'posix'),
                               env=local_tools.environment())
    try:
        output, log = process.communicate(timeout=PREVIEW_TIMEOUT)
    except subprocess.TimeoutExpired:
        terminate(process)
        process.communicate()
        raise ValueError('La consulta tardó demasiado. Intenta de nuevo o prueba con otro enlace.') from None
    if process.returncode:
        raise ValueError(error_message(log[-30000:]))
    return preview_data(json.loads(output), kind, quality)


def error_message(log):
    log = log.lower()
    if 'ffmpeg' in log or 'ffprobe' in log:
        return 'Falta una herramienta de audio o video en el servidor. Pídele ayuda a quien configuró la página.'
    if any(x in log for x in ('sign in', 'login', 'cookies', 'private', '403', 'bot', '429')):
        return 'El sitio bloqueó la descarga o pide iniciar sesión. Prueba con otro video público.'
    if 'not available' in log or 'unavailable' in log:
        return 'Ese video o formato no está disponible para descargar. Prueba con otro enlace.'
    return 'No pudimos descargar ese video. Revisa el enlace o prueba con otro video público.'


def update(job, **values):
    with LOCK:
        job.update(values)


def terminate(process):
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()
    process.wait()


def folder_size(folder):
    size = 0
    for path in folder.rglob('*'):
        try:
            if path.is_file():
                size += path.stat().st_size
        except FileNotFoundError:
            pass  # yt-dlp renombra y elimina fragmentos durante la descarga.
    return size


def media_duration(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                             '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
                            capture_output=True, text=True, check=True, timeout=15, env=local_tools.environment())
    return float(result.stdout.strip())


def normalize_audio(path, quality, deadline):
    # yt-dlp conserva un MP3 existente; aplicar la tasa elegida también en ese caso.
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=bit_rate',
                            '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
                           capture_output=True, text=True, check=True, timeout=15, env=local_tools.environment())
    if probe.stdout.strip() == str(int(quality) * 1000):
        return
    target = path.with_name('calidad.mp3')
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-vn', '-c:a', 'libmp3lame',
                    '-b:a', quality + 'K', str(target)], capture_output=True, check=True,
                   timeout=max(.1, deadline - time.monotonic()), env=local_tools.environment())
    target.replace(path)


def download(job, url, kind, quality='best'):
    process = None
    logs = []
    try:
        folder = job['folder']
        process = subprocess.Popen(command(url, kind, folder, quality), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                   errors='replace', start_new_session=(os.name == 'posix'), env=local_tools.environment())

        def read_output():
            for line in process.stdout:
                if line.startswith('PROGRESS:'):
                    match = re.search(r'(\d+(?:\.\d+)?)%', line)
                    if match:
                        percent = min(100, float(match[1]))
                        update(job, progress=percent, message=('Terminando de preparar el archivo…' if percent >= 100
                                                              else 'Descargando tu archivo…'))
                elif line.startswith('TITLE:'):
                    try:
                        update(job, title=str(json.loads(line[6:]))[:200])
                    except ValueError:
                        pass
                else:
                    logs.append(line[:1000])
                    del logs[:-30]

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        deadline = time.monotonic() + JOB_TIMEOUT
        while process.poll() is None:
            if time.monotonic() > deadline:
                raise ValueError('La descarga tardó demasiado. Prueba con un video más corto.')
            if folder_size(folder) > MAX_BYTES * 2:
                raise ValueError('El archivo es demasiado grande. Elige una calidad menor, Solo audio o un video más corto.')
            time.sleep(.5)
        reader.join(timeout=5)
        if process.returncode:
            raise ValueError(error_message(''.join(logs)))
        extension = 'mp3' if kind == 'audio' else 'mp4'
        path = folder / ('archivo.' + extension)
        if not path.is_file():
            raise ValueError('No se pudo preparar. Puedes descargar publicaciones de hasta 20 minutos y 100 MB; las transmisiones en vivo no están disponibles.')
        if kind == 'audio' and quality != 'best':
            update(job, message='Ajustando la calidad del audio…')
            normalize_audio(path, quality, deadline)
        if path.stat().st_size > MAX_BYTES:
            raise ValueError('El archivo supera 100 MB. Elige una calidad menor, Solo audio o un video más corto.')
        duration = media_duration(path)
        if not 0 < duration <= MAX_DURATION:
            raise ValueError('El archivo supera 20 minutos o no informa una duración válida. Puedes descargar un video o audio más corto.')
        # ponytail: títulos solo para el nombre de descarga; la ruta en disco es fija.
        title = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]', '', job['title']).strip('. ')[:120] or 'MiQuemi'
        update(job, state='ready', progress=100, message='Tu archivo está listo.',
               filename=title + '.' + extension, path=path, expires=time.monotonic() + TTL)
    except Exception as error:
        if process is not None:
            terminate(process)
        message = str(error) if isinstance(error, ValueError) else 'No pudimos preparar el archivo. Intenta de nuevo.'
        update(job, state='error', message=message, expires=time.monotonic() + TTL)
        shutil.rmtree(job['folder'], ignore_errors=True)
    finally:
        if process is not None and process.stdout:
            process.stdout.close()
        BUSY.release()


def cleanup():
    with LOCK:
        for key, job in list(JOBS.items()):
            if job['state'] != 'working' and job['expires'] < time.monotonic():
                shutil.rmtree(job['folder'], ignore_errors=True)
                del JOBS[key]


def limits_status():
    cleanup()
    with LOCK:
        ready = [job for job in JOBS.values() if job['state'] == 'ready']
        wait = max(1, int(min(job['expires'] for job in ready) - time.monotonic()) + 1) if len(ready) >= MAX_JOBS else 0
        return {'maxMinutes': MAX_DURATION // 60, 'maxMB': MAX_BYTES // (1024 * 1024),
                'maxFiles': MAX_JOBS, 'fileMinutes': TTL // 60, 'availableFiles': max(0, MAX_JOBS - len(ready)),
                'busy': BUSY.locked(), 'retryAfter': wait}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # Las URL de archivos son capacidades privadas; no las registramos.

    def headers_for(self, status, content_type, length=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        origin = self.headers.get('Origin')
        if origin in ORIGINS:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        if length is not None:
            self.send_header('Content-Length', str(length))

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.headers_for(status, 'application/json; charset=utf-8', len(body))
        self.end_headers()
        self.wfile.write(body)

    def is_local(self):
        local = {'localhost', '127.0.0.1', '::1'}
        try:
            host = urlsplit('http://' + self.headers.get('Host', '')).hostname
            origin = self.headers.get('Origin')
            origin_host = urlsplit(origin).hostname if origin else host
        except ValueError:
            return False
        return (HOST in local and self.client_address[0] in local and host in local
                and origin_host in local and not self.headers.get('X-Forwarded-For')
                and not self.headers.get('X-Forwarded-Host'))

    def origin_allowed(self):
        origin = self.headers.get('Origin')
        if not origin or origin in ORIGINS:
            return True
        parsed = urlsplit(origin)
        if parsed.scheme in ('http', 'https') and parsed.netloc == self.headers.get('Host'):
            return True
        self.send_json(403, {'error': 'Esta página no tiene acceso al servidor.'})
        return False

    def do_OPTIONS(self):
        if not self.origin_allowed():
            return
        self.headers_for(204, 'text/plain', 0)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health':
            return self.send_json(200, {'ok': True})
        if path == '/api/tools':
            return self.send_json(200, {'local': True, **local_tools.status()} if self.is_local() else {'local': False})
        if path == '/api/limits':
            return self.send_json(200, limits_status())
        if path.startswith('/api/jobs/') or path.startswith('/api/files/'):
            cleanup()
            with LOCK:
                job = JOBS.get(path.rsplit('/', 1)[-1])
                if not job:
                    return self.send_json(404, {'error': 'El archivo venció o el servidor reinició. Prepara la descarga otra vez.'})
                if path.startswith('/api/jobs/'):
                    return self.send_json(200, {k: job[k] for k in ('state', 'message', 'progress', 'title', 'filename')})
                if job['state'] != 'ready':
                    return self.send_json(409, {'error': 'El archivo todavía no está listo.'})
                # Abrir antes de liberar el lock: la limpieza no puede quitar el archivo durante la apertura.
                media = job['path'].open('rb')
                size = os.fstat(media.fileno()).st_size
                filename = job['filename']
            with media:
                self.headers_for(200, mimetypes.guess_type(filename)[0] or 'application/octet-stream', size)
                self.send_header('Content-Disposition', "attachment; filename=MiQuemi." + job['path'].suffix[1:]
                                 + "; filename*=UTF-8''" + quote(filename, safe=''))
                self.end_headers()
                try:
                    shutil.copyfileobj(media, self.wfile, 64 * 1024)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            return
        name = 'index.html' if path == '/' else path.lstrip('/')
        if name not in ('index.html', 'style.css', 'app.js', 'config.js', 'icon.svg'):
            return self.send_json(404, {'error': 'Página no encontrada.'})
        body = (WEB / name).read_bytes()
        self.headers_for(200, (mimetypes.guess_type(name)[0] or 'text/plain') + '; charset=utf-8', len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == '/api/tools/install':
            if not self.is_local():
                return self.send_json(403, {'error': 'La instalación desde la página está disponible solamente en localhost.'})
            if not self.origin_allowed():
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 256 or self.headers.get('Transfer-Encoding'):
                    raise ValueError('Solicitud no válida.')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('Solicitud no válida.')
                with LOCK:
                    if BUSY.locked():
                        return self.send_json(409, {'error': 'Espera a que termine la descarga antes de instalar herramientas.'})
                    started = local_tools.start_install(data.get('tool'))
            except (ValueError, TypeError, UnicodeError):
                return self.send_json(400, {'error': 'Elige yt-dlp o FFmpeg.'})
            return self.send_json(202 if started else 409, {'ok': started, 'error': '' if started else 'Ya hay una instalación en curso.'})
        if path not in ('/api/jobs', '/api/preview'):
            return self.send_json(404, {'error': 'Página no encontrada.'})
        if not self.origin_allowed():
            return
        if local_tools.INSTALL_LOCK.locked():
            return self.send_json(409, {'error': 'Espera a que termine la instalación de herramientas.'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096 or self.headers.get('Transfer-Encoding'):
                raise ValueError('El enlace enviado es demasiado largo o no es válido.')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Pega el enlace de un video.')
            url = validate_url(data.get('url'))
            kind = data.get('format')
            if kind not in ('video', 'audio'):
                raise ValueError('Elige Video o Solo audio.')
            quality = data.get('quality', 'best')
            if not isinstance(quality, str) or quality not in QUALITIES[kind]:
                raise ValueError('Elige una calidad válida para video o audio.')
        except (ValueError, TypeError, UnicodeError) as error:
            return self.send_json(400, {'error': str(error) if not isinstance(error, json.JSONDecodeError) else 'El enlace enviado no es válido.'})
        missing = local_tools.missing()
        if 'soporte YouTube' in missing and not any((urlsplit(url).hostname or '').endswith(site) for site in ('youtube.com', 'youtu.be')):
            missing.remove('soporte YouTube')
        if missing:
            return self.send_json(503, {'error': 'Falta instalar: ' + ', '.join(missing) + '. En localhost usa los botones de herramientas para instalarlo.'})
        with LOCK:
            if local_tools.INSTALL_LOCK.locked():
                return self.send_json(409, {'error': 'Espera a que termine la instalación de herramientas.'})
            acquired = BUSY.acquire(blocking=False)
        if not acquired:
            return self.send_json(429, {'error': 'Hay una consulta o descarga en curso. Espera a que termine para continuar.',
                                        'limits': limits_status()})
        if path == '/api/preview':
            try:
                status, result = 200, preview(url, kind, quality)
            except ValueError as error:
                status, result = 422, {'error': str(error) if not isinstance(error, json.JSONDecodeError)
                                      else 'No pudimos consultar los datos de ese video. Puedes intentar preparar la descarga.'}
            except Exception:
                status, result = 502, {'error': 'No pudimos consultar los datos de ese video. Puedes intentar preparar la descarga.'}
            finally:
                BUSY.release()
            return self.send_json(status, result)
        try:
            cleanup()
            with LOCK:
                # Los intentos fallidos no deben ocupar los tres lugares para archivos.
                if len(JOBS) >= MAX_JOBS:
                    for key, previous in list(JOBS.items()):
                        if previous['state'] == 'error':
                            del JOBS[key]
                            break
                if len(JOBS) >= MAX_JOBS:
                    BUSY.release()
                    return self.send_json(429, {'error': 'Ya hay tres archivos listos. Cuando venza el primero podrás preparar otro video o audio.',
                                                'limits': limits_status()})
                job_id = secrets.token_urlsafe(32)
                job = {'state': 'working', 'message': 'Buscando tu video…', 'progress': None,
                       'title': '', 'filename': '', 'folder': Path(tempfile.mkdtemp(prefix='miquemi-')),
                       'expires': float('inf')}
                JOBS[job_id] = job
            threading.Thread(target=download, args=(job, url, kind, quality), daemon=True).start()
        except Exception:
            BUSY.release()
            return self.send_json(500, {'error': 'No pudimos iniciar la descarga. Intenta de nuevo.'})
        self.send_json(202, {'id': job_id})

    def setup(self):
        super().setup()
        self.connection.settimeout(30)


def reap():
    while True:
        time.sleep(30)
        cleanup()


if __name__ == '__main__':
    threading.Thread(target=reap, daemon=True).start()
    address = (HOST, int(os.environ.get('PORT', '8000')))
    http = ThreadingHTTPServer(address, Handler)
    print(f'MiQuemi listo en http://{address[0]}:{address[1]}', flush=True)
    if '--open-browser' in sys.argv:
        threading.Thread(target=webbrowser.open, args=(f'http://127.0.0.1:{address[1]}/',), daemon=True).start()
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        print('\nMiQuemi detenido.', flush=True)
    finally:
        http.server_close()
