"""The built-in RPCS3 (0.99.0, docs/notes/standalone.md): an RPCS3 the program downloads and sets up for NHL Legacy alone, in a
folder of its own. Standard library only.

    folder/                       default datasource.app_dir('rpcs3'), or the player's choice (setting `emulator_folder`)
      rpcs3.exe | rpcs3.AppImage  the program, from the pack `rpcs3-win` / `rpcs3-linux` (packs.py, sha256-checked)
      index.json LICENSE SOURCE.txt   which build it is and where its source is (GPL v2)
      blueline.json               the mark of the built-in copy (savedata.BUILTIN_STAMP): the pack it came from
      portable/                   ALL of RPCS3's data: config, dev_flash (the system software), dev_hdd0 (saves, the game's
                                  update), caches, logs (RPCS3's get_config_dir: a "portable" folder next to the program wins)

It is an ordinary savedata.Rpcs3 rooted in portable/ (`host`), so the game patch, pictures, saves and updates work as on any
RPCS3. Its folder is the program's own: its config.yml, games.yml and input files are written freely (AGENTS.md rule 5 is
about the player's RPCS3). Rule 1 holds for the saves inside it as everywhere.

    pack_name()                   'rpcs3-win' / 'rpcs3-linux' / None (no build for this system)
    exe_path(folder) installed(folder) stamp(folder) room(folder)
    install(zip_path, folder)     unpack the pack's program files (never portable/), mark the folder
    firmware_version(folder)      '4.93' when the PS3 system software is installed, else None
    firmware_offer() download_firmware(target) check_pup(path, md5) install_firmware(folder, pup)
    game_problem(path) set_game(folder, title, path) configure(folder) host(folder, games)
    config_dir(folder) log_file(folder)   portable/config (Windows) or portable (Linux); the log

On Linux RPCS3's cache and log ignore portable/ (XDG_CACHE_HOME or ~/.cache/rpcs3), so savedata.launch starts the built-in copy
with XDG_CACHE_HOME in its folder (cache/).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

from . import datasource, onlinecfg, rpcs3cfg, savedata

WINDOWS = os.name == 'nt'
LINUX = sys.platform.startswith('linux')
PACKS = {'win': 'rpcs3-win', 'linux': 'rpcs3-linux'}
EXE = 'rpcs3.exe' if WINDOWS else 'rpcs3.AppImage'
NEEDED = 3 * 1024 ** 3          # program + system software + shader caches + the game's update: keep 3 GB free
INDEX = 'index.json'

# The PS3 system software, from Sony's own update server (never hosted by us). The list names the full file PS3UPDAT.PUP; the
# folder in its address is the file's MD5. Every region's list names the same file (2026-11-16: 4.93, MD5 a2b60b6a...).
FIRMWARE_LIST = 'http://f{0}01.ps3.update.playstation.net/update/ps3/list/{0}/ps3-updatelist.txt'
FIRMWARE_REGIONS = ('us', 'eu')
FIRMWARE_AGENT = 'PS3Update-agent/1.0.0 libhttp/1.0.0'
FIRMWARE_SHA256 = {'4.93': '158471fd834f8ea8036136b6aab43cd86c7ba73d79ca30e0af3c0fe0001cf365'}   # checked 2026-11-16
FIRMWARE_SIZE = 210 * 1024 ** 2          # about; for the progress bar until the server says
PUP_MAGIC = b'SCEUF'


class EmulatorError(Exception):
    """Something the player must know (the message says what to do, in plain words)."""


def pack_name():
    """The pack with the built-in RPCS3 for this system, or None (a Mac: no build)."""
    return PACKS['win'] if WINDOWS else PACKS['linux'] if LINUX else None


def default_folder():
    return datasource.app_dir('rpcs3')


def exe_path(folder):
    return os.path.join(folder, EXE)


def data_dir(folder):
    return os.path.join(folder, savedata.PORTABLE)


def config_dir(folder):
    """Where the built-in RPCS3 reads config.yml, games.yml and input_configs/: portable/config on Windows, portable/ itself on
    Linux (RPCS3's get_config_dir adds the config/ folder on Windows only)."""
    return os.path.join(data_dir(folder), 'config') if WINDOWS else data_dir(folder)


def log_file(folder):
    """The built-in RPCS3's log: portable/log/RPCS3.log on Windows; on Linux its cache folder, which savedata.launch keeps in
    the folder too (savedata.builtin_cache)."""
    if WINDOWS:
        return os.path.join(data_dir(folder), 'log', 'RPCS3.log')
    return os.path.join(savedata.builtin_cache(exe_path(folder)), 'rpcs3', 'RPCS3.log')


def installed(folder):
    """Is the built-in RPCS3 unpacked in `folder` (the program, its mark and its data folder)?"""
    return bool(folder) and os.path.isfile(exe_path(folder)) and os.path.isfile(os.path.join(folder, savedata.BUILTIN_STAMP)) \
        and os.path.isdir(data_dir(folder))


def stamp(folder):
    """What blueline.json says ({'sha256', 'version', ...}), or {}."""
    try:
        with open(os.path.join(folder, savedata.BUILTIN_STAMP), encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def room(folder):
    """Free bytes on the drive `folder` is (or would be) on."""
    where = os.path.abspath(folder)
    while not os.path.isdir(where) and os.path.dirname(where) != where:
        where = os.path.dirname(where)
    try:
        return shutil.disk_usage(where).free
    except OSError:
        return 0


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def _member_ok(name):
    parts = name.replace('\\', '/').split('/')
    return not (name.startswith(('/', '\\')) or re.match(r'^[A-Za-z]:', name) or '..' in parts
                or parts[0].lower() in (savedata.PORTABLE, savedata.BUILTIN_STAMP.lower()))


def install(zip_path, folder, progress=None):
    """Unpack the pack `zip_path` into `folder`: the program files are replaced, portable/ (the player's saves, system software,
    settings) is never touched. Marks the folder (blueline.json). `progress(fraction)`. Returns the stamp."""
    if not installed(folder) and room(folder) < NEEDED:
        raise EmulatorError(f"There is not enough free space there: RPCS3 and the game need about {NEEDED // 1024 ** 3} GB. "
                            "Pick another folder.")
    if _running_in(folder):
        raise EmulatorError("Close NHL Legacy first: the built-in RPCS3 is running.")
    os.makedirs(folder, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        members = [m for m in z.infolist() if not m.is_dir()]
        bad = [m.filename for m in members if not _member_ok(m.filename)]
        if bad:
            raise EmulatorError("The RPCS3 download holds files it should not, so it was not used.")
        index = {}
        if INDEX in z.namelist():
            try:
                index = json.loads(z.read(INDEX).decode('utf-8'))
            except ValueError:
                index = {}
        total = sum(m.file_size for m in members) or 1
        done = 0
        for m in members:
            target = os.path.join(folder, *m.filename.replace('\\', '/').split('/'))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(m) as src, open(target + '.part', 'wb') as out:
                shutil.copyfileobj(src, out, 1 << 20)
            os.replace(target + '.part', target)
            done += m.file_size
            if progress:
                progress(done / total)
    os.makedirs(data_dir(folder), exist_ok=True)
    icons = os.path.join(folder, 'Icons')
    if os.path.isdir(icons):        # in a portable copy RPCS3 looks for its own overlay pictures inside portable/ (lab 2026-11-16)
        shutil.copytree(icons, os.path.join(data_dir(folder), 'Icons'), dirs_exist_ok=True)
    if not WINDOWS:
        exe = exe_path(folder)
        os.chmod(exe, os.stat(exe).st_mode | 0o111)
    mark = {'sha256': _sha256(zip_path), 'version': index.get('version'), 'source': index.get('source'),
            'commit': index.get('commit'), 'installed': time.strftime('%Y-%m-%d %H:%M:%S')}
    path = os.path.join(folder, savedata.BUILTIN_STAMP)
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(mark, f, indent=1)
    os.replace(path + '.tmp', path)
    return mark


def _running_in(folder):
    running = savedata.running_rpcs3()
    return bool(running) and os.path.normcase(os.path.abspath(running)) == os.path.normcase(os.path.abspath(exe_path(folder)))


def firmware_version(folder):
    """The installed PS3 system software's version ('4.93'), or None. RPCS3 writes dev_flash/vsh/etc/version.txt last."""
    path = os.path.join(data_dir(folder), 'dev_flash', 'vsh', 'etc', 'version.txt')
    try:
        with open(path, encoding='ascii', errors='replace') as f:
            first = f.readline()
    except OSError:
        return None
    found = re.match(r'release:(\d+)\.(\d{2})', first.strip())
    return f'{int(found.group(1))}.{found.group(2)}' if found else None


def parse_offer(text):
    """(version, address, md5) of the full system software file in Sony's update list `text`, or None."""
    for line in text.splitlines():
        fields = dict(part.split('=', 1) for part in line.strip().split(';') if '=' in part)
        url = fields.get('CDN', '')
        if url.endswith('/PS3UPDAT.PUP') and fields.get('SystemSoftwareVersion'):
            found = re.search(r'/(?:\d{4}_\d{4}_)?([0-9a-f]{32})/PS3UPDAT\.PUP$', url)
            version = fields['SystemSoftwareVersion']
            version = re.sub(r'^(\d+)\.(\d{2})\d*$', lambda m: f'{int(m.group(1))}.{m.group(2)}', version)
            return version, url, found.group(1) if found else None
    return None


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': FIRMWARE_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def firmware_offer():
    """(version, address, md5) of the system software Sony serves now. Raises EmulatorError when no list can be read."""
    for region in FIRMWARE_REGIONS:
        try:
            offer = parse_offer(_get(FIRMWARE_LIST.format(region)).decode('ascii', 'replace'))
        except OSError:
            continue
        if offer:
            return offer
    raise EmulatorError("Sony's update server did not answer, so the PS3 system software could not be downloaded. Check the "
                        "internet connection and try again, or pick a PS3UPDAT.PUP you have.")


def check_pup(path, md5=None, sha256=None):
    """Is `path` a PS3 system software file (and, when given, the one with that MD5 / SHA-256)? Raises EmulatorError if not."""
    try:
        with open(path, 'rb') as f:
            head = f.read(len(PUP_MAGIC))
    except OSError as err:
        raise EmulatorError(f"The file could not be read: {err}") from err
    if head != PUP_MAGIC:
        raise EmulatorError("That file is not the PS3 system software. Pick the file PS3UPDAT.PUP.")
    if md5 or sha256:
        digest_md5, digest_sha = hashlib.md5(), hashlib.sha256()
        with open(path, 'rb') as f:
            for block in iter(lambda: f.read(1 << 20), b''):
                digest_md5.update(block)
                digest_sha.update(block)
        if (md5 and digest_md5.hexdigest() != md5) or (sha256 and digest_sha.hexdigest() != sha256):
            raise EmulatorError("The downloaded system software is not the file Sony published, so it was not used. Try again.")
    return True


def download_firmware(target, progress=None, cancelled=None, offer=None):
    """Download PS3UPDAT.PUP from Sony's server into `target` (a piece already there in `target`.part is continued) and check
    it. `progress(fraction)`; `cancelled()` True stops it (InterruptedError). Returns (target, version)."""
    version, url, md5 = offer or firmware_offer()
    part = target + '.part'
    have = os.path.getsize(part) if os.path.isfile(part) else 0
    headers = {'User-Agent': FIRMWARE_AGENT}
    if have:
        headers['Range'] = f'bytes={have}-'
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            if have and r.status != 206:            # the server sent the whole file: start again
                have = 0
            length = int(r.headers.get('Content-Length') or 0)
            total = (have + length) or FIRMWARE_SIZE
            with open(part, 'ab' if have else 'wb') as out:
                got = have
                while True:
                    if cancelled and cancelled():
                        raise InterruptedError()
                    block = r.read(1 << 18)
                    if not block:
                        break
                    out.write(block)
                    got += len(block)
                    if progress:
                        progress(min(1.0, got / total))
    except OSError as err:
        if isinstance(err, InterruptedError):
            raise
        raise EmulatorError("The PS3 system software could not be downloaded (the connection dropped). Press Set up again: "
                            "the download goes on where it stopped.") from err
    try:
        check_pup(part, md5=md5, sha256=FIRMWARE_SHA256.get(version))
    except EmulatorError:
        os.remove(part)
        raise
    os.replace(part, target)
    return target, version


FIRMWARE_DONE = 'Successfully installed PS3 firmware'
FIRMWARE_FAILED = ('Error while installing firmware', 'Error while extracting firmware')


def install_firmware(folder, pup, timeout=300, poll=0.5):
    """Install the system software file `pup` with the built-in RPCS3 (`rpcs3 --headless --installfw`): no window, no question,
    a few seconds. Without --headless RPCS3 asks "Install firmware: <file>?" in a window that waits for a click (round
    2026-11-16). Headless, it installs and quits by itself, and on 0.0.43-20607 it crashes while quitting (exit 0xC0000409,
    after the work is done), so the answer is its log line FIRMWARE_DONE and the version file, not its exit code (the files'
    dates come from Sony's file, so they cannot tell). Returns the version."""
    check_pup(pup)
    if firmware_version(folder):
        return firmware_version(folder)
    log = log_file(folder)
    # RPCS3 opens its log before it makes the log folder: on its first start in a new folder it writes no log at all
    os.makedirs(os.path.dirname(log), exist_ok=True)
    started = time.time() - 2

    def done():
        text = ''
        if os.path.isfile(log) and os.path.getmtime(log) >= started:
            text = onlinecfg.read_shared(log)
        if FIRMWARE_DONE in text and firmware_version(folder):
            return True
        return False if any(word in text for word in FIRMWARE_FAILED) else None

    failed = EmulatorError("RPCS3 could not install the PS3 system software. Try Set up again; if it fails again, "
                           "pick the file PS3UPDAT.PUP yourself.")
    proc = savedata.launch([exe_path(folder), '--headless', '--installfw', os.path.abspath(pup)], cwd=folder,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end = time.time() + timeout
    try:
        while time.time() < end:
            answer = done()
            if answer is None and proc.poll() is not None:
                answer = done()                       # it quits right after the line: read the log once more
            if answer:
                return firmware_version(folder)
            if answer is False or proc.poll() is not None:
                raise failed
            time.sleep(poll)
        raise EmulatorError("Installing the PS3 system software took too long. Try Set up again.")
    finally:
        _end(proc)


def _end(proc):
    if proc.poll() is not None:
        return
    if WINDOWS:
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def game_problem(path):
    """None when `path` (an .iso or a game folder) is NHL Legacy (EU or NA) that RPCS3 can run, else what is wrong, in plain words."""
    if not path or not os.path.exists(path):
        return "That file is not there any more. Pick the game again."
    title = savedata.game_title_id(path)
    if title is None:
        return ("That is not a game disc RPCS3 can read. Pick a decrypted .iso of NHL Legacy, or the game's folder (the one "
                "with PS3_GAME in it).")
    if title not in savedata.GAMES:
        return f"That is another game ({title}). Pick NHL Legacy (BLES02153 or BLUS31540)."
    head = _eboot_head(path)
    if head is not None and head[:4] != b'SCE\x00':
        return "That disc image is still encrypted. RPCS3 needs a decrypted .iso of NHL Legacy."
    return None


def _eboot_head(path):
    try:
        if os.path.isfile(path):
            from .art.disc import IsoImage
            iso = IsoImage(path)
            try:
                return iso.read(iso.find('/PS3_GAME/USRDIR/EBOOT.BIN'), size=16)
            finally:
                iso.f.close()
        with open(os.path.join(path, 'PS3_GAME', 'USRDIR', 'EBOOT.BIN'), 'rb') as f:
            return f.read(16)
    except Exception:           # noqa: BLE001 - a file it cannot read: the title check already passed, RPCS3 has the last word
        return None


def set_game(folder, title, path):
    """Name the game in the built-in RPCS3's games list (games.yml in config_dir: `TITLE: path`, as RPCS3 writes it), keeping
    the other lines."""
    cfg = os.path.join(config_dir(folder), 'games.yml')
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    where = os.path.abspath(path).replace('\\', '/')
    if os.path.isdir(path) and not where.endswith('/'):
        where += '/'
    try:
        with open(cfg, encoding='utf-8-sig') as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    lines = [line for line in lines if line.partition(':')[0].strip().strip('"\'') != title]
    lines.append(f'{title}: {where}')
    with open(cfg + '.tmp', 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(cfg + '.tmp', cfg)


def configure(folder):
    """Give the built-in RPCS3's config.yml the settings NHL Legacy wants (rpcs3cfg.BUILTIN_DEFAULTS); every other key stays
    RPCS3's. Run after install_firmware: RPCS3 writes its full config.yml then, so the keys land in a complete file. Returns
    True when the file changed."""
    cfg = os.path.join(config_dir(folder), 'config.yml')
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    try:
        with open(cfg, encoding='utf-8-sig', newline='') as f:
            text = f.read()
    except OSError:
        text = ''
    new = text
    for path, value in rpcs3cfg.BUILTIN_DEFAULTS:
        new = rpcs3cfg.put(new, path, value)
    if new == text:
        return False
    with open(cfg + '.tmp', 'w', encoding='utf-8', newline='') as f:
        f.write(new)
    os.replace(cfg + '.tmp', cfg)
    return True


def host(folder, games=None):
    """The built-in RPCS3 as an savedata.Rpcs3 (its data in portable/). Raises savedata.NoGameError (with the RPCS3) when it has
    neither a roster nor a game yet."""
    if not installed(folder):
        raise savedata.Rpcs3Error("The built-in RPCS3 is not set up yet. Press Set up.")
    return savedata.find_rpcs3(exe_path(folder), games)
