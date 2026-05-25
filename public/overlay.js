const video = document.querySelector("#alert-video");
const stage = document.querySelector(".stage");
const message = document.querySelector("#alert-message");
const params = new URLSearchParams(window.location.search);

const queue = [];
let isPlaying = false;

const settings = {
  debug: params.get("debug") === "1",
  fit: getVideoFit(params.get("fit")),
  volume: clampNumber(Number(params.get("volume") || "1"), 0, 1)
};

video.style.objectFit = settings.fit;
video.volume = settings.volume;

function clampNumber(value, min, max) {
  if (Number.isNaN(value)) {
    return max;
  }

  return Math.min(max, Math.max(min, value));
}

function getVideoFit(value) {
  if (value === "cover") {
    return "cover";
  }

  return "contain";
}

function debugLog(message, data) {
  if (settings.debug) {
    console.info(message, data || "");
  }
}

function setAlertMessage(value) {
  const text = typeof value === "string" ? value.trim() : "";
  const hasMessage = text.length > 0;

  message.textContent = text;
  message.setAttribute("aria-hidden", hasMessage ? "false" : "true");
  stage.classList.toggle("has-message", hasMessage);
}

function enqueueAlert(alert) {
  queue.push(alert);
  debugLog("Alert empfangen", alert);
  playNext();
}

async function playNext() {
  if (isPlaying || queue.length === 0) {
    return;
  }

  const alert = queue.shift();
  isPlaying = true;

  try {
    video.classList.remove("is-playing");
    video.pause();
    video.removeAttribute("src");
    video.load();
    setAlertMessage(alert.message);

    await new Promise((resolve) => window.setTimeout(resolve, 80));

    video.src = `${alert.url}?v=${encodeURIComponent(alert.id)}`;
    video.currentTime = 0;
    video.classList.add("is-playing");
    await video.play();
    debugLog("Alert spielt", alert);
  } catch (error) {
    console.error(`Konnte ${alert.file} nicht abspielen`, error);
    finishCurrent();
  }
}

function finishCurrent() {
  video.classList.remove("is-playing");
  video.pause();
  video.removeAttribute("src");
  video.load();
  setAlertMessage("");
  isPlaying = false;
  playNext();
}

video.addEventListener("ended", finishCurrent);
video.addEventListener("error", () => {
  console.error("Video konnte nicht geladen werden");
  finishCurrent();
});

const events = new EventSource("/overlay/alerts/events");

events.addEventListener("ready", () => {
  debugLog("Overlay verbunden");
});

events.addEventListener("alert", (event) => {
  try {
    enqueueAlert(JSON.parse(event.data));
  } catch (error) {
    console.error("Ungueltiges Alert-Event", error);
  }
});

events.addEventListener("error", () => {
  console.error("Verbindung zum Webhook-Server verloren");
});
