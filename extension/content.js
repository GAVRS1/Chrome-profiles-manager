const now = ()=> Date.now();
function postToBg(obj){ try{ chrome.runtime.sendMessage(obj); }catch{} }

const isWeb = /^https?:|^file:/i.test(location.protocol);

// ======== УТИЛИТЫ СЕЛЕКТОРОВ И ТАРГЕТОВ ========
function getIndexInParent(el){
  if (!el || !el.parentNode) return 0;
  let i = 0, n = el;
  while (n = n.previousElementSibling) i++;
  return i;
}

// строим достаточно стабильный CSS-селектор
function getSelector(el){
  if (!el || el.nodeType !== 1) return null;
  if (el.id) return `#${CSS.escape(el.id)}`;
  let parts = [];
  while (el && el.nodeType === 1 && parts.length < 5) {
    let part = el.localName.toLowerCase();
    if (!part) break;
    // особые атрибуты
    if (el.getAttribute) {
      const name = el.getAttribute("name");
      if (name) { part += `[name="${CSS.escape(name)}"]`; }
      const role = el.getAttribute("role");
      if (role) { part += `[role="${CSS.escape(role)}"]`; }
      const type = el.getAttribute("type");
      if (type && (el.localName.toLowerCase()==="input" || el.localName.toLowerCase()==="button")) {
        part += `[type="${CSS.escape(type)}"]`;
      }
      const dataKey = el.getAttribute("data-key") || el.getAttribute("data-testid") || el.getAttribute("data-test") || el.getAttribute("data-id");
      if (dataKey) { part += `[data-key="${CSS.escape(dataKey)}"]`; }
    }
    // классы (первые 2, чтобы не раздувать)
    if (el.classList && el.classList.length) {
      const cls = Array.from(el.classList).slice(0,2).map(c=>`.`+CSS.escape(c)).join("");
      if (cls) part += cls;
    }
    // позиция
    const idx = getIndexInParent(el);
    part += `:nth-child(${idx+1})`;
    parts.unshift(part);
    // стоп-условие: если у родителя есть id — добавляем и выходим
    if (el.parentElement && el.parentElement.id) {
      parts.unshift(`#${CSS.escape(el.parentElement.id)}`);
      break;
    }
    el = el.parentElement;
  }
  return parts.join(" > ");
}

function qsSelector(sel){
  if (!sel) return null;
  try { return document.querySelector(sel); } catch { return null; }
}

function isEditable(el){
  if (!el) return false;
  const tn = el.tagName?.toLowerCase();
  if (tn === "input" || tn === "textarea") return true;
  if (el.isContentEditable) return true;
  return false;
}

function setValueAndCaret(el, value, selStart, selEnd){
  if (!el) return;
  if (el.tagName?.toLowerCase() === "input" || el.tagName?.toLowerCase()==="textarea") {
    const prev = el.value;
    if (prev !== value) {
      el.value = value;
      el.dispatchEvent(new Event("input", {bubbles:true}));
      el.dispatchEvent(new Event("change", {bubbles:true}));
    }
    if (typeof selStart === "number" && typeof selEnd === "number") {
      try { el.selectionStart = selStart; el.selectionEnd = selEnd; } catch {}
    }
  } else if (el.isContentEditable) {
    if (el.innerText !== value) {
      el.innerText = value;
      el.dispatchEvent(new Event("input", {bubbles:true}));
    }
    // курсор в конец (упрощённо)
    const range = document.createRange();
    range.selectNodeContents(el);
    range.collapse(false);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }
}

function getScrollableAncestor(start){
  let el = start;
  while (el && el !== document.body && el !== document.documentElement) {
    const s = getComputedStyle(el);
    const oy = s.overflowY, ox = s.overflowX;
    const canY = (oy === "auto" || oy === "scroll");
    const canX = (ox === "auto" || ox === "scroll");
    if (canY || canX) return el;
    el = el.parentElement;
  }
  return null;
}

// защита от петель: когда сами применяем действие, не отправляем его обратно
let REPLAYING = false;
function withReplayGuard(fn){ REPLAYING = true; try{ fn(); } finally { REPLAYING = false; } }

