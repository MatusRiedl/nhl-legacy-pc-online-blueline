"""Controls of the built-in RPCS3: the Player 1 profile RPCS3 reads for NHL Legacy (standard library only).

RPCS3 reads `input_configs/<title id>/Default.yml` before its global profile (rpcs3/Emu/Io/pad_config.cpp `cfg_input::load`).
Blueline writes that per-game file for both titles in the built-in RPCS3's own config folder (emulator.config_dir). It owns the
`Player 1 Input:` block and nothing else: Players 2-7 and any other line stay as RPCS3 wrote them. Keys the block leaves out
take the handler's own defaults (pad_thread.cpp: "Reload with proper defaults"), so a controller profile names only its handler
and device and gets that handler's usual buttons.

    PADS / pads()          the controller kinds on this system: (key, RPCS3 handler, label)
    BUTTONS                the PS3 buttons of the keyboard table: (key in the file, label)
    DEFAULT_KEYS           the keyboard layout a reset gives (RPCS3's own, the right stick on I / J / K / L)
    MOUSE_STICK            the right stick on the mouse's movement (RPCS3's names)
    profile(choices)       the Player 1 block for the player's choices, as lines
    with_profile(text, choices)   a profile file's text with Blueline's Player 1 block in it
    write(folder, choices) both titles' files in the built-in RPCS3 at `folder`; the paths written
    first_joystick()       Linux: the first game controller's name as RPCS3's evdev handler names it, or ''

Key names are RPCS3's (Qt's key names: "A", "1", "Left", "Return", "Space", "Shift Left", "PgDown"...; mouse "Mouse Left",
"Mouse MLeft", "Wheel Up"). The page turns a key press into that name (web/js/update.js `rpcsKey`).
"""
import os
import sys

from . import emulator, savedata

WINDOWS = sys.platform == 'win32'

# (key, RPCS3's handler name, device, label). The device of a hidapi / XInput pad is "<name> #1" (the handlers'
# m_name_string); Linux's evdev names a pad by its kernel name, found when the file is written (first_joystick).
_WINDOWS_PADS = (
    ('xinput', 'XInput', 'XInput Pad #1', 'Xbox or other PC controller'),
    ('ds4', 'DualShock 4', 'DS4 Pad #1', 'DualShock 4 controller'),
    ('dualsense', 'DualSense', 'DualSense Pad #1', 'DualSense controller'),
)
_LINUX_PADS = (
    ('evdev', 'Evdev', None, 'Xbox or other controller'),
    ('ds4', 'DualShock 4', 'DS4 Pad #1', 'DualShock 4 controller'),
    ('dualsense', 'DualSense', 'DualSense Pad #1', 'DualSense controller'),
)
PADS = _WINDOWS_PADS if WINDOWS else _LINUX_PADS
MODES = ('controller', 'keyboard')

BUTTONS = (
    ('Left Stick Up', 'Left stick up'), ('Left Stick Down', 'Left stick down'),
    ('Left Stick Left', 'Left stick left'), ('Left Stick Right', 'Left stick right'),
    ('Right Stick Up', 'Right stick up'), ('Right Stick Down', 'Right stick down'),
    ('Right Stick Left', 'Right stick left'), ('Right Stick Right', 'Right stick right'),
    ('Cross', 'Cross'), ('Square', 'Square'), ('Circle', 'Circle'), ('Triangle', 'Triangle'),
    ('L1', 'L1'), ('R1', 'R1'), ('L2', 'L2'), ('R2', 'R2'), ('L3', 'L3 (press left stick)'), ('R3', 'R3 (press right stick)'),
    ('Up', 'D-pad up'), ('Down', 'D-pad down'), ('Left', 'D-pad left'), ('Right', 'D-pad right'),
    ('Start', 'Start'), ('Select', 'Select'),
)
BUTTON_KEYS = tuple(key for key, _label in BUTTONS)

