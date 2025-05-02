from . import medialist, statemapping
import config
import events
from flask import Blueprint, Flask, render_template, request, send_file
import os
import shutil
import traceback
from web import serve_when_loaded
from werkzeug.security import safe_join

DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(DIR, "static")
TEMPATES_DIR = os.path.join(DIR, "templates")

web_loaded = False
web_loaded_callback = lambda: web_loaded

pngbindspages_parent = Blueprint("pngbindsparent", __name__, static_folder=STATIC_DIR, static_url_path="/static/pngbinds")
pngbindspages = Blueprint("pngbinds", __name__, url_prefix="/pngbinds", template_folder=TEMPATES_DIR)
pngbindsapi = Blueprint("pngbindsapi", __name__, url_prefix="/pngbinds")

@pngbindsapi.route("/statemap.json", methods=["GET", "PUT"])
@serve_when_loaded(web_loaded_callback)
def statemap_file():
    if request.method == "PUT":
        statemap = statemapping.StateMap.__new__(statemapping.StateMap)
        try:
            statemap.__setstate__(request.get_json())
        except (KeyError, TypeError, AttributeError) as e:
            traceback.print_exception(e)
            return "", 422
        with open(statemapping.STATEMAP_FILE, "w") as f:
            statemap.dump(f, indent="    ")
        return "", 200
    elif os.path.isfile(statemapping.STATEMAP_FILE):
        return send_file(statemapping.STATEMAP_FILE)
    else:
        return {}
    
@pngbindsapi.get("/media/list")
@serve_when_loaded(web_loaded_callback)
def get_media_list():
    return [name for name in medialist.load_media_list().keys()]

@pngbindsapi.route("/media/file/<name>", methods=["GET", "POST", "DELETE"])
@serve_when_loaded(web_loaded_callback)
def get_media_file(name:str):
    if request.method == "POST":
        file = request.files["file"]
        path = safe_join(medialist.MEDIA_DIR, file.filename)
        with open(path, "wb") as f:
            shutil.copyfileobj(file, f)
        mlist = medialist.load_media_list()
        mlist[name] = path
        medialist.save_media_list(mlist)
        return "", 200
    elif request.method == "DELETE":
        mlist = medialist.load_media_list()
        path = mlist.pop(name, None)
        if path is not None:
            if os.path.isfile(path):
                os.remove(path)
            medialist.save_media_list(mlist)
            return "", 200
        return "", 404
    else:
        mlist = medialist.load_media_list()
        mpath = mlist.get(name, None)
        if isinstance(mpath, str) and os.path.isfile(mpath):
            return send_file(mpath)
        return "", 404

@pngbindspages.get("/")
@serve_when_loaded(web_loaded_callback)
def statemap_interface():
    return render_template("states.html")

@pngbindspages.get("/media")
@serve_when_loaded(web_loaded_callback)
def media_interface():
    return render_template("media.html")

def _add_if_no_bp(t:Flask|Blueprint, bp:Blueprint):
    if isinstance(t, Flask):
        it = t.blueprints.values()
    else:
        it = (b for b, _ in t._blueprints)

    for b in it:
        if b == bp:
            return False
    t.register_blueprint(bp)
    return True

def add_routes(app:Flask, api:Blueprint):
    _add_if_no_bp(pngbindspages_parent, pngbindspages)
    _add_if_no_bp(app, pngbindspages_parent)
    _add_if_no_bp(api, pngbindsapi)