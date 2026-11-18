"""RPCS3's config.yml as text, one key at a time, and the config Play boots with (standard library only).

RPCS3 writes plain YAML: two spaces per level, `Key: value`, a block header `Name:` with nothing after it. These helpers walk
that layout line by line, so every line they do not set stays as it was (line endings included). The player's own files are
only read; what Play boots with is the app's own copy (docs/notes/standalone.md).

    get(text, path)              the value at `path` (('Video', 'Resolution Scale')), or None
    put(text, path, value)       `text` with that key set; a missing key goes at the end of its block, a missing block at the end
    GAME_KEYS                    the Game settings card's keys (field -> key path in config.yml)
    apply(text, choices)         `text` with the player's Game settings, then the blit fix (onlinecfg.blit_config)
    write_play(rpcs3, title, choices)   that config as the app's own file play/config_<TITLE>.yml; its path (None: no config)
    BUILTIN_DEFAULTS             what the built-in RPCS3's config.yml gets when it is set up
"""
import os

from . import datasource, onlinecfg

# The Game settings card (app/gamesettings.py): field -> where it lives in config.yml (RPCS3 source, rpcs3/Emu/system_config.h,
# value names from system_config_types.cpp: Frame limit Off / 30 / 50 / 60 / 120 / Display / Auto / PS3 Native / Infinite,
# VSync Mode Disabled / Adaptive / Full, Resolution Scale 25-800, Master Volume 0-200).
GAME_KEYS = {
    'resolution': ('Video', 'Resolution Scale'),
    'fullscreen': ('Miscellaneous', 'Start games in fullscreen mode'),
    'frame_limit': ('Video', 'Frame limit'),
    'vsync': ('Video', 'VSync Mode'),
    'volume': ('Audio', 'Master Volume'),
}

# Written into the built-in RPCS3's own config.yml when it is set up (its folder is the program's; rule 5 is about the player's).
BUILTIN_DEFAULTS = (
    (('Video', 'Renderer'), 'Vulkan'),                                       # the goal light fix is a Vulkan shader
    (('Video', 'Disable Blit Engine Upscaling'), 'true'),                    # no endless loading above 100 % also when the
                                                                             # player starts it by hand (nothing to undo at 100 %)
    (('Miscellaneous', 'Automatically start games after boot'), 'true'),
    (('Miscellaneous', 'Exit RPCS3 when process finishes'), 'true'),         # closing the game closes RPCS3 too
    (('Miscellaneous', 'Show trophy popups'), 'false'),
)


def _newline(text):
    return '\r\n' if '\r\n' in text else '\n'


def _indent(line):
    return len(line) - len(line.lstrip(' '))


def _block(lines, path):
    """(header line, end) of the block named by `path` (a tuple of headers), or None. The block's lines are header + 1 to
    end (exclusive). path () is the whole file: (-1, len(lines))."""
    start, end = -1, len(lines)
    for depth, name in enumerate(path):
        want = '  ' * depth + name + ':'
        found = None
        for i in range(start + 1, end):
            if lines[i].rstrip() == want:
                found = i
                break
        if found is None:
            return None
        stop = found + 1
        while stop < end and (not lines[stop].strip() or _indent(lines[stop]) > 2 * depth):
            stop += 1
        start, end = found, stop
    return start, end


def _key_line(lines, path):
    """The index of `path`'s key line (path[-1] inside the block path[:-1]), or None."""
    block = _block(lines, path[:-1])
    if block is None:
        return None
    prefix = '  ' * (len(path) - 1) + path[-1] + ':'
    for i in range(block[0] + 1, block[1]):
        if lines[i].startswith(prefix) and _indent(lines[i]) == 2 * (len(path) - 1):
            return i
    return None


def _plain(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
        value = value[1:-1]
    return value


def get(text, path):
    """The value of the key at `path` (block headers, then the key), quotes taken off, or None when it is not there."""
    lines = text.splitlines()
    i = _key_line(lines, tuple(path))
    return None if i is None else _plain(lines[i].partition(':')[2])


def put(text, path, value):
    """`text` with the key at `path` set to `value` (written as it is: numbers, true / false, RPCS3's plain words). A missing
    key goes after the last line of its block; missing blocks are added at the end of the file. Every other line is kept."""
    path = tuple(path)
    value = str(value).lower() if isinstance(value, bool) else str(value)
    newline, lines = _newline(text), text.splitlines()
    line = '  ' * (len(path) - 1) + f'{path[-1]}: {value}'
    i = _key_line(lines, path)
    if i is not None:
        lines[i] = line
    else:
        depth = 0
        while depth < len(path) - 1 and _block(lines, path[:depth + 1]) is not None:
            depth += 1
        if depth == len(path) - 1:
            end = _block(lines, path[:-1])[1]
            while end > 0 and not lines[end - 1].strip():
                end -= 1
            lines.insert(end, line)
        else:
            add = ['  ' * d + name + ':' for d, name in enumerate(path[depth:-1], depth)] + [line]
            end = len(lines) if depth == 0 else _block(lines, path[:depth])[1]
            while depth and end > 0 and not lines[end - 1].strip():
                end -= 1
            lines[end:end] = add
    return newline.join(lines) + (newline if text.endswith('\n') or not text else '')


def apply(text, choices):
    """`text` (a config.yml) with the player's Game settings `choices` ({field: value}; a field left out or None keeps the
    config's own value), then the blit fix: at a resolution scale other than 100 % "Disable Blit Engine Upscaling" is ticked,
    or matches load for ever (onlinecfg.blit_config)."""
    for field, path in GAME_KEYS.items():
        value = (choices or {}).get(field)
        if value is not None:
            text = put(text, path, value)
    return onlinecfg.blit_config(text)


def play_dir(rpcs3):
    """Where Play's config goes: the program's folder, except for the Flatpak RPCS3, which cannot see it (onlinecfg.config_dir)."""
    if rpcs3.flatpak:
        where = os.path.join(rpcs3.folder, 'play')
        os.makedirs(where, exist_ok=True)
        return where
    return datasource.app_dir('play')


def write_play(rpcs3, title, choices=None):
    """Write the config Play boots `title` with (the player's config for the game + their Game settings + the blit fix) to
    play/config_<TITLE>.yml in the program's folder. Returns its path, or None when RPCS3 has no config.yml yet (it never ran):
    a file of a few keys would set every other key to RPCS3's default, so Play then boots as before. RPCS3's own files are not
    touched."""
    base = onlinecfg.base_config(rpcs3, title)
    if not base.strip():
        return None
    path = os.path.join(play_dir(rpcs3), f'config_{title}.yml')
    text = apply(base, choices)
    with open(path + '.tmp', 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    os.replace(path + '.tmp', path)
    return path
