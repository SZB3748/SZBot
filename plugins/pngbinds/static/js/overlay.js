

/**
 * @typedef StateInfo
 * @property {string|null} name
 * @property {{content_name:string, border_name:string}|null} media
 */

/** @type {MediaListBounds} */
let mlist;
/** @type {StateMap} */
let statemap;
let currentState = null;

/**
 * @param {StateInfo} info
 */
async function displayState(info) {
    /** @type {HTMLImageElement} */
    const borderImage = document.getElementById("border-image");
    /** @type {HTMLImageElement} */
    const contentImage = document.getElementById("content-image");
    if (currentState == info.name)
        return;

    currentState = info.name;

    if (info.media != null) {
        borderImage.src = await getMedia(info.media.border_name, true);
        contentImage.src = await getMedia(info.media.content_name, true);

        const borderBounds = mlist[info.media.border_name];
        const contentBounds = mlist[info.media.content_name];

        const contentContainer = document.getElementById("content-container");
        const contentMargin = document.getElementById("content-margin");

        if (borderBounds == null)
            contentContainer.style = "";
        else {
            borderImage.addEventListener("load", () => {
                const top = Number(borderBounds.top);
                const left = Number(borderBounds.left);
                const width = borderImage.naturalWidth - left - Number(borderBounds.right);
                const height = borderImage.naturalHeight - top - Number(borderBounds.bottom);
                contentContainer.style = `width: ${width}px; height: ${height}px; top: ${top}px; left: ${left}px;`;
            }, {once: true});
        }
        if (contentBounds == null)
            contentMargin.style = "";
        else {
            contentMargin.style = `top: ${Number(contentBounds.top)}px; right: ${Number(contentBounds.right)}px; bottom: ${Number(contentBounds.bottom)}px; left: ${Number(contentBounds.left)}px;`;
        }
    }
}

function preloadAssets() {
    for (const name in mlist) {
        getMedia(name, true);
    }
}

window.addEventListener("load", async () => {
    [mlist, statemap] = await Promise.all([getMediaListBounds(), getStatemap()]);
    preloadAssets(); //allows for media to be changed ASAP
    const events = new WebSocket("/api/events");

    events.addEventListener("open", async () => {
        const r = await fetch("/api/pngbinds/state/current");
        if (!r.ok)
            return;
        displayState(await r.json());
    });
    
    events.addEventListener("message", ev => {
        const event = JSON.parse(ev.data);
        switch (event.name) {
            case "pngbinds:state_change": {
                displayState(event.data);
                break;
            }
        }
    });
});