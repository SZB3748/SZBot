

/**
 * @typedef QueuedSong A song gotten from a youtube video that is/was queued.
 * @property {string} id The song's ID on youtube.
 * @property {number} start The number of seconds into the song to begin playing from.
 * @property {string} duration The song's duration (HH:MM:SS).
 * @property {string} title The song's title.
 * @property {string} thumbnail The filename for the song's youtube thumbnail (usually `video_id`.`extension`).
 */

/**
 * @typedef QueueState The current state of the queue.
 * @property {QueuedSong?} current The song that's currently playing.
 * @property {QueuedSong?} next The song that has been pre-loaded to play next.
 * @property {QueuedSong[]} queue The songs in the queue.
 */

/**
 * @typedef PlayerState The current state of the song player.
 * @property {"play"|"pause"|null} state If the song player is playing a song or paused. `null` if there is no song playing.
 * @property {number} position The number of milliseconds that have elapsed for the current song.
 */


/** @type {PlayerState?} */
let playerState = null;
/** @type {QueueState?} */
let queueState = null;

/**
 * @param {boolean} value
 * @returns {Promise<Response>}
 */
function setOverlayPersistence(value) {
    const body = new FormData();
    body.set("value", JSON.stringify(value));
    return fetch("/api/music/overlay/persistent", {
        method: "POST",
        body: body
    });
}

/**
 * @param {number} count
 */
function skipSong(count) {
    const body = new FormData();
    body.set("count", `${count}`);
    return fetch("/api/music/queue/skip", {
        method: "POST",
        body: body
    });
}

/**
 * @param {string} state 
 * @returns {Promise<PlayerState?>}
 */
async function setPlayState(state) {
    const body = new FormData();
    body.set("state", state);
    const r = await fetch("/api/music/playerstate", {
        method: "POST",
        body: body
    });
    if (r.ok) {
        return r.json();
    } else return null;
}

/**
 * @param {number} seconds 
 */
function seekSong(seconds) {
    const body = new FormData();
    body.set("seconds", seconds);
    fetch("/api/music/seek", {
        method: "POST",
        body: body
    });
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
    const r = await fetch("/api/music/queue");
    if (r.ok)
            return r.json();
    else return null;
}

function updatePausePlayButton() {
    const pausePlayButton = document.getElementById("pauseplay-song");
    if (playerState?.state == null)
        pausePlayButton.disabled = true;
    else {
        pausePlayButton.disabled = false;
        if (playerState.state == "pause") {
            pausePlayButton.classList.remove("pause");
            pausePlayButton.classList.add("play");
        } else {
            pausePlayButton.classList.remove("play");
            pausePlayButton.classList.add("pause");
        }
    }
}

async function refreshState() {
    const qstate = await getQueueState();
    if (qstate == null)
        return;
    queueState = qstate;
    updatePausePlayButton();
    updateQueueVisuals(queueState);
}

/**
 * @param {string} duration A duration string HH:MM:SS
 * @returns {Number} Duration in seconds
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

let updateProgress;
/**
 * Generates a new callback for visually updating the current song's progress. Callback is used in an interval.
 * @param {number} duration The maximum duration of the song.
 */
function updateProgressCallback() {
    let lastProgressUpdate = Date.now();
    const songId = queueState?.current?.id;

    const currentSong = document.getElementById("current-song");
    const durationCurrent = currentSong.querySelector(":scope .duration-current");
    const progress = currentSong.querySelector(":scope .progress");

    console.log("starting progress interval");
    return () => {
        const currentSong = document.getElementById("current-song");
        if (currentSong.getAttribute("song-id") !== songId || playerState?.state !== "play") {
            clearInterval(updateProgress);
            updateProgress = null;
            return;
        }
        
        const now = Date.now()
        playerState.position = Math.min(playerState.position + now - lastProgressUpdate, progress.max * 1000);
        lastProgressUpdate = now;
        
        progress.value = playerState.position / 1000;
        durationCurrent.innerText = formatDuration(playerState.position / 1000);
    }
}

/**
 * Populate an element with everything needed to display a song's info.
 * @param {HTMLElement} elm The destination element.
 * @param {number} num What number element this is in the queue.
 * @param {QueuedSong} data
 */
function populateSongItem(elm, num, data) {
    while (elm.children.length > 0)
        elm.firstChild.remove();

    const marker = document.createElement("span");
    const container = document.createElement("div");
    const icon = document.createElement("img");
    const title = document.createElement("a");
    const duration = document.createElement("span");

    marker.classList.add("marker");
    container.classList.add("container");
    icon.classList.add("icon");
    title.classList.add("title");
    duration.classList.add("duration");

    marker.innerText = num + ".";
    icon.src = "/music/thumbnail/"+data.thumbnail;
    title.href = "https://youtube.com/watch?v=" + data.id;
    title.title = data.id;
    title.target = "_blank";
    title.innerText = data.title;
    duration.innerText = `${formatDuration(data.start)} / ${data.duration}`;

    container.append(marker, icon, title, duration);
    elm.appendChild(container);
}

/**
 * @param {QueueState} state 
 */
