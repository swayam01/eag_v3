(() => {
  function getPageSelection() {
    const selection = window.getSelection();
    return selection ? selection.toString().trim() : "";
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "GET_PAGE_CONTEXT") {
      sendResponse({
        title: document.title || "Untitled Page",
        url: window.location.href,
        selectedText: getPageSelection()
      });
      return true;
    }
    return false;
  });
})();
