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
PLUGIN_VERSION = "2.1"
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

# ---------- NOVO: BACKDROPS & POSTERS GALERIJA ----------
def get_all_backdrops(media_id, media_type, api_key):
    """Dobija sve backdrop slike za film/seriju"""
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/{media_type}/{media_id}/images?api_key={api_key}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        
        backdrops = data.get("backdrops", [])
        # Sortiraj po popularnosti (vote_average + vote_count)
        backdrops.sort(key=lambda x: (x.get("vote_average", 0) * x.get("vote_count", 0)), reverse=True)
        return backdrops
    except Exception as e:
        print(f"[TMDB] Get all backdrops error: {e}")
        return []

def get_all_posters(media_id, media_type, api_key):
    """Dobija sve poster slike za film/seriju"""
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/{media_type}/{media_id}/images?api_key={api_key}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        
        posters = data.get("posters", [])
        # Sortiraj po popularnosti
        posters.sort(key=lambda x: (x.get("vote_average", 0) * x.get("vote_count", 0)), reverse=True)
        return posters
    except Exception as e:
        print(f"[TMDB] Get all posters error: {e}")
        return []

# ---------- NOVO: SEASON & EPISODE FUNKCIJE ----------
def get_tv_seasons(tv_id, api_key):
    """Dobija listu sezona za TV seriju"""
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/tv/{tv_id}?api_key={api_key}&language={language}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return data.get("seasons", [])
    except Exception as e:
        print(f"[TMDB] Get seasons error: {e}")
        return []

def get_season_episodes(tv_id, season_number, api_key):
    """Dobija listu epizoda za određenu sezonu"""
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{season_number}?api_key={api_key}&language={language}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return data.get("episodes", [])
    except Exception as e:
        print(f"[TMDB] Get episodes error: {e}")
        return []

