"""emulator: the built-in RPCS3 (a portable copy in a folder of the program's own)."""
import hashlib
import json
import os
import zipfile

import pytest

from legacy_roster import emulator, rpcs3cfg, savedata

EU = 'BLES02153'


def _pack(tmp_path, extra=()):
    path = tmp_path / 'rpcs3-pack.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(emulator.EXE, b'program')
        z.writestr('Icons/ui/cross.png', b'png')
        z.writestr('LICENSE', 'GPL v2')
        z.writestr(emulator.INDEX, json.dumps({'version': '0.0.43-1', 'source': 'https://example.org/rpcs3', 'commit': 'abc'}))
        for name, data in extra:
            z.writestr(name, data)
    return str(path)


def test_install_unpacks_the_program_marks_the_folder_and_keeps_portable(tmp_path, monkeypatch):
    monkeypatch.setattr(emulator, 'room', lambda folder: emulator.NEEDED)
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    folder = str(tmp_path / 'rpcs3')
    assert not emulator.installed(folder)
    pack = _pack(tmp_path)
    mark = emulator.install(pack, folder)
    assert emulator.installed(folder)
    assert mark['version'] == '0.0.43-1' and mark['commit'] == 'abc'
    assert mark['sha256'] == hashlib.sha256(open(pack, 'rb').read()).hexdigest()
    assert emulator.stamp(folder)['sha256'] == mark['sha256']
    assert os.path.isfile(os.path.join(folder, 'portable', 'Icons', 'ui', 'cross.png'))
    save = os.path.join(folder, 'portable', 'dev_hdd0', 'home', '00000001', 'savedata', 'x.bin')
    os.makedirs(os.path.dirname(save))
    open(save, 'wb').write(b'mine')
    emulator.install(_pack(tmp_path, [('rpcs3.dll', b'new')]), folder)       # a newer build: the player's data stays
    assert open(save, 'rb').read() == b'mine'
    assert os.path.isfile(os.path.join(folder, 'rpcs3.dll'))


@pytest.mark.parametrize('name', ['portable/config/config.yml', '../evil.txt', 'blueline.json', '/abs.txt'])
def test_a_pack_with_files_outside_the_program_is_refused(tmp_path, monkeypatch, name):
    monkeypatch.setattr(emulator, 'room', lambda folder: emulator.NEEDED)
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    with pytest.raises(emulator.EmulatorError):
        emulator.install(_pack(tmp_path, [(name, b'x')]), str(tmp_path / 'rpcs3'))
    assert not os.path.exists(tmp_path / 'evil.txt')


def test_too_little_room_is_refused_before_anything_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(emulator, 'room', lambda folder: emulator.NEEDED - 1)
    with pytest.raises(emulator.EmulatorError, match='free space'):
        emulator.install(_pack(tmp_path), str(tmp_path / 'rpcs3'))
    assert not os.path.exists(tmp_path / 'rpcs3')


def test_the_built_in_rpcs3_is_an_rpcs3_rooted_in_portable(tmp_path, monkeypatch):
    monkeypatch.setattr(emulator, 'room', lambda folder: emulator.NEEDED)
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    folder = str(tmp_path / 'rpcs3')
    emulator.install(_pack(tmp_path), folder)
    with pytest.raises(savedata.NoGameError) as no_game:
        emulator.host(folder)
    assert no_game.value.rpcs3.folder == os.path.join(folder, 'portable')
    game = tmp_path / 'games' / 'NHL Legacy.iso'
    game.parent.mkdir()
    game.write_bytes(b'iso')
    emulator.set_game(folder, EU, str(game))
    emulator.set_game(folder, EU, str(game))                                 # once in the list, not twice
    games_yml = os.path.join(emulator.config_dir(folder), 'games.yml')
    assert open(games_yml, encoding='utf-8').read() == f"{EU}: {str(game).replace(os.sep, '/')}\n"
    found = emulator.host(folder)
    assert found.builtin and not found.native
    assert found.folder == os.path.join(folder, 'portable')
    assert found.dev_hdd0 == os.path.join(folder, 'portable', 'dev_hdd0')
    assert found.game_disc(EU) == os.path.normpath(str(game))
    assert found.command() == [emulator.exe_path(folder)]


def test_a_players_portable_rpcs3_is_found_in_its_portable_folder(tmp_path):
    root = tmp_path / 'RPCS3'
    (root / 'portable' / 'dev_hdd0' / 'home' / '00000001' / 'savedata').mkdir(parents=True)
    (root / 'dev_hdd0').mkdir()                                              # left from before it was made portable
    exe = root / emulator.EXE
    exe.write_bytes(b'program')
    game = tmp_path / 'nhl.iso'
    game.write_bytes(b'iso')
    found = savedata.find_rpcs3(str(exe), {EU: str(game)})
    assert found.folder == str(root / 'portable') and not found.builtin


