/** @type {StateMap} */
let statemap;
/** @type {PngBindsMediaList} */
let mlist;

/**
 * 
 * @param {string} name
 * @param {State} state
 * @param {HTMLElement} dest
 */
function createStateElement(name, state, dest) {
    const nameContainer = document.createElement("div");
    const contentContainer = document.createElement("div");
    const borderContainer = document.createElement("div");
    const changeContainer = document.createElement("div");

    const nameSpan = document.createElement("span");
    const contentSpan = document.createElement("span");
    const borderSpan = document.createElement("span");
    const changeSpanLatter = document.createElement("span");
    const changeSpanFirst = document.createElement("span");
    const changeSpanMiddle = document.createElement("span");
    const changeSpanLast = document.createElement("span");

    const nameInput = document.createElement("input");
    const contentInput = document.createElement("select");
    const borderInput = document.createElement("select");
    const changeNameInput = document.createElement("select");
    const changeTimeoutInput = document.createElement("input");

    const deleteButton = document.createElement("button");
    deleteButton.innerText = "Delete"; //TODO replace with trash icon
    deleteButton.addEventListener("click", () => {
        const currentName = nameInput.getAttribute("old-name");
        document.querySelectorAll("select.uses-state-name").forEach(/** @param {HTMLSelectElement} elm */ elm => {
            const opt = elm.querySelector(`:scope > option[value=${JSON.stringify(currentName)}`);
            opt.remove();
            if (elm.value == currentName) {
                elm.value = "";
            }
        });
        delete statemap.states[currentName];
        dest.remove();
    });

    nameSpan.innerText = "Name"
    contentSpan.innerText = "Content Name";
    borderSpan.innerText = "Border Name";
    changeSpanFirst.innerText = "Change to";
    changeSpanMiddle.innerText = "after";
    changeSpanLast.innerText = "seconds";

    nameInput.classList.add("needs-validation");
    contentInput.classList.add("needs-validation");
    borderInput.classList.add("needs-validation");
    changeNameInput.classList.add("needs-validation", "uses-state-name");
    changeTimeoutInput.classList.add("needs-validation");

    nameInput.required = true;
    nameInput.minLength = 1;
    contentInput.required = true;
    borderInput.required = true;
    // changeNameInput.required = true;     // null option value is "", so required will make it unselectable

    nameInput.value = name;
    for (const mname of mlist) {
        const contentOption = document.createElement("option");
        const borderOption = document.createElement("option");
        contentOption.text = contentOption.value = mname;
        borderOption.text = borderOption.value = mname;
        contentInput.appendChild(contentOption);
        borderInput.appendChild(borderOption);
    }
    contentInput.value = state.media?.content_name || "";
    borderInput.value = state.media?.border_name || "";

    changeTimeoutInput.type = "number";
    changeTimeoutInput.step = "any";
    const nullOption = document.createElement("option");
    nullOption.setAttribute("null-option", "");
    nullOption.text = "N/A";
    nullOption.value = "";
    nullOption.style.fontWeight = "bold";
    changeNameInput.appendChild(nullOption);

    for (const sname in statemap.states) {
        const changeNameOption = document.createElement("option");
        changeNameOption.text = changeNameOption.value = sname;
        changeNameInput.appendChild(changeNameOption);
    }
    if (state.change == null) {
        changeSpanLatter.style.display = "none";
        changeTimeoutInput.required = false;
    } else {
        changeNameInput.value = state.change.destination;
        changeTimeoutInput.value = state.change.timeout;
        changeTimeoutInput.required = true;
    }

    //event listeners

    nameInput.setAttribute("old-name", name);
    nameInput.addEventListener("input", () => {
        nameInput.setCustomValidity("");
    });
    nameInput.addEventListener("change", () => {
        const oldname = nameInput.getAttribute("old-name");
        const newname = nameInput.value;
        if (!nameInput.reportValidity() || oldname == newname)
            return;
        for (const sname in statemap.states) {
            if (nameInput.value == sname) {
                nameInput.setCustomValidity(`Name ${nameInput.value} is already in use.`);
                nameInput.reportValidity();
                return;
            }
        }
        if (oldname != null) {
            delete statemap.states[oldname];
            statemap.states[newname] = state;
            if (oldname in statemap.transitions) {
                const transitions = statemap.transitions[oldname];
                delete statemap.transitions[oldname];
                if (newname in statemap.transitions) {
                    //i dont think this should be possible, but whatever
                    statemap.transitions[newname].push(...transitions)
                } else {
                    statemap.transitions[newname] = transitions;
                }
            }
        }
        nameInput.setAttribute("old-name", newname);

        document.querySelectorAll("select.uses-state-name").forEach(/** @param {HTMLSelectElement} elm */ elm => {
            /** @type {HTMLOptionElement} */
            const opt = elm.querySelector(`:scope > option[value=${JSON.stringify(oldname)}]`);
            opt.value = opt.text = newname;
            if (elm.value == oldname)
                elm.value = newname;
        });
    });

    contentInput.addEventListener("change", () => {
        state.media.content_name = contentInput.value;
    });
    borderInput.addEventListener("change", () => {
        state.media.border_name = borderInput.value;
    });
    changeNameInput.addEventListener("change", () => {
        if (changeNameInput.value == nullOption.value) {
            changeSpanLatter.style.display = "none";
            state.change = null;
            changeTimeoutInput.required = false;
        } else {
            changeSpanLatter.style.display = "";
            state.change = {
                destination: changeNameInput.value,
                timeout: Number(changeTimeoutInput.value)
            };
            changeTimeoutInput.required = true;
        }
    });
    changeTimeoutInput.addEventListener("change", () => {
        state.change.timeout = Number(changeTimeoutInput.value);
    })

    nameContainer.append(nameSpan, nameInput, deleteButton);
    contentContainer.append(contentSpan, contentInput);
    borderContainer.append(borderSpan, borderInput);
    changeSpanLatter.append(changeSpanMiddle, changeTimeoutInput, changeSpanLast);
    changeContainer.append(changeSpanFirst, changeNameInput, changeSpanLatter);
    dest.append(nameContainer, contentContainer, borderContainer, changeContainer);
    dest.setAttribute("state-name", name);
}