def get_episode_details(tv_id, season_number, episode_number, api_key):
    """Dobija detalje o epizodi"""
    try:
        language = config.plugins.ciefptmdb.language.value
        url = f"https://api.themoviedb.org/3/tv/{tv_id}/season/{season_number}/episode/{episode_number}?api_key={api_key}&language={language}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(url, context=ctx, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"[TMDB] Get episode details error: {e}")
        return None

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
            if filename.startswith(('movie_', 'tv_', 'gallery_backdrop_', 'gallery_poster_')) and (filename.endswith('.jpg') or filename.endswith('.png')):
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
            if filename.startswith(('movie_', 'tv_', 'gallery_backdrop_', 'gallery_poster_')) and (filename.endswith('.jpg') or filename.endswith('.png')):
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
            <eLabel text="MENU: More" position="1300,990" size="200,50" font="Regular;24" foregroundColor="white" backgroundColor="#023030" halign="center" valign="center" transparent="0"/>
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

        # Extended action map - IZBRISALI SMO "info" AKCIJU
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "MenuActions", "DirectionActions"],
                                    {
                                        "cancel": self.keyBack,
                                        "ok": self.toggle_backdrop_view,
                                        "red": self.close,
                                        "green": self.advanced_search_menu,
                                        "yellow": self.auto_cast_explorer,  # Cast Explorer ostaje na ŽUTOM
                                        "blue": self.auto_epg_search,
                                        "menu": self.show_more_options,  # MENU sada otvara dodatne opcije
                                        "up": self.keyUp,
                                        "down": self.keyDown
                                    }, -1)

        self["backdrop"].hide()
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

    def show_more_options(self):
        """Prikazuje dodatne opcije preko MENU dugmeta - zamenio Settings"""
        from Screens.ChoiceBox import ChoiceBox
        
        menu_list = []
        
        # Uvek dodaj Settings opciju
        menu_list.append(("⚙️ Settings", "settings"))
        
        # Ako ima media detalja, dodaj opcije za galerije
        if self.current_media_details:
            menu_list.append(("🖼️ Backdrop Gallery", "backdrop_gallery"))
            menu_list.append(("🎬 Poster Gallery", "poster_gallery"))
            
            # Ako je u pitanju TV serija, dodaj opciju za sezone i epizode
            if self.current_media_type == "tv":
                menu_list.append(("📺 Season & Episodes", "seasons"))
        
        # Ako je profil osobe, dodaj opciju za filmografiju
        if self.current_person_details:
            menu_list.append(("🎞️ Filmography", "filmography"))
        
        # Ako je film ili serija, dodaj opciju za glumce
        if self.current_media_details:
            menu_list.append(("👥 Cast Explorer", "cast_explorer"))
        
        # Dodaj opciju za brisanje keša
        menu_list.append(("🗑️ Clear Cache", "clear_cache"))
        
        def option_callback(choice):
            if choice:
                if choice[1] == "settings":
                    self.open_settings()
                elif choice[1] == "backdrop_gallery":
                    self.open_backdrop_gallery()
                elif choice[1] == "poster_gallery":
                    self.open_poster_gallery()
                elif choice[1] == "seasons":
                    self.show_season_list()
                elif choice[1] == "filmography":
                    self.show_person_filmography()
                elif choice[1] == "cast_explorer":
                    self.auto_cast_explorer()
                elif choice[1] == "clear_cache":
                    self.clear_cache_dialog()
        
        self.session.openWithCallback(option_callback, ChoiceBox,
                                      title="More Options",
                                      list=menu_list)

    def clear_cache_dialog(self):
        """Dijalog za brisanje keša"""
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
                else:
                    self["status"].setText("No posters found to delete")
            else:
                self["status"].setText("Cache deletion cancelled")
                
        self.session.openWithCallback(confirmation_callback, MessageBox, message, MessageBox.TYPE_YESNO)

    def open_backdrop_gallery(self):
        """Otvara galeriju sa svim backdrop slikama"""
        if not self.current_media_details:
            self["status"].setText("No media loaded!")
            return
        
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return
        
        media_id = self.current_media_details.get("id")
        media_type = self.current_media_type
        media_title = self.current_media_details.get("title") or self.current_media_details.get("name", "Media")
        
        self["status"].setText("Loading backdrops...")
        
        # Uzmi sve backdrope
        backdrops = get_all_backdrops(media_id, media_type, api_key)
        
        if not backdrops:
            self["status"].setText("No backdrops found!")
            return
        
        # Pronađi indeks trenutnog backdroпa ako postoji
        current_index = 0
        current_backdrop_path = self.current_media_details.get("backdrop_path")
        if current_backdrop_path:
            for i, backdrop in enumerate(backdrops):
                if backdrop.get("file_path") == current_backdrop_path:
                    current_index = i
                    break
        
        # Otvori galeriju
        self.session.open(BackdropGalleryScreen, 
                          media_id, 
                          media_type, 
                          media_title, 
                          backdrops, 
                          current_index,
                          "backdrops")
        
        self["status"].setText(f"Loaded {len(backdrops)} backdrops")

    def open_poster_gallery(self):
        """Otvara galeriju sa svim poster slikama"""
        if not self.current_media_details:
            self["status"].setText("No media loaded!")
            return
        
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return
        
        media_id = self.current_media_details.get("id")
        media_type = self.current_media_type
        media_title = self.current_media_details.get("title") or self.current_media_details.get("name", "Media")
        
        self["status"].setText("Loading posters...")
        
        # Uzmi sve postere
        posters = get_all_posters(media_id, media_type, api_key)
        
        if not posters:
            self["status"].setText("No posters found!")
            return
        
        # Pronađi indeks trenutnog postera ako postoji
        current_index = 0
        current_poster_path = self.current_media_details.get("poster_path")
        if current_poster_path:
            for i, poster in enumerate(posters):
                if poster.get("file_path") == current_poster_path:
                    current_index = i
                    break
        
        # Otvori galeriju
        self.session.open(BackdropGalleryScreen, 
                          media_id, 
                          media_type, 
                          media_title, 
                          posters, 
                          current_index,
                          "posters")
        
        self["status"].setText(f"Loaded {len(posters)} posters")

    def show_season_list(self):
        """Prikazuje listu sezona za TV seriju"""
        if not self.current_media_type == "tv" or not self.current_media_details:
            self["status"].setText("This is not a TV series!")
            return
            
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return
            
        tv_id = self.current_media_details.get("id")
        if not tv_id:
            self["status"].setText("No TV series ID!")
            return
            
        self["status"].setText("Loading seasons...")
        seasons = get_tv_seasons(tv_id, api_key)
        
        if not seasons:
            self["status"].setText("No seasons found!")
            return
            
        menu_list = []
        for season in seasons:
            season_num = season.get("season_number", 0)
            name = season.get("name", f"Season {season_num}")
            episode_count = season.get("episode_count", 0)
            year = season.get("air_date", "")[:4] if season.get("air_date") else ""
            
            # Preskoči specijalne sezone (season_number = 0)
            if season_num == 0:
                continue
                
            display_text = f"{name}"
            if episode_count > 0:
                display_text += f" ({episode_count} eps)"
            if year:
                display_text += f" - {year}"
                
            menu_list.append((display_text, season))
            
        def season_selected(choice):
            if choice:
                selected_season = choice[1]
                season_num = selected_season.get("season_number")
                self.show_episode_list(tv_id, season_num, selected_season.get("name", f"Season {season_num}"))
                
        self.session.openWithCallback(season_selected, ChoiceBox,
                                      title=f"Seasons: {self.current_media_details.get('name', 'TV Series')}",
                                      list=menu_list)

    def show_episode_list(self, tv_id, season_num, season_name):
        """Prikazuje listu epizoda za odabranu sezonu"""
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return
            
        self["status"].setText(f"Loading {season_name}...")
        episodes = get_season_episodes(tv_id, season_num, api_key)
        
        if not episodes:
            self["status"].setText(f"No episodes found for {season_name}!")
            return
            
        menu_list = []
        for episode in episodes:
            ep_num = episode.get("episode_number", 0)
            name = episode.get("name", f"Episode {ep_num}")
            air_date = episode.get("air_date", "")
            rating = episode.get("vote_average", 0)
            
            # Formatiraj datum
            if air_date and len(air_date) >= 10:
                pretty_date = f"{air_date[8:10]}.{air_date[5:7]}.{air_date[:4]}"
            else:
                pretty_date = "N/A"
                
            # Zvezdice za ocenu
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
                
            display_text = f"Ep {ep_num}: {name}"
            if rating > 0:
                display_text += f" {stars} {rating:.1f}"
            if pretty_date != "N/A":
                display_text += f" ({pretty_date})"
                
            menu_list.append((display_text, episode))
            
        def episode_selected(choice):
            if choice:
                selected_episode = choice[1]
                episode_num = selected_episode.get("episode_number")
                self.show_episode_details(tv_id, season_num, episode_num, selected_episode)
                
        self.session.openWithCallback(episode_selected, ChoiceBox,
                                      title=f"{season_name} - Episodes",
                                      list=menu_list)

    def show_episode_details(self, tv_id, season_num, episode_num, episode_data):
        """Prikazuje detalje o epizodi"""
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return
            
        self["status"].setText("Loading episode details...")
        
        # Koristimo podatke koje već imamo ili dobijamo dodatne detalje
        episode_name = episode_data.get("name", f"Episode {episode_num}")
        overview = episode_data.get("overview", "No description available.")
        air_date = episode_data.get("air_date", "")
        runtime = episode_data.get("runtime", 0)
        rating = episode_data.get("vote_average", 0)
        
        # Ažuriraj prikaz
        self.clear_display()
        
        # Prikaži informacije
        series_name = self.current_media_details.get("name", "TV Series")
        self["title"].setText(f"{series_name} - {season_num}x{episode_num:02d}")
        self["epg_title"].setText(f"{episode_name}")
        
        # Duration
        if runtime:
            self["duration"].setText(f"Duration: {runtime} min")
        else:
            self["duration"].setText("Duration: N/A")
            
        # Rating
        if rating:
            self["rating"].setText(f"Rating: {rating:.1f}/10 ★")
        else:
            self["rating"].setText("Rating: N/A")
            
        # Air date
        if air_date:
            pretty_date = f"{air_date[8:10]}.{air_date[5:7]}.{air_date[:4]}"
            self["imdb_rating"].setText(f"Aired: {pretty_date}")
        else:
            self["imdb_rating"].setText("Aired: N/A")
            
        # Genres - prazno za epizodu
        self["genres"].setText("")
        
        # Director - pokušaj da pronađeš režisera
        crew = episode_data.get("crew", [])
        directors = [c["name"] for c in crew if c.get("job") == "Director"]
        if directors:
            self["director"].setText(f"Director: {', '.join(directors)}")
        else:
            self["director"].setText("")
            
        # Plot
        if len(overview) > 500:
            overview = overview[:500] + "..."
        self["plot"].setText("Plot:\n" + overview)
        
        # Cast - pokušaj da prikažeš glumce za ovu epizodu
        guest_stars = episode_data.get("guest_stars", [])[:6]  # Prvih 6 gostujućih glumaca
        cast_text = "Guest Stars:\n"
        if guest_stars:
            for star in guest_stars:
                char = star.get("character", "").strip()
                name = star.get("name", "").strip()
                if char:
                    cast_text += f"• {name} as {char}\n"
                else:
                    cast_text += f"• {name}\n"
        else:
            cast_text += "No guest stars info"
        self["cast"].setText(cast_text)
        
        # Download still slike ako postoji
        still_path = episode_data.get("still_path")
        if still_path:
            # Koristimo postojeću funkciju za download, ali sa drugim prefiksom
            download_poster_async(still_path, f"{tv_id}_s{season_num}e{episode_num}", "tv", self.episode_still_downloaded)
        else:
            self._show_placeholder()
            
        self["status"].setText(f"Episode {season_num}x{episode_num:02d} loaded")

    def episode_still_downloaded(self, path):
        """Callback kada se still slika epizode download-uje"""
        if path and os.path.exists(path):
            pixmap = load_pixmap_safe(path)
            if pixmap:
                self["poster"].instance.setPixmap(pixmap)
                self["poster"].show()
                return
                
        # Fallback na placeholder
        self._show_placeholder()

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
        self.display_mode = 0
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

            candidates = [r for r in results if r.get("media_type") in ("movie", "tv")]
            if not candidates:
                return None, None

            if year:
                for c in candidates:
                    c_year = (c.get("release_date") or c.get("first_air_date") or "")[:4]
                    if c_year == str(year):
                        return c, c["media_type"]

            candidates.sort(key=lambda x: x.get("popularity", 0), reverse=True)
            best = candidates[0]

            if best["media_type"] == "movie":
                temp_details = _get_media_details(best["id"], "movie", api_key)
                runtime = temp_details.get("runtime") if temp_details else 0
                if runtime and runtime < 35:
                    tv_result = _search_tmdb_tv(title, year, api_key)
                    if tv_result[0]:
                        return tv_result

            return best, best["media_type"]

        except Exception as e:
            print(f"[TMDB] Multi search error: {e}")
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
            ("9. Search Top Rated Movies", "top_rated_movies"),
            ("10. Search Top Rated Series", "top_rated_series"),
            ("11. Search Upcoming Movies", "upcoming_movies")
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
                elif choice[1] == "top_rated_movies":
                    self.search_top_rated_movies()
                elif choice[1] == "top_rated_series":
                    self.search_top_rated_series()
                elif choice[1] == "upcoming_movies":
                    self.search_upcoming_movies()

        self.session.openWithCallback(search_callback, ChoiceBox,
                                      title="Advanced Search - Select Type",
                                      list=menu_list)

    def cast_explorer_menu(self):
        """Prikazuje meni za istraživanje glumačke ekipe"""
        from Screens.ChoiceBox import ChoiceBox

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

            if release_date and len(release_date) == 10:
                try:
                    y, m, d = release_date.split("-")
                    pretty_date = f"{int(d):02d}.{int(m):02d}.{y}"
                except:
                    pretty_date = release_date
            else:
                pretty_date = "N/A"

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
                person_type = selected.get("known_for_department", "Acting")
                self["status"].setText(f"Loading {person_name}...")
                details = _get_person_details(person_id, api_key)
                if details:
                    self.display_person_info(details, api_key, person_type)

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
                year = ""
            else:
                continue

            rating = item.get("vote_average", 0) if media_type != "person" else item.get("popularity", 0)

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

        self.display_mode = 0
        self.show_classic_view()
        self.clear_display()

        self["status"].setText(f"Searching {person_type}...")
        match, media_type = _search_tmdb_person(query, api_key)

        if not match:
            self["status"].setText(f"No {person_type} found")
            self._show_placeholder()
            return

        self.current_person_name = query
        self.display_person_info(match, api_key, person_type)

    def display_person_info(self, person_data, api_key, person_type):
        """Prikazuje informacije o glumcu/direktoru sa korisnim informacijama"""
        person_id = person_data.get("id")
        details = _get_person_details(person_id, api_key)

        if not details:
            self["status"].setText("Error loading person details")
            return

        self.current_person_details = details
        self.current_person_name = details.get("name", "Unknown")
        
        name = details.get("name", "N/A")
        known_for = details.get("known_for_department", "N/A")
        birthday = details.get("birthday", "N/A")
        place_of_birth = details.get("place_of_birth", "N/A")
        biography = details.get("biography", "No biography available.")

        self["title"].setText(f"{name} ({known_for})")
        self["epg_title"].setText("")

        birth_info = f"Born: {birthday}"
        if place_of_birth and place_of_birth != "N/A":
            birth_info += f" in {place_of_birth}"
        self["duration"].setText(birth_info)

        movie_count = len(details.get("movie_credits", {}).get("cast", []))
        tv_count = len(details.get("tv_credits", {}).get("cast", []))

        career_info = ""
        if birthday:
            try:
                birth_year = int(birthday[:4])
                current_year = 2024
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

        self["imdb_rating"].setText("")
        self["genres"].setText("")
        self["director"].setText("")

        if len(biography) > 400:
            biography = biography[:400] + "..."
        self["plot"].setText(f"Biography:\n{biography}")

        movie_credits = details.get("movie_credits", {}).get("cast", [])
        tv_credits = details.get("tv_credits", {}).get("cast", [])

        def get_movie_score(movie):
            popularity = movie.get('popularity', 0) or 0
            vote_count = movie.get('vote_count', 0) or 0
            return (vote_count * 10) + popularity

        def get_tv_score(tv):
            popularity = tv.get('popularity', 0) or 0
            vote_count = tv.get('vote_count', 0) or 0
            return (vote_count * 10) + popularity

        movie_credits.sort(key=get_movie_score, reverse=True)
        tv_credits.sort(key=get_tv_score, reverse=True)

        top_movies = movie_credits[:4]
        top_tv = tv_credits[:2]

        filmography = "Known For:\n"
        if top_movies:
            filmography += "Movies:\n"
            for movie in top_movies:
                title = movie.get('title', 'N/A')
                year = movie.get('release_date', '')[:4]
                if title and title != 'N/A':
                    filmography += f"• {title} ({year})\n"

        if top_tv:
            filmography += "TV Series:\n"
            for tv in top_tv:
                name = tv.get('name', 'N/A')
                year = tv.get('first_air_date', '')[:4]
                if name and name != 'N/A':
                    filmography += f"• {name} ({year})\n"

        if not top_movies and not top_tv:
            filmography += "No notable works found"

        self["cast"].setText(filmography)

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

        movie_credits = person_details.get("movie_credits", {}).get("cast", [])
        tv_credits = person_details.get("tv_credits", {}).get("cast", [])

        def get_movie_score(movie):
            popularity = movie.get('popularity', 0) or 0
            vote_count = movie.get('vote_count', 0) or 0
            return (vote_count * 10) + popularity

        def get_tv_score(tv):
            popularity = tv.get('popularity', 0) or 0
            vote_count = tv.get('vote_count', 0) or 0
            return (vote_count * 10) + popularity

        movie_credits.sort(key=get_movie_score, reverse=True)
        tv_credits.sort(key=get_tv_score, reverse=True)

        menu_list = []

        for movie in movie_credits[:8]:
            title = movie.get('title', 'N/A')
            year = movie.get('release_date', '')[:4]
            rating = movie.get('vote_average', 0)

            if title and title != 'N/A':
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

                if rating > 0:
                    menu_list.append((f"[Mov] {title} ({year}) {stars} {rating:.1f}", movie))
                else:
                    menu_list.append((f"[Mov] {title} ({year})", movie))

        for tv in tv_credits[:4]:
            name = tv.get('name', 'N/A')
            year = tv.get('first_air_date', '')[:4]
            rating = tv.get('vote_average', 0)

            if name and name != 'N/A':
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

    def load_media_from_person_profile(self, media_id, media_type, media_title):
        """Učitava detalje filma/serije iz osobnog profila"""
        self.previous_person_details = getattr(self, 'current_person_details', None)
        self.previous_person_name = getattr(self, 'current_person_name', None)

        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["status"].setText("TMDB API key not set!")
            return

        self.display_mode = 0
        self.show_classic_view()
        self.clear_display()

        self["status"].setText(f"Loading {media_title}...")

        details = _get_media_details(media_id, media_type, api_key)
        if not details:
            self["status"].setText("Error loading media details")
            return

        person_name = getattr(self, 'current_person_name', 'Filmography')
        self.display_media_info(details, media_type, f"From: {person_name}")

    def show_main_cast(self):
        """Prikazuje glavnu glumačku ekipu"""
        if not hasattr(self, 'current_media_details'):
            self["status"].setText("No media details available")
            return

        credits = self.current_media_details.get("credits", {})
        cast = credits.get("cast", [])[:8]

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

    def auto_cast_explorer(self):
        """Automatski prikazuje glumce i režisera"""
        if hasattr(self, 'current_person_details') and self.current_person_details:
            self.show_person_filmography()
            return

        if not hasattr(self, 'current_media_details') or not self.current_media_details:
            self["status"].setText("No media loaded! Use Auto EPG or manual search first.")
            return

        credits = self.current_media_details.get("credits", {})
        cast = credits.get("cast", [])
        crew = credits.get("crew", [])

        directors = [person for person in crew if person.get("job") == "Director"]

        menu_list = []

        if directors:
            for director in directors[:2]:
                name = director.get("name", "Unknown")
                menu_list.append((f"🎬 Director: {name}", director))

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

    def toggle_backdrop_view(self):
        """Otvara galeriju backdroпova umesto toggle-a"""
        if not self.current_media_details:
            self["status"].setText("No media loaded! Use Auto EPG or search first.")
            return
        
        self.open_backdrop_gallery()

    def toggle_fullscreen_backdrop(self):
        if not self.from_auto_epg:
            self.auto_epg_search()
            return

        self.display_mode = (self.display_mode + 1) % 2
        
        if self.display_mode == 1 and self.current_backdrop_path:
            self.show_only_backdrop()
            self["status"].setText("Backdrop view")
        else:
            self.show_classic_view()
            self["status"].setText("Classic view")

    def show_only_backdrop(self):
        """Prikaži samo backdrop sliku (sakrij sve tekstualne informacije)"""
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

        self["poster"].show()

        if self.current_backdrop_path and os.path.exists(self.current_backdrop_path):
            pixmap = LoadPixmap(self.current_backdrop_path)
            if pixmap:
                self["backdrop"].instance.setPixmap(pixmap)
                self["backdrop"].show()
        else:
            self["backdrop"].hide()

    def show_classic_view(self):
        """Prikaži klasični prikaz sa svim informacijama"""
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

        self["poster"].show()
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

        self.display_mode = 0
        self.show_classic_view()
        self.clear_display()

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

        details = _get_media_details(self.media_id, self.media_type, api_key)
        if not details:
            self["status"].setText("Error fetching details")
            self._show_placeholder()
            return

        self.display_media_info(details, media_type)

    def _display_media_details(self, match, media_type, api_key, epg_info=None):
        details = _get_media_details(self.media_id, self.media_type, api_key)
        if not details:
            self["status"].setText("Error fetching details")
            self._show_placeholder()
            return

        self.current_media_details = details
        self.current_media_type = media_type

        if media_type == "movie":
            title = details.get("title", "N/A")
            year = details.get("release_date", "")[:4] if details.get("release_date") else ""
            runtime = details.get("runtime")
            duration = f"{runtime} min" if runtime else "N/A"
        else:
            title = details.get("name", "N/A")
            year = details.get("first_air_date", "")[:4] if details.get("first_air_date") else ""
            duration_data = details.get("episode_run_time")
            if duration_data and isinstance(duration_data, list) and duration_data:
                duration = f"~{duration_data[0]} min/ep"
            else:
                duration = "N/A"

        self["title"].setText(title + (f" ({year})" if year else ""))
        self["epg_title"].setText("")

        self["duration"].setText(f"Duration: {duration}")

        vote = details.get("vote_average", 0)
        if vote:
            self["rating"].setText(f"TMDB: {vote:.1f}/10 ★")
        else:
            self["rating"].setText("TMDB: N/A")

        if config.plugins.ciefptmdb.show_imdb_rating.value and config.plugins.ciefptmdb.omdb_api_key.value:
            self["imdb_rating"].setText("IMDB: Loading...")
            threading.Thread(target=self._fetch_imdb_rating, args=(details, media_type), daemon=True).start()
        else:
            self["imdb_rating"].setText("")

        genres = [g["name"] for g in details.get("genres", [])]
        if genres:
            self["genres"].setText(f"Genres: {', '.join(genres)}")
        else:
            self["genres"].setText("Genres: N/A")

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

        overview = details.get("overview", "").strip()
        if overview:
            overview = overview.replace("\r\n", " ").replace("\n", " ")
            if len(overview) > 500:
                overview = overview[:500].rsplit(" ", 1)[0] + " ..."
            self["plot"].setText("Plot:\n" + overview)
        else:
            self["plot"].setText("Plot:\nNo description available.")

        cast = credits.get("cast", [])[:6]
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

        if self.poster_path and config.plugins.ciefptmdb.cache_enabled.value:
            self["status"].setText("Downloading poster...")
            self.download_in_progress = True
            self.download_timer.start(12000, True)

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
        self.current_person_details = None
        self.current_person_name = None

        if hasattr(self, 'current_media_details') and self.current_media_details is not None:
            self["status"].setText("Returned to media view")
            if hasattr(self, 'current_media_type'):
                self.display_media_info(self.current_media_details, self.current_media_type)
        else:
            self.clear_all_and_reset()

    def keyBack(self):
        """Handle back/exit button - step back in navigation"""
        if hasattr(self, 'current_media_details') and self.current_media_details is not None:
            self.clear_all_and_reset()
            return

        if hasattr(self, 'current_person_details') and self.current_person_details is not None:
            self.back_from_person_profile()
            return

        self.close()

    def keyUp(self):
        pass

    def keyDown(self):
        pass

    def open_settings(self):
        self.session.open(SettingsScreen)    

    def __onClose(self):
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


