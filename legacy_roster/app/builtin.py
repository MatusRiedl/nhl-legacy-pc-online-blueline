"""Setup's "Where is your game?" choice and the built-in RPCS3 (0.99.0, docs/notes/standalone.md). Slice `emulator`.

Three ways to play: Blueline's own RPCS3 (recommended: downloaded and set up for NHL Legacy, the goal light fixed), the
player's own RPCS3, NHL Legacy Native. For Blueline's RPCS3 the card shows three rows that turn green (RPCS3, the PS3 system
software, the game) and one Set up button that does what is missing. The roster scan stays UpdateController's: Set up ends
with update.set_rpcs3(the built-in's program), and so does picking it once it is ready.

    BuiltinController(host, update)
      snapshot()                  the card's view
      choose(kind)                'builtin' | 'rpcs3' | 'native'
      setup()                     download RPCS3 (pack rpcs3-win / rpcs3-linux), the system software (Sony's server), set up
      pick_game(folder) pick_pup() pick_folder() cancel() source_url()
"""
import os
import threading

from .. import datasource, emulator, packs, rpcs3input, savedata
from . import jobs
from . import settings as S

SLICE = 'emulator'
CHOICES = (('builtin', "Blueline's RPCS3"), ('rpcs3', "My RPCS3"), ('native', "NHL Legacy Native"))