// ======== УЛАВЛИВАНИЕ СОБЫТИЙ МАСТЕРА ========
if (isWeb) {
  // ---------- INPUT (любые изменения в полях ввода) ----------
  let lastInputTs = 0;
  document.addEventListener("input", (e)=>{
    if (REPLAYING) return;
    const t = e.target;
    if (!isEditable(t)) return;
    const sel = getSelector(t);
    const payload = {
      selector: sel,
      value: t.value ?? t.innerText ?? "",
      selStart: t.selectionStart ?? null,
      selEnd: t.selectionEnd ?? null,
    };
    const nowTs = now();
    // простая «анти-спам» защита: не чаще, чем раз в 40мс
    if (nowTs - lastInputTs < 40) return;
    lastInputTs = nowTs;
    postToBg({type:"input", ts: nowTs, payload});
  }, true);

  // ---------- KEYBOARD (оставляем для Enter/Tab/стрелок и т.п.) ----------
  document.addEventListener("keydown", (e)=>{
    if (REPLAYING) return;
    const payload = {
      key: e.key, code: e.code,
      ctrl: e.ctrlKey, alt: e.altKey, shift: e.shiftKey, meta: e.metaKey,
      repeat: e.repeat, type: "down"
    };
    postToBg({type:"key", ts:now(), payload});
  }, true);

  document.addEventListener("keyup", (e)=>{
    if (REPLAYING) return;
    const payload = { key:e.key, code:e.code, type:"up" };
    postToBg({type:"key", ts:now(), payload});
  }, true);

  // ---------- CLICK (кнопки, дивы и т.д.) ----------
  document.addEventListener("click", (e)=>{
    if (REPLAYING) return;
    const a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    // ссылку по-прежнему отправляем как NAV (чтобы корректно обрабатывать newTab)
    if (a) {
      const href = new URL(a.href, location.href).toString();
      const newTab = e.ctrlKey || e.metaKey || e.button===1 || a.target==="_blank";
      postToBg({type:"nav", ts:now(), payload:{action:"link", href, newTab}});
      return;
    }
    // для любых других элементов шлём CLICK по селектору
    const el = e.target.closest?.("*");
    if (!el) return;
    const sel = getSelector(el);
    postToBg({type:"click", ts:now(), payload:{selector: sel, button: e.button||0}});
  }, true);

  // ---------- NAV (SPA изменения) ----------
  const _ps = history.pushState.bind(history);
  const _rs = history.replaceState.bind(history);
  history.pushState = function(state, title, url){
    if (!REPLAYING) try{ postToBg({type:"nav", ts:now(), payload:{action:"pushState", url:String(url||"")}});}catch{}
    return _ps(state, title, url);
  };
  history.replaceState = function(state, title, url){
    if (!REPLAYING) try{ postToBg({type:"nav", ts:now(), payload:{action:"replaceState", url:String(url||"")}});}catch{}
    return _rs(state, title, url);
  };
  window.addEventListener("popstate", ()=> !REPLAYING && postToBg({type:"nav", ts:now(), payload:{action:"popstate"}}), true);
  window.addEventListener("hashchange", ()=> !REPLAYING && postToBg({type:"nav", ts:now(), payload:{action:"hash", url:location.href}}), true);

  // ---------- SCROLL (по месту: ближайший скролл-контейнер) ----------
  let lastWheelTs = 0;
  window.addEventListener("wheel", (e)=>{
    if (REPLAYING) return;
    const target = e.target?.closest?.("*");
    const scrollEl = getScrollableAncestor(target) || null;
    const selector = scrollEl ? getSelector(scrollEl) : null;
    const payload = {
      selector,
      dx: e.deltaX || 0,
      dy: e.deltaY || 0,
      mode: e.deltaMode || 0
    };
    const ts = now();
    if (ts - lastWheelTs < 20) return; // чуть-чуть притормозим поток
    lastWheelTs = ts;
    postToBg({type:"scroll", ts, payload});
  }, { capture: true, passive: true });

  // ---------- ETH RPC DUP ----------
  (function patchEthereum(){
    const g = window;
    const tryHook = ()=>{
      if (!g.ethereum || typeof g.ethereum.request!=="function") return false;
      const orig = g.ethereum.request.bind(g.ethereum);
      g.ethereum.request = async function(args){
        if (!REPLAYING) try{ postToBg({type:"rpc", ts:now(), payload:{method: args?.method, params: args?.params ?? []}}); }catch{}
        return orig(args);
      };
      return true;
    };
    if (!tryHook()){
      const t = setInterval(()=>{ if(tryHook()) clearInterval(t); }, 1000);
    }
  })();
}

