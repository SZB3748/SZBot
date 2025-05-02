
/**
 * @param {PngBindsMediaList} mlist 
 * @param {HTMLElement} dest
 */
function displayMedia(mlist, dest) {
    while (dest.children.length > 0)
        dest.firstChild.remove();

    for (const name of mlist) {
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
            nameSpan.innerText = name;
            img.alt = `media ${name}`;
            img.src = bUrl;
            img.classList.add("media-image");
            deleteButton.innerText = "Delete"; //TODO replace with trash icon
            deleteButton.addEventListener("click", () => {
                deleteMedia(name).then(ok => {
                    if (ok) {
                        item.remove();
                    } else {
                        alert(`Failed to delete media ${name}`);
                    }
                });
            });

            item.append(nameSpan, img, deleteButton);
        });
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