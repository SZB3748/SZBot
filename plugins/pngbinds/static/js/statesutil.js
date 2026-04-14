/**
 * @typedef MediaReference
 * @property {string} content_name
 * @property {string} border_name
 */

/**
 * @typedef TimeoutChange
 * @property {string} destination
 * @property {number} timeout seconds
 */

/**
 * @typedef State
 * @property {MediaReference} media
 * @property {TimeoutChange?} change
 */

/**
 * @typedef {"HOLD"|"TRIGGER_DOWN"|"TRIGGER_UP"} TransitionMode
 */

/** @type {TransitionMode[]} */
const TRANSITION_MODES = ["TRIGGER_DOWN", "TRIGGER_UP", "HOLD"];

/**
 * @typedef Transition
 * @property {string} keybind
 * @property {TransitionMode} mode
 * @property {string} destination
 * @property {string?} pop_destination
 */

/**
 * @typedef StateMap
 * @property {Object<string, State>} states
 * @property {Object<string, Transition[]>} transitions
 */


/**
 * @returns {Promise<StateMap|null>}
 */
async function getStatemap() {
    const r = await fetch("/api/pngbinds/statemap.json");
    if (r.ok) {
        return r.json();
    }
    return null;
}

/**
 * @param {StateMap} statemap 
 * @returns {Promise<boolean>}
 */
async function saveStatemap(statemap) {
    const r = await fetch("/api/pngbinds/statemap.json", {
        method: "PUT",
        body: JSON.stringify(statemap, null, "    "),
        headers: {
            "Content-Type": "application/json"
        }
    });
    return r.ok;
}