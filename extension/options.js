async function load(){
  const s = await chrome.storage.local.get(["wsURL","profile"]);
  document.getElementById("wsURL").value = s.wsURL || "ws://127.0.0.1:8765";
  document.getElementById("profile").value = s.profile || "prof_"+Math.random().toString(36).slice(2,8);
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
