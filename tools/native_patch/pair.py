"""Finds where a new build of NHL Legacy Native keeps what the patch needs, from a build `build.BUILDS` already knows
(README.md "A new build of the port"). Reads both exes, writes nothing; needs capstone (`pip install capstone`).

    py -3.13 -B tools/native_patch/pair.py <known NHLLegacy.exe> <new NHLLegacy.exe> [--swap <work>/swap.json] [--every 40]

It works only while the port translated the game the same way (the same function table, the same instructions in every
lifted function); then only addresses moved. 1.0.1 and 1.0.2 were such builds. It checks:
- the new table holds the same guest addresses in the same order;
- every `--every`-th lifted function and every function in `--swap` (the ones the patch replaces) has the same instructions,
  calls and memory references taken out;
- each helper and data address of the known build pairs with one new address every time it is used;
- the helpers' own bodies are the same, and their thread-block offsets say `tramp_off`;
- the console clock constant is in `.text` 5 times (`build.console_clock`, online).
Anything else stops it: the port was translated again, and the patch needs a new lift ("From nothing" in README.md).
At the end it prints the `BUILDS` row and the `savedata.NATIVE_PATCHED` entry."""
import collections
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build                                    # noqa: E402  (BUILDS, Exe)
import capstone                                 # noqa: E402

BASE = build.BASE
CLOCK = 79800000
RIP = re.compile(r'\[rip ([+-]) (0x[0-9a-f]+)\]')
DISP = re.compile(r'(\[[a-z0-9]+ \+ )(0x[0-9a-f]+)\]')


class Exe(build.Exe):
    def __init__(self, path):
        super().__init__(path)
        self.pdata = {}
        for name, size, va, raw, at in self.sections:
            if name.rstrip(b'\0') == b'.pdata':
                for o in range(at, at + size, 12):
                    begin, end, _ = struct.unpack_from('<III', self.bytes, o)
                    if begin:
                        self.pdata.setdefault(begin, end)

    def section(self, name):
        return next(s for s in self.sections if s[0].rstrip(b'\0') == name)

    def table(self, rva):
        """The function table as a list of (guest, host), in its order."""
        at, rows = self.file_at(rva), []
        while True:
            guest, host, name = struct.unpack_from('<QQQ', self.bytes, at)
            if not host and not name:
                return rows
            rows.append((guest, host))
            at += 24

    def code(self, va):
        """A host function's bytes, from .pdata; None when it has no entry of its own."""
        end = self.pdata.get(va - BASE)
        return self.read(va - BASE, end - (va - BASE)) if end else None


def find_table(exe, guests):
    """Where the new exe's table starts: the first three guest addresses, 24 bytes apart, in .rdata."""
    _, size, va, raw, at = exe.section(b'.rdata')
    blob = exe.bytes[at:at + raw]
    hits = []
    for m in re.finditer(re.escape(struct.pack('<Q', guests[0])), blob):
        o = m.start()
        if all(struct.unpack_from('<Q', blob, o + 24 * k)[0] == guests[k] for k in (1, 2)):
            hits.append(va + o)
    return hits


MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
MD.detail = True


def norm(ins):
    """The instruction's text with its call / jump target and rip-relative address taken out, and those addresses."""
    text, targets = ins.op_str, []
    if (ins.group(capstone.CS_GRP_CALL) or ins.group(capstone.CS_GRP_JUMP)) and re.fullmatch(r'0x[0-9a-f]+', text):
        targets.append(int(text, 16))
        text = 'T'
    m = RIP.search(text)
    if m:
        targets.append(ins.address + ins.size + int(m[2], 16) * (1 if m[1] == '+' else -1))
        text = RIP.sub('[rip+T]', text)
    return ins.mnemonic + ' ' + text, targets


def disp_shift(x, y, tx, ty):
    """The shift of a [reg + offset] displacement when that is all two instructions differ in (the thread block's
    offsets move between builds: 1.0.0 -> 1.0.1 +0x340), else None."""
    mx, my = DISP.search(tx), DISP.search(ty)
    if x.mnemonic == y.mnemonic and mx and my and DISP.sub(r'\1D]', tx) == DISP.sub(r'\1D]', ty):
        return int(my[2], 16) - int(mx[2], 16)
    return None


def same(old, new, fo, fn, shifts):
    """None when a function differs, else the (old, new) addresses it refers to outside itself; displacement shifts it
    has go into `shifts`."""
    co, cn = old.code(fo), new.code(fn)
    if co is None or cn is None:
        return 'no pdata'
    io, inn = list(MD.disasm(co, fo)), list(MD.disasm(cn, fn))
    if len(io) != len(inn):
        return None
    pairs, mine = [], collections.Counter()
    for x, y in zip(io, inn):
        (tx, gx), (ty, gy) = norm(x), norm(y)
        if len(gx) != len(gy):
            return None
        if tx != ty:
            s = disp_shift(x, y, tx, ty)
            if s is None:
                return None
            mine[s] += 1
        pairs += [(p, q) for p, q in zip(gx, gy) if not fo <= p < fo + len(co)]
    shifts.update(mine)
    return pairs


def body_shift(old, new, a, b):
    """Two helpers' bodies: (instructions, other differences, Counter of displacement shifts)."""
    io, inn = list(MD.disasm(old.code(a), a)), list(MD.disasm(new.code(b), b))
    shifts, other = collections.Counter(), abs(len(io) - len(inn))
    for x, y in zip(io, inn):
        tx = re.sub(r'0x[0-9a-f]{6,}', 'A', x.mnemonic + x.op_str)
        ty = re.sub(r'0x[0-9a-f]{6,}', 'A', y.mnemonic + y.op_str)
        if tx == ty:
            continue
        s = disp_shift(x, y, x.op_str, y.op_str)
        if s is None:
            other += 1
        else:
            shifts[s] += 1
    return len(io), other, shifts


