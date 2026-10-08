"""Checks sin red: límites, acceso, archivos y errores de una descarga."""
import json
from importlib.util import find_spec
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server


class DownloadCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.ORIGINS = {'https://family.github.io'}
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.base = 'http://127.0.0.1:' + str(cls.http.server_port)
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()

    def setUp(self):
        self.probe = patch.object(server, 'media_duration', return_value=1)
        self.probe.start()
        self.addCleanup(self.probe.stop)
        self.dependencies = patch.object(server.local_tools, 'missing', return_value=[])
        self.dependencies.start()
        self.addCleanup(self.dependencies.stop)

    def tearDown(self):
        deadline = time.monotonic() + 5
        while server.BUSY.locked() and time.monotonic() < deadline:
            time.sleep(.05)
        with server.LOCK:
            for job in server.JOBS.values():
                shutil.rmtree(job['folder'], ignore_errors=True)
            server.JOBS.clear()

    def request(self, path, data=None, origin=None, method=None, extra_headers=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        headers.update(extra_headers or {})
        body = json.dumps(data).encode() if data is not None else None
        request = Request(self.base + path, body, headers, method=method)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            result = json.loads(raw) if 'json' in response.headers.get('Content-Type', '') else raw
            return response.status, result, response.headers

    def wait_job(self, job_id):
        for _ in range(100):
            status, data, _ = self.request('/api/jobs/' + job_id)
            self.assertEqual(status, 200)
            if data['state'] != 'working':
                return data
            time.sleep(.05)
        self.fail('La descarga de prueba no terminó.')

    @staticmethod
    def fake_command(url, kind, folder, quality='best'):
        extension = 'mp3' if kind == 'audio' else 'mp4'
        script = ("import pathlib,time; print('TITLE:\"Receta de mamá\"',flush=True); "
                  "print('PROGRESS: 50%',flush=True); time.sleep(.2); "
                  "pathlib.Path(__import__('sys').argv[1]).write_bytes(b'media-check')")
        return [sys.executable, '-c', script, str(folder / ('archivo.' + extension))]

    def test_download_video_and_audio(self):
        for kind in ('video', 'audio'):
            with self.subTest(kind=kind), patch.object(server, 'command', self.fake_command):
                status, result, _ = self.request('/api/jobs', {'url': 'https://youtu.be/example', 'format': kind})
                self.assertEqual(status, 202)
                job_id = result['id']
                self.assertEqual(self.request('/api/jobs/' + job_id)[0], 200)
                job = self.wait_job(job_id)
                self.assertEqual(job['state'], 'ready')
                status, media, headers = self.request('/api/files/' + job_id)
                self.assertEqual((status, media), (200, b'media-check'))
                self.assertIn("filename*=UTF-8''Receta%20de%20mam%C3%A1", headers['Content-Disposition'])
                self.assertNotIn('folder', job)
                self.assertNotIn('path', job)
                server.JOBS[job_id]['expires'] = 0
                folder = server.JOBS[job_id]['folder']
                self.assertEqual(self.request('/api/files/' + job_id)[0], 404)
                self.assertFalse(folder.exists())

    def test_boundaries(self):
        for url in ('http://youtube.com/a', 'https://youtube.com.evil.test/a',
                    'https://localhost/a', 'file:///etc/passwd', 'https://youtube.com:8000/a',
                    'https://user:password@youtube.com/a', 'https://youtube.com/a\nb'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                server.validate_url(url)
        self.assertEqual(server.validate_url(' https://www.youtube.com/watch?v=a '), 'https://www.youtube.com/watch?v=a')
        data = {'url': 'https://youtu.be/example', 'format': 'video'}
        self.assertEqual(self.request('/api/jobs', data, origin='https://evil.test')[0], 403)
        self.assertEqual(self.request('/api/jobs', {**data, 'format': 'exe'})[0], 400)
        status, _, headers = self.request('/api/jobs', origin='https://family.github.io', method='OPTIONS')
        self.assertEqual(status, 204)
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'https://family.github.io')
        self.assertEqual(self.request('/../server.py')[0], 404)
        self.assertEqual(self.request('/api/files/unknown')[0], 404)
        self.assertEqual(self.request('/api/jobs', data=[1, 2])[0], 400)
        self.assertEqual(self.request('/api/jobs', {'url': 'x' * 5000, 'format': 'video'})[0], 400)

    def test_quality_validation_and_download(self):
        data = {'url': 'https://youtu.be/example', 'format': 'video'}
        for kind, quality in (('video', '96'), ('audio', '720'), ('video', '--exec=bad'),
                              ('video', None), ('video', 720), ('audio', ['128'])):
            with self.subTest(kind=kind, quality=quality):
                self.assertEqual(self.request('/api/jobs', {**data, 'format': kind, 'quality': quality})[0], 400)
        for kind, quality in (('video', '720'), ('audio', '96')):
            with self.subTest(kind=kind), patch.object(server, 'command', side_effect=self.fake_command) as command, \
                    patch.object(server, 'normalize_audio') as normalize:
                status, result, _ = self.request('/api/jobs', {**data, 'format': kind, 'quality': quality})
                self.assertEqual(status, 202)
                self.assertEqual(self.wait_job(result['id'])['state'], 'ready')
                self.assertEqual(command.call_args.args[3], quality)
                self.assertEqual(normalize.call_count, int(kind == 'audio'))

    def test_busy_and_error_cleanup(self):
        data = {'url': 'https://youtu.be/example', 'format': 'video'}
        with patch.object(server, 'command', self.fake_command):
            status, job, _ = self.request('/api/jobs', data)
            self.assertEqual(status, 202)
            self.assertEqual(self.request('/api/jobs', data)[0], 429)
            self.wait_job(job['id'])
        def failing_command(*_):
            return [sys.executable, '-c', "print('ERROR: sign in to confirm you are not a bot'); exit(1)"]
        with patch.object(server, 'command', failing_command):
            _, job, _ = self.request('/api/jobs', data)
            result = self.wait_job(job['id'])
            self.assertEqual(result['state'], 'error')
            self.assertIn('bloqueó', result['message'])
            self.assertFalse(server.JOBS[job['id']]['folder'].exists())
            self.assertFalse(server.BUSY.locked())

    def test_resource_limit(self):
        def oversized_command(url, kind, folder, quality='best'):
            return [sys.executable, '-c', "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(b'x'*100)",
                    str(folder / 'archivo.mp4')]
        with patch.object(server, 'MAX_BYTES', 10), patch.object(server, 'command', oversized_command):
            _, job, _ = self.request('/api/jobs', {'url': 'https://youtu.be/example', 'format': 'video'})
            result = self.wait_job(job['id'])
            self.assertEqual(result['state'], 'error')
            self.assertFalse(server.JOBS[job['id']]['folder'].exists())

    def test_failed_attempts_do_not_block_next_download(self):
        def failing_command(*_):
            return [sys.executable, '-c', "print('ERROR: unavailable'); exit(1)"]
        data = {'url': 'https://youtu.be/example', 'format': 'video'}
        with patch.object(server, 'command', failing_command):
            for _ in range(4):
                status, job, _ = self.request('/api/jobs', data)
                self.assertEqual(status, 202)
                self.assertEqual(self.wait_job(job['id'])['state'], 'error')
        with patch.object(server, 'command', self.fake_command):
            status, job, _ = self.request('/api/jobs', data)
            self.assertEqual(status, 202)
            self.assertEqual(self.wait_job(job['id'])['state'], 'ready')
            self.assertLessEqual(len(server.JOBS), 3)

    def test_limits_and_expiry_release_a_slot(self):
        self.assertEqual(self.request('/api/limits')[0], 200)
        self.assertEqual(self.request('/api/limits')[1]['availableFiles'], 3)
        data = {'url': 'https://youtu.be/example', 'format': 'video'}
        with patch.object(server, 'command', self.fake_command):
            ids = []
            for _ in range(3):
                status, job, _ = self.request('/api/jobs', data)
                self.assertEqual(status, 202)
                self.assertEqual(self.wait_job(job['id'])['state'], 'ready')
                ids.append(job['id'])
            status, result, _ = self.request('/api/jobs', data)
            self.assertEqual(status, 429)
            self.assertEqual(result['limits']['availableFiles'], 0)
            self.assertGreater(result['limits']['retryAfter'], 0)
            self.assertLessEqual(result['limits']['retryAfter'], server.TTL)
            server.JOBS[ids[0]]['expires'] = time.monotonic() - 1
            limits = self.request('/api/limits')[1]
            self.assertEqual(limits['availableFiles'], 1)
            self.assertEqual(limits['retryAfter'], 0)
            status, job, _ = self.request('/api/jobs', data)
            self.assertEqual(status, 202)
            self.assertEqual(self.wait_job(job['id'])['state'], 'ready')

    def test_unknown_source_duration_still_has_final_limit(self):
        with patch.object(server, 'command', self.fake_command), patch.object(server, 'media_duration', return_value=1201):
            _, job, _ = self.request('/api/jobs', {'url': 'https://youtu.be/example', 'format': 'audio'})
            result = self.wait_job(job['id'])
            self.assertEqual(result['state'], 'error')
            self.assertIn('20 minutos', result['message'])
            self.assertFalse(server.JOBS[job['id']]['folder'].exists())

    def test_installation_requires_local_host(self):
        data = {'tool': 'ffmpeg'}
        self.assertEqual(self.request('/api/tools/install', data, origin='https://family.github.io')[0], 403)
        self.assertEqual(self.request('/api/tools/install', data, extra_headers={'Host': 'evil.test'})[0], 403)
        self.assertEqual(self.request('/api/tools/install', data, extra_headers={'X-Forwarded-For': '8.8.8.8'})[0], 403)
        self.assertEqual(self.request('/api/tools/install', {'tool': 'ffmpeg; rm -rf /'})[0], 400)
        with patch.object(server, 'HOST', '0.0.0.0'):
            self.assertEqual(self.request('/api/tools')[1], {'local': False})
            self.assertEqual(self.request('/api/tools/install', data)[0], 403)
        with patch.object(server.local_tools, 'start_install', return_value=True) as installer:
            self.assertEqual(self.request('/api/tools/install', data)[0], 202)
            installer.assert_called_once_with('ffmpeg')

    def test_public_downloads_do_not_require_a_code(self):
        with patch.object(server, 'HOST', '0.0.0.0'), patch.object(server, 'command', self.fake_command):
            self.assertEqual(self.request('/api/limits')[0], 200)
            status, result, headers = self.request('/api/jobs', {'url': 'https://youtu.be/example', 'format': 'video'},
                                                   origin='https://family.github.io')
            self.assertEqual(status, 202)
            self.assertEqual(headers['Access-Control-Allow-Origin'], 'https://family.github.io')
            job = self.wait_job(result['id'])
            self.assertEqual(job['state'], 'ready')
            self.assertEqual(self.request('/api/files/' + result['id'])[0], 200)
            self.assertEqual(self.request('/api/tools/install', {'tool': 'ffmpeg'})[0], 403)

    def test_missing_tools_explain_how_to_install(self):
        with patch.object(server.local_tools, 'missing', return_value=['FFmpeg/ffprobe']):
            status, result, _ = self.request('/api/jobs', {'url': 'https://youtu.be/example', 'format': 'audio'})
            self.assertEqual(status, 503)
            self.assertIn('botones', result['error'])


@unittest.skipUnless(find_spec('yt_dlp'), 'La selección de formatos requiere yt-dlp en este Python.')
class FormatCheck(unittest.TestCase):
    @staticmethod
    def select(formats, quality='best'):
        from yt_dlp import YoutubeDL, parse_options
        args = server.command('https://youtu.be/example', 'video', Path('/tmp'), quality)
        options = parse_options(args[len(server.local_tools.ytdlp_command()):]).ydl_opts
        options.update(quiet=True, no_warnings=True)
        info = {'id': 'synthetic', 'title': 'Quality check', 'formats': [
            {**item, 'url': 'https://example.invalid/' + item['format_id']} for item in formats]}
        with YoutubeDL(options) as downloader:
            return downloader.process_ie_result(info, download=False)

    def test_lower_resolution_landscape_and_portrait(self):
        for portrait in (False, True):
            formats = [{'format_id': str(resolution), 'height': resolution if not portrait else resolution * 16 // 9,
                        'width': resolution * 16 // 9 if not portrait else resolution,
                        'vcodec': 'avc1', 'acodec': 'mp4a.40.2', 'ext': 'mp4'}
                       for resolution in (480, 720, 1080, 2160)]
            for quality in ('best', '1080', '720', '480'):
                with self.subTest(portrait=portrait, quality=quality):
                    selected = self.select(formats, quality)
                    self.assertEqual(min(selected['width'], selected['height']), 2160 if quality == 'best' else int(quality))
            with self.subTest(portrait=portrait, missing_smaller=True):
                selected = self.select(formats[2:], '480')
                self.assertEqual(min(selected['width'], selected['height']), 1080)
            with self.subTest(portrait=portrait, extractor_prefers_higher=True):
                selected = self.select([{**item, 'preference': index} for index, item in enumerate(formats)], '720')
                self.assertEqual(min(selected['width'], selected['height']), 720)

    def test_highest_quality_ignores_resolution_and_container(self):
        from yt_dlp import YoutubeDL
        formats = [
            {'format_id': '720', 'height': 720, 'width': 1280, 'vcodec': 'avc1', 'acodec': 'none', 'ext': 'mp4'},
            {'format_id': '1080', 'height': 1080, 'width': 1920, 'vcodec': 'avc1', 'acodec': 'none', 'ext': 'mp4'},
            {'format_id': '2160', 'height': 2160, 'width': 3840, 'vcodec': 'vp9', 'acodec': 'none', 'ext': 'webm'},
            {'format_id': 'aac', 'abr': 128, 'vcodec': 'none', 'acodec': 'mp4a.40.2', 'ext': 'm4a'},
            {'format_id': 'opus', 'abr': 160, 'vcodec': 'none', 'acodec': 'opus', 'ext': 'webm'},
        ]
        for kind in ('video', 'audio'):
            args = server.command('https://youtu.be/example', kind, Path('/tmp'))
            info = {'id': 'synthetic', 'title': 'Quality check', 'formats': [
                {**item, 'url': 'https://example.invalid/' + item['format_id']} for item in formats]}
            with YoutubeDL({'format': args[args.index('-f') + 1], 'quiet': True, 'no_warnings': True}) as downloader:
                selected = downloader.process_ie_result(info, download=False)
            if kind == 'video':
                self.assertEqual(selected['height'], 2160)
                self.assertEqual(selected['requested_formats'][1]['acodec'], 'opus')
            else:
                self.assertEqual(selected['acodec'], 'opus')


class LocalToolsCheck(unittest.TestCase):
    def test_archive_only_copies_selected_binaries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / 'tools.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('../../outside', 'unwanted')
                bundle.writestr('../../ffmpeg', 'binary')
                bundle.writestr('bin/ffprobe', 'probe')
            with patch.object(server.local_tools, 'BIN', root / 'bin'):
                server.local_tools.extract_binaries(archive, ('ffmpeg', 'ffprobe'))
                self.assertEqual((root / 'bin/ffmpeg').read_text(), 'binary')
                self.assertEqual(set(p.name for p in (root / 'bin').iterdir()), {'ffmpeg', 'ffprobe'})
                with self.assertRaises(ValueError):
                    server.local_tools.extract_binaries(archive, ('deno',))

    def test_failed_installation_can_be_retried(self):
        tools = server.local_tools
        state = {'ytDlp': {'installed': False}, 'ffmpeg': {'installed': False}, 'youtube': {'installed': False}}
        with tempfile.TemporaryDirectory() as temp, patch.object(tools, 'ROOT', Path(temp)), \
                patch.object(tools, 'INSTALL_STATE', {}), patch.object(tools, 'status', return_value=state), \
                patch.object(tools, 'install_ffmpeg', side_effect=ValueError('Sin conexión')):
            self.assertTrue(tools.INSTALL_LOCK.acquire(blocking=False))
            tools.install('ffmpeg')
            self.assertFalse(tools.INSTALL_LOCK.locked())
            self.assertEqual(tools.INSTALL_STATE, {'state': 'error', 'message': 'Sin conexión'})

    def test_old_deno_falls_back_to_supported_node(self):
        tools = server.local_tools
        def installed_version(args):
            return 'deno 1.0.0' if args[0] == 'deno' else 'v22.22.1' if args[0] == 'node' else 'installed'
        with patch.object(tools, 'version', side_effect=installed_version):
            self.assertTrue(tools.status()['youtube']['installed'])
            self.assertEqual(tools.status()['youtube']['version'], 'v22.22.1')


if __name__ == '__main__':
    unittest.main()
