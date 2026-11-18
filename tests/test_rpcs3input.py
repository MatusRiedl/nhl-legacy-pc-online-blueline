"""rpcs3input: the Player 1 profile Blueline writes for the built-in RPCS3."""
import os

from legacy_roster import emulator, rpcs3input, savedata


def _parse(lines):
    """The block's `Config:` keys as {key: value} with quotes taken off (enough for these tests)."""
    out = {}
    for line in lines:
        if line.startswith('    ') and ':' in line:
            key, value = line.strip().split(':', 1)
            value = value.strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace('\\"', '"').replace('\\\\', '\\')
            out[key] = value
    return out


def test_a_keyboard_profile_names_every_button_and_leaves_the_ps_button_empty():
    lines = rpcs3input.profile({'mode': 'keyboard', 'keys': {'Cross': 'Shift Left'}})
    assert lines[:4] == ['Player 1 Input:', '  Handler: Keyboard', '  Device: Keyboard', '  Config:']
    keys = _parse(lines)
    assert set(rpcs3input.BUTTON_KEYS) <= set(keys)
    assert keys['Cross'] == 'Shift Left' and keys['Square'] == 'Z' and keys['Start'] == 'Return'
    assert keys['PS Button'] == ''


def test_the_mouse_stick_puts_the_mouse_on_the_right_stick_and_escape_is_never_bound():
    keys = rpcs3input.keys_of({'mouse_stick': True, 'keys': {'Right Stick Up': 'I', 'Cross': 'Esc'}})
    assert keys['Right Stick Up'] == 'Mouse MUp' and keys['Right Stick Left'] == 'Mouse MLeft'
    assert keys['Cross'] == rpcs3input.DEFAULT_KEYS['Cross']
    assert rpcs3input.keys_of(None) == rpcs3input.DEFAULT_KEYS


def test_a_controller_profile_names_only_handler_and_device_quoted_where_yaml_needs_it():
    pad = rpcs3input.PADS[1]                               # DualShock 4 on every system
    lines = rpcs3input.profile({'mode': 'controller', 'pad': pad[0]})
    assert lines == ['Player 1 Input:', f'  Handler: {pad[1]}', '  Device: "DS4 Pad #1"']
    assert rpcs3input._quoted('XInput Pad #1') == '"XInput Pad #1"'      # " #" would start a YAML comment
    assert rpcs3input._quoted('Shift Left') == 'Shift Left'
    assert rpcs3input._quoted('') == '""' and rpcs3input._quoted('Null') == '"Null"'
    assert rpcs3input._quoted(',') == '","'


def test_an_unknown_pad_falls_back_to_the_first_and_evdev_takes_the_joystick_given():
    lines = rpcs3input.profile({'pad': 'nope'}, joystick='Microsoft X-Box 360 pad')
    handler, device = rpcs3input.PADS[0][1], rpcs3input.PADS[0][2]
    assert lines[1] == f'  Handler: {handler}'
    if device is None:                                     # Linux: evdev, the joystick's kernel name
        assert lines[2] == '  Device: Microsoft X-Box 360 pad'


def test_with_profile_replaces_player_1_and_keeps_the_other_players_and_newlines():
    text = ('Player 1 Input:\r\n  Handler: Null\r\n  Device: ""\r\n  Config:\r\n    Cross: X\r\n'
            'Player 2 Input:\r\n  Handler: Null\r\n  Device: ""\r\n')
    new = rpcs3input.with_profile(text, {'mode': 'keyboard'})
    assert '\r\n' in new and '\n' not in new.replace('\r\n', '')
    lines = new.split('\r\n')
    assert lines.count('Player 1 Input:') == 1 and 'Player 2 Input:' in lines
    assert lines[lines.index('Player 2 Input:') + 1] == '  Handler: Null'
    assert '  Handler: Keyboard' in lines
    assert rpcs3input.with_profile('', {'mode': 'keyboard'}).startswith('Player 1 Input:\n')
    again = rpcs3input.with_profile(new, {'mode': 'keyboard'})
    assert again == new


def test_write_fills_both_titles_once_and_leaves_a_file_that_says_the_same(tmp_path):
    folder = str(tmp_path / 'rpcs3')
    choices = {'mode': 'keyboard', 'keys': {'Start': 'P'}}
    written = rpcs3input.write(folder, choices)
    assert len(written) == len(savedata.GAMES)
    for title in savedata.GAMES:
        path = os.path.join(emulator.config_dir(folder), 'input_configs', title, 'Default.yml')
        assert path in written
        assert '    Start: P' in open(path, encoding='utf-8').read().splitlines()
    assert rpcs3input.write(folder, choices) == []
    assert not [n for n in os.listdir(os.path.dirname(written[0])) if n.endswith('.tmp')]
    assert len(rpcs3input.write(folder, {'mode': 'controller', 'pad': 'ds4'})) == len(savedata.GAMES)


def test_first_joystick_reads_the_kernels_device_list(tmp_path):
    devices = tmp_path / 'devices'
    devices.write_text(
        'I: Bus=0003 Vendor=046d\nN: Name="Logitech USB Keyboard"\nH: Handlers=sysrq kbd event3\n\n'
        'I: Bus=0003 Vendor=045e\nN: Name="Microsoft X-Box 360 pad"\nH: Handlers=event5 js0\n\n', encoding='utf-8')
    assert rpcs3input.first_joystick(str(devices)) == 'Microsoft X-Box 360 pad'
    assert rpcs3input.first_joystick(str(tmp_path / 'missing')) == ''
