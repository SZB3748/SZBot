

/**
 * @typedef StateInfo
 * @property {string|null} name
 * @property {{content_name:string, border_name:string}|null} media
 */

/** @type {PngBindsMediaList} */
let mlist;
/** @type {StateMap} */
let statemap;
let currentState = null;

let displayChangeBuffer = null;

/**
 * @param {StateInfo} info
 */
async function displayState(info) {
    /** @type {HTMLImageElement} */
    const borderImage = document.getElementById("border-image");
    /** @type {HTMLDivElement} */
    const contentDiv = document.getElementById("content-div");
    if (currentState == info.name)
        return;

    currentState = info.name;

    if (info.media != null) {
        const borderMedia = mlist[info.media.border_name];
        const contentMedia = mlist[info.media.content_name];
        if (borderMedia.type == "image") {
            borderImage.src = await getMedia(info.media.border_name, true);
        } else {
            borderImage.src = ""; //borders can only use image media
        }

        while (contentDiv.children.length > 0) {
            contentDiv.firstChild.remove();
        }

        switch (contentMedia.type) {
        case "image": {
            const img = document.createElement("img");
            img.src = await getMedia(info.media.content_name, true);
            contentDiv.appendChild(img);
            break;
        }
        case "iframe": {
            const iframe = document.createElement("iframe");
            iframe.src = contentMedia.value;
            contentDiv.appendChild(iframe);
            break;
        }
        }

        const borderBounds = mlist[info.media.border_name]?.bounds;
        const contentBounds = mlist[info.media.content_name]?.bounds;

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
        if (mlist[name].type == "image") {
            getMedia(name, true);
        }
    }
}

/**
 * @param {StateInfo} info
 */
function bufferedDisplayState(info) {
    if (displayChangeBuffer != null)
        clearTimeout(displayChangeBuffer);
    displayChangeBuffer = setTimeout(() => {
        displayState(info);
        displayChangeBuffer = null;
    }, 100);
}


window.addEventListener("load", async () => {
    [mlist, statemap] = await Promise.all([getMediaList(), getStatemap()]);
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
                bufferedDisplayState(event.data);
                break;
            }
        }
    });
});