def test_configure_writes_the_games_defaults_and_keeps_the_rest(tmp_path):
    folder = str(tmp_path / 'rpcs3')
    cfg = os.path.join(emulator.config_dir(folder), 'config.yml')
    os.makedirs(os.path.dirname(cfg))
    open(cfg, 'w', encoding='utf-8', newline='').write(
        'Video:\n  Renderer: OpenGL\n  Resolution Scale: 150\nMiscellaneous:\n  Exit RPCS3 when process finishes: false\n')
    assert emulator.configure(folder)
    text = open(cfg, encoding='utf-8').read()
    assert rpcs3cfg.get(text, ('Video', 'Renderer')) == 'Vulkan'
    assert rpcs3cfg.get(text, ('Video', 'Resolution Scale')) == '150'
    assert rpcs3cfg.get(text, ('Video', 'Disable Blit Engine Upscaling')) == 'true'
    assert rpcs3cfg.get(text, ('Miscellaneous', 'Exit RPCS3 when process finishes')) == 'true'
    assert not emulator.configure(folder)                                    # the second time changes nothing


def test_the_firmware_version_is_read_from_dev_flash(tmp_path):
    folder = str(tmp_path / 'rpcs3')
    assert emulator.firmware_version(folder) is None
    path = os.path.join(folder, 'portable', 'dev_flash', 'vsh', 'etc', 'version.txt')
    os.makedirs(os.path.dirname(path))
    open(path, 'w').write('release:04.9300:\nbuild:68500,20260108:x\n')
    assert emulator.firmware_version(folder) == '4.93'


def test_sonys_list_gives_the_full_file_its_version_and_md5():
    text = ("# EU\nDest=85;CompatibleSystemSoftwareVersion=4.9300-;\n"
            "Dest=85;IncrementalUpdateVersion=00010b72-00010b72;ImageVersion=00010b94;SystemSoftwareVersion=4.9300;"
            "CDN=http://deu01.ps3.update.playstation.net/update/ps3/image/eu/2026_0318_a2b60b6ac1d2e49e230144345616927c/"
            "PS3PATCH.PUP;CDN_Timeout=30;\n"
            "Dest=85;ImageVersion=00010b94;SystemSoftwareVersion=4.9300;"
            "CDN=http://deu01.ps3.update.playstation.net/update/ps3/image/eu/2026_0318_a2b60b6ac1d2e49e230144345616927c/"
            "PS3UPDAT.PUP;CDN_Timeout=30;\n")
    version, url, md5 = emulator.parse_offer(text)
    assert version == '4.93' and url.endswith('/PS3UPDAT.PUP') and md5 == 'a2b60b6ac1d2e49e230144345616927c'
    assert emulator.parse_offer('# EU\n') is None


def test_check_pup_wants_the_header_and_the_checksum(tmp_path):
    good = tmp_path / 'PS3UPDAT.PUP'
    good.write_bytes(emulator.PUP_MAGIC + b'\0' * 100)
    assert emulator.check_pup(str(good), md5=hashlib.md5(good.read_bytes()).hexdigest())
    with pytest.raises(emulator.EmulatorError, match='not the file Sony published'):
        emulator.check_pup(str(good), md5='0' * 32)
    bad = tmp_path / 'other.bin'
    bad.write_bytes(b'PK\3\4')
    with pytest.raises(emulator.EmulatorError, match='not the PS3 system software'):
        emulator.check_pup(str(bad))


def test_the_game_check_names_what_is_wrong(tmp_path, monkeypatch):
    assert 'not there' in emulator.game_problem(str(tmp_path / 'missing.iso'))
    other = tmp_path / 'other'
    (other / 'PS3_GAME').mkdir(parents=True)
    assert 'not a game disc' in emulator.game_problem(str(other))
    monkeypatch.setattr(savedata, 'game_title_id', lambda path: 'BLUS30001')
    assert 'another game' in emulator.game_problem(str(other))
    monkeypatch.setattr(savedata, 'game_title_id', lambda path: EU)
    (other / 'PS3_GAME' / 'USRDIR').mkdir()
    (other / 'PS3_GAME' / 'USRDIR' / 'EBOOT.BIN').write_bytes(b'\x8a\x11' * 8)
    assert 'encrypted' in emulator.game_problem(str(other))
    (other / 'PS3_GAME' / 'USRDIR' / 'EBOOT.BIN').write_bytes(b'SCE\0' + b'\0' * 12)
    assert emulator.game_problem(str(other)) is None


