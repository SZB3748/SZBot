
/**
 * @param {PngBindsMediaList} mlist 
 * @param {HTMLElement} dest
 */
function displayMedia(mlist, dest) {
    while (dest.children.length > 0)
        dest.firstChild.remove();

    for (const name in mlist) {
        const type = mlist[name].type;
        const bounds = mlist[name]?.bounds;
        const item = document.createElement("div");
        item.classList.add("media-item");

        const nameSpan = document.createElement("span");
        var valueElement = null;
        const deleteButton = document.createElement("button");

        const boundsContainer = document.createElement("span");
        const boundsInputsContainer = document.createElement("span");
        const boundsSpan = document.createElement("span");
        const boundsInput = document.createElement("input");
        const topInput = document.createElement("input");
        const rightInput = document.createElement("input");
        const bottomInput = document.createElement("input");
        const leftInput = document.createElement("input");

        const saveBoundsButton = document.createElement("button");
        saveBoundsButton.innerText = "Save Bounds";
        saveBoundsButton.addEventListener("click", () => {
            let ok;
            if (boundsInput.checked) {
                const bounds = mlist[name];
                ok = setMediaBounds(name, bounds.top, bounds.right, bounds.bottom, bounds.left);
            } else {
                ok = deleteMediaBounds(name);
            }
            if (!ok) {
                alert(`Failed to save bounds for media ${name}`);
            }
        });

        nameSpan.innerText = name;

        switch (type) {
        case "image": {
            const img = document.createElement("img");
            img.alt = `media ${name}`;
            getMedia(name, true).then(bUrl => {
                if (bUrl == null) {
                    item.remove();
                    return;
                }
                img.src = bUrl;
                img.classList.add("media-image");
                
            });
            valueElement = img;
            break;
        }
        case "iframe": {
            const iframe = document.createElement("iframe");
            iframe.src = mlist[name].value;
            iframe.classList.add("media-iframe");
            valueElement = iframe;
            break;
        }
        }
        deleteButton.classList.add("delete-button");
        deleteButton.title = "Delete Media";
        deleteButton.addEventListener("click", () => {
            deleteMedia(name).then(ok => {
                if (ok) {
                    item.remove();
                } else {
                    alert(`Failed to delete media ${name}`);
                }
            });
        });
        const delIcon = document.createElement("img");
        deleteButton.appendChild(delIcon);

        boundsSpan.innerText = "Bounds";
        boundsSpan.title = "Bounds will be used as padding (inner spacing) when the media is selected as a border, and margins (outer spacing) when the media is selected as content.";
        topInput.placeholder = topInput.title = "Top";
        rightInput.placeholder = rightInput.title = "Right";
        bottomInput.placeholder = bottomInput.title = "Bottom";
        leftInput.placeholder = leftInput.title = "Left";

        boundsInput.type = "checkbox";
        topInput.type = rightInput.type = bottomInput.type = leftInput.type = "number";
        topInput.step = rightInput.step = bottomInput.step = leftInput.step = "1";
        topInput.min = rightInput.min = bottomInput.min = leftInput.min = "1";
        if (bounds == null) {
            boundsInput.checked = false;
            boundsInputsContainer.style.display = "none";
        } else {
            topInput.required = rightInput.required = bottomInput.required = leftInput.required = true;
            boundsInput.checked = true;
            topInput.value = bounds.top;
            rightInput.value = bounds.right;
            bottomInput.value = bounds.bottom;
            leftInput.value = bounds.left;
        }

        const onchange = (n, i) => {
            return () => {
                mlist[name].bounds[n] = Number(i.value);
            };
        }

        topInput.addEventListener("change", onchange("top", topInput));
        rightInput.addEventListener("change", onchange("right", rightInput));
        bottomInput.addEventListener("change", onchange("bottom", bottomInput));
        leftInput.addEventListener("change", onchange("left", leftInput));

        boundsInput.addEventListener("change", () => {
            if (boundsInput.checked) {
                topInput.required = rightInput.required = bottomInput.required = leftInput.required = true;
                boundsInputsContainer.style.display = "";
                mlist[name].bounds = {top: Number(topInput.value), right: Number(rightInput.value), bottom: Number(bottomInput.value), left: Number(leftInput.value)};
            } else {
                topInput.required = rightInput.required = bottomInput.required = leftInput.required = false;
                boundsInputsContainer.style.display = "none";
                mlist[name].bounds = null;
            }
        });

        boundsInputsContainer.append(topInput, rightInput, bottomInput, leftInput);
        boundsContainer.append(boundsSpan, boundsInput, boundsInputsContainer, saveBoundsButton);
        item.appendChild(nameSpan);
        if (valueElement != null)
            item.appendChild(valueElement)
        item.append(boundsContainer, deleteButton);
        dest.appendChild(item);
    }
}

