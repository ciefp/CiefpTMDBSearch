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
import time
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
from enigma import eTimer, eServiceCenter, iServiceInformation, eEPGCache, eConsoleAppContainer
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
    ("ru-RU", "Русский"),
    ("pt-BR", "Português"),
    ("pl-PL", "Polski"),
    ("tr-TR", "Türkçe"),
    ("ar-AE", "العربية"),
    ("zh-CN", "中文")
])
config.plugins.ciefptmdb.auto_search_epg = ConfigYesNo(default=True)

# plugin dir and files
PLUGIN_NAME = "CiefpTMDBSearch"
PLUGIN_DESC = "TMDB search for movies and series with poster, rating, actors and description"
PLUGIN_VERSION = "1.3"
PLUGIN_DIR = os.path.dirname(__file__) if '__file__' in globals() else "/usr/lib/enigma2/python/Plugins/Extensions/CiefpTMDBSearch"
API_KEY_FILE = os.path.join(PLUGIN_DIR, "tmdbapikey.txt")
BACKGROUND = os.path.join(PLUGIN_DIR, "background.png")
PLACEHOLDER = os.path.join(PLUGIN_DIR, "placeholder.png")
PLUGIN_ICON = os.path.join(PLUGIN_DIR, "plugin.png")

VERSION_URL = "https://raw.githubusercontent.com/ciefp/CiefpTMDBSearch/main/version.txt"
UPDATE_COMMAND = "wget -q --no-check-certificate https://raw.githubusercontent.com/ciefp/CiefpTMDBSearch/main/installer.sh -O - | /bin/sh"
BACKUP_FILE = "/tmp/tmdbapikey_backup.txt"

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
# ---------- EPG Helpers ----------
def get_current_service():
    """Vraća trenutni servis (ref) koji se gleda – radi na svim modernim Enigma2 verzijama"""
    try:
        from Screens.InfoBar import InfoBar
        if InfoBar.instance:
            # Prvo probaj standardni način (OpenPLi, OpenBH, VTI...)
            playing_service = InfoBar.instance.session.nav.getCurrentlyPlayingServiceReference()
            if playing_service:
                return playing_service

            # Ako nema, probaj preko servicelist (OpenATV 7.x koristi ServiceListLegacy)
            servicelist = InfoBar.instance.servicelist
            if servicelist:
                # Novi način (OpenATV 7.4+)
                if hasattr(servicelist, "getCurrent") and callable(getattr(servicelist, "getCurrent")):
                    return servicelist.getCurrent()
                # Stari fallback
                if hasattr(servicelist, "servicelist") and servicelist.servicelist:
                    return servicelist.servicelist.getCurrentSelection()
    except Exception as e:
        print(f"[TMDB] get_current_service error: {e}")
    return None


def get_current_epg_event():
    """Vraća trenutni EPG event kao dict – radi na svim formatima"""
    service = get_current_service()
    if not service:
        return None

    try:
        epg = eEPGCache.getInstance()
        event = epg.lookupEventTime(service, -1, 0)  # current event
        if not event:
            return None

        # Podrška za sve moguće tipove
        if isinstance(event, tuple) and len(event) >= 5:
            return {
                'name': str(event[2]) if len(event) > 2 else '',
                'short': str(event[3]) if len(event) > 3 else '',
                'ext': str(event[4]) if len(event) > 4 else ''
            }
        elif isinstance(event, dict):
            return {
                'name': event.get('title') or event.get('name') or '',
                'short': event.get('short_description') or event.get('short') or '',
                'ext': event.get('extended_description') or event.get('description') or event.get('ext') or ''
            }
        else:
            # Stari objekat
            return {
                'name': event.getEventName() or '',
                'short': event.getShortDescription() or '',
                'ext': event.getExtendedDescription() or ''
            }
    except Exception as e:
        print(f"[TMDB] EPG lookup error: {e}")
        return None

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

# ---------- TMDB helpers ----------
def _search_tmdb_movie(title, year=None, api_key=None):
    if not api_key:
        return None, None
    try:
        language = config.plugins.ciefptmdb.language.value
        params = {"api_key": api_key, "query": title, "language": language}
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
    except Exception as e:
        print(f"[TMDB] Movie search error: {e}")
        return None, None