# RPCS3's own keyboard layout (keyboard_pad_handler::init_config) with the right stick moved from Delete / End / PgDown / Home
# to I / J / K / L, beside the left hand's W / A / S / D. The PS button stays empty: it opens RPCS3's home menu over the game.
DEFAULT_KEYS = {
    'Left Stick Up': 'W', 'Left Stick Down': 'S', 'Left Stick Left': 'A', 'Left Stick Right': 'D',
    'Right Stick Up': 'I', 'Right Stick Down': 'K', 'Right Stick Left': 'J', 'Right Stick Right': 'L',
    'Cross': 'X', 'Square': 'Z', 'Circle': 'C', 'Triangle': 'V',
    'L1': 'Q', 'R1': 'E', 'L2': 'R', 'R2': 'T', 'L3': 'F', 'R3': 'G',
    'Up': 'Up', 'Down': 'Down', 'Left': 'Left', 'Right': 'Right',
    'Start': 'Return', 'Select': 'Space',
}
MOUSE_STICK = {
    'Right Stick Up': 'Mouse MUp', 'Right Stick Down': 'Mouse MDown',
    'Right Stick Left': 'Mouse MLeft', 'Right Stick Right': 'Mouse MRight',
}
MOUSE_BUTTONS = ('Mouse Left', 'Mouse Right', 'Mouse Middle', 'Mouse Back', 'Mouse Fwd', 'Wheel Up', 'Wheel Down')
# Keys a binding may not take: Escape leaves fullscreen and stops the game in RPCS3's window.
REFUSED = ('Esc', 'Escape')
FILE_NAME = 'Default.yml'
HEADER = 'Player 1 Input:'


def pads():
    """The controller kinds offered on this system: [(key, label)]."""
    return [(key, label) for key, _handler, _device, label in PADS]


def _pad(key):
    for row in PADS:
        if row[0] == key:
            return row
    return PADS[0]


def keys_of(choices):
    """The keyboard binding of every button: the player's own over DEFAULT_KEYS, the mouse on the right stick when asked."""
    choices = choices or {}
    keys = dict(DEFAULT_KEYS)
    for key, value in (choices.get('keys') or {}).items():
        if key in keys and isinstance(value, str) and value not in REFUSED:
            keys[key] = value
    if choices.get('mouse_stick'):
        keys.update(MOUSE_STICK)
    return keys


def _quoted(value):
    """A YAML scalar as RPCS3 writes it: plain when it is a plain word, quoted otherwise ("", "Null", punctuation, and
    "XInput Pad #1", where " #" would start a YAML comment)."""
    if value and all(ch.isalnum() or ch in ' -' for ch in value) and value[0].isalnum() and value not in ('Null', 'true', 'false'):
        return value
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def first_joystick(devices='/proc/bus/input/devices'):
    """Linux: the name RPCS3's evdev handler gives the first game controller (the kernel's name of the first device with a
    js handler), or '' when none is plugged in or the list cannot be read."""
    try:
        with open(devices, encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError:
        return ''
    for block in text.split('\n\n'):
        name, joystick = '', False
        for line in block.splitlines():
            if line.startswith('N: Name='):
                name = line[len('N: Name='):].strip().strip('"')
            elif line.startswith('H: Handlers='):
                joystick = any(part.startswith('js') for part in line[len('H: Handlers='):].split())
        if joystick and name:
            return name
    return ''


def profile(choices, joystick=None):
    """The `Player 1 Input:` block for `choices` ({'mode', 'pad', 'keys', 'mouse_stick'}), as lines."""
    choices = choices or {}
    if choices.get('mode') == 'keyboard':
        keys = keys_of(choices)
        lines = [HEADER, '  Handler: Keyboard', '  Device: Keyboard', '  Config:']
        lines += [f'    {key}: {_quoted(keys[key])}' for key in BUTTON_KEYS]
        lines.append('    PS Button: ""')
        return lines
    _key, handler, device, _label = _pad(choices.get('pad'))
    if device is None:
        device = first_joystick() if joystick is None else joystick
    return [HEADER, f'  Handler: {_quoted(handler)}', f'  Device: {_quoted(device or "")}']


def with_profile(text, choices, joystick=None):
    """`text` (a profile file, '' for none) with its `Player 1 Input:` block replaced by Blueline's; other lines kept."""
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.rstrip() == HEADER), None)
    block = profile(choices, joystick)
    if start is None:
        lines = block + lines
    else:
        end = start + 1
        while end < len(lines) and (not lines[end].strip() or lines[end].startswith(' ')):
            end += 1
        lines[start:end] = block
    return newline.join(lines) + newline


def files(folder):
    """The per-game profile files of both titles in the built-in RPCS3 at `folder`."""
    base = os.path.join(emulator.config_dir(folder), 'input_configs')
    return [os.path.join(base, title, FILE_NAME) for title in savedata.GAMES]


def write(folder, choices, joystick=None):
    """Write Blueline's Player 1 block into both titles' profile files of the built-in RPCS3 at `folder`; returns the paths.
    A file that already says the same is left alone."""
    written = []
    for path in files(folder):
        try:
            with open(path, encoding='utf-8', newline='') as f:
                old = f.read()
        except FileNotFoundError:
            old = ''
        new = with_profile(old, choices, joystick)
        if new == old:
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.tmp', 'w', encoding='utf-8', newline='') as f:
            f.write(new)
        os.replace(path + '.tmp', path)
        written.append(path)
    return written
