
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
 * @typedef {'null'|'boolean'|'string'|'integer'|'float'|'object'|'list'} MetaTypeName
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
 * @typedef {{fields: MetaFieldCollection, anyfield: Object<string, MetaTypeExpression>}} MetaTypeObjectOptions
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
    return [grouping, backmap];
}

/**
 * @param {any} configs
 * @param {HTMLElement} dest
 * @param {string} fieldname
 * @param {MetaField} metafield
 * @param {string} pluginName
 */
function addAllTypes(configs, dest, fieldname, metafield, pluginName) {
    if (metafield == undefined) {
        metafield = {types:{}};
    }
    if (metafield.types == undefined) {
        metafield.types = {};
    }
    for (const typename of ["null", "boolean", "string", "integer", "float", "object", "list"]) {
        if (!metafield.types[typename]) {
            metafield.types[typename] = true;
        }
    }
    return addMetaTypes(configs, dest, fieldname, metafield, pluginName);
}

/**
 * @param {any} configs
 * @param {HTMLElement} dest
 * @param {string} fieldname
 * @param {MetaField} metafield
 * @param {string} pluginName
 * @returns {Map<string, (remove: boolean|undefined) => void>}
 */
function addMetaTypes(configs, dest, fieldname, metafield, pluginName) {
    const value = configs?.[fieldname];
    const cbMap = new Map();
    /** @type {MetaTypeName} */
    let typename;
    for (typename in metafield.types) {
        const typeExpr = metafield.types[typename];
        /** @type {MetaTypeOptions} */
        let options = {};
        let excludeFlag = false;
        if (typeExpr !== true) {
            if (typeExpr === false) {
                continue; //skip
            } else if (typeof typeExpr === "object") {
                options = typeExpr;
            } else if (typeof typeExpr === "string") {
                if (typeExpr === "exclude") {
                    excludeFlag = true;
                } else {
                    console.error(`Field ${fieldname} error: bad type command ${typeExpr}`);
                    continue;
                }
            } else {
                console.error(`Field ${fieldname} error: bad type ${typeExpr}`);
                continue;
            }
        }

        const inputContainer = document.createElement("div");
        inputContainer.classList.add(`input-type-${typename}`);

        let cb = undefined;
        switch (typename) {
        case "string": {
            const stringInput = document.createElement("input");
            const lt = options["<"], le = options["<="],
                  gt = options[">"], ge = options[">="],
                  pattern = options["pattern"];
            if (lt != undefined) {
                if (le != undefined && le <= lt)
                    stringInput.maxLength = String(le);
                else
                    stringInput.maxLength = String(lt+1);
            } else if (le != undefined)
                stringInput.maxLength = String(le);
            
            if (gt != undefined) {
                if (ge != undefined && ge >= gt)
                    stringInput.minLength = String(ge);
                else
                    stringInput.minLength = String(gt+1);
            } else if (ge != undefined)
                stringInput.minLength = String(ge);

            if (pattern != undefined)
                stringInput.pattern = pattern;

            if (typeof value === "string") {
                stringInput.value = value;
            }
            const stringcb = () => {
                if (configs != undefined && stringInput.reportValidity())
                    configs[fieldname] = stringInput.value;
            };
            stringInput.addEventListener("change", () => { stringcb(); });
            if (!excludeFlag)
                cb = stringcb;
            inputContainer.appendChild(stringInput);
            break;
        }
        case "float":
        case "integer": {
            const numberInput = document.createElement("input");
            numberInput.type = "number";
            const lt = options["<"], le = options["<="],
                  gt = options[">"], ge = options[">="];
            if (lt != undefined) {
                if (le != undefined && le <= lt)
                    numberInput.max = String(le);
                else
                    numberInput.max = String(lt+1);
            } else if (le != undefined)
                numberInput.max = String(le);
            
            if (gt != undefined) {
                if (ge != undefined && ge >= gt)
                    numberInput.min = String(ge);
                else
                    numberInput.min = String(gt+1);
            } else if (ge != undefined)
                numberInput.min = String(ge);
            
            numberInput.step = typename === "float" ? "any" : "1";
            if (typeof value === "number") {
                numberInput.value = String(value);
            }
            const numbercb = () => {
                if (configs != undefined && numberInput.value.length > 0 && numberInput.reportValidity())
                    configs[fieldname] = Number(numberInput.value);
            };
            numberInput.addEventListener("change", () => { numbercb(); });
            if (!excludeFlag)
                cb = numbercb;
            inputContainer.appendChild(numberInput);
            break;
        }
        case "boolean": {
            const booleanInput = document.createElement("input");
            booleanInput.type = "checkbox";
            if (typeof value === "boolean") {
                booleanInput.checked = value;
            }
            const booleancb = () => {
                if (configs != undefined)
                    configs[fieldname] = booleanInput.checked;
            };
            booleanInput.addEventListener("change", () => { booleancb(); });
            if (!excludeFlag)
                cb = booleancb;
            inputContainer.appendChild(booleanInput);
            break;
        }
        case "null": {
            const nullInput = document.createElement("input");
            nullInput.value = "NULL";
            nullInput.readOnly = true;
            const nullcb = () => {
                if (configs != undefined)
                    configs[fieldname] = null;
            };
            nullInput.addEventListener("change", () => { nullcb(); });
            if (!excludeFlag)
                cb = nullcb;
            inputContainer.appendChild(nullInput);
            break;
        }
        case "object": {
            const container = document.createElement("div");
            const subfieldContainer = document.createElement("div");
            container.appendChild(subfieldContainer);
            const valueIsObject = typeof value === "object" && !Array.isArray(value);
            const subconfigs = valueIsObject ? value : {};
            if (options.fields != undefined) { //field collection
                /** @type {MetaFieldGrouping} */
                const subgrouping = new Map();
                const subbackmap = new Map();
                for (const fn in options.fields) {
                    subgrouping.set(fn, options.fields[fn]);
                    subbackmap.set(fn, pluginName);
                }
                createConfigDisplay(subconfigs, subgrouping, subbackmap, subfieldContainer);
            } else { //type collection
                const addField = createAnyfieldDisplay(subconfigs, options.anyfield, pluginName, subfieldContainer);
                const addFieldButton = document.createElement("button");
                addFieldButton.addEventListener("click", () => {
                    addField();
                });
                addFieldButton.innerText = "+";
                container.appendChild(addFieldButton);
            }
            if (!excludeFlag) {
                cb = () => {
                    if (configs != undefined) {
                        configs[fieldname] = subconfigs;
                    }
                };
            }
            inputContainer.appendChild(container);
            break;
        }
        case "list": {
            const container = document.createElement("div");
            const listItemContainer = document.createElement("div");
            const list = Array.isArray(value) ? value : [];
            container.appendChild(listItemContainer);
            const addItem = createListDisplay(list, options.types, pluginName, listItemContainer);
            const addItemButton = document.createElement("button");
            addItemButton.addEventListener("click", () => {
                addItem();
            });
            addItemButton.innerText = "+";
            container.appendChild(addItemButton);
            if (!excludeFlag) {
                cb = () => {
                    if (configs != undefined) {
                        configs[fieldname] = list;
                    }
                };
            }
            inputContainer.appendChild(container);
            break;
        }
        }

        if (cb === undefined) {
            if (metafield.default === undefined) {
                cb = () => {
                    delete configs[fieldname];
                }
            } else {
                cb = () => {
                    configs[fieldname] = metafield.default;
                };
            }
        }

        cbMap.set(typename, remove => {
            if (remove) {
                if (Array.isArray(configs)) {
                    configs.splice(fieldname, 1);
                } else {
                    delete configs[fieldname];
                }
            } else {
                cb();
            }
        });

        if (excludeFlag) {
            const excludeInfo = document.createElement("img");
            excludeInfo.classList.add("exclude-info");
            excludeInfo.alt = "excluded";
            excludeInfo.title = "Values for this type are excluded, and the default value is used instead.";
            inputContainer.appendChild(excludeInfo);
        }

        dest.appendChild(inputContainer);
    }

    return cbMap;
}