def _search_tmdb_tv(title, year=None, api_key=None):
    if not api_key:
        return None, None
    try:
        language = config.plugins.ciefptmdb.language.value
        params = {"api_key": api_key, "query": title, "language": language}
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
    except Exception as e:
        print(f"[TMDB] TV search error: {e}")
        return None, None


def _search_tmdb_multi(title, year=None, api_key=None):
    if not api_key:
        return None, None
    try:
        language = config.plugins.ciefptmdb.language.value
        params = {"api_key": api_key, "query": title, "language": language,
                  "include_adult": "false"}  # Isključi adult da izbegneš gluposti
        if year:
            params["year"] = year  # Za filmove, ili first_air_date_year za TV, ali multi podržava oba
        url = "https://api.themoviedb.org/3/search/multi?" + urllib.parse.urlencode(params)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        results = data.get("results", [])
        if not results:
            return None, None

        # Filtriraj samo movie i tv, odaberi prvi sa najvećom popularity (ili samo prvi, jer TMDB sortira)
        valid_results = [r for r in results if r.get("media_type") in ["movie", "tv"]]
        if valid_results:
            # Ako ima year, prioritet match-u
            if year:
                for res in valid_results:
                    res_year = res.get("release_date", "")[:4] if res["media_type"] == "movie" else res.get(
                        "first_air_date", "")[:4]
                    if res_year == str(year):
                        return res, res["media_type"]
            # Inače, uzmi prvi (najpopularniji)
            best = valid_results[0]
            return best, best["media_type"]
        return None, None
    except Exception as e:
        print(f"[TMDB] Multi search error: {e}")
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
    except Exception as e:
        print(f"[TMDB] Details error: {e}")
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
        except Exception as e:
            print(f"[TMDB] Poster download error: {e}")
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

def get_current_epg_event():
    service = get_current_service()
    if not service:
        return None

    epg = eEPGCache.getInstance()
    event = epg.lookupEventTime(service, -1, 0)  # Current event
    if not event:
        return None

    # Handle tuple or dict (common in newer Enigma2)
    if isinstance(event, tuple):
        # Standard tuple: (start_time, duration, name, short_desc, ext_desc, id)
        if len(event) < 6:
            return None
        return {
            'name': event[2] or '',
            'short': event[3] or '',
            'ext': event[4] or '',
            'start': event[0],
            'duration': event[1],
            'id': event[5]
        }
    elif isinstance(event, dict):
        # Already dict - normalize keys if needed
        return {
            'name': event.get('name', '') or event.get('title', ''),
            'short': event.get('short', '') or event.get('short_description', ''),
            'ext': event.get('ext', '') or event.get('extended_description', '') or event.get('description', ''),
            'start': event.get('begin', 0) or event.get('start_time', 0),
            'duration': event.get('duration', 0),
            'id': event.get('id', 0) or event.get('event_id', 0)
        }
    else:
        # If it's old object style (rare now), fallback
        try:
            return {
                'name': event.getEventName() or '',
                'short': event.getShortDescription() or '',
                'ext': event.getExtendedDescription() or '',
                'start': event.getBeginTime(),
                'duration': event.getDuration(),
                'id': event.getEventId()
            }
        except:
            print("[TMDB] Unknown event type!")
            return None

def clean_title_for_search(title):
    """Clean and prepare title for TMDB search"""
    if not title:
        return ""
    
    # Remove common prefixes and suffixes
    patterns_to_remove = [
        r'^\[.*?\]\s*',  # [HD], [4K], etc.
        r'^\(.*?\)\s*',  # (2018), etc.
        r'\s*\[.*?\]$',  # [HD] at end
        r'\s*\(.*?\)$',  # (2018) at end
        r'^Film:\s*',    # Film: prefix
        r'^Movie:\s*',   # Movie: prefix
        r'^TV\s*',       # TV prefix
        r'\s*–.*$',      # – description
        r'\s*\-.*$',     # - description
        r'\s*:.*$',      # : description
    ]
    
    cleaned_title = title
    for pattern in patterns_to_remove:
        cleaned_title = re.sub(pattern, '', cleaned_title)
    
    # Remove extra spaces
    cleaned_title = re.sub(r'\s+', ' ', cleaned_title).strip()
    
    return cleaned_title

