"""Setup's Game settings card (0.99.0, docs/notes/standalone.md). Slice `game`.

The player's choices are kept in settings `game` ({field: value}) and go into the config Play boots with
(rpcs3cfg.write_play: the app's own copy of the game's config, the player's RPCS3 files untouched). A field the player never
picked shows what the config holds now. NHL Legacy Native keeps its settings in its own launcher (rule 5: no ini writes).

    GameSettingsController(host, update)
      snapshot()              the card's view
      set(field, value)       one choice (value None: back to what RPCS3's config says)
      reset()                 every choice back to RPCS3's own
"""
import threading

from .. import onlinecfg, rpcs3cfg
from . import settings as S

SLICE = 'game'

# (field, label, [(value, label)]): the values are RPCS3's own words (rpcs3cfg.GAME_KEYS has where each lives).
FIELDS = (
    ('resolution', "Resolution", [(100, "720p"), (150, "1080p"), (200, "1440p"), (300, "4K")]),
    ('fullscreen', "Display", [(True, "Fullscreen"), (False, "Window")]),
    ('frame_limit', "Frame limit", [('Auto', "Auto"), ('30', "30"), ('60', "60"), ('Off', "Off")]),
    ('vsync', "VSync", [('Disabled', "Off"), ('Adaptive', "Adaptive"), ('Full', "On")]),
    ('volume', "Volume", [(0, "Mute"), (25, "25 %"), (50, "50 %"), (75, "75 %"), (100, "100 %")]),
)
FIELD_NAMES = tuple(f[0] for f in FIELDS)


def _same(value, word):
    """True when `value` (an option) is what the config's `word` says."""
    if word is None:
        return False
    if isinstance(value, bool):
        return word.lower() == str(value).lower()
    return str(value).lower() == word.strip().lower()


def _coerce(field, value):
    """`value` as the option it names, or None when it names none of the field's options."""
    for name, _label, options in FIELDS:
        if name == field:
            for option, _text in options:
                if option == value or str(option) == str(value):
                    return option
    return None


class GameSettingsController:
    def __init__(self, host, update):
        self.host, self.update = host, update
        self.lock = threading.RLock()

    @property
    def settings(self):
        return self.update.settings

    def changed(self):
        self.host.changed(SLICE)

    def choices(self):
        return dict(self.settings.get(S.GAME) or {})

    def _title(self, r):
        games = r.games() if r else {}
        slot = self.update.selected_slot() if hasattr(self.update, 'selected_slot') else None
        title = getattr(slot, 'title_id', None)
        return title if title in games else next(iter(games), None)

    def snapshot(self):
        with self.lock:
            r = self.update.rpcs3
            if r is None or r.plain or self.update.export_mode:
                return {'shown': False}
            if r.native:
                return {'shown': True, 'native': True, 'fields': [], 'locked': [],
                        'note': "NHL Legacy Native keeps its game settings in its own launcher."}
            title = self._title(r)
            base = onlinecfg.base_config(r, title) if title else ''
            choices = self.choices()
            fields = []
            for name, label, options in FIELDS:
                word = rpcs3cfg.get(base, rpcs3cfg.GAME_KEYS[name]) if base else None
                chosen = choices.get(name)
                rows = [{'value': value, 'label': text,
                         'on': (value == chosen) if chosen is not None else _same(value, word)} for value, text in options]
                fields.append({'key': name, 'label': label, 'options': rows, 'own': chosen is None,
                               'now': None if chosen is not None or any(o['on'] for o in rows) else word})
            scale = choices.get('resolution')
            if scale is None:
                word = rpcs3cfg.get(base, rpcs3cfg.GAME_KEYS['resolution']) if base else None
                scale = int(word) if word and word.isdigit() else 100
            locked = [{'label': "Disable Blit Engine Upscaling",
                       'text': "On by itself above 720p: without it matches load for ever." if scale != 100 else
                               "Not needed at 720p. Blueline turns it on by itself above 720p."}]
            if r.builtin:
                locked.insert(0, {'label': "Renderer", 'text': "Vulkan: the goal light needs it."})
            note = None
            if not base:
                note = "RPCS3 has not saved its settings yet: start it once, then these choices apply."
            return {'shown': True, 'native': False, 'fields': fields, 'locked': locked, 'note': note,
                    'builtin': r.builtin, 'can_reset': bool(choices) and not r.builtin,
                    'enabled': not self.update.busy}

    def set(self, field, value):
        with self.lock:
            if field not in FIELD_NAMES:
                return
            game = self.choices()
            option = _coerce(field, value) if value is not None else None
            if option is None:
                game.pop(field, None)
            else:
                game[field] = option
            self.settings[S.GAME] = game
            S.save(self.settings)
            self.changed()

    def reset(self):
        with self.lock:
            self.settings[S.GAME] = {}
            S.save(self.settings)
            self.changed()
