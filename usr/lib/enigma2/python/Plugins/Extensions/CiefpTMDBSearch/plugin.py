# -*- coding: utf-8 -*-
#
from __future__ import print_function
import os
import re
import json
import ssl
import urllib.request
import urllib.parse
import threading
from io import BytesIO

# Enigma2 imports
from Components.config import config, ConfigSubsection, ConfigText, ConfigSelection, ConfigYesNo
from Components.Pixmap import Pixmap
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.config import configfile
from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Screens.MessageBox import MessageBox
from enigma import eTimer
from Tools.LoadPixmap import LoadPixmap

# ---------- CONFIG ----------
config.plugins.ciefptmdb = ConfigSubsection()
config.plugins.ciefptmdb.tmdb_api_key = ConfigText(default="", fixed_size=False)
config.plugins.ciefptmdb.cache_folder = ConfigSelection(default="/tmp/CiefpTMDBSearch/", choices=[
    ("/tmp/CiefpTMDBSearch/", "/tmp/CiefpTMDBSearch/"),
    ("/media/hdd/CiefpTMDBSearch/", "/media/hdd/CiefpTMDBSearch/"),
    ("/usr/lib/enigma2/python/Plugins/Extensions/CiefpTMDBSearch/", "Plugin folder")
])
config.plugins.ciefptmdb.cache_enabled = ConfigYesNo(default=True)
config.plugins.ciefptmdb.language = ConfigSelection(default="en-US", choices=[
    ("en-US", "English"),
    ("sr-RS", "Srpski"),
    ("hr-HR", "Hrvatski"),
    ("bs-BA", "Bosanski"),
    ("sk-SK", "Slovenský"),  
    ("de-DE", "Deutsch"),
    ("es-ES", "Español"),
    ("fr-FR", "Français"),
    ("it-IT", "Italiano"),
    ("ru-RBRO", "Русский"),
    ("pt-BR", "Português"),
    ("pl-PL", "Polski"),
    ("tr-TR", "Türkçe"),
    ("ar-AE", "العربية"),
    ("zh-CN", "中文")
])

# plugin dir and files
PLUGIN_NAME = "CiefpTMDBSearch"
PLUGIN_DESC = "TMDB search for movies and series with poster, rating, actors and description"
PLUGIN_VERSION = "1.0"
PLUGIN_DIR = os.path.dirname(__file__) if '__file__' in globals() else "/usr/lib/enigma2/python/Plugins/Extensions/CiefpTMDBSearch"
API_KEY_FILE = os.path.join(PLUGIN_DIR, "tmdbapikey.txt")
BACKGROUND = os.path.join(PLUGIN_DIR, "background.png")
PLACEHOLDER = os.path.join(PLUGIN_DIR, "placeholder.png")
PLUGIN_ICON = os.path.join(PLUGIN_DIR, "plugin.png")

def load_api_key_from_file():
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
                if key:
                    config.plugins.ciefptmdb.tmdb_api_key.value = key
                    config.plugins.ciefptmdb.tmdb_api_key.save()
        except Exception:
            pass