# ---------- MAIN SEARCH SCREEN ----------
class CiefpTMDBMain(Screen):
    skin = """
        <screen position="center,center" size="1800,1000" title="..:: CiefpTMDBSearch (v{version}) ::..">
            <!-- EPG Title -->
            <widget name="epg_title" position="50,50" size="900,40" font="Regular;30" foregroundColor="yellow" backgroundColor="background" transparent="1"/>

            <!-- Title -->
            <widget name="title" position="50,100" size="900,50" font="Regular;40" foregroundColor="white" backgroundColor="background" transparent="1"/>

            <!-- Duration, Rating, Genres, Director -->
            <widget name="duration" position="50,160" size="1200,40" font="Regular;30" foregroundColor="lightgrey" backgroundColor="background" transparent="1"/>
            <widget name="rating" position="50,200" size="1200,40" font="Regular;30" foregroundColor="green" backgroundColor="background" transparent="1"/>
            <widget name="genres" position="50,240" size="1200,40" font="Regular;30" foregroundColor="blue" backgroundColor="background" transparent="1"/>
            <widget name="director" position="50,280" size="1200,40" font="Regular;30" foregroundColor="orange" backgroundColor="background" transparent="1"/>

            <!-- Plot -->
            <widget name="plot" position="50,330" size="1200,300" font="Regular;28" foregroundColor="white" backgroundColor="background" transparent="1" valign="top"/>

            <!-- Cast -->
            <widget name="cast" position="50,640" size="1200,250" font="Regular;26" foregroundColor="cyan" backgroundColor="background" transparent="1" valign="top"/>

            <!-- Poster -->
            <widget name="poster" position="1300,100" size="500,750" alphatest="blend" zPosition="2"/>
            
            <!-- Status -->
            <widget name="status" position="1350,920" size="400,50" font="Regular;26" foregroundColor="#00FF00" halign="left" />

            <!-- Buttons (as before) -->
            <ePixmap pixmap="buttons/red.png" position="50,920" size="35,35" alphatest="blend" />
            <eLabel text="Exit" position="100,910" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#800000" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/green.png" position="300,920" size="35,35" alphatest="blend" />
            <eLabel text="Search Movies" position="350,910" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#008000" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/yellow.png" position="550,920" size="35,35" alphatest="blend" />
            <eLabel text="Search Series" position="600,910" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#808000" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/blue.png" position="800,920" size="35,35" alphatest="blend" />
            <eLabel text="Auto EPG Search" position="850,910" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#000080" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/red.png" position="1050,920" size="35,35" alphatest="blend" />
            <eLabel text="MENU: Settings" position="1100,910" size="200,50" font="Regular;28" foregroundColor="white" backgroundColor="#800080" halign="center" valign="center" transparent="0"/>
        </screen>
    """.format(version=PLUGIN_VERSION)


    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session

        self["left_text"] = Label("")

        self["status"] = Label("Ready")
        self["epg_title"] = Label("")
        self["title"] = Label("")
        self["duration"] = Label("")
        self["rating"] = Label("")
        self["genres"] = Label("")
        self["director"] = Label("")
        self["plot"] = Label("")
        self["cast"] = Label("")
        self["poster"] = Pixmap()

        # Extended action map
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "MenuActions"],
        {
            "cancel": self.close,
            "red": self.close,
            "green": self.search_movies,
            "yellow": self.search_series,
            "blue": self.auto_epg_search,
            "menu": self.open_settings
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
        
        self.container = eConsoleAppContainer()
        self.container.appClosed.append(self.command_finished)
        self.container.dataAvail.append(self.version_data_avail)
        self.version_check_in_progress = False
        self.version_buffer = b''

        self.onLayoutFinish.append(self.check_for_updates)

    def check_for_updates(self):
        if self.version_check_in_progress: return
        self.version_check_in_progress = True
        self["status"].setText("Checking for updates...")
        try:
            self.container.execute(f"wget -q --timeout=10 -O - {VERSION_URL}")
        except Exception as e:
            self.version_check_in_progress = False
            self["status"].setText("Update check failed.")
            print("[CiefpTMDBSearch] Update error:", e)

    def version_data_avail(self, data):
        self.version_buffer += data

    def command_finished(self, retval):
        if self.version_check_in_progress:
            self.version_check_closed(retval)
        else:
            self.update_completed(retval)

    def version_check_closed(self, retval):
        self.version_check_in_progress = False
        if retval == 0:
            try:
                remote_version = self.version_buffer.decode().strip()
                self.version_buffer = b''
                if remote_version != PLUGIN_VERSION:
                    self.session.openWithCallback(self.start_update, MessageBox,
                        f"New version: v{remote_version}\nInstall now?", MessageBox.TYPE_YESNO)
                else:
                    self["status"].setText("The plugin is up to date.")
            except Exception as e:
                self["status"].setText("Version check failed.")
        else:
            self["status"].setText("Update check failed.")

    def start_update(self, answer):
        if not answer: 
            self["status"].setText("Update cancelled.")
            return
        if os.path.exists(API_KEY_FILE):
            shutil.copy2(API_KEY_FILE, BACKUP_FILE)
        self["status"].setText("Updating...")
        self.container.execute(UPDATE_COMMAND)

    def update_completed(self, retval):
        if os.path.exists(BACKUP_FILE):
            shutil.move(BACKUP_FILE, API_KEY_FILE)
        if retval == 0:
            self["status"].setText("Update OK! Restarting...")
            self.container.execute("sleep 2 && killall -9 enigma2")
        else:
            self["status"].setText("Update failed.")


    def _show_placeholder(self):
        px = load_pixmap_safe(PLACEHOLDER)
        if px and self["poster"] and hasattr(self["poster"], "instance") and self["poster"].instance:
            try:
                self["poster"].instance.setPixmap(px)
            except Exception:
                pass

    def open_settings(self):
        self.session.open(SettingsScreen)

    def auto_epg_search(self):
        self["status"].setText("Auto EPG Search in progress...")

        event_data = get_current_epg_event()
        if not event_data or not event_data.get('name'):
            self["status"].setText("No EPG data found!")
            return

        raw_title = event_data['name']
        description = event_data['short'] + " " + event_data['ext']
        title = re.sub(r"\s*\[.*?\]|\s*\(.*?\)|\s*-\s*.+$", "", raw_title).strip()
        title = re.sub(r"^Film[:\-]?\s*|^Movie[:\-]?\s*", "", title, flags=re.I).strip()

        # Izvlačenje godine iz naslova ili opisa
        year = None
        year_match = re.search(r"\b(19|20)\d{2}\b", raw_title + " " + description)
        if year_match:
            year = int(year_match.group(0))

        if not title:
            self["status"].setText("No title found in EPG!")
            return

        self["status"].setText(f"Searching: {title}" + (f" ({year})" if year else ""))

        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API Key not set!")
            return

        # NOVO: Koristimo multi search + pametan fallback
        result, media_type = self.multi_search_with_fallback(title, year, api_key)

        if not result:
            self["status"].setText("Nothing found on TMDB")
            return

        media_id = result["id"]
        details = _get_media_details(media_id, media_type, api_key)
        if not details:
            self["status"].setText("Error loading details")
            return

        self.display_media_info(details, media_type, raw_title)

    def display_media_info(self, details, media_type, epg_title=""):
        if not details:
            self["status"].setText("No details from TMDB")
            return

        self["status"].setText("Info loaded")

        # Naslov
        title = details.get("title") if media_type == "movie" else details.get("name", "Unknown")
        year = details.get("release_date", "")[:4] if media_type == "movie" else details.get("first_air_date", "")[:4]
        self["title"].setText(title + (f" ({year})" if year else ""))

        # EPG naslov (gore levo)
        self["epg_title"].setText(f"EPG Title: {epg_title}" if epg_title else "")

        # Ocena
        rating = details.get("vote_average", 0)
        if rating:
            self["rating"].setText(f"{rating:.1f}/10 ★")
        else:
            self["rating"].setText("N/A")

        # Trajanje
        if media_type == "movie":
            runtime = details.get("runtime")
            duration = f"{runtime} min" if runtime else "N/A"
        else:
            runtime = details.get("episode_run_time")
            if runtime and len(runtime) > 0:
                duration = f"~{runtime[0]} min/ep"
            else:
                duration = "N/A"
        self["duration"].setText(f"Duration: {duration}")

        # Žanrovi
        genres = ", ".join([g["name"] for g in details.get("genres", [])]) or "N/A"
        self["genres"].setText(f"Genres: {genres}")

        # Reditelj / Kreatori
        credits = details.get("credits", {})
        crew = credits.get("crew", [])
        directors = [c["name"] for c in crew if c["job"] == "Director"]
        creators = [c["name"] for c in crew if c["known_for_department"] == "Creator"] if media_type == "tv" else []
        if directors:
            dir_text = "Director: " + ", ".join(directors)
        elif creators:
            dir_text = "Created by: " + ", ".join(creators)
        else:
            dir_text = "N/A"
        self["director"].setText(dir_text)

        # Opis
        overview = details.get("overview", "") or "No description available."
        self["plot"].setText("Plot:\n" + overview)

        # Glumci – samo prvih 5, lepše formatirano
        cast_list = credits.get("cast", [])[:5]  # samo prvih 5
        cast_text = "Cast:\n"
        if cast_list:
            for actor in cast_list:
                character = actor.get("character", "").strip()
                name = actor["name"]
                if character:
                    cast_text += f"• {name} as {character}\n"
                else:
                    cast_text += f"• {name}\n"
        else:
            cast_text += "No cast info"
        self["cast"].setText(cast_text)

        # Poster
        poster_path = details.get("poster_path")
        media_id = details.get("id")
        if poster_path and media_id:
            download_poster_async(poster_path, media_id, media_type, self.poster_downloaded)
        else:
            placeholder = load_pixmap_safe(PLACEHOLDER)
            if placeholder:
                self["poster"].instance.setPixmap(placeholder)
            self["poster"].show()

    def poster_downloaded(self, path):
        if path and os.path.exists(path):
            pixmap = load_pixmap_safe(path)
            if pixmap:
                self["poster"].instance.setPixmap(pixmap)
                self["poster"].show()
                return

        # Ako nema postera ili greška – stavi placeholder
        placeholder = load_pixmap_safe(PLACEHOLDER)
        if placeholder:
            self["poster"].instance.setPixmap(placeholder)
        self["poster"].show()

    def multi_search_with_fallback(self, title, year, api_key):
        """Najbolji mogući search – koristi /search/multi + pametan fallback"""
        try:
            language = config.plugins.ciefptmdb.language.value
            params = {
                "api_key": api_key,
                "query": title,
                "language": language,
                "include_adult": "false"
            }
            if year:
                params["year"] = year

            url = "https://api.themoviedb.org/3/search/multi?" + urllib.parse.urlencode(params)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(url, context=ctx, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))

            results = data.get("results", [])
            if not results:
                return None, None

            # Filtriramo samo movie i tv
            candidates = [r for r in results if r.get("media_type") in ("movie", "tv")]
            if not candidates:
                return None, None

            # 1. Prioritet: tačan godišnji match
            if year:
                for c in candidates:
                    c_year = (c.get("release_date") or c.get("first_air_date") or "")[:4]
                    if c_year == str(year):
                        return c, c["media_type"]

            # 2. Prioritet: najveća popularity
            candidates.sort(key=lambda x: x.get("popularity", 0), reverse=True)
            best = candidates[0]

            # 3. Ako je film kraći od 30 min → verovatno greška, probaj samo TV
            if best["media_type"] == "movie":
                temp_details = _get_media_details(best["id"], "movie", api_key)
                runtime = temp_details.get("runtime") if temp_details else 0
                if runtime and runtime < 35:  # short film
                    tv_result = _search_tmdb_tv(title, year, api_key)
                    if tv_result[0]:
                        return tv_result

            return best, best["media_type"]

        except Exception as e:
            print(f"[TMDB] Multi search error: {e}")
            # Fallback na staru logiku ako nešto zezne
            result, mtype = _search_tmdb_movie(title, year, api_key)
            if result:
                return result, mtype
            return _search_tmdb_tv(title, year, api_key)

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
            self["status"].setText("TMDB API key not set!")
            return

        # Clear previous results
        self["title"].setText("")
        self["duration"].setText("")
        self["rating"].setText("")
        self["genres"].setText("")
        self["director"].setText("")
        self["plot"].setText("")
        self["cast"].setText("")
        self["epg_title"].setText("")

        # Search
        self["status"].setText(f"Searching {mode}...")
        if mode == "movie":
            match, media_type = _search_tmdb_movie(query, None, api_key)
        else:
            match, media_type = _search_tmdb_tv(query, None, api_key)

        if not match:
            self["status"].setText("No results found")
            self._show_placeholder()
            return

        self.media_id = match.get("id")
        self.media_type = media_type
        self.poster_path = match.get("poster_path")
        self._display_media_details(match, media_type, api_key)

    def _display_media_details(self, match, media_type, api_key, epg_info=None):
        """Display media details using proper widgets"""
        details = _get_media_details(self.media_id, self.media_type, api_key)
        if not details:
            self["status"].setText("Error fetching details")
            self._show_placeholder()
            return

        # ==================== DISPLAY DATA IN PROPER WIDGETS ====================

        # Title and year
        if media_type == "movie":
            title = details.get("title", "N/A")
            year = details.get("release_date", "")[:4] if details.get("release_date") else ""
            runtime = details.get("runtime")
            duration = f"{runtime} min" if runtime else "N/A"
        else:  # tv
            title = details.get("name", "N/A")
            year = details.get("first_air_date", "")[:4] if details.get("first_air_date") else ""
            duration_data = details.get("episode_run_time")
            if duration_data and isinstance(duration_data, list) and duration_data:
                duration = f"~{duration_data[0]} min/ep"
            else:
                duration = "N/A"

        # Set title with year
        self["title"].setText(title + (f" ({year})" if year else ""))

        # Clear EPG title for manual searches
        self["epg_title"].setText("")

        # Duration
        self["duration"].setText(f"Duration: {duration}")

        # Rating
        vote = details.get("vote_average", 0)
        if vote:
            self["rating"].setText(f"Rating: {vote:.1f}/10 ★")
        else:
            self["rating"].setText("Rating: N/A")

        # Genres
        genres = [g["name"] for g in details.get("genres", [])]
        if genres:
            self["genres"].setText(f"Genres: {', '.join(genres)}")
        else:
            self["genres"].setText("Genres: N/A")

        # Director/Creator
        credits = details.get("credits", {})
        if media_type == "movie":
            directors = [c["name"] for c in credits.get("crew", []) if c["job"] == "Director"]
            if directors:
                self["director"].setText(f"Director: {', '.join(directors[:2])}")
            else:
                self["director"].setText("Director: N/A")
        else:
            creators = [c["name"] for c in details.get("created_by", [])]
            if creators:
                self["director"].setText(f"Created by: {', '.join(creators[:2])}")
            else:
                self["director"].setText("Creator: N/A")

        # Plot
        overview = details.get("overview", "").strip()
        if overview:
            # Clean up overview text
            overview = overview.replace("\r\n", " ").replace("\n", " ")
            if len(overview) > 500:  # Limit length for display
                overview = overview[:500].rsplit(" ", 1)[0] + " ..."
            self["plot"].setText("Plot:\n" + overview)
        else:
            self["plot"].setText("Plot:\nNo description available.")

        # Cast
        cast = credits.get("cast", [])[:6]  # First 6 actors
        cast_text = "Cast:\n"
        if cast:
            for person in cast:
                char = person.get("character", "").strip()
                name = person.get("name", "").strip()
                if char:
                    cast_text += f"• {name} as {char}\n"
                else:
                    cast_text += f"• {name}\n"
        else:
            cast_text += "No cast information"

        self["cast"].setText(cast_text)

        # ==================== POSTER ====================
        if self.poster_path and config.plugins.ciefptmdb.cache_enabled.value:
            self["status"].setText("Downloading poster...")
            self.download_in_progress = True
            self.download_timer.start(12000, True)  # 12 seconds timeout

            folder = ensure_cache_folder()
            fname = (f"movie_{self.media_id}_" if media_type == "movie" else f"tv_{self.media_id}_") + os.path.basename(
                self.poster_path or "none.jpg")
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

# ---------- SETTINGS SCREEN ----------
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

        self.menu_list.append(f"Cache folder: {config.plugins.ciefptmdb.cache_folder.value}")

        poster_status = "YES" if config.plugins.ciefptmdb.cache_enabled.value else "NO"
        self.menu_list.append(f"Download Posters:  {poster_status}")

        # LANGUAGE
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

        if idx == 2:  # Download posters
            config.plugins.ciefptmdb.cache_enabled.value = not config.plugins.ciefptmdb.cache_enabled.value
            self.buildMenu()

        elif idx == 3:
            self.change_language()

        elif idx == 4:  # Clear cache
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

        self["status"].setText(f"Language → {pretty_names[next_code]}")
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
                    self["status"].setText(f"Deleted {poster_count} posters ({freed_size:.1f} MB)")
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
            self["status"].setText("All settings saved!")
        except Exception as e:
            self["status"].setText(f"Error: {e}")

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