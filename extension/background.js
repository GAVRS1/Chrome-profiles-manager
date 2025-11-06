const DEFAULT_WS_URL = "ws://127.0.0.1:8765";

function randomProfileName(){
  return "prof_" + Math.random().toString(36).slice(2, 8);
}

let cfg = { wsURL: DEFAULT_WS_URL, profile: randomProfileName() };

async function readProfileDefaults(){
  try {
    const resp = await fetch(chrome.runtime.getURL("profile_config.json"));
    if (!resp.ok) return {};
    const data = await resp.json();
    const result = {};
    if (typeof data.wsURL === "string" && data.wsURL.trim()) {
      result.wsURL = data.wsURL.trim();
    }
    if (typeof data.profile === "string" && data.profile.trim()) {
      result.profile = data.profile.trim();
    }
    return result;
  } catch (e) {
    return {};
  }
}

// вкладка, которую мы «ведём» в этом профиле
let controlledTabId = null;

// грузим конфиг из storage
async function loadCfg() {
  const defaults = await readProfileDefaults();
  if (defaults.wsURL) cfg.wsURL = defaults.wsURL;
  if (defaults.profile) cfg.profile = defaults.profile;
  const s = await chrome.storage.local.get(["wsURL","profile"]);
  cfg.wsURL = s.wsURL || cfg.wsURL;
  cfg.profile = s.profile || cfg.profile;
}

// гарантируем offscreen-документ (WS живёт там)
async function ensureOffscreen() {
  if (chrome.offscreen && chrome.offscreen.hasDocument) {
    const has = await chrome.offscreen.hasDocument();
    if (has) return;
  }
  await chrome.offscreen.createDocument({
    url: chrome.runtime.getURL("offscreen.html"),
    reasons: ['BLOBS'],
    justification: 'Persistent WebSocket to local hub'
  });
  // передадим стартовую конфигурацию
  chrome.runtime.sendMessage({source:"sw", type:"cfg", wsURL: cfg.wsURL, profile: cfg.profile}).catch(()=>{});
}

// выбрать активную вкладку и взять под контроль (если ещё нет)
async function ensureControlledTab() {
  if (controlledTabId != null) return controlledTabId;
  const [tab] = await chrome.tabs.query({active:true, lastFocusedWindow:true});
  if (tab && tab.id != null) {
    controlledTabId = tab.id;
    return controlledTabId;
  }
  // если активной нет — берём первую попавшуюся http/https/file
  const tabs = await chrome.tabs.query({url:["http://*/*","https://*/*","file://*/*"]});
  if (tabs && tabs.length) {
    controlledTabId = tabs[0].id;
    return controlledTabId;
  }
  return null;
}

// безопасная отправка ТОЛЬКО в контролируемую вкладку
async function sendToControlled(data) {
  const id = controlledTabId ?? await ensureControlledTab();
  if (id == null) return;
  try {
    await chrome.tabs.sendMessage(id, data);
  } catch (e) {
    // вкладка могла закрыться — попробуем выбрать другую
    controlledTabId = null;
    const fallback = await ensureControlledTab();
    if (fallback != null) {
      try { await chrome.tabs.sendMessage(fallback, data); } catch {}
    }
  }
}

// держим controlledTabId в актуальном состоянии
chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabId === controlledTabId) controlledTabId = null;
});

// опционально можно следовать за активной вкладкой:
// chrome.tabs.onActivated.addListener((info) => { controlledTabId = info.tabId; });

// сообщения:
// 1) из offscreen (данные с WS-хаба) → ТОЛЬКО в контролируемую вкладку
// 2) из контент-скриптов (события мастера) → переправить в offscreen (чтобы ушло на хаб)
chrome.runtime.onMessage.addListener((msg, sender) => {
  // из offscreen
  if (msg && msg.source === "offscreen") {
    const data = msg.payload;
    if (!data) return;

    // не спамим hub_state в контент
    if (data.type === "hub_state") return;

    // спец-обработка навигации с созданием новой вкладки
    if (data.type === "nav" && data.payload && data.payload.action === "link" && data.payload.newTab === true) {
      // создаём новую вкладку, берём её под контроль
      chrome.tabs.create({ url: data.payload.href, active: true }, (tab) => {
        if (tab && tab.id != null) controlledTabId = tab.id;
      });
      return;
    }

    // всё остальное — направляем только в контролируемую вкладку
    sendToControlled(data);
  }
  // из контент-скриптов
  else if (msg && msg.type && (
           msg.type === "key"    || msg.type === "nav"   || msg.type === "rpc" ||
           msg.type === "input"  || msg.type === "click" || msg.type === "scroll" ||
           msg.type === "status")) {
    chrome.runtime.sendMessage({source:"sw", type:"send", data: msg}).catch(()=>{});
  }
});

// изменения настроек — пробросить в offscreen
chrome.storage.onChanged.addListener((changes)=>{
  if (changes.wsURL) cfg.wsURL = changes.wsURL.newValue;
  if (changes.profile) cfg.profile = changes.profile.newValue;
  chrome.runtime.sendMessage({source:"sw", type:"cfg", wsURL: cfg.wsURL, profile: cfg.profile}).catch(()=>{});
});

// init
loadCfg().then(ensureOffscreen);
