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
from Components.ScrollLabel import ScrollLabel
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
from Screens.ChoiceBox import ChoiceBox
from enigma import eTimer, eServiceCenter, iServiceInformation, eEPGCache, eConsoleAppContainer, eSize, ePoint
from Tools.LoadPixmap import LoadPixmap

# ---------- CONFIG ----------
config.plugins.ciefptmdb = ConfigSubsection()
config.plugins.ciefptmdb.tmdb_api_key = ConfigText(default="", fixed_size=False)
config.plugins.ciefptmdb.omdb_api_key = ConfigText(default="", fixed_size=False)  # DODAJEMO OMDb API KEY
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
    ("sl-SI", "Slovenščina"),  # DODAJ SLOVENAČKI
    ("mk-MK", "Македонски"),    # DODAJ MAKEDONSKI
    ("cs-CZ", "Čeština"),      # DODAJ ČEŠKI
    ("sk-SK", "Slovenský"),
    ("hu-HU", "Magyar"),       # DODAJ MAĐARSKI
    ("ro-RO", "Română"),       # DODAJ RUMUNSKI
    ("bg-BG", "Български"),    # DODAJ BUGARSKI
    ("el-GR", "Ελληνικά"),     # DODAJ GRČKI
    ("de-DE", "Deutsch"),
    ("fr-FR", "Français"),
    ("es-ES", "Español"),
    ("it-IT", "Italiano"),
    ("pt-PT", "Português PT"), # DODAJ PORTUGALSKI (Evropa)
    ("pt-BR", "Português BR"),
    ("nl-NL", "Nederlands"),   # DODAJ HOLANDSKI
    ("sv-SE", "Svenska"),      # DODAJ ŠVEDSKI
    ("no-NO", "Norsk"),        # DODAJ NORVEŠKI
    ("da-DK", "Dansk"),        # DODAJ DANSKI
    ("fi-FI", "Suomi"),        # DODAJ FINSKI
    ("ru-RU", "Русский"),
    ("uk-UA", "Українська"),   # DODAJ UKRAJINSKI
    ("pl-PL", "Polski"),
    ("tr-TR", "Türkçe"),
    ("ar-AE", "العربية"),
    ("he-IL", "עברית"),        # DODAJ HEBREJSKI
    ("ja-JP", "日本語"),        # DODAJ JAPANSKI
    ("ko-KR", "한국어"),        # DODAJ KOREJSKI
    ("zh-CN", "中文 (简)"),
    ("zh-TW", "中文 (繁)"),     # DODAJ KINESKI (Tradicionalni)
    ("th-TH", "ไทย"),          # DODAJ TAJLANDSKI
    ("vi-VN", "Tiếng Việt"),   # DODAJ VIJETNAMSKI
])
config.plugins.ciefptmdb.auto_search_epg = ConfigYesNo(default=True)
config.plugins.ciefptmdb.show_imdb_rating = ConfigYesNo(default=True)  # DODAJEMO opciju za IMDB rating

# plugin dir and files
PLUGIN_NAME = "CiefpTMDBSearch"
PLUGIN_DESC = "TMDB search with Popular, Trending and Top Rated sections"
PLUGIN_VERSION = "2.0"
PLUGIN_DIR = os.path.dirname(__file__) if '__file__' in globals() else "/usr/lib/enigma2/python/Plugins/Extensions/CiefpTMDBSearch"
API_KEY_FILE = os.path.join(PLUGIN_DIR, "tmdbapikey.txt")
OMDB_API_KEY_FILE = os.path.join(PLUGIN_DIR, "omdbapikey.txt")  # DODAJEMO OMDb API fajl
BACKGROUND = os.path.join(PLUGIN_DIR, "background.png")
PLACEHOLDER = os.path.join(PLUGIN_DIR, "placeholder.png")
PLUGIN_ICON = os.path.join(PLUGIN_DIR, "plugin.png")
BACKGROUND_SETTINGS = os.path.join(PLUGIN_DIR, "background_settings.png")

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