function updateQueueVisuals(state) {
    const currentSong = document.getElementById("current-song");
    const nextSongContainer = document.getElementById("next-container");
    const nextSong = document.getElementById("next-song");
    /** @type {HTMLOListElement} */
    const queueContainer = document.getElementById("queue-container");

    if (state.current == null || playerState == null) {
        while (currentSong.children.length > 0)
            currentSong.firstChild.remove();
        currentSong.removeAttribute("song-id");
        const p = document.createElement("p");
        p.innerText = state.next || state.queue.length ? "Preparing Next Song" : "No Song is Currently Playing";
        currentSong.appendChild(p);
    } else {
        if (currentSong.getAttribute("song-id") !== state.current.id) {
            while (currentSong.children.length > 0)
                currentSong.firstChild.remove();

            currentSong.setAttribute("song-id", state.current.id);
            const icon = document.createElement("img");
            const title = document.createElement("a");
            const progress = document.createElement("input");
            const durationCurrent = document.createElement("span");
            const durationTotal = document.createElement("span");
            const durationContainer = document.createElement("span");
            const columnGroup = document.createElement("div");


            icon.classList.add("icon");
            icon.src = "/music/thumbnail/"+state.current.thumbnail;
            
            title.classList.add("title");
            title.href = "https://youtube.com/watch?v=" + state.current.id;
            title.title = state.current.id;
            title.target = "_blank";
            title.innerText = state.current.title;

            durationCurrent.classList.add("duration-current");
            durationCurrent.innerText = formatDuration(playerState.position / 1000);
            durationTotal.innerText = "/ " + state.current.duration;
            durationContainer.append(durationCurrent, durationTotal);

            columnGroup.style = "display: flex; flex-direction: column;";
            columnGroup.append(title, durationContainer);
            
            progress.classList.add("progress");
            progress.type = "range";
            progress.min = 0;
            progress.max = parseDuration(state.current.duration);
            progress.step = 0.1;
            progress.value = playerState.position / 1000;
            
            progress.addEventListener("mousedown", () => {
                clearInterval(updateProgress);
                updateProgress = null;
            });
            
            progress.addEventListener("input", () => {
                durationCurrent.innerText = formatDuration(progress.value);
            });
            
            progress.addEventListener("change", () => {
                seekSong(Math.round(progress.value));
            });
            
            currentSong.append(icon, columnGroup, progress);
            if (updateProgress)
                clearInterval(updateProgress);
            updateProgress = setInterval(updateProgressCallback(), 100);
        }
    }
    let queueStart = 0;
    let workingNext = null;
    if (state.next == null) {
        if (state.queue.length > 0) {
            queueStart++;
            workingNext = state.queue[0];
        }
    } else
        workingNext = state.next;

    if (workingNext == null)
        nextSongContainer.removeAttribute("song-id");
    else if (nextSongContainer.getAttribute("song-id") != workingNext.id) {
        populateSongItem(nextSong, 1, workingNext);
        nextSongContainer.setAttribute("song-id", workingNext.id);
    }

    while (queueContainer.children.length > 0)
        queueContainer.firstChild.remove();

    let numCounter = 2;
    for (let i = queueStart; i < state.queue.length; i++) {
        const item = document.createElement("div");
        item.classList.add("item");
        populateSongItem(item, numCounter++, state.queue[i]);
        queueContainer.appendChild(item);

    }
}

const events = new WebSocket("/api/music/events");

events.addEventListener("open", ev => {
    console.log("Listening for events");
});

events.addEventListener("message", ev => {
    const event = JSON.parse(ev.data);
    switch (event.name) {
    case "change_playerstate": {
        playerState = event.data;
        if (updateProgress)
            clearInterval(updateProgress);
        updateProgress = setInterval(updateProgressCallback(), 100);
        break;
    }
    case "play_song":
        playerState = {
            state: "play",
            position: event.data.start * 1000
        };
    case "queue_song":
        if (event.data.success !== false)
            refreshState();
        break;
    }
});

events.addEventListener("error", ev => {
    
});

events.addEventListener("close", ev => {
    
});

window.addEventListener("load", async () => {
    /** @type {HTMLInputElement} */
    const addSongInput = document.getElementById("add-song");
    const viewQueueFileButton = document.getElementById("view-queue-file");
    const persistenceEnableButton = document.getElementById("enable-ovpersist-button");
    const persistenceDisableButton = document.getElementById("disable-ovpersist-button");
    const skipSongButton = document.getElementById("skip-song");
    /** @type {HTMLButtonElement} */
    const pausePlayButton = document.getElementById("pauseplay-song");

    addSongInput.addEventListener("keydown", ev => {
        if (ev.key !== "Enter" || ev.shiftKey || ev.ctrlKey || !addSongInput.reportValidity())
            return;
        
        ev.preventDefault();
        
        const body = new FormData();
        body.set("url", addSongInput.value);
        
        fetch("/api/music/queue/push", {
            method: "POST",
            body: body
        })
        addSongInput.value = "";
    });

    viewQueueFileButton.addEventListener("click", () => {
        fetch("/api/music/open-queue");
    });

    persistenceEnableButton.addEventListener("click", () => { setOverlayPersistence(true) });
    persistenceDisableButton.addEventListener("click", () => { setOverlayPersistence(false) });
    skipSongButton.addEventListener("click", async () => {
        const r = await skipSong(1);
        if (!r.ok)
            return;
        const count = await r.json();
        if (Number(count) > 0) {
            clearInterval(updateProgress);
            updateProgress = null;
            playerState = null;
            refreshState();
        }
    });

    pausePlayButton.disabled = true;
    const stateInfo = await getPlayerState()
    if (stateInfo?.state != null) {
        playerState = stateInfo;
        updatePausePlayButton();
    }

    queueState = await getQueueState()
    if (queueState != null)
        updateQueueVisuals(queueState);

    pausePlayButton.addEventListener("click", async () => {
        const stateInfo = await setPlayState(playerState?.state == "pause" ? "play" : "pause");
        if (stateInfo == null)
            return;
        playerState = stateInfo;
        updatePausePlayButton();
    });
});