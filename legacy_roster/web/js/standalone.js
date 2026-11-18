// Setup's parts for playing (0.99.0): the choice of where the game runs (Blueline's RPCS3 / my RPCS3 / NHL Legacy Native),
// the built-in RPCS3's three rows and its Set up button (slice `emulator`, app/builtin.py), the Game settings card (slice
// `game`, app/gamesettings.py) and the Controls window (slice `controls`, app/controls.py).
import { html, cls, useEffect, useState } from './lib.js';
import { Button, Toggle, Segmented, Card, PathText, ProgressBar, Modal } from './ui.js';
import { call } from './bridge.js';
import { useSlice } from './store.js';

// --- where the game runs ---------------------------------------------------------------------------------------
export function HostChoice({ e }) {
  if (!e || !e.choices) return null;
  return html`<${Segmented} className="hosts"
    options=${e.choices.map((c) => ({ value: c.kind, label: c.label }))}
    value=${e.shown} disabled=${!e.enabled} onChange=${(kind) => call('builtin_choose', kind)}/>`;
}

function Row({ row, e }) {
  return html`<div class=${cls('bl-row', row.done && 'done', row.tone)}>
    <span class="bl-mark" aria-hidden="true">${row.done ? '✓' : ''}</span>
    <div class="main">
      <div class="title">${row.title}</div>
      <div class="sub">${row.text}</div>
      ${row.key === 'game' && html`<div class="row wrap bl-acts">
        <${Button} small kind=${row.done ? 'ghost' : 'primary'} disabled=${!e.enabled}
          onClick=${() => call('builtin_pick_game', false)}>${row.done ? 'Change...' : 'Pick the game (.iso)...'}</${Button}>
        <${Button} small kind="link" disabled=${!e.enabled} onClick=${() => call('builtin_pick_game', true)}>or its folder...</${Button}>
      </div>`}
      ${row.key === 'firmware' && e.pup && html`<div class="row wrap bl-acts">
        <${Button} small kind="link" disabled=${!e.enabled} onClick=${() => call('builtin_pick_pup')}>Or pick the file PS3UPDAT.PUP yourself...</${Button}>
      </div>`}
    </div>
  </div>`;
}

export function BuiltinBody({ e }) {
  return html`<div class="bl">
    <div class="bl-rows">${e.rows.map((row) => html`<${Row} key=${row.key} row=${row} e=${e}/>`)}</div>
    ${e.busy && html`<div class="bl-step">
      <div class="sub">${e.step}</div>
      <${ProgressBar} value=${e.bar == null ? 0 : e.bar} active indeterminate=${e.bar == null}/>
    </div>`}
    ${e.error && html`<div class="note bad">${e.error}</div>`}
    ${(e.button || e.busy) && html`<div class="row wrap bl-foot">
      ${e.button && html`<${Button} kind="primary" disabled=${!e.button.can} title=${e.button.why || undefined}
        onClick=${() => call('builtin_setup')}>${e.button.text}</${Button}>`}
      ${e.busy && html`<${Button} small onClick=${() => call('builtin_cancel')}>Stop</${Button}>`}
      ${e.button && e.button.why && html`<span class="small-note">${e.button.why}</span>`}
    </div>`}
    <div class="row bl-folder">
      <span class="small-note">Folder</span><${PathText} path=${e.folder}/>
      ${e.can_move && html`<${Button} small kind="link" disabled=${!e.enabled} onClick=${() => call('builtin_pick_folder')}>Change</${Button}>`}
    </div>
    ${e.source && html`<div class="small-note bl-source">RPCS3 is free software (GPL v2).
      <${Button} small kind="link" onClick=${() => call('builtin_source')}>Its source</${Button}></div>`}
  </div>`;
}

// --- Game settings -----------------------------------------------------------------------------------------------
function Field({ f, enabled }) {
  const on = f.options.find((o) => o.on);
  return html`<div class="gs-row">
    <span class="gs-label">${f.label}</span>
    <${Segmented} className="tiny" options=${f.options.map((o) => ({ value: String(o.value), label: o.label }))}
      value=${on ? String(on.value) : null} disabled=${!enabled}
      onChange=${(v) => { const o = f.options.find((x) => String(x.value) === v); call('game_set', f.key, o ? o.value : null); }}/>
    ${f.now && html`<span class="small-note">now ${f.now}</span>`}
  </div>`;
}

