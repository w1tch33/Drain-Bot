(function () {
  const state = {
    playlist: [],
    playlistIndex: 0,
    currentDrain: null,
    gameCleanup: null,
    gameLoopCleanup: null,
    mapCleanup: null,
    marqueeX: 0,
    meowTimer: null,
    lastTrackAdvanceKey: "",
  };

  const qs = (selector) => document.querySelector(selector);
  const resultsPanel = qs("#resultsPanel");
  const searchPanel = qs("#searchPanel");
  const loadingOverlay = qs("#loadingOverlay");
  const loadingDots = qs("#loadingDots");
  const visitedCount = qs("#visitedCount");
  const modalLayer = qs("#modalLayer");
  const modalWindow = modalLayer.querySelector(".modal-window");
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
  const onlyUnvisitedToggle = qs("#onlyUnvisited");
  const onlyVisitedToggle = qs("#onlyVisited");
  const themeSelect = qs("#themeSelect");
  const volumeControl = qs("#volumeControl");
  const minDistanceValue = qs("#minDistanceValue");
  const maxDistanceValue = qs("#maxDistanceValue");
  const volumeValue = qs("#volumeValue");
  const notificationsBadge = qs("#notificationsBadge");
  const desktop = qs("#desktop");
  const BASE_WIDTH = 1433;
  const BASE_HEIGHT = 768;
  const DRAIN_MAN_HIGH_SCORE_KEY = "draintool-drainman-high-score";
  const CLIMBER_HIGH_SCORE_KEY = "draintool-drainclimber-high-score";
  const TORCH_SPRINT_HIGH_SCORE_KEY = "draintool-torchsprint-high-score";
  const GAME_LABELS = {
    ladderclimb: "Drain Climber Turbo",
    torchsprint: "Drain Runner",
  };
  const GAME_STORAGE_KEYS = {
    ladderclimb: CLIMBER_HIGH_SCORE_KEY,
    torchsprint: TORCH_SPRINT_HIGH_SCORE_KEY,
  };
  const THEME_STORAGE_KEY = "draintool-theme";
  const THEMES = new Set([
    "mac-system-1",
    "crt-green",
    "pink-noir",
    "blood-red",
    "icy-blue",
    "camcorder-vhs",
    "dr41n",
    "special-chaos",
  ]);
  const THEME_ASSET_MAP = {
    "pink-noir": [
      "/static/themes/envi%27s-crush-assets/envi%27s%20crush%20background.webp",
      "/static/themes/envi%27s-crush-assets/envis-crush-frame-original.png",
    ],
    dr41n: [
      "/static/themes/Dr41n-assets/Background.webp",
      "/static/themes/Dr41n-assets/Dr41n%20hump%20overlay%20cropped.webp",
    ],
    "blood-red": [
      "/static/themes/blood-moon-assets/Background-clear.webp",
      "/static/themes/blood-moon-assets/Frame-opaque-strong.webp",
    ],
    "camcorder-vhs": [
      "/static/themes/vhs-ghost-assets/VHS%20Ghost%20Background.webp",
    ],
    "icy-blue": [
      "/static/themes/frostbyte-assets/frostbyte%20background.webp",
      "/static/themes/frostbyte-assets/frostbyte%20frame.webp",
    ],
  };
  const preloadedThemeAssets = new Set();
  let musicMarqueeTimer = null;
  let audioUnlocked = false;
  let pendingAutoplay = false;
  let fadeToken = 0;
  let meowPrimed = false;
  let searchTimer = null;
  let searchAbortController = null;

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
    const activeTheme = document.documentElement.getAttribute("data-theme") || "mac-system-1";
    const themeScale = activeTheme === "camcorder-vhs" ? 0.95 : 1;
    const scale = Math.min(window.innerWidth / BASE_WIDTH, window.innerHeight / BASE_HEIGHT, 1) * themeScale;
    desktop.style.transform = activeTheme === "camcorder-vhs"
      ? `translateY(-48px) scale(${scale})`
      : `scale(${scale})`;
  }

  function applyTheme(themeName) {
    if (themeName === "sunset-haze" || themeName === "ancient-scripts") themeName = "mac-system-1";
    const theme = THEMES.has(themeName) ? themeName : "mac-system-1";
    if (theme === "mac-system-1") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", theme);
    }
    if (themeSelect && themeSelect.value !== theme) {
      themeSelect.value = theme;
    }
    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch (_error) {
      // Ignore storage failures (private mode, blocked storage).
    }
    preloadThemeAssets(theme);
    fitDesktop();
  }

  function preloadThemeAssets(theme) {
    const assets = THEME_ASSET_MAP[theme] || [];
    for (const src of assets) {
      if (preloadedThemeAssets.has(src)) continue;
      const img = new Image();
      img.src = src;
      img.decoding = "async";
      img.fetchPriority = "high";
      preloadedThemeAssets.add(src);
    }
  }

  function setupThemes() {
    const castleImage = new Image();
    castleImage.src = "/static/themes/blood-moon-castle.webp";
    castleImage.fetchPriority = "high";
    castleImage.decoding = "async";
    const dr41nBackground = new Image();
    dr41nBackground.src = "/static/themes/Drain_Theme_Background.png?v=20260415b";
    dr41nBackground.fetchPriority = "high";
    dr41nBackground.decoding = "async";
    let storedTheme = "mac-system-1";
    try {
      storedTheme = localStorage.getItem(THEME_STORAGE_KEY) || "mac-system-1";
    } catch (_error) {
      storedTheme = "mac-system-1";
    }
    applyTheme(storedTheme);
    if (themeSelect) {
      themeSelect.addEventListener("change", () => applyTheme(themeSelect.value));
    }
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
      only_unvisited: onlyUnvisitedToggle.checked ? "1" : "0",
      only_visited: onlyVisitedToggle.checked ? "1" : "0",
      session_type: "long",
    });
  }

  function syncVisitFilters(changed) {
    if (changed === "unvisited" && onlyUnvisitedToggle.checked) {
      onlyVisitedToggle.checked = false;
    }
    if (changed === "visited" && onlyVisitedToggle.checked) {
      onlyUnvisitedToggle.checked = false;
    }
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const text = await response.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_error) {
      throw new Error("The server returned a non-JSON response. Try refreshing the page.");
    }
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

  function showPopupMessage(message, isError = false) {
    let stack = qs("#clientFlashStack");
    if (!stack) {
      stack = document.createElement("div");
      stack.id = "clientFlashStack";
      stack.className = "flash-stack";
      document.body.appendChild(stack);
    }

    const item = document.createElement("div");
    item.className = `flash-message client-flash ${isError ? "client-flash-error" : ""}`;
    item.innerHTML = `
      <span>${escapeHtml(message)}</span>
      <button class="retro-button client-flash-close" type="button">X</button>
    `;
    const closeButton = item.querySelector(".client-flash-close");
    closeButton.addEventListener("click", () => item.remove());
    stack.appendChild(item);
  }

  function setNotificationsBadge(count) {
    if (!notificationsBadge) return;
    const unread = Math.max(0, Number(count || 0));
    notificationsBadge.textContent = unread > 99 ? "99+" : String(unread);
    notificationsBadge.classList.toggle("hidden", unread <= 0);
  }

  function notificationTimeLabel(ts) {
    const seconds = Math.max(0, Math.round(Date.now() / 1000 - Number(ts || 0)));
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  }

  function notificationsHtml(payload) {
    const rows = (payload.items || [])
      .filter((item) => !item.read)
      .filter((item) => !String(item.message || "").toLowerCase().startsWith("new high score in "))
      .map(
        (item) => `
          <div class="notification-item ${item.read ? "" : "unread"}" data-id="${escapeHtml(item.id)}">
            <div class="notification-text">${escapeHtml(item.message)}</div>
            <div class="notification-meta">${escapeHtml(notificationTimeLabel(item.ts))}</div>
          </div>
        `
      )
      .join("");
    return `
      <div class="auth-links">
        <button class="retro-button" id="markAllNotificationsRead" type="button">Mark All Read</button>
      </div>
      <div class="notifications-list">${rows || '<div class="notification-item"><div class="notification-text">No notifications yet.</div></div>'}</div>
    `;
  }

  function visibleNotificationCount(payload) {
    return (payload.items || [])
      .filter((item) => !item.read)
      .filter((item) => !String(item.message || "").toLowerCase().startsWith("new high score in "))
      .length;
  }

  function activityHtml(payload) {
    const viewer = String(payload.viewer || "");
    const rows = (payload.items || [])
      .map((item) => {
        const actor = String(item.actor || "").trim();
        const actorLabel = actor && actor === viewer ? "You" : actor || "Someone";
        return `
          <div class="notification-item">
            <div class="notification-text"><strong>${escapeHtml(actorLabel)}</strong>: ${escapeHtml(item.message || "")}</div>
            <div class="notification-meta">${escapeHtml(notificationTimeLabel(item.ts))}</div>
          </div>
        `;
      })
      .join("");
    return `
      <div class="profile-section">
        <div class="profile-heading">Friend Activity</div>
      </div>
      <div class="notifications-list">${rows || '<div class="notification-item"><div class="notification-text">No activity yet.</div></div>'}</div>
    `;
  }

  async function refreshNotifications() {
    try {
      const payload = await fetchJson("/api/notifications");
      setNotificationsBadge(visibleNotificationCount(payload));
      return payload;
    } catch (_error) {
      return null;
    }
  }

  async function openNotifications() {
    setLoading(true);
    try {
      const payload = await fetchJson("/api/notifications");
      setNotificationsBadge(visibleNotificationCount(payload));
      openModal("Notifications", notificationsHtml(payload));
      const markReadButton = qs("#markAllNotificationsRead");
      if (markReadButton) {
        markReadButton.addEventListener("click", async () => {
          const updated = await fetchJson("/api/notifications/read", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids: [] }),
          });
          setNotificationsBadge(visibleNotificationCount(updated));
          openModal("Notifications", notificationsHtml(updated));
        });
      }
    } catch (error) {
      drawMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function openActivity() {
    setLoading(true);
    try {
      const payload = await fetchJson("/api/activity?limit=100");
      openModal("Activity Feed", activityHtml(payload));
    } catch (error) {
      drawMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  function visitedListHtml(rows) {
    if (!rows || !rows.length) {
      return '<div class="profile-copy">No visited drains yet.</div>';
    }
    return `
      <div class="profile-section">
        <div class="profile-heading">Visited Drains</div>
        <div class="profile-list">
          ${rows
            .map(
              (row) => `
                <button class="retro-button result-item visited-open" type="button" data-name="${escapeHtml(row.name)}">
                  <span class="result-line">${escapeHtml(row.name)} (${Number(row.distance_km).toFixed(1)} km)</span>
                </button>
              `
            )
            .join("")}
        </div>
      </div>
    `;
  }

  async function openVisitedDrains() {
    setLoading(true);
    try {
      const rows = await fetchJson("/api/visited");
      openModal("Drains Completed", visitedListHtml(rows));
      modalBody.querySelectorAll(".visited-open").forEach((button) => {
        bindPress(button, async () => {
          const targetName = button.dataset.name;
          await openDrain(targetName);
        });
      });
    } catch (error) {
      drawMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  function mapPopupHtml(row) {
    const stateText = row.visited ? "Visited" : "Unvisited";
    const distance = Number(row.distance_km || 0).toFixed(1);
    return `
      <div class="map-popup-title">${escapeHtml(row.name)}</div>
      <div>${escapeHtml(stateText)} • ${distance} km</div>
      <button class="retro-button map-open-drain" type="button" data-name="${escapeHtml(row.name)}">Open Drain</button>
    `;
  }

  async function openMapPanel(focusDrainName = "") {
    setLoading(true);
    try {
      const rows = await fetchJson("/api/map-drains");
      openModal(
        "Drain Map",
        `
          <div class="map-shell">
            <div class="map-toolbar">
              <span><span class="map-dot visited"></span>Visited</span>
              <span><span class="map-dot unvisited"></span>Unvisited</span>
              <span>${rows.length} drains</span>
              <button class="retro-button" id="mapLocateButton" type="button">My Location</button>
              <button class="retro-button" id="mapStyleToggleButton" type="button">Satellite</button>
              <button class="retro-button" id="mapLabelsToggleButton" type="button">Labels On</button>
            </div>
            <div class="map-view" id="drainMapView"></div>
            <div class="profile-copy" id="mapStatusText"></div>
          </div>
        `
      );

      if (!window.L) {
        modalBody.innerHTML = `<div class="profile-copy">Map library failed to load. Refresh and try again.</div>`;
        return;
      }
      const mapEl = modalBody.querySelector("#drainMapView");
      if (!mapEl) return;
      const locateButton = modalBody.querySelector("#mapLocateButton");
      const styleButton = modalBody.querySelector("#mapStyleToggleButton");
      const labelsButton = modalBody.querySelector("#mapLabelsToggleButton");
      const mapStatus = modalBody.querySelector("#mapStatusText");

      const map = L.map(mapEl, { zoomControl: true, preferCanvas: true, maxZoom: 22 });
      const streetLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        maxNativeZoom: 19,
        detectRetina: true,
        attribution: "&copy; OpenStreetMap",
      });
      const satelliteLayer = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 22,
        maxNativeZoom: 19,
        detectRetina: true,
        attribution: "Tiles &copy; Esri",
      });
      const labelsLayer = L.tileLayer("https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png", {
        maxZoom: 22,
        detectRetina: true,
        subdomains: "abcd",
        attribution: "&copy; OpenStreetMap &copy; CARTO",
      });
      let usingSatellite = false;
      let labelsEnabled = true;
      streetLayer.addTo(map);
      labelsLayer.addTo(map);
      map.setView([-37.8136, 144.9631], 11);

      const markers = [];
      const markerByName = new Map();
      rows.forEach((row) => {
        if (!Number.isFinite(row.lat) || !Number.isFinite(row.lon)) return;
        const markerIcon = L.divIcon({
          className: "map-pin-wrap",
          html: `
            <div class="map-pin-label">${escapeHtml(row.name)}</div>
            <div class="map-pin-marker ${row.visited ? "visited" : "unvisited"}"></div>
          `,
          iconSize: [160, 42],
          iconAnchor: [80, 38],
          popupAnchor: [0, -34],
        });
        const marker = L.marker([row.lat, row.lon], { icon: markerIcon });
        marker.bindPopup(mapPopupHtml(row));
        marker.addTo(map);
        markerByName.set(String(row.name || ""), marker);
        marker.on("popupopen", (event) => {
          const button = event.popup.getElement()?.querySelector(".map-open-drain");
          if (!button) return;
          bindPress(button, async () => {
            await openDrain(button.dataset.name || "");
          });
        });
        markers.push(marker);
      });

      if (focusDrainName) {
        const targetMarker = markerByName.get(String(focusDrainName));
        if (targetMarker) {
          const latLng = targetMarker.getLatLng();
          map.setView(latLng, 15);
          setTimeout(() => targetMarker.openPopup(), 80);
        }
      }

      if (styleButton) {
        bindPress(styleButton, () => {
          usingSatellite = !usingSatellite;
          if (usingSatellite) {
            if (map.hasLayer(streetLayer)) map.removeLayer(streetLayer);
            satelliteLayer.addTo(map);
            styleButton.textContent = "Street";
            if (mapStatus) mapStatus.textContent = "Satellite view on.";
          } else {
            if (map.hasLayer(satelliteLayer)) map.removeLayer(satelliteLayer);
            streetLayer.addTo(map);
            styleButton.textContent = "Satellite";
            if (mapStatus) mapStatus.textContent = "Street map view on.";
          }
        });
      }

      if (labelsButton) {
        bindPress(labelsButton, () => {
          labelsEnabled = !labelsEnabled;
          if (labelsEnabled) {
            labelsLayer.addTo(map);
            labelsButton.textContent = "Labels On";
            if (mapStatus) mapStatus.textContent = usingSatellite ? "Satellite + labels." : "Street + labels.";
          } else {
            if (map.hasLayer(labelsLayer)) map.removeLayer(labelsLayer);
            labelsButton.textContent = "Labels Off";
            if (mapStatus) mapStatus.textContent = usingSatellite ? "Satellite without labels." : "Street without labels.";
          }
        });
      }

      let locationMarker = null;
      if (locateButton) {
        bindPress(locateButton, () => {
          if (!navigator.geolocation) {
            if (mapStatus) mapStatus.textContent = "Location not supported on this device/browser.";
            return;
          }
          if (mapStatus) mapStatus.textContent = "Finding your location...";
          navigator.geolocation.getCurrentPosition(
            (position) => {
              const lat = position.coords.latitude;
              const lon = position.coords.longitude;
              map.flyTo([lat, lon], Math.max(map.getZoom(), 14));
              if (locationMarker) {
                locationMarker.setLatLng([lat, lon]);
              } else {
                locationMarker = L.circleMarker([lat, lon], {
                  radius: 7,
                  color: "#0d47a1",
                  weight: 2,
                  fillColor: "#42a5f5",
                  fillOpacity: 0.95,
                }).addTo(map);
              }
              if (mapStatus) mapStatus.textContent = "Centered on your location.";
            },
            () => {
              if (mapStatus) mapStatus.textContent = "Couldn't access your location.";
            },
            { enableHighAccuracy: true, timeout: 9000, maximumAge: 120000 }
          );
        });
      }

      setTimeout(() => map.invalidateSize(), 40);
      state.mapCleanup = () => {
        map.remove();
      };
    } catch (error) {
      drawMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  function highScoreEntries(highScores) {
    return Object.values(highScores || {})
      .sort((left, right) => left.label.localeCompare(right.label))
      .map(
        (entry) => `
          <div class="profile-row profile-score-row">
            <span>${escapeHtml(entry.label)}</span>
            <span>${Number(entry.score || 0)}</span>
          </div>
        `
      )
      .join("");
  }

  async function syncHighScore(game, score) {
    try {
      const payload = await fetchJson("/api/high-scores", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ game, score }),
      });
      const completed = payload.completed_challenges || [];
      if (completed.length) {
        const first = completed[0];
        showPopupMessage(`Challenge complete: ${first.label} ${first.target}`);
      }
      return payload;
    } catch (_error) {
      // Keep local scores even if account sync fails.
      return null;
    }
  }

  async function syncStoredHighScores() {
    try {
      const profile = await fetchJson("/api/profile");
      const localScores = Object.fromEntries(
        Object.entries(GAME_STORAGE_KEYS).map(([gameKey, storageKey]) => [gameKey, readStoredNumber(storageKey)])
      );
      const remoteScores = Object.fromEntries(
        Object.keys(GAME_STORAGE_KEYS).map((gameKey) => [gameKey, Number(profile.high_scores?.[gameKey]?.score || 0)])
      );
      Object.entries(GAME_STORAGE_KEYS).forEach(([gameKey, storageKey]) => {
        writeStoredNumber(storageKey, Math.max(localScores[gameKey], remoteScores[gameKey]));
      });

      const uploads = [];
      Object.keys(GAME_STORAGE_KEYS).forEach((gameKey) => {
        if (localScores[gameKey] > remoteScores[gameKey]) {
          uploads.push(syncHighScore(gameKey, localScores[gameKey]));
        }
      });
      await Promise.all(uploads);
    } catch (_error) {
      // Keep local score fallback if account score sync fails.
    }
  }

  function progressionHtml(progression, compact = false) {
    const rank = progression?.rank || {};
    const streaks = progression?.streaks || {};
    const seasonal = progression?.seasonal || {};
    const badges = (progression?.badges || []);
    const topBadges = badges.filter((badge) => badge.earned).slice(0, compact ? 3 : 6);
    const badgeRows = topBadges
      .map((badge) => `<span class="badge-pill">${escapeHtml(badge.label)}</span>`)
      .join("");

    const challengeRows = compact
      ? ""
      : (seasonal.challenges || [])
          .map(
            (challenge) => `
              <div class="profile-row profile-score-row">
                <span>${escapeHtml(challenge.label)}</span>
                <span>${Number(challenge.progress || 0)}/${Number(challenge.target || 0)}</span>
              </div>
            `
          )
          .join("");

    return `
      <div class="profile-mini-heading">Progression</div>
      <div class="profile-copy">Rank: ${escapeHtml(rank.name || "Rookie")} (${Number(rank.xp || 0)} XP)</div>
      <div class="profile-copy">Visit Streak: ${Number(streaks.current || 0)} day(s) | Best: ${Number(streaks.longest || 0)}</div>
      <div class="profile-copy">Seasonal: ${Number(seasonal.completed || 0)}/${Number(seasonal.total || 0)} complete</div>
      ${badgeRows ? `<div class="badge-grid">${badgeRows}</div>` : '<div class="profile-copy">No badges yet.</div>'}
      ${challengeRows ? `<div class="profile-list profile-score-list">${challengeRows}</div>` : ""}
    `;
  }

  function profileHtml(profile) {
    const incoming = (profile.incoming_requests || [])
      .map(
        (request) => `
          <div class="profile-row">
            <span>${escapeHtml(request.username)}</span>
            <button class="retro-button accept-friend-button" type="button" data-username="${escapeHtml(request.username)}">Accept</button>
          </div>
        `
      )
      .join("");

    const outgoing = (profile.outgoing_requests || [])
      .map((request) => `<div class="profile-copy">Pending: ${escapeHtml(request.username)}</div>`)
      .join("");

    const friends = (profile.friends || [])
      .map(
        (friend) => `
          <div class="profile-card">
            <div class="profile-card-info">
              <div class="profile-name">${escapeHtml(friend.username)}</div>
              <div class="profile-copy">Drains: ${friend.stats.total}</div>
              <div class="profile-copy">Visited: ${friend.stats.visited}</div>
              ${progressionHtml(friend.progression, true)}
              <div class="profile-mini-heading">High Scores</div>
              <div class="profile-list profile-score-list">${highScoreEntries(friend.high_scores) || "<div class=\"profile-copy\">No scores yet.</div>"}</div>
            </div>
            <button class="retro-button remove-friend-button" type="button" data-username="${escapeHtml(friend.username)}">Remove Friend</button>
          </div>
        `
      )
      .join("");

    return `
      <div class="profile-section">
        <div class="profile-name">${escapeHtml(profile.username)}</div>
        <div class="profile-copy">Drains: ${profile.stats.total}</div>
        <div class="profile-copy">Visited: ${profile.stats.visited}</div>
      </div>
      <div class="profile-section">
        <div class="profile-heading">Badges & Progression</div>
        ${progressionHtml(profile.progression)}
      </div>
      <div class="profile-section">
        <div class="profile-heading">Friends</div>
        <div class="profile-list">${friends || "<div class=\"profile-copy\">No friends yet.</div>"}</div>
      </div>
      <div class="profile-section">
        <div class="profile-heading">Add Friend</div>
        <form class="modal-form" id="friendRequestForm">
          <input class="retro-input" name="username" placeholder="username" required>
          <button class="retro-button" type="submit">Send Request</button>
        </form>
        ${outgoing || ""}
      </div>
      <div class="profile-section">
        <div class="profile-heading">Friend Requests</div>
        <div class="profile-list">${incoming || "<div class=\"profile-copy\">No incoming requests.</div>"}</div>
      </div>
      <div class="profile-section">
        <div class="profile-heading">High Scores</div>
        <div class="profile-list profile-score-list">${highScoreEntries(profile.high_scores) || "<div class=\"profile-copy\">No scores yet.</div>"}</div>
      </div>
      <div class="profile-section">
        <div class="profile-heading">Friend Challenges</div>
        <form class="modal-form" id="profileChallengeForm">
          <input class="retro-input" name="username" placeholder="friend username" required>
          <select class="retro-input" name="game">
            ${Object.entries(GAME_LABELS).map(([key, label]) => `<option value="${escapeHtml(key)}">${escapeHtml(label)}</option>`).join("")}
          </select>
          <input class="retro-input" name="target" type="number" min="1" step="1" placeholder="target score" required>
          <button class="retro-button" type="submit">Send Challenge</button>
        </form>
        <div class="profile-mini-heading">Incoming</div>
        <div class="profile-list profile-score-list">
          ${(profile.game_challenges?.incoming || []).map((item) => `<div class="profile-row profile-score-row"><span>${escapeHtml(item.from)} • ${escapeHtml(item.label)}</span><span>${Number(item.target)}</span></div>`).join("") || "<div class=\"profile-copy\">No incoming challenges.</div>"}
        </div>
        <div class="profile-mini-heading">Outgoing</div>
        <div class="profile-list profile-score-list">
          ${(profile.game_challenges?.outgoing || []).map((item) => `<div class="profile-row profile-score-row"><span>To ${escapeHtml(item.to)} • ${escapeHtml(item.label)}</span><span>${Number(item.target)}</span></div>`).join("") || "<div class=\"profile-copy\">No outgoing challenges.</div>"}
        </div>
      </div>
    `;
  }

  async function openProfile() {
    setLoading(true);
    try {
      await syncStoredHighScores();
      const profile = await fetchJson("/api/profile");
      openModal(`${profile.username} Profile`, profileHtml(profile));
      const friendRequestForm = modalBody.querySelector("#friendRequestForm");
      if (friendRequestForm) {
        friendRequestForm.addEventListener("submit", async (event) => {
          event.preventDefault();
          const formData = new FormData(event.currentTarget);
          try {
            await fetchJson("/api/friends/request", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ username: formData.get("username") }),
            });
            showPopupMessage(`Friend request sent to ${formData.get("username")}.`);
            await openProfile();
          } catch (error) {
            showPopupMessage(error.message, true);
          }
        });
      }

      modalBody.querySelectorAll(".accept-friend-button").forEach((button) => {
        button.addEventListener("click", async () => {
          await fetchJson(`/api/friends/accept/${encodeURIComponent(button.dataset.username)}`, {
            method: "POST",
          });
          showPopupMessage(`You are now friends with ${button.dataset.username}.`);
          await openProfile();
        });
      });

      modalBody.querySelectorAll(".remove-friend-button").forEach((button) => {
        button.addEventListener("click", async () => {
          await fetchJson(`/api/friends/remove/${encodeURIComponent(button.dataset.username)}`, {
            method: "POST",
          });
          showPopupMessage(`Removed ${button.dataset.username} from your friends.`);
          await openProfile();
        });
      });

      const profileChallengeForm = modalBody.querySelector("#profileChallengeForm");
      if (profileChallengeForm) {
        profileChallengeForm.addEventListener("submit", async (event) => {
          event.preventDefault();
          const formData = new FormData(event.currentTarget);
          try {
            await fetchJson("/api/challenges/request", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                username: formData.get("username"),
                game: formData.get("game"),
                target: Number(formData.get("target") || 0),
              }),
            });
            showPopupMessage(`Challenge sent to ${formData.get("username")}.`);
            await openProfile();
          } catch (error) {
            showPopupMessage(error.message, true);
          }
        });
      }
    } catch (error) {
      drawMessage(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function searchDrains(queryText = searchInput.value.trim()) {
    const query = String(queryText || "").trim();
    if (!query) {
      searchPanel.innerHTML = "";
      return;
    }
    if (query.length < 2) {
      searchPanel.innerHTML = "<div>Type at least 2 letters.</div>";
      return;
    }
    if (searchAbortController) searchAbortController.abort();
    searchAbortController = new AbortController();
    searchPanel.innerHTML = "<div>Searching...</div>";
    try {
      const rows = await fetchJson(
        `/api/search?q=${encodeURIComponent(query)}&only_unvisited=${onlyUnvisitedToggle.checked ? "1" : "0"}&only_visited=${onlyVisitedToggle.checked ? "1" : "0"}`,
        { signal: searchAbortController.signal }
      );
      searchPanel.innerHTML = "";
      rows.forEach((row) => searchPanel.appendChild(resultButton(row)));
    } catch (error) {
      if (error.name === "AbortError") return;
      searchPanel.textContent = error.message;
    }
  }

  function openModal(title, content) {
    modalTitle.innerHTML = `<span>${escapeHtml(title)}</span>`;
    modalBody.innerHTML = "";
    modalWindow.classList.remove("game-modal-window");
    modalBody.classList.remove("game-modal-body");
    if (typeof content === "string") modalBody.innerHTML = content;
    else modalBody.appendChild(content);
    modalLayer.classList.remove("hidden");
  }

  function closeModal() {
    if (state.mapCleanup) {
      state.mapCleanup();
      state.mapCleanup = null;
    }
    modalLayer.classList.add("hidden");
    modalBody.innerHTML = "";
    modalWindow.classList.remove("game-modal-window");
    modalBody.classList.remove("game-modal-body");
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
        fadeInToTarget(Number(volumeControl.value), 420);
      }
      return;
    }
    audioUnlocked = true;
    if (audioPlayer.muted && !audioPlayer.paused) {
      audioPlayer.muted = false;
      fadeInToTarget(Number(volumeControl.value), 420);
      return;
    }
    if (pendingAutoplay) {
      pendingAutoplay = false;
      startPlaybackAt(state.playlistIndex, true, false, false);
    }
    primeMeowAudio();
  }

  function primeMeowAudio() {
    if (meowPrimed || !meowPlayer) return;
    meowPrimed = true;
    meowPlayer.preload = "auto";
    meowPlayer.load();
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

  function bindPress(element, handler) {
    if (!element) return;
    let lastTouchAt = 0;
    let touchStartX = 0;
    let touchStartY = 0;
    let touchMoved = false;
    const MOVE_THRESHOLD = 10;
    const onTouchStart = (event) => {
      const touch = event.changedTouches && event.changedTouches[0];
      touchStartX = touch ? touch.clientX : 0;
      touchStartY = touch ? touch.clientY : 0;
      touchMoved = false;
    };
    const onTouchMove = (event) => {
      const touch = event.changedTouches && event.changedTouches[0];
      if (!touch) return;
      if (Math.abs(touch.clientX - touchStartX) > MOVE_THRESHOLD || Math.abs(touch.clientY - touchStartY) > MOVE_THRESHOLD) {
        touchMoved = true;
      }
    };
    const onTouchEnd = (event) => {
      lastTouchAt = Date.now();
      if (touchMoved) return;
      event.preventDefault();
      handler(event);
    };
    const onClick = (event) => {
      if (Date.now() - lastTouchAt < 500) {
        event.preventDefault();
        return;
      }
      handler(event);
    };
    element.addEventListener("touchstart", onTouchStart, { passive: true });
    element.addEventListener("touchmove", onTouchMove, { passive: true });
    element.addEventListener("touchend", onTouchEnd, { passive: false });
    element.addEventListener("click", onClick);
  }

  async function compressImageUpload(file) {
    if (!(file instanceof File)) return null;
    if (!file.type.startsWith("image/")) return null;
    if (file.size <= 1_300_000) return null;
    if (typeof createImageBitmap !== "function") return null;
    try {
      const bitmap = await createImageBitmap(file);
      const maxSide = 1600;
      const ratio = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(bitmap.width * ratio));
      canvas.height = Math.max(1, Math.round(bitmap.height * ratio));
      const ctx = canvas.getContext("2d", { alpha: false });
      ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      bitmap.close();
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.78));
      if (!blob || blob.size >= file.size) return null;
      const safeName = (file.name || "photo").replace(/\.[^.]+$/, "");
      return { file: blob, name: `${safeName}.jpg` };
    } catch (_error) {
      return null;
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

    const features = [
      "Junction",
      "Split",
      "Slide",
      "Grille Room",
      "Chamber",
      "Waterfall",
      "Side-Pipe",
      "Stations",
      "Size Change",
      "Steps",
      "Overflow",
      "Redbrick",
      "Bluestone",
    ];
    const shapes = [
      "Round Pipe",
      "Square",
      "Rectangle",
      "Balloon",
      "Mummy",
      "Arch",
      "Slope-Bottom Arch",
      "Hallway",
      "Mushroom",
    ];
    const showDelete = drain.source === "custom" || drain.source === "synced";

    return `
      <div class="detail-section detail-name-section">
        <label>Drain Name</label>
        <input class="retro-input" id="nameField" type="text" value="${escapeHtml(drain.name || "")}">
      </div>
      <div class="detail-section detail-actions">
        <button class="retro-button" type="button" id="nearbyButton">Nearby</button>
        <button class="retro-button" type="button" id="routeFromHereButton">Build Route</button>
        <button class="retro-button" type="button" id="showOnMapButton">Show On Map</button>
        ${showDelete ? '<button class="retro-button" type="button" id="deleteDrainButton">Delete Drain</button>' : ""}
      </div>
      <div class="detail-section nearby-list" id="nearbyArea"></div>
      <div class="detail-section">
        <label class="check-row"><input id="favoriteField" type="checkbox" ${drain.favorite ? "checked" : ""}><span>Favorite</span></label>
        <label class="check-row"><input id="visitedField" type="checkbox" ${drain.visited ? "checked" : ""}><span>Visited</span></label>
      </div>
      <div class="detail-section"><label>Description</label><textarea class="retro-textarea" id="descriptionField" rows="6">${escapeHtml(drain.description || "")}</textarea></div>
      <div class="detail-section"><label>Notes</label><textarea class="retro-textarea" id="notesField" rows="5">${escapeHtml(drain.notes || "")}</textarea></div>
      <div class="detail-section"><div>FEATURES:</div><div class="feature-grid">${features
        .map(
          (feature) =>
            `<label class="check-row"><input class="featureField" type="checkbox" value="${escapeHtml(feature)}" ${(drain.features || {})[feature] ? "checked" : ""}><span>${escapeHtml(feature)}</span></label>`
        )
        .join("")}</div></div>
      <div class="detail-section"><div>SHAPES:</div><div class="feature-grid">${shapes
        .map(
          (shape) =>
            `<label class="check-row"><input class="featureField" type="checkbox" value="${escapeHtml(shape)}" ${(drain.features || {})[shape] ? "checked" : ""}><span>${escapeHtml(shape)}</span></label>`
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
      <div class="detail-section"><div class="photo-grid">${photos}</div><form id="photoUploadForm" enctype="multipart/form-data"><input class="retro-input" id="photoUploadInput" type="file" name="photo" accept="image/*" multiple><button class="retro-button" type="submit">Add Photos</button></form></div>
      <div class="detail-section"><button class="retro-button" type="button" id="saveDrainButton">Save</button><div class="profile-copy" id="drainSaveStatus"></div></div>
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
    const selectedValue = (selector) => {
      const active = modalBody.querySelector(`${selector}.active`);
      if (!active) return "";
      return active.dataset.value || "";
    };
    const saveStatus = modalBody.querySelector("#drainSaveStatus");
    const nearbyMarkup = (state.currentDrain.nearby || [])
      .map(
        (item) =>
          `<button class="retro-button nearby-open" type="button" data-name="${escapeHtml(item.name)}">${escapeHtml(item.name)} (${Number(item.distance_from_current_km).toFixed(2)} km)</button>`
      )
      .join("");

    const nearbyArea = modalBody.querySelector("#nearbyArea");
    bindPress(modalBody.querySelector("#nearbyButton"), () => {
      nearbyArea.innerHTML = nearbyMarkup || "<span>No nearby drains found.</span>";
      nearbyArea.querySelectorAll(".nearby-open").forEach((button) => {
        bindPress(button, () => openDrain(button.dataset.name));
      });
    });
    bindPress(modalBody.querySelector("#routeFromHereButton"), async () => {
      renderRoute(await fetchJson(`/api/drains/${encodeURIComponent(name)}/route`));
      closeModal();
    });
    bindPress(modalBody.querySelector("#showOnMapButton"), async () => {
      await openMapPanel(name);
    });
    const deleteDrainButton = modalBody.querySelector("#deleteDrainButton");
    if (deleteDrainButton) {
      bindPress(deleteDrainButton, async () => {
        await fetchJson(`/api/drains/${encodeURIComponent(name)}/delete`, { method: "POST" });
        await refreshStats();
        closeModal();
        drawMessage(`Deleted ${name}.`);
      });
    }

    modalBody.querySelectorAll(".difficulty-button").forEach((button) => {
      bindPress(button, () => {
        modalBody.querySelectorAll(".difficulty-button").forEach((item) => item.classList.toggle("active", item === button));
      });
    });

    modalBody.querySelectorAll(".value-button").forEach((button) => {
      bindPress(button, () => {
        modalBody.querySelectorAll(".value-button").forEach((item) => item.classList.toggle("active", item === button));
      });
    });

    modalBody.querySelectorAll(".rating-button").forEach((button) => {
      bindPress(button, () => {
        modalBody.querySelectorAll(".rating-button").forEach((item) => item.classList.toggle("active", item === button));
      });
    });

    function captureDraft() {
      return {
        display_name: modalBody.querySelector("#nameField")?.value || "",
        favorite: modalBody.querySelector("#favoriteField")?.checked || false,
        visited: modalBody.querySelector("#visitedField")?.checked || false,
        description: modalBody.querySelector("#descriptionField")?.value || "",
        notes: modalBody.querySelector("#notesField")?.value || "",
        difficulty: selectedValue(".difficulty-button"),
        value: selectedValue(".value-button"),
        rating: selectedValue(".rating-button"),
        features: Array.from(modalBody.querySelectorAll(".featureField")).reduce((acc, field) => {
          acc[field.value] = field.checked;
          return acc;
        }, {}),
      };
    }

    function restoreDraft(draft) {
      if (!draft) return;
      const favoriteField = modalBody.querySelector("#favoriteField");
      const visitedField = modalBody.querySelector("#visitedField");
      const nameField = modalBody.querySelector("#nameField");
      const descriptionField = modalBody.querySelector("#descriptionField");
      const notesField = modalBody.querySelector("#notesField");
      if (favoriteField) favoriteField.checked = !!draft.favorite;
      if (visitedField) visitedField.checked = !!draft.visited;
      if (nameField) nameField.value = draft.display_name || "";
      if (descriptionField) descriptionField.value = draft.description || "";
      if (notesField) notesField.value = draft.notes || "";
      modalBody.querySelectorAll(".difficulty-button").forEach((button) => button.classList.toggle("active", button.dataset.value === draft.difficulty));
      modalBody.querySelectorAll(".value-button").forEach((button) => button.classList.toggle("active", button.dataset.value === draft.value));
      modalBody.querySelectorAll(".rating-button").forEach((button) => button.classList.toggle("active", button.dataset.value === String(draft.rating || "")));
      modalBody.querySelectorAll(".featureField").forEach((field) => {
        field.checked = !!draft.features?.[field.value];
      });
    }

    modalBody.querySelectorAll(".delete-photo").forEach((button) => {
      bindPress(button, async () => {
        const draft = captureDraft();
        setLoading(true);
        try {
          const formData = new FormData();
          formData.append("path", button.dataset.path);
          await fetchJson(`/api/drains/${encodeURIComponent(name)}/photos/delete`, { method: "POST", body: formData });
          await openDrain(name);
          restoreDraft(draft);
        } finally {
          setLoading(false);
        }
      });
    });

    modalBody.querySelectorAll(".preview-photo").forEach((img) => {
      bindPress(img, () => openImagePreview(img.dataset.title, img.dataset.url));
    });

    modalBody.querySelector("#photoUploadForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const draft = captureDraft();
      setLoading(true);
      try {
        const input = modalBody.querySelector("#photoUploadInput");
        const files = Array.from(input?.files || []);
        if (!files.length) {
          showPopupMessage("Choose at least one photo first.", true);
          return;
        }
        const sendForm = new FormData();
        for (const sourceFile of files) {
          const compressed = await compressImageUpload(sourceFile);
          if (compressed) sendForm.append("photo", compressed.file, compressed.name);
          else sendForm.append("photo", sourceFile);
        }
        await fetchJson(`/api/drains/${encodeURIComponent(name)}/photos`, {
          method: "POST",
          body: sendForm,
        });
        await openDrain(name);
        restoreDraft(draft);
      } finally {
        setLoading(false);
      }
    });

    bindPress(modalBody.querySelector("#saveDrainButton"), async () => {
      const saveButton = modalBody.querySelector("#saveDrainButton");
      saveButton.disabled = true;
      if (saveStatus) saveStatus.textContent = "Saving...";
      setLoading(true);
      try {
        const response = await fetchJson(`/api/drains/${encodeURIComponent(name)}/update`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            display_name: modalBody.querySelector("#nameField").value,
            favorite: modalBody.querySelector("#favoriteField").checked,
            visited: modalBody.querySelector("#visitedField").checked,
            description: modalBody.querySelector("#descriptionField").value,
            notes: modalBody.querySelector("#notesField").value,
            difficulty: selectedValue(".difficulty-button"),
            value: selectedValue(".value-button"),
            rating: Number(selectedValue(".rating-button") || 0) || "",
            features: Array.from(modalBody.querySelectorAll(".featureField")).reduce((acc, field) => {
              acc[field.value] = field.checked;
              return acc;
            }, {}),
          }),
        });
        await refreshStats();
        if (saveStatus) {
          saveStatus.textContent = "Saved!";
          setTimeout(() => {
            if (saveStatus.textContent === "Saved!") saveStatus.textContent = "";
          }, 1500);
        }
        const newName = response?.drain?.name;
        if (newName && newName !== name) {
          await openDrain(newName);
          return;
        }
      } finally {
        setLoading(false);
        saveButton.disabled = false;
      }
    });
  }

  function setupSmiley() {
    if (meowFlash && meowFlash.parentElement !== document.body) {
      document.body.appendChild(meowFlash);
    }
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
    window.setTimeout(primeMeowAudio, 120);
  }

  function setupMusic() {
    state.playlist = JSON.parse(qs("#desktop").dataset.playlist);
    if (!state.playlist.length) return;

    audioPlayer.volume = 0;
    volumeValue.textContent = Number(volumeControl.value).toFixed(2);
    startSongMarquee(state.playlist[0].replace(".mp3", ""));

    function advanceToNextTrack() {
      const currentKey = audioPlayer.currentSrc || audioPlayer.src || "";
      if (currentKey && state.lastTrackAdvanceKey === currentKey) return;
      state.lastTrackAdvanceKey = currentKey;
      startPlaybackAt(state.playlistIndex + 1);
    }

    fadeInToTarget = function (targetVolume, duration = 650) {
      fadeToken += 1;
      const currentFade = fadeToken;
      const startVolume = Number(audioPlayer.volume || 0);
      const steps = 12;
      let step = 0;

      function tick() {
        if (currentFade !== fadeToken) return;
        step += 1;
        const nextVolume = startVolume + ((targetVolume - startVolume) * (step / steps));
        audioPlayer.volume = Math.max(0, Math.min(1, nextVolume));
        if (step < steps && !audioPlayer.paused) {
          window.setTimeout(tick, duration / steps);
        }
      }

      tick();
    };

    startPlaybackAt = function (index, shouldFade = true, preferMutedAutoplay = false, reloadTrack = true) {
      state.lastTrackAdvanceKey = "";
      state.playlistIndex = (index + state.playlist.length) % state.playlist.length;
      const filename = state.playlist[state.playlistIndex];
      const nextSrc = `/audio/${encodeURIComponent(filename)}`;
      if (reloadTrack || audioPlayer.src !== new URL(nextSrc, window.location.href).href) {
        audioPlayer.src = nextSrc;
      }
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
            if (audioUnlocked) {
              audioPlayer.muted = false;
              if (shouldFade) fadeInToTarget(targetVolume, 420);
              else audioPlayer.volume = targetVolume;
            }
          } else if (shouldFade) {
            fadeInToTarget(targetVolume, 420);
          }
        })
        .catch(() => {
          if (!preferMutedAutoplay) {
            // Retry once muted; if that also fails we fall back to unlock-on-input flow.
            startPlaybackAt(state.playlistIndex, shouldFade, true, false);
            return;
          }
          pendingAutoplay = true;
        });
    };

    qs("#prevSong").addEventListener("click", () => startPlaybackAt(state.playlistIndex - 1));
    qs("#nextSong").addEventListener("click", () => startPlaybackAt(state.playlistIndex + 1));
    qs("#toggleSong").addEventListener("click", () => {
      if (!audioPlayer.src) startPlaybackAt(state.playlistIndex);
      else if (audioPlayer.paused) audioPlayer.play().catch(() => {});
      else audioPlayer.pause();
    });

    audioPlayer.addEventListener("ended", advanceToNextTrack);
    audioPlayer.addEventListener("timeupdate", () => {
      if (audioPlayer.paused) return;
      if (!Number.isFinite(audioPlayer.duration) || audioPlayer.duration <= 0) return;
      if (audioPlayer.currentTime < audioPlayer.duration - 0.12) return;
      advanceToNextTrack();
    });
    audioPlayer.addEventListener("error", advanceToNextTrack);
    volumeControl.addEventListener("input", () => {
      audioPlayer.volume = Number(volumeControl.value);
      volumeValue.textContent = Number(volumeControl.value).toFixed(2);
    });

    startPlaybackAt(0, true, true);
    window.setTimeout(() => {
      if (!audioUnlocked && audioPlayer.paused) {
        startPlaybackAt(state.playlistIndex, true, true, false);
      }
    }, 500);
  }

  let fadeInToTarget = () => {};
  let startPlaybackAt = () => {};

  function openLinks() {
    openModal("Helpful Links", qs("#linksTemplate").content.cloneNode(true));
  }

  function openTutorial() {
    openModal("Tutorial", qs("#tutorialTemplate").content.cloneNode(true));
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
    const previousCleanup = state.gameLoopCleanup;
    if (previousCleanup) previousCleanup();
    state.gameLoopCleanup = () => {
      window.removeEventListener("keydown", handler);
      window.removeEventListener("keyup", handler);
      window.removeEventListener("game-control", handler);
      if (extraCleanup) extraCleanup();
    };
    window.addEventListener("keydown", handler);
    window.addEventListener("keyup", handler);
    window.addEventListener("game-control", handler);
  }

  function dispatchGameKey(type, key, code = "", slot = "") {
    const event = new KeyboardEvent(type, {
      key,
      code: code || key,
      bubbles: true,
    });
    window.dispatchEvent(event);
    window.dispatchEvent(
      new CustomEvent("game-control", {
        detail: {
          phase: type === "keydown" ? "down" : "up",
          key,
          code: code || key,
          slot,
        },
      })
    );
  }

  function bindGameControls(container) {
    const cleanups = [];
    container.querySelectorAll(".game-control").forEach((button) => {
      const slot = button.dataset.controlSlot || "";
      const press = (event) => {
        if (event) event.preventDefault();
        button.blur();
        dispatchGameKey("keydown", button.dataset.key || "", button.dataset.code || button.dataset.key || "", slot);
      };
      const release = (event) => {
        if (event) event.preventDefault();
        dispatchGameKey("keyup", button.dataset.key || "", button.dataset.code || button.dataset.key || "", slot);
      };

      button.addEventListener("pointerdown", press);
      button.addEventListener("pointerup", release);
      button.addEventListener("pointercancel", release);
      button.addEventListener("pointerleave", release);
      button.addEventListener("touchstart", press, { passive: false });
      button.addEventListener("touchend", release, { passive: false });
      button.addEventListener("touchcancel", release, { passive: false });
      cleanups.push(() => {
        button.removeEventListener("pointerdown", press);
        button.removeEventListener("pointerup", release);
        button.removeEventListener("pointercancel", release);
        button.removeEventListener("pointerleave", release);
        button.removeEventListener("touchstart", press);
        button.removeEventListener("touchend", release);
        button.removeEventListener("touchcancel", release);
      });
    });
    return () => cleanups.forEach((cleanup) => cleanup());
  }

  function configureGameControls(container, config = {}) {
    const buttons = {
      up: container.querySelector('[data-control-slot="up"]'),
      left: container.querySelector('[data-control-slot="left"]'),
      action: container.querySelector('[data-control-slot="action"]'),
      right: container.querySelector('[data-control-slot="right"]'),
      down: container.querySelector('[data-control-slot="down"]'),
    };
    Object.entries(buttons).forEach(([slot, button]) => {
      if (!button) return;
      const next = config[slot];
      if (!next) {
        button.classList.add("hidden");
        return;
      }
      button.classList.remove("hidden");
      button.textContent = next.label || button.textContent;
      button.dataset.key = next.key || "";
      button.dataset.code = next.code || next.key || "";
    });
  }

  function leaderboardHtml(payload = {}) {
    const rows = (payload.items || [])
      .map(
        (row) => `
          <div class="profile-row profile-score-row">
            <span>#${Number(row.rank)} ${escapeHtml(row.username)}</span>
            <span>${Number(row.score)}</span>
          </div>
        `
      )
      .join("");
    const viewer = payload.viewer_rank
      ? `<div class="profile-copy">You: #${Number(payload.viewer_rank.rank)} (${Number(payload.viewer_rank.score)})</div>`
      : '<div class="profile-copy">You are unranked. Beat a score to appear.</div>';
    return `
      ${rows || '<div class="profile-copy">No scores yet.</div>'}
      ${viewer}
    `;
  }

  async function loadGameLeaderboard(gameKey, leaderboardEl) {
    if (!leaderboardEl || !gameKey) return;
    leaderboardEl.innerHTML = '<div class="profile-copy">Loading leaderboard...</div>';
    try {
      const payload = await fetchJson(`/api/leaderboard?game=${encodeURIComponent(gameKey)}&limit=12`);
      leaderboardEl.innerHTML = leaderboardHtml(payload);
    } catch (error) {
      leaderboardEl.innerHTML = `<div class="profile-copy">${escapeHtml(error.message)}</div>`;
    }
  }

  function openGames() {
    openModal("Mini Games", qs("#miniGamesTemplate").content.cloneNode(true));
    modalWindow.classList.add("game-modal-window");
    modalBody.classList.add("game-modal-body");
    const canvas = qs("#gameCanvas");
    const help = qs("#gameHelp");
    const controls = qs("#gameControls");
    const leaderboard = qs("#gameLeaderboard");
    const challengeForm = qs("#gameChallengeForm");
    const challengeHint = qs("#gameChallengeHint");
    const menu = modalBody.querySelector(".game-menu-list");
    const sidePanel = modalBody.querySelector(".game-side-panel");
    canvas.tabIndex = 0;
    const cleanupControls = bindGameControls(controls);
    canvas.classList.add("hidden");
    help.classList.add("hidden");
    controls.classList.add("hidden");
    help.textContent = "Pick a game.";
    let activeGame = "";
    const challengeTargetInput = challengeForm?.querySelector('input[name="target"]');
    const setDefaultTarget = (gameKey) => {
      if (!challengeTargetInput) return;
      challengeTargetInput.value = gameKey === "ladderclimb" ? "500" : "120";
    };

    const launchGame = (gameKey) => {
      activeGame = gameKey;
      canvas.classList.remove("hidden");
      help.classList.remove("hidden");
      controls.classList.remove("hidden");
      if (menu) menu.classList.add("hidden");
      if (sidePanel) sidePanel.classList.add("hidden");
      canvas.focus();
      if (state.gameLoopCleanup) {
        state.gameLoopCleanup();
        state.gameLoopCleanup = null;
      }
      if (gameKey === "ladderclimb") {
        configureGameControls(controls, {
          left: { label: "LEFT", key: "ArrowLeft" },
          action: { label: "JUMP", key: "Space", code: "Space" },
          right: { label: "RIGHT", key: "ArrowRight" },
        });
        runLadderClimb(canvas, help, () => loadGameLeaderboard(gameKey, leaderboard));
      } else {
        configureGameControls(controls, {
          left: { label: "LEFT", key: "ArrowLeft" },
          action: { label: "BOOST", key: "ArrowUp" },
          right: { label: "RIGHT", key: "ArrowRight" },
        });
        runTorchSprint(canvas, help, () => loadGameLeaderboard(gameKey, leaderboard));
      }
      loadGameLeaderboard(gameKey, leaderboard);
      if (challengeHint) {
        challengeHint.textContent = `Send a ${GAME_LABELS[gameKey]} challenge to a friend.`;
      }
      setDefaultTarget(gameKey);
    };

    modalBody.querySelectorAll(".game-button").forEach((button) => {
      button.addEventListener("click", () => {
        button.blur();
        launchGame(button.dataset.game || "");
      });
    });

    if (challengeForm) {
      challengeForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!activeGame) {
          showPopupMessage("Pick a game before sending a challenge.", true);
          return;
        }
        const formData = new FormData(event.currentTarget);
        try {
          await fetchJson("/api/challenges/request", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              username: formData.get("username"),
              game: activeGame,
              target: Number(formData.get("target") || 0),
            }),
          });
          showPopupMessage(`Challenge sent to ${formData.get("username")}.`);
        } catch (error) {
          showPopupMessage(error.message, true);
        }
      });
    }

    const previousCleanup = state.gameCleanup;
    state.gameCleanup = () => {
      cleanupControls();
      if (state.gameLoopCleanup) {
        state.gameLoopCleanup();
        state.gameLoopCleanup = null;
      }
      if (previousCleanup) previousCleanup();
    };
  }

  function runLadderClimb(canvas, help, onScoreUpdate) {
    const ctx = canvas.getContext("2d");
    const isMobile = window.innerWidth <= 980;
    const WIDTH = 12;
    const HEIGHT = 320;
    const TILE = isMobile ? 10 : 14;
    canvas.width = WIDTH * TILE;
    canvas.height = isMobile ? 280 : 430;
    canvas.classList.remove("runner-canvas");
    canvas.classList.add("climber-canvas");
    let player = { x: WIDTH / 2, y: HEIGHT - 5, w: 0.9, h: 0.95 };
    let velocityY = 0;
    let velocityX = 0;
    let score = 0;
    let floorReached = 0;
    let combo = 0;
    let comboTimer = 0;
    let gameRunning = false;
    let gameOver = false;
    let countdown = 3;
    let cameraY = player.y;
    let waterLevel = HEIGHT + 16;
    let onGround = false;
    let rafId = null;
    let countdownTimer = null;
    let lastFrameMs = null;
    let jumpQueued = false;
    let highScore = readStoredNumber(CLIMBER_HIGH_SCORE_KEY);
    let level = 1;
    let nextMilestone = 250;
    let milestoneText = "";
    let milestoneTimer = 0;
    const keys = { left: false, right: false };
    const platforms = [];
    const ghosts = [];
    const levelThemes = [
      { skyA: "#161616", skyB: "#1f1f1f", platform: "#efefef", accent: "#8bc34a" },
      { skyA: "#101820", skyB: "#1b2730", platform: "#d7e2ea", accent: "#4fc3f7" },
      { skyA: "#1d1021", skyB: "#29152d", platform: "#f2dede", accent: "#ff8a65" },
      { skyA: "#18150b", skyB: "#252010", platform: "#ece1ba", accent: "#ffd54f" },
    ];

    function spawnInitialPlatforms() {
      platforms.length = 0;
      platforms.push({ x: 1, y: HEIGHT - 3, width: WIDTH - 2, type: "start" });
      let y = HEIGHT - 8;
      while (y > 0) {
        const width = 2 + Math.floor(Math.random() * 3);
        const x = Math.floor(Math.random() * Math.max(1, WIDTH - width));
        const typeRoll = Math.random();
        const type = typeRoll > 0.82 ? "bounce" : "normal";
        platforms.push({ x, y, width, type });
        y -= 4 + Math.floor(Math.random() * 2);
      }
    }

    function fillAhead() {
      let highest = Math.min(...platforms.map((platform) => platform.y));
      while (highest > player.y - 70) {
        highest -= Math.max(3, 5 - Math.min(2, Math.floor(level / 3))) + Math.floor(Math.random() * 2);
        const width = Math.max(2, 3 + Math.floor(Math.random() * 2) - Math.min(1, Math.floor(level / 4)));
        const x = Math.floor(Math.random() * Math.max(1, WIDTH - width));
        const typeRoll = Math.random();
        const type = typeRoll > Math.max(0.74, 0.88 - level * 0.02) ? "bounce" : "normal";
        platforms.push({ x, y: highest, width, type });
      }
    }

    function updateHelp() {
      if (gameOver) {
        help.textContent = `GAME OVER | ${score}m | High: ${highScore} | Tap to retry`;
        return;
      }
      if (!gameRunning) {
        help.textContent = countdown > 0
          ? `DRAIN CLIMBER | ${countdown} | High: ${highScore}`
          : `DRAIN CLIMBER | High: ${highScore}`;
        return;
      }
      help.textContent = `Height: ${score}m | Level: ${level} | Combo: x${Math.max(combo, 1)} | High: ${highScore}`;
    }

    function drawGameOver() {
      ctx.fillStyle = "rgba(0, 0, 0, 0.72)";
      ctx.fillRect(18, 150, canvas.width - 36, 176);
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      ctx.strokeRect(18, 150, canvas.width - 36, 176);
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 28px Chicago, Monaco, monospace";
      ctx.textAlign = "center";
      ctx.fillText("GAME OVER", canvas.width / 2, 195);
      ctx.font = "20px Chicago, Monaco, monospace";
      ctx.fillText(`Height: ${score}m`, canvas.width / 2, 232);
      ctx.fillText(`High: ${highScore}m`, canvas.width / 2, 262);
      ctx.font = "16px Chicago, Monaco, monospace";
      ctx.fillText("Tap or click to retry", canvas.width / 2, 302);
      ctx.textAlign = "start";
    }

    function drawCountdownOverlay() {
      ctx.fillStyle = "rgba(0, 0, 0, 0.58)";
      ctx.fillRect(52, 120, canvas.width - 104, 120);
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      ctx.strokeRect(52, 120, canvas.width - 104, 120);
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 54px Chicago, Monaco, monospace";
      ctx.textAlign = "center";
      ctx.fillText(String(countdown), canvas.width / 2, 196);
      ctx.textAlign = "start";
    }

    function draw() {
      const theme = levelThemes[(level - 1) % levelThemes.length];
      const offsetY = cameraY * TILE - canvas.height * (isMobile ? 0.84 : 0.68);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (let i = 0; i < canvas.height / 20; i += 1) {
        ctx.fillStyle = i % 2 === 0 ? theme.skyA : theme.skyB;
        ctx.fillRect(0, i * 20, canvas.width, 20);
      }

      ctx.fillStyle = "rgba(255,255,255,0.18)";
      ctx.font = "12px Chicago, Monaco, monospace";
      ctx.textAlign = "right";
      for (let meter = 250; meter <= Math.max(nextMilestone, score + 250); meter += 250) {
        const y = (HEIGHT - meter / 10) * TILE - offsetY;
        if (y < -18 || y > canvas.height + 18) continue;
        ctx.fillRect(8, y, canvas.width - 16, 1);
        ctx.fillText(`${meter}m`, canvas.width - 10, y - 4);
      }
      ctx.textAlign = "start";

      platforms.forEach((platform) => {
        const px = platform.x * TILE;
        const py = platform.y * TILE - offsetY;
        ctx.fillStyle = platform.type === "bounce" ? theme.accent : theme.platform;
        ctx.fillRect(px, py, platform.width * TILE, 10);
        ctx.strokeStyle = "#000";
        ctx.strokeRect(px, py, platform.width * TILE, 10);
      });

      ghosts.forEach((ghost, index) => {
        const alpha = Math.max(0, 1 - index / ghosts.length);
        ctx.fillStyle = `rgba(255, 255, 255, ${alpha * 0.3})`;
        ctx.fillRect(ghost.x * TILE, ghost.y * TILE - offsetY, player.w * TILE, player.h * TILE);
      });

      ctx.fillStyle = "#ffd54f";
      ctx.fillRect(player.x * TILE, player.y * TILE - offsetY, player.w * TILE, player.h * TILE);
      ctx.strokeStyle = "#000";
      ctx.strokeRect(player.x * TILE, player.y * TILE - offsetY, player.w * TILE, player.h * TILE);

      const waterY = waterLevel * TILE - offsetY;
      ctx.fillStyle = "#2979ff";
      ctx.fillRect(0, waterY, canvas.width, canvas.height - waterY);
      ctx.fillStyle = "rgba(255,255,255,0.25)";
      ctx.fillRect(0, waterY, canvas.width, 6);

      if (milestoneTimer > 0) {
        ctx.fillStyle = "rgba(0,0,0,0.6)";
        ctx.fillRect(38, 60, canvas.width - 76, 54);
        ctx.strokeStyle = "#fff";
        ctx.strokeRect(38, 60, canvas.width - 76, 54);
        ctx.fillStyle = "#fff";
        ctx.font = "bold 22px Chicago, Monaco, monospace";
        ctx.textAlign = "center";
        ctx.fillText(milestoneText, canvas.width / 2, 93);
        ctx.textAlign = "start";
      }

      if (!gameRunning && !gameOver && countdown > 0) {
        drawCountdownOverlay();
      }

      if (gameOver) {
        drawGameOver();
      }

      updateHelp();
    }

    function updateHighScore() {
      if (score > highScore) {
        highScore = score;
        writeStoredNumber(CLIMBER_HIGH_SCORE_KEY, highScore);
        syncHighScore("ladderclimb", highScore);
        if (onScoreUpdate) onScoreUpdate();
      }
    }

    function startRound() {
      player = { x: WIDTH / 2, y: HEIGHT - 5, w: 0.9, h: 0.95 };
      velocityY = 0;
      velocityX = 0;
      score = 0;
      floorReached = 0;
      combo = 0;
      comboTimer = 0;
      countdown = 3;
      level = 1;
      nextMilestone = 250;
      milestoneText = "";
      milestoneTimer = 0;
      gameRunning = false;
      gameOver = false;
      cameraY = player.y;
      waterLevel = HEIGHT + 16;
      onGround = false;
      jumpQueued = false;
      ghosts.length = 0;
      spawnInitialPlatforms();
      updateHelp();
      draw();
      countdownTimer = setInterval(() => {
        countdown -= 1;
        if (countdown <= 0) {
          clearInterval(countdownTimer);
          countdownTimer = null;
          lastFrameMs = null;
          gameRunning = true;
          rafId = requestAnimationFrame(step);
        } else {
          draw();
        }
      }, 1000);
    }

    function onKey(event) {
      if (event.type === "game-control") {
        const detail = event.detail || {};
        const isDown = detail.phase === "down";
        if (detail.slot === "left") keys.left = isDown;
        if (detail.slot === "right") keys.right = isDown;
        if (detail.slot === "action" && isDown) jumpQueued = true;
        return;
      }
      if (event.type === "keydown" && (event.key === " " || event.code === "Space" || event.key.startsWith("Arrow"))) {
        event.preventDefault();
      }
      if (gameOver && event.type === "keydown" && (event.key === " " || event.code === "Space" || event.key === "Enter")) {
        startRound();
        return;
      }
      if (event.type === "keydown") {
        if (event.key === "ArrowLeft" || event.key === "a") keys.left = true;
        if (event.key === "ArrowRight" || event.key === "d") keys.right = true;
        if (event.key === " " || event.code === "Space") jumpQueued = true;
      } else {
        if (event.key === "ArrowLeft" || event.key === "a") keys.left = false;
        if (event.key === "ArrowRight" || event.key === "d") keys.right = false;
      }
    }

    function step(timestamp) {
      if (!gameRunning) return;
      const now = typeof timestamp === "number" ? timestamp : performance.now();
      const deltaMs = lastFrameMs == null ? 16.67 : Math.max(10, Math.min(50, now - lastFrameMs));
      lastFrameMs = now;
      const frameScale = deltaMs / 16.67;
      const previousY = player.y;
      if (keys.left) velocityX -= (onGround ? 0.038 : 0.028) * frameScale;
      if (keys.right) velocityX += (onGround ? 0.038 : 0.028) * frameScale;
      velocityX *= Math.pow(onGround ? 0.85 : 0.985, frameScale);
      velocityX = Math.max(-0.24, Math.min(0.24, velocityX));
      player.x += velocityX * frameScale;
      if (player.x < 0) {
        player.x = 0;
        velocityX = Math.max(0.08, Math.abs(velocityX) * 0.88);
      }
      if (player.x + player.w > WIDTH) {
        player.x = WIDTH - player.w;
        velocityX = -Math.max(0.08, Math.abs(velocityX) * 0.88);
      }

      if (jumpQueued && onGround) {
        velocityY = Math.abs(velocityX) > 0.11 ? -0.86 : -0.74;
        onGround = false;
        jumpQueued = false;
      }
      jumpQueued = false;

      velocityY += 0.03 * frameScale;
      player.y += velocityY * frameScale;
      onGround = false;

      for (let index = 0; index < platforms.length; index += 1) {
        const platform = platforms[index];
        const intersectsX = player.x + player.w > platform.x && player.x < platform.x + platform.width;
        const landing = previousY + player.h <= platform.y && player.y + player.h >= platform.y;
        if (velocityY >= 0 && intersectsX && landing) {
          player.y = platform.y - player.h;
          velocityY = platform.type === "bounce" ? -0.98 : 0;
          onGround = true;
          break;
        }
      }

      ghosts.unshift({ x: player.x, y: player.y });
      if (ghosts.length > 12) ghosts.pop();

      cameraY += (player.y - cameraY) * Math.min(0.22, 0.08 * frameScale);
      waterLevel -= (0.028 + level * 0.003) * frameScale;
      const desiredWater = player.y + 26;
      if (waterLevel - desiredWater > 20) {
        waterLevel = Math.max(
          desiredWater,
          waterLevel - Math.min(0.38 * frameScale, (waterLevel - desiredWater) * 0.05 * frameScale)
        );
      }
      fillAhead();

      const climbed = Math.max(0, Math.floor((HEIGHT - player.y) * 10));
      if (climbed > score) {
        score = climbed + combo * 10;
        combo = comboTimer > 0 ? combo + 1 : 1;
        comboTimer = 44;
        floorReached = Math.max(floorReached, Math.floor((HEIGHT - player.y) / 4));
        const nextLevel = Math.max(1, Math.floor(score / 250) + 1);
        if (nextLevel !== level) level = nextLevel;
        if (score >= nextMilestone) {
          milestoneText = `${nextMilestone}m`;
          milestoneTimer = 110;
          nextMilestone += 250;
        }
        updateHighScore();
      } else if (comboTimer > 0) {
        comboTimer -= frameScale;
      } else {
        combo = 0;
      }

      if (milestoneTimer > 0) milestoneTimer -= frameScale;

      if (player.y > waterLevel) {
        gameRunning = false;
        gameOver = true;
        updateHighScore();
        draw();
        help.textContent = `GAME OVER | ${score}m | High: ${highScore}m | Tap to retry`;
        return;
      }

      draw();
      rafId = requestAnimationFrame(step);
    }

    const restartRound = () => {
      if (!gameOver) return;
      startRound();
    };

    bindGameCleanup(onKey, () => {
      if (rafId) cancelAnimationFrame(rafId);
      if (countdownTimer) clearInterval(countdownTimer);
      canvas.removeEventListener("click", restartRound);
      canvas.removeEventListener("touchstart", restartRound);
    });
    canvas.addEventListener("click", restartRound);
    canvas.addEventListener("touchstart", restartRound, { passive: true });
    draw();
    startRound();
  }

  function runTorchSprint(canvas, help, onScoreUpdate) {
    const ctx = canvas.getContext("2d");
    const isMobile = window.innerWidth <= 980;
    canvas.width = isMobile ? 340 : 520;
    canvas.height = isMobile ? 380 : 420;
    canvas.classList.remove("climber-canvas");
    canvas.classList.add("runner-canvas");
    const lanes = [canvas.width * 0.28, canvas.width * 0.5, canvas.width * 0.72];
    const player = { lane: 1, y: canvas.height - 78, size: isMobile ? 36 : 40 };
    const keys = { left: false, right: false, boost: false };
    const obstacles = [];
    const torches = [];
    let score = 0;
    let distance = 0;
    let speed = 2.1;
    let spawnTimer = 0;
    let gameRunning = false;
    let gameOver = false;
    let countdown = 3;
    let rafId = null;
    let countdownTimer = null;
    let lastFrameMs = null;
    let highScore = readStoredNumber(TORCH_SPRINT_HIGH_SCORE_KEY);
    let bestUpdated = false;

    function drawHud() {
      ctx.fillStyle = "rgba(0,0,0,0.46)";
      ctx.fillRect(10, 10, canvas.width - 20, 40);
      ctx.fillStyle = "#fff";
      ctx.font = 'bold 15px "ChicagoCustom", "Chicago", "Fixedsys", sans-serif';
      ctx.fillText(`Score: ${score}  Dist: ${distance}m  High: ${highScore}`, 18, 36);
    }

    function drawRoad() {
      const horizonY = canvas.height * 0.18;
      ctx.fillStyle = "#111";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      const gradient = ctx.createLinearGradient(0, horizonY, 0, canvas.height);
      gradient.addColorStop(0, "#4a4a4a");
      gradient.addColorStop(1, "#121212");
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.moveTo(canvas.width * 0.24, horizonY);
      ctx.lineTo(canvas.width * 0.76, horizonY);
      ctx.lineTo(canvas.width, canvas.height);
      ctx.lineTo(0, canvas.height);
      ctx.closePath();
      ctx.fill();

      const laneColor = "#e0e0e0";
      ctx.strokeStyle = laneColor;
      ctx.lineWidth = 3;
      [0.37, 0.63].forEach((ratio) => {
        ctx.setLineDash([14, 16]);
        ctx.beginPath();
        ctx.moveTo(canvas.width * ratio, horizonY + 16);
        ctx.lineTo(canvas.width * ratio, canvas.height);
        ctx.stroke();
      });
      ctx.setLineDash([]);
    }

    function drawPlayer() {
      const x = lanes[player.lane];
      const y = player.y;
      ctx.fillStyle = "#ffd54f";
      ctx.fillRect(x - player.size / 2, y - player.size / 2, player.size, player.size);
      ctx.strokeStyle = "#000";
      ctx.strokeRect(x - player.size / 2, y - player.size / 2, player.size, player.size);
      ctx.fillStyle = "#000";
      ctx.fillRect(x - 6, y - 5, 4, 4);
      ctx.fillRect(x + 2, y - 5, 4, 4);
    }

    function drawObjects() {
      obstacles.forEach((obstacle) => {
        const x = lanes[obstacle.lane];
        const size = obstacle.size;
        ctx.fillStyle = obstacle.kind === "cop" ? "#c62828" : "#424242";
        ctx.fillRect(x - size / 2, obstacle.y - size / 2, size, size);
        ctx.strokeStyle = "#000";
        ctx.strokeRect(x - size / 2, obstacle.y - size / 2, size, size);
      });
      torches.forEach((torch) => {
        const x = lanes[torch.lane];
        ctx.fillStyle = "#ffeb3b";
        ctx.beginPath();
        ctx.arc(x, torch.y, 10, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = "#000";
        ctx.stroke();
      });
    }

    function drawCountdown() {
      ctx.fillStyle = "rgba(0,0,0,0.62)";
      ctx.fillRect(canvas.width / 2 - 84, canvas.height / 2 - 70, 168, 130);
      ctx.strokeStyle = "#fff";
      ctx.strokeRect(canvas.width / 2 - 84, canvas.height / 2 - 70, 168, 130);
      ctx.fillStyle = "#fff";
      ctx.font = 'bold 62px "ChicagoCustom", "Chicago", "Fixedsys", sans-serif';
      ctx.textAlign = "center";
      ctx.fillText(String(countdown), canvas.width / 2, canvas.height / 2 + 22);
      ctx.textAlign = "start";
    }

    function drawGameOver() {
      ctx.fillStyle = "rgba(0,0,0,0.76)";
      ctx.fillRect(canvas.width / 2 - 170, canvas.height / 2 - 96, 340, 192);
      ctx.strokeStyle = "#fff";
      ctx.strokeRect(canvas.width / 2 - 170, canvas.height / 2 - 96, 340, 192);
      ctx.fillStyle = "#fff";
      ctx.textAlign = "center";
      ctx.font = 'bold 34px "ChicagoCustom", "Chicago", "Fixedsys", sans-serif';
      ctx.fillText("GAME OVER", canvas.width / 2, canvas.height / 2 - 42);
      ctx.font = '20px "ChicagoCustom", "Chicago", "Fixedsys", sans-serif';
      ctx.fillText(`Score: ${score}`, canvas.width / 2, canvas.height / 2 - 8);
      ctx.fillText(`High: ${highScore}`, canvas.width / 2, canvas.height / 2 + 18);
      ctx.font = '16px "ChicagoCustom", "Chicago", "Fixedsys", sans-serif';
      ctx.fillText("Tap or click to retry", canvas.width / 2, canvas.height / 2 + 52);
      ctx.textAlign = "start";
    }

    function updateHelp() {
      if (gameOver) {
        help.textContent = `DRAIN RUNNER | GAME OVER | Score: ${score} | High: ${highScore}`;
        return;
      }
      if (!gameRunning) {
        help.textContent = `DRAIN RUNNER | ${countdown > 0 ? countdown : ""} | High: ${highScore}`;
        return;
      }
      help.textContent = `Drain Runner | Score: ${score} | Dist: ${distance}m | High: ${highScore}`;
    }

    function maybeUpdateHighScore() {
      if (score <= highScore) return;
      highScore = score;
      bestUpdated = true;
      writeStoredNumber(TORCH_SPRINT_HIGH_SCORE_KEY, highScore);
      syncHighScore("torchsprint", highScore);
      if (onScoreUpdate) onScoreUpdate();
    }

    function draw() {
      drawRoad();
      drawObjects();
      drawPlayer();
      drawHud();
      if (!gameRunning && !gameOver && countdown > 0) drawCountdown();
      if (gameOver) drawGameOver();
      updateHelp();
    }

    function spawnObject() {
      const lane = Math.floor(Math.random() * 3);
      const y = -40;
      if (Math.random() < 0.18) {
        torches.push({ lane, y });
        return;
      }
      obstacles.push({
        lane,
        y,
        size: 26 + Math.random() * 10,
        kind: Math.random() < 0.45 ? "cop" : "pipe",
      });
    }

    function step(timestamp) {
      if (!gameRunning) return;
      const now = typeof timestamp === "number" ? timestamp : performance.now();
      const deltaMs = lastFrameMs == null ? 16.67 : Math.max(12, Math.min(40, now - lastFrameMs));
      lastFrameMs = now;
      const frameScale = deltaMs / 16.67;
      const laneShift = keys.boost ? 2 : 1;
      if (keys.left && player.lane > 0) {
        player.lane = Math.max(0, player.lane - laneShift);
        keys.left = false;
      }
      if (keys.right && player.lane < 2) {
        player.lane = Math.min(2, player.lane + laneShift);
        keys.right = false;
      }
      const moveSpeed = (2.8 + speed * 1.7) * frameScale;
      for (let i = obstacles.length - 1; i >= 0; i -= 1) {
        obstacles[i].y += moveSpeed;
        if (obstacles[i].y > canvas.height + 50) obstacles.splice(i, 1);
      }
      for (let i = torches.length - 1; i >= 0; i -= 1) {
        torches[i].y += moveSpeed;
        if (torches[i].y > canvas.height + 30) torches.splice(i, 1);
      }
      spawnTimer -= deltaMs;
      if (spawnTimer <= 0) {
        spawnObject();
        if (distance > 320 && Math.random() < 0.36) spawnObject();
        spawnTimer = Math.max(320, 980 - speed * 120 - distance * 0.35);
      }
      const targetSpeed = Math.min(7.6, 2.1 + distance / 520);
      speed += (targetSpeed - speed) * Math.min(0.12, 0.06 * frameScale);
      distance += Math.max(1, Math.floor((1.2 + speed) * (deltaMs / 45)));
      score += Math.max(1, Math.floor((1.9 + speed * 0.85) * (deltaMs / 35)));

      for (let i = torches.length - 1; i >= 0; i -= 1) {
        const torch = torches[i];
        if (torch.lane === player.lane && Math.abs(torch.y - player.y) < 24) {
          score += 25;
          torches.splice(i, 1);
        }
      }

      for (let i = 0; i < obstacles.length; i += 1) {
        const obstacle = obstacles[i];
        if (obstacle.lane !== player.lane) continue;
        if (Math.abs(obstacle.y - player.y) > 24) continue;
        gameRunning = false;
        gameOver = true;
        maybeUpdateHighScore();
        draw();
        return;
      }
      maybeUpdateHighScore();
      draw();
      rafId = requestAnimationFrame(step);
    }

    function onKey(event) {
      if (event.type === "game-control") {
        const detail = event.detail || {};
        const isDown = detail.phase === "down";
        if (detail.slot === "left" && isDown) keys.left = true;
        if (detail.slot === "right" && isDown) keys.right = true;
        if (detail.slot === "action") keys.boost = isDown;
        return;
      }
      if (event.type === "keydown" && event.key.startsWith("Arrow")) event.preventDefault();
      if (gameOver && event.type === "keydown" && (event.key === " " || event.code === "Space" || event.key === "Enter")) {
        startRound();
        return;
      }
      if (event.type === "keydown") {
        if (event.key === "ArrowLeft" || event.key === "a") keys.left = true;
        if (event.key === "ArrowRight" || event.key === "d") keys.right = true;
        if (event.key === "ArrowUp" || event.key === "w" || event.code === "Space") keys.boost = true;
      } else {
        if (event.key === "ArrowUp" || event.key === "w" || event.code === "Space") keys.boost = false;
      }
    }

    function startRound() {
      obstacles.length = 0;
      torches.length = 0;
      player.lane = 1;
      score = 0;
      distance = 0;
      speed = 2.1;
      spawnTimer = 740;
      gameRunning = false;
      gameOver = false;
      countdown = 3;
      lastFrameMs = null;
      keys.left = false;
      keys.right = false;
      keys.boost = false;
      draw();
      if (countdownTimer) clearInterval(countdownTimer);
      countdownTimer = setInterval(() => {
        countdown -= 1;
        if (countdown <= 0) {
          clearInterval(countdownTimer);
          countdownTimer = null;
          gameRunning = true;
          rafId = requestAnimationFrame(step);
        } else {
          draw();
        }
      }, 1000);
    }

    const restartRound = () => {
      if (!gameOver) return;
      startRound();
    };

    bindGameCleanup(onKey, () => {
      if (rafId) cancelAnimationFrame(rafId);
      if (countdownTimer) clearInterval(countdownTimer);
      canvas.removeEventListener("click", restartRound);
      canvas.removeEventListener("touchstart", restartRound);
      if (bestUpdated && onScoreUpdate) onScoreUpdate();
    });
    canvas.addEventListener("click", restartRound);
    canvas.addEventListener("touchstart", restartRound, { passive: true });
    draw();
    startRound();
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
  qs("#tutorialButton").addEventListener("click", openTutorial);
  qs("#notificationsButton").addEventListener("click", openNotifications);
  if (qs("#activityButton")) qs("#activityButton").addEventListener("click", openActivity);
  qs("#addDrainButton").addEventListener("click", openAddDrain);
  if (qs("#mapButton")) qs("#mapButton").addEventListener("click", openMapPanel);
  qs("#profileButton").addEventListener("click", openProfile);
  if (visitedCount) visitedCount.addEventListener("click", openVisitedDrains);
  if (qs("#syncMapButton")) qs("#syncMapButton").addEventListener("click", syncMap);
  qs("#miniGamesButton").addEventListener("click", openGames);
  qs("#closeModal").addEventListener("click", closeModal);

  modalLayer.addEventListener("click", (event) => {
    if (event.target === modalLayer) closeModal();
  });
  window.addEventListener("pointerdown", unlockAudio, { once: true });
  window.addEventListener("click", unlockAudio, { once: true });
  window.addEventListener("touchstart", unlockAudio, { once: true, passive: true });
  window.addEventListener("keydown", unlockAudio, { once: true });
  qs("#closeImagePreview").addEventListener("click", closeImagePreview);
  imagePreviewLayer.addEventListener("click", (event) => {
    if (event.target === imagePreviewLayer) closeImagePreview();
  });

  minDistance.addEventListener("input", syncSliders);
  maxDistance.addEventListener("input", syncSliders);
  onlyUnvisitedToggle.addEventListener("change", () => syncVisitFilters("unvisited"));
  onlyVisitedToggle.addEventListener("change", () => syncVisitFilters("visited"));
  searchInput.addEventListener("input", () => {
    if (searchTimer) clearTimeout(searchTimer);
    const nextQuery = searchInput.value;
    searchTimer = setTimeout(() => {
      searchDrains(nextQuery);
    }, 140);
  });
  searchInput.addEventListener("blur", () => {
    if (searchAbortController) searchAbortController.abort();
    if (searchTimer) clearTimeout(searchTimer);
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
  setupThemes();
  syncStoredHighScores();
  refreshNotifications();
  setInterval(refreshNotifications, 30000);
  requestLocation();
  window.addEventListener("resize", () => {
    fitDesktop();
    syncSliders();
  });
})();
