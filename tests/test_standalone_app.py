"""Setup's parts for playing (0.99.0): the choice of where the game runs and the built-in RPCS3 (app/builtin.py), the Game
settings card (app/gamesettings.py), the Controls window (app/controls.py) and Play's command per host. No window: a fake
host and a fake UpdateController with just what the controllers read."""
import json
import os
import time
import types
import zipfile

import pytest

from legacy_roster import emulator, packs, rpcs3cfg, rpcs3input, savedata
from legacy_roster.app import settings as S
from legacy_roster.app.builtin import BuiltinController
from legacy_roster.app.controls import ControlsController
from legacy_roster.app.gamesettings import GameSettingsController
from legacy_roster.app.update import UpdateController

EU = 'BLES02153'


class FakeHost:
    def __init__(self):
        self.slices, self.logs, self.pick = [], [], None

    def changed(self, name):
        self.slices.append(name)

    def log(self, text):
        self.logs.append(text)

    def ask_open(self, *_args):
        return self.pick

    def ask_folder(self, *_args):
        return self.pick


class FakeUpdate:
    def __init__(self, settings, rpcs3=None):
        self.settings, self.rpcs3 = settings, rpcs3
        self.busy = self.export_mode = False
        self.set_to, self.picked = [], 0

    def set_rpcs3(self, path, then=None):
        self.set_to.append(path)

    def pick_rpcs3(self):
        self.picked += 1

    def selected_slot(self):
        return None


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(S, 'save', lambda settings: None)
    monkeypatch.setattr(savedata, 'running_rpcs3', lambda: None)
    monkeypatch.setattr(emulator, 'room', lambda folder: emulator.NEEDED)


def _pack(tmp_path):
    path = tmp_path / 'rpcs3-pack.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(emulator.EXE, b'program')
        z.writestr('LICENSE', 'GPL v2')
        z.writestr(emulator.INDEX, json.dumps({'version': '0.0.43-1', 'source': 'https://github.com/example/rpcs3',
                                               'commit': 'abc'}))
    return str(path)


def _firmware(folder):
    path = os.path.join(emulator.data_dir(folder), 'dev_flash', 'vsh', 'etc', 'version.txt')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'w', encoding='ascii').write('release:04.9300:\n')


def _game(tmp_path):
    game = tmp_path / 'games' / 'NHL Legacy.iso'
    game.parent.mkdir(exist_ok=True)
    game.write_bytes(b'iso')
    return str(game)


def _builtin_host(tmp_path):
    """A set-up built-in RPCS3 (program, firmware, game) and its savedata.Rpcs3."""
    folder = str(tmp_path / 'rpcs3')
    emulator.install(_pack(tmp_path), folder)
    _firmware(folder)
    game = _game(tmp_path)
    emulator.set_game(folder, EU, game)
    return folder, game, emulator.host(folder)


def _own_rpcs3(tmp_path, config=None):
    """A player's own RPCS3 (not portable), its config.yml as given."""
    root = tmp_path / 'RPCS3'
    (root / 'dev_hdd0' / 'home' / '00000001' / 'savedata').mkdir(parents=True)
    (root / 'rpcs3.exe').write_bytes(b'program')
    if config is not None:
        (root / 'config').mkdir()
        (root / 'config' / 'config.yml').write_text(config, encoding='utf-8')
    return savedata.find_rpcs3(str(root / 'rpcs3.exe'), {EU: _game(tmp_path)})


