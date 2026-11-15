"""Package the tested Windows executable, examples, provenance and checksums."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

from a650 import __version__

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package_preview(binary, output_dir, commit, source_ref):
    binary, output_dir = Path(binary).resolve(), Path(output_dir).resolve()
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('A full Git commit SHA is required')
    if source_ref.startswith('preview-') and source_ref != f'preview-{__version__}':
        raise ValueError('Release tag does not match application version')
    result = subprocess.run([str(binary), '--version'], check=True, capture_output=True,
                            text=True, timeout=90)
    if result.stdout.strip() != f'a650 {__version__}':
        raise ValueError('Executable version does not match package version')
    notes = ROOT / 'docs' / 'releases' / f'{__version__}.md'
    if not notes.is_file():
        raise ValueError('Release notes missing for this version')
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f'a650-windows-x86_64-{__version__}.zip'
    with tempfile.TemporaryDirectory(prefix='a650-preview-', dir=output_dir) as temporary:
        stage = Path(temporary)
        shutil.copytree(ROOT / 'packaging' / 'preview', stage, dirs_exist_ok=True)
        shutil.copy2(binary, stage / 'a650.exe')
        shutil.copy2(notes, stage / 'RELEASE-NOTES-ru.md')
        shutil.copy2(ROOT / 'docs' / 'BENCH_DIAGNOSTICS.md', stage / 'BENCH-DIAGNOSTICS-ru.md')
        info = {'version': __version__, 'commit': commit, 'source_ref': source_ref,
                'platform': 'windows-x86_64', 'executable': 'a650.exe',
                'executable_sha256': digest(stage / 'a650.exe')}
        (stage / 'BUILD-INFO.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
        with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as bundle:
            for path in sorted(stage.rglob('*')):
                if path.is_file():
                    bundle.write(path, path.relative_to(stage).as_posix())
    checksum = archive.with_suffix('.zip.sha256')
    checksum.write_text(f'{digest(archive)}  {archive.name}\n', encoding='ascii')
    return archive, checksum


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True)
    parser.add_argument('--output-dir', default='dist/preview-release')
    parser.add_argument('--commit', required=True)
    parser.add_argument('--source-ref', required=True)
    args = parser.parse_args()
    for path in package_preview(args.binary, args.output_dir, args.commit, args.source_ref):
        print(path)
