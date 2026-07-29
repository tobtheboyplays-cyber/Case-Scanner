const felt = document.getElementById("proxyUrl");
const ok = document.getElementById("ok");

chrome.storage.local.get("proxyUrl").then(({ proxyUrl }) => {
  if (proxyUrl) felt.value = proxyUrl;
});

document.getElementById("lagre").addEventListener("click", async () => {
  let url = felt.value.trim().replace(/\/$/, "");
  if (url && !/^https?:\/\//.test(url)) url = "https://" + url;
  await chrome.storage.local.set({ proxyUrl: url });
  ok.textContent = "Lagret ✓";
  setTimeout(() => (ok.textContent = ""), 2000);
});
