

/**
 * @typedef QueuedVideo
 * @property {string} id
 * @property {number} start
 * @property {string} duration
 * @property {string} title
 * @property {string} thumbnail
 */

/**
 * @typedef QueueState
 * @property {QueuedVideo?} current
 * @property {QueuedVideo?} next
 * @property {QueuedVideo[]} queue
 */

/**
 * @typedef PlayerState
 * @property {string?} state
 * @property {number} position
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
function setPlayState(state) {
    const body = new FormData();
    body.set("state", state);
    return fetch("/api/music/playerstate", {
        method: "POST",
        body: body
    }).then(r => {
        if (r.ok) {
            return r.json();
        } else return null;
    });
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
function getPlayerState() {
    return fetch("api/music/playerstate").then(r => {
        if (r.ok)
            return r.json();
        else return null;
    });
}

/**
 * @returns {Promise<QueueState?>}
 */
function getQueueState() {
    return fetch("/api/music/queue").then(r => {
        if (r.ok)
            return r.json();
        else return null;
    });
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

let updateProgress;

const updateProgressCallback = () => {
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
 * 
 * @param {HTMLElement} elm 
 * @param {number} num 
 * @param {QueuedVideo} data 
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
            progress.value = playerState.position / 1000;
            
            progress.addEventListener("mousedown", () => {
                clearInterval(updateProgress);
                updateProgress = null;
            });
            
            progress.addEventListener("input", () => {
                durationCurrent.innerText = formatDuration(progress.value);
            });
            
            progress.addEventListener("change", () => {
                seekSong(progress.value);
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

    persistenceEnableButton.addEventListener("click", () => { setOverlayPersistence(true) });
    persistenceDisableButton.addEventListener("click", () => { setOverlayPersistence(false) });
    skipSongButton.addEventListener("click", async () => {
        const r = await skipSong(1);
        if (!r.ok)
            return;
        const count = await r.json();
        if (Number(count) > 0) {
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