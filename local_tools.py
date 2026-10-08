"""Herramientas de la computadora local; instalaciones privadas, sin sudo."""
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
from urllib.request import Request, urlopen
import venv
import zipfile

ROOT = Path(__file__).resolve().parent / '.tools'
BIN = ROOT / 'bin'
INSTALL_LOCK = threading.Lock()
INSTALL_STATE = {'state': 'idle', 'message': ''}


def environment():
    env = os.environ.copy()
    env['PATH'] = str(BIN) + os.pathsep + env.get('PATH', '')
    return env


def python():
    private = ROOT / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    return str(private) if private.is_file() else sys.executable


def ytdlp_command():
    if python() != sys.executable:
        return [python(), '-m', 'yt_dlp']
    executable = shutil.which('yt-dlp', path=environment()['PATH'])
    return [executable] if executable else [sys.executable, '-m', 'yt_dlp']


def version(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15, env=environment())
        if result.returncode == 0:
            return result.stdout.splitlines()[0][:100]
    except (OSError, subprocess.SubprocessError, IndexError):
        pass
    return ''


def status():
    yt = version(ytdlp_command() + ['--version'])
    ff = version(['ffmpeg', '-version'])
    probe = version(['ffprobe', '-version'])
    deno = version(['deno', '--version'])
    match = re.match(r'deno (\d+)\.(\d+)\.(\d+)', deno)
    supported_deno = bool(match and tuple(map(int, match.groups())) >= (2, 3, 0))
    node = version(['node', '--version']) if not supported_deno else ''
    node_major = int(re.search(r'\d+', node)[0]) if re.search(r'\d+', node) else 0
    return {'ytDlp': {'installed': bool(yt), 'version': yt},
            'ffmpeg': {'installed': bool(ff and probe), 'version': ff},
            'youtube': {'installed': supported_deno or node_major >= 22, 'version': deno if supported_deno else node},
            'installation': INSTALL_STATE.copy()}


def missing():
    current = status()
    return [label for key, label in (('ytDlp', 'yt-dlp'), ('ffmpeg', 'FFmpeg/ffprobe'), ('youtube', 'soporte YouTube'))
            if not current[key]['installed']]


def fetch(url, target):
    request = Request(url, headers={'User-Agent': 'MiQuemi local installer'})
    with urlopen(request, timeout=30) as response, target.open('wb') as output:
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > 300 * 1024 * 1024:
                raise ValueError('La descarga de la herramienta supera el tamaño permitido.')
            output.write(chunk)


def extract_binaries(archive, names):
    """Copiar únicamente ejecutables elegidos; nunca extraer rutas del archivo."""
    BIN.mkdir(parents=True, exist_ok=True)
    found = set()

    def save(name, source):
        path = BIN / name
        temp = path.with_suffix(path.suffix + '.tmp')
        try:
            with temp.open('wb') as output:
                shutil.copyfileobj(source, output)
            temp.chmod(0o755)
            temp.replace(path)
            found.add(name)
        finally:
            temp.unlink(missing_ok=True)

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                name = member.filename.rsplit('/', 1)[-1]
                if name in names and not member.is_dir() and member.file_size <= 200 * 1024 * 1024:
                    with bundle.open(member) as source:
                        save(name, source)
    else:
        with tarfile.open(archive, 'r:xz') as bundle:
            for member in bundle:
                name = member.name.rsplit('/', 1)[-1]
                if name in names and member.isfile() and member.size <= 200 * 1024 * 1024:
                    with bundle.extractfile(member) as source:
                        save(name, source)
    if found != set(names):
        raise ValueError('El paquete no contiene las herramientas esperadas.')


