"""tools/rpcs3_pack.py: the built-in RPCS3's pack from a build, as emulator.install takes it."""
import json
import os
import sys
import zipfile

import pytest

from legacy_roster import emulator, savedata

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import rpcs3_pack  # noqa: E402

SOURCE = 'https://github.com/example/rpcs3'


def _build(tmp_path):
    build = tmp_path / 'build'
    (build / 'Icons' / 'ui').mkdir(parents=True)
    (build / 'portable').mkdir()
    (build / 'rpcs3.exe').write_bytes(b'program')
    (build / 'rpcs3.pdb').write_bytes(b'debug')
    (build / 'Icons' / 'ui' / 'cross.png').write_bytes(b'png')
    (build / 'portable' / 'config.yml').write_text('mine', encoding='utf-8')
    (build / 'LICENSE').write_text('GPL v2', encoding='utf-8')
    return build


def test_a_windows_build_becomes_a_pack_the_install_takes_and_the_same_bytes_twice(tmp_path, monkeypatch):
    build = _build(tmp_path)
    out = str(tmp_path / 'rpcs3-win.zip')
    index = rpcs3_pack.make(str(build), out, '0.0.43-1', 'abc', SOURCE, built='2026-11-16')
    assert index['name'] == 'rpcs3-win' and index['patches']
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert 'rpcs3.exe' in names and 'Icons/ui/cross.png' in names and 'LICENSE' in names
        assert not [n for n in names if n.startswith('portable') or n.endswith('.pdb')]
        assert SOURCE in z.read('SOURCE.txt').decode('utf-8')
        assert json.loads(z.read('index.json'))['commit'] == 'abc'
    first = open(out, 'rb').read()
    rpcs3_pack.make(str(build), out, '0.0.43-1', 'abc', SOURCE, built='2026-11-16')
    assert open(out, 'rb').read() == first
    monkeypatch.setattr(emulator, 'room', lambda folder: emulator.NEEDED)
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    monkeypatch.setattr(emulator, 'EXE', 'rpcs3.exe')
    folder = str(tmp_path / 'rpcs3')
    mark = emulator.install(out, folder)
    assert mark['version'] == '0.0.43-1' and mark['source'] == SOURCE
    assert os.path.isfile(os.path.join(folder, 'rpcs3.exe'))


def test_a_linux_appimage_is_packed_as_rpcs3_appimage_executable(tmp_path):
    image = tmp_path / 'rpcs3-v0.0.43-1_linux64.AppImage'
    image.write_bytes(b'\x7fELF')
    out = str(tmp_path / 'rpcs3-linux.zip')
    licence = tmp_path / 'LICENSE'
    licence.write_text('GPL v2', encoding='utf-8')
    index = rpcs3_pack.make(str(image), out, '0.0.43-1', 'abc', SOURCE, licence=str(licence))
    assert index['name'] == 'rpcs3-linux'
    with zipfile.ZipFile(out) as z:
        info = z.getinfo('rpcs3.AppImage')
        assert (info.external_attr >> 16) & 0o111


def test_a_build_without_the_program_or_licence_is_refused(tmp_path):
    (tmp_path / 'empty').mkdir()
    with pytest.raises(SystemExit):
        rpcs3_pack.make(str(tmp_path / 'empty'), str(tmp_path / 'x.zip'), '1', 'abc', SOURCE)
    build = _build(tmp_path)
    (build / 'LICENSE').unlink()
    with pytest.raises(SystemExit):
        rpcs3_pack.make(str(build), str(tmp_path / 'y.zip'), '1', 'abc', SOURCE)
