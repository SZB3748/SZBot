/**
 * @typedef {string[]} PngBindsMediaList
 */

/**
 * @typedef MediaBounds
 * @property {number} top
 * @property {number} right
 * @property {number} bottom
 * @property {number} left
 */

/**
 * @typedef {Object<string, MediaBounds?>} MediaListBounds
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
 * @returns {Promise<MediaListBounds|null>}
 */
async function getMediaListBounds() {
    const r = await fetch("/api/pngbinds/media/list/bounds");
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

/**
 * @param {string} name
 * @param {number?} top
 * @param {number?} right
 * @param {number?} bottom
 * @param {number?} left
 * @returns {Promise<boolean>}
 */
async function setMediaBounds(name, top, right, bottom, left) {
    const body = new FormData();
    if (top != null && top != "")
        body.set("top", Number(top));
    if (right != null && right != "")
        body.set("right", Number(right));
    if (bottom != null && bottom != "")
        body.set("bottom", Number(bottom));
    if (left != null && left != "")
        body.set("left", Number(left));

    const r = await fetch(`/api/pngbinds/media/file/${name}/bounds`, {
        method: "POST",
        body: body
    });
    return r.ok;
}

/**
 * @param {string} name
 * @returns {Promise<boolean>}
 */
async function deleteMediaBounds(name) {
    const r = await fetch(`/api/pngbinds/media/file/${name}/bounds`, {
        method: "DELETE"
    });
    return r.ok;
}