def main():
    args = sys.argv[1:]
    every = int(args[args.index('--every') + 1]) if '--every' in args else 40
    swap = json.load(open(args[args.index('--swap') + 1])) if '--swap' in args else {'changed': [], 'new': []}
    old, new = Exe(args[0]), Exe(args[1])
    known = build.BUILDS.get(old.id)
    if known is None:
        raise SystemExit(f'{args[0]} is not a build build.py knows (stamp {old.id[0]:08x}, image {old.id[1]:08x}).')
    if new.id in build.BUILDS:
        print(f'note: build.py already has a row for stamp {new.id[0]:08x}, image {new.id[1]:08x}')
    orows = old.table(known['table'])
    hits = find_table(new, [g for g, _ in orows[:3]])
    if len(hits) != 1:
        raise SystemExit(f'Table: {len(hits)} places hold its first guest addresses. Translated again? (README "From nothing")')
    nrows = new.table(hits[0])
    if [g for g, _ in orows] != [g for g, _ in nrows]:
        raise SystemExit(f'Table at {hits[0]:#x}: other guest addresses ({len(orows)} rows, now {len(nrows)}). Translated again.')
    print(f'table {hits[0]:#x}: {len(nrows)} rows, the same guest addresses')

    wanted = {int(n[5:], 16) for n in swap['changed'] + swap['new']}
    look = sorted(set(range(0, len(orows), every)) | {i for i, (g, _) in enumerate(orows) if g in wanted})
    votes, seen, counts, bad = collections.defaultdict(collections.Counter), set(), collections.Counter(), []
    lifted_shifts = collections.Counter()
    for i in look:
        fo, fn = orows[i][1], nrows[i][1]
        if fo in seen:
            continue
        seen.add(fo)
        pairs = same(old, new, fo, fn, lifted_shifts)
        swapped = orows[i][0] in wanted
        if pairs is None:
            counts['different'] += 1
            bad.append(orows[i][0])
        elif pairs == 'no pdata':
            counts['no pdata (swapped)' if swapped else 'no pdata'] += 1
        else:
            counts['same (swapped)' if swapped else 'same'] += 1
            for p, q in pairs:
                votes[p][q] += 1
    print('functions', dict(counts))
    if bad:
        raise SystemExit('Different functions (guest): ' + ' '.join(hex(g) for g in bad[:20]) + ' ... Translated again.')

    row, unsure = {'table': hits[0], 'code_end': known['code_end'], 'helpers': {}, 'data': {}}, []
    _, tsize, tva, traw, tat = new.section(b'.text')
    for kind in ('helpers', 'data'):
        for name, va in known[kind].items():
            got = votes.get(va)
            if got:
                (q, n), *rest = got.most_common()
                if rest:
                    unsure.append(f'{name}: {got.most_common(3)}')
                print(f'  {name:18} {va:#x} -> {q:#x}  ({n} uses{", not unanimous" if rest else ""})')
            else:                               # never called by a sampled function: its first 32 bytes, once in .text
                sig = old.read(va - BASE, 32)
                found = [BASE + tva + m.start() for m in re.finditer(re.escape(sig), new.bytes[tat:tat + traw])]
                if len(found) != 1:
                    raise SystemExit(f'{name}: not used by the sampled functions, and its first bytes are in .text {len(found)} times')
                q = found[0]
                print(f'  {name:18} {va:#x} -> {q:#x}  (by its first 32 bytes)')
            row[kind][name] = q
    if unsure:
        raise SystemExit('Not unanimous: ' + '; '.join(unsure))

    shifts = collections.Counter()
    for name, va in known['helpers'].items():
        n, other, s = body_shift(old, new, va, row['helpers'][name])
        if other:
            raise SystemExit(f'{name}: its body differs in {other} instructions')
        shifts.update(s)
    if len(shifts) > 1:
        raise SystemExit(f'Thread block: more than one shift {dict(shifts)}')
    shift = next(iter(shifts), 0)
    if set(lifted_shifts) - {shift}:              # the lifted functions may differ only in the helpers' one shift
        raise SystemExit(f'Lifted functions: offsets shifted {dict(lifted_shifts)}, the helpers {shift:+#x}')
    if lifted_shifts:
        print(f'lifted functions: {sum(lifted_shifts.values())} thread-block offsets shifted {shift:+#x}, as the helpers')
    row['tramp_off'] = known['tramp_off'] + shift
    print(f'helpers: the same bodies; thread block shift {shift:+#x}, tramp_off {row["tramp_off"]:#x}')
    clock = new.bytes[tat:tat + traw].count(struct.pack('<I', CLOCK))
    if clock != 5:
        raise SystemExit(f'The console clock {CLOCK} is in .text {clock} times, not 5: build.console_clock needs a look')
    print('console clock: 5 times in .text')

    h = ', '.join(f'{k}={v:#x}' for k, v in row['helpers'].items())
    d = ', '.join(f'{k}={v:#x}' for k, v in row['data'].items())
    print(f'\n    ({new.id[0]:#x}, {new.id[1]:#x}): dict(\n        table={row["table"]:#x}, code_end={row["code_end"]:#x}, '
          f'tramp_off={row["tramp_off"]:#x},\n        helpers=dict({h}),\n        data=dict({d})),')
    print(f'\nsavedata.NATIVE_PATCHED: ({new.id[0]:#x}, {new.id[1]:#x})')


if __name__ == '__main__':
    main()