// ======== ПРИМЕНЕНИЕ СОБЫТИЙ НА ВЕДОМЫХ ========
chrome.runtime.onMessage.addListener(async (data)=>{
  if(!data || typeof data!=="object" || !isWeb) return;
  if(data.type==="input"){ await applyInput(data.payload); }
  else if(data.type==="click"){ await applyClick(data.payload); }
  else if(data.type==="scroll"){ await applyScroll(data.payload); }
  else if(data.type==="key"){ applyKey(data.payload); }
  else if(data.type==="nav"){ await applyNav(data.payload); }
  else if(data.type==="rpc"){ await applyRPC(data.payload); }
});

// ---------- INPUT: точечная синхронизация содержимого поля ----------
async function applyInput(p){
  const el = qsSelector(p.selector);
  if (!el || !isEditable(el)) return;
  withReplayGuard(()=> setValueAndCaret(el, p.value ?? "", p.selStart ?? null, p.selEnd ?? null));
}

// ---------- CLICK: симуляция клика по конкретному селектору ----------
async function applyClick(p){
  const el = qsSelector(p.selector);
  if (!el) return;
  // если это <a href>, то клик вёл бы к навигации — у нас это делает applyNav(), поэтому пропустим
  if (el.tagName && el.tagName.toLowerCase()==="a" && el.getAttribute("href")) return;

  withReplayGuard(()=>{
    const btn = Number(p.button)||0;
    const mk = (type)=> new MouseEvent(type, {bubbles:true, cancelable:true, button:btn});
    el.dispatchEvent(mk("mousedown"));
    el.dispatchEvent(mk("mouseup"));
    el.dispatchEvent(mk("click"));
  });
}

// ---------- SCROLL: скроллим именно найденный контейнер, иначе окно ----------
async function applyScroll(p){
  const el = qsSelector(p.selector);
  const dx = Number(p.dx)||0, dy = Number(p.dy)||0;
  withReplayGuard(()=>{
    if (el && (el.scrollHeight > el.clientHeight || el.scrollWidth > el.clientWidth)) {
      el.scrollBy({left: dx, top: dy, behavior: "auto"});
    } else {
      window.scrollBy({left: dx, top: dy, behavior: "auto"});
    }
  });
}

// ---------- KEYBOARD: спец-клавиши, которые не покрылись input-событиями ----------
function applyKey(p){
  const el = document.activeElement || document.body;

  // печатаемые символы синхронизируются через applyInput -> не дублируем
  if (p.key && p.key.length === 1) return;

  const fire = (type, key) => el.dispatchEvent(new KeyboardEvent(type, {key, bubbles:true}));

  switch (p.key) {
    case "Enter":
      if (p.type === "down") {
        fire("keydown","Enter"); fire("keyup","Enter");
        const form = el.closest?.("form");
        if (form) form.requestSubmit?.();
      }
      return;
    case "Backspace":
      if (p.type === "down") {
        // если это инпут — уже синхронизировано через input; иначе — простой keydown/keyup
        if (!(el.tagName && (el.tagName.toLowerCase()==="input" || el.tagName.toLowerCase()==="textarea"))) {
          fire("keydown","Backspace"); fire("keyup","Backspace");
        }
      }
      return;
    case "Tab":
    case "ArrowLeft":
    case "ArrowRight":
    case "ArrowUp":
    case "ArrowDown":
      fire("keydown", p.key); fire("keyup", p.key);
      return;
    default:
      return;
  }
}

// ---------- NAV ----------
async function applyNav(p){
  try{
    if(p.action==="link"){
      if (!p.newTab) location.assign(p.href);
    }
    else if(p.action==="pushState"){ history.pushState({}, "", p.url); }
    else if(p.action==="replaceState"){ history.replaceState({}, "", p.url); }
    else if(p.action==="popstate"){ history.back(); }
    else if(p.action==="hash"){ location.assign(p.url); }
  }catch{}
}

// ---------- RPC ----------
async function applyRPC(p){
  const g = window;
  if(g.ethereum && typeof g.ethereum.request==="function"){
    try{ await g.ethereum.request({method: p.method, params: p.params}); }catch{}
  }
}