def save_api_key_to_file():
    try:
        with open(API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(config.plugins.ciefptmdb.tmdb_api_key.value.strip())
    except Exception:
        pass

def ensure_cache_folder():
    folder = config.plugins.ciefptmdb.cache_folder.value
    if not os.path.exists(folder):
        try:
            os.makedirs(folder)
        except Exception:
            pass
    return folder

ensure_cache_folder()
load_api_key_from_file()

# ---------- TMDB helpers (same logic kao pre) ----------
def _search_tmdb_movie(title, year=None, api_key=None):
    if not api_key:
        return None, None
    try:
        params = {"api_key": api_key, "query": title}
        if year:
            params["year"] = year
        url = "https://api.themoviedb.org/3/search/movie?" + urllib.parse.urlencode(params)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        results = data.get("results", [])
        return (results[0], "movie") if results else (None, None)
    except Exception:
        return None, None

def _search_tmdb_tv(title, year=None, api_key=None):
    if not api_key:
        return None, None
    try:
        params = {"api_key": api_key, "query": title}
        if year:
            params["first_air_date_year"] = year
        url = "https://api.themoviedb.org/3/search/tv?" + urllib.parse.urlencode(params)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        results = data.get("results", [])
        return (results[0], "tv") if results else (None, None)
    except Exception:
        return None, None
        
def _get_media_details(media_id, media_type, api_key):
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={api_key}&language={language}&append_to_response=credits"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except:
        return None        

def download_poster_async(poster_path, media_id, media_type, callback):
    if not poster_path or not media_id:
        callback(None)
        return
    if not config.plugins.ciefptmdb.cache_enabled.value:
        callback(None)
        return
    def download_thread():
        try:
            filename = ("movie_" if media_type == "movie" else "tv_") + f"{media_id}_{os.path.basename(poster_path)}"
            folder = ensure_cache_folder()
            fname = os.path.join(folder, filename)
            if os.path.exists(fname):
                callback(fname)
                return
            base = "https://image.tmdb.org/t/p/w500"
            url = base + poster_path
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            data = urllib.request.urlopen(url, context=ctx, timeout=8).read()
            with open(fname, "wb") as f:
                f.write(data)
            callback(fname)
        except Exception:
            callback(None)
    thread = threading.Thread(target=download_thread, daemon=True)
    thread.start()

def load_pixmap_safe(path):
    if path and os.path.exists(path):
        try:
            return LoadPixmap(path)
        except Exception:
            return None
    return None

def clear_all_posters():
    try:
        folder = ensure_cache_folder()
        deleted_count = 0
        total_size = 0
        for filename in os.listdir(folder):
            if filename.startswith(('movie_', 'tv_')) and (filename.endswith('.jpg') or filename.endswith('.png')):
                filepath = os.path.join(folder, filename)
                if os.path.isfile(filepath):
                    file_size = os.path.getsize(filepath)
                    os.remove(filepath)
                    deleted_count += 1
                    total_size += file_size
        return deleted_count, total_size / (1024.0 * 1024.0)
    except Exception:
        return 0, 0.0

def get_cache_info():
    try:
        folder = ensure_cache_folder()
        poster_count = 0
        total_size = 0
        for filename in os.listdir(folder):
            if filename.startswith(('movie_', 'tv_')) and (filename.endswith('.jpg') or filename.endswith('.png')):
                filepath = os.path.join(folder, filename)
                if os.path.isfile(filepath):
                    poster_count += 1
                    total_size += os.path.getsize(filepath)
        return poster_count, total_size / (1024.0 * 1024.0)
    except Exception:
        return 0, 0.0

# ---------- MAIN SEARCH SCREEN ----------
class CiefpTMDBMain(Screen):
    skin = """
        <screen position="center,center" size="1600,900" title="..:: CiefpTMDBSearch (v{version}) ::..">
            <!-- LEFT TEXT AREA 1100x800 -->
            <widget name="left_text" position="0,0" size="1100,900" font="Regular;26" />
            <!-- RIGHT POSTER 500x750 -->
            <widget name="poster" position="1100,0" size="500,750" alphatest="on" />
            <widget name="status" position="1100,820" size="500,50" font="Regular;26" foregroundColor="#00FF00" halign="left" />
            <!-- RED: Exit -->
            <ePixmap pixmap="buttons/red.png" position="50,820" size="35,35" alphatest="blend" />
            <eLabel text="Exit" position="100,810" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#800000" halign="center" valign="center" transparent="0" />
            <!-- GREEN: Placeholder for future -->
            <ePixmap pixmap="buttons/green.png" position="300,820" size="35,35" alphatest="blend" />
            <eLabel text="Search Movies" position="350,810" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#008000" halign="center" valign="center" transparent="0" />
            <!-- YELLOW: Search -->
            <ePixmap pixmap="buttons/yellow.png" position="550,820" size="35,35" alphatest="blend" />
            <eLabel text="Search Series" position="600,810" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#808000" halign="center" valign="center" transparent="0" />
            <!-- BLUE: Settings -->
            <ePixmap pixmap="buttons/blue.png" position="800,820" size="35,35" alphatest="blend" />
            <eLabel text="Settings" position="850,810" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#000080" halign="center" valign="center" transparent="0" />
        </screen>
    """ .format(version=PLUGIN_VERSION)

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        self["left_text"] = Label("CiefpTMDBSearch\n\nPress GREEN to search for movies.\nPress YELLOW to search for series.")
        self["poster"] = Pixmap()
        self["status"] = Label("Ready")

        # simple action map (create once)
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"],
        {
            "cancel": self.close,
            "red": self.close,
            "green": self.search_movies,
            "yellow": self.search_series,
            "blue": self.open_settings
        }, -1)

        # Timer for poster download timeout
        self.download_timer = eTimer()
        self.download_timer.timeout.get().append(self._download_timeout)
        self.download_in_progress = False

        # current media info
        self.media_id = None
        self.media_type = None
        self.poster_path = None

        # show placeholder on start
        self.onLayoutFinish.append(self._show_placeholder)


        self.onClose.append(self.__onClose)

    def _show_placeholder(self):
        print("[DEBUG] Trying to load placeholder:", PLACEHOLDER, os.path.exists(PLACEHOLDER))
        px = load_pixmap_safe(PLACEHOLDER)
        print("[DEBUG] Pixmap loaded:", px is not None)
        if px and self["poster"] and hasattr(self["poster"], "instance") and self["poster"].instance:
            try:
                self["poster"].instance.setPixmap(px)
                print("[DEBUG] Placeholder set successfully.")
            except Exception as e:
                print("[DEBUG] Failed to set pixmap:", e)
        else:
            print("[DEBUG] Poster instance not ready or pixmap missing.")

    def open_settings(self):
        self.session.open(SettingsScreen)

    def search_movies(self):
        def callback(text):
            if text:
                self["left_text"].setText("Searching MOVIES for: %s" % text)
                self.tmdb_search(text, mode="movie")

        self.session.openWithCallback(callback, VirtualKeyBoard, title="Search Movies", text="")

    def search_series(self):
        def callback(text):
            if text:
                self["left_text"].setText("Searching SERIES for: %s" % text)
                self.tmdb_search(text, mode="tv")

        self.session.openWithCallback(callback, VirtualKeyBoard, title="Search TV Series", text="")

    def _download_timeout(self):
        if self.download_in_progress:
            self.download_in_progress = False
            self["status"].setText("Poster download timeout")
            px = load_pixmap_safe(PLACEHOLDER)
            if px:
                try:
                    self["poster"].instance.setPixmap(px)
                except Exception:
                    pass

    def tmdb_search(self, query, mode):
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["left_text"].setText("TMDB API key not set!\nOpen Settings (BLUE) to set API key.")
            self["status"].setText("Error: API key")
            return

        # Pretraga
        if mode == "movie":
            match, media_type = _search_tmdb_movie(query, None, api_key)
        else:
            match, media_type = _search_tmdb_tv(query, None, api_key)

        if not match:
            self["left_text"].setText("No TMDB results for:\n%s" % query)
            self["status"].setText("No results")
            self._show_placeholder()
            return

        self.media_id = match.get("id")
        self.media_type = media_type
        self.poster_path = match.get("poster_path")

        # Detalji
        details = _get_media_details(self.media_id, self.media_type, api_key)
        if not details:
            self["left_text"].setText("Failed to fetch details from TMDB.")
            self["status"].setText("Error fetching details")
            self._show_placeholder()
            return

        # ==================== PRIKUPLJANJE PODATAKA ====================
        display_lines = []

        # Naslov i godina
        if media_type == "movie":
            title = details.get("title", "N/A")
            original_title = details.get("original_title", "")
            year = details.get("release_date", "")[:4] if details.get("release_date") else "N/A"
            runtime = details.get("runtime")
            duration = f"{runtime} min" if runtime else "N/A"
        else:  # tv
            title = details.get("name", "N/A")
            original_title = details.get("original_name", "")
            year = details.get("first_air_date", "")[:4] if details.get("first_air_date") else "N/A"
            # Za serije uzimamo prosečno trajanje epizode
            duration = details.get("episode_run_time")
            if duration and isinstance(duration, list) and duration:
                duration = f"~{duration[0]} min/ep"
            else:
                duration = "N/A"

        # Originalni naslov ako je različit
        if original_title and original_title != title:
            display_lines.append(f"{title}")
            display_lines.append(f"Original: {original_title}")
        else:
            display_lines.append(f"{title}")

        display_lines.append(f"Year: {year}")
        display_lines.append(f"Duration: {duration}")

        # Ocena
        vote = details.get("vote_average", 0)
        if vote:
            display_lines.append(f"Rating: {vote:.1f}/10 ★")

        # Žanrovi
        genres = [g["name"] for g in details.get("genres", [])]
        if genres:
            display_lines.append(f"Genres: {', '.join(genres)}")

        # Režiser (samo za filmove) ili kreator (za serije)
        credits = details.get("credits", {})
        if media_type == "movie":
            directors = [c["name"] for c in credits.get("crew", []) if c["job"] == "Director"]
            if directors:
                director_text = "Director" if len(directors) == 1 else "Directors"
                display_lines.append(f"{director_text}: {', '.join(directors[:3])}")
        else:
            creators = [c["name"] for c in details.get("created_by", [])]
            if creators:
                display_lines.append(f"Created by: {', '.join(creators[:3])}")

        # Opis
        overview = details.get("overview", "").strip()
        if overview:
            overview = overview.replace("\r\n", " ").replace("\n", " ")
            if len(overview) > 800:
                overview = overview[:800].rsplit(" ", 1)[0] + " ..."
            display_lines.append("")
            display_lines.append("Plot:")
            display_lines.append(overview)

        # Glumci (prvih 5)
        # Glumci (prvih 5 kao na TMDB stranici)
        cast = credits.get("cast", [])[:5]
        if cast:
            display_lines.append("")
            display_lines.append("Cast:")
            for person in cast:
                char = person.get("character", "").strip()
                name = person.get("name", "").strip()
                if char:
                    display_lines.append(f"  • {name} as {char}")
                else:
                    display_lines.append(f"  • {name}")
                    
        # Prazan red na kraju za lepši izgled
        display_lines.append("")

        # ==================== PRIKAZ ====================
        self["left_text"].setText("\n".join(display_lines))

        # ==================== POSTER ====================
        if self.poster_path and config.plugins.ciefptmdb.cache_enabled.value:
            self["status"].setText("Downloading poster...")
            self.download_in_progress = True
            self.download_timer.start(12000, True)  # 12 sekundi timeout

            folder = ensure_cache_folder()
            fname = (f"movie_{self.media_id}_" if media_type == "movie" else f"tv_{self.media_id}_") + os.path.basename(self.poster_path or "none.jpg")
            local_cache = os.path.join(folder, fname)

            def poster_callback(local_path):
                try:
                    self.download_timer.stop()
                except:
                    pass
                self.download_in_progress = False
                if not local_path or not os.path.exists(local_path):
                    local_path = PLACEHOLDER
                px = load_pixmap_safe(local_path)
                if px and self["poster"].instance:
                    self["poster"].instance.setPixmap(px)
                self["status"].setText("Info loaded ✓" if local_path != PLACEHOLDER else "Info loaded")

            if os.path.exists(local_cache):
                poster_callback(local_cache)
            else:
                download_poster_async(self.poster_path, self.media_id, self.media_type, poster_callback)
        else:
            self._show_placeholder()
            self["status"].setText("Info loaded")

    def __onClose(self):
        # cleanup timer and actions
        try:
            self.download_timer.stop()
        except:
            pass
        try:
            if "actions" in self:
                self["actions"].destroy()
                del self["actions"]
        except:
            pass

    def close(self):
        try:
            if "actions" in self:
                self["actions"].destroy()
                del self["actions"]
        except:
            pass
        Screen.close(self)