/**
 * @param {any} configs
 * @param {MetaFieldGrouping} grouping 
 * @param {Map<string, string>} backmap 
 * @param {HTMLElement} dest
 */
function createConfigDisplay(configs, grouping, backmap, dest) {
    const keys = new Set(grouping.keys());
    for (const name in configs) {
        keys.add(name);
    }

    keys.forEach(fieldname => {
        const fieldParent = document.createElement("div");
        const nameElm = document.createElement("span");
        const descriptionElm = document.createElement("p");
        const inputParent = document.createElement("div");
        const typeSelect = document.createElement("select");
        const addRemoveButton = document.createElement("button");
        const fieldControls = document.createElement("div");

        fieldParent.classList.add("field");
        inputParent.classList.add("field-inputs");
        fieldControls.classList.add("field-controls");

        const metafield = grouping.get(fieldname);
        const pluginName = backmap.get(fieldname);
        let cbmap;
        if (metafield?.types === undefined) {
            nameElm.innerText = fieldname;
            for (const typename of ["null", "boolean", "string", "integer", "float", "object", "list"]) {
                const typeOption = document.createElement("option");
                typeOption.value = typename;
                typeOption.innerText = typename;
                typeSelect.appendChild(typeOption);
            }
            cbmap = addAllTypes(configs, inputParent, fieldname, metafield, pluginName);
        } else {
            nameElm.innerText = metafield.name == undefined ? fieldname : metafield.name;
            if (metafield.description != null) {
                descriptionElm.innerText = metafield.description;
            }
            /** @type {MetaTypeName} */
            let typename;
            for (typename in metafield.types) {
                const typeExpr = metafield.types[typename];
                if (typeExpr === false) {
                    continue; //type explicitly not allowed
                }
                const typeOption = document.createElement("option");
                typeOption.value = typename;
                typeOption.innerText = typename;
                typeSelect.appendChild(typeOption);
            }
            cbmap = addMetaTypes(configs, inputParent, fieldname, metafield, pluginName);
        }

        const disableF = v => {
            inputParent.querySelectorAll(`:scope > .show > input, :scope > .show > select`).forEach(/** @param {HTMLInputElement|HTMLSelectElement} elm */ elm => {
                elm.disabled = v;
            });
            typeSelect.disabled = v;
            inputParent.querySelectorAll(`:scope .exclude-info`).forEach(elm => {
                elm.style.display = v ? "none" : "";
            });
        };

        const updateValue = v => {
            const cb = cbmap.get(typeSelect.value);
            if (cb) cb(v);
        }

        typeSelect.addEventListener("change", () => {
            inputParent.querySelectorAll(":scope > .show").forEach(elm => {
                elm.classList.remove("show");
            });
            inputParent.querySelectorAll(`:scope > .input-type-${typeSelect.value}`).forEach(elm => {
                elm.classList.add("show");
                updateValue();
            });
        });

        const value = configs != undefined && fieldname in configs ? configs[fieldname] : metafield?.default;
        if (value === undefined) {
            addRemoveButton.innerText = "+";
            typeSelect.value = "";
            disableF(true);
        } else {
            addRemoveButton.innerText = "-";
            const vtype = typeof value;
            switch(vtype) {
                case "string":
                case "boolean":
                    typeSelect.value = vtype;
                    break;
                case "number":
                    if (!Number.isInteger(value)) {
                        typeSelect.value = "float";
                        break;
                    }
                    //fallthrough
                case "bigint":
                    typeSelect.value = "integer";
                    break;
                case "object":
                    if (value === null) {
                        typeSelect.value = "null";
                    } else if (Array.isArray(value)) {
                        typeSelect.value = "list";
                    } else {
                        typeSelect.value = "object";
                    }
                    break;
                default:
                    console.error("Bad type", vtype, "for field", fieldname);
                    break;
            }

            inputParent.querySelectorAll(`:scope > .input-type-${typeSelect.value}`).forEach(elm => {
                elm.classList.add("show");
            });

            disableF(false);
        }
        
        addRemoveButton.addEventListener("click", () => {
            const v = addRemoveButton.innerText !== "+";
            disableF(v);
            updateValue(v);
            addRemoveButton.innerText = v ? "+" : "-";
        });

        fieldControls.append(typeSelect, inputParent, addRemoveButton);
        fieldParent.append(nameElm, descriptionElm, fieldControls);
        dest.appendChild(fieldParent);
    });
}