/**
 * @param {string} statename
 * @param {Transition} transition
 * @param {HTMLElement} dest
 */
function createTransitionElement(statename, transition, dest) {
    const stateContainer = document.createElement("div");
    const keybindContainer = document.createElement("div");
    const modeContainer = document.createElement("div");
    const destContainer = document.createElement("div");
    const popdestContainer = document.createElement("div");

    const stateSpan = document.createElement("span");
    const keybindSpan = document.createElement("span");
    const modeSpan = document.createElement("span");
    const destSpan = document.createElement("span");
    const popdestSpan = document.createElement("span");

    const stateInput = document.createElement("select");
    const keybindInput = document.createElement("input");
    const modeInput = document.createElement("select");
    const destInput = document.createElement("select");
    const popdestInput = document.createElement("select");

    const delTransition = n => {
        if (!(n in statemap.transitions))
            return;
        const stateTransitions = statemap.transitions[n];
        for (let i = 0; i < stateTransitions.length; i++) {
            if (transition == stateTransitions[i]) {
                stateTransitions.splice(i, 1);
                break;
            }
        }
        if (stateTransitions.length < 1) {
            delete statemap.transitions[n];
        }
    };

    const deleteButton = document.createElement("button");
    deleteButton.innerText = "Delete"; //TODO replace with trash icon
    deleteButton.addEventListener("click", () => {
        if (stateInput.value in statemap.transitions) {
            delTransition(stateInput.value);
        }
        dest.remove();
    });

    stateSpan.innerText = "State";
    keybindSpan.innerText = "Keybind";
    modeSpan.innerText = "Mode";
    destSpan.innerText = "Destination";
    popdestSpan.innerText = "Release Destination";

    stateInput.classList.add("needs-validation", "uses-state-name", "state-input");
    keybindInput.classList.add("needs-validation", "keybind-input");
    modeInput.classList.add("needs-validation");
    destInput.classList.add("needs-validation", "uses-state-name");
    popdestInput.classList.add("needs-validation", "uses-state-name");

    stateInput.required = true;
    keybindInput.required = true;
    keybindInput.minLength = 1;
    modeInput.required = true;
    destInput.required = true;

    const emptyOption = () => {
        const opt = document.createElement("option");
        opt.style.display = "none";
        opt.value = opt.text = ""
        opt.disabled = true;
        return opt;
    };

    stateInput.appendChild(emptyOption());
    destInput.appendChild(emptyOption());
    popdestInput.appendChild(emptyOption());
    modeInput.appendChild(emptyOption());

    for (const sname in statemap.states) {
        const stateOption = document.createElement("option");
        const destOption = document.createElement("option");
        const popdestOption = document.createElement("option");
        stateOption.text = stateOption.value =
            destOption.text = destOption.value = 
            popdestOption.text = popdestOption.value = sname;
        stateInput.appendChild(stateOption);
        destInput.appendChild(destOption);
        popdestInput.appendChild(popdestOption);
    }
    stateInput.value = statename;
    destInput.value = transition.destination;
    popdestInput.value = transition.pop_destination || "";
    if (transition.mode == "HOLD") {
        popdestInput.required = true;
    } else {
        popdestContainer.style.display = "none";
        popdestInput.required = false;
    }
    keybindInput.value = transition.keybind;
    for (const mode of TRANSITION_MODES) {
        const modeOption = document.createElement("option");
        modeOption.text = modeOption.value = mode;
        modeInput.appendChild(modeOption);
    }
    modeInput.value = transition.mode;

    //event listeners

    stateInput.setAttribute("old-name", statename);
    stateInput.addEventListener("change", () => {
        const oldname = stateInput.getAttribute("old-name");
        const newname = stateInput.value;
        if (oldname == newname)
            return;
        delTransition(oldname);
        if (newname in statemap.transitions)
            statemap.transitions[newname].push(transition);
        else
            statemap.transitions[newname] = [transition];
        stateInput.setAttribute("old-name", stateInput.value);
    });

    keybindInput.addEventListener("input", () => {
        keybindInput.setCustomValidity("");
    });
    keybindInput.addEventListener("change", () => {
        const kb = keybindInput.value = keybindInput.value.trim();
        if (!keybindInput.reportValidity())
            return;
        transition.keybind = kb;
    });

    modeInput.addEventListener("change", () => {
        transition.mode = modeInput.value;
        if (transition.mode == "HOLD") {
            popdestContainer.style.display = "";
            popdestInput.required = true;
            transition.pop_destination = popdestInput.value;
        } else {
            popdestContainer.style.display = "none";
            popdestInput.required = false;
            transition.pop_destination = null;
        }
    });

    destInput.addEventListener("change", () => {
        transition.destination = destInput.value;
    });

    popdestInput.addEventListener("change", () => {
        transition.pop_destination = popdestInput.value;
    });

    stateContainer.append(stateSpan, stateInput, deleteButton);
    keybindContainer.append(keybindSpan, keybindInput);
    modeContainer.append(modeSpan, modeInput);
    destContainer.append(destSpan, destInput);
    popdestContainer.append(popdestSpan, popdestInput);
    dest.append(stateContainer, keybindContainer, modeContainer, destContainer, popdestContainer);
}