def install_ffmpeg():
    system, machine = platform.system(), platform.machine().lower()
    if system == 'Linux' and machine in ('x86_64', 'amd64'):
        asset, names = 'ffmpeg-master-latest-linux64-gpl.tar.xz', ('ffmpeg', 'ffprobe')
    elif system == 'Windows' and machine in ('x86_64', 'amd64'):
        asset, names = 'ffmpeg-master-latest-win64-gpl.zip', ('ffmpeg.exe', 'ffprobe.exe')
    else:
        raise ValueError('La instalación automática de FFmpeg admite Linux y Windows de 64 bits. En macOS instala FFmpeg con Homebrew y vuelve a verificar.')
    INSTALL_STATE['message'] = 'Descargando FFmpeg y ffprobe. Puede tardar unos minutos…'
    with tempfile.TemporaryDirectory(prefix='install-', dir=ROOT) as temp:
        archive = Path(temp) / asset
        fetch('https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/' + asset, archive)
        extract_binaries(archive, names)


def install_ytdlp():
    INSTALL_STATE['message'] = 'Preparando yt-dlp en una carpeta privada de esta aplicación…'
    try:
        venv.EnvBuilder(with_pip=True).create(ROOT / 'venv')
    except (OSError, subprocess.SubprocessError):
        raise ValueError('Python necesita soporte venv/pip. En Ubuntu instala python3-venv y vuelve a pulsar Instalar yt-dlp.') from None
    subprocess.run([python(), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-cache-dir',
                    '-q', 'yt-dlp[default]'], capture_output=True, text=True, check=True, timeout=300)


def install_deno():
    system, machine = platform.system(), platform.machine().lower()
    arch = 'aarch64' if machine in ('aarch64', 'arm64') else 'x86_64' if machine in ('x86_64', 'amd64') else ''
    suffix = {'Linux': 'unknown-linux-gnu', 'Darwin': 'apple-darwin', 'Windows': 'pc-windows-msvc'}.get(system)
    if not arch or not suffix:
        raise ValueError('Instala Deno manualmente para habilitar YouTube en esta computadora.')
    name = 'deno.exe' if os.name == 'nt' else 'deno'
    INSTALL_STATE['message'] = 'Preparando el soporte de YouTube…'
    with tempfile.TemporaryDirectory(prefix='install-', dir=ROOT) as temp:
        archive = Path(temp) / 'deno.zip'
        fetch(f'https://github.com/denoland/deno/releases/latest/download/deno-{arch}-{suffix}.zip', archive)
        extract_binaries(archive, (name,))


def install(tool):
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        current = status()
        if tool == 'ffmpeg' and not current['ffmpeg']['installed']:
            install_ffmpeg()
        if tool == 'yt-dlp':
            if not current['ytDlp']['installed']:
                install_ytdlp()
            if not current['youtube']['installed']:
                install_deno()
        current = status()
        ready = current['ffmpeg']['installed'] if tool == 'ffmpeg' else current['ytDlp']['installed'] and current['youtube']['installed']
        if not ready:
            raise ValueError('La herramienta no pudo ejecutarse. Revisa su compatibilidad con esta computadora.')
        INSTALL_STATE.update(state='ready', message='Herramienta lista. Ya puedes volver a verificar o preparar una descarga.')
    except Exception as error:
        message = str(error) if isinstance(error, ValueError) else 'No se pudo instalar. Revisa tu conexión y los permisos de la carpeta del proyecto; vuelve a intentar.'
        INSTALL_STATE.update(state='error', message=message)
    finally:
        INSTALL_LOCK.release()


def start_install(tool):
    if tool not in ('yt-dlp', 'ffmpeg'):
        raise ValueError('Elige yt-dlp o FFmpeg.')
    if not INSTALL_LOCK.acquire(blocking=False):
        return False
    INSTALL_STATE.update(state='installing', message='Verificando herramientas…')
    try:
        threading.Thread(target=install, args=(tool,), daemon=True).start()
    except Exception:
        INSTALL_STATE.update(state='error', message='No se pudo iniciar la instalación. Intenta de nuevo.')
        INSTALL_LOCK.release()
        raise
    return True
