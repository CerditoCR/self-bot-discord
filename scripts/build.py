"""Build the Windows console runtime and desktop app. No network requests."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def run(*args):
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', *args], cwd=ROOT, check=True)

def main():
    if os.name != 'nt':
        raise SystemExit('Build on Windows to produce Windows executables.')
    run('--console', '--name', 'local-runner', '--distpath', 'build/runtime', '--workpath', 'build/runner', '--specpath', 'build/spec', 'bot.py')
    shutil.copyfile(ROOT/'build/runtime/local-runner.exe', ROOT/'local-runner.exe')
    args = ['--windowed','--name','SELF BOT DISCORD','--distpath','dist','--workpath','build/gui','--specpath','build/spec']
    for name in ('bot.py','core.py','i18n.py','legacy_engine.py','local-runner.exe'):
        args.extend(['--add-data', str(ROOT/name)+';.'])
    run(*args,'app.py')
    print('Build complete: dist/SELF BOT DISCORD.exe')

if __name__ == '__main__':main()
