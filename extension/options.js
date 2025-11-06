const DEFAULT_WS_URL = "ws://127.0.0.1:8765";

function randomProfileName(){
  return "prof_" + Math.random().toString(36).slice(2, 8);
}

async function readProfileDefaults(){
  const fallback = { wsURL: DEFAULT_WS_URL, profile: randomProfileName() };
  try {
    const resp = await fetch(chrome.runtime.getURL("profile_config.json"));
    if (!resp.ok) return fallback;
    const data = await resp.json();
    if (typeof data.wsURL === "string" && data.wsURL.trim()) {
      fallback.wsURL = data.wsURL.trim();
    }
    if (typeof data.profile === "string" && data.profile.trim()) {
      fallback.profile = data.profile.trim();
    }
  } catch (e) {
    return fallback;
  }
  return fallback;
}

async function load(){
  const defaults = await readProfileDefaults();
  const s = await chrome.storage.local.get(["wsURL","profile"]);
  document.getElementById("wsURL").value = s.wsURL || defaults.wsURL;
  document.getElementById("profile").value = s.profile || defaults.profile;
}
async function save(){
  const wsURL = document.getElementById("wsURL").value.trim();
  const profile = document.getElementById("profile").value.trim();
  await chrome.storage.local.set({wsURL, profile});
  try{ await chrome.runtime.sendMessage({type:"reload_ws"}); }catch{}
  alert("Saved. Current profile: "+profile);
}
document.getElementById("save").addEventListener("click", save);
load();