# ---------- SETTINGS SCREEN (re-used, minimal changes) ----------
class SettingsScreen(Screen):
    skin = """
        <screen name="SettingsScreen" position="center,center" size="1600,800" title="..:: CiefpTMDBSearch Settings ::..">
            <widget name="status" position="20,650" size="1000,40" font="Regular;26" foregroundColor="#00FF00" />
            <widget name="background" position="1000,0" size="600,800" pixmap="%s" alphatest="on" />
            <ePixmap pixmap="buttons/red.png" position="0,720" size="35,35" alphatest="blend" />
            <eLabel text="Cancel" position="50,710" size="200,50" font="Regular;28" foregroundColor="white" backgroundColor="#800000" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/green.png" position="250,720" size="35,35" alphatest="blend" />
            <eLabel text="Save" position="300,710" size="200,50" font="Regular;28" foregroundColor="white" backgroundColor="#008000" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/yellow.png" position="500,720" size="35,35" alphatest="blend" />
            <eLabel text="API Key" position="550,710" size="200,50" font="Regular;28" foregroundColor="white" backgroundColor="#808000" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/blue.png" position="750,720" size="35,35" alphatest="blend" />
            <eLabel text="Language" position="800,710" size="200,50" font="Regular;28" foregroundColor="white" backgroundColor="#000080" halign="center" valign="center" transparent="0" />
            <widget name="menu" position="50,50" size="900,550" scrollbarMode="showOnDemand" itemHeight="50" font="Regular;28" />
        </screen>
    """ % BACKGROUND

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.menu_list = []
        self["menu"] = MenuList(self.menu_list)
        self["status"] = Label("Settings - use colors")
        self["background"] = Pixmap()
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "MenuActions"],
            {
                "cancel": self.keyCancel,
                "red": self.keyCancel,
                "green": self.keySave,
                "yellow": self.editApiKey,
                "blue": self.change_language,
                "menu": self.clearCache,
                "ok": self.keyOk
            }, -1)
        self.onLayoutFinish.append(self.buildMenu)
        self.onClose.append(self.__onClose)

    def __onClose(self):
        try:
            if "actions" in self:
                self["actions"].destroy()
                del self["actions"]
        except:
            pass
    def buildMenu(self):
        self.menu_list = []

        api_status = "✓ SET" if config.plugins.ciefptmdb.tmdb_api_key.value else "✗ NOT SET"
        self.menu_list.append(f"TMDB API Key: {api_status}")

        self.menu_list.append("Cache folder: /tmp/CiefpTMDBSearch/")

        poster_status = "YES" if config.plugins.ciefptmdb.cache_enabled.value else "NO"
        self.menu_list.append(f"Download Posters:  {poster_status}")

        # JEZIK – hardkodovano, nikad više greške
        lang_names = {
            "en-US": "English",
            "sr-RS": "Srpski",
            "hr-HR": "Hrvatski",
            "bs-BA": "Bosanski",
            "sk-SK": "Slovenský",
            "de-DE": "Deutsch",
            "es-ES": "Español",
            "fr-FR": "Français",
            "it-IT": "Italiano",
            "ru-RU": "Русский",
            "pt-BR": "Português",
            "pl-PL": "Polski",
            "tr-TR": "Türkçe",
            "ar-AE": "العربية",
            "zh-CN": "中文"
        }
        current_lang = lang_names.get(config.plugins.ciefptmdb.language.value, "English")
        self.menu_list.append(f"Description language: {current_lang}")

        poster_count, cache_size = get_cache_info()
        self.menu_list.append(f"Cache: {poster_count} posters ({cache_size:.1f} MB)")
        self.menu_list.append(">>> CLEAR ALL POSTERS (MENU button) <<<")

        self["menu"].setList(self.menu_list)

    def keyOk(self):
        idx = self["menu"].getSelectedIndex()

        if idx == 2:  # Preuzimanje postera
            config.plugins.ciefptmdb.cache_enabled.value = not config.plugins.ciefptmdb.cache_enabled.value
            self.buildMenu()

        elif idx == 3:
            choices = config.plugins.ciefptmdb.language.choices
            current = config.plugins.ciefptmdb.language.value

            # Pronađi trenutni indeks
            for i, (code, name) in enumerate(choices):
                if code == current:
                    next_i = (i + 1) % len(choices)
                    next_code, next_name = choices[next_i]
                    config.plugins.ciefptmdb.language.value = next_code
                    config.plugins.ciefptmdb.language.save()
                    configfile.save()  # OBAVEZNO!
                    self["status"].setText(f"Jezik → {next_name}")
                    self.buildMenu()  # Odmah osveži prikaz
                    return

        elif idx == 4:  # Brisanje keša
            self.clearCache()

    def change_language(self):
        lang_order = [
            "en-US", "sr-RS", "hr-HR", "bs-BA", "sk-SK",
            "de-DE", "es-ES", "fr-FR", "it-IT", "ru-RU",
            "pt-BR", "pl-PL", "tr-TR", "ar-AE", "zh-CN"
        ]

        try:
            current_idx = lang_order.index(config.plugins.ciefptmdb.language.value)
        except ValueError:
            current_idx = 0

        next_idx = (current_idx + 1) % len(lang_order)
        next_code = lang_order[next_idx]

        config.plugins.ciefptmdb.language.value = next_code
        config.plugins.ciefptmdb.language.save()
        configfile.save()

        pretty_names = {
            "en-US": "English", "sr-RS": "Srpski",     "hr-HR": "Hrvatski",
            "bs-BA": "Bosanski", "sk-SK": "Slovenský", "de-DE": "Deutsch",
            "es-ES": "Español",  "fr-FR": "Français",  "it-IT": "Italiano",
            "ru-RU": "Русский",  "pt-BR": "Português", "pl-PL": "Polski",
            "tr-TR": "Türkçe",   "ar-AE": "العربية",     "zh-CN": "中文"
        }

        self["status"].setText(f"Jezik → {pretty_names[next_code]}")
        self.buildMenu()

    def editApiKey(self):
        def callback(result):
            if result is not None:
                config.plugins.ciefptmdb.tmdb_api_key.value = result.strip()
                config.plugins.ciefptmdb.tmdb_api_key.save()
                save_api_key_to_file()
                self["status"].setText("API key updated!")
                self.buildMenu()
        current_key = config.plugins.ciefptmdb.tmdb_api_key.value
        self.session.openWithCallback(callback, VirtualKeyBoard, title="Enter TMDB API Key", text=current_key)

    def clearCache(self):
        poster_count, cache_size = get_cache_info()
        if poster_count == 0:
            self["status"].setText("Cache is already empty!")
            return
        message = f"Delete {poster_count} posters ({cache_size:.1f} MB)?\n\nThis cannot be undone!"
        def confirmation_callback(result):
            if result:
                deleted_count, freed_size = clear_all_posters()
                if deleted_count > 0:
                    self["status"].setText(f"Deleted {deleted_count} posters ({freed_size:.1f} MB)")
                    self.buildMenu()
                else:
                    self["status"].setText("No posters found to delete")
            else:
                self["status"].setText("Cache deletion cancelled")
        self.session.openWithCallback(confirmation_callback, MessageBox, message, MessageBox.TYPE_YESNO)

    def keySave(self):
        try:
            save_api_key_to_file()
            config.plugins.ciefptmdb.cache_enabled.save()
            config.plugins.ciefptmdb.language.save()
            configfile.save()
            self["status"].setText("Sve sačuvano!")
        except Exception as e:
            self["status"].setText(f"Greška: {e}")

    def keyCancel(self):
        self["status"].setText("Cancelled")
        self.close()

    def close(self):
        try:
            if "actions" in self:
                self["actions"].destroy()
                del self["actions"]
        except:
            pass
        Screen.close(self)

# ---------- plugin entry ----------
def main(session, **kwargs):
    session.open(CiefpTMDBMain)
    
def Plugins(**kwargs):
    icon = PLUGIN_ICON if os.path.exists(PLUGIN_ICON) and LoadPixmap(PLUGIN_ICON) else None
    return [PluginDescriptor(
        name="{0} v{1}".format(PLUGIN_NAME, PLUGIN_VERSION),
        description=PLUGIN_DESC,
        where=PluginDescriptor.WHERE_PLUGINMENU,
        icon=PLUGIN_ICON,
        fnc=main
    )]    
    