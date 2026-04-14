const STORAGE_KEYS = {
  clips: "researchClipItems",
  theme: "researchClipTheme"
};

const el = {
  selectedText: document.getElementById("selectedText"),
  manualNote: document.getElementById("manualNote"),
  tagsInput: document.getElementById("tagsInput"),
  pageTitle: document.getElementById("pageTitle"),
  pageUrl: document.getElementById("pageUrl"),
  saveBtn: document.getElementById("saveBtn"),
  clearFormBtn: document.getElementById("clearFormBtn"),
  refreshSelectionBtn: document.getElementById("refreshSelectionBtn"),
  searchInput: document.getElementById("searchInput"),
  listContainer: document.getElementById("listContainer"),
  emptyState: document.getElementById("emptyState"),
  itemCount: document.getElementById("itemCount"),
  themeToggle: document.getElementById("themeToggle"),
  itemTemplate: document.getElementById("itemTemplate")
};

let currentPage = {
  title: "",
  url: ""
};

let clips = [];
let editingId = null;

function generateId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function parseTags(raw) {
  return raw
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

async function fetchPageContext() {
  try {
    const tab = await getActiveTab();
    if (!tab?.id) {
      return;
    }

    const response = await chrome.tabs.sendMessage(tab.id, { type: "GET_PAGE_CONTEXT" });
    currentPage = {
      title: response?.title || tab.title || "Untitled Page",
      url: response?.url || tab.url || ""
    };

    el.pageTitle.textContent = currentPage.title || "-";
    el.pageUrl.textContent = currentPage.url || "-";
    if (response?.selectedText) {
      el.selectedText.value = response.selectedText;
    }
  } catch (_error) {
    const tab = await getActiveTab();
    currentPage = {
      title: tab?.title || "Unavailable",
      url: tab?.url || ""
    };
    el.pageTitle.textContent = currentPage.title || "-";
    el.pageUrl.textContent = currentPage.url || "-";
  }
}

async function loadClips() {
  const data = await chrome.storage.local.get(STORAGE_KEYS.clips);
  clips = Array.isArray(data[STORAGE_KEYS.clips]) ? data[STORAGE_KEYS.clips] : [];
}

async function saveClips() {
  await chrome.storage.local.set({ [STORAGE_KEYS.clips]: clips });
}

function resetForm() {
  editingId = null;
  el.selectedText.value = "";
  el.manualNote.value = "";
  el.tagsInput.value = "";
  el.saveBtn.textContent = "Save Clip";
}

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleString();
  } catch (_error) {
    return iso;
  }
}

async function copyText(text) {
  await navigator.clipboard.writeText(text);
}

function buildCopyPayload(item) {
  return [
    `Title: ${item.title}`,
    `URL: ${item.url}`,
    item.selectedText ? `Selected Text:\n${item.selectedText}` : "",
    item.manualNote ? `Note:\n${item.manualNote}` : "",
    item.tags?.length ? `Tags: ${item.tags.join(", ")}` : ""
  ]
    .filter(Boolean)
    .join("\n\n");
}

function renderClips() {
  const query = el.searchInput.value.trim().toLowerCase();

  const filtered = clips.filter((item) => {
    if (!query) {
      return true;
    }

    const haystack = [
      item.title,
      item.url,
      item.selectedText,
      item.manualNote,
      ...(item.tags || [])
    ]
      .join(" ")
      .toLowerCase();

    return haystack.includes(query);
  });

  el.listContainer.innerHTML = "";
  el.itemCount.textContent = String(filtered.length);
  el.emptyState.classList.toggle("hidden", filtered.length !== 0);

  filtered
    .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))
    .forEach((item) => {
      const node = el.itemTemplate.content.firstElementChild.cloneNode(true);

      node.querySelector(".clip-title").textContent = item.title || "Untitled";

      const urlEl = node.querySelector(".clip-url");
      urlEl.href = item.url;
      urlEl.textContent = item.url;

      node.querySelector(".clip-selection").textContent = item.selectedText || "No selected text.";
      node.querySelector(".clip-note").textContent = item.manualNote ? `Note: ${item.manualNote}` : "";
      node.querySelector(".clip-footer").textContent = `Updated: ${formatDate(item.updatedAt)}`;

      const tagsBox = node.querySelector(".clip-tags");
      (item.tags || []).forEach((tag) => {
        const span = document.createElement("span");
        span.className = "tag";
        span.textContent = tag;
        tagsBox.appendChild(span);
      });

      node.querySelector(".copy-btn").addEventListener("click", async () => {
        await copyText(buildCopyPayload(item));
      });

      node.querySelector(".edit-btn").addEventListener("click", () => {
        editingId = item.id;
        el.selectedText.value = item.selectedText || "";
        el.manualNote.value = item.manualNote || "";
        el.tagsInput.value = (item.tags || []).join(", ");
        currentPage = { title: item.title, url: item.url };
        el.pageTitle.textContent = item.title || "-";
        el.pageUrl.textContent = item.url || "-";
        el.saveBtn.textContent = "Update Clip";
      });

      node.querySelector(".delete-btn").addEventListener("click", async () => {
        clips = clips.filter((clip) => clip.id !== item.id);
        await saveClips();
        renderClips();
      });

      el.listContainer.appendChild(node);
    });
}

async function handleSave() {
  const selectedText = el.selectedText.value.trim();
  const manualNote = el.manualNote.value.trim();
  const tags = parseTags(el.tagsInput.value);

  if (!selectedText && !manualNote) {
    window.alert("Add selected text or a note before saving.");
    return;
  }

  const now = new Date().toISOString();

  if (editingId) {
    clips = clips.map((item) => {
      if (item.id !== editingId) {
        return item;
      }
      return {
        ...item,
        title: currentPage.title || item.title,
        url: currentPage.url || item.url,
        selectedText,
        manualNote,
        tags,
        updatedAt: now
      };
    });
  } else {
    clips.unshift({
      id: generateId(),
      title: currentPage.title || "Untitled Page",
      url: currentPage.url || "",
      selectedText,
      manualNote,
      tags,
      createdAt: now,
      updatedAt: now
    });
  }

  await saveClips();
  resetForm();
  await fetchPageContext();
  renderClips();
}

async function loadTheme() {
  const data = await chrome.storage.local.get(STORAGE_KEYS.theme);
  const theme = data[STORAGE_KEYS.theme] || "light";
  document.body.classList.toggle("dark", theme === "dark");
  el.themeToggle.checked = theme === "dark";
}

async function toggleTheme() {
  const nextTheme = el.themeToggle.checked ? "dark" : "light";
  document.body.classList.toggle("dark", nextTheme === "dark");
  await chrome.storage.local.set({ [STORAGE_KEYS.theme]: nextTheme });
}

async function init() {
  await loadTheme();
  await loadClips();
  await fetchPageContext();
  renderClips();

  el.saveBtn.addEventListener("click", handleSave);
  el.clearFormBtn.addEventListener("click", resetForm);
  el.refreshSelectionBtn.addEventListener("click", fetchPageContext);
  el.searchInput.addEventListener("input", renderClips);
  el.themeToggle.addEventListener("change", toggleTheme);
}

init();