def test_config_and_log_follow_rpcs3s_folders_per_system(tmp_path, monkeypatch):
    folder = str(tmp_path / 'rpcs3')
    monkeypatch.setattr(emulator, 'WINDOWS', True)
    assert emulator.config_dir(folder) == os.path.join(folder, 'portable', 'config')
    assert emulator.log_file(folder) == os.path.join(folder, 'portable', 'log', 'RPCS3.log')
    monkeypatch.setattr(emulator, 'WINDOWS', False)                          # Linux: no config/, the cache outside portable/
    assert emulator.config_dir(folder) == os.path.join(folder, 'portable')
    assert emulator.log_file(folder) == os.path.join(folder, 'cache', 'rpcs3', 'RPCS3.log')


def test_the_built_in_rpcs3_on_linux_gets_its_own_cache_folder(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(savedata, 'WINDOWS', False)
    monkeypatch.setattr(savedata.subprocess, 'Popen', lambda args, **kw: seen.update(kw))
    folder = tmp_path / 'rpcs3'
    folder.mkdir()
    exe = folder / emulator.EXE
    exe.write_bytes(b'program')
    savedata.launch([str(exe), '--no-gui'])
    assert 'XDG_CACHE_HOME' not in seen['env'] or seen['env']['XDG_CACHE_HOME'] != str(folder / 'cache')
    (folder / savedata.BUILTIN_STAMP).write_text('{}')
    savedata.launch([str(exe), '--no-gui'], env={'HOME': 'h'})
    assert seen['env'] == {'HOME': 'h', 'XDG_CACHE_HOME': str(folder / 'cache')}


def test_install_firmware_waits_for_rpcs3s_log_line(tmp_path, monkeypatch):
    folder = str(tmp_path / 'rpcs3')
    pup = tmp_path / 'PS3UPDAT.PUP'
    pup.write_bytes(emulator.PUP_MAGIC + b'\0' * 10)
    flash = os.path.join(emulator.data_dir(folder), 'dev_flash', 'vsh', 'etc', 'version.txt')
    log = emulator.log_file(folder)

    class Proc:
        pid = 1
        def poll(self):
            return None

    seen = []

    def fake_launch(args, **kw):
        seen.append(args)
        assert os.path.isdir(os.path.dirname(log))      # RPCS3 writes no log on a first start without its log folder
        os.makedirs(os.path.dirname(flash), exist_ok=True)
        open(flash, 'w').write('release:04.9300:\n')               # Sony's file dates: not the sign it finished
        os.makedirs(os.path.dirname(log), exist_ok=True)
        open(log, 'w', encoding='utf-8').write('·S 0:00:01 GUI: Successfully installed PS3 firmware version 4.93.\n')
        return Proc()
    monkeypatch.setattr(savedata, 'launch', fake_launch)
    monkeypatch.setattr(emulator, '_end', lambda proc: None)
    assert emulator.install_firmware(folder, str(pup), poll=0.01) == '4.93'
    # headless: without it RPCS3 asks "Install firmware: <file>?" in a window and waits for a click
    assert seen[0][1:3] == ['--headless', '--installfw']
    assert emulator.install_firmware(folder, str(pup), poll=0.01) == '4.93'      # already in: RPCS3 is not asked again
    assert len(seen) == 1

    # headless RPCS3 quits (and crashes while quitting) right after the line: the line and the version file decide
    os.remove(flash)

    class Gone(Proc):
        def poll(self):
            return 0xC0000409

    def quits_at_once(args, **kw):
        fake_launch(args)
        return Gone()
    monkeypatch.setattr(savedata, 'launch', quits_at_once)
    assert emulator.install_firmware(folder, str(pup), poll=0.01) == '4.93'

    os.remove(flash)
    def failing(args, **kw):
        open(log, 'w', encoding='utf-8').write('·E 0:00:01 GUI: Error while installing firmware: TAR contents are invalid.\n')
        return Proc()
    monkeypatch.setattr(savedata, 'launch', failing)
    with pytest.raises(emulator.EmulatorError, match='could not install'):
        emulator.install_firmware(folder, str(pup), poll=0.01)

    def crashes_early(args, **kw):
        open(log, 'w', encoding='utf-8').write('·! 0:00:01 GUI: Firmware Installer: starting\n')
        return Gone()
    monkeypatch.setattr(savedata, 'launch', crashes_early)
    with pytest.raises(emulator.EmulatorError, match='could not install'):
        emulator.install_firmware(folder, str(pup), poll=0.01)
