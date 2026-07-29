// Bakgrunns-service worker.
// Sørger for at sidepanelet åpnes når man klikker på verktøylinje-ikonet.

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((err) => console.error("Kunne ikke sette sidepanel-oppførsel:", err));
});
