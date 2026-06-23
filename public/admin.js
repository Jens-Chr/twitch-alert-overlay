(() => {
  const apiBase = "/admin/alerts/api/files";

  const state = {
    files: [],
    selectedName: "",
    search: "",
    toastTimer: 0,
  };

  const el = {
    uploadButton: document.getElementById("uploadButton"),
    fileInput: document.getElementById("fileInput"),
    dropZone: document.getElementById("dropZone"),
    uploadStatus: document.getElementById("uploadStatus"),
    search: document.getElementById("searchInput"),
    list: document.getElementById("fileList"),
    name: document.getElementById("nameInput"),
    size: document.getElementById("sizeInput"),
    modified: document.getElementById("modifiedInput"),
    url: document.getElementById("urlInput"),
    selectedInfo: document.getElementById("selectedInfo"),
    refresh: document.getElementById("refreshButton"),
    delete: document.getElementById("deleteButton"),
    openLink: document.getElementById("openLink"),
    video: document.getElementById("previewVideo"),
    emptyPreview: document.getElementById("emptyPreview"),
    toast: document.getElementById("toast"),
  };

  async function api(path, options = {}) {
    const response = await fetch(path, { ...options, cache: "no-store" });
    const contentType = response.headers.get("Content-Type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : await response.text();

    if (response.status === 401) {
      window.location.href = "/admin/alerts";
      throw new Error("admin login required");
    }
    if (!response.ok) {
      throw new Error(payload.error || response.statusText || "Request failed");
    }
    return payload;
  }

  function fileApiPath(name) {
    return apiBase + "/" + encodeURIComponent(name);
  }

  function mediaPath(file) {
    const version = file.modifiedAt ? "?v=" + encodeURIComponent(file.modifiedAt) : "";
    return file.url + version;
  }

  function formatSize(bytes) {
    if (!Number.isFinite(bytes)) {
      return "";
    }
    const units = ["B", "KB", "MB", "GB"];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit += 1;
    }
    const digits = unit === 0 ? 0 : value >= 10 ? 1 : 2;
    return value.toFixed(digits) + " " + units[unit];
  }

  function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "";
    }
    return date.toLocaleString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function showToast(message, isError = false) {
    window.clearTimeout(state.toastTimer);
    el.toast.textContent = message;
    el.toast.classList.toggle("is-error", isError);
    el.toast.hidden = false;
    state.toastTimer = window.setTimeout(() => {
      el.toast.hidden = true;
    }, isError ? 5200 : 2600);
  }

  function selectedFile() {
    return state.files.find((file) => file.name === state.selectedName) || null;
  }

  function filteredFiles() {
    const search = state.search.trim().toLowerCase();
    if (!search) {
      return state.files;
    }
    return state.files.filter((file) => file.name.toLowerCase().includes(search));
  }

  function renderList() {
    el.list.textContent = "";
    if (state.files.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "Keine WebM-Dateien";
      el.list.appendChild(empty);
      return;
    }

    const items = filteredFiles();
    if (items.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "Keine Treffer";
      el.list.appendChild(empty);
      return;
    }

    for (const file of items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "file-item";
      button.classList.toggle("is-selected", file.name === state.selectedName);
      button.addEventListener("click", () => selectFile(file.name));

      const main = document.createElement("span");
      main.className = "file-main";

      const title = document.createElement("span");
      title.className = "file-title";
      title.textContent = file.name;

      const url = document.createElement("span");
      url.className = "file-url";
      url.textContent = file.url;

      const meta = document.createElement("span");
      meta.className = "file-meta";

      const size = document.createElement("span");
      size.className = "status-pill";
      size.textContent = formatSize(file.size);

      main.append(title, url);
      meta.append(size);
      button.append(main, meta);
      el.list.appendChild(button);
    }
  }

  function clearDetails() {
    state.selectedName = "";
    el.name.value = "";
    el.size.value = "";
    el.modified.value = "";
    el.url.value = "";
    el.selectedInfo.hidden = true;
    el.delete.disabled = true;
    el.openLink.href = "#";
    el.openLink.classList.add("is-disabled");
    el.video.pause();
    el.video.removeAttribute("src");
    el.video.load();
    el.video.hidden = true;
    el.emptyPreview.hidden = false;
    renderList();
  }

  function renderDetails() {
    const file = selectedFile();
    if (!file) {
      clearDetails();
      return;
    }

    el.name.value = file.name;
    el.size.value = formatSize(file.size);
    el.modified.value = formatDate(file.modifiedAt);
    el.url.value = file.url;
    el.selectedInfo.textContent = "Webhook-Wert: " + file.name;
    el.selectedInfo.hidden = false;
    el.delete.disabled = false;
    el.openLink.href = file.url;
    el.openLink.classList.remove("is-disabled");
    el.video.src = mediaPath(file);
    el.video.hidden = false;
    el.emptyPreview.hidden = true;
    renderList();
  }

  function selectFile(name) {
    state.selectedName = name;
    renderDetails();
  }

  async function loadFiles({ keepSelection = false } = {}) {
    const previous = state.selectedName;
    const payload = await api(apiBase);
    state.files = Array.isArray(payload.files) ? payload.files : [];
    if (keepSelection && state.files.some((file) => file.name === previous)) {
      state.selectedName = previous;
    } else if (!state.files.some((file) => file.name === state.selectedName)) {
      state.selectedName = state.files[0]?.name || "";
    }
    renderList();
    renderDetails();
  }

  function validWebM(file) {
    return file && file.name && file.name.toLowerCase().endsWith(".webm");
  }

  async function uploadFiles(fileList) {
    const files = Array.from(fileList || []).filter(validWebM);
    if (files.length === 0) {
      showToast("Keine WebM-Datei gefunden", true);
      return;
    }

    let uploaded = 0;
    for (const file of files) {
      el.uploadStatus.textContent = "Upload: " + file.name;
      try {
        await api(fileApiPath(file.name), {
          method: "POST",
          headers: { "Content-Type": file.type || "video/webm" },
          body: file,
        });
        uploaded += 1;
        state.selectedName = file.name;
      } catch (error) {
        showToast(file.name + ": " + error.message, true);
      }
    }

    el.uploadStatus.textContent = "Bereit";
    await loadFiles({ keepSelection: true });
    if (uploaded > 0) {
      showToast(uploaded === 1 ? "Datei hochgeladen" : uploaded + " Dateien hochgeladen");
    }
  }

  async function deleteSelected() {
    const file = selectedFile();
    if (!file) {
      return;
    }
    if (!window.confirm('Datei "' + file.name + '" loeschen?')) {
      return;
    }

    try {
      await api(fileApiPath(file.name), { method: "DELETE" });
      showToast("Datei geloescht");
      state.selectedName = "";
      await loadFiles();
    } catch (error) {
      showToast(error.message, true);
    }
  }

  function wireDropZone() {
    el.uploadButton.addEventListener("click", () => el.fileInput.click());
    el.dropZone.addEventListener("click", () => el.fileInput.click());
    el.dropZone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        el.fileInput.click();
      }
    });
    el.fileInput.addEventListener("change", () => {
      uploadFiles(el.fileInput.files);
      el.fileInput.value = "";
    });

    for (const eventName of ["dragenter", "dragover"]) {
      el.dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        el.dropZone.classList.add("is-dragging");
      });
    }
    for (const eventName of ["dragleave", "drop"]) {
      el.dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        el.dropZone.classList.remove("is-dragging");
      });
    }
    el.dropZone.addEventListener("drop", (event) => uploadFiles(event.dataTransfer.files));
  }

  el.search.addEventListener("input", () => {
    state.search = el.search.value;
    renderList();
  });
  el.refresh.addEventListener("click", () => {
    loadFiles({ keepSelection: true }).then(() => showToast("Liste aktualisiert")).catch((error) => showToast(error.message, true));
  });
  el.delete.addEventListener("click", deleteSelected);

  wireDropZone();
  loadFiles().catch((error) => showToast(error.message, true));
})();
