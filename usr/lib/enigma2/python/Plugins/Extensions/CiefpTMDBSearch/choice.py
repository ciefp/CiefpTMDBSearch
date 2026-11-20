# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import ssl
import threading
import urllib.request

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components.config import config
from Screens.Screen import Screen
from Tools.LoadPixmap import LoadPixmap

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
PLACEHOLDER = os.path.join(PLUGIN_DIR, "placeholder.png")


def _ensure_cache_folder():
    try:
        folder = config.plugins.ciefptmdb.cache_folder.value
    except Exception:
        folder = "/tmp/CiefpTMDBSearch/"
    if not os.path.exists(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass
    return folder


def _is_cache_enabled():
    try:
        return bool(config.plugins.ciefptmdb.cache_enabled.value)
    except Exception:
        return True


def _load_pixmap_safe(path):
    if path and os.path.exists(path):
        try:
            return LoadPixmap(path)
        except Exception:
            return None
    return None


class CiefpChoiceScreen(Screen):
    """
    FHD ekran (1920x1080) za prikaz liste izbora sa leve strane
    i postera/portreta (500x750) selektovane stavke sa desne strane.

    Format stavki u listi `items`:
      - 4-tuple: (display_text, payload, image_path, media_type)
      - 3-tuple: (display_text, payload, image_path)
      - 2-tuple: (display_text, payload)
      - dict:    {"label": ..., "payload": ..., "image_path": ..., "media_type": ...}

    Na OK vraća (display_text, payload) kroz callback, isto kao ChoiceBox.
    """

    skin = """
        <screen name="CiefpChoiceScreen" position="center,center" size="1920,1080" backgroundColor="#011a2e">
            <!-- Naslov ekrana -->
            <widget name="title" position="50,35" size="1200,55" font="Regular;38" foregroundColor="yellow" backgroundColor="#011a2e" transparent="1" />

            <!-- Lista sa leve strane -->
            <widget name="list" position="50,110" size="1200,840" scrollbarMode="showOnDemand" itemHeight="40" font="Regular;28" foregroundColor="white" backgroundColor="#011a2e" />

            <!-- Poster selektovane stavke sa desne strane (500x750) -->
            <widget name="poster" position="1320,110" size="500,750" alphatest="blend" zPosition="2" />

            <!-- Status / brojač stavki -->
            <widget name="status" position="50,995" size="1230,45" font="Regular;26" foregroundColor="#00FF00" backgroundColor="#011a2e" halign="left" valign="center" transparent="1" />
            <widget name="counter" position="1320,880" size="500,45" font="Regular;26" foregroundColor="#D3D3D3" backgroundColor="#011a2e" halign="center" valign="center" transparent="1" />

            <!-- Donja dugmad -->
            <ePixmap pixmap="buttons/red.png" position="1320,1000" size="35,35" alphatest="blend" />
            <eLabel text="Exit" position="1370,990" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#800000" halign="center" valign="center" transparent="0" />

            <ePixmap pixmap="buttons/green.png" position="1590,1000" size="35,35" alphatest="blend" />
            <eLabel text="Select (OK)" position="1640,990" size="210,50" font="Regular;26" foregroundColor="white" backgroundColor="#008000" halign="center" valign="center" transparent="0" />
        </screen>
    """

    def __init__(self, session, title="Select", list=None):
        Screen.__init__(self, session)
        self.session = session
        self.screen_title = title or "Select"
        self.raw_items = list or []
        self.normalized_items = self._normalize_items(self.raw_items)
        self._request_token = 0

        self["title"] = Label(self.screen_title)
        self["list"] = MenuList([item["label"] for item in self.normalized_items], enableWrapAround=True)
        self["poster"] = Pixmap()
        self["status"] = Label("")
        self["counter"] = Label("")

        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions", "DirectionActions"],
            {
                "ok": self.keyOk,
                "green": self.keyOk,
                "cancel": self.keyCancel,
                "red": self.keyCancel,
                "up": self.keyUp,
                "down": self.keyDown,
                "left": self.keyPageUp,
                "right": self.keyPageDown,
            },
            -1,
        )

        self.onLayoutFinish.append(self._on_layout_finish)
        self.onClose.append(self._on_close)

    def _normalize_items(self, items):
        normalized = []
        for entry in items:
            if isinstance(entry, dict):
                label = entry.get("label", "")
                payload = entry.get("payload")
                image_path = entry.get("image_path") or entry.get("poster_path") or entry.get("profile_path")
                media_type = entry.get("media_type")
            elif isinstance(entry, (tuple, list)):
                label = entry[0] if len(entry) > 0 else ""
                payload = entry[1] if len(entry) > 1 else None
                third = entry[2] if len(entry) > 2 else None
                fourth = entry[3] if len(entry) > 3 else None

                if len(entry) == 3 and third in ("movie", "tv", "person"):
                    image_path = None
                    media_type = third
                else:
                    image_path = third
                    media_type = fourth
            else:
                label = str(entry)
                payload = entry
                image_path = None
                media_type = None

            if not image_path and isinstance(payload, dict):
                image_path = payload.get("poster_path") or payload.get("profile_path")

            if not media_type:
                if isinstance(payload, dict):
                    if payload.get("media_type") in ("movie", "tv", "person"):
                        media_type = payload.get("media_type")
                    elif payload.get("profile_path") and not payload.get("poster_path"):
                        media_type = "person"
                    elif payload.get("first_air_date") or (payload.get("name") and not payload.get("title")):
                        media_type = "tv"
                    else:
                        media_type = "movie"
                else:
                    media_type = "movie"

            if isinstance(image_path, str):
                image_path = image_path.strip()
                if image_path.lower() in ("", "none", "null"):
                    image_path = None
                elif not image_path.startswith(("http://", "https://", "/")):
                    image_path = "/" + image_path

            normalized.append({
                "label": label,
                "payload": payload,
                "image_path": image_path,
                "media_type": media_type,
            })
        return normalized

    def _on_layout_finish(self):
        self.setTitle(self.screen_title)
        self._show_placeholder()
        self._update_selection_preview()

    def _show_placeholder(self):
        px = _load_pixmap_safe(PLACEHOLDER)
        if px and "poster" in self and self["poster"].instance:
            try:
                self["poster"].instance.setPixmap(px)
                self["poster"].show()
            except Exception:
                pass

    def _set_poster_file(self, path):
        px = _load_pixmap_safe(path)
        if not px:
            self._show_placeholder()
            return
        if "poster" in self and self["poster"].instance:
            try:
                self["poster"].instance.setPixmap(px)
                self["poster"].show()
            except Exception:
                self._show_placeholder()

    def _update_selection_preview(self):
        total = len(self.normalized_items)
        if total == 0:
            self["counter"].setText("0 / 0")
            self["status"].setText("No items")
            self._show_placeholder()
            return

        idx = self["list"].getSelectedIndex()
        if idx < 0 or idx >= total:
            idx = 0

        item = self.normalized_items[idx]
        self["counter"].setText(f"{idx + 1} / {total}")
        self["status"].setText(item["label"])

        image_path = item.get("image_path")
        if not image_path:
            self._show_placeholder()
            return

        # Ako je već prosleđena lokalna putanja na disku
        if os.path.exists(image_path):
            self._set_poster_file(image_path)
            return

        if not _is_cache_enabled():
            self._show_placeholder()
            return

        media_type = item.get("media_type", "movie")
        prefix = "person_" if media_type == "person" else ("tv_" if media_type == "tv" else "movie_")
        payload = item.get("payload")
        item_id = payload.get("id") if isinstance(payload, dict) else None
        base_name = os.path.basename(image_path)
        filename = f"{prefix}{item_id}_{base_name}" if item_id else f"choice_{prefix}{base_name}"

        folder = _ensure_cache_folder()
        local_path = os.path.join(folder, filename)

        if os.path.exists(local_path):
            self._set_poster_file(local_path)
            return

        # Prikaži placeholder dok se slika preuzima u pozadini
        self._show_placeholder()
        self._request_token += 1
        current_token = self._request_token

        def _download_worker(req_token=current_token, img_rel=image_path, m_type=media_type, target=local_path):
            try:
                if img_rel.startswith(("http://", "https://")):
                    url = img_rel
                else:
                    size_seg = "h632" if m_type == "person" else "w500"
                    url = f"https://image.tmdb.org/t/p/{size_seg}{img_rel}"

                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                data = urllib.request.urlopen(url, context=ctx, timeout=8).read()
                if not data:
                    raise ValueError("Empty image response")

                with open(target, "wb") as f:
                    f.write(data)

                if req_token == self._request_token:
                    self._set_poster_file(target)
            except Exception as e:
                if os.path.exists(target):
                    try:
                        os.remove(target)
                    except Exception:
                        pass
                print(f"[CiefpChoiceScreen] Image download error ({url}): {e}")
                if req_token == self._request_token:
                    self._show_placeholder()


        threading.Thread(target=_download_worker, daemon=True).start()

    def keyUp(self):
        self["list"].up()
        self._update_selection_preview()

    def keyDown(self):
        self["list"].down()
        self._update_selection_preview()

    def keyPageUp(self):
        self["list"].pageUp()
        self._update_selection_preview()

    def keyPageDown(self):
        self["list"].pageDown()
        self._update_selection_preview()

    def keyOk(self):
        total = len(self.normalized_items)
        if total == 0:
            self.close(None)
            return
        idx = self["list"].getSelectedIndex()
        if idx < 0 or idx >= total:
            self.close(None)
            return
        chosen = self.normalized_items[idx]
        # Vraća (display_text, payload) isto kao ChoiceBox
        self.close((chosen["label"], chosen["payload"]))

    def keyCancel(self):
        self.close(None)

    def _on_close(self):
        try:
            if "actions" in self:
                self["actions"].destroy()
                del self["actions"]
        except Exception:
            pass