def load_omdb_api_key_from_file():
    if os.path.exists(OMDB_API_KEY_FILE):
        try:
            with open(OMDB_API_KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
                if key:
                    config.plugins.ciefptmdb.omdb_api_key.value = key
                    config.plugins.ciefptmdb.omdb_api_key.save()
        except Exception:
            pass

def save_api_key_to_file():
    try:
        with open(API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(config.plugins.ciefptmdb.tmdb_api_key.value.strip())
    except Exception:
        pass

def save_omdb_api_key_to_file():
    try:
        with open(OMDB_API_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(config.plugins.ciefptmdb.omdb_api_key.value.strip())
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
load_omdb_api_key_from_file()  # UČITAJ OMDb API KEY

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

# ---------- TMDB ADVANCED SEARCH POPULAR ----------
def get_popular_movies(api_key, page=1):
    """Dobija listu popularnih filmova (20 po stranici)"""
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/movie/popular?api_key={api_key}&language={language}&page={page}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return data.get("results", [])[:20]  # Vrati maksimalno 20
    except Exception as e:
        print(f"[TMDB] Popular movies error: {e}")
        return []

def get_popular_tv(api_key, page=1):
    """Dobija listu popularnih serija (20 po stranici)"""
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/tv/popular?api_key={api_key}&language={language}&page={page}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return data.get("results", [])[:20]
    except Exception as e:
        print(f"[TMDB] Popular TV error: {e}")
        return []
        
def get_popular_persons(api_key, page=1):
    """Dobija listu najpopularnijih osoba (glumci, režiseri...) – 20 po stranici"""
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/person/popular?api_key={api_key}&language={language}&page={page}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return data.get("results", [])[:20]
    except Exception as e:
        print(f"[TMDB] Popular persons error: {e}")
        return []    

def get_trending_all(api_key, time_window="day"):
    """Dobija 20 trending filmova/serija/osoba (mješovito)"""
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/trending/all/{time_window}?api_key={api_key}&language={language}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return data.get("results", [])[:20]
    except Exception as e:
        print(f"[TMDB] Trending error: {e}")
        return []

def get_top_rated_movies(api_key, page=1):
    """Dobija 20 najbolje ocenjenih filmova"""
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/movie/top_rated?api_key={api_key}&language={language}&page={page}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return data.get("results", [])[:20]
    except Exception as e:
        print(f"[TMDB] Top rated movies error: {e}")
        return []

def get_top_rated_tv(api_key, page=1):
    """Dobija 20 najbolje ocenjenih serija"""
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/tv/top_rated?api_key={api_key}&language={language}&page={page}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return data.get("results", [])[:20]
    except Exception as e:
        print(f"[TMDB] Top rated TV error: {e}")
        return []

def get_upcoming_movies(api_key, page=1):
    """Dobija 20 predstojećih filmova"""
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/movie/upcoming?api_key={api_key}&language={language}&page={page}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return data.get("results", [])[:20]
    except Exception as e:
        print(f"[TMDB] Upcoming movies error: {e}")
        return []
        
# ---------- TMDB ADVANCED HELPERS ----------
def _search_tmdb_person(name, api_key=None):
    """Pretraga glumaca i direktora"""
    if not api_key:
        return None, None
    try:
        language = config.plugins.ciefptmdb.language.value
        params = {"api_key": api_key, "query": name, "language": language}
        url = "https://api.themoviedb.org/3/search/person?" + urllib.parse.urlencode(params)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        results = data.get("results", [])
        return (results[0], "person") if results else (None, None)
    except Exception as e:
        print(f"[TMDB] Person search error: {e}")
        return None, None


def _get_person_details(person_id, api_key):
    """Dobijanje detalja o osobi"""
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/person/{person_id}?api_key={api_key}&language={language}&append_to_response=movie_credits,tv_credits"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"[TMDB] Person details error: {e}")
        return None


def download_person_photo_async(profile_path, person_id, callback):
    """Download slike glumca/direktora"""
    if not profile_path or not person_id:
        callback(None)
        return
    if not config.plugins.ciefptmdb.cache_enabled.value:
        callback(None)
        return

    def download_thread():
        try:
            filename = f"person_{person_id}_{os.path.basename(profile_path)}"
            folder = ensure_cache_folder()
            fname = os.path.join(folder, filename)

            if os.path.exists(fname):
                callback(fname)
                return

            base = "https://image.tmdb.org/t/p/h632"  # Optimalna veličina za profile
            url = base + profile_path
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            data = urllib.request.urlopen(url, context=ctx, timeout=8).read()
            with open(fname, "wb") as f:
                f.write(data)
            callback(fname)
        except Exception as e:
            print(f"[TMDB] Person photo download error: {e}")
            callback(None)

    thread = threading.Thread(target=download_thread, daemon=True)
    thread.start()

# ---------- OMDb helpers ----------
def _search_omdb(title, year=None, api_key=None):
    if not api_key:
        return None
    try:
        params = {"apikey": api_key, "t": title, "r": "json"}
        if year:
            params["y"] = year
            
        url = "http://www.omdbapi.com/?" + urllib.parse.urlencode(params)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        
        # Proveri da li je odgovor uspešan
        if data.get("Response") == "True":
            return data
        return None
    except Exception as e:
        print(f"[OMDb] Search error: {e}")
        return None

def get_imdb_rating(media_info, media_type, api_key):
    """Dobija IMDB ocenu za film/seriju"""
    if not api_key:
        return None
        
    title = media_info.get("title") if media_type == "movie" else media_info.get("name")
    year = media_info.get("release_date", "")[:4] if media_type == "movie" else media_info.get("first_air_date", "")[:4]
    
    if not title:
        return None
        
    # Prvo pokušaj sa IMDB ID ako ga imamo
    imdb_id = media_info.get("imdb_id")
    if imdb_id:
        try:
            params = {"apikey": api_key, "i": imdb_id, "r": "json"}
            url = "http://www.omdbapi.com/?" + urllib.parse.urlencode(params)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(url, context=ctx, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            
            if data.get("Response") == "True" and data.get("imdbRating") not in ["N/A", ""]:
                return data.get("imdbRating")
        except Exception:
            pass
    
    # Fallback na pretragu po naslovu
    omdb_data = _search_omdb(title, year, api_key)
    if omdb_data and omdb_data.get("imdbRating") not in ["N/A", ""]:
        return omdb_data.get("imdbRating")
    
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
        <screen position="center,center" size="1920,1080" title="..:: CiefpTMDBSearch (v{version}) ::..">
            <!-- EPG Title -->
            <widget name="epg_title" position="50,50" size="900,40" font="Regular;30" foregroundColor="yellow" backgroundColor="background" transparent="1"/>

            <!-- Title -->
            <widget name="title" position="50,100" size="900,50" font="Regular;40" foregroundColor="white" backgroundColor="background" transparent="1"/>

            <!-- Duration, Rating, Genres, Director -->
            <widget name="duration" position="50,160" size="1200,40" font="Regular;30" foregroundColor="lightgrey" backgroundColor="background" transparent="1"/>
            <widget name="rating" position="50,200" size="1200,40" font="Regular;30" foregroundColor="green" backgroundColor="background" transparent="1"/>
            <widget name="imdb_rating" position="50,240" size="1200,40" font="Regular;30" foregroundColor="#F5C518" backgroundColor="background" transparent="1"/>
            <widget name="genres" position="50,280" size="1200,40" font="Regular;30" foregroundColor="blue" backgroundColor="background" transparent="1"/>
            <widget name="director" position="50,320" size="1200,40" font="Regular;30" foregroundColor="orange" backgroundColor="background" transparent="1"/>

            <!-- Plot -->
            <widget name="plot" position="50,370" size="1200,300" font="Regular;28" foregroundColor="white" backgroundColor="background" transparent="1" valign="top"/>

            <!-- Cast -->
            <widget name="cast" position="50,650" size="1200,300" font="Regular;26" foregroundColor="cyan" backgroundColor="background" transparent="1" valign="top"/>

            <!-- Poster -->
            <widget name="poster" position="1300,100" size="500,750" alphatest="blend" zPosition="2"/>
            
            <!-- Backdrop -->
            <widget name="backdrop" position="50,100" size="1200,720" zPosition="1" alphatest="blend" />
    
            <!-- Status -->
            <widget name="status" position="1530,990" size="270,60" font="Regular;26" foregroundColor="#00FF00" halign="left" />
            
            <!-- Ažurirane oznake za dugmad -->
            <ePixmap pixmap="buttons/red.png" position="0,1000" size="35,35" alphatest="blend" />
            <eLabel text="Exit" position="50,990" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#800000" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/green.png" position="250,1000" size="35,35" alphatest="blend" />
            <eLabel text="Adv.Search" position="300,990" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#008000" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/yellow.png" position="500,1000" size="35,35" alphatest="blend" />
            <eLabel text="Cast Exp." position="550,990" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#808000" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/blue.png" position="750,1000" size="35,35" alphatest="blend" />
            <eLabel text="Auto EPG" position="800,990" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#000080" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/red.png" position="1000,1000" size="35,35" alphatest="blend" />
            <eLabel text="OK:Backdrop" position="1050,990" size="200,50" font="Regular;24" foregroundColor="white" backgroundColor="#800080" halign="center" valign="center" transparent="0"/>
            <ePixmap pixmap="buttons/green.png" position="1250,1000" size="35,35" alphatest="blend" />
            <eLabel text="MENU: Settings" position="1300,990" size="200,50" font="Regular;24" foregroundColor="white" backgroundColor="#023030" halign="center" valign="center" transparent="0"/>
        </screen>
    """.format(version=PLUGIN_VERSION)

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.display_mode = 0
        self.from_auto_epg = False
        self.current_backdrop_path = None
        self.current_media_details = None
        self.current_media_type = None
        self.current_person_details = None
        self.current_person_name = None
        self.previous_person_details = None
        self.previous_person_name = None
        self["left_text"] = Label("")
        self["status"] = Label("Ready")
        self["epg_title"] = Label("")
        self["title"] = Label("")
        self["duration"] = Label("")
        self["rating"] = Label("")
        self["imdb_rating"] = Label("") 
        self["genres"] = Label("")
        self["director"] = Label("")
        self["plot"] = Label("")
        self["cast"] = Label("")
        self["poster"] = Pixmap()
        self["backdrop"] = Pixmap()

        # Extended action map
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "MenuActions", "DirectionActions"],
                                    {
                                        "cancel": self.keyBack,  # PROMENJENO: sada poziva keyBack umesto cl
                                        "ok": self.toggle_backdrop_view,
                                        "red": self.close,
                                        "green": self.advanced_search_menu,  # Manuelna pretraga
                                        "yellow": self.auto_cast_explorer,  # AUTO Cast Explorer
                                        "blue": self.auto_epg_search,  # Auto EPG pretraga
                                        "menu": self.open_settings,
                                        "up": self.keyUp,
                                        "down": self.keyDown
                                    }, -1)

        self["backdrop"].hide()  # sakrij na početku
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
        self.onLayoutFinish.append(self.show_default_background)
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
            import shutil
            shutil.copy2(API_KEY_FILE, BACKUP_FILE)
        self["status"].setText("Updating...")
        self.container.execute(UPDATE_COMMAND)

    def update_completed(self, retval):
        if os.path.exists(BACKUP_FILE):
            import shutil
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

    def show_default_background(self):
        # Ova metoda se više ne koristi za backdrop, jer backdrop sada ima specifičnu poziciju
        # Umesto toga, samo sakrijemo backdrop
        self["backdrop"].hide()

    def download_backdrop_async(self, backdrop_path, media_id, media_type, callback):
        if not backdrop_path or not media_id:
            callback(None)
            return
        if not config.plugins.ciefptmdb.cache_enabled.value:
            callback(None)
            return

        def download_thread():
            try:
                filename = ("backdrop_movie_" if media_type == "movie" else "backdrop_tv_") + f"{media_id}_{os.path.basename(backdrop_path)}"
                folder = ensure_cache_folder()
                fname = os.path.join(folder, filename)

                if os.path.exists(fname):
                    callback(fname)
                    return

                url = "https://image.tmdb.org/t/p/w1280" + backdrop_path
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                data = urllib.request.urlopen(url, context=ctx, timeout=12).read()
                with open(fname, "wb") as f:
                    f.write(data)
                callback(fname)
            except Exception as e:
                print(f"[TMDB] Backdrop download error: {e}")
                callback(None)

        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()

    def backdrop_downloaded(self, path):
        if path and os.path.exists(path):
            self.current_backdrop_path = path
            # Uvek ažuriraj backdrop kada se download završi
            if self.display_mode == 1:
                self.show_only_backdrop()
        else:
            self.current_backdrop_path = None
            if self.display_mode == 1:
                self.show_classic_view()

    def _fetch_imdb_rating(self, media_info, media_type):
        """Dobija IMDB ocenu u pozadini i ažurira prikaz"""
        try:
            imdb_rating = get_imdb_rating(media_info, media_type, config.plugins.ciefptmdb.omdb_api_key.value)
            if imdb_rating:
                # Ažuriraj prikaz na glavnom thread-u
                self["imdb_rating"].setText(f"IMDB: {imdb_rating}/10 ⭐")
            else:
                self["imdb_rating"].setText("IMDB: N/A")
        except Exception as e:
            print(f"[TMDB] IMDB rating error: {e}")
            self["imdb_rating"].setText("IMDB: Error")

    def display_media_info(self, details, media_type, epg_title=""):
        if not details:
            self["status"].setText("No details from TMDB")
            return

        self.current_media_details = details
        self.current_media_type = media_type

        self["status"].setText("Info loaded")

        # === OSNOVNE INFORMACIJE ===
        title = details.get("title") if media_type == "movie" else details.get("name", "Unknown")
        year = details.get("release_date", "")[:4] if media_type == "movie" else details.get("first_air_date", "")[:4]
        self["title"].setText(title + (f" ({year})" if year else ""))
        self["epg_title"].setText(f"EPG Title: {epg_title}" if epg_title else "")

        # TMDB RATING
        tmdb_rating = details.get("vote_average", 0)
        self["rating"].setText(f"TMDB: {tmdb_rating:.1f}/10 ★" if tmdb_rating else "TMDB: N/A")

        # IMDB RATING (dodajemo asinhrono da ne blokiramo prikaz)
        if config.plugins.ciefptmdb.show_imdb_rating.value and config.plugins.ciefptmdb.omdb_api_key.value:
            self["imdb_rating"].setText("IMDB: Loading...")
            # Pokreni IMDB pretragu u pozadini
            threading.Thread(target=self._fetch_imdb_rating, args=(details, media_type), daemon=True).start()
        else:
            self["imdb_rating"].setText("")

        # DURATION
        if media_type == "movie":
            runtime = details.get("runtime")
            duration = f"{runtime} min" if runtime else "N/A"
        else:
            runtime = details.get("episode_run_time")
            duration = f"~{runtime[0]} min/ep" if runtime and len(runtime) > 0 else "N/A"
        self["duration"].setText(f"Duration: {duration}")

        # GENRES
        genres = ", ".join([g["name"] for g in details.get("genres", [])]) or "N/A"
        self["genres"].setText(f"Genres: {genres}")

        # DIRECTOR/CREATOR
        credits = details.get("credits", {})
        crew = credits.get("crew", [])
        directors = [c["name"] for c in crew if c["job"] == "Director"]
        creators = [c["name"] for c in crew if c["known_for_department"] == "Creator"] if media_type == "tv" else []
        dir_text = "Director: " + ", ".join(directors) if directors else (
            "Created by: " + ", ".join(creators) if creators else "N/A")
        self["director"].setText(dir_text)

        # PLOT - ograniči dužinu
        overview = details.get("overview", "") or "No description available."
        if len(overview) > 500:
            overview = overview[:500] + "..."
        self["plot"].setText("Plot:\n" + overview)

        # CAST - ograniči broj glumaca
        cast_list = credits.get("cast", [])[:4]  # Samo 4 glumca
        cast_text = "Cast:\n" + ("\n".join(
            [f"• {a['name']} as {a.get('character', '')}" for a in cast_list]) if cast_list else "No cast info")
        self["cast"].setText(cast_text)

        # POSTER I BACKDROP
        poster_path = details.get("poster_path")
        media_id = details.get("id")
        if poster_path and media_id:
            download_poster_async(poster_path, media_id, media_type, self.poster_downloaded)
        else:
            self._show_placeholder()

        # BACKDROP
        backdrop_path = details.get("backdrop_path")
        if backdrop_path and media_id:
            self.download_backdrop_async(backdrop_path, media_id, media_type, self.backdrop_downloaded)
        else:
            self.current_backdrop_path = None
            self["backdrop"].hide()

    def auto_epg_search(self):
        self["status"].setText("Auto EPG Search in progress...")
        self.from_auto_epg = True
        self.display_mode = 0  # Resetuj na klasični prikaz
        self.show_classic_view()

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

        # Koristimo multi search + pametan fallback
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

    def advanced_search_menu(self):
        """Prikazuje meni za naprednu pretragu"""
        from Screens.ChoiceBox import ChoiceBox

        menu_list = [
            ("1. Search Movies", "movies"),
            ("2. Search TV Series", "series"),
            ("3. Search Actors", "actors"),
            ("4. Search Directors", "directors"),
            ("5. Search popular Movies", "popular_movies"),
            ("6. Search popular Series", "popular_series"),
            ("7. Search popular Persons", "popular_persons"),
            ("8. Search trending All (Daily)", "trending_all"),
            ("9. Search Top Rated Movies", "top_rated_movies"),       # ← NOVO
            ("10. Search Top Rated Series", "top_rated_series"),      # ← NOVO
            ("11. Search Upcoming Movies", "upcoming_movies")         # ← NOVO
        ]

        def search_callback(choice):
            if choice:
                if choice[1] == "movies":
                    self.search_movies()
                elif choice[1] == "series":
                    self.search_series()
                elif choice[1] == "actors":
                    self.search_actors()
                elif choice[1] == "directors":
                    self.search_directors()
                elif choice[1] == "popular_movies":
                    self.search_popular_movies()
                elif choice[1] == "popular_series":
                    self.search_popular_series()
                elif choice[1] == "popular_persons":
                    self.search_popular_persons()
                elif choice[1] == "trending_all":
                    self.search_trending_all()
                elif choice[1] == "top_rated_movies":                    # ← NOVO
                    self.search_top_rated_movies()
                elif choice[1] == "top_rated_series":                    # ← NOVO
                    self.search_top_rated_series()
                elif choice[1] == "upcoming_movies":               # ← NOVO
                    self.search_upcoming_movies()

        self.session.openWithCallback(search_callback, ChoiceBox,
                                      title="Advanced Search - Select Type",
                                      list=menu_list)

    def cast_explorer_menu(self):
        """Prikazuje meni za istraživanje glumačke ekipe"""
        from Screens.ChoiceBox import ChoiceBox

        # Proveri da li postoji trenutni media
        if not self.media_id or not self.media_type:
            self["status"].setText("No media loaded!")
            return

        menu_list = [
            ("⭐ Main Cast", "main_cast"),
            ("👥 Full Cast & Crew", "full_cast"),
            ("🌟 Actor Profiles", "actor_profiles")
        ]

        def cast_callback(choice):
            if choice:
                if choice[1] == "main_cast":
                    self.show_main_cast()
                elif choice[1] == "full_cast":
                    self.show_full_cast()
                elif choice[1] == "actor_profiles":
                    self.show_actor_profiles()

        self.session.openWithCallback(cast_callback, ChoiceBox,
                                      title="Cast & Crew Explorer",
                                      list=menu_list)

    def search_actors(self):
        """Pretraga glumaca"""

        def callback(text):
            if text:
                self["status"].setText(f"Searching actors: {text}")
                self.tmdb_search_person(text, "actor")

        self.session.openWithCallback(callback, VirtualKeyBoard,
                                      title="Search Actors", text="")

    def search_directors(self):
        """Pretraga direktora"""

        def callback(text):
            if text:
                self["status"].setText(f"Searching directors: {text}")
                self.tmdb_search_person(text, "director")

        self.session.openWithCallback(callback, VirtualKeyBoard,
                                      title="Search Directors", text="")

    def search_popular_movies(self):
        """Prikazuje 20 najpopularnijih filmova u ChoiceBox-u"""
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return

        self["status"].setText("Loading popular movies...")
        movies = get_popular_movies(api_key)

        if not movies:
            self["status"].setText("No popular movies found")
            return

        menu_list = []
        for movie in movies:
            title = movie.get("title", "N/A")
            year = movie.get("release_date", "")[:4]
            rating = movie.get("vote_average", 0)

            # Format ocene sa zvezdicama
            if rating >= 8:
                stars = "★★★★★"
            elif rating >= 7:
                stars = "★★★★☆"
            elif rating >= 6:
                stars = "★★★☆☆"
            elif rating >= 5:
                stars = "★★☆☆☆"
            elif rating > 0:
                stars = "★☆☆☆☆"
            else:
                stars = "☆☆☆☆☆"

            display_text = f"[Mov] {title} ({year}) {stars}"
            if rating > 0:
                display_text += f" {rating:.1f}"
            menu_list.append((display_text, movie, "movie"))

        def selected_callback(choice):
            if choice:
                selected = choice[1]
                media_id = selected.get("id")
                title = selected.get("title", "Unknown")
                self["status"].setText(f"Loading {title}...")
                details = _get_media_details(media_id, "movie", api_key)
                if details:
                    self.display_media_info(details, "movie")

        self.session.openWithCallback(selected_callback, ChoiceBox,
                                      title="Popular Movies (TMDB)",
                                      list=menu_list)

    def search_popular_series(self):
        """Prikazuje 20 najpopularnijih serija u ChoiceBox-u"""
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return

        self["status"].setText("Loading popular series...")
        series = get_popular_tv(api_key)

        if not series:
            self["status"].setText("No popular series found")
            return

        menu_list = []
        for tv in series:
            name = tv.get("name", "N/A")
            year = tv.get("first_air_date", "")[:4]
            rating = tv.get("vote_average", 0)

            # Format ocene sa zvezdicama
            if rating >= 8:
                stars = "★★★★★"
            elif rating >= 7:
                stars = "★★★★☆"
            elif rating >= 6:
                stars = "★★★☆☆"
            elif rating >= 5:
                stars = "★★☆☆☆"
            elif rating > 0:
                stars = "★☆☆☆☆"
            else:
                stars = "☆☆☆☆☆"

            display_text = f"[Ser] {name} ({year}) {stars}"
            if rating > 0:
                display_text += f" {rating:.1f}"
            menu_list.append((display_text, tv, "tv"))

        def selected_callback(choice):
            if choice:
                selected = choice[1]
                media_id = selected.get("id")
                title = selected.get("name", "Unknown")
                self["status"].setText(f"Loading {title}...")
                details = _get_media_details(media_id, "tv", api_key)
                if details:
                    self.display_media_info(details, "tv")

        self.session.openWithCallback(selected_callback, ChoiceBox,
                                      title="Popular Series (TMDB)",
                                      list=menu_list)

    def search_upcoming_movies(self):
        """Prikazuje 20 predstojećih filmova"""
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return

        self["status"].setText("Loading upcoming movies...")
        movies = get_upcoming_movies(api_key)

        if not movies:
            self["status"].setText("No upcoming movies found")
            return

        menu_list = []
        for movie in movies:
            title = movie.get("title", "N/A")
            release_date = movie.get("release_date", "")
            rating = movie.get("vote_average", 0)

            # Format datuma: YYYY-MM-DD → DD.MM.YYYY
            if release_date and len(release_date) == 10:
                try:
                    y, m, d = release_date.split("-")
                    pretty_date = f"{int(d):02d}.{int(m):02d}.{y}"
                except:
                    pretty_date = release_date
            else:
                pretty_date = "N/A"

            # Zvezdice
            if rating >= 8.5:
                stars = "★★★★★"
            elif rating >= 7.5:
                stars = "★★★★☆"
            elif rating >= 6.5:
                stars = "★★★☆☆"
            elif rating >= 5.5:
                stars = "★★☆☆☆"
            elif rating > 0:
                stars = "★☆☆☆☆"
            else:
                stars = "☆☆☆☆☆"

            display_text = f"[Upc] {title} ({pretty_date}) {stars}"
            if rating > 0:
                display_text += f" {rating:.1f}"

            menu_list.append((display_text, movie, "movie"))

        def selected_callback(choice):
            if choice:
                selected = choice[1]
                media_id = selected.get("id")
                title = selected.get("title", "Unknown")
                self["status"].setText(f"Loading {title}...")
                details = _get_media_details(media_id, "movie", api_key)
                if details:
                    self.display_media_info(details, "movie")

        self.session.openWithCallback(selected_callback, ChoiceBox,
                                      title="Upcoming Movies (TMDB)",
                                      list=menu_list)

    def search_popular_persons(self):
        """Prikazuje 20 najpopularnijih osoba u ChoiceBox-u"""
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return

        self["status"].setText("Loading popular persons...")
        persons = get_popular_persons(api_key)

        if not persons:
            self["status"].setText("No popular persons found")
            return

        menu_list = []
        for person in persons:
            name = person.get("name", "N/A")
            known_for = person.get("known_for_department", "")
            popularity = person.get("popularity", 0)

            # Prikaz poznatih uloga/filmova (kratko)
            known_titles = []
            for item in person.get("known_for", [])[:3]:
                if item["media_type"] == "movie":
                    title = item.get("title", "")
                    year = item.get("release_date", "")[:4]
                else:
                    title = item.get("name", "")
                    year = item.get("first_air_date", "")[:4]
                if title and year:
                    known_titles.append(f"{title} ({year})")
                elif title:
                    known_titles.append(title)

            known_str = ", ".join(known_titles) if known_titles else "N/A"

            # Format popularnosti sa zvezdicama
            if popularity >= 50:
                stars = "★★★★★"
            elif popularity >= 30:
                stars = "★★★★☆"
            elif popularity >= 20:
                stars = "★★★☆☆"
            elif popularity >= 10:
                stars = "★★☆☆☆"
            elif popularity > 0:
                stars = "★☆☆☆☆"
            else:
                stars = "☆☆☆☆☆"

            display_text = f"[Person] {name} • {known_for} {stars}"
            if popularity > 0:
                display_text += f" {popularity:.1f}"
            menu_list.append((display_text, person))

        def selected_callback(choice):
            if choice:
                selected = choice[1]
                person_id = selected.get("id")
                person_name = selected.get("name", "Unknown")
                person_type = selected.get("known_for_department", "Acting")  # ← Dodato
                self["status"].setText(f"Loading {person_name}...")
                details = _get_person_details(person_id, api_key)
                if details:
                    self.display_person_info(details, api_key, person_type)  # ← Sada 3 argumenta

        self.session.openWithCallback(selected_callback, ChoiceBox,
                                      title="Popular Persons (TMDB)",
                                      list=menu_list)

    def search_trending_all(self):
        """Prikazuje 20 trending naslova/osoba dnevno (mješovito)"""
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return

        self["status"].setText("Loading trending...")
        results = get_trending_all(api_key, "day")

        if not results:
            self["status"].setText("No trending results")
            return

        menu_list = []
        for item in results:
            media_type = item.get("media_type", "")
            if media_type == "movie":
                title = item.get("title", "N/A")
                year = item.get("release_date", "")[:4]
                prefix = "[Mov]"
            elif media_type == "tv":
                title = item.get("name", "N/A")
                year = item.get("first_air_date", "")[:4]
                prefix = "[Ser]"
            elif media_type == "person":
                title = item.get("name", "N/A")
                known_for = item.get("known_for_department", "")
                prefix = f"[Person] {title} • {known_for}"
                # Za osobe nema godine, pa preskočimo
                year = ""
            else:
                continue

            rating = item.get("vote_average", 0) if media_type != "person" else item.get("popularity", 0)

            # Zvezdice
            if rating >= 8 or (media_type == "person" and rating >= 50):
                stars = "★★★★★"
            elif rating >= 7 or (media_type == "person" and rating >= 30):
                stars = "★★★★☆"
            elif rating >= 6 or (media_type == "person" and rating >= 20):
                stars = "★★★☆☆"
            elif rating >= 5 or (media_type == "person" and rating >= 10):
                stars = "★★☆☆☆"
            elif rating > 0:
                stars = "★☆☆☆☆"
            else:
                stars = "☆☆☆☆☆"

            if media_type == "person":
                display_text = f"{prefix} {stars} {rating:.1f}"
            else:
                display_text = f"{prefix} {title} ({year}) {stars}"
                if rating > 0:
                    display_text += f" {rating:.1f}"

            menu_list.append((display_text, item, media_type))

        def selected_callback(choice):
            if choice:
                selected, m_type = choice[1], choice[2]
                if m_type == "person":
                    person_id = selected.get("id")
                    person_name = selected.get("name", "Unknown")
                    person_type = selected.get("known_for_department", "Acting")
                    self["status"].setText(f"Loading {person_name}...")
                    details = _get_person_details(person_id, api_key)
                    if details:
                        self.display_person_info(details, api_key, person_type)
                else:
                    media_id = selected.get("id")
                    title = selected.get("title") or selected.get("name", "Unknown")
                    self["status"].setText(f"Loading {title}...")
                    details = _get_media_details(media_id, m_type, api_key)
                    if details:
                        self.display_media_info(details, m_type)

        self.session.openWithCallback(selected_callback, ChoiceBox,
                                      title="Trending All - Daily (TMDB)",
                                      list=menu_list)

    def search_top_rated_movies(self):
        """Prikazuje 20 najbolje ocenjenih filmova"""
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return

        self["status"].setText("Loading top rated movies...")
        movies = get_top_rated_movies(api_key)

        if not movies:
            self["status"].setText("No top rated movies found")
            return

        menu_list = []
        for movie in movies:
            title = movie.get("title", "N/A")
            year = movie.get("release_date", "")[:4]
            rating = movie.get("vote_average", 0)

            # Zvezdice (pošto su top rated, biće uglavnom visoke)
            if rating >= 9.0:
                stars = "★★★★★"
            elif rating >= 8.5:
                stars = "★★★★☆"
            elif rating >= 8.0:
                stars = "★★★★☆"
            elif rating >= 7.5:
                stars = "★★★☆☆"
            else:
                stars = "★★☆☆☆"

            display_text = f"[Mov] {title} ({year}) {stars} {rating:.1f}"
            menu_list.append((display_text, movie, "movie"))

        def selected_callback(choice):
            if choice:
                selected = choice[1]
                media_id = selected.get("id")
                title = selected.get("title", "Unknown")
                self["status"].setText(f"Loading {title}...")
                details = _get_media_details(media_id, "movie", api_key)
                if details:
                    self.display_media_info(details, "movie")

        self.session.openWithCallback(selected_callback, ChoiceBox,
                                      title="Top Rated Movies (TMDB)",
                                      list=menu_list)

    def search_top_rated_series(self):
        """Prikazuje 20 najbolje ocenjenih serija"""
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return

        self["status"].setText("Loading top rated series...")
        series = get_top_rated_tv(api_key)

        if not series:
            self["status"].setText("No top rated series found")
            return

        menu_list = []
        for tv in series:
            name = tv.get("name", "N/A")
            year = tv.get("first_air_date", "")[:4]
            rating = tv.get("vote_average", 0)

            if rating >= 9.0:
                stars = "★★★★★"
            elif rating >= 8.5:
                stars = "★★★★☆"
            elif rating >= 8.0:
                stars = "★★★★☆"
            elif rating >= 7.5:
                stars = "★★★☆☆"
            else:
                stars = "★★☆☆☆"

            display_text = f"[Ser] {name} ({year}) {stars} {rating:.1f}"
            menu_list.append((display_text, tv, "tv"))

        def selected_callback(choice):
            if choice:
                selected = choice[1]
                media_id = selected.get("id")
                title = selected.get("name", "Unknown")
                self["status"].setText(f"Loading {title}...")
                details = _get_media_details(media_id, "tv", api_key)
                if details:
                    self.display_media_info(details, "tv")

        self.session.openWithCallback(selected_callback, ChoiceBox,
                                      title="Top Rated Series (TMDB)",
                                      list=menu_list)
        
    def tmdb_search_person(self, query, person_type):
        """TMDB pretraga osoba"""
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return

        # Clear previous results
        self.display_mode = 0
        self.show_classic_view()
        self.clear_display()

        self["status"].setText(f"Searching {person_type}...")
        match, media_type = _search_tmdb_person(query, api_key)

        if not match:
            self["status"].setText(f"No {person_type} found")
            self._show_placeholder()
            return

        self.current_person_name = query  # Spremi ime osobe
        self.display_person_info(match, api_key, person_type)

    def display_person_info(self, person_data, api_key, person_type):
        """Prikazuje informacije o glumcu/direktoru sa korisnim informacijama"""
        person_id = person_data.get("id")
        details = _get_person_details(person_id, api_key)

        if not details:
            self["status"].setText("Error loading person details")
            return

        self.current_person_details = details  # SPREMI DETALJE OSOBE
        self.current_person_name = details.get("name", "Unknown")
        
        # Prikaz osnovnih informacija
        name = details.get("name", "N/A")
        known_for = details.get("known_for_department", "N/A")
        birthday = details.get("birthday", "N/A")
        place_of_birth = details.get("place_of_birth", "N/A")
        biography = details.get("biography", "No biography available.")

        self["title"].setText(f"{name} ({known_for})")
        self["epg_title"].setText("")  # Clear EPG title

        # Osnovne informacije
        birth_info = f"Born: {birthday}"
        if place_of_birth and place_of_birth != "N/A":
            birth_info += f" in {place_of_birth}"
        self["duration"].setText(birth_info)

        # KORISNE INFORMACIJE - Godine karijere i filmografija
        movie_count = len(details.get("movie_credits", {}).get("cast", []))
        tv_count = len(details.get("tv_credits", {}).get("cast", []))

        career_info = ""
        if birthday:
            try:
                birth_year = int(birthday[:4])
                current_year = 2024  # Možeš da koristiš datetime.now().year ali 2024 je sigurnije
                career_years = current_year - birth_year
                career_info = f"{career_years}+ years"
            except:
                pass

        filmography_info = f"{movie_count} movies"
        if tv_count > 0:
            filmography_info += f", {tv_count} TV"

        if career_info:
            self["rating"].setText(f"{career_info} | {filmography_info}")
        else:
            self["rating"].setText(filmography_info)

        # Ostali widgeti prazni
        self["imdb_rating"].setText("")
        self["genres"].setText("")
        self["director"].setText("")

        # Biografija - koristimo plot widget
        if len(biography) > 400:
            biography = biography[:400] + "..."
        self["plot"].setText(f"Biography:\n{biography}")

        # Filmografija - POBOLJŠANO SORTIRANJE
        movie_credits = details.get("movie_credits", {}).get("cast", [])
        tv_credits = details.get("tv_credits", {}).get("cast", [])

        # Sortiraj po kombinovanom skoru (popularnost + broj glasova)
        def get_movie_score(movie):
            popularity = movie.get('popularity', 0) or 0
            vote_count = movie.get('vote_count', 0) or 0
            # Daj veću težinu broju glasova jer je to bolji pokazatelj popularnosti
            return (vote_count * 10) + popularity

        def get_tv_score(tv):
            popularity = tv.get('popularity', 0) or 0
            vote_count = tv.get('vote_count', 0) or 0
            return (vote_count * 10) + popularity

        # Sortiraj i uzmi najbolje
        movie_credits.sort(key=get_movie_score, reverse=True)
        tv_credits.sort(key=get_tv_score, reverse=True)

        top_movies = movie_credits[:4]  # Uzmi 4 najbolja filma
        top_tv = tv_credits[:2]  # Uzmi 2 najbolje TV serije

        filmography = "Known For:\n"
        if top_movies:
            filmography += "Movies:\n"
            for movie in top_movies:
                title = movie.get('title', 'N/A')
                year = movie.get('release_date', '')[:4]
                # Prikaži samo ako ima naslov
                if title and title != 'N/A':
                    filmography += f"• {title} ({year})\n"

        if top_tv:
            filmography += "TV Series:\n"
            for tv in top_tv:
                name = tv.get('name', 'N/A')
                year = tv.get('first_air_date', '')[:4]
                # Prikaži samo ako ima naslov
                if name and name != 'N/A':
                    filmography += f"• {name} ({year})\n"

        # Ako nema filmova/serija, prikaži poruku
        if not top_movies and not top_tv:
            filmography += "No notable works found"

        self["cast"].setText(filmography)

        # Download slike
        profile_path = details.get("profile_path")
        if profile_path:
            download_person_photo_async(profile_path, person_id, self.person_photo_downloaded)
        else:
            self._show_placeholder()

        self["status"].setText(f"{person_type.capitalize()} info loaded")

    def person_photo_downloaded(self, path):
        """Callback kada se photo download završi"""
        if path and os.path.exists(path):
            pixmap = load_pixmap_safe(path)
            if pixmap:
                self["poster"].instance.setPixmap(pixmap)
                self["poster"].show()
                return

        # Fallback na placeholder
        self._show_placeholder()

    def clear_display(self):
        """Čisti prikaz pre nove pretrage"""
        self["title"].setText("")
        self["duration"].setText("")
        self["rating"].setText("")
        self["imdb_rating"].setText("")
        self["genres"].setText("")
        self["director"].setText("")
        self["plot"].setText("")
        self["cast"].setText("")
        self["epg_title"].setText("")

    def show_person_filmography(self):
        """Prikazuje filmografiju glumca/režisera u ChoiceBox-u sa ocenama - sortirano po popularnosti"""
        if not hasattr(self, 'current_person_details'):
            self["status"].setText("No person details available")
            return

        person_details = self.current_person_details
        person_name = person_details.get("name", "Unknown")

        # Uzmi filmove i TV serije
        movie_credits = person_details.get("movie_credits", {}).get("cast", [])
        tv_credits = person_details.get("tv_credits", {}).get("cast", [])

        # Sortiraj po popularnosti (najpopularniji prvi)
        def get_movie_score(movie):
            popularity = movie.get('popularity', 0) or 0
            vote_count = movie.get('vote_count', 0) or 0
            # Daj veću težinu broju glasova jer je to bolji pokazatelj popularnosti
            return (vote_count * 10) + popularity

        def get_tv_score(tv):
            popularity = tv.get('popularity', 0) or 0
            vote_count = tv.get('vote_count', 0) or 0
            return (vote_count * 10) + popularity

        movie_credits.sort(key=get_movie_score, reverse=True)
        tv_credits.sort(key=get_tv_score, reverse=True)

        # Napravi listu za ChoiceBox
        menu_list = []

        # Dodaj najpopularnije filmove (prvih 8)
        for movie in movie_credits[:8]:
            title = movie.get('title', 'N/A')
            year = movie.get('release_date', '')[:4]
            rating = movie.get('vote_average', 0)

            if title and title != 'N/A':
                # Formatiraj ocenu sa zvezdicama
                if rating >= 8:
                    stars = "★★★★★"
                elif rating >= 7:
                    stars = "★★★★☆"
                elif rating >= 6:
                    stars = "★★★☆☆"
                elif rating >= 5:
                    stars = "★★☆☆☆"
                elif rating > 0:
                    stars = "★☆☆☆☆"
                else:
                    stars = "☆☆☆☆☆"  # Nema ocenu

                # SAMO NASLOV I OCENA - BEZ KARAKTERA
                if rating > 0:
                    menu_list.append((f"[Mov] {title} ({year}) {stars} {rating:.1f}", movie))
                else:
                    menu_list.append((f"[Mov] {title} ({year})", movie))

        # Dodaj najpopularnije TV serije (prvih 4)
        for tv in tv_credits[:4]:
            name = tv.get('name', 'N/A')
            year = tv.get('first_air_date', '')[:4]
            rating = tv.get('vote_average', 0)

            if name and name != 'N/A':
                # Formatiraj ocenu sa zvezdicama
                if rating >= 8:
                    stars = "★★★★★"
                elif rating >= 7:
                    stars = "★★★★☆"
                elif rating >= 6:
                    stars = "★★★☆☆"
                elif rating >= 5:
                    stars = "★★☆☆☆"
                elif rating > 0:
                    stars = "★☆☆☆☆"
                else:
                    stars = "☆☆☆☆☆"  # Nema ocenu

                # SAMO NASLOV I OCENA - BEZ KARAKTERA
                if rating > 0:
                    menu_list.append((f"[Ser] {name} ({year}) {stars} {rating:.1f}", tv))
                else:
                    menu_list.append((f"[Ser] {name} ({year})", tv))

        if not menu_list:
            self["status"].setText("No filmography available")
            return

        def media_selected(choice):
            if choice:
                selected_media = choice[1]
                media_type = "movie" if selected_media.get('title') else "tv"
                media_id = selected_media.get('id')
                media_title = selected_media.get('title') or selected_media.get('name', 'Unknown')

                if media_id:
                    self["status"].setText(f"Loading {media_title}...")
                    self.load_media_from_person_profile(media_id, media_type, media_title)
                else:
                    self["status"].setText("Error loading media details")

        self.session.openWithCallback(media_selected, ChoiceBox,
                                      title=f"Filmography: {person_name}",
                                      list=menu_list)

        def media_selected(choice):
            if choice:
                selected_media = choice[1]
                media_type = "movie" if selected_media.get('title') else "tv"
                media_id = selected_media.get('id')
                media_title = selected_media.get('title') or selected_media.get('name', 'Unknown')

                if media_id:
                    self["status"].setText(f"Loading {media_title}...")
                    self.load_media_from_person_profile(media_id, media_type, media_title)
                else:
                    self["status"].setText("Error loading media details")

        self.session.openWithCallback(media_selected, ChoiceBox,
                                      title=f"Filmography: {person_name}",
                                      list=menu_list)

    def load_media_from_person_profile(self, media_id, media_type, media_title):
        """Učitava detalje filma/serije iz osobnog profila"""
        # Sačuvaj trenutni profil kao prethodno stanje
        self.previous_person_details = getattr(self, 'current_person_details', None)
        self.previous_person_name = getattr(self, 'current_person_name', None)

        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return

        # Clear previous results
        self.display_mode = 0
        self.show_classic_view()
        self.clear_display()

        self["status"].setText(f"Loading {media_title}...")

        # Uzmi detalje o mediju
        details = _get_media_details(media_id, media_type, api_key)
        if not details:
            self["status"].setText("Error loading media details")
            return

        # Prikaži detalje koristeći postojeću metodu
        person_name = getattr(self, 'current_person_name', 'Filmography')
        self.display_media_info(details, media_type, f"From: {person_name}")

    def show_main_cast(self):
        """Prikazuje glavnu glumačku ekipu"""
        if not hasattr(self, 'current_media_details'):
            self["status"].setText("No media details available")
            return

        credits = self.current_media_details.get("credits", {})
        cast = credits.get("cast", [])[:8]  # Prvih 8 glumaca

        cast_text = "⭐ Main Cast:\n"
        for i, person in enumerate(cast, 1):
            character = person.get("character", "")
            name = person.get("name", "")
            cast_text += f"{i}. {name}"
            if character:
                cast_text += f" as {character}"
            cast_text += "\n"

        self["cast"].setText(cast_text)
        self["status"].setText("Main cast displayed")

    def show_full_cast(self):
        """Prikazuje kompletnu ekipu"""
        self["status"].setText("Full cast feature coming soon!")
        # Ovo ćemo implementirati u narednoj fazi

    def auto_cast_explorer(self):
        """Automatski prikazuje glumce i režisera - MODIFIKOVANA METODA"""
        # PROVJERA DA LI JE OVO PROFIL GLUMCA/REŽISERA
        if hasattr(self, 'current_person_details') and self.current_person_details:
            # Ako je profil osobe - prikaži filmografiju
            self.show_person_filmography()
            return

        # PROVJERA DA LI JE OVO FILM/SERIJA
        if not hasattr(self, 'current_media_details') or not self.current_media_details:
            self["status"].setText("No media loaded! Use Auto EPG or manual search first.")
            return

        credits = self.current_media_details.get("credits", {})
        cast = credits.get("cast", [])
        crew = credits.get("crew", [])

        # Pronađi režisera
        directors = [person for person in crew if person.get("job") == "Director"]

        # Napravi listu za ChoiceBox
        menu_list = []

        # Dodaj režisera
        if directors:
            for director in directors[:2]:
                name = director.get("name", "Unknown")
                menu_list.append((f"🎬 Director: {name}", director))

        # Dodaj glavne glumce (prva 3-4)
        main_cast = cast[:4]
        for i, actor in enumerate(main_cast):
            name = actor.get("name", "Unknown")
            character = actor.get("character", "")
            if character and len(character) > 20:
                character = character[:20] + "..."
            menu_list.append((f"⭐ Star: {name} ({character})", actor))

        if not menu_list:
            self["status"].setText("No cast/director info available")
            return

        def person_selected(choice):
            if choice:
                selected_person = choice[1]
                person_name = selected_person.get("name", "")
                person_type = "director" if selected_person.get("job") == "Director" else "actor"

                if person_name:
                    self["status"].setText(f"Searching {person_type}: {person_name}")
                    self.tmdb_search_person(person_name, person_type)
                else:
                    self["status"].setText("No name found for selected person")

        title = self.current_media_details.get("title") or self.current_media_details.get("name", "Current Media")
        self.session.openWithCallback(person_selected, ChoiceBox,
                                      title=f"Cast & Crew: {title}",
                                      list=menu_list)

    def show_actor_profiles(self):
        """Prikazuje listu glumaca za odabir profila"""
        self["status"].setText("Actor profiles feature coming soon!")
        # Ovo ćemo implementirati u narednoj fazi

    def toggle_backdrop_view(self):
        """Toggle između klasičnog prikaza i backdrop prikaza - radi i za manualnu i auto pretragu"""

        # Proveri da li ima backdrop slike
        if not self.current_backdrop_path or not os.path.exists(self.current_backdrop_path):
            self["status"].setText("No backdrop image available")
            return

        # Prebaci režim
        self.display_mode = (self.display_mode + 1) % 2

        if self.display_mode == 1:
            # BACKDROP MOD - sakrij tekst, prikaži backdrop
            self.show_only_backdrop()
            self["status"].setText("Backdrop view - Press OK to return")
        else:
            # KLASIČNI MOD - vrati tekstualne informacije
            self.show_classic_view()
            self["status"].setText("Classic view")


    def toggle_fullscreen_backdrop(self):
        # Ako nismo došli preko Auto EPG → samo pokreni normalnu pretragu
        if not self.from_auto_epg:
            self.auto_epg_search()
            return

        # Prebaci režim
        self.display_mode = (self.display_mode + 1) % 2
        
        if self.display_mode == 1 and self.current_backdrop_path:
            # BACKDROP MOD – slika levo, informacije desno
            self.show_only_backdrop()
            self["status"].setText("Backdrop view")
        else:
            # VRATI KLASIČNI IZGLED
            self.show_classic_view()
            self["status"].setText("Classic view")

    def show_only_backdrop(self):
        """Prikaži samo backdrop sliku (sakrij sve tekstualne informacije)"""
        # Sakrij SVE tekstualne widget-e sa leve strane
        self["title"].hide()
        self["epg_title"].hide()
        self["duration"].hide()
        self["rating"].hide()
        self["imdb_rating"].hide()
        self["genres"].hide()
        self["director"].hide()
        self["plot"].hide()
        self["cast"].hide()
        self["status"].hide()

        # OSTAVI POSTER VIDLJIV (desna strana ostaje ista)
        self["poster"].show()

        # Prikaži backdrop u levom delu ekrana
        if self.current_backdrop_path and os.path.exists(self.current_backdrop_path):
            pixmap = LoadPixmap(self.current_backdrop_path)
            if pixmap:
                self["backdrop"].instance.setPixmap(pixmap)
                self["backdrop"].show()
        else:
            self["backdrop"].hide()

    def show_classic_view(self):
        """Prikaži klasični prikaz sa svim informacijama"""
        # Vrati sve tekstualne widget-e vidljive
        self["title"].show()
        self["epg_title"].show()
        self["duration"].show()
        self["rating"].show()
        self["imdb_rating"].show()
        self["genres"].show()
        self["director"].show()
        self["plot"].show()
        self["cast"].show()
        self["status"].show()

        # Poster ostaje vidljiv
        self["poster"].show()

        # Sakrij backdrop
        self["backdrop"].hide()

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
        self.display_mode = 0
        self.show_classic_view()
        self.clear_display()

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

        # Uzmi detalje i koristi display_media_info umjesto _display_media_details
        details = _get_media_details(self.media_id, self.media_type, api_key)
        if not details:
            self["status"].setText("Error fetching details")
            self._show_placeholder()
            return

        # Koristite display_media_info koja pravilno postavlja current_media_details
        self.display_media_info(details, media_type)

    def _display_media_details(self, match, media_type, api_key, epg_info=None):
        details = _get_media_details(self.media_id, self.media_type, api_key)
        if not details:
            self["status"].setText("Error fetching details")
            self._show_placeholder()
            return

        # DODAJTE OVO ISPOD return - OVO JE KLJUČNO!
        self.current_media_details = details  # SPREMITE DETALJE SA CREDITS PODACIMA
        self.current_media_type = media_type

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

        # TMDB Rating
        vote = details.get("vote_average", 0)
        if vote:
            self["rating"].setText(f"TMDB: {vote:.1f}/10 ★")
        else:
            self["rating"].setText("TMDB: N/A")

        # IMDB Rating (asinhrono)
        if config.plugins.ciefptmdb.show_imdb_rating.value and config.plugins.ciefptmdb.omdb_api_key.value:
            self["imdb_rating"].setText("IMDB: Loading...")
            threading.Thread(target=self._fetch_imdb_rating, args=(details, media_type), daemon=True).start()
        else:
            self["imdb_rating"].setText("")

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

        backdrop_path = details.get("backdrop_path")
        if backdrop_path and self.media_id:
            self.download_backdrop_async(backdrop_path, self.media_id, media_type, self.backdrop_downloaded)
        else:
            self["backdrop"].hide()

        self["status"].setText("Info loaded")

        self.display_mode = 0
        self.show_classic_view()

    def clear_all_and_reset(self):
        """Resetuje prikaz na početno stanje"""
        self.clear_display()
        self._show_placeholder()
        self["status"].setText("Ready")
        # Resetujte sve atribute
        self.current_media_details = None
        self.current_media_type = None
        self.current_backdrop_path = None
        self.current_person_details = None
        self.current_person_name = None
        self.display_mode = 0
        self.show_classic_view()
        self["epg_title"].setText("")

    def back_from_person_profile(self):
        """Vraća se sa profila osobe na prethodni medij"""
        # Resetuj profil osobe
        self.current_person_details = None
        self.current_person_name = None

        # Ako postoji prethodni medij, vrati se na njega
        if hasattr(self, 'current_media_details') and self.current_media_details is not None:
            self["status"].setText("Returned to media view")
            # Ažuriraj prikaz sa postojećim medijem
            if hasattr(self, 'current_media_type'):
                self.display_media_info(self.current_media_details, self.current_media_type)
        else:
            # Ako nema prethodnog medija, resetuj na početno
            self.clear_all_and_reset()

    def keyBack(self):
        """Handle back/exit button - step back in navigation"""
        # Ako smo na glavnom ekranu i imamo učitane podatke, resetuj prikaz
        if hasattr(self, 'current_media_details') and self.current_media_details is not None:
            self.clear_all_and_reset()
            return

        # Ako smo na profilu osobe, vrati se na prethodni medij (ako postoji)
        if hasattr(self, 'current_person_details') and self.current_person_details is not None:
            self.back_from_person_profile()
            return

        # Ako nema ničega za resetovanje, zatvori plugin
        self.close()

    def keyUp(self):
        """Scroll up - trenutno ne radi sa običnim Label"""
        pass

    def keyDown(self):
        """Scroll down - trenutno ne radi sa običnim Label"""
        pass

    def open_settings(self):
        self.session.open(SettingsScreen)    

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
        self.display_mode = 0
        self.from_auto_epg = False
        self.current_backdrop_path = None
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
            <eLabel text="TMDB API Key" position="550,710" size="200,50" font="Regular;28" foregroundColor="white" backgroundColor="#808000" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/blue.png" position="750,720" size="35,35" alphatest="blend" />
            <eLabel text="OMDb API Key" position="800,710" size="200,50" font="Regular;28" foregroundColor="white" backgroundColor="#000080" halign="center" valign="center" transparent="0" />
            <widget name="menu" position="50,50" size="900,550" scrollbarMode="showOnDemand" itemHeight="50" font="Regular;28" />
        </screen>
    """ % BACKGROUND_SETTINGS


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
                "blue": self.editOmdbApiKey,  # PROMENJENO: sada je OMDb API
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

        # DODAJEMO OMDb API status
        omdb_status = "✓ SET" if config.plugins.ciefptmdb.omdb_api_key.value else "✗ NOT SET"
        self.menu_list.append(f"OMDb API Key: {omdb_status}")

        self.menu_list.append(f"Cache folder: {config.plugins.ciefptmdb.cache_folder.value}")

        poster_status = "YES" if config.plugins.ciefptmdb.cache_enabled.value else "NO"
        self.menu_list.append(f"Download Posters:  {poster_status}")

        # DODAJEMO IMDB rating opciju
        imdb_status = "YES" if config.plugins.ciefptmdb.show_imdb_rating.value else "NO"
        self.menu_list.append(f"Show IMDB Rating:  {imdb_status}")

        lang_names = {
            "en-US": "English", "sr-RS": "Srpski", "hr-HR": "Hrvatski",
            "bs-BA": "Bosanski", "sl-SI": "Slovenščina", "mk-MK": "Македонски",
            "cs-CZ": "Čeština", "sk-SK": "Slovenský", "hu-HU": "Magyar", 
            "ro-RO": "Română", "bg-BG": "Български", "el-GR": "Ελληνικά",
            "de-DE": "Deutsch", "fr-FR": "Français", "es-ES": "Español",
            "it-IT": "Italiano", "pt-PT": "Português PT", "pt-BR": "Português BR",
            "nl-NL": "Nederlands", "sv-SE": "Svenska", "no-NO": "Norsk",
            "da-DK": "Dansk", "fi-FI": "Suomi", "ru-RU": "Русский",
            "uk-UA": "Українська", "pl-PL": "Polski", "tr-TR": "Türkçe",
            "ar-AE": "العربية", "he-IL": "עברית", "ja-JP": "日本語",
            "ko-KR": "한국어", "zh-CN": "中文 (简)", "zh-TW": "中文 (繁)",
            "th-TH": "ไทย", "vi-VN": "Tiếng Việt"
        }
        current_lang = lang_names.get(config.plugins.ciefptmdb.language.value, "English")
        self.menu_list.append(f"Description language: {current_lang}")

        poster_count, cache_size = get_cache_info()
        self.menu_list.append(f"Cache: {poster_count} posters ({cache_size:.1f} MB)")
        self.menu_list.append(">>> CLEAR ALL POSTERS (MENU button) <<<")

        self["menu"].setList(self.menu_list)

    def keyOk(self):
        idx = self["menu"].getSelectedIndex()

        if idx == 0:  # TMDB API Key status
            self.editApiKey()
        elif idx == 1:  # OMDb API Key status
            self.editOmdbApiKey()
        elif idx == 2:  # Cache folder
            pass  # Ne radi ništa, samo informacija
        elif idx == 3:  # Download Posters
            config.plugins.ciefptmdb.cache_enabled.value = not config.plugins.ciefptmdb.cache_enabled.value
            self.buildMenu()
        elif idx == 4:  # Show IMDB Rating
            config.plugins.ciefptmdb.show_imdb_rating.value = not config.plugins.ciefptmdb.show_imdb_rating.value
            self.buildMenu()
        elif idx == 5:  # Language
            self.change_language()
        elif idx == 7:  # Clear cache (poslednja stavka)
            self.clearCache()


    def change_language(self):
        lang_order = [
            "en-US", "sr-RS", "hr-HR", "bs-BA", "sl-SI", "mk-MK",
            "cs-CZ", "sk-SK", "hu-HU", "ro-RO", "bg-BG", "el-GR",
            "de-DE", "fr-FR", "es-ES", "it-IT", "pt-PT", "pt-BR",
            "nl-NL", "sv-SE", "no-NO", "da-DK", "fi-FI", "ru-RU",
            "uk-UA", "pl-PL", "tr-TR", "ar-AE", "he-IL", "ja-JP",
            "ko-KR", "zh-CN", "zh-TW", "th-TH", "vi-VN"
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
            "en-US": "English", "sr-RS": "Srpski", "hr-HR": "Hrvatski",
            "bs-BA": "Bosanski", "sl-SI": "Slovenščina", "mk-MK": "Македонски",
            "cs-CZ": "Čeština", "sk-SK": "Slovenský", "hu-HU": "Magyar",
            "ro-RO": "Română", "bg-BG": "Български", "el-GR": "Ελληνικά",
            "de-DE": "Deutsch", "fr-FR": "Français", "es-ES": "Español",
            "it-IT": "Italiano", "pt-PT": "Português PT", "pt-BR": "Português BR",
            "nl-NL": "Nederlands", "sv-SE": "Svenska", "no-NO": "Norsk",
            "da-DK": "Dansk", "fi-FI": "Suomi", "ru-RU": "Русский",
            "uk-UA": "Українська", "pl-PL": "Polski", "tr-TR": "Türkçe",
            "ar-AE": "العربية", "he-IL": "עברית", "ja-JP": "日本語",
            "ko-KR": "한국어", "zh-CN": "中文 (简)", "zh-TW": "中文 (繁)",
            "th-TH": "ไทย", "vi-VN": "Tiếng Việt"
        }

        self["status"].setText(f"Language → {pretty_names[next_code]}")
        self.buildMenu()

    def editApiKey(self):
        def callback(result):
            if result is not None:
                config.plugins.ciefptmdb.tmdb_api_key.value = result.strip()
                config.plugins.ciefptmdb.tmdb_api_key.save()
                save_api_key_to_file()
                self["status"].setText("TMDB API key updated!")
                self.buildMenu()
        current_key = config.plugins.ciefptmdb.tmdb_api_key.value
        self.session.openWithCallback(callback, VirtualKeyBoard, title="Enter TMDB API Key", text=current_key)

    def editOmdbApiKey(self):
        def callback(result):
            if result is not None:
                config.plugins.ciefptmdb.omdb_api_key.value = result.strip()
                config.plugins.ciefptmdb.omdb_api_key.save()
                save_omdb_api_key_to_file()
                self["status"].setText("OMDb API key updated!")
                self.buildMenu()
        current_key = config.plugins.ciefptmdb.omdb_api_key.value
        self.session.openWithCallback(callback, VirtualKeyBoard, title="Enter OMDb API Key", text=current_key)

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
            save_omdb_api_key_to_file()
            config.plugins.ciefptmdb.cache_enabled.save()
            config.plugins.ciefptmdb.show_imdb_rating.save()
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