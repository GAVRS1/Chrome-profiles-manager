let ws = null;
let wsURL = "ws://127.0.0.1:8765";
let profile = "prof_"+Math.random().toString(36).slice(2,8);
let ready = false;
let retry = 1000;

async function loadCfg() {
  const s = await chrome.storage.local.get(["wsURL","profile"]);
  wsURL = s.wsURL || wsURL;
  profile = s.profile || profile;
}

function connect() {
  if (ws) { try{ ws.close(); }catch{} ws=null; }
  ready = false;

  const url = `${wsURL}?profile=${encodeURIComponent(profile)}`;
  try { ws = new WebSocket(url); } catch { schedule(); return; }

  ws.onopen = () => { ready = true; retry = 1000; ping(); };
  ws.onclose = (ev) => { ready = false; schedule(); };
  ws.onerror = () => { ready = false; schedule(); };
  ws.onmessage = (ev) => {
    let data; try { data = JSON.parse(ev.data); } catch { return; }
    // отдаём SW, он уже раскидает по вкладкам
    chrome.runtime.sendMessage({source:"offscreen", payload:data}).catch(()=>{});
  };
}

function schedule(){
  retry = Math.min((retry * 1.7) | 0, 15000); // экспоненциальный бэкофф
  setTimeout(connect, retry);
}

function ping(){
  if (ready) {
    try { ws.send(JSON.stringify({type:"status", ts:Date.now(), profile})); } catch {}
  }
  setTimeout(ping, 15000);
}

// сообщения от SW
chrome.runtime.onMessage.addListener((msg)=>{
  if (!msg || msg.source !== "sw") return;
  if (msg.type === "cfg") {
    wsURL = msg.wsURL || wsURL;
    profile = msg.profile || profile;
    connect();
  } else if (msg.type === "send" && ready) {
    try { ws.send(JSON.stringify(msg.data)); } catch {}
  }
});

loadCfg().then(connect);
