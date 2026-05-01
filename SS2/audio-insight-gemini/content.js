(() => {
  function getMediaSrc(el) {
    if (el.src) return el.src;
    const source = el.querySelector("source[src]");
    if (source) return source.src;
    if (el.currentSrc) return el.currentSrc;
    return "";
  }

  function getMimeFromSrc(src) {
    const ext = src.split("?")[0].split(".").pop().toLowerCase();
    const map = {
      mp3: "audio/mpeg", wav: "audio/wav", ogg: "audio/ogg",
      flac: "audio/flac", aac: "audio/aac", m4a: "audio/mp4",
      webm: "audio/webm", mp4: "video/mp4", mpeg: "audio/mpeg"
    };
    return map[ext] || "";
  }

  function scanMedia() {
    const results = [];
    const seen = new Set();

    document.querySelectorAll("audio, video").forEach((el, idx) => {
      const src = getMediaSrc(el);
      if (!src || src.startsWith("blob:") || seen.has(src)) return;
      seen.add(src);

      const isVideo = el.tagName === "VIDEO";
      const duration = isFinite(el.duration) ? Math.round(el.duration) : null;

      let label = "";
      const closest = el.closest("[aria-label], [title]");
      if (closest) label = closest.getAttribute("aria-label") || closest.getAttribute("title") || "";
      if (!label) {
        const fname = src.split("/").pop().split("?")[0];
        label = decodeURIComponent(fname).slice(0, 80);
      }

      results.push({
        index: idx,
        src,
        mimeType: getMimeFromSrc(src),
        isVideo,
        duration,
        label
      });
    });

    return results;
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "SCAN_MEDIA") {
      sendResponse({
        pageTitle: document.title || "Untitled Page",
        pageUrl: window.location.href,
        media: scanMedia()
      });
      return true;
    }
    return false;
  });
})();
