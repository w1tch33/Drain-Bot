(function () {
  const state = {
    playlist: [],
    playlistIndex: 0,
    currentDrain: null,
    gameCleanup: null,
    marqueeX: 0,
    meowTimer: null,
  };

  const qs = (selector) => document.querySelector(selector);
  const resultsPanel = qs("#resultsPanel");
  const searchPanel = qs("#searchPanel");
  const loadingOverlay = qs("#loadingOverlay");
  const loadingDots = qs("#loadingDots");
  const visitedCount = qs("#visitedCount");
  const modalLayer = qs("#modalLayer");
  const modalTitle = qs("#modalTitle");
  const modalBody = qs("#modalBody");
  const imagePreviewLayer = qs("#imagePreviewLayer");
  const imagePreviewTitle = qs("#imagePreviewTitle");
  const imagePreviewBody = qs("#imagePreviewBody");
  const audioPlayer = qs("#audioPlayer");
  const meowPlayer = qs("#meowPlayer");
  const meowFlash = qs("#meowFlash");
  const songMarquee = qs("#songMarquee");
  const searchInput = qs("#searchInput");
  const minDistance = qs("#minDistance");
  const maxDistance = qs("#maxDistance");
  const volumeControl = qs("#volumeControl");
  const minDistanceValue = qs("#minDistanceValue");
  const maxDistanceValue = qs("#maxDistanceValue");
  const volumeValue = qs("#volumeValue");
  const desktop = qs("#desktop");
  const BASE_WIDTH = 1433;
  const BASE_HEIGHT = 768;
  const DRAIN_MAN_HIGH_SCORE_KEY = "draintool-drainman-high-score";
  const CLIMBER_HIGH_SCORE_KEY = "draintool-drainclimber-high-score";
  let musicMarqueeTimer = null;
  let audioUnlocked = false;
  let pendingAutoplay = false;

  function requestLocation() {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          await fetchJson("/api/location", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              lat: position.coords.latitude,
              lon: position.coords.longitude,
            }),
          });
        } catch (_error) {
          // Keep current fallback origin if location save fails.
        }
      },
      () => {},
      { enableHighAccuracy: true, maximumAge: 300000, timeout: 8000 }
    );
  }

  function setLoading(visible) {
    loadingOverlay.classList.toggle("hidden", !visible);
  }

  function fitDesktop() {
    if (window.innerWidth <= 980) {
      desktop.style.transform = "none";
      return;
    }
    const scale = Math.min(window.innerWidth / BASE_WIDTH, window.innerHeight / BASE_HEIGHT, 1);
    desktop.style.transform = `scale(${scale})`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function formatMinutes(minutes) {
    const rounded = Math.round(minutes);
    if (rounded < 60) return `${rounded} min`;
    const hours = Math.floor(rounded / 60);
    const mins = rounded % 60;
    return mins ? `${hours}h ${mins}m` : `${hours}h`;
  }

  function syncSliders() {
    if (Number(minDistance.value) > Number(maxDistance.value)) {
      minDistance.value = maxDistance.value;
    }
    minDistanceValue.textContent = minDistance.value;
    maxDistanceValue.textContent = maxDistance.value;
    positionSliderValue(minDistance, minDistanceValue);
    positionSliderValue(maxDistance, maxDistanceValue);
  }

  function positionSliderValue(slider, label) {
    const min = Number(slider.min || 0);
    const max = Number(slider.max || 100);
    const value = Number(slider.value || 0);
    const percent = max === min ? 0 : (value - min) / (max - min);
    const trackWidth = slider.clientWidth - 18;
    const x = 9 + trackWidth * percent;
    label.style.left = `${x}px`;
  }

  function queryParams() {
    return new URLSearchParams({
      min_distance: minDistance.value,
      max_distance: maxDistance.value,
      only_unvisited: qs("#onlyUnvisited").checked ? "1" : "0",
      session_type: "long",
    });
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed");
    return data;
  }

  function drawMessage(text) {
    resultsPanel.innerHTML = `<div>${escapeHtml(text)}</div>`;
  }

  function resultButton(row) {
    const button = document.createElement("button");
    button.className = "retro-button result-item";
    button.type = "button";
    button.innerHTML = `<span class="result-line">${escapeHtml(row.name)} (${Number(row.distance_km).toFixed(1)} km)${row.drive_time_text ? ` (${escapeHtml(row.drive_time_text)})` : ""}</span>`;
    button.addEventListener("click", () => openDrain(row.name));
    return button;
  }

  function renderRows(rows) {
    resultsPanel.innerHTML = "";
    if (!rows.length) {
      drawMessage("No drains found.");
      return;
    }
    rows.forEach((row) => resultsPanel.appendChild(resultButton(row)));
  }

  function haversine(a, b) {
    const rad = (value) => (value * Math.PI) / 180;
    const radius = 6371;
    const dLat = rad(b.lat - a.lat);
    const dLon = rad(b.lon - a.lon);
    const inner =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
    return radius * 2 * Math.atan2(Math.sqrt(inner), Math.sqrt(1 - inner));
  }

  function renderRoute(route) {
    resultsPanel.innerHTML = "";
    if (!route.route || route.route.length < 2) {
      drawMessage("No valid route found");
      return;
    }

    const parts = route.route.map((item, index) => {
      if (index === 0) return item.name;
      return `${haversine(route.route[index - 1], item).toFixed(1)}km -> ${item.name}`;
    });

    resultsPanel.insertAdjacentHTML("beforeend", `<div>${escapeHtml(parts.join(" -> "))}</div>`);
    resultsPanel.insertAdjacentHTML(
      "beforeend",
      `<div style="margin:6px 0 10px;">Total time: ${escapeHtml(formatMinutes(route.total_minutes))}</div>`
    );

    route.route.forEach((row) => {
      resultsPanel.appendChild(
        resultButton({
          name: row.name,
          distance_km: row.distance_km,
          drive_time_text: formatMinutes(row.drive_minutes || 0),
        })
      );
    });
  }

  async function runPicker() {
    setLoading(true);
    try {
      renderRows(await fetchJson(`/api/run?${queryParams().toString()}`));
    } catch (error) {
      drawMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function buildRoute() {
    setLoading(true);
    try {
      renderRoute(await fetchJson(`/api/route?${queryParams().toString()}`));
    } catch (error) {
      drawMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function randomDrain() {
    setLoading(true);
    try {
      const drain = await fetchJson(`/api/random?${queryParams().toString()}`);
      await openDrain(drain.name);
    } catch (error) {
      drawMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function syncMap() {
    openModal("Sync Map", qs("#syncMapTemplate").content.cloneNode(true));
    qs("#undoSyncButton").addEventListener("click", async () => {
      setLoading(true);
      try {
        const result = await fetchJson("/api/sync-kml/undo", { method: "POST" });
        closeModal();
        await refreshStats();
        drawMessage(`Removed ${result.removed} drains from the last sync.`);
      } catch (error) {
        drawMessage(error.message);
      } finally {
        setLoading(false);
      }
    });
    qs("#syncMapForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      setLoading(true);
      try {
        const result = await fetchJson("/api/sync-kml", {
          method: "POST",
          body: new FormData(event.currentTarget),
        });
        closeModal();
        await refreshStats();
        drawMessage(`Import complete. Found ${result.count} entries and added ${result.added} new drains.`);
        if (searchInput.value.trim()) {
          await searchDrains();
        }
      } catch (error) {
        drawMessage(error.message);
      } finally {
        setLoading(false);
      }
    });
  }

  async function refreshStats() {
    const stats = await fetchJson("/api/stats");
    visitedCount.textContent = `Drains Completed: ${stats.visited}`;
  }

  async function searchDrains() {
    const query = searchInput.value.trim();
    if (!query) {
      searchPanel.innerHTML = "";
      return;
    }
    try {
      const rows = await fetchJson(
        `/api/search?q=${encodeURIComponent(query)}&only_unvisited=${qs("#onlyUnvisited").checked ? "1" : "0"}`
      );
      searchPanel.innerHTML = "";
      rows.forEach((row) => searchPanel.appendChild(resultButton(row)));
    } catch (error) {
      searchPanel.textContent = error.message;
    }
  }

  function openModal(title, content) {
    modalTitle.innerHTML = `<span>${escapeHtml(title)}</span>`;
    modalBody.innerHTML = "";
    if (typeof content === "string") modalBody.innerHTML = content;
    else modalBody.appendChild(content);
    modalLayer.classList.remove("hidden");
  }

  function closeModal() {
    modalLayer.classList.add("hidden");
    modalBody.innerHTML = "";
    if (state.gameCleanup) {
      state.gameCleanup();
      state.gameCleanup = null;
    }
  }

  function openImagePreview(title, url) {
    imagePreviewTitle.innerHTML = `<span>${escapeHtml(title)}</span>`;
    imagePreviewBody.innerHTML = `<img src="${escapeHtml(url)}" alt="${escapeHtml(title)}">`;
    imagePreviewLayer.classList.remove("hidden");
  }

  function closeImagePreview() {
    imagePreviewLayer.classList.add("hidden");
    imagePreviewBody.innerHTML = "";
  }

  function setupLoadingDots() {
    let count = 0;
    setInterval(() => {
      if (loadingOverlay.classList.contains("hidden")) return;
      count = (count + 1) % 4;
      loadingDots.textContent = ".".repeat(count);
    }, 300);
  }

  function showMeow() {
    meowFlash.classList.remove("hidden");
    meowFlash.getAnimations().forEach((animation) => animation.cancel());
    meowFlash.style.animation = "none";
    meowFlash.offsetHeight;
    meowFlash.style.animation = "";
    clearTimeout(state.meowTimer);
    state.meowTimer = setTimeout(() => {
      meowFlash.classList.add("hidden");
    }, 820);
  }

  function startSongMarquee(text) {
    if (musicMarqueeTimer) {
      clearInterval(musicMarqueeTimer);
      musicMarqueeTimer = null;
    }

    const clean = text || "";
    songMarquee.innerHTML = `<span class="song-track">${escapeHtml(clean)}</span>`;
    const track = songMarquee.querySelector(".song-track");
    if (!track) return;

    requestAnimationFrame(() => {
      const containerWidth = songMarquee.clientWidth;
      const trackWidth = track.scrollWidth;

      let x = containerWidth;
      const resetPoint = Math.max(trackWidth, containerWidth);
      musicMarqueeTimer = setInterval(() => {
        x -= 1;
        if (x < -resetPoint - 24) {
          x = containerWidth;
        }
        track.style.transform = `translateX(${x}px)`;
      }, 16);
    });
  }

  function unlockAudio() {
    if (audioUnlocked) {
      if (audioPlayer.muted && !audioPlayer.paused) {
        audioPlayer.muted = false;
        audioPlayer.volume = Number(volumeControl.value);
      }
      return;
    }
    audioUnlocked = true;
    if (pendingAutoplay) {
      pendingAutoplay = false;
      startPlaybackAt(state.playlistIndex);
    }
  }

  function readStoredNumber(key) {
    try {
      return Number(window.localStorage.getItem(key) || 0);
    } catch (_error) {
      return 0;
    }
  }

  function writeStoredNumber(key, value) {
    try {
      window.localStorage.setItem(key, String(value));
    } catch (_error) {
      // Ignore storage failures in restricted browsers.
    }
  }

  function detailHtml(drain) {
    const photos = (drain.photos || [])
      .map((photo) => {
        if (photo.available) {
          return `<div class="photo-card"><img class="preview-photo" src="${escapeHtml(photo.url)}" alt="${escapeHtml(photo.filename)}" data-url="${escapeHtml(photo.url)}" data-title="${escapeHtml(photo.filename)}"><div>${escapeHtml(photo.filename)}</div><button class="retro-button delete-photo" type="button" data-path="${escapeHtml(photo.path)}">Delete</button></div>`;
        }
        return `<div class="photo-card"><div style="height:80px;display:grid;place-items:center;border:1px solid #000;">Local only</div><div>${escapeHtml(photo.filename)}</div></div>`;
      })
      .join("");

    const nearby = (drain.nearby || [])
      .map(
        (item) =>
          `<button class="retro-button nearby-open" type="button" data-name="${escapeHtml(item.name)}">${escapeHtml(item.name)} (${Number(item.distance_from_current_km).toFixed(2)} km)</button>`
      )
      .join("");

    const features = ["Junction", "Split", "Slide", "Grille Room", "Chamber", "Waterfall", "Side-Pipe"];
    const showDelete = drain.source === "custom" || drain.source === "synced";

    return `
      <div class="detail-section detail-actions">
        <button class="retro-button" type="button" id="nearbyButton">Nearby</button>
        <button class="retro-button" type="button" id="routeFromHereButton">Build Route</button>
        <a class="retro-button" href="${escapeHtml(drain.maps_url)}" target="_blank" rel="noreferrer">Google Earth</a>
        ${showDelete ? '<button class="retro-button" type="button" id="deleteDrainButton">Delete Drain</button>' : ""}
      </div>
      <div class="detail-section nearby-list" id="nearbyArea"></div>
      <div class="detail-section">
        <label class="check-row"><input id="favoriteField" type="checkbox" ${drain.favorite ? "checked" : ""}><span>Favorite</span></label>
        <label class="check-row"><input id="visitedField" type="checkbox" ${drain.visited ? "checked" : ""}><span>Visited</span></label>
      </div>
      <div class="detail-section"><label>Description</label><textarea class="retro-textarea" id="descriptionField" rows="6">${escapeHtml(drain.description || "")}</textarea></div>
      <div class="detail-section"><label>Witch's Notes</label><textarea class="retro-textarea" id="notesField" rows="5">${escapeHtml(drain.notes || "")}</textarea></div>
      <div class="detail-section"><div>FEATURES:</div><div class="feature-grid">${features
        .map(
          (feature) =>
            `<label class="check-row"><input class="featureField" type="checkbox" value="${escapeHtml(feature)}" ${(drain.features || {})[feature] ? "checked" : ""}><span>${escapeHtml(feature)}</span></label>`
        )
        .join("")}</div></div>
      <div class="detail-section"><div>Difficulty</div><div class="difficulty-row">${["easy", "medium", "hard"]
        .map(
          (value) =>
            `<button class="retro-button difficulty-button ${drain.difficulty === value ? "active" : ""}" type="button" data-value="${value}">${value.toUpperCase()}</button>`
        )
        .join("")}</div></div>
      <div class="detail-section"><div>Value</div><div class="value-row">${["trash", "bad", "mid", "good", "amazing"]
        .map(
          (value) =>
            `<button class="retro-button value-button ${drain.value === value ? "active" : ""}" type="button" data-value="${value}">${value.toUpperCase()}</button>`
        )
        .join("")}</div></div>
      <div class="detail-section"><div>Rating (1-10)</div><div class="rating-row">${Array.from({ length: 10 }, (_, index) => index + 1)
        .map(
          (rating) =>
            `<button class="retro-button rating-button ${Number(drain.rating) === rating ? "active" : ""}" type="button" data-value="${rating}">${rating}</button>`
        )
        .join("")}</div></div>
      <div class="detail-section"><div class="photo-grid">${photos}</div><form id="photoUploadForm" enctype="multipart/form-data"><input class="retro-input" type="file" name="photo" accept="image/*"><button class="retro-button" type="submit">Add Photo</button></form></div>
      <div class="detail-section"><button class="retro-button" type="button" id="saveDrainButton">Save</button></div>
    `;
  }

  async function openDrain(name) {
    setLoading(true);
    try {
    state.currentDrain = await fetchJson(`/api/drains/${encodeURIComponent(name)}`);
      openModal(state.currentDrain.name, detailHtml(state.currentDrain));
      bindDetail(name);
    } catch (error) {
      drawMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  function bindDetail(name) {
    let difficulty = state.currentDrain.difficulty || "";
    let value = state.currentDrain.value || "";
    let rating = state.currentDrain.rating || "";
    const nearbyMarkup = (state.currentDrain.nearby || [])
      .map(
        (item) =>
          `<button class="retro-button nearby-open" type="button" data-name="${escapeHtml(item.name)}">${escapeHtml(item.name)} (${Number(item.distance_from_current_km).toFixed(2)} km)</button>`
      )
      .join("");

    const nearbyArea = modalBody.querySelector("#nearbyArea");
    modalBody.querySelector("#nearbyButton").addEventListener("click", () => {
      nearbyArea.innerHTML = nearbyMarkup || "<span>No nearby drains found.</span>";
      nearbyArea.querySelectorAll(".nearby-open").forEach((button) => {
        button.addEventListener("click", () => openDrain(button.dataset.name));
      });
    });
    modalBody.querySelector("#routeFromHereButton").addEventListener("click", async () => {
      renderRoute(await fetchJson(`/api/drains/${encodeURIComponent(name)}/route`));
      closeModal();
    });
    const deleteDrainButton = modalBody.querySelector("#deleteDrainButton");
    if (deleteDrainButton) {
      deleteDrainButton.addEventListener("click", async () => {
        await fetchJson(`/api/drains/${encodeURIComponent(name)}/delete`, { method: "POST" });
        await refreshStats();
        closeModal();
        drawMessage(`Deleted ${name}.`);
      });
    }

    modalBody.querySelectorAll(".difficulty-button").forEach((button) => {
      button.addEventListener("click", () => {
        difficulty = button.dataset.value;
        modalBody.querySelectorAll(".difficulty-button").forEach((item) => item.classList.toggle("active", item === button));
      });
    });

    modalBody.querySelectorAll(".value-button").forEach((button) => {
      button.addEventListener("click", () => {
        value = button.dataset.value;
        modalBody.querySelectorAll(".value-button").forEach((item) => item.classList.toggle("active", item === button));
      });
    });

    modalBody.querySelectorAll(".rating-button").forEach((button) => {
      button.addEventListener("click", () => {
        rating = Number(button.dataset.value);
        modalBody.querySelectorAll(".rating-button").forEach((item) => item.classList.toggle("active", item === button));
      });
    });

    modalBody.querySelectorAll(".delete-photo").forEach((button) => {
      button.addEventListener("click", async () => {
        const formData = new FormData();
        formData.append("path", button.dataset.path);
        await fetchJson(`/api/drains/${encodeURIComponent(name)}/photos/delete`, { method: "POST", body: formData });
        await openDrain(name);
      });
    });

    modalBody.querySelectorAll(".preview-photo").forEach((img) => {
      img.addEventListener("click", () => openImagePreview(img.dataset.title, img.dataset.url));
    });

    modalBody.querySelector("#photoUploadForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      await fetchJson(`/api/drains/${encodeURIComponent(name)}/photos`, {
        method: "POST",
        body: new FormData(event.currentTarget),
      });
      await openDrain(name);
    });

    modalBody.querySelector("#saveDrainButton").addEventListener("click", async () => {
      await fetchJson(`/api/drains/${encodeURIComponent(name)}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          favorite: modalBody.querySelector("#favoriteField").checked,
          visited: modalBody.querySelector("#visitedField").checked,
          description: modalBody.querySelector("#descriptionField").value,
          notes: modalBody.querySelector("#notesField").value,
          difficulty,
          value,
          rating,
          features: Array.from(modalBody.querySelectorAll(".featureField")).reduce((acc, field) => {
            acc[field.value] = field.checked;
            return acc;
          }, {}),
        }),
      });
      await refreshStats();
      await openDrain(name);
    });
  }

  function setupSmiley() {
    const frame = qs("#smileyFrame");
    let phase = 0;
    setInterval(() => {
      phase += 0.16;
      const bob = Math.sin(phase) * 10;
      const glitchX = Math.random() < 0.18 ? (Math.random() - 0.5) * 24 : 0;
      const glitchY = Math.random() < 0.18 ? (Math.random() - 0.5) * 18 : 0;
      frame.style.transform = `translate(${glitchX}px, ${bob + glitchY}px)`;
    }, 70);

    qs("#smileyImage").addEventListener("click", () => {
      unlockAudio();
      frame.animate(
        [
          { transform: frame.style.transform || "translate(0,0)" },
          { transform: "translate(0,-16px)" },
          { transform: frame.style.transform || "translate(0,0)" },
        ],
        { duration: 220, easing: "steps(2, end)" }
      );
      meowPlayer.currentTime = 0;
      meowPlayer.play().catch(() => {});
      showMeow();
    });
  }

  function setupMusic() {
    state.playlist = JSON.parse(qs("#desktop").dataset.playlist);
    if (!state.playlist.length) return;

    audioPlayer.volume = 0;
    volumeValue.textContent = Number(volumeControl.value).toFixed(2);
    startSongMarquee(state.playlist[0].replace(".mp3", ""));

    function fadeInToTarget(targetVolume) {
      const startVolume = Number(audioPlayer.volume || 0);
      const steps = 18;
      const duration = 1200;
      let step = 0;

      function tick() {
        step += 1;
        const nextVolume = startVolume + ((targetVolume - startVolume) * (step / steps));
        audioPlayer.volume = Math.max(0, Math.min(1, nextVolume));
        if (step < steps && !audioPlayer.paused) {
          window.setTimeout(tick, duration / steps);
        }
      }

      tick();
    }

    function startPlaybackAt(index, shouldFade = true, preferMutedAutoplay = false) {
      state.playlistIndex = (index + state.playlist.length) % state.playlist.length;
      const filename = state.playlist[state.playlistIndex];
      audioPlayer.src = `/audio/${encodeURIComponent(filename)}`;
      startSongMarquee(filename.replace(".mp3", ""));
      const targetVolume = Number(volumeControl.value);
      audioPlayer.muted = !!preferMutedAutoplay;
      if (shouldFade) {
        audioPlayer.volume = 0;
      } else {
        audioPlayer.volume = targetVolume;
      }
      audioPlayer.play()
        .then(() => {
          if (preferMutedAutoplay) {
            window.setTimeout(() => {
              audioPlayer.muted = false;
              if (shouldFade) fadeInToTarget(targetVolume);
              else audioPlayer.volume = targetVolume;
            }, 180);
          } else if (shouldFade) {
            fadeInToTarget(targetVolume);
          }
        })
        .catch(() => {
          pendingAutoplay = true;
        });
    }

    qs("#prevSong").addEventListener("click", () => startPlaybackAt(state.playlistIndex - 1));
    qs("#nextSong").addEventListener("click", () => startPlaybackAt(state.playlistIndex + 1));
    qs("#toggleSong").addEventListener("click", () => {
      if (!audioPlayer.src) startPlaybackAt(state.playlistIndex);
      else if (audioPlayer.paused) audioPlayer.play().catch(() => {});
      else audioPlayer.pause();
    });

    audioPlayer.addEventListener("ended", () => startPlaybackAt(state.playlistIndex + 1));
    volumeControl.addEventListener("input", () => {
      audioPlayer.volume = Number(volumeControl.value);
      volumeValue.textContent = Number(volumeControl.value).toFixed(2);
    });

    startPlaybackAt(0, true, true);
  }

  function openLinks() {
    openModal("Helpful Links", qs("#linksTemplate").content.cloneNode(true));
  }

  function openAddDrain() {
    openModal("Add Drain", qs("#addDrainTemplate").content.cloneNode(true));
    qs("#addDrainForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(event.currentTarget);
      await fetchJson("/api/custom-drains", { method: "POST", body: formData });
      await refreshStats();
      closeModal();
      await openDrain(formData.get("name"));
    });
  }

  function bindGameCleanup(handler, extraCleanup) {
    if (state.gameCleanup) state.gameCleanup();
    state.gameCleanup = () => {
      window.removeEventListener("keydown", handler);
      if (extraCleanup) extraCleanup();
    };
    window.addEventListener("keydown", handler);
  }

  function dispatchGameKey(type, key, code = "") {
    const event = new KeyboardEvent(type, {
      key,
      code: code || key,
      bubbles: true,
    });
    window.dispatchEvent(event);
  }

  function bindGameControls(container) {
    const cleanups = [];
    container.querySelectorAll(".game-control").forEach((button) => {
      const key = button.dataset.key || "";
      const code = button.dataset.code || "";
      const press = () => dispatchGameKey("keydown", key, code);
      const release = () => dispatchGameKey("keyup", key, code);

      button.addEventListener("pointerdown", press);
      button.addEventListener("pointerup", release);
      button.addEventListener("pointercancel", release);
      button.addEventListener("pointerleave", release);
      button.addEventListener("click", () => {
        if (key !== "Space") {
          dispatchGameKey("keydown", key, code);
          dispatchGameKey("keyup", key, code);
        }
      });
      cleanups.push(() => {
        button.removeEventListener("pointerdown", press);
        button.removeEventListener("pointerup", release);
        button.removeEventListener("pointercancel", release);
        button.removeEventListener("pointerleave", release);
      });
    });
    return () => cleanups.forEach((cleanup) => cleanup());
  }

  function openGames() {
    openModal("Mini Games", qs("#miniGamesTemplate").content.cloneNode(true));
    const canvas = qs("#gameCanvas");
    const help = qs("#gameHelp");
    const controls = qs("#gameControls");
    canvas.classList.add("hidden");
    help.classList.add("hidden");
    controls.classList.add("hidden");
    help.textContent = "SELECT GAME";
    bindGameControls(controls);
    modalBody.querySelectorAll(".game-button").forEach((button) => {
      button.addEventListener("click", () => {
        canvas.classList.remove("hidden");
        help.classList.remove("hidden");
        controls.classList.remove("hidden");
        if (state.gameCleanup) {
          state.gameCleanup();
          state.gameCleanup = null;
        }
        if (button.dataset.game === "navigator") runNavigator(canvas, help);
        else if (button.dataset.game === "drainman") runDrainMan(canvas, help);
        else runClimber(canvas, help);
      });
    });
  }

  function runNavigator(canvas, help) {
    const ctx = canvas.getContext("2d");
    canvas.width = 480;
    canvas.height = 480;
    help.textContent = "Use WASD or arrow keys to reach the glowing exit.";
    const size = [21, 25, 31][Math.floor(Math.random() * 3)];
    const tile = canvas.width / size;
    const maze = Array.from({ length: size }, () => Array(size).fill(1));
    const dirs = [[2, 0], [-2, 0], [0, 2], [0, -2]];
    const drips = [];
    let gameStarted = false;
    let gameWon = false;
    let countdown = 3;
    let drawRaf = null;
    let countdownTimer = null;

    function carve(x, y) {
      dirs.sort(() => Math.random() - 0.5);
      for (const [dx, dy] of dirs) {
        const nx = x + dx;
        const ny = y + dy;
        if (nx > 0 && ny > 0 && nx < size - 1 && ny < size - 1 && maze[ny][nx] === 1) {
          maze[y + dy / 2][x + dx / 2] = 0;
          maze[ny][nx] = 0;
          carve(nx, ny);
        }
      }
    }

    maze[1][1] = 0;
    carve(1, 1);
    maze[1][1] = 2;
    maze[size - 2][size - 2] = 3;
    const player = { x: 1, y: 1 };

    function spawnDrip() {
      if (Math.random() < 0.3) {
        const x = Math.floor(Math.random() * size);
        const y = Math.floor(Math.random() * size);
        if (maze[y][x] === 0) drips.push({ x, y, life: 0 });
      }
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (let y = 0; y < size; y += 1) {
        for (let x = 0; x < size; x += 1) {
          const value = maze[y][x];
          ctx.fillStyle =
            value === 1
              ? ["#3a3a3a", "#444", "#505050"][Math.floor(Math.random() * 3)]
              : value === 3
                ? Math.floor(Date.now() / 250) % 2 === 0 ? "#66FF66" : "#33CC33"
                : "#111";
          ctx.fillRect(x * tile, y * tile, tile, tile);
        }
      }
      spawnDrip();
      drips.forEach((drip) => {
        ctx.fillStyle = "#4FC3F7";
        ctx.beginPath();
        ctx.arc(drip.x * tile + tile / 2, drip.y * tile + drip.life, 2, 0, Math.PI * 2);
        ctx.fill();
        drip.life += 4;
      });
      for (let index = drips.length - 1; index >= 0; index -= 1) {
        if (drips[index].life > tile) drips.splice(index, 1);
      }
      ctx.fillStyle = "#00E5FF";
      ctx.fillRect(player.x * tile + 4, player.y * tile + 4, tile - 8, tile - 8);
      if (!gameStarted) {
        ctx.fillStyle = "#dcdcdc";
        ctx.font = 'bold 46px "ChicagoCustom", "Chicago", "Fixedsys", sans-serif';
        ctx.textAlign = "center";
        ctx.fillText(String(countdown), canvas.width / 2, canvas.height / 2);
      }
      if (gameWon) {
        ctx.fillStyle = "rgba(0, 0, 0, 0.7)";
        ctx.fillRect(84, 184, 312, 108);
        ctx.fillStyle = "#dcdcdc";
        ctx.font = 'bold 24px "ChicagoCustom", "Chicago", "Fixedsys", sans-serif';
        ctx.fillText("YOU ESCAPED", canvas.width / 2, 228);
        ctx.font = '18px "ChicagoCustom", "Chicago", "Fixedsys", sans-serif';
        ctx.fillText("Click Drain Navigator", canvas.width / 2, 258);
        ctx.fillText("to play again.", canvas.width / 2, 282);
      }
    }

    function onKey(event) {
      if (!gameStarted) return;
      const move = ({ w: [0, -1], a: [-1, 0], s: [0, 1], d: [1, 0], ArrowUp: [0, -1], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowRight: [1, 0] })[event.key];
      if (!move) return;
      const nx = player.x + move[0];
      const ny = player.y + move[1];
      if (maze[ny]?.[nx] !== 1) {
        player.x = nx;
        player.y = ny;
        draw();
        if (maze[ny][nx] === 3) {
          gameStarted = false;
          gameWon = true;
          help.textContent = "YOU ESCAPED THE DRAIN! Click Drain Navigator to play again.";
        }
      }
    }

    function tickCountdown() {
      draw();
      if (countdown > 1) {
        countdown -= 1;
        countdownTimer = setTimeout(tickCountdown, 1000);
      } else {
        countdown = 0;
        gameStarted = true;
        draw();
      }
    }

    function renderLoop() {
      draw();
      if (!gameWon) drawRaf = requestAnimationFrame(renderLoop);
    }

    bindGameCleanup(onKey, () => {
      if (drawRaf) cancelAnimationFrame(drawRaf);
      if (countdownTimer) clearTimeout(countdownTimer);
    });
    draw();
    drawRaf = requestAnimationFrame(renderLoop);
    countdownTimer = setTimeout(tickCountdown, 500);
  }

  function runDrainMan(canvas, help) {
    const ctx = canvas.getContext("2d");
    const layout = [
      "#####################",
      "#.........#.........#",
      "#.###.###.#.###.###.#",
      "#o###.###.#.###.###o#",
      "#...................#",
      "#.###.#.#####.#.###.#",
      "#.....#...#...#.....#",
      "#####.### # ###.#####",
      "    #.#       #.#    ",
      "#####.# ## ## #.#####",
      "     .  #   #  .     ",
      "#####.# ##### #.#####",
      "    #.#       #.#    ",
      "#####.# ##### #.#####",
      "#.........#.........#",
      "#.###.###.#.###.###.#",
      "#o..#.....P.....#..o#",
      "###.#.#.#####.#.#.###",
      "#.....#...#...#.....#",
      "#.######### #########",
      "#...................#",
      "#####################",
    ];
    const tile = 22;
    canvas.width = 462;
    canvas.height = 484;
    let player = { x: 10, y: 16 };
    let direction = { x: 1, y: 0 };
    let nextDirection = { x: 1, y: 0 };
    let turnBufferTimer = 0;
    let score = 0;
    let highScore = readStoredNumber(DRAIN_MAN_HIGH_SCORE_KEY);
    let level = 1;
    let frightened = false;
    let frightenedTimer = 0;
    let gameRunning = false;
    let mouthOpen = true;
    let statusMessage = "";
    const BASE_FRIGHT_TIME = 80;
    let frightTime = BASE_FRIGHT_TIME;
    let countdown = 3;
    let loopTimer = null;
    let countdownTimer = null;
    const dots = new Set();
    const powerDots = new Set();
    const walls = new Set();
    const cops = [{ x: 19, y: 19 }, { x: 19, y: 1 }];
    const copSpawns = [{ x: 19, y: 19 }, { x: 19, y: 1 }];
    help.textContent = "Use arrow keys. Eat dots and avoid the cops.";

    layout.forEach((row, y) => row.split("").forEach((cell, x) => {
      if (cell === "#") walls.add(`${x},${y}`);
      if (cell === ".") dots.add(`${x},${y}`);
      if (cell === "o") powerDots.add(`${x},${y}`);
      if (cell === "P") player = { x, y };
    }));

    function canMove(x, y) { return !walls.has(`${x},${y}`); }

    function updateHighScore() {
      if (score > highScore) {
        highScore = score;
        writeStoredNumber(DRAIN_MAN_HIGH_SCORE_KEY, highScore);
      }
    }

    function updateHelp(message) {
      if (message) {
        statusMessage = message;
        help.textContent = message;
        return;
      }
      if (!gameRunning && statusMessage) {
        help.textContent = statusMessage;
        return;
      }
      help.textContent = gameRunning
        ? `Score: ${score} | Level: ${level} | High: ${highScore}`
        : `LEVEL ${level}${countdown > 0 ? ` | ${countdown}` : ""} | High: ${highScore}`;
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      layout.forEach((row, y) => {
        row.split("").forEach((cell, x) => {
          ctx.fillStyle = walls.has(`${x},${y}`) ? "#0D47A1" : "#000";
          ctx.fillRect(x * tile, y * tile, tile, tile);
          if (dots.has(`${x},${y}`) || powerDots.has(`${x},${y}`)) {
            ctx.fillStyle = dots.has(`${x},${y}`) ? "#FFD54F" : "#FFEB3B";
            ctx.beginPath();
            ctx.arc(x * tile + tile / 2, y * tile + tile / 2, dots.has(`${x},${y}`) ? 3 : 6, 0, Math.PI * 2);
            ctx.fill();
          }
        });
      });
      ctx.fillStyle = "#FFEB3B";
      if (mouthOpen) {
        ctx.beginPath();
        ctx.arc(player.x * tile + tile / 2, player.y * tile + tile / 2, tile / 2 - 2, 0.25 * Math.PI, 1.75 * Math.PI);
        ctx.lineTo(player.x * tile + tile / 2, player.y * tile + tile / 2);
        ctx.fill();
      } else {
        ctx.beginPath();
        ctx.arc(player.x * tile + tile / 2, player.y * tile + tile / 2, tile / 2 - 2, 0, Math.PI * 2);
        ctx.fill();
      }
      cops.forEach((cop) => {
        ctx.fillStyle = frightened ? (frightenedTimer < 20 && frightenedTimer % 4 < 2 ? "#FFFFFF" : "#1E88E5") : "#E53935";
        ctx.beginPath();
        ctx.arc(cop.x * tile + tile / 2, cop.y * tile + tile / 2, tile / 2 - 4, 0, Math.PI * 2);
        ctx.fill();
      });
      updateHelp();
    }

    function onKey(event) {
      const move = ({ ArrowUp: [0, -1], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowRight: [1, 0], w: [0,-1], a: [-1,0], s:[0,1], d:[1,0] })[event.key];
      if (!move) return;
      nextDirection = { x: move[0], y: move[1] };
      turnBufferTimer = 5;
    }

    function moveCops() {
      cops.forEach((cop, index) => {
        const options = [[1,0],[-1,0],[0,1],[0,-1]].sort(() => Math.random() - 0.5);
        let best = null;
        let bestDist = frightened ? -1 : 9999;
        options.forEach(([dx, dy]) => {
          const nx = (cop.x + dx + layout[0].length) % layout[0].length;
          const ny = (cop.y + dy + layout.length) % layout.length;
          if (!canMove(nx, ny)) return;
          const dist = Math.abs(nx - player.x) + Math.abs(ny - player.y);
          if ((frightened && dist > bestDist) || (!frightened && dist < bestDist)) {
            bestDist = dist;
            best = { x: nx, y: ny };
          }
        });
        if (best) cops[index] = best;
      });
    }

    function restartCountdown() {
      gameRunning = false;
      countdown = 3;
      statusMessage = "";
      draw();
      if (countdownTimer) clearInterval(countdownTimer);
      countdownTimer = setInterval(() => {
        countdown -= 1;
        draw();
        if (countdown <= 0) {
          clearInterval(countdownTimer);
          countdownTimer = null;
          statusMessage = "";
          gameRunning = true;
          loopTimer = setTimeout(step, 110);
        }
      }, 1000);
    }

    function step() {
      if (!gameRunning) return;
      if (turnBufferTimer > 0) {
        const tx = (player.x + nextDirection.x + layout[0].length) % layout[0].length;
        const ty = (player.y + nextDirection.y + layout.length) % layout.length;
        if (canMove(tx, ty)) {
          direction = nextDirection;
          turnBufferTimer = 0;
        } else {
          turnBufferTimer -= 1;
        }
      }

      const nx = (player.x + direction.x + layout[0].length) % layout[0].length;
      const ny = (player.y + direction.y + layout.length) % layout.length;
      if (canMove(nx, ny)) player = { x: nx, y: ny };

      const key = `${player.x},${player.y}`;
      if (dots.delete(key)) score += 10;
      if (powerDots.delete(key)) {
        score += 25;
        frightened = true;
        frightenedTimer = frightTime;
      }
      updateHighScore();

      for (let i = 0; i < 1 + Math.floor(level / 2); i += 1) moveCops();

      for (let i = 0; i < cops.length; i += 1) {
        if (cops[i].x === player.x && cops[i].y === player.y) {
          if (frightened) {
            cops[i] = { ...copSpawns[i] };
            score += 50;
            updateHighScore();
          } else {
            gameRunning = false;
            updateHighScore();
            updateHelp(`GAME OVER | Score: ${score} | High: ${highScore}`);
            draw();
            return;
          }
        }
      }

      if (frightened) {
        frightenedTimer -= 1;
        if (frightenedTimer <= 0) frightened = false;
      }
      if (dots.size === 0 && powerDots.size === 0) {
        level += 1;
        frightTime = Math.max(30, BASE_FRIGHT_TIME - level * 5);
        layout.forEach((row, y) => row.split("").forEach((cell, x) => {
          if (cell === ".") dots.add(`${x},${y}`);
          if (cell === "o") powerDots.add(`${x},${y}`);
        }));
        cops[0] = { ...copSpawns[0] };
        cops[1] = { ...copSpawns[1] };
        restartCountdown();
        return;
      }
      mouthOpen = !mouthOpen;
      draw();
      loopTimer = setTimeout(step, 110);
    }

    bindGameCleanup(onKey, () => {
      if (loopTimer) clearTimeout(loopTimer);
      if (countdownTimer) clearInterval(countdownTimer);
    });
    draw();
    restartCountdown();
  }

  function runClimber(canvas, help) {
    const ctx = canvas.getContext("2d");
    const WIDTH = 10;
    const HEIGHT = 200;
    const TILE = 20;
    canvas.width = WIDTH * TILE;
    canvas.height = 500;
    let player = { x: WIDTH / 2, y: HEIGHT - 4 };
    let velocityY = 0;
    let velocityX = 0;
    let score = 0;
    let highScore = readStoredNumber(CLIMBER_HIGH_SCORE_KEY);
    let combo = 0;
    let comboTimer = 0;
    let gameRunning = false;
    let cameraY = player.y;
    let waterLevel = HEIGHT + 10;
    let onGround = false;
    let maxHeight = player.y;
    let statusMessage = "";
    const keys = { a: false, d: false, " ": false, space: false };
    const trail = [];
    const platforms = [];
    let rafId = null;
    let countdownTimer = null;

    function generatePlatforms() {
      platforms.length = 0;
      const startY = HEIGHT - 3;
      platforms.push([0, startY, WIDTH, "normal"]);
      let y = startY - 5;
      while (y > 0) {
        const width = 2 + Math.floor(Math.random() * 3);
        const x = Math.floor(Math.random() * (WIDTH - width));
        const type = ["normal", "bounce", "break"][Math.floor(Math.random() * 3)];
        platforms.push([x, y, width, type]);
        y -= 5;
      }
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const offsetY = cameraY * TILE - 250;
      for (let i = 0; i < 25; i += 1) {
        ctx.fillStyle = `rgb(30,30,${40 + i * 4})`;
        ctx.fillRect(0, i * 20, canvas.width, 20);
      }
      platforms.forEach(([x, y, w, type]) => {
        for (let i = 0; i < w; i += 1) {
          const px = (x + i) * TILE;
          const py = y * TILE - offsetY;
          ctx.fillStyle = type === "bounce" ? "#4CAF50" : "#E0E0E0";
          ctx.fillRect(px, py, TILE, TILE);
        }
      });
      trail.forEach(([tx, ty]) => {
        ctx.fillStyle = "#FF8A65";
        ctx.fillRect(tx * TILE + 6, ty * TILE - offsetY + 6, TILE - 12, TILE - 12);
      });
      ctx.fillStyle = "#FF7043";
      ctx.fillRect(player.x * TILE + 2, player.y * TILE - offsetY + 2, TILE - 4, TILE - 4);
      const waterY = waterLevel * TILE - offsetY;
      ctx.fillStyle = "#2979FF";
      ctx.fillRect(0, waterY, canvas.width, canvas.height - waterY);
      if (!gameRunning && statusMessage) {
        help.textContent = statusMessage;
      } else {
        help.textContent = gameRunning
          ? `Score: ${score} | Combo: x${Math.max(combo, 1)} | High: ${highScore}`
          : `DRAIN CLIMBER | High: ${highScore}`;
      }
    }

    function keyDown(event) {
      if (event.key === "a" || event.key === "d" || event.key === " " || event.key === "ArrowLeft" || event.key === "ArrowRight") keys[event.key] = true;
      if (event.code === "Space") keys.space = true;
    }
    function keyUp(event) {
      if (event.key === "a" || event.key === "d" || event.key === " " || event.key === "ArrowLeft" || event.key === "ArrowRight") keys[event.key] = false;
      if (event.code === "Space") keys.space = false;
    }

    function restartCountdown() {
      let countdown = 3;
      gameRunning = false;
      statusMessage = "";
      draw();
      help.textContent = `DRAIN CLIMBER ${countdown}`;
      if (countdownTimer) clearInterval(countdownTimer);
      countdownTimer = setInterval(() => {
        countdown -= 1;
        help.textContent = countdown > 0 ? `DRAIN CLIMBER ${countdown}` : "Go!";
        if (countdown <= 0) {
          clearInterval(countdownTimer);
          countdownTimer = null;
          statusMessage = "";
          gameRunning = true;
          rafId = requestAnimationFrame(step);
        }
      }, 1000);
    }

    function step() {
      if (!gameRunning) return;
      const prevY = player.y;
      if (keys.a || keys.ArrowLeft) velocityX -= 0.4;
      if (keys.d || keys.ArrowRight) velocityX += 0.4;
      velocityX = Math.max(-0.9, Math.min(0.9, velocityX));
      player.x += velocityX;
      if (Math.abs(velocityX) > 0.3 || Math.abs(velocityY) > 1) trail.push([player.x, player.y]);
      if (trail.length > 15) trail.shift();
      player.x = Math.max(0, Math.min(WIDTH - 1, player.x));
      if ((keys.space || keys[" "]) && onGround) {
        velocityY = Math.abs(velocityX) > 0.5 ? -3.25 : -2.5;
        onGround = false;
      }
      velocityY += 0.36;
      player.y += velocityY;
      velocityX *= 0.1;
      onGround = false;
      for (let i = 0; i < platforms.length; i += 1) {
        const [x, y, w, type] = platforms[i];
        if (player.x >= x - 0.2 && player.x <= x + w && prevY <= y - 1 && player.y >= y - 1) {
          player.y = y - 1;
          velocityY = type === "bounce" ? -3.5 : 0;
          onGround = true;
          if (type === "break") {
            platforms.splice(i, 1);
          }
          break;
        }
      }
      cameraY += (player.y - cameraY) * 0.1;
      let highest = Math.min(...platforms.map((p) => p[1]));
      while (highest > player.y - 50) {
        highest -= 5;
        const width = 2 + Math.floor(Math.random() * 3);
        const x = Math.floor(Math.random() * (WIDTH - width));
        const type = ["normal", "bounce"][Math.floor(Math.random() * 2)];
        platforms.push([x, highest, width, type]);
      }
      while (platforms.length && platforms[0][1] > player.y + 30) platforms.shift();
      waterLevel -= 0.05;
      if (player.y < maxHeight) {
        maxHeight = player.y;
        combo += 1;
        comboTimer = 30;
        score = Math.floor((HEIGHT - maxHeight) * (1 + combo * 0.2));
        if (score > highScore) {
          highScore = score;
          writeStoredNumber(CLIMBER_HIGH_SCORE_KEY, highScore);
        }
      }
      if (comboTimer > 0) comboTimer -= 1;
      else combo = 0;
      if (player.y > waterLevel) {
        gameRunning = false;
        statusMessage = `GAME OVER | Score: ${score} | High: ${highScore} | Click Drain Climber to retry.`;
        draw();
        return;
      }
      draw();
      rafId = requestAnimationFrame(step);
    }

    generatePlatforms();
    bindGameCleanup(keyDown, () => {
      window.removeEventListener("keyup", keyUp);
      if (rafId) cancelAnimationFrame(rafId);
      if (countdownTimer) clearInterval(countdownTimer);
    });
    window.addEventListener("keyup", keyUp);
    draw();
    restartCountdown();
  }

  qs("#runButton").addEventListener("click", runPicker);
  qs("#randomButton").addEventListener("click", randomDrain);
  qs("#routeButton").addEventListener("click", buildRoute);
  qs("#linksButton").addEventListener("click", openLinks);
  qs("#addDrainButton").addEventListener("click", openAddDrain);
  if (qs("#syncMapButton")) qs("#syncMapButton").addEventListener("click", syncMap);
  qs("#miniGamesButton").addEventListener("click", openGames);
  qs("#closeModal").addEventListener("click", closeModal);

  modalLayer.addEventListener("click", (event) => {
    if (event.target === modalLayer) closeModal();
  });
  window.addEventListener("pointerdown", unlockAudio, { once: true });
  qs("#closeImagePreview").addEventListener("click", closeImagePreview);
  imagePreviewLayer.addEventListener("click", (event) => {
    if (event.target === imagePreviewLayer) closeImagePreview();
  });

  minDistance.addEventListener("input", syncSliders);
  maxDistance.addEventListener("input", syncSliders);
  searchInput.addEventListener("input", searchDrains);
  searchInput.addEventListener("blur", () => {
    setTimeout(() => {
      searchInput.value = "";
      searchPanel.innerHTML = "";
    }, 120);
  });

  syncSliders();
  fitDesktop();
  setupLoadingDots();
  setupSmiley();
  setupMusic();
  requestLocation();
  window.addEventListener("resize", () => {
    fitDesktop();
    syncSliders();
  });
})();
