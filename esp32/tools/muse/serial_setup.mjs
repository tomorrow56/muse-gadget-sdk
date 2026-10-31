// Copyright (c) Meta Platforms, Inc. and affiliates. Apache-2.0.
import { MuseSerial, SETTINGS } from './serial_settings.mjs';
const $ = id => document.getElementById(id);
let session = null, confirmed = null, busy = false;
const keys = Object.keys(SETTINGS);
const labels = { sleep: '消灯時間', brightness: '明るさ', volume: '音量', mic_gain: 'マイクゲイン', speaker: 'スピーカー' };
const values = () => Object.fromEntries(keys.map(key => [key, key === 'speaker' ? $(key).checked : $(key).value === '' ? NaN : Number($(key).value)]));
function message(text, kind = '') { $('message').textContent = text; $('message').className = kind; }
function event(text) {
  const row = document.createElement('li'); row.textContent = `${new Date().toLocaleTimeString()} ${text}`;
  $('events').prepend(row); while ($('events').children.length > 40) $('events').lastElementChild.remove();
}
function changed() {
  if (!confirmed) return [];
  const draft = values(); return keys.filter(key => draft[key] !== confirmed.device[key]);
}
function update() {
  const online = Boolean(session?.online), edits = changed();
  $('connect').disabled = busy;
  $('connect').textContent = online ? '切断する' : 'USBで接続';
  $('connection').textContent = busy ? '通信中' : online ? 'USB接続中' : '未接続';
  $('connection').classList.toggle('online', online);
  $('fields').disabled = busy || !online || !confirmed;
  $('refresh').disabled = $('wake').disabled = busy || !online;
  $('save').disabled = busy || !online || !confirmed || !edits.length || !$('settings').checkValidity();
  $('change-count').textContent = !confirmed ? '設定を読み込み待ち' : edits.length ? `${edits.length}項目の変更が未保存です` : '実機の設定と一致しています';
  for (const key of ['brightness', 'volume', 'mic_gain']) {
    $(`${key}-value`).textContent = confirmed ? `${$(key).value}${key === 'mic_gain' ? ' dB' : '%'}` : '—';
  }
}
function show(status) {
  confirmed = status;
  for (const key of keys) { if (key === 'speaker') $(key).checked = status.device[key]; else $(key).value = status.device[key]; }
  $('board').textContent = status.board;
  const dev = status.device;
  $('device-info').textContent = `${dev.name || 'Muse Gadget'} · FW ${dev.fw || '—'} · Wi-Fi ${dev.wifi?.state || '—'}`;
  $('saved').textContent = `実機から確認：${new Date().toLocaleTimeString()}`;
  update();
}
function clear() {
  confirmed = null; $('settings').reset(); $('board').textContent = 'Museを接続してください';
  $('device-info').textContent = 'Chromeで開き、USBデータケーブルを接続してください。';
  $('saved').textContent = '再接続時にも実機から現在値を読み込みます。'; update();
}
async function operation(action) {
  busy = true; update();
  try { await action(); }
  catch (error) { message(error.message, 'error'); event('操作を完了できませんでした。'); }
  finally { busy = false; update(); }
}
$('connect').onclick = () => operation(async () => {
  if (session) { const old = session; session = null; await old.close(); clear(); message('USB接続を終了しました。'); return; }
  if (!window.isSecureContext || !navigator.serial) throw new Error('Chromeで localhost または HTTPS から開いてください。');
  // requestPort is directly inside the click operation, before any awaited work.
  let port;
  try { port = await navigator.serial.requestPort(); }
  catch (error) { if (error.name === 'NotFoundError') { message('デバイス選択をキャンセルしました。'); return; } throw error; }
  const current = new MuseSerial(port, { onDisconnect: error => {
    if (session !== current) return;
    session = null; clear(); message(error.message, 'error'); event('USB接続が切れました。');
    void current.close();
  } });
  session = current;
  message('接続しています。実機の起動と設定の応答を待っています…');
  try {
    const status = await current.connect();
    show(status); message('現在の設定を読み込みました。', 'success'); event('USB接続・設定の読み込み完了。');
  } catch (error) {
    if (session === current) session = null;
    clear(); throw error;
  }
});
$('refresh').onclick = () => operation(async () => {
  if (changed().length && !window.confirm('未保存の変更を取り消して、実機の設定を読み直しますか？')) return;
  show(await session.query()); message('現在の設定を読み込みました。', 'success'); event('設定を再読み込みしました。');
});
$('wake').onclick = () => operation(async () => {
  await session.wake(); message('画面の復帰コマンドを送信しました。', 'success'); event('画面の復帰を実行しました。');
});
$('settings').onsubmit = e => {
  e.preventDefault(); if (busy || !confirmed || !$('settings').reportValidity()) return;
  void operation(async () => {
    const requested = values(), edits = changed();
    if (!edits.length) return;
    let saving = '';
    try {
      for (const key of edits) { saving = key; show(await session.set(key, requested[key])); event(`${labels[key]}を保存し、読み戻しを確認しました。`); }
      message('変更を実機に保存しました。', 'success');
    } catch (error) {
      // ACK without readback is not reported as success. Reload actual values.
      confirmed = null;
      try { if (session?.online) show(await session.query()); } catch {}
      throw new Error(`${labels[saving]}の保存確認に失敗しました。${error.message}`);
    }
  });
};
for (const key of keys) $(key).addEventListener('input', update);
for (const button of document.querySelectorAll('[data-sleep]')) button.onclick = () => { $('sleep').value = button.dataset.sleep; update(); };
window.addEventListener('pagehide', () => { void session?.close(); });
clear();
if (!window.isSecureContext || !navigator.serial) {
  $('connect').disabled = true;
  message('このブラウザではUSB接続を利用できません。ChromeでlocalhostまたはHTTPSから開いてください。', 'error');
}
