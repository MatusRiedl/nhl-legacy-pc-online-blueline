"""rpcs3cfg: RPCS3's config.yml one key at a time, and the config Play boots with."""
from types import SimpleNamespace

from legacy_roster import rpcs3cfg

EU = 'BLES02153'
CONFIG = """Core:
  PPU Decoder: Recompiler (LLVM)
  SPU XFloat Accuracy: Approximate
Video:
  Renderer: Vulkan
  Frame limit: Auto
  VSync Mode: Disabled
  Resolution Scale: 100
  Disable Blit Engine Upscaling: false
  Vulkan:
    Adapter: "Some GPU"
    Exclusive Fullscreen Mode: Automatic
  Performance Overlay:
    Enabled: false
Audio:
  Renderer: Cubeb
  Master Volume: 100
Miscellaneous:
  Automatically start games after boot: true
  Exit RPCS3 when process finishes: false
  Start games in fullscreen mode: true
  GDB Server: 127.0.0.1:2345
"""


def test_get_reads_a_key_by_its_blocks_and_takes_quotes_off():
    assert rpcs3cfg.get(CONFIG, ('Video', 'Resolution Scale')) == '100'
    assert rpcs3cfg.get(CONFIG, ('Video', 'Vulkan', 'Adapter')) == 'Some GPU'
    assert rpcs3cfg.get(CONFIG, ('Audio', 'Renderer')) == 'Cubeb'           # the same key name in another block
    assert rpcs3cfg.get(CONFIG, ('Video', 'Renderer')) == 'Vulkan'
    assert rpcs3cfg.get(CONFIG, ('Miscellaneous', 'GDB Server')) == '127.0.0.1:2345'
    assert rpcs3cfg.get(CONFIG, ('Video', 'Enabled')) is None              # only inside Performance Overlay
    assert rpcs3cfg.get(CONFIG, ('Net', 'PSN status')) is None


def test_put_changes_one_line_and_keeps_every_other():
    out = rpcs3cfg.put(CONFIG, ('Video', 'Resolution Scale'), 300)
    assert out == CONFIG.replace('Resolution Scale: 100', 'Resolution Scale: 300')
    assert rpcs3cfg.put(out, ('Video', 'Resolution Scale'), 100) == CONFIG
    assert rpcs3cfg.put(CONFIG, ('Video', 'Frame limit'), 'Auto') == CONFIG      # the same value: byte for byte
    out = rpcs3cfg.put(CONFIG, ('Miscellaneous', 'Start games in fullscreen mode'), False)
    assert 'Start games in fullscreen mode: false' in out
    out = rpcs3cfg.put(CONFIG, ('Video', 'Vulkan', 'Exclusive Fullscreen Mode'), 'Disable')
    assert out == CONFIG.replace('Mode: Automatic', 'Mode: Disable')


def test_put_adds_a_missing_key_at_the_end_of_its_block_and_a_missing_block_at_the_end():
    out = rpcs3cfg.put(CONFIG, ('Audio', 'Buffer Duration'), 100)
    lines = out.splitlines()
    assert lines[lines.index('  Master Volume: 100') + 1] == '  Buffer Duration: 100'
    assert rpcs3cfg.get(out, ('Audio', 'Buffer Duration')) == '100'
    out = rpcs3cfg.put(CONFIG, ('Video', 'Vulkan', 'Asynchronous Texture Streaming 2'), 'true')
    assert out.splitlines()[out.splitlines().index('    Exclusive Fullscreen Mode: Automatic') + 1] == \
        '    Asynchronous Texture Streaming 2: true'
    out = rpcs3cfg.put(CONFIG, ('Video', 'Shaders', 'Mode'), 'Async')       # a new block inside Video, before Audio
    assert rpcs3cfg.get(out, ('Video', 'Shaders', 'Mode')) == 'Async'
    assert out.index('  Shaders:') < out.index('Audio:')
    out = rpcs3cfg.put(CONFIG, ('Net', 'Internet enabled'), 'Connected')
    assert out.endswith('Net:\n  Internet enabled: Connected\n')
    assert rpcs3cfg.put('', ('Video', 'Resolution Scale'), 150) == 'Video:\n  Resolution Scale: 150\n'


def test_windows_line_endings_stay():
    crlf = CONFIG.replace('\n', '\r\n')
    out = rpcs3cfg.put(crlf, ('Audio', 'Master Volume'), 40)
    assert out == crlf.replace('Master Volume: 100', 'Master Volume: 40')
    assert '\n' not in out.replace('\r\n', '')


def test_apply_sets_the_chosen_fields_and_ticks_the_blit_box_above_100():
    out = rpcs3cfg.apply(CONFIG, {'resolution': 300, 'fullscreen': False, 'frame_limit': '60', 'vsync': 'Adaptive',
                                  'volume': 0})
    assert rpcs3cfg.get(out, ('Video', 'Resolution Scale')) == '300'
    assert rpcs3cfg.get(out, ('Video', 'Disable Blit Engine Upscaling')) == 'true'
    assert rpcs3cfg.get(out, ('Miscellaneous', 'Start games in fullscreen mode')) == 'false'
    assert rpcs3cfg.get(out, ('Video', 'Frame limit')) == '60'
    assert rpcs3cfg.get(out, ('Video', 'VSync Mode')) == 'Adaptive'
    assert rpcs3cfg.get(out, ('Audio', 'Master Volume')) == '0'
    assert rpcs3cfg.apply(CONFIG, {}) == CONFIG                              # RPCS3's own everywhere, at 100 %
    assert rpcs3cfg.apply(CONFIG, {'resolution': None, 'volume': None}) == CONFIG
    own = rpcs3cfg.put(CONFIG, ('Video', 'Resolution Scale'), 200)           # the player's own scale gets the fix too
    assert rpcs3cfg.get(rpcs3cfg.apply(own, {}), ('Video', 'Disable Blit Engine Upscaling')) == 'true'


def test_write_play_is_the_apps_own_file_and_rpcs3s_files_stay(tmp_path):
    root = tmp_path / 'rpcs3'
    (root / 'config' / 'custom_configs').mkdir(parents=True)
    (root / 'config' / 'config.yml').write_text(CONFIG, encoding='utf-8', newline='')
    custom = CONFIG.replace('Master Volume: 100', 'Master Volume: 55')
    (root / 'config' / 'custom_configs' / f'config_{EU}.yml').write_text(custom, encoding='utf-8', newline='')
    rpcs3 = SimpleNamespace(folder=str(root), flatpak=False)
    path = rpcs3cfg.write_play(rpcs3, EU, {'resolution': 150})
    assert str(tmp_path) not in path                                        # the program's folder (LOCALAPPDATA of the tests)
    text = open(path, encoding='utf-8', newline='').read()
    assert rpcs3cfg.get(text, ('Audio', 'Master Volume')) == '55'            # the game's custom config is the base
    assert rpcs3cfg.get(text, ('Video', 'Resolution Scale')) == '150'
    assert rpcs3cfg.get(text, ('Video', 'Disable Blit Engine Upscaling')) == 'true'
    assert (root / 'config' / 'config.yml').read_text(encoding='utf-8') == CONFIG
    assert (root / 'config' / 'custom_configs' / f'config_{EU}.yml').read_text(encoding='utf-8') == custom


def test_write_play_gives_none_when_rpcs3_never_wrote_a_config(tmp_path):
    rpcs3 = SimpleNamespace(folder=str(tmp_path / 'rpcs3'), flatpak=False)
    assert rpcs3cfg.write_play(rpcs3, EU, {'resolution': 300}) is None