/**
 * @param {HTMLElement} dest
 */
function displayStates(dest) {
    while (dest.children.length > 0)
        dest.firstChild.remove();
    for (const name in statemap.states) {
        const container = document.createElement("div");
        container.classList.add("state");
        createStateElement(name, statemap.states[name], container);
        dest.appendChild(container);
    }
}

/**
 * @param {HTMLElement} dest
 */
function displayTransitions(dest) {
    while (dest.children.length > 0)
        dest.firstChild.remove();
    for (const statename in statemap.transitions) {
        const transitions = statemap.transitions[statename];
        for (const transition of transitions) {
            const container = document.createElement("div");
            container.classList.add("transition");
            createTransitionElement(statename, transition, container);
            dest.appendChild(container);
        }
    }
}

/**
 * @returns {boolean}
 */
function validateInputs() {
    let allValid = true;
    document.querySelectorAll(".needs-validation").forEach(/** @param {HTMLInputElement|HTMLSelectElement} elm */ elm => {
        allValid = allValid && elm.reportValidity();
    });
    return allValid;
}

window.addEventListener("load", async () => {
    const statesContainer = document.getElementById("states-container");
    const transitionsContainer = document.getElementById("transitions-container");
    [mlist, statemap] = await Promise.all([getMediaList(), getStatemap()]);
    if (mlist != null && statemap != null) {
        displayStates(statesContainer);
        displayTransitions(transitionsContainer);
    }

    const addStateButton = document.getElementById("add-state-button");
    addStateButton.addEventListener("click", () => {
        const container = document.createElement("div");
        container.classList.add("state");
        const basename = "New State"
        let newname = basename;
        if (statemap.states) {
            let i = 1;
            while (newname in statemap.states) {
                newname = `${basename} (${i})`;
                i++;
            }
        } else {
            statemap.states = {};
        }
        const newstate = {
            media: {
                content_name: "",
                border_name: ""
            },
            change: null
        };
        statemap.states[newname] = newstate;
        document.querySelectorAll("select.uses-state-name").forEach(/** @param {HTMLSelectElement} elm */ elm => {
            const newoption = document.createElement("option");
            newoption.text = newoption.value = newname;
            elm.appendChild(newoption);
        });
        createStateElement(newname, newstate, container);
        statesContainer.appendChild(container);
    });

    const addTransitionButton = document.getElementById("add-transition-button");
    addTransitionButton.addEventListener("click", () => {
        const container = document.createElement("div");
        container.classList.add("transition");
        if (statemap.transitions == null) {
            statemap.transitions = {};
        }
        const newtransition = {
            keybind: "",
            mode: "",
            destination: "",
            pop_destination: null
        };
        createTransitionElement("", newtransition, container);
        transitionsContainer.appendChild(container);
    });

    const saveButton = document.getElementById("save-button");
    saveButton.addEventListener("click", async () => {
        if (!validateInputs())
            return;
        const ok = await saveStatemap(statemap);
            if (!ok) {
                alert("Failed to save")
            }
        });
});