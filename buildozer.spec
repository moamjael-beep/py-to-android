[app]

# App info
title = YT Downloader
package.name = ytdownloader
package.domain = org.ytdl

# Source
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.exclude_dirs = tests, bin, .buildozer, __pycache__

# Version
version = 1.0.0

# -----------------------------------------------------------------------
# Dependencies
# -----------------------------------------------------------------------
# NOTE: pytubefix needs requests + certifi + urllib3 to work on Android.
# imageio-ffmpeg and nodejs-wheel-binaries are NOT included (not Android-compatible).
requirements = python3,kivy,pytubefix,requests,certifi,urllib3,idna,charset-normalizer



# -----------------------------------------------------------------------
# Android settings
# -----------------------------------------------------------------------
android.permissions = android.permission.INTERNET, android.permission.WRITE_EXTERNAL_STORAGE, android.permission.READ_EXTERNAL_STORAGE, android.permission.MANAGE_EXTERNAL_STORAGE

android.api = 33
android.minapi = 24
android.ndk = 25c
android.sdk = 33
android.ndk_api = 24

android.archs = arm64-v8a, armeabi-v7a

# Allow backup
android.allow_backup = True

# Orientation
orientation = portrait

# Fullscreen
fullscreen = 0

# -----------------------------------------------------------------------
# Icons & Presplash (optional — remove if you have no assets)
# -----------------------------------------------------------------------
# icon.filename = %(source.dir)s/icon.png
# presplash.filename = %(source.dir)s/presplash.png

# -----------------------------------------------------------------------
# Build type
# -----------------------------------------------------------------------
# Change to 'release' and add keystore settings below for Play Store upload
android.build_type = debug

# Release signing (uncomment and fill for release build):
# android.release_artifact = aab
# android.keystore = myapp.keystore
# android.keystore_alias = myapp
# android.keystore_password = yourpassword
# android.keyalias_password = yourpassword

# -----------------------------------------------------------------------
# Python for Android (p4a)
# -----------------------------------------------------------------------
p4a.branch = develop

# Bootstrap: SDL2 is best for Kivy apps
p4a.bootstrap = sdl2

# -----------------------------------------------------------------------
# Buildozer settings
# -----------------------------------------------------------------------
[buildozer]
log_level = 2
warn_on_root = 1