def _wait(predicate, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


# --- where the game runs and the built-in RPCS3 ----------------------------------------------------------------------
def test_with_no_game_in_use_the_card_offers_blueline_rpcs3_and_asks_for_the_game_first(tmp_path, monkeypatch):
    monkeypatch.setattr(emulator, 'pack_name', lambda: 'rpcs3-win')
    update = FakeUpdate({S.EMULATOR_FOLDER: str(tmp_path / 'rpcs3')})
    c = BuiltinController(FakeHost(), update)
    view = c.snapshot()
    assert view['shown'] == 'builtin' and view['in_use'] is None
    assert [ch['kind'] for ch in view['choices']] == ['builtin', 'rpcs3', 'native']
    assert [r['key'] for r in view['rows']] == ['rpcs3', 'firmware', 'game'] and not any(r['done'] for r in view['rows'])
    assert view['button'] == {'text': "Set up", 'can': False, 'why': "Pick your game first."}
    assert view['can_move'] and view['pup']


def test_a_game_that_is_not_nhl_legacy_is_named_and_a_good_one_unlocks_set_up(tmp_path, monkeypatch):
    monkeypatch.setattr(emulator, 'pack_name', lambda: 'rpcs3-win')
    host = FakeHost()
    update = FakeUpdate({S.EMULATOR_FOLDER: str(tmp_path / 'rpcs3')})
    c = BuiltinController(host, update)
    host.pick = _game(tmp_path)
    monkeypatch.setattr(emulator, 'game_problem', lambda path: "This is not NHL Legacy.")
    c.pick_game()
    game_row = c.snapshot()['rows'][2]
    assert game_row['tone'] == 'bad' and game_row['text'] == "This is not NHL Legacy."
    monkeypatch.setattr(emulator, 'game_problem', lambda path: None)
    monkeypatch.setattr(savedata, 'game_title_id', lambda path: EU)
    c.pick_game()
    view = c.snapshot()
    assert view['rows'][2]['done'] and update.settings['games'][EU] == os.path.normpath(host.pick)
    assert view['button'] == {'text': "Set up", 'can': True, 'why': None}
    assert update.set_to == []                                              # not in use yet: nothing switched


def test_set_up_downloads_installs_the_firmware_writes_settings_controls_and_the_game(tmp_path, monkeypatch):
    monkeypatch.setattr(emulator, 'pack_name', lambda: 'rpcs3-win')
    folder = str(tmp_path / 'rpcs3')
    pack = _pack(tmp_path)
    game = _game(tmp_path)
    monkeypatch.setattr(emulator, 'game_problem', lambda path: None)
    monkeypatch.setattr(packs, 'manifest', lambda timeout=None: {'rpcs3-win': {'size': 1, 'sha256': 'x'}})
    monkeypatch.setattr(packs, 'sync', lambda **kw: (['rpcs3-win'], None))
    monkeypatch.setattr(packs, 'path', lambda name: pack)
    fetched = []

    def download(target, progress=None, cancelled=None):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        open(target, 'wb').write(b'SCEUF')
        fetched.append(target)
        return target, '4.93'
    monkeypatch.setattr(emulator, 'download_firmware', download)
    monkeypatch.setattr(emulator, 'install_firmware', lambda f, pup: _firmware(f))
    update = FakeUpdate({S.EMULATOR_FOLDER: folder, 'games': {EU: game},
                         S.CONTROLS: {'mode': 'keyboard', 'keys': {'Start': 'P'}}})
    c = BuiltinController(FakeHost(), update)
    c.setup()
    assert _wait(lambda: update.set_to), c.error
    assert update.set_to == [emulator.exe_path(folder)] and not c.busy and c.error is None
    assert emulator.installed(folder) and emulator.firmware_version(folder) == '4.93'
    assert fetched and not os.path.exists(fetched[0])                       # Sony's file is deleted after the install
    cfg = open(os.path.join(emulator.config_dir(folder), 'config.yml'), encoding='utf-8').read()
    assert rpcs3cfg.get(cfg, ('Video', 'Renderer')) == 'Vulkan'
    for path in rpcs3input.files(folder):
        assert '    Start: P' in open(path, encoding='utf-8').read().splitlines()
    assert EU in open(os.path.join(emulator.config_dir(folder), 'games.yml'), encoding='utf-8').read()


def test_set_up_without_the_download_server_says_so_and_stays_usable(tmp_path, monkeypatch):
    monkeypatch.setattr(emulator, 'pack_name', lambda: 'rpcs3-win')
    monkeypatch.setattr(emulator, 'game_problem', lambda path: None)
    monkeypatch.setattr(packs, 'manifest', lambda timeout=None: None)
    update = FakeUpdate({S.EMULATOR_FOLDER: str(tmp_path / 'rpcs3'), 'games': {EU: _game(tmp_path)}})
    c = BuiltinController(FakeHost(), update)
    c.setup()
    assert _wait(lambda: c.error)
    assert 'did not answer' in c.error and not c.busy and update.set_to == []
    assert c.snapshot()['button']['can']


def test_a_ready_built_in_rpcs3_is_used_at_once_and_the_other_choices_go_to_their_program(tmp_path, monkeypatch):
    monkeypatch.setattr(emulator, 'pack_name', lambda: 'rpcs3-win')
    monkeypatch.setattr(emulator, 'game_problem', lambda path: None)
    folder, game, _r = _builtin_host(tmp_path)
    mine = tmp_path / 'mine.exe'
    mine.write_bytes(b'x')
    update = FakeUpdate({S.EMULATOR_FOLDER: folder, 'games': {EU: game}, 'hosts': {'rpcs3': str(mine)}})
    c = BuiltinController(FakeHost(), update)
    c.choose('builtin')
    assert update.set_to == [emulator.exe_path(folder)]
    c.choose('rpcs3')
    assert update.set_to[-1] == str(mine)
    c.choose('native')
    assert update.picked == 1                                               # no port known: the picker opens
    assert c.source_url() == 'https://github.com/example/rpcs3'


def test_the_built_in_rpcs3_in_use_shows_no_set_up_button(tmp_path, monkeypatch):
    monkeypatch.setattr(emulator, 'pack_name', lambda: 'rpcs3-win')
    monkeypatch.setattr(emulator, 'game_problem', lambda path: None)
    folder, game, r = _builtin_host(tmp_path)
    c = BuiltinController(FakeHost(), FakeUpdate({S.EMULATOR_FOLDER: folder, 'games': {EU: game}}, rpcs3=r))
    view = c.snapshot()
    assert view['shown'] == 'builtin' and view['in_use'] == 'builtin'
    assert all(row['done'] for row in view['rows']) and view['button'] is None
    assert not view['can_move'] and view['source'] == 'https://github.com/example/rpcs3'


# --- Game settings ---------------------------------------------------------------------------------------------------
def _field(view, key):
    return next(f for f in view['fields'] if f['key'] == key)


def _on(field):
    return [o['value'] for o in field['options'] if o['on']]


def test_game_settings_show_what_the_players_rpcs3_says_and_keep_their_choices(tmp_path):
    r = _own_rpcs3(tmp_path, 'Video:\n  Resolution Scale: 150\n  Frame limit: 50\n  VSync Mode: Full\nAudio:\n'
                             '  Master Volume: 75\n')
    update = FakeUpdate({}, rpcs3=r)
    g = GameSettingsController(FakeHost(), update)
    view = g.snapshot()
    assert view['shown'] and not view['builtin'] and not view['can_reset']
    assert _on(_field(view, 'resolution')) == [150] and _on(_field(view, 'vsync')) == ['Full']
    assert _on(_field(view, 'frame_limit')) == [] and _field(view, 'frame_limit')['now'] == '50'
    assert [lock['label'] for lock in view['locked']] == ["Disable Blit Engine Upscaling"]
    assert 'On by itself' in view['locked'][0]['text']
    g.set('resolution', '300')                                              # the page sends strings too
    g.set('frame_limit', 'nonsense')
    view = g.snapshot()
    assert update.settings[S.GAME] == {'resolution': 300} and view['can_reset']
    assert _on(_field(view, 'resolution')) == [300] and not _field(view, 'resolution')['own']
    g.set('resolution', None)
    assert update.settings[S.GAME] == {}
    g.set('volume', 0)
    g.reset()
    assert update.settings[S.GAME] == {}


def test_game_settings_of_the_built_in_rpcs3_lock_vulkan_and_the_port_keeps_its_own(tmp_path, monkeypatch):
    _folder, _game, r = _builtin_host(tmp_path)
    g = GameSettingsController(FakeHost(), FakeUpdate({S.GAME: {'resolution': 100}}, rpcs3=r))
    view = g.snapshot()
    assert view['builtin'] and not view['can_reset']
    assert [lock['label'] for lock in view['locked']] == ["Renderer", "Disable Blit Engine Upscaling"]
    assert 'Not needed at 720p' in view['locked'][1]['text']
    assert view['note']                                                     # RPCS3 has written no config.yml yet
    native = types.SimpleNamespace(plain=False, native=True, builtin=False)
    assert GameSettingsController(FakeHost(), FakeUpdate({}, rpcs3=native)).snapshot()['native']
    export = FakeUpdate({}, rpcs3=r)
    export.export_mode = True
    assert GameSettingsController(FakeHost(), export).snapshot() == {'shown': False}


# --- Controls --------------------------------------------------------------------------------------------------------
def test_controls_of_the_players_rpcs3_say_where_to_set_them(tmp_path):
    view = ControlsController(FakeHost(), FakeUpdate({}, rpcs3=_own_rpcs3(tmp_path))).snapshot()
    assert view['own'] and 'Configuration > Pads' in view['note']


def test_a_key_on_two_buttons_swaps_escape_is_refused_and_the_files_follow(tmp_path):
    folder, _game, r = _builtin_host(tmp_path)
    update = FakeUpdate({}, rpcs3=r)
    c = ControlsController(FakeHost(), update)
    view = c.snapshot()
    assert not view['own'] and view['mode'] == 'controller' and len(view['buttons']) == len(rpcs3input.BUTTONS)
    c.set_mode('keyboard')
    c.bind('Cross', 'Z')                                                    # Z was Square's: Square takes X
    keys = rpcs3input.keys_of(update.settings[S.CONTROLS])
    assert keys['Cross'] == 'Z' and keys['Square'] == 'X'
    assert update.settings[S.CONTROLS]['keys'] == {'Cross': 'Z', 'Square': 'X'}
    for path in rpcs3input.files(folder):
        lines = open(path, encoding='utf-8').read().splitlines()
        assert '  Handler: Keyboard' in lines and '    Cross: Z' in lines and '    Square: X' in lines
    c.bind('Circle', 'Esc')
    assert 'Escape' in c.snapshot()['error'] and rpcs3input.keys_of(update.settings[S.CONTROLS])['Circle'] == 'C'
    c.bind('Cross', 'X')                                                    # back: both are RPCS3's own again
    assert update.settings[S.CONTROLS]['keys'] == {}
    c.set_pad('ds4')
    assert update.settings[S.CONTROLS]['mode'] == 'controller'
    assert '  Device: "DS4 Pad #1"' in open(rpcs3input.files(folder)[0], encoding='utf-8').read().splitlines()


def test_binding_a_right_stick_key_turns_the_mouse_stick_off_and_keeps_the_others_on_keys(tmp_path):
    _folder, _game, r = _builtin_host(tmp_path)
    update = FakeUpdate({S.CONTROLS: {'mode': 'keyboard'}}, rpcs3=r)
    c = ControlsController(FakeHost(), update)
    c.set_mouse_stick(True)
    view = c.snapshot()
    assert view['mouse_stick'] and all(b['mouse'] for b in view['buttons'] if b['key'] in rpcs3input.MOUSE_STICK)
    c.bind('Right Stick Up', 'Mouse MUp')                                   # nothing else may hold a mouse movement
    c.bind('Cross', 'I')                                                    # I is no stick key while the mouse holds it
    keys = rpcs3input.keys_of(update.settings[S.CONTROLS])
    assert not update.settings[S.CONTROLS]['mouse_stick']
    assert keys['Right Stick Left'] == 'J' and keys['Right Stick Down'] == 'K'
    assert keys['Cross'] == 'I' and keys['Right Stick Up'] != 'I'
    c.reset()
    assert rpcs3input.keys_of(update.settings[S.CONTROLS]) == rpcs3input.DEFAULT_KEYS


# --- Play ------------------------------------------------------------------------------------------------------------
def test_play_boots_the_built_in_rpcs3_through_blueline_config_with_the_blit_fix_and_controls(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'app'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'app'))
    folder, game, r = _builtin_host(tmp_path)
    me = types.SimpleNamespace(settings={}, host=FakeHost())
    assert UpdateController._play_command(me, r, None) == [emulator.exe_path(folder), os.path.normpath(game)]   # no config yet
    emulator.configure(folder)                                              # as Set up does after the firmware
    me = types.SimpleNamespace(settings={S.GAME: {'resolution': 300, 'fullscreen': True},
                                         S.CONTROLS: {'mode': 'keyboard'}}, host=FakeHost())
    command = UpdateController._play_command(me, r, None)
    assert command[0] == emulator.exe_path(folder) and '--no-gui' in command and '--fullscreen' in command
    config = command[command.index('--config') + 1]
    text = open(config, encoding='utf-8').read()
    assert rpcs3cfg.get(text, ('Video', 'Resolution Scale')) == '300'
    assert rpcs3cfg.get(text, ('Video', 'Disable Blit Engine Upscaling')) == 'true'
    assert command[-1] == os.path.normpath(game)
    assert '  Handler: Keyboard' in open(rpcs3input.files(folder)[0], encoding='utf-8').read().splitlines()


def test_play_on_the_players_rpcs3_leaves_their_config_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'app'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'app'))
    own = 'Video:\n  Resolution Scale: 200\n  Disable Blit Engine Upscaling: false\n'
    r = _own_rpcs3(tmp_path, own)
    me = types.SimpleNamespace(settings={}, host=FakeHost())
    command = UpdateController._play_command(me, r, None)
    config = command[command.index('--config') + 1]
    assert rpcs3cfg.get(open(config, encoding='utf-8').read(), ('Video', 'Disable Blit Engine Upscaling')) == 'true'
    assert open(os.path.join(r.folder, 'config', 'config.yml'), encoding='utf-8').read() == own
    assert not os.path.isdir(os.path.join(r.folder, 'config', 'input_configs'))
