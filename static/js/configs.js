
/**
 * @typedef ConfigMeta
 * @property {string|undefined} name
 * @property {string|undefined} description
 * @property {MetaFieldCollection|undefined} configs
 */

/**
 * @typedef {Object<string, ConfigMeta>} ConfigMetaCollection
 */

/**
 * @typedef {Object<string, MetaField>} MetaFieldCollection
 */

/**
 * @typedef MetaField
 * @property {string|undefined} name
 * @property {string|undefined} description
 * @property {MetaTypesList|undefined} types
 * @property {boolean|undefined} optional
 * @property {any|undefined} default
 */

/**
 * @typedef {'null'|'boolean'|'string'|'integer'|'float'|'object'|'list'} MetaTypeNames
 */

/**
 * @typedef MetaTypesList
    @property {string|boolean|undefined} null
    @property {string|boolean|undefined} boolean
    @property {string|boolean|MetaTypeStringOptions|undefined} string
    @property {string|boolean|MetaTypeIntegerOptions|undefined} integer
    @property {string|boolean|MetaTypeFloatOptions|undefined} float
    @property {string|boolean|MetaTypeObjectOptions|undefined} object
    @property {string|boolean|MetaTypeListOptions|undefined} list
 */

/**
 * @typedef {string|boolean|MetaTypeOptions} MetaTypeExpression
 */

/**
 * @typedef {MetaTypeStringOptions|MetaTypeIntegerOptions|MetaTypeFloatOptions|MetaTypeObjectOptions|MetaTypeListOptions} MetaTypeOptions
 */

/**
 * @typedef {{">": number, "<": number, ">=": number, "<=": number, pattern: string}} MetaTypeStringOptions
 * @param {number} 
 */

/**
 * @typedef {{">": number, "<": number, ">=": number, "<=": number}} MetaTypeIntegerOptions
 */

/**
 * @typedef {{">": number, "<": number, ">=": number, "<=": number}} MetaTypeFloatOptions
 */

/**
 * @typedef {{fields: MetaFieldCollection}} MetaTypeObjectOptions
 */

/**
 * @typedef {{types: Object<string, MetaTypeExpression>}} MetaTypeListOptions
 */

/**
 * @typedef {Map<string, MetaField} MetaFieldGrouping
 */


/**
 * @returns {Promise<any?>} The configs JSON, or null if no config data could be loaded.
 */
async function getConfigs() {
    const r = await fetch("/api/configs");
    if (!r.ok)
        return null;
    const value = await r.json();
    return typeof value == "object" && !Array.isArray(value) ? value : null;
}

/**
 * @returns {Promise<ConfigMetaCollection?>} The config metas of all enabled plugins, or null if no config metadata could be loaded.
 */
async function getConfigsMeta() {
    const r = await fetch("/api/configs/meta");
    if (!r.ok)
        return null;
    const value = await r.json();
    return typeof value == "object" && !Array.isArray(value) ? value : null;
}

/**
 * @param {any} configs
 */
function putConfigs(configs) {
    return fetch("/api/configs", {
        method: "PUT",
        body: JSON.stringify(configs),
        headers: {
            "Content-Type": "application/json"
        }
    });
}

/**
 * @param {ConfigMetaCollection} metas 
 * @returns {[MetaFieldGrouping, Map<string, string>]} A MetaFieldGrouping and a field key to plugin map.
 */
function groupMetaFields(metas) {
    const grouping = new Map();
    const backmap = new Map();
    for (const name in metas) {
        const meta = metas[name];
        if (meta.configs == undefined)
            continue;
        for (const fieldname in meta.configs) {
            if (grouping.has(fieldname)) {
                console.warn("Field", fieldname, "from plugin", name, "already present");
            } else {
                grouping.set(fieldname, meta.configs[fieldname]);
                backmap.set(fieldname, name);
            }
        }
    }
    return grouping, backmap;
}

/**
 * @param {any} configs
 * @param {MetaFieldGrouping} grouping 
 * @param {Map<string, string>} backmap 
 * @param {HTMLElement} dest
 */
function createConfigDisplay(configs, grouping, backmap, dest) {
    //TODO
}

/**
 * @param {string} name 
 */
function changeInterface(name) {
    const current = document.getElementById(`interface-${name}`);
    if (current == null) {
        console.error("bad interface name:", name);
        return;
    }
    const old = document.querySelector(".interface.show");
    if (old != null)
        old.classList.remove("show");

    current.classList.add("show");
}

async function initConfigData() {
    const configInfo = Array.from((await Promise.all([getConfigs(), getConfigsMeta()])).values());
    /** @type {object?} */
    const configs = configInfo[0];
    /** @type {ConfigMetaCollection?} */
    const metas = configInfo[1];
    /** @type {HTMLTextAreaElement} */
    const rawTextarea = document.getElementById("raw-editor");
    rawTextarea.value = JSON.stringify(configs, null, 4);
    if (configs != null && metas != null) {
        const [grouping, backmap] = groupMetaFields(metas);
        const dest = document.getElementById("interface-pretty");
        while (dest.children.length > 0)
            dest.firstChild.remove();
        createConfigDisplay(configs, grouping, backmap, dest);
    }
    return configs;
}

window.addEventListener("load", async () => {
    let configs = await initConfigData();
    
    /** @type {HTMLTextAreaElement} */
    const rawTextarea = document.getElementById("raw-editor");
    rawTextarea.addEventListener("change", async () => {
        configs = JSON.parse(rawTextarea.value);
        const metas = await getConfigsMeta();
        const [grouping, backmap] = groupMetaFields(metas);
        const dest = document.getElementById("interface-pretty");
        while (dest.children.length > 0)
            dest.firstChild.remove();
        createConfigDisplay(configs, grouping, backmap, dest);
    });
    
    const prettyButton = document.getElementById("interface-pretty-button");
    const rawButton = document.getElementById("interface-raw-button");

    prettyButton.addEventListener("click", () => location.hash = "pretty");
    rawButton.addEventListener("click", () => location.hash = "raw");

    const saveButton = document.getElementById("save-button");
    const cancelButton = document.getElementById("cancel-button");

    saveButton.addEventListener("click", () => {
        //TODO validate data
        putConfigs(configs);
    });
    cancelButton.addEventListener("click", () => {
        configs = initConfigData();
    });

    const interfaceName = location.hash.trim().slice(1);
    if (interfaceName.length > 0)
        changeInterface(interfaceName);
});

window.addEventListener("hashchange", () => {
    const interfaceName = location.hash.trim().slice(1);
    if (interfaceName.length > 0)
        changeInterface(interfaceName);
});