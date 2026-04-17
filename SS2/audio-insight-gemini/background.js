chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "OPEN_RECORDER") {
    chrome.windows.create({
      url: chrome.runtime.getURL("recorder.html"),
      type: "popup",
      width: 420,
      height: 480,
      focused: true
    }).then((win) => sendResponse({ ok: true, windowId: win.id }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }
  return false;
});
