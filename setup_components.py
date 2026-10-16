"""Explicit online installer. The player never calls this module implicitly."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile
import subprocess

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent

def install(asr=True, report=print):
    downloads = ROOT / 'downloads'
    downloads.mkdir(exist_ok=True)
    manifest = []
    known_path=ROOT/'component-manifest.json'
    known={x['url']:x['sha256'] for x in json.loads(known_path.read_text('utf-8'))} if known_path.exists() else {}
    def fetch(url, name):
        p = downloads / name
        if not p.exists():
            report('Загрузка: ' + name)
            req = urllib.request.Request(url, headers={'User-Agent': 'LocalDub-MVP/0.1'})
            with urllib.request.urlopen(req, timeout=120) as r, p.with_suffix(p.suffix+'.part').open('wb') as f:
                total = int(r.headers.get('Content-Length', 0)); done = 0; last = -1
                while chunk := r.read(1024*1024):
                    f.write(chunk); done += len(chunk)
                    percent = int(done * 100 / total) if total else done//1048576
                    if percent != last:
                        report(f'{name}: {percent}' + ('%' if total else ' МБ')); last = percent
            p.with_suffix(p.suffix+'.part').replace(p)
        with p.open('rb') as content: checksum=hashlib.file_digest(content,'sha256').hexdigest()
        if url in known and checksum!=known[url]:raise RuntimeError('SHA-256 mismatch: '+name)
        manifest.append({'url': url, 'file': name, 'sha256': checksum})
        return p
    def unpack(p, dest):
        dest.mkdir(parents=True, exist_ok=True)
        if p.suffix == '.zip':
            with zipfile.ZipFile(p) as z: z.extractall(dest)
        else:
            seven = Path('C:/Program Files/7-Zip/7z.exe')
            if seven.exists(): subprocess.run([str(seven), 'x', str(p), '-o'+str(dest), '-y'], check=True, stdout=subprocess.DEVNULL)
            else:
                import py7zr
                with py7zr.SevenZipFile(p) as z: z.extractall(dest)
    native = ROOT / 'native'; native.mkdir(exist_ok=True)
    if not (native/'libmpv-2.dll').exists():
        p = fetch('https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/20261016/mpv-dev-x86_64-20261016-git-a2cd83c56d.7z', 'mpv.7z')
        unpack(p, native)
    if not (native/'ffmpeg.exe').exists():
        p = fetch('https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.7z', 'ffmpeg.7z')
        unpack(p, downloads/'ffmpeg')
        for name in ('ffmpeg.exe','ffprobe.exe'):
            shutil.copy2(next((downloads/'ffmpeg').rglob(name)), native/name)
    if not (native/'piper'/'piper.exe').exists():
        unpack(fetch('https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip','piper.zip'), native)
    models = ROOT/'models'; models.mkdir(exist_ok=True)
    if not (models/'translation'/'model.bin').exists():
        p = fetch('https://huggingface.co/ordois/opus-mt-en-ru-ctranslate2-int8/resolve/9ae164a637a7e380d3e09768899c886af9925afe/opus-mt-en-ru-ctranslate2-int8.zip','translation.zip')
        unpack(p, downloads/'translation')
        src = next((downloads/'translation').rglob('model.bin')).parent
        shutil.copytree(src, models/'translation', dirs_exist_ok=True)
        for item in json.loads((models/'translation/manifest.json').read_text('utf-8'))['files']:
            with (models/'translation'/item['name']).open('rb') as f:
                if hashlib.file_digest(f,'sha256').hexdigest()!=item['sha256']:
                    raise RuntimeError('Invalid translation model: '+item['name'])
    for name in ('ru_RU-denis-medium.onnx','ru_RU-denis-medium.onnx.json','MODEL_CARD'):
        dst = models/name
        if not dst.exists(): shutil.copy2(fetch('https://huggingface.co/rhasspy/piper-voices/resolve/c10ece1aade47bb51c153c893d14e5bf8e5b7117/ru/ru_RU/denis/medium/'+name, 'denis-'+name), dst)
    if asr:
        model = models/'whisper-tiny'; model.mkdir(exist_ok=True)
        for name in ('model.bin','config.json','tokenizer.json','vocabulary.txt'):
            if not (model/name).exists():
                shutil.copy2(fetch('https://huggingface.co/Systran/faster-whisper-tiny/resolve/d90ca5fe260221311c53c58e660288d3deb8d356/'+name,'whisper-'+name), model/name)
    old = ROOT/'component-manifest.json'
    prior = json.loads(old.read_text('utf-8')) if old.exists() else []
    byfile = {x['file']: x for x in prior+manifest}
    old.write_text(json.dumps(list(byfile.values()), ensure_ascii=False, indent=2), 'utf-8')
    report('Компоненты установлены. Дальнейшая работа полностью локальная.')

if __name__ == '__main__': install('--no-asr' not in sys.argv)
