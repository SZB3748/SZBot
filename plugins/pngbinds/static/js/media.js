
/**
 * @param {MediaListBounds} mlist 
 * @param {HTMLElement} dest
 */
function displayMedia(mlist, dest) {
    while (dest.children.length > 0)
        dest.firstChild.remove();

    for (const name in mlist) {
        const bounds = mlist[name];
        const item = document.createElement("div");
        item.classList.add("media-item");
        getMedia(name, true).then(bUrl => {
            if (bUrl == null) {
                item.remove();
                return;
            }
            const nameSpan = document.createElement("span");
            const img = document.createElement("img");
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
            img.alt = `media ${name}`;
            img.src = bUrl;
            img.classList.add("media-image");
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
                    mlist[name][n] = Number(i.value);
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
                    mlist[name] = {top: Number(topInput.value), right: Number(rightInput.value), bottom: Number(bottomInput.value), left: Number(leftInput.value)};
                } else {
                    topInput.required = rightInput.required = bottomInput.required = leftInput.required = false;
                    boundsInputsContainer.style.display = "none";
                    mlist[name] = null;
                }
            });

            boundsInputsContainer.append(topInput, rightInput, bottomInput, leftInput);
            boundsContainer.append(boundsSpan, boundsInput, boundsInputsContainer, saveBoundsButton);
            item.append(nameSpan, img, boundsContainer, deleteButton);
        });
        dest.appendChild(item);
    }
}

window.addEventListener("load", async () => {
    const mlist = await getMediaListBounds();
    const mediaContainer = document.getElementById("media-container");
    if (mlist != null) {
        displayMedia(mlist, mediaContainer);
    }

    /** @type {HTMLInputElement} */
    const uploadInput = document.getElementById("upload-input");
    /** @type {HTMLImageElement} */
    const uploadPreview = document.getElementById("upload-preview");
    uploadInput.addEventListener("change", () => {
        if (uploadInput.files.length < 1)
            return;

        if (uploadPreview.src) {
            URL.revokeObjectURL(uploadPreview.src);
        }

        uploadPreview.src = URL.createObjectURL(uploadInput.files[0]);
    });

    /** @type {HTMLInputElement} */
    const uploadNameInput = document.getElementById("upload-name");
    /** @type {HTMLButtonElement} */
    const uploadButton = document.getElementById("upload-button");
    uploadButton.addEventListener("click", () => {
        const name = uploadNameInput.value.trim().replaceAll(/[\t\n]/g, "    ");
        if (uploadInput.files.length < 1 || name.length < 1)
            return;
        
        const file = uploadInput.files[0];
        uploadMedia(name, file).then(ok => {
            if (ok) {
                uploadNameInput.value = "";
                uploadInput.value = "";
                uploadPreview.src = "";
                if (mediaCache.has(name)) {
                    URL.revokeObjectURL(mediaCache.get(name));
                    mediaCache.remove(name);
                }
                getMediaListBounds().then(mlist => {
                    if (mlist != null)
                        displayMedia(mlist, mediaContainer);
                });
            } else {
                alert("Failed to upload media.");
            }
        })
    });
});