# ---------- BACKDROP GALLERY SCREEN ----------
class BackdropGalleryScreen(Screen):
    skin = """
        <screen position="center,center" size="1920,1080" title="Backdrop Gallery">
            <!-- Backdrop slika - pun ekran -->
            <widget name="backdrop_image" position="50,50" size="1820,900" alphatest="blend" />

            <!-- Poster slika - centrirana, manja -->
            <widget name="poster_image" position="660,50" size="600,900" alphatest="blend" />

            <!-- Info i navigacija -->
            <widget name="info" position="50,970" size="1500,50" font="Regular;30" foregroundColor="white" />
            <widget name="nav" position="1600,970" size="270,50" font="Regular;30" foregroundColor="yellow" halign="right" />

            <!-- Dugmad -->
            <ePixmap pixmap="buttons/red.png" position="0,1020" size="35,35" alphatest="blend" />
            <eLabel text="Exit" position="50,1010" size="200,50" font="Regular;26" foregroundColor="white" backgroundColor="#800000" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/green.png" position="250,1020" size="35,35" alphatest="blend" />
            <eLabel text="Switch to Posters" position="300,1010" size="200,50" font="Regular;24" foregroundColor="white" backgroundColor="#008000" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/yellow.png" position="500,1020" size="35,35" alphatest="blend" />
            <eLabel text="Prev" position="550,1010" size="150,50" font="Regular;26" foregroundColor="white" backgroundColor="#808000" halign="center" valign="center" transparent="0" />
            <ePixmap pixmap="buttons/blue.png" position="700,1020" size="35,35" alphatest="blend" />
            <eLabel text="Next" position="750,1010" size="150,50" font="Regular;26" foregroundColor="white" backgroundColor="#000080" halign="center" valign="center" transparent="0" />
        </screen>
    """

    def __init__(self, session, media_id, media_type, media_title, images_list, current_index=0,
                 gallery_type="backdrops"):
        Screen.__init__(self, session)
        self.session = session
        self.media_id = media_id
        self.media_type = media_type
        self.media_title = media_title
        self.images_list = images_list
        self.current_index = current_index
        self.gallery_type = gallery_type  # "backdrops" ili "posters"

        self["backdrop_image"] = Pixmap()
        self["poster_image"] = Pixmap()
        self["info"] = Label("")
        self["nav"] = Label("")

        self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"],
                                    {
                                        "cancel": self.close,
                                        "red": self.close,
                                        "green": self.switch_gallery_type,
                                        "yellow": self.prev_image,
                                        "blue": self.next_image,
                                        "left": self.prev_image,
                                        "right": self.next_image,
                                        "up": self.prev_image,
                                        "down": self.next_image,
                                        "ok": self.close,
                                    }, -1)

        self.onLayoutFinish.append(self.load_current_image)
        self.onClose.append(self.__onClose)

    def __onClose(self):
        try:
            if "actions" in self:
                self["actions"].destroy()
                del self["actions"]
        except:
            pass

    def load_current_image(self):
        if not self.images_list or self.current_index >= len(self.images_list):
            self["info"].setText("No images available")
            return

        current_image = self.images_list[self.current_index]
        file_path = current_image.get("file_path", "")

        if not file_path:
            self["info"].setText("No image path")
            return

        # Ažuriraj info
        total = len(self.images_list)
        resolution = f"{current_image.get('width', 0)}x{current_image.get('height', 0)}"
        language = current_image.get('iso_639_1', 'N/A')
        votes = current_image.get('vote_count', 0)

        info_text = f"{self.media_title} - {self.gallery_type.title()} {self.current_index + 1}/{total}"
        if resolution != "0x0":
            info_text += f" | {resolution}"
        if language != 'null' and language != 'N/A':
            info_text += f" | Lang: {language}"
        if votes > 0:
            info_text += f" | Votes: {votes}"

        self["info"].setText(info_text)
        self["nav"].setText("← → to navigate")

        # Sakrij jedan, pokaži drugi widget zavisno od tipa
        if self.gallery_type == "backdrops":
            self["poster_image"].hide()
            self["backdrop_image"].show()
        else:
            self["backdrop_image"].hide()
            self["poster_image"].show()

        # Download sliku
        self.download_and_display_image(file_path)

    def download_and_display_image(self, file_path):
        """Download i prikaz slike sa različitim veličinama za postere i backdropove"""
        try:
            # Generiši cache ime
            if self.gallery_type == "backdrops":
                filename = f"gallery_backdrop_{self.media_id}_{os.path.basename(file_path)}"
            else:
                filename = f"gallery_poster_{self.media_id}_{os.path.basename(file_path)}"

            folder = ensure_cache_folder()
            fname = os.path.join(folder, filename)

            # Proveri da li već postoji u cache-u
            if os.path.exists(fname):
                self.display_image(fname)
                return

            # Odredi veličinu za download
            if self.gallery_type == "posters":
                base_url = "https://image.tmdb.org/t/p/w500"  # Manja rezolucija za postere
            else:
                base_url = "https://image.tmdb.org/t/p/w1280"  # Puna rezolucija za backdropove

            url = base_url + file_path

            def download_thread():
                try:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    data = urllib.request.urlopen(url, context=ctx, timeout=15).read()
                    with open(fname, "wb") as f:
                        f.write(data)
                    # Prikaži sliku nakon download-a
                    self.display_image(fname)
                except Exception as e:
                    print(f"[Gallery] Download error: {e}")
                    self["info"].setText(f"Download error: {str(e)[:50]}")

            thread = threading.Thread(target=download_thread, daemon=True)
            thread.start()

        except Exception as e:
            print(f"[Gallery] Error: {e}")
            self["info"].setText(f"Error loading image")

    def display_image(self, path):
        """Prikazuje sliku na ekranu"""
        if not path or not os.path.exists(path):
            # Fallback ako nema slike
            placeholder = load_pixmap_safe(PLACEHOLDER)
            if placeholder:
                if self.gallery_type == "backdrops":
                    self["backdrop_image"].instance.setPixmap(placeholder)
                else:
                    self["poster_image"].instance.setPixmap(placeholder)
            return

        pixmap = load_pixmap_safe(path)
        if not pixmap:
            return

        # Postavi sliku na odgovarajući widget
        if self.gallery_type == "backdrops":
            self["backdrop_image"].instance.setPixmap(pixmap)
            # Podesi scale za backdrop (2 = scale to fill and crop)
            try:
                self["backdrop_image"].instance.setScale(2)  # SCALE_ASPECT_CROP
            except:
                pass
        else:
            self["poster_image"].instance.setPixmap(pixmap)
            # Podesi scale za poster (2 = scale to fill and crop)
            try:
                self["poster_image"].instance.setScale(2)  # SCALE_ASPECT_CROP
            except:
                pass

    def prev_image(self):
        """Prethodna slika"""
        if len(self.images_list) <= 1:
            return

        self.current_index = (self.current_index - 1) % len(self.images_list)
        self.load_current_image()

    def next_image(self):
        """Sledeća slika"""
        if len(self.images_list) <= 1:
            return

        self.current_index = (self.current_index + 1) % len(self.images_list)
        self.load_current_image()

    def switch_gallery_type(self):
        """Prebacuje između backdroпova i postera"""
        if self.gallery_type == "backdrops":
            # Prebaci na poster galeriju
            self.open_posters_gallery()
        else:
            # Već smo u poster galeriji, možemo zatvoriti ili ostati
            pass

    def open_posters_gallery(self):
        """Otvara galeriju postera"""
        api_key = config.plugins.ciefptmdb.tmdb_api_key.value.strip()
        if not api_key:
            self["info"].setText("TMDB API key not set!")
            return

        posters = get_all_posters(self.media_id, self.media_type, api_key)
        if not posters:
            self.session.open(MessageBox, "No posters found for this media.", MessageBox.TYPE_INFO)
            return

        def delayed_open():
            self.session.open(
                BackdropGalleryScreen,
                self.media_id,
                self.media_type,
                self.media_title,
                posters,
                0,
                "posters"
            )

        # zatvori trenutni screen
        self.close()

        # ODLOŽENO otvaranje
        t = eTimer()
        t.callback.append(delayed_open)
        t.start(100, True)

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
                "blue": self.editOmdbApiKey,
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

        omdb_status = "✓ SET" if config.plugins.ciefptmdb.omdb_api_key.value else "✗ NOT SET"
        self.menu_list.append(f"OMDb API Key: {omdb_status}")

        self.menu_list.append(f"Cache folder: {config.plugins.ciefptmdb.cache_folder.value}")

        poster_status = "YES" if config.plugins.ciefptmdb.cache_enabled.value else "NO"
        self.menu_list.append(f"Download Posters:  {poster_status}")

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

        if idx == 0:
            self.editApiKey()
        elif idx == 1:
            self.editOmdbApiKey()
        elif idx == 2:
            pass
        elif idx == 3:
            config.plugins.ciefptmdb.cache_enabled.value = not config.plugins.ciefptmdb.cache_enabled.value
            self.buildMenu()
        elif idx == 4:
            config.plugins.ciefptmdb.show_imdb_rating.value = not config.plugins.ciefptmdb.show_imdb_rating.value
            self.buildMenu()
        elif idx == 5:
            self.change_language()
        elif idx == 7:
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