

/**
 * @typedef QueuedVideo
 * @property {string} id
 * @property {number} start
 * @property {string} duration
 * @property {string} title
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
    return fetch("/api/music/song/playerstate", {
        method: "POST",
        body: body
    }).then(r => {
        if (r.ok) {
            return r.json();
        } else return null;
    });
}

/**
 * @returns {Promise<PlayerState?>}
 */
function getPlayerState() {
    return fetch("api/music/song/playerstate").then(r => {
        if (r.ok)
            return r.json();
        else return null;
    });
}

window.addEventListener("load", () => {
    const persistenceEnableButton = document.getElementById("enable-ovpersist-button");
    const persistenceDisableButton = document.getElementById("disable-ovpersist-button");
    const skipSongButton = document.getElementById("skip-song");
    /** @type {HTMLButtonElement} */
    const pausePlayButton = document.getElementById("pauseplay-song");

    persistenceEnableButton.addEventListener("click", () => { setOverlayPersistence(true) });
    persistenceDisableButton.addEventListener("click", () => { setOverlayPersistence(false) });
    skipSongButton.addEventListener("click", () => {
        skipSong(1);
    });

    pausePlayButton.disabled = true;
    getPlayerState().then(stateInfo => {
        if (stateInfo?.state != null) {
            playerState = stateInfo;
            pausePlayButton.disabled = false;
            pausePlayButton.innerText = playerState.state[0].toUpperCase() + playerState.state.substring(1);
        }
    });

    pausePlayButton.addEventListener("click", async () => {
        const stateInfo = await setPlayState(playerState?.state == "pause" ? "play" : "pause");
        if (stateInfo == null)
            return;
        playerState = stateInfo;
        if (stateInfo.state == null)
            pausePlayButton.disabled = true;
        else {
            pausePlayButton.disabled = false;
            pausePlayButton.innerText = playerState.state[0].toUpperCase() + playerState.state.substring(1);
        }
    });


});