/**
 * @param {any} configs
 * @param {MetaTypesList|undefined} types 
 * @param {string} pluginName 
 * @param {HTMLElement} dest
 */
function createAnyfieldDisplay(configs, types, pluginName, dest) {
    /** @type {Map<string, HTMLInputElement} */
    const nameElms = new Map();
    const nameOrder = [];

    const addFields = () => {
        while (dest.children.length > 0) {
            dest.firstChild.remove();
        }
        nameOrder.forEach(addField);
    }

    /**
     * @param {string|undefined} name 
     */
    const addField = name => {
        const fieldParent = document.createElement("div");
        const nameElm = document.createElement("input");
        const inputParent = document.createElement("div");
        const typeSelect = document.createElement("select");
        const removeButton = document.createElement("button");
        const fieldControls = document.createElement("div");

        fieldParent.classList.add("field");
        inputParent.classList.add("field-inputs");
        fieldControls.classList.add("field-controls");

        /**
         * @param {string} fieldname
         */
        const manageTypes = fieldname => {
            while (inputParent.children.length > 0) {
                inputParent.firstChild.remove();
            }
            /** @type {MetaField} */
            const metafield = {
                name: fieldname,
                types: types,
                optional: true
            };

            let cbmap;
            if (types === undefined) {
                for (const typename of ["null", "boolean", "string", "integer", "float", "object", "list"]) {
                    const typeOption = document.createElement("option");
                    typeOption.value = typename;
                    typeOption.innerText = typename;
                    typeSelect.appendChild(typeOption);
                }
                cbmap = addAllTypes(configs, inputParent, fieldname, metafield, pluginName);
            } else {
                /** @type {MetaTypeName} */
                let typename;
                for (typename in types) {
                    const typeExpr = types[typename];
                    if (typeExpr === false) {
                        continue; //type explicitly not allowed
                    }
                    const typeOption = document.createElement("option");
                    typeOption.value = typename;
                    typeOption.innerText = typename;
                    typeSelect.appendChild(typeOption);
                }
                cbmap = addMetaTypes(configs, inputParent, fieldname, metafield, pluginName);
            }

            const updateValue = v => {
                const cb = cbmap.get(typeSelect.value);
                if (cb) cb(v);
            }

            typeSelect.addEventListener("change", () => {
                inputParent.querySelectorAll(":scope > .show").forEach(elm => {
                    elm.classList.remove("show");
                });
                inputParent.querySelectorAll(`:scope > .input-type-${typeSelect.value}`).forEach(elm => {
                    elm.classList.add("show");
                    updateValue();
                });
            });

            const value = configs != undefined && fieldname in configs ? configs[fieldname] : metafield?.default;
            if (value === undefined) {
                typeSelect.value = "";
            } else {
                const vtype = typeof value;
                switch(vtype) {
                    case "string":
                    case "boolean":
                        typeSelect.value = vtype;
                        break;
                    case "number":
                        if (!Number.isInteger(value)) {
                            typeSelect.value = "float";
                            break;
                        }
                        //fallthrough
                    case "bigint":
                        typeSelect.value = "integer";
                        break;
                    case "object":
                        if (value === null) {
                            typeSelect.value = "null";
                        } else if (Array.isArray(value)) {
                            typeSelect.value = "list";
                        } else {
                            typeSelect.value = "object";
                        }
                        break;
                    default:
                        console.error("Bad type", vtype, "for field", fieldname);
                        break;
                }

                inputParent.querySelectorAll(`:scope > .input-type-${typeSelect.value}`).forEach(elm => {
                    elm.classList.add("show");
                });
            }

            removeButton.innerText = "-";
            removeButton.addEventListener("click", () => {
                updateValue(true);
                fieldParent.remove();
                nameElms.delete(name);
                const nameIndex = nameOrder.indexOf(name);
                if (nameIndex >= 0) {
                    nameOrder.splice(nameIndex, 1);
                }
            });

            fieldControls.append(typeSelect, inputParent, removeButton);
            fieldParent.append(nameElm, fieldControls);
            dest.appendChild(fieldParent);
        };

        if (name != undefined) {
            nameElms.set(name, nameElm);
            nameElm.value = name;
            manageTypes(name);
        }

        const flagElms = (value, msg) => {
            nameElm.setCustomValidity(msg);
            if (value != undefined) {
                nameElms.forEach(elm => {
                    if (elm.value == value) {
                        elm.setCustomValidity(msg);
                    }
                });
            }
        };

        let badValue;
        const evaluateNameChange = () => {
            const newName = nameElm.value;
            const owner = nameElms.get(newName);
            if (owner == undefined) {
                const currentValue = configs[name];
                if (currentValue != undefined) {
                    delete configs[name];
                    nameElms.delete(name);
                    configs[newName] = currentValue;
                }
                const nameIndex = nameOrder.indexOf(name);
                if (nameIndex >= 0) {
                    nameOrder[nameIndex] = newName;
                }
                nameElms.set(newName, nameElm);
                manageTypes(newName);
                name = newName;
            } else if (owner != nameElm) {
                badValue = newName;
                flagElms(badValue, "Field names must be unique");
            }
        };

        nameElm.addEventListener("input", () => {
            flagElms(badValue, ""); //unflags elms with badValue
            badValue = undefined;
        });
        nameElm.addEventListener("change", evaluateNameChange);

        fieldParent.append(nameElm, fieldControls);
        dest.appendChild(fieldParent);
    };

    const startingKeys = Object.keys(configs || {});
    if (startingKeys.length > 0) {
        nameOrder.push(...startingKeys);
    }

    addFields();

    return addField;
}


