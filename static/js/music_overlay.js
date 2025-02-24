
/**
 * @typedef PlayerState
 * @property {string?} state
 * @property {number} position
 */

const events = new WebSocket("/api/music/events");
/** @type {PlayerState?} */
let playerState = null;
let persistent = false;
let currentDuration = null;

/**
 * @type {{name: string, data: QueuedVideo}[]}
 */
const toastQueue = [];


/**
 * @param {string} duration
 * @returns {Number}
 */
function parseDuration(duration) {
    const [hours, minutes, seconds] = duration.split(":");
    return Number(hours) * 3600 + Number(minutes) * 60 + Number(seconds);
}

/**
 * @param {number} seconds
 * @returns {string}
 */
function formatDuration(seconds) {
    seconds = Math.trunc(seconds);
    hours = String(Math.floor(seconds / 3600)).padStart(2, "0")
    mins = String(Math.floor(seconds / 60) % 60).padStart(2, "0")
    secs = String(seconds % 60).padStart(2, "0")
    return [hours, mins, secs].join(":");
}

/**
 * @returns {Promise<PlayerState?>}
 */
async function getPlayerState() {
    const r = await fetch("/api/music/playerstate")
    if (r.ok)
        return r.json();
    else return null;
}

/**
 * @returns {Promise<QueueState?>}
 */
async function getQueueState() {
    return fetch("/api/music/queue").then(r => {
        if (r.ok)
            return r.json();
        else return null;
    });
}

let updateProgress;

/**
 * @param {number} duration
 */
function updateProgressCallback(duration) {
    let lastProgressUpdate = Date.now();

    const progressBar = document.getElementById("progress-bar");
    const durationCurrent = document.querySelector("#persistent .current-duration");


    console.log("starting progress interval");
    return () => {
        const now = Date.now()
        playerState.position = Math.min(playerState.position + now - lastProgressUpdate, duration);
        lastProgressUpdate = now;
        
        const percent = Math.min((playerState.position / duration * 100).toFixed(2), 100);
        progressBar.style.width = `${percent}%`;
        durationCurrent.innerText = formatDuration(playerState.position / 1000);
    }
}


/**
 * @param {boolean} state 
 */
async function updatePersistence(state) {
    const persistentDisplay = document.getElementById("persistent");
    persistent = state;

    if (state) {
        const pstate = await getPlayerState();
        if (pstate == null)
            return;
        const qstate = await getQueueState();
        if (qstate == null)
            return;
        
        playerState = pstate;
        if (qstate.current != null)
            setCurrentSong(qstate.current);
    } else if (updateProgress) {
        persistentDisplay.classList.remove("show");
        clearInterval(updateProgress);
        updateProgress = null;
    }
}

/**
 * @param {QueuedVideo} queued
 */
function setCurrentSong(queued) {
    const persistentDisplay = document.getElementById("persistent");
    /** @type {HTMLImageElement} */
    const icon = document.querySelector("#persistent .icon");
    const title = document.querySelector("#persistent .title");
    const currentDuration = document.querySelector("#persistent .current-duration");
    const duration = document.querySelector("#persistent .duration");

    icon.src =  "/music/thumbnail/"+queued.thumbnail;
    title.innerText = queued.title;
    currentDuration.innerText = formatDuration(playerState.position / 1000);
    duration.innerText = queued.duration;

    if (updateProgress)
        clearInterval(updateProgress);
    if (playerState.state == "play")
        updateProgress = setInterval(updateProgressCallback(parseDuration(queued.duration) * 1000));

    persistentDisplay.classList.add("show");
}
/**
 * @param {string} action
 * @param {QueuedVideo} queued
 * @return {Promise<void>}
 */
function runToast(action, queued) {
    const actionSpan = document.querySelector("#toast .action");
    /** @type {HTMLImageElement} */
    const icon = document.querySelector("#toast .icon");
    const title = document.querySelector("#toast .title");
    const duration = document.querySelector("#toast .duration");

    actionSpan.innerText = action + " • • •";
    icon.src =  queued.thumbnail ? "/music/thumbnail/"+queued.thumbnail : "/static/img/idiot.webp";
    title.innerText = queued.title;
    duration.innerText = queued.duration ? `${formatDuration(queued.start)} / ${queued.duration}` : "";

    const toast = document.getElementById("toast");
    toast.classList.add(persistent && playerState?.state != null ? "show-top" : "show");

    return new Promise(callback => {
        const prevUpdateProgress = updateProgress;
        const checkPlayingSong = setInterval(() => {
            if (updateProgress !== prevUpdateProgress) {
                clearInterval(checkPlayingSong);
                toast.classList.remove("show");
                toast.classList.add("show-top");
            }
        }, 50);
        setTimeout(() => {
            clearInterval(checkPlayingSong);
            toast.classList.remove("show", "show-top");
            callback();
        }, 7000);
    })
}


events.addEventListener("open", ev => {
    console.log("Listening for events");
});

events.addEventListener("message", ev => {
    const event = JSON.parse(ev.data);
    switch (event.name) {
    case "overlay_persistence_change":
        updatePersistence(event.data.value);
        break;
    case "change_playerstate":
        playerState = event.data;
        if (updateProgress)
            clearInterval(updateProgress);
        if (playerState.state == "play")
            updateProgress = setInterval(updateProgressCallback(currentDuration));
        break;
    case "play_song":
        currentDuration = parseDuration(event.data.duration) * 1000;
        if (persistent) {
            playerState = {
                position: event.data.start * 1000,
                state: "play"
            };
            setCurrentSong(event.data);
        }
        else
            toastQueue.push({
                name: "Playing",
                data: event.data
            });
        break;
    case "queue_song":
        if (event.data.success === false)
            toastQueue.push({
                name: "Failed to Queue",
                data: {title: event.data.id}
            });
        else
            toastQueue.push({
                name: "Queued",
                data: event.data
            });
        break;
    }
});

window.addEventListener("load", async () => {
    const toastCheck = async () => {
        if (toastQueue.length < 1)
            setTimeout(toastCheck, 750);
        else {
            const toast = toastQueue.splice(0, 1)[0];
            await runToast(toast.name, toast.data);
            setTimeout(toastCheck, 0);
        }
    };
    toastCheck();

    const params = new URLSearchParams(location.search);
    const persistentParam =  params.get("persistent");
    if (persistentParam !== null && persistentParam.trim() !== "false")
        updatePersistence(true);
});