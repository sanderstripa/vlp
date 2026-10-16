"""Assemble the tested PyInstaller folder and a per-user NSIS installer."""
from pathlib import Path
import argparse
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent

def package(binary, compiler, output):
    binary=Path(binary).resolve(); output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    native=binary/'native'; native.mkdir(exist_ok=True)
    for name in ('libmpv-2.dll','ffmpeg.exe','ffprobe.exe'):shutil.copy2(ROOT/'native'/name,native/name)
    shutil.copytree(ROOT/'native/piper',native/'piper',dirs_exist_ok=True)
    models=binary/'models';models.mkdir(exist_ok=True)
    for name in ('translation','whisper-tiny'):shutil.copytree(ROOT/'models'/name,models/name,dirs_exist_ok=True)
    for name in ('ru_RU-denis-medium.onnx','ru_RU-denis-medium.onnx.json','MODEL_CARD'):shutil.copy2(ROOT/'models'/name,models/name)
    for name in ('README.md','REPORT.md','THIRD_PARTY.md','LICENSE','component-manifest.json','test-video.mp4','test-video.srt'):
        shutil.copy2(ROOT/name,binary/name)
    shutil.copytree(ROOT/'licenses',binary/'licenses',dirs_exist_ok=True)
    def esc(s):return str(s).replace('$','$$').replace('"','$\\"')
    # Delete only package-owned files. Never recursively delete the installation folder.
    lines=[]
    for p in sorted(binary.rglob('*')):
        if p.is_file():lines.append('Delete "$INSTDIR\\'+esc(str(p.relative_to(binary)))+'"')
    for p in sorted((p for p in binary.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
        lines.append('RMDir "$INSTDIR\\'+esc(str(p.relative_to(binary)))+'"')
    (output/'uninstall-files.nsh').write_text('\n'.join(lines),'utf-8-sig')
    src=ROOT/'installer.nsi'
    subprocess.run([str(compiler),'/DBINARY='+str(binary),'/DOUTDIR='+str(output),str(src)],check=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',default=str(ROOT/'dist/LocalDub'));p.add_argument('--compiler',default='makensis');p.add_argument('--output',default=str(ROOT/'release'));args=p.parse_args()
    package(args.binary,args.compiler,args.output)
