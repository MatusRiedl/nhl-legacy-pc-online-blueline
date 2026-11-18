"""Setup's Controls card for Blueline's RPCS3 (0.99.0, docs/notes/standalone.md). Slice `controls`.

A controller (the default: Xbox / PC pad, PlayStation 4 or 5) or the keyboard and mouse, every PS3 button on a key the player
presses. The choices are kept in settings `controls` ({'mode', 'pad', 'keys', 'mouse_stick'}) and written into the built-in
RPCS3's per-game profile files at once (rpcs3input.write), also at Set up and before Play. The player's own RPCS3 and NHL
Legacy Native keep their own controls; the card then says where to set them.

    ControlsController(host, update)
      snapshot()                    the card's view
      set_mode(mode)                'controller' | 'keyboard'
      set_pad(pad)                  a key of rpcs3input.PADS
      bind(button, name)            one PS3 button on a key / mouse button (RPCS3's name, from the page)
      set_mouse_stick(on)           the right stick on the mouse's movement
      reset()                       the keyboard layout back to rpcs3input.DEFAULT_KEYS
"""
import os
import threading

from .. import emulator, rpcs3input
from . import settings as S

SLICE = 'controls'


class ControlsController:
    def __init__(self, host, update):
        self.host, self.update = host, update
        self.lock = threading.RLock()
        self.error = None

    @property
    def settings(self):
        return self.update.settings

    def changed(self):
        self.host.changed(SLICE)

    def choices(self):
        c = dict(self.settings.get(S.CONTROLS) or {})
        c['mode'] = c.get('mode') if c.get('mode') in rpcs3input.MODES else 'controller'
        c['pad'] = c.get('pad') if c.get('pad') in [k for k, _l in rpcs3input.pads()] else rpcs3input.PADS[0][0]
        c['keys'] = dict(c.get('keys') or {})
        c['mouse_stick'] = bool(c.get('mouse_stick'))
        return c

    def _folder(self):
        """The built-in RPCS3's folder when it is the game in use, else None."""
        r = self.update.rpcs3
        if r is None or not r.builtin:
            return None
        return os.path.dirname(r.exe)

    def snapshot(self):
        with self.lock:
            r = self.update.rpcs3
            if r is None or r.plain or self.update.export_mode:
                return {'shown': False}
            if not r.builtin:
                where = "in its own launcher" if r.native else "in RPCS3's own window: Configuration > Pads"
                return {'shown': True, 'own': True, 'note': f"Your {r.name} keeps its controls: set them {where}."}
            c = self.choices()
            keys = rpcs3input.keys_of(c)
            return {
                'shown': True, 'own': False, 'mode': c['mode'],
                'modes': [{'key': 'controller', 'label': "Controller"}, {'key': 'keyboard', 'label': "Keyboard and mouse"}],
                'pad': c['pad'], 'pads': [{'key': k, 'label': label} for k, label in rpcs3input.pads()],
                'buttons': [{'key': key, 'label': label, 'value': keys[key],
                             'mouse': key in rpcs3input.MOUSE_STICK and c['mouse_stick'],
                             'changed': keys[key] != rpcs3input.DEFAULT_KEYS[key]}
                            for key, label in rpcs3input.BUTTONS],
                'mouse_stick': c['mouse_stick'], 'mouse_buttons': list(rpcs3input.MOUSE_BUTTONS),
                'refused': list(rpcs3input.REFUSED),
                'can_reset': bool(c['keys']) or c['mouse_stick'],
                'error': self.error, 'enabled': not self.update.busy,
            }

    def _save(self, c):
        self.settings[S.CONTROLS] = c
        S.save(self.settings)
        self.apply()

    def apply(self, folder=None):
        """Write the choices into the built-in RPCS3's profile files (when it is set up). Returns the paths written."""
        folder = folder or self._folder()
        if not folder or not emulator.installed(folder):
            return []
        try:
            written = rpcs3input.write(folder, self.choices())
            self.error = None
            return written
        except OSError as err:
            self.error = f"The controls could not be saved ({err})."
            self.host.log(self.error)
            return []

    def set_mode(self, mode):
        with self.lock:
            if mode not in rpcs3input.MODES:
                return
            c = self.choices()
            c['mode'] = mode
            self._save(c)
            self.changed()

    def set_pad(self, pad):
        with self.lock:
            if pad not in [k for k, _l in rpcs3input.pads()]:
                return
            c = self.choices()
            c['pad'], c['mode'] = pad, 'controller'
            self._save(c)
            self.changed()

    def bind(self, button, name):
        with self.lock:
            if button not in rpcs3input.BUTTON_KEYS or not isinstance(name, str) or not name.strip():
                return
            name = name.strip()
            if name in rpcs3input.REFUSED:
                self.error = "Escape stays RPCS3's own (it leaves the game). Pick another key."
                self.changed()
                return
            c = self.choices()
            keys = rpcs3input.keys_of(c)
            old = keys[button] if keys[button] not in rpcs3input.MOUSE_STICK.values() else rpcs3input.DEFAULT_KEYS[button]
            # a key on two buttons: the other button gets this button's old key (a swap), so no key does two things
            for other, value in keys.items():
                if other != button and value == name:
                    c['keys'][other] = old
            c['keys'][button] = name
            if button in rpcs3input.MOUSE_STICK and c['mouse_stick']:
                c['mouse_stick'] = False
                for key in rpcs3input.MOUSE_STICK:
                    if key != button and key not in c['keys']:
                        c['keys'][key] = rpcs3input.DEFAULT_KEYS[key]
            c['keys'] = {k: v for k, v in c['keys'].items() if v != rpcs3input.DEFAULT_KEYS.get(k)}
            self.error = None
            self._save(c)
            self.changed()

    def set_mouse_stick(self, on):
        with self.lock:
            c = self.choices()
            c['mouse_stick'] = bool(on)
            if on:
                for key in rpcs3input.MOUSE_STICK:
                    c['keys'].pop(key, None)
            self._save(c)
            self.changed()

    def reset(self):
        with self.lock:
            c = self.choices()
            c['keys'], c['mouse_stick'] = {}, False
            self.error = None
            self._save(c)
            self.changed()
