
# 🎬 CiefpTMDBSearch v2.0 - Enigma2 Plugin

![Plugin Version](https://img.shields.io/badge/Version-1.6-blue.svg)
![Python](https://img.shields.io/badge/Python-2.7-green.svg)
![Platform](https://img.shields.io/badge/Platform-Enigma2-orange.svg)

**Revolutionary TMDB search plugin for Enigma2 that makes exploring movies and series more fun than watching them!** 🍿

![CiefpTMDBSearch](https://raw.githubusercontent.com/ciefp/CiefpTMDBSearch/main/tmdb.jpg)

---

## 📸 Screenshots

### Screenshots
| Main Screen | Settings | Movies Poster  | Movies Backdrop |
|-------------|----------|----------------|-----------------|
| ![Main](https://raw.githubusercontent.com/ciefp/CiefpTMDBSearch/main/main.jpg) | ![Settings](https://raw.githubusercontent.com/ciefp/CiefpTMDBSearch/main/settings.jpg) | ![Movies](https://raw.githubusercontent.com/ciefp/CiefpTMDBSearch/main/movies.jpg) |![Movies](https://raw.githubusercontent.com/ciefp/CiefpTMDBSearch/main/movies2.jpg) |


| Series Example | Auto EPG Search | Director Profile | Actor Profile |
|----------------|-----------------|------------------|---------------|
| ![Series](https://raw.githubusercontent.com/ciefp/CiefpTMDBSearch/main/series.jpg) | ![Auto EPG](https://raw.githubusercontent.com/ciefp/CiefpTMDBSearch/main/autoepg.jpg) | ![Director Profile](https://raw.githubusercontent.com/ciefp/CiefpTMDBSearch/main/director.jpg) | ![Actor Profile](https://raw.githubusercontent.com/ciefp/CiefpTMDBSearch/main/actor.jpg)|

---

## 🚀 What's NEW in Version 1.6

### 🎯 **AUTO CAST EXPLORER** (Yellow Button)
- **One-click access** to director and main cast from current movie/series
- **Instant profiling** - explore anyone from the crew with single click
- **Seamless navigation** between actors and directors

### 📊 **SMARTER PROFILE DISPLAY**
- **Replaced confusing "Popularity" score** with meaningful information:
  - **Career years** (e.g., "50+ years")
  - **Project count** (e.g., "86 movies, 31 TV")
- **Better "Known For" sorting** - shows truly popular works

### 🎨 **ENHANCED USER EXPERIENCE**
- Improved text formatting and layout
- Optimized information display
- Better readability on all screens

---

## 🎮 Quick Start Guide

### **1. AUTO EPG SEARCH** (🔵 Blue Button)
- Click while watching TV - automatically finds current movie/series from EPG
- **Result:** Complete details about the movie/series

### **2. CAST EXPLORER** (🟡 Yellow Button) **← NEW!**
- **First:** Load any movie/series (via Auto EPG or manual search)
- **Then:** Click yellow button for cast & crew list
- **Select:** Choose anyone for instant profile
- **Result:** Automatic display of complete person profile

### **3. ADVANCED SEARCH** (🟢 Green Button)
- Manual search for movies, series, actors, directors
- **Menu options:** Search Movies, Search TV Series, Search Actors, Search Directors

### **4. BACKDROP VIEW** (OK Button)
- Toggle between classic and backdrop view
- **Classic:** Text information + poster
- **Backdrop:** Background image + poster

### **5. SETTINGS** (MENU Button)
- API keys setup (TMDB, OMDb)
- Language selection for descriptions
- Cache management
- Update checking

---

## ⚙️ Installation

### Automatic Installation:
```bash
wget -q --no-check-certificate https://raw.githubusercontent.com/ciefp/CiefpTMDBSearch/main/installer.sh -O - | /bin/sh
```

### Manual Installation:
1. Download latest release
2. Extract to `/usr/lib/enigma2/python/Plugins/Extensions/`
3. Restart Enigma2

---

## 🔑 API Configuration

### TMDB API Key (Required):
1. Get free API key from [The Movie Database](https://www.themoviedb.org/settings/api)
2. Enter in plugin settings or create `tmdbapikey.txt` in plugin folder

### OMDb API Key (Optional - for IMDB ratings):
1. Get free API key from [OMDb API](http://www.omdbapi.com/apikey.aspx)
2. Enter in plugin settings or create `omdbapikey.txt` in plugin folder

---

## 🌍 Supported Languages

- **English, Srpski, Hrvatski, Bosanski**
- **Slovenščina, Македонски, Čeština, Slovenský**
- **Magyar, Română, Български, Ελληνικά**
- **Deutsch, Français, Español, Italiano**
- **Português, Nederlands, Svenska, Norsk**
- **Dansk, Suomi, Русский, Українська**
- **Polski, Türkçe, العربية, עברית**
- **日本語, 한국어, 中文, ไทย, Tiếng Việt**

---

## 💡 Pro Tips

1. **Fastest Workflow:** Blue → Yellow = Instant info about everyone in the movie!
2. **For Research:** Green button for detailed search of anyone/anything
3. **For Atmosphere:** OK button to switch to beautiful backdrop images
4. **For Accuracy:** OMDb API key for IMDB ratings (optional)

---

## 🐛 Bug Reports & Feature Requests

Found a bug? Have an idea? 
- [Open an Issue](https://github.com/ciefp/CiefpTMDBSearch/issues)
- [Discussions](https://github.com/ciefp/CiefpTMDBSearch/discussions)

---

## 📊 Version Comparison: v1.5 vs v1.6

| Feature | v1.5 | v1.6 |
|---------|------|------|
| Auto Cast Explorer | ❌ | ✅ |
| Career Information | ❌ | ✅ |
| Project Count Display | ❌ | ✅ |
| Smart "Known For" Sorting | ❌ | ✅ |
| Enhanced Profile Layout | ❌ | ✅ |
| Better TMDB Data Handling | ❌ | ✅ |

---

## 🎉 Why v1.6 is Revolutionary

✅ **Faster** - Less clicking, more information  
✅ **Smarter** - Automatic connections between people and projects  
✅ **More Useful** - Real information instead of confusing numbers  
✅ **More Fun** - Like exploring film history!  

**Now exploring movies and series is more entertaining than watching them!**

---

## 📄 License

This project is licensed under the GPL v2 License - see the [LICENSE](LICENSE) file for details.

---

## Special Thanks

This plugin was developed with the assistance of various AI platforms that provided coding help, ideas, and solutions:

- **DeepSeek AI** - for extensive coding assistance and feature implementation
- **ChatGPT** - for creative solutions and debugging help  
- **Grok** - for technical insights and optimization suggestions
- **Qwen** - for additional coding support and testing ideas

While the original concept was mine, these AI assistants each contributed valuable perspectives that helped shape the final plugin. Thank you all!

..::CiefpSettings ::..

## 👨‍💻 Developer

**ciefp** - [GitHub Profile](https://github.com/ciefp)

*If you enjoy this plugin, consider giving it a ⭐ on GitHub!*
```