window.addEventListener("load", async () => {
    const mlist = await getMediaList();
    const mediaContainer = document.getElementById("media-container");
    if (mlist != null) {
        displayMedia(mlist, mediaContainer);
    }

    /** @type {HTMLInputElement} */
    const uploadImageInput = document.getElementById("upload-image-input");
    /** @type {HTMLInputElement} */
    const uploadIFrameInput = document.getElementById("upload-iframe-input");
    /** @type {HTMLImageElement} */
    const uploadImagePreview = document.getElementById("upload-image-preview");
    /** @type {HTMLIFrameElement} */
    const uploadIFramePreview = document.getElementById("upload-iframe-preview");

    /** @type {HTMLSelectElement} */
    const uploadType = document.getElementById("upload-type");
    let oldType = uploadType.value;
    uploadType.addEventListener("change", () => {
        document.getElementById(`${oldType}-input`).style.display = "none";
        oldType = uploadType.value;
        document.getElementById(`${oldType}-input`).style.display = "";
    });
    for (let i = 0; i < uploadType.children.length; i++) {
        /** @type {HTMLOptionElement} */
        const option = uploadType.children.item(i);
        if (option.value != uploadType.value) {
            document.getElementById(`${option.value}-input`).style.display = "none";
        }
    }

    uploadImageInput.addEventListener("change", () => {
        if (uploadImageInput.files.length < 1)
            return;

        if (uploadPreview.src) {
            URL.revokeObjectURL(uploadPreview.src);
        }

        uploadImagePreview.src = URL.createObjectURL(uploadImageInput.files[0]);
    });

    uploadIFrameInput.addEventListener("change", () => {
        uploadIFramePreview.src = uploadIFrameInput.value;
    });

    /** @type {HTMLInputElement} */
    const uploadNameInput = document.getElementById("upload-name");
    /** @type {HTMLButtonElement} */
    const uploadButton = document.getElementById("upload-button");
    uploadButton.addEventListener("click", () => {
        const name = uploadNameInput.value.trim().replaceAll(/[\t\n]/g, "    ");
        const type = uploadType.value;
        if ((type == "image" && uploadImageInput.files.length < 1) || (type == "iframe" && uploadIFrameInput.value.length < 1) || name.length < 1)
            return;
        
        const file = type == "image" ? uploadImageInput.files[0] : undefined;
        const value = type == "iframe" ? uploadIFrameInput.value : undefined;
        uploadMedia(name, type, value, file).then(ok => {
            if (ok) {
                uploadNameInput.value = "";
                uploadImageInput.value = "";
                uploadIFrameInput.value = "";
                uploadImagePreview.src = "";
                uploadIFramePreview.src = "";
                if (mediaCache.has(name)) {
                    URL.revokeObjectURL(mediaCache.get(name));
                    mediaCache.remove(name);
                }
                getMediaList().then(mlist => {
                    if (mlist != null)
                        displayMedia(mlist, mediaContainer);
                });
            } else {
                alert("Failed to upload media.");
            }
        })
    });
});