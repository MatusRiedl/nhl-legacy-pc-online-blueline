"""Make the built-in RPCS3's pack (0.99.0, docs/notes/standalone.md, MAINTAINING.md "The built-in RPCS3").

    python tools/rpcs3_pack.py <build> --version 0.0.43-20606 --commit <sha> --source <fork URL> [--license <file>]
                               [--out private/packs/rpcs3-win.zip]

<build> is what the fork's GitHub build gave, unpacked:
  Windows  the folder of the 7z (it holds rpcs3.exe), or the .7z itself when 7-Zip is installed  ->  rpcs3-win.zip
  Linux    the .AppImage file                                                                ->  rpcs3-linux.zip

The pack holds the program files (never a portable/ folder: that is the player's data), index.json (version, source, commit,
built, patches: emulator.install stamps the folder with it), RPCS3's LICENSE and SOURCE.txt (GPL v2: where the source of this
very build is). The zip is the same bytes for the same build (sorted, fixed dates), so publishing it twice changes nothing.
Then `python tools/publish_packs.py <host>:<folder> --only rpcs3-win,rpcs3-linux --dry-run` (the owner's go first).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from legacy_roster import emulator, savedata  # noqa: E402

PATCHES = ["Goal light: the vertex program's RSQ of 0 gives +infinity "
           "(rpcs3/Emu/RSX/Program/VertexProgramDecompiler.cpp), so the goal lamp shows."]
# what a build folder may hold that is not the program: left out of the pack
LEFT_OUT = {savedata.PORTABLE, 'config', 'log', 'cache', 'dev_hdd0', 'dev_hdd1', 'dev_flash', 'dev_flash2', 'dev_flash3',
            'dev_usb000', 'dev_bdvd', 'games', 'shaderlog', 'savestates', 'captures', 'screenshots', 'test',
            savedata.BUILTIN_STAMP, 'index.json', 'SOURCE.txt', 'LICENSE', 'COPYING', 'LICENSE.txt'}   # the last: _licence
FIXED_DATE = (2020, 1, 1, 0, 0, 0)
SEVEN_ZIP = ('7z', '7za', r'C:\Program Files\7-Zip\7z.exe', r'C:\Program Files (x86)\7-Zip\7z.exe')


def source_text(version, source, commit):
    return (f"RPCS3 {version}, built for Blueline (NHL Legacy).\n\n"
            "RPCS3 is free software under the GNU General Public License, version 2 (the file LICENSE).\n"
            f"The source of this build: {source}\nCommit: {commit}\n\n"
            "Changes from RPCS3's own source:\n" + ''.join(f"- {p}\n" for p in PATCHES))


def _unpack_7z(path, into):
    for exe in SEVEN_ZIP:
        found = shutil.which(exe) or (exe if os.path.isfile(exe) else None)
        if found:
            subprocess.run([found, 'x', '-y', f'-o{into}', path], check=True, stdout=subprocess.DEVNULL)
            return into
    raise SystemExit("7-Zip was not found: unpack the .7z yourself and give its folder.")


def _files(build):
    """[(name in the pack, file on disk, executable)] of the build."""
    if os.path.isfile(build) and build.lower().endswith('.appimage'):
        return [('rpcs3.AppImage', build, True)]
    exe = os.path.join(build, 'rpcs3.exe')
    if not os.path.isfile(exe):
        raise SystemExit(f"No rpcs3.exe in {build}: give the unpacked Windows build or the Linux .AppImage.")
    rows = []
    for here, dirs, names in os.walk(build):
        rel = os.path.relpath(here, build)
        if rel == '.':
            dirs[:] = [d for d in dirs if d not in LEFT_OUT]
            names = [n for n in names if n not in LEFT_OUT]
        dirs.sort()
        for name in sorted(names):
            if name.endswith(('.pdb', '.log')):
                continue
            path = os.path.join(here, name)
            arc = name if rel == '.' else f"{rel.replace(os.sep, '/')}/{name}"
            rows.append((arc, path, False))
    return rows


def _licence(build, given):
    for path in ([given] if given else []) + [os.path.join(build, n) for n in ('LICENSE', 'COPYING', 'LICENSE.txt')
                                              if os.path.isdir(build)]:
        if path and os.path.isfile(path):
            with open(path, 'rb') as f:
                return f.read()
    raise SystemExit("RPCS3's LICENSE was not found in the build: give it with --license (the fork's LICENSE file).")


def _entry(name, executable=False):
    info = zipfile.ZipInfo(name, FIXED_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = ((0o755 if executable else 0o644) | 0o100000) << 16
    return info


def make(build, out, version, commit, source, licence=None, built=None):
    """Write the pack `out` from `build`; returns its index."""
    work = None
    if os.path.isfile(build) and build.lower().endswith('.7z'):
        work = tempfile.mkdtemp(prefix='rpcs3-pack-')
        build = _unpack_7z(build, work)
    try:
        rows = _files(build)
        linux = rows[0][0] == 'rpcs3.AppImage'
        index = {'name': 'rpcs3-linux' if linux else 'rpcs3-win', 'version': version, 'commit': commit, 'source': source,
                 'built': built or time.strftime('%Y-%m-%d'), 'patches': PATCHES}
        text = _licence(build if not linux else os.path.dirname(build), licence)
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with zipfile.ZipFile(out + '.part', 'w') as z:
            for arc, path, executable in rows:
                if not emulator._member_ok(arc):         # noqa: SLF001 - the install's own rule
                    raise SystemExit(f"{arc} may not be in the pack.")
                with open(path, 'rb') as f:
                    z.writestr(_entry(arc, executable), f.read())
            z.writestr(_entry('LICENSE'), text)
            z.writestr(_entry('SOURCE.txt'), source_text(version, source, commit))
            z.writestr(_entry(emulator.INDEX), json.dumps(index, indent=1, sort_keys=True) + '\n')
        os.replace(out + '.part', out)
        return index
    finally:
        if work:
            shutil.rmtree(work, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('build', help="the unpacked Windows build (or its .7z), or the Linux .AppImage")
    ap.add_argument('--version', required=True, help="RPCS3's version of the build, e.g. 0.0.43-20606")
    ap.add_argument('--commit', required=True, help="the fork's commit the build was made from")
    ap.add_argument('--source', required=True, help="the fork's address (https://github.com/...): its source, GPL v2")
    ap.add_argument('--license', help="RPCS3's LICENSE file when the build has none")
    ap.add_argument('--built', help="the build's date (default today)")
    ap.add_argument('--out', help="the pack (default private/packs/rpcs3-win.zip or rpcs3-linux.zip)")
    args = ap.parse_args()
    if not args.source.startswith('https://github.com/'):
        raise SystemExit("--source must be the fork's GitHub address (the window opens only those).")
    linux = args.build.lower().endswith('.appimage')
    out = args.out or os.path.join(ROOT, 'private', 'packs', 'rpcs3-linux.zip' if linux else 'rpcs3-win.zip')
    index = make(args.build, out, args.version, args.commit, args.source, args.license, args.built)
    size = os.path.getsize(out)
    print(f"{out}: {index['name']} {index['version']} ({size / 1024 ** 2:.1f} MB), sha256 {emulator._sha256(out)}")  # noqa: SLF001


if __name__ == '__main__':
    main()
