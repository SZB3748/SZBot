/**
 * @typedef {string[]} PngBindsMediaList
 */


/** @type {Map<string, string>} */
const mediaCache = new Map();


/**
 * @returns {Promise<PngBindsMediaList|null>}
 */
async function getMediaList() {
    const r = await fetch("/api/pngbinds/media/list");
    if (r.ok)
        return r.json();
    return null;
}

/**
 * @param {string} name
 * @param {bool} useCache
 * @returns {Promise<string|null>}
 */
async function getMedia(name, useCache) {
    if (useCache) {
        if (mediaCache.has(name)) {
            return mediaCache.get(name);
        }
    }
    const r = await fetch(`/api/pngbinds/media/file/${name}`);
    if (!r.ok)
        return null;
    const b = await r.blob();
    const bUrl = URL.createObjectURL(b);

    if (useCache) {
        mediaCache.set(name, bUrl);
    }
    return bUrl;
}

/**
 * @param {string} name
 * @param {File} file
 * @returns {Promise<bool>}
 */
async function uploadMedia(name, file) {
    const body = new FormData();
    body.set("file", file);
    const r = await fetch(`/api/pngbinds/media/file/${name}`, {
        method: "POST",
        body: body
    });
    return r.ok;
}

/**
 * @param {string} name
 * @returns {Promise<bool>}
 */
async function deleteMedia(name) {
    const r = await fetch(`/api/pngbinds/media/file/${name}`, {
        method: "DELETE"
    });
    return r.ok;
}