/**
 * @param {any[]|undefined} list
 * @param {MetaTypesList|undefined} types 
 * @param {string} pluginName 
 * @param {HTMLElement} dest
 */
function createListDisplay(list, types, pluginName, dest) {
    /** @type {HTMLDivElement[]} */
    const itemOrder = [];
    const setIndexes = [];

    const popElm = elm => {
        const index = itemOrder.indexOf(elm);
        if (index >= 0) {
            itemOrder.splice(index, 1);
            setIndexes.splice(index, 1);
            list.splice(index, 1);
        }
    }

    const addItems = () => {
        while (dest.children.length > 0) {
            dest.firstChild.remove();
        }
        if (list != undefined) {
            for (let i = 0; i < list.length; i++) {
                addItem(i);
            }
        }
    }

    /**
     * @param {number|undefined} index 
     */
    const addItem = index => {
        if (index == undefined || index < 0) {
            index = itemOrder.length;
        }
        const itemParent = document.createElement("div");
        const inputParent = document.createElement("div");
        const typeSelect = document.createElement("select");
        const removeButton = document.createElement("button");
        const fieldControls = document.createElement("div");

        itemParent.classList.add("field");
        inputParent.classList.add("field-inputs");
        fieldControls.classList.add("field-controls");
        itemOrder.push(itemParent);

        let typeSelectChange;

        /** @param {number} currentIndex */
        const setIndex = currentIndex => {
            while (inputParent.children.length > 0) {
                inputParent.firstChild.remove();
            }
            while (typeSelect.children.length > 0) {
                typeSelect.firstChild.remove();
            }

            /** @type {MetaField} */
            const metafield = {
                types: types
            };

            let cbmap;
            if (types === undefined) {
                for (const typename of ["null", "boolean", "string", "integer", "float", "object", "list"]) {
                    const typeOption = document.createElement("option");
                    typeOption.value = typename;
                    typeOption.innerText = typename;
                    typeSelect.appendChild(typeOption);
                }
                cbmap = addAllTypes(list, inputParent, currentIndex, metafield, pluginName);
            } else {
                /** @type {MetaTypeName} */
                let typename;
                for (typename in types) {
                    const typeExpr = types[typename];
                    if (typeExpr === false) {
                        continue; //type explicitly not allowed
                    }
                    const typeOption = document.createElement("option");
                    typeOption.value = typename;
                    typeOption.innerText = typename;
                    typeSelect.appendChild(typeOption);
                }
                cbmap = addMetaTypes(list, inputParent, currentIndex, metafield, pluginName);
            }

            if (typeSelectChange != undefined) {
                typeSelect.removeEventListener("change", typeSelectChange);
            }
            const typechangelistener = () => {
                inputParent.querySelectorAll(":scope > .show").forEach(elm => {
                    elm.classList.remove("show");
                });
                inputParent.querySelectorAll(`:scope > .input-type-${typeSelect.value}`).forEach(elm => {
                    elm.classList.add("show");
                    const cb = cbmap.get(typeSelect.value);
                    if (cb) cb();
                });
            };
            typeSelect.addEventListener("change", typechangelistener);

            const value = list?.[currentIndex];
            if (value === undefined) {
                typeSelect.value = "";
            } else {
                const vtype = typeof value;
                switch(vtype) {
                    case "string":
                    case "boolean":
                        typeSelect.value = vtype;
                        break;
                    case "number":
                        if (!Number.isInteger(value)) {
                            typeSelect.value = "float";
                            break;
                        }
                        //fallthrough
                    case "bigint":
                        typeSelect.value = "integer";
                        break;
                    case "object":
                        if (value === null) {
                            typeSelect.value = "null";
                        } else if (Array.isArray(value)) {
                            typeSelect.value = "list";
                        } else {
                            typeSelect.value = "object";
                        }
                        break;
                    default:
                        console.error("Bad type", vtype, "for field", currentIndex);
                        break;
                }

                inputParent.querySelectorAll(`:scope > .input-type-${typeSelect.value}`).forEach(elm => {
                    elm.classList.add("show");
                });
            }
            
            return typechangelistener;
        };

        setIndexes.push(setIndex);
        typeSelectChange = setIndex(index);

        removeButton.innerText = "-";
        removeButton.addEventListener("click", () => {
            itemParent.remove();
            popElm(itemParent);
            for (let i = 0; i < list.length; i++) {
                setIndexes[i](i);
            }
        });

        fieldControls.append(typeSelect, inputParent, removeButton);
        itemParent.append(fieldControls);
        dest.appendChild(itemParent);
    };

    addItems();

    return addItem;
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
    const interfacePretty = document.getElementById("interface-pretty");
    rawTextarea.addEventListener("change", async () => {
        configs = JSON.parse(rawTextarea.value);
        const metas = await getConfigsMeta();
        const [grouping, backmap] = groupMetaFields(metas);
        while (interfacePretty.children.length > 0)
            interfacePretty.firstChild.remove();
        createConfigDisplay(configs, grouping, backmap, interfacePretty);
    });
    
    const prettyButton = document.getElementById("interface-pretty-button");
    const rawButton = document.getElementById("interface-raw-button");

    prettyButton.addEventListener("click", () => location.hash = "pretty");
    rawButton.addEventListener("click", () => location.hash = "raw");

    const saveButton = document.getElementById("save-button");
    const cancelButton = document.getElementById("cancel-button");

    saveButton.addEventListener("click", () => {
        let isValid = true;
        interfacePretty.querySelectorAll(":scope input").forEach(elm => {
            if (!elm.reportValidity() && isValid) {
                isValid = false;
                elm.scrollIntoView();
            }
        });
        if (isValid) {
            putConfigs(configs).then(r => {
                if (!r.ok) {
                    alert("Failed to save configs");
                }
            });

        }
    });
    cancelButton.addEventListener("click", () => {
        configs = initConfigData();
    });

    const interfaceName = location.hash.trim().slice(1);
    if (interfaceName.length > 0) {
        rawTextarea.value = JSON.stringify(configs, null, 4);
        changeInterface(interfaceName);
    }

    
    window.addEventListener("hashchange", () => {
        const interfaceName = location.hash.trim().slice(1);
        if (interfaceName.length > 0) {
            rawTextarea.value = JSON.stringify(configs, null, 4);
            changeInterface(interfaceName);
        }
    });
});