export function GameCard({ busy }) {
  const g = useSlice('game');
  const c = useSlice('controls');
  const [open, setOpen] = useState(false);
  if (!g || !g.shown) return null;
  const pads = c && c.shown && !c.own;
  return html`<${Card} title="Game settings" aside=${g.native ? '' : 'used by Play'} style=${{ '--i': 1 }}>
    <div class="card-body gs">
      ${g.native ? html`<div class="note info" style=${{ marginTop: 0 }}>${g.note}</div>` : html`
        ${g.fields.map((f) => html`<${Field} key=${f.key} f=${f} enabled=${g.enabled && !busy}/>`)}
        ${g.locked.map((l) => html`<div key=${l.label} class="gs-lock"><span class="lock">${l.label}</span>${l.text}</div>`)}
        ${g.note && html`<div class="note amber">${g.note}</div>`}`}
      <div class="row wrap gs-foot">
        ${pads && html`<${Button} small onClick=${() => setOpen(true)}>Controls...</${Button}>`}
        ${c && c.shown && c.own && html`<span class="small-note">${c.note}</span>`}
        ${g.can_reset && html`<${Button} small kind="link" disabled=${busy} onClick=${() => call('game_reset')}>Use RPCS3's own settings</${Button}>`}
      </div>
    </div>
    ${open && pads && html`<${ControlsWindow} c=${c} onClose=${() => setOpen(false)}/>`}
  </${Card}>`;
}

// --- Controls ------------------------------------------------------------------------------------------------------
// A key press as RPCS3 names it (Qt's key names: letters and marks as the keyboard types them, "Left", "Return", "PgDown"...).
const NAMED = {
  ArrowLeft: 'Left', ArrowRight: 'Right', ArrowUp: 'Up', ArrowDown: 'Down', Enter: 'Return', NumpadEnter: 'Enter',
  Space: 'Space', Backspace: 'Backspace', Tab: 'Tab', Delete: 'Del', Insert: 'Ins', Home: 'Home', End: 'End',
  PageUp: 'PgUp', PageDown: 'PgDown', CapsLock: 'CapsLock', ShiftLeft: 'Shift Left', ShiftRight: 'Shift Right',
  ControlLeft: 'Ctrl', ControlRight: 'Ctrl', AltLeft: 'Alt', AltRight: 'AltGr', Escape: 'Esc',
};
export function rpcsKey(e) {
  if (NAMED[e.code]) return NAMED[e.code];
  if (/^F([1-9]|1[0-2])$/.test(e.key)) return e.key;
  if (/^Numpad[0-9]$/.test(e.code)) return e.code.slice(6);
  if (e.key && e.key.length === 1 && e.key !== ' ') return e.key.toUpperCase();
  return null;
}
const MOUSE = ['Mouse Left', 'Mouse Middle', 'Mouse Right', 'Mouse Back', 'Mouse Fwd'];

function ControlsWindow({ c, onClose }) {
  const [wait, setWait] = useState(null);          // the button waiting for a key
  useEffect(() => {
    if (!wait) return undefined;
    const done = (name) => { setWait(null); if (name) call('controls_bind', wait, name); };
    const key = (ev) => {
      ev.preventDefault(); ev.stopPropagation();
      if (ev.key === 'Escape') { setWait(null); return; }
      done(rpcsKey(ev));
    };
    const mouse = (ev) => {
      if (ev.target.closest && ev.target.closest('.ck-key.wait')) return;     // the click that started the wait
      ev.preventDefault(); ev.stopPropagation();
      done(MOUSE[ev.button] || null);
    };
    const wheel = (ev) => { ev.preventDefault(); done(ev.deltaY < 0 ? 'Wheel Up' : 'Wheel Down'); };
    const menu = (ev) => ev.preventDefault();
    window.addEventListener('keydown', key, true);
    window.addEventListener('mousedown', mouse, true);
    window.addEventListener('wheel', wheel, { capture: true, passive: false });
    window.addEventListener('contextmenu', menu, true);
    return () => {
      window.removeEventListener('keydown', key, true);
      window.removeEventListener('mousedown', mouse, true);
      window.removeEventListener('wheel', wheel, true);
      window.removeEventListener('contextmenu', menu, true);
    };
  }, [wait]);
  const close = () => { if (wait) setWait(null); else onClose(); };
  const keyboard = c.mode === 'keyboard';
  // straight into <body>, as the big windows: the card it opens from slides in, which would hold the window inside the card
  const page = html`<${Modal} title="Controls" wide onClose=${close} buttons=${html`
      ${keyboard && html`<${Button} kind="link" disabled=${!c.can_reset} onClick=${() => call('controls_reset')}>Reset the keys</${Button}>`}
      <${Button} kind="primary" onClick=${onClose}>Done</${Button}>`}>
    <div class="ck">
      <${Segmented} options=${c.modes.map((m) => ({ value: m.key, label: m.label }))} value=${c.mode}
        disabled=${!c.enabled} onChange=${(m) => call('controls_mode', m)}/>
      ${!keyboard ? html`<div class="ck-pads">
          <${Segmented} options=${c.pads.map((p) => ({ value: p.key, label: p.label }))} value=${c.pad}
            disabled=${!c.enabled} onChange=${(p) => call('controls_pad', p)}/>
          <div class="small-note">Plug the controller in before you press Play. It works with the game's usual buttons.</div>
        </div>` : html`
        <div class="row ck-mouse">
          <${Toggle} on=${c.mouse_stick} disabled=${!c.enabled} label="Mouse moves the right stick"
            onChange=${(v) => call('controls_mouse', v)}/>
          <span>Mouse moves the right stick (shooting and dekes)</span>
        </div>
        <div class="small-note">Click a button, then press the key or mouse button for it. Escape stops waiting.</div>
        <div class="ck-grid">${c.buttons.map((b) => html`<div key=${b.key} class="ck-row">
          <span class="ck-label">${b.label}</span>
          <button type="button" class=${cls('ck-key', wait === b.key && 'wait', b.changed && 'changed', b.mouse && 'mouse')}
            disabled=${!c.enabled} onClick=${() => setWait(wait === b.key ? null : b.key)}>
            ${wait === b.key ? 'Press a key...' : b.mouse ? 'Mouse' : b.value}</button>
        </div>`)}</div>`}
      ${c.error && html`<div class="note bad">${c.error}</div>`}
    </div>
  </${Modal}>`;
  return window.ReactDOM ? window.ReactDOM.createPortal(page, document.body) : page;
}