class BuiltinController:
    def __init__(self, host, update):
        self.host, self.update = host, update
        self.lock = threading.RLock()
        self.wanted = False          # "Blueline's RPCS3" picked while another game is in use (its rows show)
        self.busy = False
        self.step = None             # what Set up does now
        self.bar = None              # 0-1, or None (a step without a measure)
        self.error = None
        self.game_error = None       # the game the player picked is not one RPCS3 can run
        self.pup = None              # a PS3UPDAT.PUP the player picked (Set up uses it instead of downloading)
        self.listed = None           # the packs server's entry for this system's RPCS3 pack (size, sha256), once looked
        self._looking = False
        self._stop = False

    @property
    def settings(self):
        return self.update.settings

    def changed(self):
        self.host.changed(SLICE)

    def folder(self):
        return self.settings.get(S.EMULATOR_FOLDER) or emulator.default_folder()

    def kind(self):
        """The kind of game in use now: 'builtin', 'native', 'rpcs3', or None."""
        r = self.update.rpcs3
        if r is None or r.plain:
            return None
        return 'builtin' if r.builtin else 'native' if r.native else 'rpcs3'

    def game(self):
        """(title, path) of the game the player picked for the built-in RPCS3, or (None, None)."""
        games = self.settings.get('games') or {}
        for title in savedata.GAMES:
            if games.get(title) and os.path.exists(games[title]):
                return title, games[title]
        return None, None

    def ready(self, folder=None):
        folder = folder or self.folder()
        title, path = self.game()
        return emulator.installed(folder) and bool(emulator.firmware_version(folder)) and bool(path) \
            and emulator.game_problem(path) is None

    # --- the choice --------------------------------------------------------------------------------------------
    def choose(self, kind):
        with self.lock:
            if self.busy or self.update.busy:
                return
            if kind == 'builtin':
                if self.ready():
                    self.wanted = False
                    self.changed()
                    folder = self.folder()
                    emulator.set_game(folder, *self.game())
                    self.update.set_rpcs3(emulator.exe_path(folder))
                    return
                self.wanted = True
                self.changed()
                self._look()
                return
            self.wanted = False
            self.changed()
            path = (self.settings.get('hosts') or {}).get(kind)
        if kind in ('rpcs3', 'native') and path and os.path.exists(path):
            self.update.set_rpcs3(path)
        elif kind in ('rpcs3', 'native'):
            self.update.pick_rpcs3()

    def _look(self):
        """Ask the packs server once for the RPCS3 pack's size (the row says how much it downloads)."""
        name = emulator.pack_name()
        if self.listed is not None or self._looking or not name:
            return
        self._looking = True

        def work():
            listed = packs.manifest(timeout=10)
            with self.lock:
                self._looking = False
                self.listed = (listed or {}).get(name) or {}
                self.changed()
        threading.Thread(target=work, daemon=True).start()

    # --- the rows ----------------------------------------------------------------------------------------------
    def _rows(self, folder):
        rows = []
        stamp = emulator.stamp(folder)
        if emulator.installed(folder):
            newer = self.listed and self.listed.get('sha256') and self.listed['sha256'] != stamp.get('sha256')
            text = f"RPCS3 {stamp.get('version') or ''}".strip() + " for NHL Legacy, with the goal light fixed."
            rows.append({'key': 'rpcs3', 'title': "RPCS3", 'done': True, 'tone': 'amber' if newer else 'good',
                         'text': "A newer build is ready: press Set up." if newer else text})
        else:
            size = (self.listed or {}).get('size')
            about = f" (about {round(size / 1024 ** 2)} MB)" if size else ""
            rows.append({'key': 'rpcs3', 'title': "RPCS3", 'done': False, 'tone': 'muted',
                         'text': f"Blueline downloads it{about} into a folder of its own."})
        version = emulator.firmware_version(folder)
        rows.append({'key': 'firmware', 'title': "PS3 system software", 'done': bool(version),
                     'tone': 'good' if version else 'muted',
                     'text': f"Version {version}." if version else
                     ("Your file PS3UPDAT.PUP is used." if self.pup else
                      "RPCS3 needs it once. Blueline downloads it from Sony's own update server (about 200 MB).")})
        title, path = self.game()
        problem = self.game_error or (emulator.game_problem(path) if path else None)
        if path and not problem:
            rows.append({'key': 'game', 'title': "Your game", 'done': True, 'tone': 'good',
                         'text': f"NHL Legacy ({savedata.region(title)}): {os.path.basename(os.path.normpath(path))}"})
        else:
            rows.append({'key': 'game', 'title': "Your game", 'done': False, 'tone': 'bad' if problem else 'muted',
                         'text': problem or "Pick a decrypted .iso of NHL Legacy (EU or NA), or the game's folder."})
        return rows

    def snapshot(self):
        with self.lock:
            kind = self.kind()
            export = self.update.export_mode
            can = emulator.pack_name() is not None
            if self.wanted or kind == 'builtin' or (kind is None and can and not export and not self.update.rpcs3):
                shown = 'builtin' if can else None
            else:
                shown = kind
            folder = self.folder()
            rows = self._rows(folder) if shown == 'builtin' else []
            installed = emulator.installed(folder)
            if rows and not installed:
                self._look()                 # the RPCS3 row says how much it downloads (also on the first start)
            ready = bool(rows) and all(r['done'] for r in rows) and rows[0]['tone'] == 'good'
            game_ok = bool(rows) and rows[2]['done']
            if self.busy:
                button = {'text': "Setting up...", 'can': False, 'why': None}
            elif ready and kind == 'builtin':
                button = None
            elif ready:
                button = {'text': "Use Blueline's RPCS3", 'can': not self.update.busy, 'why': None}
            else:
                why = None if game_ok else "Pick your game first."
                button = {'text': "Set up", 'can': game_ok and not self.update.busy, 'why': why}
            return {
                'shown': shown, 'in_use': kind,
                'choices': [{'kind': k, 'label': label, 'tag': "recommended" if k == 'builtin' else None,
                             'can': can if k == 'builtin' else True,
                             'why': None if can or k != 'builtin' else "There is no built-in RPCS3 for this system."}
                            for k, label in CHOICES],
                'rows': rows, 'button': button, 'busy': self.busy, 'step': self.step, 'bar': self.bar,
                'error': self.error, 'folder': folder, 'can_move': not installed and not self.busy,
                'pup': not rows[1]['done'] if rows else False,
                'source': (emulator.stamp(folder) or {}).get('source') if installed else None,
                'enabled': not self.busy and not self.update.busy,
            }

    # --- the player's picks ------------------------------------------------------------------------------------
    def pick_game(self, folder=False):
        with self.lock:
            if self.busy:
                return
        start = os.path.expanduser('~')
        if folder:
            path = self.host.ask_folder("Pick the folder of your NHL Legacy game (it holds PS3_GAME)", start)
        else:
            path = self.host.ask_open("Pick your NHL Legacy game", ['Game disc image (*.iso)', 'All files (*.*)'], start)
        if not path:
            return
        path = os.path.normpath(path)
        problem = emulator.game_problem(path)
        with self.lock:
            self.game_error = problem
            if problem is None:
                title = savedata.game_title_id(path)
                self.settings.setdefault('games', {})[title] = path
                S.save(self.settings)
                self.error = None
            self.changed()
            use = problem is None and self.kind() == 'builtin'
        if use:
            emulator.set_game(self.folder(), title, path)
            self.update.set_rpcs3(emulator.exe_path(self.folder()))

    def pick_pup(self):
        """The fallback when Sony's server cannot be reached: the player's own PS3UPDAT.PUP."""
        with self.lock:
            if self.busy:
                return
        path = self.host.ask_open("Pick the PS3 system software (PS3UPDAT.PUP)", ['PS3 system software (*.PUP)',
                                                                               'All files (*.*)'], os.path.expanduser('~'))
        if not path:
            return
        try:
            emulator.check_pup(path)
        except emulator.EmulatorError as err:
            with self.lock:
                self.error = str(err)
                self.changed()
            return
        with self.lock:
            self.pup, self.error = path, None
            self.changed()

    def pick_folder(self):
        """Another folder for the built-in RPCS3 (before it is set up: it takes a few GB)."""
        with self.lock:
            if self.busy or emulator.installed(self.folder()):
                return
        path = self.host.ask_folder("Where should Blueline put RPCS3? (it needs about 3 GB)", os.path.dirname(self.folder()))
        if not path:
            return
        target = os.path.join(os.path.normpath(path), 'Blueline RPCS3')
        with self.lock:
            if emulator.room(target) < emulator.NEEDED:
                self.error = f"There is not enough free space there: RPCS3 and the game need about " \
                             f"{emulator.NEEDED // 1024 ** 3} GB. Pick another folder."
            else:
                self.settings[S.EMULATOR_FOLDER] = target
                S.save(self.settings)
                self.error = None
            self.changed()

    def cancel(self):
        with self.lock:
            self._stop = True

    def source_url(self):
        """Where the built-in RPCS3's source is (the pack's index names it; only a GitHub address is opened)."""
        source = (emulator.stamp(self.folder()) or {}).get('source') or ''
        return source if source.startswith('https://github.com/') else None

    # --- Set up --------------------------------------------------------------------------------------------------
    def setup(self):
        with self.lock:
            if self.busy or self.update.busy:
                return
            title, path = self.game()
            problem = emulator.game_problem(path) if path else "Pick your game first."
            if problem:
                self.game_error = problem if path else None
                self.error = None if path else problem
                self.changed()
                return
            folder = self.folder()
            self.busy, self.error, self._stop, self.step, self.bar = True, None, False, "Starting...", None
            self.changed()
        jobs.run(lambda: self._setup(folder, title, path), done=self._done, failed=self._failed,
                 expected=(emulator.EmulatorError, savedata.Rpcs3Error, OSError),
                 context=lambda: [f"built-in RPCS3 folder: {folder}", f"game: {title} {path}"])

    def _say(self, step):
        with self.lock:
            self.step, self.bar = step, None
            self.changed()
        self.host.log(step)

    def _progress(self, step):
        def tell(fraction):
            with self.lock:
                self.step, self.bar = step, max(0.0, min(1.0, fraction))
                self.changed()
        return tell

    def _cancelled(self):
        return self._stop

    def _setup(self, folder, title, path):
        name = emulator.pack_name()
        if name is None:
            raise emulator.EmulatorError("There is no built-in RPCS3 for this system. Pick your own RPCS3.")
        if savedata.running_rpcs3():
            raise emulator.EmulatorError(f"{savedata.close_first()}: Blueline sets up its RPCS3 while the game is closed.")
        # 1. RPCS3 (the pack; a newer one replaces the program, never portable/)
        self._say("Looking for RPCS3 on the download server...")
        listed = packs.manifest()
        if listed is None and not emulator.installed(folder):
            raise emulator.EmulatorError("The download server did not answer. Check the internet connection and press "
                                         "Set up again.")
        if listed is not None:
            with self.lock:
                self.listed = listed.get(name) or {}
            if name not in listed and not emulator.installed(folder):
                raise emulator.EmulatorError("RPCS3 is not on the download server yet. Pick your own RPCS3 for now.")
            done, why = packs.sync(progress=self._progress("Downloading RPCS3..."), cancelled=self._cancelled,
                                   listed=listed, wanted=[name])
            if why:
                raise emulator.EmulatorError(f"RPCS3 could not be downloaded ({why}). Press Set up again.")
        pack = packs.path(name)
        if pack and (not emulator.installed(folder) or emulator.stamp(folder).get('sha256') != _sha(pack)):
            emulator.install(pack, folder, progress=self._progress("Unpacking RPCS3..."))
        if not emulator.installed(folder):
            raise emulator.EmulatorError("RPCS3 could not be set up. Press Set up again.")
        # 2. the PS3 system software (Sony's own server; the player's own file when picked)
        if not emulator.firmware_version(folder):
            pup = self.pup
            if not pup:
                target = os.path.join(datasource.app_dir('firmware'), 'PS3UPDAT.PUP')
                pup, _version = emulator.download_firmware(
                    target, progress=self._progress("Downloading the PS3 system software from Sony's server..."),
                    cancelled=self._cancelled)
            self._say("Installing the PS3 system software...")
            emulator.install_firmware(folder, pup)
            if pup != self.pup:
                try:
                    os.remove(pup)
                except OSError:
                    pass
        # 3. RPCS3's settings for the game, the controls (a controller unless the player chose the keyboard), the game
        emulator.configure(folder)
        rpcs3input.write(folder, self.settings.get(S.CONTROLS))
        emulator.set_game(folder, title, path)
        return folder

    def _done(self, folder):
        with self.lock:
            self.busy, self.step, self.bar, self.wanted, self.pup = False, None, None, False, None
            self.changed()
        self.host.log("Blueline's RPCS3 is set up. The first start of the game takes a few minutes longer: RPCS3 "
                      "prepares the game for your PC once.")
        self.update.set_rpcs3(emulator.exe_path(folder))

    def _failed(self, message):
        with self.lock:
            self.busy, self.step, self.bar = False, None, None
            self.error = "Stopped." if self._stop else message
            self.changed()


def _sha(path):
    return emulator._sha256(path)                      # noqa: SLF001 - one hash function for the pack and the stamp
