# stalker_overlay_display.py
#
# Your overlay with the slide-down digital display.
#
# - The whole message system runs from launch, whether the monitor is visible or not.
#   While the monitor is up, new messages still arrive (with the ping sound) but are
#   invisible. Press + : the monitor slowly slides down and the messages ride
#   down WITH it, already on the screen. Press - : it slides back up (numpad or main keyboard).
# - The typewriter effect only plays when a message appears in an EMPTY slot while the
#   monitor is down. A new message that REPLACES an older one just swaps in instantly.
# - The monitor changes height with the content: for a single random message it sits higher
#   (room for 1 message); when a conversation starts it slides lower (room for 2 messages),
#   and goes back up when the conversation ends.
# - RANDOM messages: own size/position profile, persist until the next random one.
# - CONVERSATIONS: message 1 goes in the TOP slot and stays, the reply goes in the
#   BOTTOM slot. Every new message after that appears at the bottom and BOUNCES the
#   previous one upwards into the top slot (the one that was on top is erased).
# - While a conversation waits for the next reply, typing dots ( • • • ) show in the slot where the
#   reply will land, starting DOTS_START_DELAY_MS after the previous message was written.
# - Started with  --with-game  (see launch_stalker2_with_overlay.bat): the overlay quits by
#   itself when the game closes. Without that flag it runs until you close it.
# - A message can't repeat within the last RECENT_BLOCK_COUNT messages that were SHOWN
#   (random AND conversation messages, compared by text, remembered across restarts).
# - A name keeps the same fallback portrait every time (saved in character_assignments.json).
# - No ReShade, no REST bridge.
#
# Needs:  pip install PyQt5      (no 'keyboard' module needed any more)
# Folders (same as before): messages/messages.txt, images/<faction>/, images/characters/,
#   images/default.png, images/display.png, fonts/, ping.wav

import sys
import os
import re
import json
import random
import ctypes
import time
import threading
import subprocess
import atexit
import traceback
from collections import deque
from pathlib import Path

from PyQt5 import QtWidgets, QtGui, QtCore

try:
    from PyQt5.QtMultimedia import QSoundEffect
    _QSE_AVAILABLE = True
except Exception:
    _QSE_AVAILABLE = False
try:
    from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
    _QMP_AVAILABLE = True
except Exception:
    _QMP_AVAILABLE = False

# ============================================================
# CONFIG
# ============================================================

if getattr(sys, "frozen", False):                  # running as the packaged .exe: the folders sit next to the exe
    BASE_DIR = Path(sys.executable).parent.resolve()
else:
    BASE_DIR = Path(__file__).parent.resolve()

MESSAGES_FILE = BASE_DIR / "messages" / "messages.txt"
IMAGES_DIR = BASE_DIR / "images"
CHARACTERS_DIR = IMAGES_DIR / "characters"
SOUND_FILE = BASE_DIR / "ping.wav"       # the ping is found automatically: sounds/ping.wav, ping.wav, sounds/ping.mp3 or ping.mp3
PING_VOLUME = 22                         # 0 (silent) .. 100 (full)
DEFAULT_AVATAR_NAME = "scientist4.png"   # picture used when a character has no picture (looked up in images/characters and every images/<faction> folder)
FONTS_DIR = BASE_DIR / "fonts"
DEFAULT_IMAGE = IMAGES_DIR / "default.png"
ASSIGN_FILE = BASE_DIR / "character_assignments.json"
RECENT_FILE = BASE_DIR / "recent_messages.json"
PID_FILE = BASE_DIR / "overlay.pid"

# ---------------- game link (only used with --with-game) ----------------
GAME_EXE = "Stalker2-Win64-Shipping.exe"   # the game's process name
GAME_CHECK_MS = 5000                        # how often to look for the game
QUIT_WHEN_STEAM_CLOSES = True               # also quit when Steam itself is closed
STEAM_EXE = "steam.exe"
GAME_START_TIMEOUT_S = 600                  # quit if the game never starts within 10 minutes

# ---------------- digital display ----------------
DISPLAY_IMAGE = IMAGES_DIR / "display.png"
# BLOOD / DIRT LAYER: letters hide BEHIND things you paint on the monitor (blood splatter, cracks, dirt).
# Best: make images/blood.png = same size as display.png, transparent everywhere except the blood.
# No blood.png? Then the red parts of display.png are picked out automatically (BLOOD_AUTO).
BLOOD_ON_TOP = True
# Easiest: outline the things that must cover the letters as polygons, in PIXELS OF YOUR display.png
# (its original size). Everything inside a polygon is drawn on top of the text. Add more polygons
# (more [ (x,y), (x,y), ... ] lists) for more plasters / splatters. This one is the white plaster.
BLOOD_POLYGONS = [
    [(1034, 553), (1038, 540), (1042, 533), (1044, 533), (1089, 549), (1089, 550), (1087, 554),
     (1082, 563), (1079, 568), (1078, 569), (1075, 569), (1048, 560)],
]
BLOOD_IMAGE = IMAGES_DIR / "blood.png"   # used when BLOOD_POLYGONS is empty (same size as display.png, transparent except the blood)
BLOOD_AUTO = False                       # used when there is neither: pick the red pixels of display.png
BLOOD_MIN_RED = 90                       # auto mode: a pixel counts as blood if red >= this ...
BLOOD_RED_OVER = 45                      # ... and red is at least this much higher than green and blue
DISPLAY_SCALE = 1.0
DISPLAY_DX_CM, DISPLAY_DY_CM = -74, -2   # where the display sits when it is DOWN

# ---------------- random GIF transmissions ----------------
GIFS_DIR = BASE_DIR / "vids"             # put bolt.gif, energy.gif, etc. here
# ---- TEST / VIDEO MODES: force one kind of content, one after the other (set ONE to True) ----
ONLY_CONVERSATIONS = False              # only 2-person conversations, back to back
ONLY_GIFS = False                       # only GIF messages + their gifs, back to back
ONLY_RANDOM_MESSAGES = False            # only single random messages
NORMAL_MODE = True                      # True = everything normal and random (the three above are ignored)
CONVERSATION_CHANCE = 0.3               # chance per message interval that a 2-person conversation starts instead of a single message (1 = always, 0.3 = 30%, 0 = never)
GIF_EVENT_CHANCE = 0.0                  # chance per message interval for a RANDOM GIF (0 = off; GIFs now follow GIF_MESSAGES)
GIF_PLAYBACK_SPEED_PERCENT = 100          # 80 = about 20% slower than the GIF's authored timing
GIF_AREA_HEIGHT = 220                    # space occupied by the GIF between the two conversation slots
GIF_MAX_WIDTH = 1600                     # (not used any more - see GIF_BOX_W / GIF_BOX_H)
# Every GIF is shown in the SAME box. The GIF is scaled to FILL the box (no stretching);
# whatever sticks out past the edges is cropped. Make the box the size of your monitor screen.
GIF_BOX_W = 880
# The GIF waits (hidden, paused) until the monitor is open, then it "buffers in": it starts very
# blurred and dim and slowly sharpens while it plays.
GIF_BLUR_IN = True
GIF_BLUR_RADIUS = 40                     # how blurry it starts (0 = sharp)
GIF_BLUR_IN_MS = 4300                    # how long it takes to become sharp
GIF_EXIT_MS = 1500                       # the GIF blurs out and fades away like this when it ends (0 = vanish instantly)
GIF_START_OPACITY = 0.15                 # how faint it starts (fades up to 1)
GIF_BOX_H = 550
# MOVE THE GIF on the monitor, in millimetres from its default spot:
#   GIF_DX_MM  + = right, - = left          GIF_DY_MM  + = down, - = up
GIF_DX_MM = -27.0
GIF_DY_MM = 35.0
# CURVED SCREEN: the GIF is bent a little, like a slightly curved monitor.
GIF_CURVE_PERCENT = 6.5                  # top and bottom edges bow: edges are this % shorter than the middle (0 = flat)
GIF_CURVE_SIDES_PERCENT = 5.0            # same for the left/right edges (try 2-4 if you want it)
GIF_CURVE_STRIP_PX = 1                   # smoothness of the bend (smaller = smoother, a bit slower)

# ---------------- messages that are followed by a GIF ----------------
# (name, faction, message text, gif file in the vids folder)
GIF_MESSAGES = [
    ("Anatoly Markov", "Loners", "remember throw a bolt and run like hell", "bolt.gif"),
    ("Grigori Vekov", "Loners", "Remember to take your energy drinks when going near the poppy field.", "energy.gif"),
    ("Dmitri Morozov", "Loners", "Found a truck lying on it's side in Cordon. Legends are it was Strelok's.", "killstrelok.gif"),
    ("Mikhail Yakovlev", "Scientist", "Guys this is called a magic cube. It gives a lot of Physical Protection. Found in gravitational spots", "magiccube.gif"),
    ("Alexey Strakhov", "Scientist", "Teleporter found in Rostok", "map.gif"),
    ("Igor Zhdanov", "Loners", "Saw a snork eating my friend today :'(", "snork.gif"),
    ("Sidorovich", "Trader", "Buy 2 guns get the second gun free ;)", "Sidad.gif"),
    ("Anonymous", "Loners", "Just took out a bunch of Loners alone!", "explosion.gif"),
]
GIF_UPLOAD_TEXT = "gif uploading..."
GIF_UPLOAD_COLOR = "#FFB000"             # amber "status" colour; other good ones: "#00E5FF" (cyan), "#B8FF9A" (pale green), "#FF7A1A" (orange)
GIF_UPLOAD_GLOW_COLOR = ""               # "" = glow in the same colour as the text
GIF_UPLOAD_GLOW_STRENGTH = 2.0           # glow of the uploading line: 0 = none, 1 = normal, 2 = strong, 3 = very strong
GIF_UPLOAD_GLOW_RADIUS = 12              # how far its glow spreads (pixels)
GIF_UPLOAD_MOVE_MM = (100.0, 15.0)       # move ONLY the uploading line, measured from where the message text STARTS (so message length never matters): (right+/left-, down+/up-) in mm. Nothing else moves.
GIF_UPLOAD_BASE_TEXT = "gif uploading"   # the dots after it animate like the conversation typing dots
GIF_UPLOAD_AFTER_MS = 3000               # the "gif uploading..." text appears this long after the message is written
GIF_START_AFTER_MS = 4000                # the GIF starts this long after the text appeared
# (the timers only run while the monitor is open - they wait while it is up)

# Hotkeys = Windows virtual-key codes, read by polling (works without the 'keyboard' module).
#   Numpad + 0x6B   Numpad - 0x6D   main-keyboard + 0xBB   main-keyboard - 0xBD
#   Numpad 0-9: 0x60-0x69 (keep NumLock ON)
#   Up arrow 0x26   Down 0x28   Left 0x25   Right 0x27
#   F8 0x77   F9 0x78   F10 0x79   Insert 0x2D   Home 0x24   Pause 0x13
HOTKEY_DOWN_VKS = (0x6B, 0xBB)   # + (numpad or main keyboard) -> monitor comes down
HOTKEY_UP_VKS = (0x6D, 0xBD)     # - (numpad or main keyboard) -> monitor goes back up
HOTKEY_DOWN_NAME = "+"
HOTKEY_UP_NAME = "-"
HOTKEY_POLL_MS = 25

SLIDE_DOWN_MS = 2500     # how slowly the display comes down (bigger = slower)
SLIDE_UP_MS = 2000       # how fast it goes back up
# Easing for the way DOWN. "OutCubic" starts moving at once and settles gently (no dead start).
# The old "InOutCubic" starts very slowly, which feels like a delay. Going up keeps InOutCubic.
SLIDE_DOWN_EASING = "OutCubic"

# ---------------- monitor height follows the content ----------------
# In random mode the monitor sits this much HIGHER than its full-down position (so there is room
# for only one message). In conversation mode it sits at DISPLAY_DX_CM / DISPLAY_DY_CM as before.
# 0 = switched off. The random message itself stays where PROFILES["random"] puts it on the screen.
MONITOR_RAISE_RANDOM_CM = 10.0
# Moves ONLY the random-message text up (+) or down (-) on screen. The monitor never moves
# because of this. Leave PROFILES["random"]["dy_cm"] alone and change this number instead.
RANDOM_TEXT_UP_CM = 0.0
MODE_SLIDE_MS = 1500        # how fast the monitor moves between the random and conversation heights

# ---------------- positions (same formula as your original) ----------------
PANEL_MARGIN_X, PANEL_MARGIN_Y = 60, 60
PANEL_WIDTH = 1000

# ---------------- message styles ----------------
# Portrait size: the  avatar=  number in each profile below is the portrait HEIGHT in pixels.
# Small pictures are now enlarged to that height too (before, they were only ever shrunk).
AVATAR_SCALE_UP = False
SHOW_FACTION = False      # True = show the faction in brackets after the name, e.g. (Loners)

# MOVE ONLY THE PORTRAIT (the text stays where it is), in millimetres: (right +/left -, down +/up -)
# (dx_cm / dy_cm in the profiles below still move the WHOLE message, text included.)
# MOVE ONLY THE TEXT (name, faction, message; the portrait stays where it is), same units:
TEXT_MOVE_MM = {
    "random":       (0.0, 0.0),
    "convo_top":    (0.0, 0.0),
    "convo_bottom": (0.0, 0.0),
}
# Text starts a FIXED distance from the left edge (= the avatar= number of the profile), so the
# portrait's size or position never pushes the text any more.
# Old-Soviet-screen look: a slight blur on all the text (0 = sharp; try 0.6 - 1.5)
TEXT_BLUR_RADIUS = 1.8

# ---------------- TEXT COLOURS AND CRT GLOW (name + message) ----------------
# Colours are any CSS colour: "#39FF14" (neon green), "lime", "#00ff66" ...
NAME_COLOR = "#B8FF9A"
MESSAGE_COLOR = "#B8FF9A"
# (the "gif uploading..." line uses GIF_UPLOAD_COLOR, the users counter has its own settings further down)
TEXT_GLOW_STRENGTH = 2.0        # 0 = no glow, 1 = normal, 2 = strong, 3 = very strong
TEXT_GLOW_RADIUS = 200           # how far the glow spreads (pixels)
TEXT_GLOW_COLOR = ""            # "" = glow has the same colour as the text; or set e.g. "#00ff66"
MSG_PAD = 150    # transparent safety margin around each message so a moved portrait/text is never cut off

AVATAR_MOVE_MM = {
    "random":       (5.0, 6.0),
    "convo_top":    (0.0, 0.0),
    "convo_bottom": (0.0, 0.0),
}

PROFILES = {
    # same look and spot on the monitor as the conversation's top message
    "random": dict(font=13, words=8, name=30, faction=0, avatar=190,
                   dx_cm=-65.7, dy_cm=-2),
    "convo_top": dict(font=13, words=8, name=28, faction=-200, avatar=170,
                      dx_cm=-65, dy_cm=-1),
    "convo_bottom": dict(font=13, words=8, name=28, faction=-200, avatar=170,
                         dx_cm=-65, dy_cm=7),
}

# ---------------- timings ----------------
TYPING_INTERVAL_MS = 30
TEST_MODE = False
MIN_INTERVAL_SEC, MAX_INTERVAL_SEC = 60, 60      # SECONDS between messages (a random time between the two numbers), e.g. 20, 45

START_ENGINE_AT_LAUNCH = True        # True = messages run from launch; False = start at first Down press
INITIAL_MESSAGE_DELAY_MS = 2000      # first message this long after launch
NO_SOUND_FIRST_MS = 5 * 60 * 1000    # no ping for this long after the game starts (messages still appear)
                                     # (with --with-game it counts from the moment the game is detected;
                                     #  otherwise from launching the script)
TYPEWRITER_ON_REPLACE = False        # False = a replacing message swaps in instantly (no typewriter)

CONVERSATION_REPLY_DELAY_MS = 7000   # after a message finishes typing, wait this long for the reply
DOTS_START_DELAY_MS = 3000           # typing dots appear this long after the previous message was written
DOTS_INTERVAL_MS = 400               # speed of the dots animation
TYPEWRITER_AFTER_DOTS = False        # False = the reply simply replaces the dots; True = it types in
CONVERSATION_END_HOLD_MS = 6000      # after the LAST message finishes typing, hold this long
# If the monitor is up when a conversation step is due, the conversation PAUSES until the
# monitor is fully down again, then waits the delay above and continues.
BOUNCE_MS = 900                      # how long the old message takes to bounce up
NEW_MESSAGE_START_DELAY_MS = 350     # new message starts typing this long after the bounce begins
RANDOM_REPLACE_DELAY_MS = 2000       # pause between erasing a random message and the next one
POST_CONVERSATION_DELAY_MS = 5000    # after a conversation ends, wait before the next random

# ---------------- random message replace: the old one bounces up and away ----------------
RANDOM_BOUNCE_UP_CM = 4.0            # how far the old random message flies up
RANDOM_BOUNCE_MS = 900               # how long that takes (it fades out while moving)
RANDOM_TYPEWRITER = True              # the new random message types in (typewriter) after the old one is gone
# Radio-glitch: while a message sits on the monitor it now and then flickers - a few letters turn into
# random characters for a moment, then settle. A random number of times per message, never constant.
GLITCH_ENABLED = True
# ---- ALL-AT-ONCE GLITCH: now and then the WHOLE monitor glitches together (every visible name, message and
# portrait), glitch.gif plays BEHIND the text, and the users counter drops to 0 until the glitch is over.
GLITCH_GLOBAL = True                 # False = the old separate glitches per message
GLITCH_EVERY_SEC = (25, 70)          # a glitch happens every random(min, max) seconds
GLITCH_SOUND_NAME = "glitch.mp3"     # plays while the glitch lasts (looked for in the sounds/, vids/ and script folders)
GLITCH_SOUND_VOLUME = 20             # 0 (silent) .. 100 (full)
GLITCH_GIF_NAME = "glitch.gif"       # looked for in vids/, images/ and next to the script
GLITCH_GIF_OPACITY = 0.7             # 1 = fully visible noise, 0.3 = faint
# glitch.gif while the monitor is DOWN (conversation height): same box as the other GIFs, then moved by mm
GLITCH_GIF_DOWN_DX_MM = 0.0          # right+ / left-
GLITCH_GIF_DOWN_DY_MM = 0.0          # down+ / up-
# glitch.gif while the monitor is UP (random-message height): smaller. Size in pixels; position in mm from the
# top-left corner of the random message (right+ / left-, down+ / up-)
GLITCH_GIF_UP_W = 850
GLITCH_GIF_UP_H = 200
GLITCH_GIF_UP_DX_MM = 0.0
GLITCH_GIF_UP_DY_MM = -5.0
GLITCH_MAX_PER_MESSAGE = 3           # each message glitches 0 .. this many times (random)
GLITCH_FIRST_AFTER_MS = 4000         # never right after the message appears
GLITCH_WINDOW_MS = 45000             # all glitches of a message happen inside this time after it appeared
GLITCH_MIN_GAP_MS = 8000             # at least this long between two glitches
GLITCH_FRAMES = (3, 6)               # one glitch = this many flicker frames (random)
GLITCH_FRAME_MS = 280                # length of one flicker frame
GLITCH_CHAR_FRAC = (0.04, 0.12)      # share of the letters that get scrambled (only a few)
GLITCH_NAME = True                   # the name and faction flicker too (a few letters)
GLITCH_PICTURE = True                # the portrait flickers (fades in and out for a moment)
GLITCH_JITTER = True                 # the whole message jumps sideways a few pixels
GLITCH_JITTER_PX = 6
GLITCH_COLOR_FLASH = False            # name and text flash a colour for a frame
GLITCH_COLORS = ("#ff3b3b", "#3bff6a", "#3be6ff")
GLITCH_DOUBLE_IMAGE = False           # the portrait splits into a red and a blue copy
GLITCH_GHOST_PX = 5
GLITCH_SCANLINES = False              # thin scan lines with a bright band sweeping down
GLITCH_CHARS = "#@%&?*+=/\\|<>01XZ$~"
RANDOM_NEW_DELAY_MS = 200            # the new message appears this long AFTER the old one is totally gone

# ---------------- "users connected" counter on the monitor ----------------
SHOW_USERS_COUNTER = True
USERS_MIN, USERS_MAX = 150, 180      # the number stays between these
USERS_STEP = 4                       # changes by up to +/- this much every update
USERS_UPDATE_MS = 5000               # new number every 5 seconds
USERS_ROLL_MS = 90                   # the number rolls: it counts through every value, this long per step
USERS_TEXT = "Users connected: {n}"
USERS_FONT_SIZE = 9
USERS_COLOR = "#FFB000"
USERS_GLOW_STRENGTH = 1.0        # glow of the users counter (separate from the name/message glow)
USERS_GLOW_RADIUS = 6
USERS_GLOW_COLOR = ""            # "" = same colour as USERS_COLOR
USERS_SOFTNESS = 0.8             # slight blur of the users text (0 = sharp)
# Where it sits ON THE MONITOR IMAGE: fraction of the image width/height from its top-left corner,
# plus a nudge in cm (right/down positive). It rides with the monitor.
USERS_X_FRAC, USERS_Y_FRAC = 0.11, 0.26
USERS_NUDGE_X_CM, USERS_NUDGE_Y_CM = -0.4, 0.1

# ---------------- menu / inventory detection (mouse cursor trick) ----------------
# While you play the game hides the mouse cursor; in the inventory, map and pause menu it shows it.
# If the cursor stays visible, the monitor goes up by itself; when it is gone the monitor comes back.
MENU_DETECT = True
MENU_POLL_MS = 200
MENU_HIDE_DELAY_MS = 1500            # cursor visible this long -> monitor slides up
MENU_SHOW_DELAY_MS = 1000            # cursor gone this long -> monitor slides back down
MENU_ONLY_WHEN_GAME_FOCUSED = True   # only react while the game window is the active window
MENU_DEBUG = True                    # print what the cursor check sees whenever it changes

PING_WHEN_MONITOR_UP = True         # (the ping now always plays, monitor up or down; only the first minutes after the game starts are silent) play the ping for new messages even while the monitor is up
RECENT_BLOCK_COUNT = 180              # a message can't repeat within this many messages


# ============================================================
# CONVERSATIONS
# ============================================================

CONVERSATIONS = [
    [("Kolyan Dubrovsky", "Bandits", "Fuck you Vanya!"),
     ("Vanya Kozlov", "Bandits", "Fuck you Kolyan!")],

    [("Roman Bellicov", "Loner", "Niko it's your cousin. Let's go artifact hunting."),
     ("Niko Bellicov", "Mercenary", "Sorry cousin I can't now. Im busy."),
     ("Roman Bellicov", "Loner", "👎")],

    [("Makar Lysenko", "Scientist", "I just saw a jellyfish artifact...."),
     ("Makar Lysenko", "Scientist", "It was not an artifact!")],

    [("Vitaly Vetrov", "Duty", "How is your face Boris? Don't fuck with me again!"),
     ("Boris Ignatov", "Freedom", "Tis but a scratch....")],

    [("Dimitri", "Bandit", "У мене не працює автоматичний переклад."),
     ("Jules", "Bandit", "English, motherfucker. Do you speak it?")],

    [("Janko Halpertovych", "Loners", "I Just had the biggest Sausage I've ever seen."),
     ("Michal Skotko", "Loners", "That's what she said!")],

    [("Dutch", "Bandits", "I have a plan!"),
     ("Artur", "Bandits", "Guys! Dutch just walked into a gravitational anomaly..."),
     ("Artur", "Bandits", "Again..."),
     ("Micha", "Bandits", "Skill issue....")],

    [("Arnold", "Duty", "I'll be back!"),
     ("Schwartz", "Freedom", "Yeah we will see...")],

    [("Oleg Ignatov", "Bandit", "Who took my vodka?"),
     ("Igor Moroz", "Bandit", "What vodka?"),
     ("Oleg Ignatov", "Bandit", "Exactly!")],

    [("Maksym Rybakov", "Loner", "There's an anomaly near the road."),
     ("Dima Orlov", "Loner", "Which one?"),
     ("Maksym Rybakov", "Loner", "The one that kills you."),
     ("Dima Orlov", "Loner", "Very Helpful.....")],

    [("Petr Sorokin", "Loner", "Anyone have spare medkits?"),
     ("Igor Zhdanov", "Loner", "No."),
     ("Petr Sorokin", "Loner", "Bandages?"),
     ("Oleg Krylov", "Loner", "No."),
     ("Petr Sorokin", "Loner", "Hope?"),
     ("Viktor Volkov", "Loner", "No."),
     ("Petr Sorokin", "Loner", "Assholes!")],

    [("Evgeny Gromov", "Loner", "Bloodsucker at my position!"),
     ("Andrei Karpov", "Duty", "Shoot it."),
     ("Evgeny Gromov", "Loner", "With what?"),
     ("Andrei Karpov", "Duty", "Your gun."),
     ("Evgeny Gromov", "Loner", "Which one?"),
     ("Andrei Karpov", "Duty", "..."),
     ("Andrei Karpov", "Duty", "Idiot.")],

    [("Makar Lysenko", "Scientist", "Don't enter the bunker."),
     ("Vasily Orlov", "Loner", "Why?"),
     ("Makar Lysenko", "Scientist", "Burer."),
     ("Vasily Orlov", "Loner", "How many?"),
     ("Makar Lysenko", "Scientist", "I don't know."),
     ("Vasily Orlov", "Loner", "Nice...")],

    [("Makar Lysenko", "Scientist", "Who touched the artifact?"),
     ("Igor Zhdanov", "Loner", "Nobody."),
     ("Makar Lysenko", "Scientist", "It's gone."),
     ("Igor Zhdanov", "Loner", "..."),
     ("Makar Lysenko", "Scientist", "Who touched it?"),
     ("Igor Zhdanov", "Loner", "Nobody! stop asking!")],

    [("Sidorovich", "Trader", "I have a job for you."),
     ("Roman Bellicov", "Loner", "How much?"),
     ("Sidorovich", "Trader", "500 coupons."),
     ("Roman Bellicov", "Loner", "No."),
     ("Sidorovich", "Trader", "600."),
     ("Roman Bellicov", "Loner", "I'm listening."),
     ("Niko Bellicov", "Mercenary", "Cousin don't....")],

    [("Makar Lysenko", "Scientist", "I just stepped on human shit!"),
     ("Makar Lysenko", "Scientist", "WTF guys!")],
]


# A specific message always uses a specific picture (file name; looked up in images/characters and every images/<faction> folder)
MESSAGE_AVATARS = {
    "Just took out a bunch of Loners alone!": "scientist4.png",
}

CHARACTER_IMAGES = {
    "michal skotko": "Michal.png",
    "wolf": "Wolf.png",
    "janko halpertovych": "Janko.png",
    "roman bellicov": "Roman.png",
    "niko bellicov": "Niko.png",
    "makar lysenko": "Makar.png",
    "sidorovich": "Sidorovich.png",
    "igor zhdanov": "IgorZhdanov.png",
    "vasily orlov": "Vasily.png",
    "andrei karpov": "Andrei.png",
    "evgeny gromov": "Evgeny.png",
    "petr sorokin": "Petr.png",
    "viktor volkov": "Viktor.png",
    "dima orlov": "Dima.png",
    "oleg krylov": "OlegKrylov.png",
    "maksym rybakov": "Maksym.png",
    "igor moroz": "IgorMoroz.png",
    "oleg ignatov": "OlegIgnatov.png",
    "schwartz": "Schwartz.png",
    "arnold": "Arnold.png",
    "artur": "Artur.png",
    "micha": "Micha.png",
    "dimitri": "Dimitri.png",
    "jules": "Jules.png",
    "boris ignatov": "Boris.png",
    "vanya kozlov": "Vanya.png",
    "kolyan dubrovsky": "Kolyan.png",
    "birch": "Birch.png",
    "odorf sniggab": "Odorf.png",
    "jan snech": "Jan.png",
    "forrest": "Forrest.png",
    "steve": "Steve.png",
    "obi": "Obi.png",
    "bormir": "Bormir.png",
    "cj": "CJ.png",
    "herman granger": "Herman.png",
    "vitaly vetrov": "Vitaly.png",
    "dutch": "Dutch.png",
}


# ============================================================
# SETTINGS FILE  (settings.txt next to this program)
# ============================================================
# Every line "NAME = value" in settings.txt replaces the value of the same NAME above. Lines starting
# with # are comments. Strings may be written with or without quotes, true/false for on/off.
# A dict entry is written with a dot:  PROFILES.random.font = 14   or   TEXT_MOVE_MM.random = (0, 0)
# If a line is wrong it is ignored (and noted in overlay_debug.txt). No settings.txt = built-in values.

SETTINGS_FILE = BASE_DIR / "settings.txt"
_SETTINGS_NOTES = []


def _parse_setting_value(raw):
    import ast
    t = raw.strip()
    low = t.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    try:
        return ast.literal_eval(t)
    except Exception:
        return t.strip("\"'")


def _coerce_setting(old, new):
    """Return `new` converted to the type of `old`, or raise ValueError."""
    if isinstance(old, Path):
        raise ValueError("folders and files cannot be changed here")
    if isinstance(old, bool):
        if isinstance(new, bool):
            return new
        raise ValueError("expected true or false")
    if isinstance(old, (int, float)):
        if isinstance(new, bool) or not isinstance(new, (int, float)):
            raise ValueError("expected a number")
        return float(new) if isinstance(old, float) else (int(new) if float(new) == int(new) else new)
    if isinstance(old, str):
        return str(new)
    if isinstance(old, tuple):
        if isinstance(new, (tuple, list)):
            return tuple(new)
        raise ValueError("expected a pair like (1, 2)")
    if isinstance(old, list):
        if isinstance(new, (tuple, list)):
            return list(new)
        raise ValueError("expected a list")
    return new


def _apply_user_settings():
    if not SETTINGS_FILE.exists():
        return
    try:
        lines = SETTINGS_FILE.read_text(encoding="utf-8-sig").splitlines()
    except Exception as e:
        _SETTINGS_NOTES.append(f"could not read settings.txt: {e}")
        return
    g = globals()
    applied = 0
    for n, line in enumerate(lines, 1):
        t = line.strip()
        if not t or t.startswith("#") or t.startswith(";") or t.startswith("["):
            continue
        if "=" not in t:
            _SETTINGS_NOTES.append(f"settings.txt line {n}: no '=' found - ignored")
            continue
        key, raw = t.split("=", 1)
        key = key.strip()
        parts = key.split(".")
        try:
            val = _parse_setting_value(raw)
            if parts[0] not in g or parts[0].startswith("_"):
                raise ValueError("unknown setting")
            if len(parts) == 1:
                g[key] = _coerce_setting(g[key], val)
            else:
                d = g[parts[0]]
                for k in parts[1:-1]:
                    d = d[k]
                if not isinstance(d, dict) or parts[-1] not in d:
                    raise ValueError("unknown entry")
                d[parts[-1]] = _coerce_setting(d[parts[-1]], val)
            applied += 1
        except Exception as e:
            _SETTINGS_NOTES.append(f"settings.txt line {n} ({key}): {e} - ignored")
    _SETTINGS_NOTES.append(f"settings.txt: {applied} setting(s) loaded")


_apply_user_settings()


# ============================================================
# HELPERS
# ============================================================

LOG_FILE = BASE_DIR / "overlay_debug.txt"


def debug(msg):
    print("[overlay]", msg)
    try:                                   # also written to a file: pythonw has no console
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + str(msg) + "\n")
    except Exception:
        pass


def load_lines(path):
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [ln.strip() for ln in f.readlines() if ln.strip()]
    except Exception as e:
        debug(f"Failed reading messages: {e}")
        return []


_messages = load_lines(MESSAGES_FILE)
if not _messages:
    _messages = ["TestUser(Bandit): Hello world!", "OtherUser(Duty): Another message"]

_factions = (
    [d.name.lower() for d in IMAGES_DIR.iterdir()
     if d.is_dir() and d.name.lower() != "characters"]
    if IMAGES_DIR.exists()
    else ["bandit", "duty", "freedom", "loner", "scientist"]
)
if not _factions:
    _factions = ["loner"]

_faction_re = re.compile(r"\(([^)]+)\)")


def message_key(text):
    """Normalised text used to recognise 'the same message' (case/spacing/punctuation ignored)."""
    t = re.sub(r"\W+", " ", (text or "").lower()).strip()
    return t or (text or "").strip().lower()


def line_text(line):
    """The message part of a 'Name(Faction): text' line."""
    return line.split(":", 1)[1].strip() if ":" in line else line.strip()


def scramble_text(text, frac):
    """Replace only a FEW letters (about `frac` of them, at least 2) with random characters."""
    chars = list(text)
    idx = [i for i, c in enumerate(chars) if not c.isspace()]
    if not idx:
        return text
    k = min(len(idx), max(2, int(len(idx) * frac)))
    for i in random.sample(idx, k):
        chars[i] = random.choice(GLITCH_CHARS)
    return "".join(chars)


def wrap_message(text, words_per_line):
    words = text.split()
    if not words:
        return ""
    return "\n".join(" ".join(words[i:i + words_per_line])
                     for i in range(0, len(words), words_per_line))


def extract_parts(line):
    parts = line.split(":", 1)
    prefix = parts[0].strip() if parts else ""
    message_text = parts[1].strip() if len(parts) > 1 else ""

    m = _faction_re.search(prefix)
    faction = m.group(1).strip().lower() if m else None
    name = prefix.split("(")[0].strip() if "(" in prefix else prefix

    if not faction:
        for f in _factions:
            if f in prefix.lower():
                faction = f
                break
    if not faction:
        faction = random.choice(_factions)
    return faction, name, message_text


# ---------------- images ----------------

def images_for_faction(faction):
    faction = (faction or "").lower().strip()
    folder = IMAGES_DIR / faction
    if not folder.exists():
        alt1 = IMAGES_DIR / (faction + "s")
        alt2 = IMAGES_DIR / faction.rstrip("s")
        if alt1.exists():
            folder = alt1
        elif alt2.exists():
            folder = alt2
    if not folder.exists():
        return []
    return [str(p) for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp")]


def _load_assignments():
    try:
        return json.loads(ASSIGN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


_assignments = _load_assignments()


def _save_assignments():
    try:
        ASSIGN_FILE.write_text(json.dumps(_assignments, indent=2), encoding="utf-8")
    except Exception as e:
        debug(f"Could not save assignments: {e}")


def assigned_faction_image(name, faction):
    """A name always keeps the same fallback image; different names get different images when possible."""
    key = (name or "").strip().lower()

    path = _assignments.get(key)
    if path and (BASE_DIR / path).exists():
        return str(BASE_DIR / path)

    imgs = images_for_faction(faction)
    if not imgs:
        return None

    rel = sorted(os.path.relpath(i, BASE_DIR) for i in imgs)
    use_count = {}
    for p in _assignments.values():
        use_count[p] = use_count.get(p, 0) + 1
    least = min(use_count.get(r, 0) for r in rel)
    pick = random.choice([r for r in rel if use_count.get(r, 0) == least])

    _assignments[key] = pick
    _save_assignments()
    return str(BASE_DIR / pick)


_RECENT_AVATARS = deque(maxlen=6)      # (name, image) of the last portraits shown
_AVATAR_SHOWN = {}                     # image -> how many times shown (to cycle through all of them)


def _norm(p):
    return os.path.normcase(os.path.abspath(p)) if p else p


def default_avatar():
    """Picture for anyone without one: DEFAULT_AVATAR_NAME, else images/default.png."""
    f = _find_image_file(DEFAULT_AVATAR_NAME)
    if f:
        return f
    return str(DEFAULT_IMAGE) if DEFAULT_IMAGE.exists() else None


def _find_image_file(filename):
    for folder in [CHARACTERS_DIR] + (sorted(d for d in IMAGES_DIR.iterdir() if d.is_dir()) if IMAGES_DIR.exists() else []):
        f = folder / filename
        if f.exists():
            return str(f)
    return None


def get_character_image(name, faction, text=None):
    """Portrait for a name, but never the same picture right after another person's:
    a person keeps their picture while they are talking, other people get a different one."""
    key = (name or "").strip().lower()
    if text:
        fixed = {message_key(t): f for t, f in MESSAGE_AVATARS.items()}.get(message_key(text))
        forced = _find_image_file(fixed) if fixed else None
        if forced:
            _RECENT_AVATARS.append((key, forced))
            return forced
    anonymous = key in ("", "anonymous", "unknown")
    base = _base_character_image(name, faction)

    if not anonymous:                       # same person again -> same picture
        for n, i in reversed(_RECENT_AVATARS):
            if n == key:
                return i
    used = {_norm(i) for n, i in _RECENT_AVATARS if anonymous or n != key}
    img = base
    if img is None or _norm(img) in used:
        pool = images_for_faction(faction)
        pool = [q for q in pool if _norm(q) not in used]
        if not pool:                        # faction has too few pictures: use any faction's
            allp = []
            for d in IMAGES_DIR.iterdir() if IMAGES_DIR.exists() else []:
                if d.is_dir() and d.name.lower() != "characters":
                    allp += [str(f) for f in d.iterdir()
                             if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp")]
            pool = [q for q in allp if _norm(q) not in used]
        if pool:
            least = min(_AVATAR_SHOWN.get(_norm(q), 0) for q in pool)
            img = random.choice([q for q in pool if _AVATAR_SHOWN.get(_norm(q), 0) == least])
    if img and (not _RECENT_AVATARS or _RECENT_AVATARS[-1] != (key, img)):
        _RECENT_AVATARS.append((key, img))
        _AVATAR_SHOWN[_norm(img)] = _AVATAR_SHOWN.get(_norm(img), 0) + 1
    return img


def _base_character_image(name, faction):
    """1) character portrait  2) saved faction image  3) default.png"""
    filename = CHARACTER_IMAGES.get((name or "").strip().lower())
    if filename:
        p = CHARACTERS_DIR / filename
        if p.exists():
            return str(p)

    img = assigned_faction_image(name, faction)
    if img:
        return img

    return default_avatar()


# ---------------- sound / fonts / window flags ----------------

def process_running(exe):
    """True/False if a process with this file name exists, None if it couldn't be checked.
    NOTE: tasklist cuts long names ('Stalker2-Win64-Shipping.exe' -> 'Stalker2-Win64-Shipping...'),
    so only the first part of the name is compared."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe}", "/NH"],
            capture_output=True, text=True, timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.lower()
        if "no tasks" in out:
            return False
        return exe.lower()[:18] in out
    except Exception:
        return None


def game_is_running():
    return process_running(GAME_EXE)


# No ping until this moment. With --with-game it stays muted until the game is detected, then 5 minutes.
_quiet = {"until": float("inf") if "--with-game" in sys.argv else time.time() + NO_SOUND_FIRST_MS / 1000}


class Ping:
    """One shared ping. Uses QSoundEffect, and falls back to winsound if that can't play."""

    def __init__(self):
        self.effect = None
        self.player = None
        global SOUND_FILE
        for cand in (BASE_DIR / "sounds" / "ping.wav", BASE_DIR / "ping.wav",
                     BASE_DIR / "sounds" / "ping.mp3", BASE_DIR / "ping.mp3"):
            if cand.exists():
                SOUND_FILE = cand
                break
        if SOUND_FILE.suffix.lower() == ".mp3" and SOUND_FILE.exists():      # mp3 needs the media player
            if _QMP_AVAILABLE:
                self.player = QMediaPlayer()
                self.player.setMedia(QMediaContent(QtCore.QUrl.fromLocalFile(str(SOUND_FILE))))
                self.player.setVolume(max(0, min(100, int(PING_VOLUME))))
            else:
                debug("QMediaPlayer not available - ping.mp3 cannot play")
        elif not SOUND_FILE.exists():
            debug(f"WARNING: ping sound not found at {SOUND_FILE}")
        elif _QSE_AVAILABLE:
            try:
                self.effect = QSoundEffect()
                self.effect.setSource(QtCore.QUrl.fromLocalFile(str(SOUND_FILE)))
                self.effect.setVolume(max(0.0, min(1.0, PING_VOLUME / 100.0)))
            except Exception as e:
                debug(f"QSoundEffect failed: {e}")
                self.effect = None
        else:
            debug("QtMultimedia not available - will try winsound")

    def play(self):
        if time.time() < _quiet["until"]:
            debug("(ping muted: first minutes after the game started)")
            return
        debug("ping")
        if self.player is not None:
            self.player.setPosition(0)
            self.player.play()
            return
        if self.effect is not None:
            try:
                if self.effect.status() != QSoundEffect.Error:
                    self.effect.play()
                    return
            except Exception:
                pass
        # fallback (Windows only)
        try:
            import winsound
            if SOUND_FILE.exists():
                winsound.PlaySound(str(SOUND_FILE), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass


_ping = None


def make_sound():
    global _ping
    if _ping is None:
        _ping = Ping()
    return _ping


_font_cache = {}


def safe_load_font(path, size, fallback="Segoe UI"):
    key = (str(path), size)
    if key in _font_cache:
        return _font_cache[key]

    family = fallback
    if path.exists():
        try:
            fid = QtGui.QFontDatabase.addApplicationFont(str(path))
            families = QtGui.QFontDatabase.applicationFontFamilies(fid)
            if families:
                family = families[0]
        except Exception as e:
            debug(f"font load error {path}: {e}")

    font = QtGui.QFont(family)
    if size > 0:                       # a size <= 0 (like -200) keeps the default size
        font.setPointSize(size)
    _font_cache[key] = font
    return font


class _CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("flags", ctypes.c_uint32),
                ("hCursor", ctypes.c_void_p), ("x", ctypes.c_long), ("y", ctypes.c_long)]


def cursor_visible():
    """True if a mouse cursor is currently shown (None if it can't be checked)."""
    try:
        ci = _CURSORINFO()
        ci.cbSize = ctypes.sizeof(_CURSORINFO)
        if not ctypes.windll.user32.GetCursorInfo(ctypes.byref(ci)):
            return None
        return bool(ci.flags & 1) and bool(ci.hCursor)     # CURSOR_SHOWING and a real cursor image
    except Exception:
        return None


def foreground_exe():
    """File name of the program that owns the active window, lower case ('' if unknown)."""
    try:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        pid = ctypes.c_uint32()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = kernel32.OpenProcess(0x1000, False, pid.value)      # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(520)
            size = ctypes.c_uint32(520)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        pass
    return ""


def make_click_through(widget):
    try:
        hwnd = int(widget.winId())
        ex = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex | 0x80000 | 0x20)
    except Exception:
        pass


OVERLAY_FLAGS = (QtCore.Qt.FramelessWindowHint
                 | QtCore.Qt.WindowStaysOnTopHint
                 | QtCore.Qt.Tool
                 | QtCore.Qt.WindowDoesNotAcceptFocus)


def make_placeholder_display(w=1100, h=420):
    pix = QtGui.QPixmap(w, h)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setBrush(QtGui.QColor(15, 20, 15, 235))
    p.setPen(QtGui.QPen(QtGui.QColor("#5f7a5f"), 4))
    p.drawRoundedRect(2, 2, w - 4, h - 4, 18, 18)
    p.end()
    return pix


# ============================================================
# DISPLAY WINDOW (the image that slides down)
# ============================================================

class DisplayWindow(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowFlags(OVERLAY_FLAGS)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

        pix = QtGui.QPixmap(str(DISPLAY_IMAGE)) if DISPLAY_IMAGE.exists() else QtGui.QPixmap()
        if pix.isNull():
            debug("images/display.png not found - using a placeholder")
            pix = make_placeholder_display()
        if DISPLAY_SCALE != 1.0:
            pix = pix.scaled(int(pix.width() * DISPLAY_SCALE),
                             int(pix.height() * DISPLAY_SCALE),
                             QtCore.Qt.KeepAspectRatio,
                             QtCore.Qt.SmoothTransformation)

        label = QtWidgets.QLabel(self)
        label.setPixmap(pix)
        label.setGeometry(0, 0, pix.width(), pix.height())
        label.setStyleSheet("background: transparent;")
        self.setFixedSize(pix.size())

        make_click_through(self)

        # layer above the text that follows the monitor (blood splatter hides the letters)
        self.blood = None
        if BLOOD_ON_TOP:
            try:
                bp = make_blood_pixmap(pix)
                if bp is not None:
                    self.blood = BloodWindow(bp)
                    self.blood_timer = QtCore.QTimer(self)
                    self.blood_timer.timeout.connect(self._blood_raise)
                    self.blood_timer.start(400)
            except Exception as e:
                debug(f"blood layer failed: {e}")
                self.blood = None

    def _blood_raise(self):
        if self.blood is not None and self.isVisible():
            self.blood.move(self.pos())
            if not self.blood.isVisible():
                self.blood.show()
            self.blood.raise_()

    def moveEvent(self, e):
        super().moveEvent(e)
        if getattr(self, "blood", None) is not None:
            self.blood.move(self.pos())

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "blood", None) is not None:
            self.blood.move(self.pos())
            self.blood.show()
            self.blood.raise_()

    def hideEvent(self, e):
        super().hideEvent(e)
        if getattr(self, "blood", None) is not None:
            self.blood.hide()


class BloodWindow(QtWidgets.QWidget):
    """Transparent click-through window with only the blood/dirt pixels, kept above the text."""

    def __init__(self, pix):
        super().__init__()
        self.setWindowFlags(OVERLAY_FLAGS)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        lab = QtWidgets.QLabel(self)
        lab.setPixmap(pix)
        lab.setGeometry(0, 0, pix.width(), pix.height())
        lab.setStyleSheet("background: transparent;")
        self.setFixedSize(pix.size())
        make_click_through(self)


def make_blood_pixmap(display_pix):
    """images/blood.png if present, else (BLOOD_AUTO) the red pixels of the monitor image."""
    if BLOOD_POLYGONS:
        src = QtGui.QPixmap(str(DISPLAY_IMAGE)) if DISPLAY_IMAGE.exists() else QtGui.QPixmap()
        ow = src.width() if not src.isNull() else display_pix.width()
        k = display_pix.width() / float(ow or 1)
        out = QtGui.QPixmap(display_pix.size())
        out.fill(QtCore.Qt.transparent)
        path = QtGui.QPainterPath()
        for poly in BLOOD_POLYGONS:
            if len(poly) >= 3:
                pg = QtGui.QPolygonF([QtCore.QPointF(x * k, y * k) for x, y in poly])
                sub = QtGui.QPainterPath()
                sub.addPolygon(pg)
                sub.closeSubpath()
                path = path.united(sub)
        pt = QtGui.QPainter(out)
        pt.setRenderHint(QtGui.QPainter.Antialiasing)
        pt.setClipPath(path)
        pt.drawPixmap(0, 0, display_pix)
        pt.end()
        return out
    if BLOOD_IMAGE.exists():
        bp = QtGui.QPixmap(str(BLOOD_IMAGE))
        if not bp.isNull():
            if bp.size() != display_pix.size():
                bp = bp.scaled(display_pix.size(), QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)
            return bp
    if not BLOOD_AUTO:
        return None
    img = display_pix.toImage().convertToFormat(QtGui.QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    ptr = img.bits()
    ptr.setsize(img.byteCount())
    buf = bytearray(ptr)                      # B, G, R, A per pixel
    try:
        import numpy as np
        a = np.frombuffer(buf, dtype=np.uint8).reshape(-1, 4).astype(np.int16)
        b, g, r, al = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
        mask = (r >= BLOOD_MIN_RED) & (r - g >= BLOOD_RED_OVER) & (r - b >= BLOOD_RED_OVER) & (al > 0)
        out = np.frombuffer(buf, dtype=np.uint8).reshape(-1, 4).copy()
        out[~mask] = 0
        buf = bytearray(out.tobytes())
    except ImportError:
        for i in range(0, len(buf), 4):
            bl, gr, re = buf[i], buf[i + 1], buf[i + 2]
            if not (re >= BLOOD_MIN_RED and re - gr >= BLOOD_RED_OVER and re - bl >= BLOOD_RED_OVER and buf[i + 3] > 0):
                buf[i] = buf[i + 1] = buf[i + 2] = buf[i + 3] = 0
    res = QtGui.QImage(bytes(buf), w, h, w * 4, QtGui.QImage.Format_ARGB32).copy()
    debug("blood layer made automatically from the red pixels of display.png")
    return QtGui.QPixmap.fromImage(res)


# ============================================================
# ONE MESSAGE WINDOW
# ============================================================

class CrtGlowEffect(QtWidgets.QGraphicsEffect):
    """CRT look for a text label: a soft glow around the letters plus a slight softness."""

    def __init__(self, color, strength=1.0, radius=6, softness=1.0, parent=None):
        super().__init__(parent)
        self._color = QtGui.QColor(color)
        self._strength = float(strength)
        self._radius = max(1, int(radius))
        self._pad = max(2, int(radius * 2))
        self._soft = float(softness)

    def boundingRectFor(self, rect):
        return rect.adjusted(-self._pad, -self._pad, self._pad, self._pad)

    def draw(self, painter):
        try:
            pix, offset = self.sourcePixmap(QtCore.Qt.LogicalCoordinates,
                                            QtWidgets.QGraphicsEffect.PadToEffectBoundingRect)
            if pix.isNull():
                return
            w, h = pix.width(), pix.height()
            smooth = QtCore.Qt.SmoothTransformation
            painter.save()
            painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
            if self._strength > 0:
                tint = QtGui.QPixmap(pix)
                tp = QtGui.QPainter(tint)
                tp.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
                tp.fillRect(tint.rect(), self._color)
                tp.end()
                kw = max(3, int(self._radius * 0.9))               # radius sets how wide the glow spreads
                reps = max(1, int(self._strength + 0.999))        # strength > 1 stacks the glow
                for k, op in ((kw, 0.9), (max(2, kw // 2), 0.65)):
                    small = tint.scaled(max(1, w // k), max(1, h // k), QtCore.Qt.IgnoreAspectRatio, smooth)
                    glow = small.scaled(w, h, QtCore.Qt.IgnoreAspectRatio, smooth)
                    painter.setOpacity(min(1.0, op * self._strength / reps))
                    for _ in range(reps):
                        painter.drawPixmap(offset, glow)
            crisp = 1.0
            if self._soft > 0:                                    # slight blur of the letters themselves
                f = 1.0 / (1.0 + 0.5 * self._soft)
                small = pix.scaled(max(1, int(w * f)), max(1, int(h * f)), QtCore.Qt.IgnoreAspectRatio, smooth)
                soft = small.scaled(w, h, QtCore.Qt.IgnoreAspectRatio, smooth)
                painter.setOpacity(0.75)
                painter.drawPixmap(offset, soft)
                crisp = 1.0 - min(0.5, 0.3 * self._soft)
            painter.setOpacity(crisp)
            painter.drawPixmap(offset, pix)
            painter.restore()
        except Exception:
            self.drawSource(painter)


class ScanLines(QtWidgets.QWidget):
    """Transparent overlay: dark horizontal lines plus a bright band at `band` (0..1 down the window)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.band = 0.0
        self.hide()

    def paintEvent(self, _event):
        p = QtGui.QPainter(self)
        h, w = self.height(), self.width()
        p.setPen(QtGui.QColor(0, 0, 0, 90))
        for y in range(0, h, 3):
            p.drawLine(0, y, w, y)
        y0 = int(self.band * h)
        p.fillRect(0, y0, w, max(6, h // 10), QtGui.QColor(255, 255, 255, 45))
        p.end()


class SingleMessage(QtWidgets.QWidget):

    def __init__(self, profile):
        super().__init__()
        self.profile = profile

        self.setWindowFlags(OVERLAY_FLAGS)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

        self.main_layout = QtWidgets.QHBoxLayout(self)
        self.main_layout.setContentsMargins(MSG_PAD, MSG_PAD, MSG_PAD, MSG_PAD)
        self.main_layout.setSpacing(12)

        # avatar
        self.img_label = QtWidgets.QLabel()
        self.img_label.setFixedWidth(profile["avatar"])
        self.img_label.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignHCenter)
        self.img_label.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum)
        self.main_layout.addWidget(self.img_label, 0)
        # the portrait itself is drawn by a separate label (not in the layout) so it can be moved
        # on its own; img_label above only reserves the space for it
        self.avatar_label = QtWidgets.QLabel(self)
        self.avatar_label.setStyleSheet("background: transparent;")
        self.avatar_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.avatar_label.hide()
        key = next((k for k, v in PROFILES.items() if v is profile), None)
        mx, my = AVATAR_MOVE_MM.get(key, (0.0, 0.0))
        self._avatar_dx = int((mx + profile.get("avatar_dx_mm", 0)) * 96 / 25.4)
        self._avatar_dy = int((my + profile.get("avatar_dy_mm", 0)) * 96 / 25.4)
        tx, ty = TEXT_MOVE_MM.get(key, (0.0, 0.0))
        # the whole window is shifted by the text offset; the portrait is placed backwards by the
        # same amount, so on screen only the text has moved
        self._text_shift = QtCore.QPoint(int(tx * 96 / 25.4), int(ty * 96 / 25.4))
        self._content_h = 0

        # text area
        self.text_layout = QtWidgets.QVBoxLayout()
        self.text_layout.setContentsMargins(0, 0, 0, 0)
        self.text_layout.setSpacing(8)
        self.main_layout.addLayout(self.text_layout, 1)

        self.name_row = QtWidgets.QHBoxLayout()

        self.name_label = QtWidgets.QLabel()
        self.name_label.setFont(safe_load_font(FONTS_DIR / "StalkerName.ttf", profile["name"]))
        self.name_label.setStyleSheet(f"color: {NAME_COLOR}; background: transparent;")

        self.faction_label = QtWidgets.QLabel()
        self.faction_label.setFont(safe_load_font(FONTS_DIR / "StalkerFaction.ttf", profile["faction"]))
        self.faction_label.setStyleSheet(f"color: {NAME_COLOR}; background: transparent;")

        self.name_row.addWidget(self.name_label)
        self.name_row.addWidget(self.faction_label)
        self.name_row.addStretch()
        self.text_layout.addLayout(self.name_row)

        self.msg_label = QtWidgets.QLabel()
        self.msg_label.setFont(safe_load_font(FONTS_DIR / "StalkerMessage.ttf", profile["font"]))
        self.msg_label.setStyleSheet(f"color: {MESSAGE_COLOR}; background: transparent;")
        self.msg_label.setWordWrap(True)
        self.msg_label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        self.msg_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.text_layout.addWidget(self.msg_label)

        self.upload_label = QtWidgets.QLabel(self)          # child of the window, NOT in the layout: moving it never moves other text
        self.upload_label.setFont(safe_load_font(FONTS_DIR / "StalkerMessage.ttf", max(profile["font"] - 2, 6)))
        self.upload_label.setStyleSheet(f"color: {GIF_UPLOAD_COLOR}; background: transparent;")
        self.upload_label.hide()
        self.upload_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.upload_timer = QtCore.QTimer(self)
        self.upload_timer.timeout.connect(self._upload_tick)
        self._upload_n = 3

        # CRT look: glow + slight softness, in the colour of each label
        if TEXT_GLOW_STRENGTH > 0 or TEXT_BLUR_RADIUS > 0:
            for lbl, col in ((self.name_label, NAME_COLOR), (self.faction_label, NAME_COLOR),
                             (self.msg_label, MESSAGE_COLOR), (self.upload_label, GIF_UPLOAD_COLOR)):
                up = lbl is self.upload_label
                lbl.setGraphicsEffect(CrtGlowEffect((GIF_UPLOAD_GLOW_COLOR if up else TEXT_GLOW_COLOR) or col,
                                                    GIF_UPLOAD_GLOW_STRENGTH if up else TEXT_GLOW_STRENGTH,
                                                    GIF_UPLOAD_GLOW_RADIUS if up else TEXT_GLOW_RADIUS,
                                                    TEXT_BLUR_RADIUS, lbl))

        self.img_opacity_effect = QtWidgets.QGraphicsOpacityEffect(self.avatar_label)
        self.avatar_label.setGraphicsEffect(self.img_opacity_effect)

        # state
        self.stage = None
        self.has_content = False
        self.on_state_change = None
        self._on_typed = None
        self._cleared_cbs = []
        self._last_glitch_anim = None
        self.typing = False                 # True while this window shows the typing dots
        self._dots_n = 1
        self.dots_timer = QtCore.QTimer(self)
        self.dots_timer.timeout.connect(self._dots_tick)

        self._glitch_plan = []
        self._glitch_frames_left = 0
        self.glitch_timer = QtCore.QTimer(self)
        self.glitch_timer.setSingleShot(True)
        self.glitch_timer.timeout.connect(self._glitch_start)
        self.glitch_frame_timer = QtCore.QTimer(self)
        self.glitch_frame_timer.timeout.connect(self._glitch_frame)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._on_tick)

        self.name_full = ""
        self.faction_full = ""
        self.msg_full = ""
        self.name_i = self.faction_i = self.msg_i = 0

        self.sound = make_sound()

        # logical position (where it sits when the monitor is down) + slide offset
        self._base_pos = QtCore.QPoint(0, 0)
        self._offset = QtCore.QPoint(0, 0)
        self._jitter = QtCore.QPoint(0, 0)

        # glitch overlays: two tinted copies of the portrait, and scan lines
        self.ghosts = []
        for _ in range(2):
            g = QtWidgets.QLabel(self)
            g.setStyleSheet("background: transparent;")
            g.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            g.hide()
            self.ghosts.append(g)
        self.scan = ScanLines(self)

        self.setFixedWidth(PANEL_WIDTH + 2 * MSG_PAD)
        make_click_through(self)

    # ------------------------------------------------------------
    # POSITION = base position + monitor slide offset
    # ------------------------------------------------------------

    def _place(self):
        self.move(self._base_pos + self._offset + self._jitter + self._text_shift
                  - QtCore.QPoint(MSG_PAD, MSG_PAD))

    def get_base_pos(self):
        return self._base_pos

    def set_base_pos(self, p):
        self._base_pos = QtCore.QPoint(p)
        self._place()

    def set_offset(self, off):
        self._offset = QtCore.QPoint(off)
        self._place()

    basePos = QtCore.pyqtProperty(QtCore.QPoint, fget=get_base_pos, fset=set_base_pos)

    # ------------------------------------------------------------

    def _notify(self):
        if self.on_state_change:
            self.on_state_change()

    # ------------------------------------------------------------
    # SHOW A MESSAGE (type it in; it then stays until clear_out)
    # ------------------------------------------------------------

    def show_message(self, name, message, image_path, faction, on_typed=None,
                     play_sound=True, instant=False):
        self._stop_dots()
        self.timer.stop()
        if self._last_glitch_anim is not None:
            self._last_glitch_anim.stop()
        self._on_typed = on_typed
        self._cleared_cbs = []
        self.has_content = True

        self.name_full = name or ""
        self.faction_full = f"({faction.capitalize()})" if (faction and SHOW_FACTION) else ""
        self.msg_full = wrap_message(message or "", self.profile["words"])
        self.name_i = self.faction_i = self.msg_i = 0

        # avatar
        max_h = self.profile["avatar"]
        pix_path = image_path if (image_path and os.path.exists(image_path)) else (
            default_avatar())
        self.img_label.clear()
        self.avatar_label.clear()
        self.img_label.setFixedWidth(max_h)
        if pix_path:
            pix = QtGui.QPixmap(pix_path)
            if not pix.isNull():
                if pix.height() > max_h or (AVATAR_SCALE_UP and pix.height() < max_h):
                    pix = pix.scaledToHeight(max_h, QtCore.Qt.SmoothTransformation)
                self.avatar_label.setPixmap(pix)          # slot width stays fixed (see TEXT_MOVE_MM note)

        # measure the finished message so the window height is stable while typing
        self.name_label.setText(self.name_full)
        self.faction_label.setText(self.faction_full)
        self.msg_label.setText(self.msg_full)
        self.main_layout.activate()
        lay = self.main_layout
        h = lay.totalHeightForWidth(PANEL_WIDTH + 2 * MSG_PAD) if lay.hasHeightForWidth() else 0
        h = max(h, lay.sizeHint().height(), max_h + 2 * MSG_PAD)
        self.setFixedHeight(h)
        self._content_h = h
        self._place_avatar()

        if instant:
            # monitor is up: place the finished message immediately (no typing)
            self.name_i = len(self.name_full)
            self.faction_i = len(self.faction_full)
            self.msg_i = len(self.msg_full)
            self.img_opacity_effect.setOpacity(1.0)
            self._on_typed = None
            self.stage = "hold"
            self._schedule_glitches()
            if play_sound and self.sound:
                try:
                    self.sound.play()
                except Exception:
                    pass
            self._notify()
            if on_typed:
                QtCore.QTimer.singleShot(0, on_typed)
            return

        self.name_label.setText("")
        self.faction_label.setText("")
        self.msg_label.setText("")
        self.img_opacity_effect.setOpacity(1.0)

        if play_sound and self.sound:
            try:
                self.sound.play()
            except Exception:
                pass

        self.stage = "name_in"
        self.timer.start(TYPING_INTERVAL_MS)
        self._notify()

    # ------------------------------------------------------------
    # ERASE (reverse typewriter -> glitch fade -> on_done)
    # ------------------------------------------------------------

    def _place_avatar(self):
        """Put the portrait where the layout reserved space for it, plus its own mm offset."""
        pm = self.avatar_label.pixmap()
        if pm is None or pm.isNull():
            self.avatar_label.hide()
            return
        ch = self._content_h or self.height()
        x = MSG_PAD + self._avatar_dx - self._text_shift.x()
        y = MSG_PAD + (ch - 2 * MSG_PAD - pm.height()) // 2 + self._avatar_dy - self._text_shift.y()
        self.avatar_label.setGeometry(x, y, pm.width(), pm.height())
        self.avatar_label.show()
        self.avatar_label.raise_()

    def show_upload_text(self, text):
        """Small text under the message (e.g. 'gif uploading...'). The portrait stays where it is."""
        self._upload_n = 1
        self.upload_label.setText(GIF_UPLOAD_BASE_TEXT + ".")
        self.upload_label.adjustSize()
        self._place_upload()
        self.upload_label.show()
        self.upload_label.raise_()
        self.upload_timer.start(DOTS_INTERVAL_MS)

    def _place_upload(self):
        """Absolute position: from the top of the message text + its own mm offset (independent of the message length)."""
        self.main_layout.activate()
        ml = self.msg_label
        dx = int(GIF_UPLOAD_MOVE_MM[0] * 96 / 25.4)
        dy = int(GIF_UPLOAD_MOVE_MM[1] * 96 / 25.4)
        self.upload_label.move(ml.x() + dx, ml.y() + dy)

    def show_typing(self, name, faction, image_path):
        """Show portrait + name with animated typing dots (someone is writing a reply)."""
        self.show_message(name, "• • •", image_path, faction,
                          on_typed=None, play_sound=False, instant=True)
        self.typing = True
        self._dots_n = 1
        self.msg_label.setText("•")
        self.dots_timer.start(DOTS_INTERVAL_MS)

    def _dots_tick(self):
        if not self.typing:
            self.dots_timer.stop()
            return
        self._dots_n = self._dots_n % 3 + 1
        self.msg_label.setText(" ".join(["•"] * self._dots_n))

    def _upload_tick(self):
        self._upload_n = self._upload_n % 3 + 1
        self.upload_label.setText(GIF_UPLOAD_BASE_TEXT + "." * self._upload_n)
        self.upload_label.adjustSize()

    def _stop_dots(self):
        self.upload_timer.stop()
        self.upload_label.hide()
        self._cancel_glitch()               # called whenever the content changes or is removed
        self.dots_timer.stop()
        self.typing = False

    def clear_out(self, on_done=None, instant=False):
        self._stop_dots()
        if on_done:
            self._cleared_cbs.append(on_done)

        if not self.has_content:
            self._run_cleared_callbacks()
            return

        if instant:
            self.timer.stop()
            if self._last_glitch_anim is not None:
                self._last_glitch_anim.stop()
            self.stage = None
            self._on_typed = None
            self.name_label.setText("")
            self.faction_label.setText("")
            self.msg_label.setText("")
            self.img_opacity_effect.setOpacity(1.0)
            self._finish_clear()
            return

        if self.stage in ("name_out", "faction_out", "msg_out", "glitch"):
            return                                    # already erasing

        self._on_typed = None
        self.stage = "name_out"
        self.timer.start(TYPING_INTERVAL_MS)

    def discard(self):
        """Throw the content away at once (no typing/glitch)."""
        self._stop_dots()
        self.timer.stop()
        if self._last_glitch_anim is not None:
            self._last_glitch_anim.stop()
        self._on_typed = None
        self.name_label.setText("")
        self.faction_label.setText("")
        self.msg_label.setText("")
        self.img_opacity_effect.setOpacity(1.0)
        self._finish_clear()

    def bounce_away(self, up_px, ms):
        """Old message: bounces up and away while fading out, then it is gone."""
        self._stop_dots()
        self.timer.stop()
        if self._last_glitch_anim is not None:
            self._last_glitch_anim.stop()
        self._on_typed = None
        self._away_start = QtCore.QPoint(self._base_pos)

        move = QtCore.QPropertyAnimation(self, b"basePos")
        move.setStartValue(self._away_start)
        move.setEndValue(self._away_start + QtCore.QPoint(0, -int(up_px)))
        move.setDuration(ms)
        move.setEasingCurve(QtCore.QEasingCurve.OutBounce)

        fade = QtCore.QPropertyAnimation(self, b"windowOpacity")
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setDuration(ms)
        fade.setEasingCurve(QtCore.QEasingCurve.InQuad)

        group = QtCore.QParallelAnimationGroup(self)
        group.addAnimation(move)
        group.addAnimation(fade)
        group.finished.connect(self._away_done)
        self._away_group = group
        group.start()

    def _away_done(self):
        self._abort_away()

    def _abort_away(self):
        """Finish a running bounce-away at once and put the window back, empty."""
        g = getattr(self, "_away_group", None)
        if g is None:
            return
        self._away_group = None
        try:
            g.finished.disconnect()
        except Exception:
            pass
        g.stop()
        self.setWindowOpacity(1.0)          # restore while still visible (a hidden window may keep alpha 0)
        self.discard()
        self.set_base_pos(self._away_start)
        self.setWindowOpacity(1.0)

    def reset_for_show(self, home):
        """Make sure a window that bounced away earlier is back at its home spot, opaque, and idle."""
        g = getattr(self, "_away_group", None)
        if g is not None:
            self._abort_away()
        self.setWindowOpacity(1.0)
        self.set_base_pos(home)

    # ------------------------------------------------------------
    # RANDOM RADIO GLITCHES while the message sits on the monitor
    # ------------------------------------------------------------

    def glitch_now(self, frames):
        """Called by the controller for the all-at-once glitch."""
        if self.stage != "hold" or self.typing or not self.has_content:
            return False
        self._glitch_frames_left = frames
        self.glitch_frame_timer.start(GLITCH_FRAME_MS)
        return True

    def _schedule_glitches(self):
        self._cancel_glitch()
        if GLITCH_GLOBAL or not GLITCH_ENABLED or GLITCH_MAX_PER_MESSAGE <= 0:
            return
        n = random.randint(0, GLITCH_MAX_PER_MESSAGE)
        times = sorted(random.uniform(GLITCH_FIRST_AFTER_MS, GLITCH_WINDOW_MS) for _ in range(n))
        plan, last = [], 0.0
        for t in times:
            if not plan or t - last >= GLITCH_MIN_GAP_MS:
                plan.append(t - last)
                last = t
        self._glitch_plan = plan
        self._glitch_next()

    def _glitch_next(self):
        if self._glitch_plan:
            self.glitch_timer.start(int(self._glitch_plan.pop(0)))

    def _cancel_glitch(self):
        self._glitch_plan = []
        self.glitch_timer.stop()
        was_flickering = self.glitch_frame_timer.isActive()
        self.glitch_frame_timer.stop()
        if was_flickering:
            self._glitch_clear_fx()
            if self.stage == "hold" and not self.typing:
                self._glitch_restore()

    def _glitch_clear_fx(self):
        """Switch off every visual glitch effect (jitter, colours, ghosts, scan lines, flicker)."""
        self.img_opacity_effect.setOpacity(1.0)
        self.name_label.setStyleSheet(f"color: {NAME_COLOR}; background: transparent;")
        self.msg_label.setStyleSheet(f"color: {MESSAGE_COLOR}; background: transparent;")
        for g in self.ghosts:
            g.hide()
        self.scan.hide()
        if not self._jitter.isNull():
            self._jitter = QtCore.QPoint(0, 0)
            self._place()

    def _tinted_pixmap(self, color):
        src = self.avatar_label.pixmap()
        if src is None or src.isNull():
            return None
        out = QtGui.QPixmap(src)
        p = QtGui.QPainter(out)
        p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
        p.fillRect(out.rect(), QtGui.QColor(*color))
        p.end()
        return out

    def _glitch_fx_frame(self):
        if GLITCH_JITTER:
            j = GLITCH_JITTER_PX
            self._jitter = QtCore.QPoint(random.randint(-j, j), 0)
            self._place()
        if GLITCH_COLOR_FLASH and random.random() < 0.6:
            col = random.choice(GLITCH_COLORS)
            self.name_label.setStyleSheet(f"color: {col}; background: transparent;")
            self.msg_label.setStyleSheet(f"color: {col}; background: transparent;")
        else:
            self.name_label.setStyleSheet(f"color: {NAME_COLOR}; background: transparent;")
            self.msg_label.setStyleSheet(f"color: {MESSAGE_COLOR}; background: transparent;")
        if GLITCH_DOUBLE_IMAGE and random.random() < 0.75:
            geo = self.avatar_label.geometry()
            for g, color, sign in zip(self.ghosts, ((255, 32, 32, 170), (32, 96, 255, 170)), (-1, 1)):
                pm = self._tinted_pixmap(color)
                if pm is None:
                    continue
                g.setPixmap(pm)
                dx = sign * random.randint(2, GLITCH_GHOST_PX)
                g.setGeometry(geo.translated(dx, random.randint(-1, 1)))
                g.show()
                g.raise_()
        else:
            for g in self.ghosts:
                g.hide()
        if GLITCH_SCANLINES:
            self.scan.setGeometry(self.rect().adjusted(MSG_PAD, MSG_PAD, -MSG_PAD, -MSG_PAD))
            self.scan.band = random.random()
            self.scan.show()
            self.scan.raise_()
            self.scan.update()

    def _glitch_restore(self):
        self._glitch_clear_fx()
        self.msg_label.setText(self.msg_full)
        self.name_label.setText(self.name_full)
        self.faction_label.setText(self.faction_full)
        self.img_opacity_effect.setOpacity(1.0)

    def _glitch_start(self):
        if self.stage != "hold" or self.typing or not self.has_content:
            return
        self._glitch_frames_left = random.randint(*GLITCH_FRAMES)
        self.glitch_frame_timer.start(GLITCH_FRAME_MS)

    def _glitch_frame(self):
        if self.stage != "hold" or self.typing or not self.has_content:
            self.glitch_frame_timer.stop()
            return
        if self._glitch_frames_left > 0:
            self._glitch_frames_left -= 1
            frac = random.uniform(*GLITCH_CHAR_FRAC)
            self.msg_label.setText(scramble_text(self.msg_full, frac))
            if GLITCH_NAME:
                self.name_label.setText(scramble_text(self.name_full, max(frac, 0.2)))
                self.faction_label.setText(scramble_text(self.faction_full, max(frac, 0.2)))
            if GLITCH_PICTURE:
                self.img_opacity_effect.setOpacity(random.choice((0.0, 0.25, 0.5, 0.75, 1.0)))
            self._glitch_fx_frame()
        else:
            self.glitch_frame_timer.stop()
            self._glitch_restore()
            self._glitch_next()

    def _typed_done(self):
        self.timer.stop()
        self.stage = "hold"
        self._schedule_glitches()
        cb, self._on_typed = self._on_typed, None
        if cb:
            cb()

    def _run_cleared_callbacks(self):
        cbs, self._cleared_cbs = self._cleared_cbs, []
        for cb in cbs:
            try:
                cb()
            except Exception:
                debug("callback error " + traceback.format_exc())

    # ------------------------------------------------------------
    # TYPEWRITER
    # ------------------------------------------------------------

    def _on_tick(self):
        try:
            s = self.stage

            if s == "name_in":
                if self.name_i < len(self.name_full):
                    self.name_i += 1
                    self.name_label.setText(self.name_full[:self.name_i])
                else:
                    self.stage = "faction_in"
                    self.faction_i = 0

            elif s == "faction_in":
                if self.faction_i < len(self.faction_full):
                    self.faction_i += 1
                    self.faction_label.setText(self.faction_full[:self.faction_i])
                else:
                    self.stage = "msg_in"
                    self.msg_i = 0

            elif s == "msg_in":
                if self.msg_i < len(self.msg_full):
                    self.msg_i += 1
                    self.msg_label.setText(self.msg_full[:self.msg_i])
                else:
                    self._typed_done()

            elif s == "name_out":
                if self.name_i > 0:
                    self.name_i -= 1
                    self.name_label.setText(self.name_full[:self.name_i])
                else:
                    self.stage = "faction_out"

            elif s == "faction_out":
                if self.faction_i > 0:
                    self.faction_i -= 1
                    self.faction_label.setText(self.faction_full[:self.faction_i])
                else:
                    self.stage = "msg_out"

            elif s == "msg_out":
                if self.msg_i > 0:
                    self.msg_i -= 1
                    self.msg_label.setText(self.msg_full[:self.msg_i])
                else:
                    self.timer.stop()
                    self.stage = "glitch"
                    self._start_glitch_fade()

            else:
                self.timer.stop()

        except Exception:
            debug("typing tick error " + traceback.format_exc())
            self.timer.stop()

    # ------------------------------------------------------------
    # GLITCH / FADE
    # ------------------------------------------------------------

    def _start_glitch_fade(self):
        anim = QtCore.QPropertyAnimation(self.img_opacity_effect, b"opacity")
        anim.setDuration(1000)
        anim.setStartValue(1.0)
        anim.setKeyValueAt(0.2, 0.0)
        anim.setKeyValueAt(0.5, 1.0)
        anim.setKeyValueAt(0.8, 0.2)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)
        anim.finished.connect(lambda a=anim: self._glitch_done(a))
        anim.start()
        self._last_glitch_anim = anim

    def _glitch_done(self, anim):
        if anim is self._last_glitch_anim and self.stage == "glitch":
            self._finish_clear()

    def _finish_clear(self):
        self.has_content = False
        self.stage = None
        self._notify()
        self._run_cleared_callbacks()


# ============================================================
# USERS CONNECTED LABEL (rides with the monitor)
# ============================================================

class UsersLabel(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowFlags(OVERLAY_FLAGS)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.has_content = True            # visible whenever the monitor is visible
        self.label = QtWidgets.QLabel(self)
        self.label.setFont(safe_load_font(FONTS_DIR / "StalkerMessage.ttf", USERS_FONT_SIZE))
        self.label.setStyleSheet(f"color: {USERS_COLOR}; background: transparent;")
        self._pad = 20                       # room around the text so the glow is not cut off
        self.label.move(self._pad, self._pad)
        if USERS_GLOW_STRENGTH > 0 or USERS_SOFTNESS > 0:
            self.label.setGraphicsEffect(CrtGlowEffect(USERS_GLOW_COLOR or USERS_COLOR, USERS_GLOW_STRENGTH,
                                                       USERS_GLOW_RADIUS, USERS_SOFTNESS, self.label))
        self._base_pos = QtCore.QPoint(0, 0)
        self._offset = QtCore.QPoint(0, 0)
        self.set_count(USERS_MIN)
        make_click_through(self)

    def set_count(self, n):
        self.label.setText(USERS_TEXT.format(n=n))
        self.label.adjustSize()
        self.setFixedSize(self.label.width() + 2 * self._pad, self.label.height() + 2 * self._pad)

    def set_base_pos(self, p):
        self._base_pos = QtCore.QPoint(p)
        self.move(self._base_pos + self._offset - QtCore.QPoint(self._pad, self._pad))

    def set_offset(self, off):
        self._offset = QtCore.QPoint(off)
        self.move(self._base_pos + self._offset - QtCore.QPoint(self._pad, self._pad))


class GlitchSound:
    """glitch.mp3, looped until stop() is called. Volume = GLITCH_SOUND_VOLUME."""

    def __init__(self):
        self.player = None
        self.playing = False
        if not _QMP_AVAILABLE:
            debug("QMediaPlayer not available - no glitch sound")
            return
        for folder in (BASE_DIR / "sounds", BASE_DIR / "sound", GIFS_DIR, BASE_DIR):
            f = folder / GLITCH_SOUND_NAME
            if f.exists():
                self.player = QMediaPlayer()
                self.player.setMedia(QMediaContent(QtCore.QUrl.fromLocalFile(str(f))))
                self.player.setVolume(max(0, min(100, int(GLITCH_SOUND_VOLUME))))
                self.player.mediaStatusChanged.connect(self._status)
                return
        debug(f"{GLITCH_SOUND_NAME} not found (sounds/, vids/ or next to the script) - no glitch sound")

    def _status(self, st):
        if st == QMediaPlayer.EndOfMedia and self.playing:   # shorter than the glitch: loop
            self.player.setPosition(0)
            self.player.play()

    def play(self):
        if self.player is None:
            return
        self.playing = True
        self.player.setPosition(0)
        self.player.play()

    def stop(self):
        self.playing = False
        if self.player is not None:
            self.player.stop()


class GlitchGifWindow(QtWidgets.QWidget):
    """glitch.gif noise that plays behind the text during a glitch. Rides with the monitor."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(OVERLAY_FLAGS)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.has_content = False            # only while a glitch is running
        self.label = QtWidgets.QLabel(self)
        self.label.setScaledContents(True)
        self.label.setStyleSheet("background: transparent;")
        self.movie = None
        self.available = False
        for folder in (GIFS_DIR, IMAGES_DIR, BASE_DIR):
            f = folder / GLITCH_GIF_NAME
            if f.exists():
                self.movie = QtGui.QMovie(str(f))
                self.movie.setCacheMode(QtGui.QMovie.CacheAll)
                if self.movie.isValid():
                    self.label.setMovie(self.movie)
                    self.available = True
                break
        if not self.available:
            debug(f"{GLITCH_GIF_NAME} not found (vids/, images/ or next to the script) - glitches without the noise gif")
        self._base_pos = QtCore.QPoint(0, 0)
        self._offset = QtCore.QPoint(0, 0)
        self.setWindowOpacity(GLITCH_GIF_OPACITY)
        make_click_through(self)

    def set_box(self, base, w, h):
        self.setFixedSize(w, h)
        self.label.setGeometry(0, 0, w, h)
        self._base_pos = QtCore.QPoint(base)
        self.move(self._base_pos + self._offset)

    def set_base_pos(self, p):
        self._base_pos = QtCore.QPoint(p)
        self.move(self._base_pos + self._offset)

    def set_offset(self, off):
        self._offset = QtCore.QPoint(off)
        self.move(self._base_pos + self._offset)

    def play(self):
        if self.movie is not None and self.available:
            self.movie.jumpToFrame(random.randint(0, max(0, self.movie.frameCount() - 1)))
            self.movie.start()

    def stop(self):
        if self.movie is not None:
            self.movie.stop()


class GifDisplayWindow(QtWidgets.QWidget):
    """Animated GIF panel occupying the two-message conversation area."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(OVERLAY_FLAGS)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(GIF_BOX_W, GIF_BOX_H)          # anything outside this box is cropped
        self.label = QtWidgets.QLabel(self)
        self.label.setGeometry(0, 0, GIF_BOX_W, GIF_BOX_H)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setStyleSheet("background: transparent;")
        self.movie = None
        self.on_finished = None
        self.has_content = False
        self._base_pos = QtCore.QPoint(0, 0)
        self._offset = QtCore.QPoint(0, 0)
        make_click_through(self)

    def set_base_pos(self, p):
        self._base_pos = QtCore.QPoint(p)
        self.move(self._base_pos + self._offset)

    def set_offset(self, off):
        self._offset = QtCore.QPoint(off)
        self.move(self._base_pos + self._offset)

    def prepare_gif(self, path):
        self.stop_gif()
        movie = QtGui.QMovie(str(path))
        if not movie.isValid():
            debug(f"GIF could not be opened: {path}")
            movie.deleteLater()
            return False

        movie.setCacheMode(QtGui.QMovie.CacheAll)
        movie.setSpeed(GIF_PLAYBACK_SPEED_PERCENT)
        # PyQt5 QMovie has no setLoopCount(). Detect the first frame wrap
        # ourselves so even infinitely-looping GIFs play only once.
        self._last_frame_number = 0
        movie.frameChanged.connect(self._frame_changed)
        movie.jumpToFrame(0)
        frame = movie.currentPixmap()
        if not frame.isNull():
            # fill the whole box (cover): same size for every GIF, extra is cropped
            target = frame.size().scaled(GIF_BOX_W, GIF_BOX_H, QtCore.Qt.KeepAspectRatioByExpanding)
            movie.setScaledSize(target)
            movie.jumpToFrame(0)
        movie.finished.connect(self._movie_finished)
        self.movie = movie
        self.has_content = False            # stays hidden until the monitor is open (see start_gif)
        self.label.setGeometry(0, 0, GIF_BOX_W, GIF_BOX_H)
        self._render_frame()
        self.label.show()
        return True

    def _render_frame(self):
        """Draw the current GIF frame into the box (cover-fit) and bend it like a curved screen."""
        if self.movie is None:
            return
        frame = self.movie.currentPixmap()
        if frame.isNull():
            return
        W, H = GIF_BOX_W, GIF_BOX_H
        base = QtGui.QPixmap(W, H)
        base.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(base)
        p.drawPixmap((W - frame.width()) // 2, (H - frame.height()) // 2, frame)
        p.end()

        step = max(1, int(GIF_CURVE_STRIP_PX))
        if GIF_CURVE_PERCENT:
            k = GIF_CURVE_PERCENT / 100.0
            out = QtGui.QPixmap(W, H)
            out.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(out)
            p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
            for x in range(0, W, step):
                u = ((x + step / 2.0) / W) * 2.0 - 1.0          # -1 (left) .. 1 (right)
                dh = H * (1.0 - k * u * u)                       # middle full height, edges shorter
                p.drawPixmap(QtCore.QRectF(x, (H - dh) / 2.0, step, dh), base,
                             QtCore.QRectF(x, 0, step, H))
            p.end()
            base = out
        if GIF_CURVE_SIDES_PERCENT:
            k = GIF_CURVE_SIDES_PERCENT / 100.0
            out = QtGui.QPixmap(W, H)
            out.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(out)
            p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
            for y in range(0, H, step):
                v = ((y + step / 2.0) / H) * 2.0 - 1.0
                dw = W * (1.0 - k * v * v)
                p.drawPixmap(QtCore.QRectF((W - dw) / 2.0, y, dw, step), base,
                             QtCore.QRectF(0, y, W, step))
            p.end()
            base = out
        self.label.setPixmap(base)

    def start_gif(self):
        """Start playing; the picture buffers in (blurred + faint, then sharp)."""
        if self.movie is None or not self.movie.isValid():
            return
        self._end_blur()
        if GIF_BLUR_IN and GIF_BLUR_IN_MS > 0:
            self.blur = QtWidgets.QGraphicsBlurEffect(self.label)
            self.blur.setBlurHints(QtWidgets.QGraphicsBlurEffect.PerformanceHint)
            self.blur.setBlurRadius(GIF_BLUR_RADIUS)
            self.label.setGraphicsEffect(self.blur)
            self.setWindowOpacity(GIF_START_OPACITY)

            a1 = QtCore.QPropertyAnimation(self.blur, b"blurRadius")
            a1.setStartValue(float(GIF_BLUR_RADIUS))
            a1.setEndValue(0.0)
            a1.setDuration(GIF_BLUR_IN_MS)
            a1.setEasingCurve(QtCore.QEasingCurve.OutCubic)
            a2 = QtCore.QPropertyAnimation(self, b"windowOpacity")
            a2.setStartValue(float(GIF_START_OPACITY))
            a2.setEndValue(1.0)
            a2.setDuration(GIF_BLUR_IN_MS)
            a2.setEasingCurve(QtCore.QEasingCurve.OutCubic)
            group = QtCore.QParallelAnimationGroup(self)
            group.addAnimation(a1)
            group.addAnimation(a2)
            group.finished.connect(lambda: QtCore.QTimer.singleShot(0, self._end_blur))
            self._blur_group = group
            group.start()
        self.movie.start()

    def _end_blur(self):
        g = getattr(self, "_blur_group", None)
        self._blur_group = None
        if g is not None:
            try:
                g.finished.disconnect()
            except Exception:
                pass
            g.stop()
        if getattr(self, "blur", None) is not None:
            self.label.setGraphicsEffect(None)
            self.blur = None
        self.setWindowOpacity(1.0)

    def exit_gif(self, done):
        """Blur out + fade away (the buffering-in effect backwards), then call done()."""
        if GIF_EXIT_MS <= 0 or not self.has_content or not self.isVisible():
            done()
            return
        self._end_blur()
        self.blur = QtWidgets.QGraphicsBlurEffect(self.label)
        self.blur.setBlurHints(QtWidgets.QGraphicsBlurEffect.PerformanceHint)
        self.blur.setBlurRadius(0.0)
        self.label.setGraphicsEffect(self.blur)
        a1 = QtCore.QPropertyAnimation(self.blur, b"blurRadius")
        a1.setStartValue(0.0)
        a1.setEndValue(float(GIF_BLUR_RADIUS))
        a1.setDuration(GIF_EXIT_MS)
        a1.setEasingCurve(QtCore.QEasingCurve.InCubic)
        a2 = QtCore.QPropertyAnimation(self, b"windowOpacity")
        a2.setStartValue(1.0)
        a2.setEndValue(0.0)
        a2.setDuration(GIF_EXIT_MS)
        a2.setEasingCurve(QtCore.QEasingCurve.InCubic)
        group = QtCore.QParallelAnimationGroup(self)
        group.addAnimation(a1)
        group.addAnimation(a2)
        group.finished.connect(lambda: QtCore.QTimer.singleShot(0, done))
        self._blur_group = group
        group.start()

    def pause(self):
        if self.movie is not None and self.movie.state() == QtGui.QMovie.Running:
            self.movie.setPaused(True)
        g = getattr(self, "_blur_group", None)
        if g is not None and g.state() == QtCore.QAbstractAnimation.Running:
            g.pause()

    def resume(self):
        if self.movie is not None and self.movie.state() == QtGui.QMovie.Paused:
            self.movie.setPaused(False)
        g = getattr(self, "_blur_group", None)
        if g is not None and g.state() == QtCore.QAbstractAnimation.Paused:
            g.resume()

    def stop_gif(self):
        self._end_blur()
        if self.movie is not None:
            self.movie.stop()
            self.movie.deleteLater()
            self.movie = None
        self.label.clear()
        self.has_content = False

    def _frame_changed(self, frame_number):
        self._render_frame()
        # A decreasing frame number means the GIF has looped back to its start.
        if (self.movie is not None and frame_number < self._last_frame_number
                and self._last_frame_number > 0):
            self.movie.stop()
            self._movie_finished()
            return
        self._last_frame_number = frame_number

    def _movie_finished(self):
        callback = self.on_finished
        self.on_finished = None
        if callback:
            callback()


# ============================================================
# CONTROLLER
# ============================================================

class OverlayApp(QtCore.QObject):

    toggle_requested = QtCore.pyqtSignal()
    game_status = QtCore.pyqtSignal(bool)
    quit_now = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()

        # ---------------- windows ----------------
        self.display = DisplayWindow()
        # two random windows: when a new random message arrives, the old one bounces away
        self.random_pool = [SingleMessage(PROFILES["random"]), SingleMessage(PROFILES["random"])]
        self.random_widget = self.random_pool[0]
        self.convo_top = SingleMessage(PROFILES["convo_top"])
        self.convo_bottom = SingleMessage(PROFILES["convo_bottom"])
        self.gif_widget = GifDisplayWindow()
        self.gif_widget.on_finished = self._gif_finished
        self.widgets = self.random_pool + [self.convo_top, self.convo_bottom]
        self.users_label = UsersLabel() if SHOW_USERS_COUNTER else None
        self.glitch_gif = GlitchGifWindow()
        self.glitch_sound = GlitchSound()
        self._glitching = False
        # the glitch noise comes FIRST so every raise_() after it puts the text above it
        self.riders = [self.glitch_gif] + self.widgets + [self.gif_widget] + ([self.users_label] if self.users_label else [])

        for w in self.widgets:
            w.on_state_change = self.sync_visibility

        # ---------------- positions ----------------
        screen = QtWidgets.QApplication.primaryScreen()
        self.screen_w = screen.size().width() if screen else 3840
        self.px_per_cm = 96 / 2.54
        self.raise_px = int(MONITOR_RAISE_RANDOM_CM * self.px_per_cm)
        self.monitor_mode = "random"        # "random" = raised monitor, "convo" = full-down monitor
        self._mode_cb = None

        self.down_pos = self._pos_for(DISPLAY_DX_CM, DISPLAY_DY_CM)
        self.up_pos = QtCore.QPoint(self.down_pos.x(), -self.display.height())
        self.display.move(self.up_pos)

        for w in self.widgets:
            w.set_base_pos(self._pos_for(w.profile["dx_cm"], w.profile["dy_cm"]))
        # the monitor sits `raise_px` higher in random mode; this cancels that out so the random
        # text stays at the SAME SCREEN position as the convo top message (only the monitor moves)
        for rw in self.random_pool:
            rw.set_base_pos(rw.get_base_pos()
                            + QtCore.QPoint(0, self.raise_px - int(RANDOM_TEXT_UP_CM * self.px_per_cm)))
        self.random_bounce_px = int(RANDOM_BOUNCE_UP_CM * self.px_per_cm)
        self.random_home = QtCore.QPoint(self.random_pool[0].get_base_pos())   # where random messages live

        # users counter: placed on the monitor image (in full-down coordinates, rides with the monitor)
        if self.users_label:
            self.users_label.set_base_pos(QtCore.QPoint(
                self.down_pos.x() + int(USERS_X_FRAC * self.display.width()
                                        + USERS_NUDGE_X_CM * self.px_per_cm),
                self.down_pos.y() + int(USERS_Y_FRAC * self.display.height()
                                        + USERS_NUDGE_Y_CM * self.px_per_cm)))
            self.users_n = random.randint(USERS_MIN, USERS_MAX)
            self.users_label.set_count(self.users_n)
            self.users_timer = QtCore.QTimer(self)
            self.users_timer.timeout.connect(self._users_tick)
            self.users_timer.start(USERS_UPDATE_MS)

        self.convo_top_pos = self._pos_for(PROFILES["convo_top"]["dx_cm"],
                                           PROFILES["convo_top"]["dy_cm"])
        self.convo_bottom_pos = self._pos_for(PROFILES["convo_bottom"]["dx_cm"],
                                              PROFILES["convo_bottom"]["dy_cm"])
        # Center the GIF in the space normally occupied by both conversation messages.
        # The box keeps the SAME CENTRE as before (the old 1000 x 350 area), so changing
        # GIF_BOX_W / GIF_BOX_H makes it grow or shrink around that centre.
        cx = self.convo_top_pos.x() + PANEL_WIDTH // 2
        cy = self.convo_top_pos.y() + 2 + GIF_AREA_HEIGHT // 2
        self.gif_widget.set_base_pos(QtCore.QPoint(
            cx - GIF_BOX_W // 2 + int(GIF_DX_MM * self.px_per_cm / 10),
            cy - GIF_BOX_H // 2 + int(GIF_DY_MM * self.px_per_cm / 10)))
        self._bounce_anim = None

        # ---------------- slide ----------------
        self.display_down = False
        self.slide_anim = QtCore.QPropertyAnimation(self.display, b"pos", self)
        self.slide_anim.setEasingCurve(QtCore.QEasingCurve.InOutCubic)
        self.slide_anim.valueChanged.connect(self._apply_offset)   # messages ride with the monitor
        self.slide_anim.finished.connect(self._on_slide_finished)
        self._apply_offset(self.up_pos)
        self.toggle_requested.connect(self.toggle_display)

        # ---------------- message engine ----------------
        self.recent_keys = deque(maxlen=RECENT_BLOCK_COUNT)
        try:
            for k in json.loads(RECENT_FILE.read_text(encoding="utf-8"))[-RECENT_BLOCK_COUNT:]:
                self.recent_keys.append(k)
        except Exception:
            pass

        self.update_timer = QtCore.QTimer(self)
        self.update_timer.timeout.connect(self.update_message)
        self.glitch_global_timer = QtCore.QTimer(self)
        self.glitch_global_timer.setSingleShot(True)
        self.glitch_global_timer.timeout.connect(self._glitch_global_fire)
        self._glitch_schedule()

        self.conversation_active = False
        self.current_conversation = None
        self.current_conversation_index = 0
        self.gif_active = False
        self.gif_started = False
        self.last_gif_path = None
        self.gif_by_key = {message_key(t): g for (_n, _f, t, g) in GIF_MESSAGES}
        self.gif_chain = None                     # a message that is waiting to be followed by its GIF
        self.gif_chain_timer = QtCore.QTimer(self)
        self.gif_chain_timer.setInterval(200)
        self.gif_chain_timer.timeout.connect(self._gif_chain_tick)

        # conversation pause/resume (waits for the monitor)
        self._conv_token = 0
        self._conv_waiting = False
        self._conv_pending = None
        self._conv_delay = 0
        self._conv_dots = False
        self._conv_pushed_for = None

        # optional: quit automatically when the game closes
        if "--with-game" in sys.argv:
            self._start_game_watch()

        # the message engine runs whether or not the monitor is visible
        self.engine_started = False
        if START_ENGINE_AT_LAUNCH:
            self.engine_started = True
            QtCore.QTimer.singleShot(INITIAL_MESSAGE_DELAY_MS, self.update_message)

        # create + paint every window once (parked above the screen) so the FIRST slide down is smooth
        QtCore.QTimer.singleShot(300, self._prewarm)

        # ---------------- hotkey (polling) ----------------
        self._key_state = {}
        self.hotkey_timer = QtCore.QTimer(self)
        self.hotkey_timer.setInterval(HOTKEY_POLL_MS)
        self.hotkey_timer.timeout.connect(self._poll_hotkey)
        self.hotkey_timer.start()

        # ---------------- menu detection ----------------
        self._menu_auto_hidden = False       # True when the monitor was put away by the menu check
        self._menu_since = None              # when the current cursor state began
        self._menu_state = None
        if MENU_DETECT:
            self.menu_timer = QtCore.QTimer(self)
            self.menu_timer.setInterval(MENU_POLL_MS)
            self.menu_timer.timeout.connect(self._poll_menu)
            self.menu_timer.start()

    def _users_tick(self):
        """Random walk between USERS_MIN and USERS_MAX; goes up and down."""
        if self._glitching:
            return
        step = random.choice([d for d in range(-USERS_STEP, USERS_STEP + 1) if d != 0])
        target = max(USERS_MIN, min(USERS_MAX, self.users_n + step))
        self._users_target = target
        if not hasattr(self, "_users_roll"):
            self._users_roll = QtCore.QTimer(self)
            self._users_roll.timeout.connect(self._users_roll_step)
        if not self._users_roll.isActive():
            self._users_roll.start(USERS_ROLL_MS)

    def _users_roll_step(self):
        """Roll the shown number one step toward the new value."""
        if self._glitching:
            return
        if self.users_n == self._users_target:
            self._users_roll.stop()
            return
        self.users_n += 1 if self._users_target > self.users_n else -1
        self.users_label.set_count(self.users_n)
        if self.users_n == self._users_target:
            self._users_roll.stop()

    # ---------------- all-at-once glitch ----------------

    def _glitch_schedule(self):
        if not (GLITCH_ENABLED and GLITCH_GLOBAL):
            return
        lo, hi = GLITCH_EVERY_SEC
        self.glitch_global_timer.start(int(random.uniform(lo, max(lo, hi)) * 1000))

    def _glitch_global_fire(self):
        busy = (self._glitching or self.gif_active or self.gif_chain or self.conversation_active_typing()
                or not self.display.isVisible() or not self.monitor_ready())
        shown = [w for w in self.widgets if w.has_content and w.stage == "hold" and not w.typing and w.isVisible()]
        if busy or not shown:
            self.glitch_global_timer.start(4000)        # try again soon
            return
        frames = random.randint(*GLITCH_FRAMES)
        self._glitching = True
        # position + size of the noise: smaller when the monitor is up (random-message height)
        if self.monitor_mode == "random":
            rw = self.random_widget
            base = rw._base_pos + QtCore.QPoint(int(GLITCH_GIF_UP_DX_MM * self.px_per_cm / 10),
                                                int(GLITCH_GIF_UP_DY_MM * self.px_per_cm / 10))
            self.glitch_gif.set_box(base, GLITCH_GIF_UP_W, GLITCH_GIF_UP_H)
        else:
            gb = self.gif_widget._base_pos
            base = gb + QtCore.QPoint(int(GLITCH_GIF_DOWN_DX_MM * self.px_per_cm / 10),
                                      int(GLITCH_GIF_DOWN_DY_MM * self.px_per_cm / 10))
            self.glitch_gif.set_box(base, GIF_BOX_W, GIF_BOX_H)
        self.glitch_gif.set_offset(self.display.pos() - self.down_pos)
        self.glitch_gif.has_content = self.glitch_gif.available
        self.glitch_gif.play()
        self.glitch_sound.play()
        if self.users_label:
            self.users_label.set_count(0)
        self.sync_visibility()                           # noise first, text raised above it
        for w in shown:
            w.glitch_now(frames)
        QtCore.QTimer.singleShot(frames * GLITCH_FRAME_MS + 150, self._glitch_global_end)

    def _glitch_global_end(self):
        self._glitching = False
        self.glitch_gif.stop()
        self.glitch_sound.stop()
        self.glitch_gif.has_content = False
        self.glitch_gif.hide()
        if self.users_label:
            self.users_label.set_count(self.users_n)
        self.sync_visibility()
        self._glitch_schedule()

    def conversation_active_typing(self):
        return False

    def _prewarm(self):
        if self.display_down or self.display.isVisible():
            return
        try:
            self.display.move(self.up_pos)
            self.display.show()
            for w in self.riders:
                w.show()
            QtWidgets.QApplication.processEvents()
        finally:
            if not self.display_down:
                self.display.hide()
                for w in self.riders:
                    w.hide()
                self.sync_visibility()

    # ========================================================
    # GAME LINK
    # ========================================================

    def _start_game_watch(self):
        self._game_seen = False
        self._game_t0 = time.time()
        self.game_status.connect(self._on_game_status)
        self.quit_now.connect(QtWidgets.QApplication.quit)
        debug(f"Linked to the game: will quit when {GAME_EXE} closes")

        def loop():
            steam_missing = 0
            while True:
                running = game_is_running()
                if running is not None:
                    self.game_status.emit(running)
                if QUIT_WHEN_STEAM_CLOSES and running is False:
                    steam = process_running(STEAM_EXE)
                    steam_missing = steam_missing + 1 if steam is False else 0
                    if steam_missing >= 2:                 # Steam is gone (checked twice in a row)
                        debug("Steam closed - quitting the overlay")
                        self.quit_now.emit()
                        return
                time.sleep(GAME_CHECK_MS / 1000)

        threading.Thread(target=loop, daemon=True).start()

    def _on_game_status(self, running):
        if running:
            if not self._game_seen:
                _quiet["until"] = time.time() + NO_SOUND_FIRST_MS / 1000
                debug(f"Game detected - no ping for the next {NO_SOUND_FIRST_MS / 60000:.1f} min")
            self._game_seen = True
        elif self._game_seen:
            debug("Game closed - quitting the overlay")
            QtWidgets.QApplication.quit()
        elif time.time() - self._game_t0 > GAME_START_TIMEOUT_S:
            debug("Game never started - quitting the overlay")
            QtWidgets.QApplication.quit()

    # ========================================================
    # HOTKEY
    # ========================================================

    def _poll_menu(self):
        vis = cursor_visible()
        if vis is None:
            return
        if MENU_ONLY_WHEN_GAME_FOCUSED and foreground_exe() != GAME_EXE.lower():
            vis = False                      # not in the game: treat as "no menu"
            if self._menu_auto_hidden is False:
                self._menu_state = None
                return
        now = time.time()
        if vis != self._menu_state:
            self._menu_state = vis
            self._menu_since = now
            if MENU_DEBUG:
                debug(f"menu check: cursor {'VISIBLE' if vis else 'hidden'}")
        held_ms = (now - self._menu_since) * 1000

        if vis and self.display_down and not self._menu_auto_hidden and held_ms >= MENU_HIDE_DELAY_MS:
            self._menu_auto_hidden = True
            debug("Menu/inventory detected - monitor goes up")
            self.slide_up()
        elif (not vis) and self._menu_auto_hidden and held_ms >= MENU_SHOW_DELAY_MS:
            self._menu_auto_hidden = False
            debug("Menu closed - monitor comes back down")
            self.slide_down()

    def _poll_hotkey(self):
        for vks, action, label in ((HOTKEY_DOWN_VKS, self.slide_down, HOTKEY_DOWN_NAME),
                                   (HOTKEY_UP_VKS, self.slide_up, HOTKEY_UP_NAME)):
            try:
                down = any(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000 for vk in vks)
            except Exception:
                return

            if down and not self._key_state.get(label, False):    # key just went down
                debug(f"{label} pressed")
                self._menu_auto_hidden = False       # your own key press always wins over the menu check
                action()
            self._key_state[label] = down

    # ========================================================
    # POSITIONS
    # ========================================================

    def _pos_for(self, dx_cm, dy_cm):
        x = self.screen_w - PANEL_MARGIN_X - PANEL_WIDTH + int(dx_cm * self.px_per_cm)
        y = PANEL_MARGIN_Y + int(dy_cm * self.px_per_cm)
        return QtCore.QPoint(x, y)

    # ========================================================
    # DISPLAY SLIDE
    # ========================================================

    def toggle_display(self):
        if self.display_down:
            self.slide_up()
        else:
            self.slide_down()

    def _instant(self):
        """True while the monitor is fully up/hidden: messages are placed without animation."""
        return not self.display.isVisible()

    def target_pos(self):
        """Where the monitor rests while it is down: raised for one message, lower for a conversation."""
        if self.monitor_mode == "random":
            return QtCore.QPoint(self.down_pos.x(), self.down_pos.y() - self.raise_px)
        return QtCore.QPoint(self.down_pos)

    def _run_mode_cb(self):
        cb, self._mode_cb = self._mode_cb, None
        if cb:
            cb()

    def set_monitor_mode(self, mode, then=None):
        """Move the monitor to the height for this mode, then call `then`.
        If the monitor is put away (up), nothing needs to move: it just remembers the mode."""
        self.monitor_mode = mode
        self._mode_cb = then
        if not (self.display_down and self.display.isVisible()):
            self._run_mode_cb()
            return
        if self.display.pos() == self.target_pos() and self.slide_anim.state() != QtCore.QAbstractAnimation.Running:
            self._run_mode_cb()
            return
        self.slide_anim.stop()
        self.slide_anim.setEasingCurve(QtCore.QEasingCurve.InOutCubic)
        self.slide_anim.setStartValue(self.display.pos())
        self.slide_anim.setEndValue(self.target_pos())
        self.slide_anim.setDuration(MODE_SLIDE_MS)
        self.slide_anim.start()

    def _enter_convo_mode(self):
        self.set_monitor_mode("convo", then=self._conversation_next)

    def _apply_offset(self, pos):
        off = QtCore.QPoint(pos) - self.down_pos
        for w in self.riders:
            w.set_offset(off)

    def slide_down(self):
        if self.display_down:
            return                          # already down (or on its way down)
        self.display_down = True
        self.slide_anim.stop()

        if not self.engine_started:
            self.engine_started = True
            debug("First press - message timings start; the first message is already on the screen")
            self.update_message()           # monitor still hidden -> message is placed instantly

        if not self.display.isVisible():
            self.display.move(self.up_pos)
            self._apply_offset(self.up_pos)
            self.display.show()
            self.sync_visibility()          # messages come down together with the monitor
            # let the windows finish their first paint BEFORE the motion starts,
            # otherwise the first frames stall and the slide seems to start late
            QtWidgets.QApplication.processEvents()
            if not self.display_down:       # Up key was pressed meanwhile
                return

        self.slide_anim.setEasingCurve(getattr(QtCore.QEasingCurve, SLIDE_DOWN_EASING,
                                               QtCore.QEasingCurve.OutCubic))
        self.slide_anim.setStartValue(self.display.pos())
        self.slide_anim.setEndValue(self.target_pos())
        self.slide_anim.setDuration(SLIDE_DOWN_MS)
        self.slide_anim.start()
        t = self.target_pos()
        debug(f"slide down: mode={self.monitor_mode}, from y={self.display.pos().y()} to y={t.y()} "
              f"(full-down y={self.down_pos.y()}, raise={self.raise_px}px)")

    def slide_up(self):
        if not self.display_down:
            return                          # already up (or on its way up)
        self.display_down = False
        if self.gif_active and self.gif_started:
            self.gif_widget.pause()         # monitor is going away: the GIF pauses until it is open again
        self.slide_anim.stop()
        if self._mode_cb:                   # a height change was still pending: don't leave it hanging
            QtCore.QTimer.singleShot(0, self._run_mode_cb)
        self.slide_anim.setEasingCurve(QtCore.QEasingCurve.InOutCubic)
        self.slide_anim.setStartValue(self.display.pos())
        self.slide_anim.setEndValue(self.up_pos)
        self.slide_anim.setDuration(SLIDE_UP_MS)
        self.slide_anim.start()

    def _on_slide_finished(self):
        t = self.target_pos()
        got = self.display.pos()
        debug(f"slide finished: mode={self.monitor_mode}, wanted y={t.y()}, monitor is at y={got.y()}")
        if self.display_down and got != t:
            debug("WARNING: the monitor window is not where it was told to go - moving it again")
            self.display.move(t)
        self._apply_offset(self.display.pos())
        if self.display_down and self.display.pos() == self.target_pos():
            self._run_mode_cb()             # height change finished -> e.g. the conversation's 1st message
            self._conv_resume()             # monitor is fully down -> paused conversation continues
            if self.gif_active:
                self._start_gif_if_ready()
        if not self.display_down and self.display.pos() == self.up_pos:
            self.display.hide()
            self.sync_visibility()          # monitor is away -> hide the message windows too

    def sync_visibility(self):
        monitor_visible = self.display.isVisible()
        for w in self.riders:
            want = monitor_visible and w.has_content
            if want:
                if not w.isVisible():
                    w.show()
                w.raise_()
            elif w.isVisible():
                w.hide()

    # ========================================================
    # PICKING MESSAGES
    # ========================================================

    def remember(self, text):
        """Call whenever a message is actually shown (random or conversation)."""
        self.recent_keys.append(message_key(text))
        try:
            RECENT_FILE.write_text(json.dumps(list(self.recent_keys)), encoding="utf-8")
        except Exception:
            pass

    def pick_line(self, pool):
        """Random line, but never one whose text was shown in the last RECENT_BLOCK_COUNT messages."""
        recent = set(self.recent_keys)
        candidates = [ln for ln in pool if message_key(line_text(ln)) not in recent]
        if candidates:
            return random.choice(candidates)

        # everything was used recently (tiny message pool): take the least recently shown
        order = {k: i for i, k in enumerate(self.recent_keys)}
        return min(pool, key=lambda ln: order.get(message_key(line_text(ln)), -1))

    def get_message_pool(self):
        pool = _messages.copy()
        existing = set(pool)
        for conversation in CONVERSATIONS:
            if not conversation:
                continue
            name, faction, text = conversation[0]
            line = f"{name}({faction}): {text}"
            if line not in existing:
                pool.append(line)
                existing.add(line)
        # messages that are followed by a GIF must be in the pool too
        keys = {message_key(line_text(ln)) for ln in pool}
        for name, faction, text, _gif in GIF_MESSAGES:
            if message_key(text) not in keys:
                pool.append(f"{name}({faction}): {text}")
                keys.add(message_key(text))
        return pool

    def find_conversation(self, name, faction, text):
        for index, conversation in enumerate(CONVERSATIONS):
            if not conversation:
                continue
            n, f, t = conversation[0]
            if n.lower() == name.lower() and f.lower() == faction.lower() and t == text:
                return index
        return None

    # ========================================================
    # RANDOM GIF TRANSMISSIONS
    # ========================================================

    def start_gif_event(self, gif_files=None):
        if self.gif_active or self.conversation_active:
            return
        if gif_files is None:
            gif_files = sorted(p for p in GIFS_DIR.glob("*")
                               if p.is_file() and p.suffix.lower() == ".gif"
                               and p.name.lower() != GLITCH_GIF_NAME.lower()) if GIFS_DIR.exists() else []
        if not gif_files:
            self.schedule_next()
            return

        choices = [p for p in gif_files if str(p) != self.last_gif_path]
        path = random.choice(choices or gif_files)
        self.last_gif_path = str(path)
        debug(f"Starting random GIF transmission: {path.name}")

        self.gif_active = True
        self.gif_started = False
        self.update_timer.stop()
        self._rand_token = getattr(self, "_rand_token", 0) + 1

        # Clear message windows so the GIF uses the entire two-message area.
        for w in self.random_pool + [self.convo_top, self.convo_bottom]:
            w.discard()
        self.gif_widget.on_finished = self._gif_finished
        self._gif_exiting = False
        if not self.gif_widget.prepare_gif(path):
            self.gif_active = False
            self.set_monitor_mode("random")
            self.schedule_next()
            return

        # In conversation mode the monitor slides down to reveal the larger viewing area.
        self.set_monitor_mode("convo", then=self._start_gif_if_ready)
        self.sync_visibility()
        # If the monitor is currently hidden, playback waits until the user presses +.
        self._start_gif_if_ready()

    def _start_gif_if_ready(self):
        if not self.gif_active or not self.monitor_ready():
            return
        if self.gif_started:
            self.gif_widget.resume()        # monitor is open again: the paused GIF continues
            return
        if self.gif_widget.movie is None or not self.gif_widget.movie.isValid():
            self._gif_finished()
            return
        self.gif_started = True
        self.gif_widget.has_content = True  # now it may be shown
        self.sync_visibility()
        self.gif_widget.start_gif()
        debug(f"GIF playback started at {GIF_PLAYBACK_SPEED_PERCENT}% speed")

    def _gif_finished(self):
        if not self.gif_active or getattr(self, "_gif_exiting", False):
            return
        self._gif_exiting = True
        self.gif_widget.exit_gif(self._gif_finish_now)      # blur out first, then clean up

    def _gif_finish_now(self):
        self._gif_exiting = False
        if not self.gif_active:
            return
        debug("GIF transmission finished")
        self.gif_active = False
        self.gif_started = False
        self.gif_widget.stop_gif()
        self.set_monitor_mode("random")
        self.sync_visibility()
        # like after a conversation: a random message shows a few seconds later
        QtCore.QTimer.singleShot(POST_CONVERSATION_DELAY_MS, self._show_post_conversation_random)

    # ========================================================
    # RANDOM MESSAGES
    # ========================================================

    def schedule_next(self):
        if TEST_MODE:
            ms = random.randint(5, 12) * 1000
        else:
            ms = int(random.uniform(MIN_INTERVAL_SEC, max(MIN_INTERVAL_SEC, MAX_INTERVAL_SEC)) * 1000)
        self.update_timer.start(ms)
        debug(f"Next update in {ms / 1000:.1f}s")

    def update_message(self):
        if self.conversation_active or self.gif_active or self.gif_chain:
            return

        # A GIF never plays on its own: a "random GIF" is always announced by its own message first
        # ( message -> "gif uploading..." -> GIF ), see GIF_MESSAGES.
        linked = [(n, f, t, g) for (n, f, t, g) in GIF_MESSAGES if (GIFS_DIR / g).exists()]
        forced = None if NORMAL_MODE else (
            "conv" if ONLY_CONVERSATIONS else "gif" if ONLY_GIFS else "random" if ONLY_RANDOM_MESSAGES else None)
        if forced == "gif" and not linked:
            debug("ONLY_GIFS is on but no GIF from GIF_MESSAGES was found in the gifs folder")
            self.schedule_next()
            return
        if linked and (forced == "gif" or (forced is None and random.random() < GIF_EVENT_CHANCE)):
            last = Path(self.last_gif_path).name if self.last_gif_path else None
            choices = [e for e in linked if e[3] != last] or linked
            name, faction, text, gif = random.choice(choices)
            img = get_character_image(name, faction, text)
            self._show_random_message(name, text, img, faction)
            self.schedule_next()
            return

        pool = self.get_message_pool()
        if not pool:
            return

        line = self.pick_line(pool)
        faction, name, text = extract_parts(line)

        # like the GIF chance: each interval rolls whether a 2-person conversation starts
        convs = [i for i, c in enumerate(CONVERSATIONS) if c]
        recent = set(self.recent_keys)
        fresh = [i for i in convs if message_key(CONVERSATIONS[i][0][2]) not in recent] or convs
        if fresh and (forced == "conv" or (forced is None and random.random() < CONVERSATION_CHANCE)):
            self.start_conversation(random.choice(fresh))
            return
        if forced == "conv":
            self.schedule_next()
            return

        gif_keys = {message_key(t) for (_n, _f, t, _g) in GIF_MESSAGES}
        # no conversation this time: an ordinary message (never a conversation's first line)
        for _ in range(30):
            line = self.pick_line(pool)
            faction, name, text = extract_parts(line)
            if self.find_conversation(name, faction, text) is None and not (
                    forced == "random" and message_key(text) in gif_keys):
                break
        else:
            self.schedule_next()
            return

        img = get_character_image(name, faction, text)
        self._show_random_message(name, text, img, faction)
        self.schedule_next()

    def _show_random_message(self, name, text, img, faction):
        if self.gif_active:
            return
        w = self.random_widget
        if w.has_content:
            if TYPEWRITER_ON_REPLACE:
                # erase the old one (reverse typing + glitch), pause, then type the new one
                w.clear_out(on_done=lambda: QtCore.QTimer.singleShot(
                    RANDOM_REPLACE_DELAY_MS,
                    lambda: self._display_random_now(name, text, img, faction)),
                    instant=self._instant())
            else:
                # the new message simply replaces the old one - no typewriter
                self._display_random_now(name, text, img, faction, replacing=True)
        else:
            self._display_random_now(name, text, img, faction)

    # ---- message -> "gif uploading..." -> GIF ----

    def _gif_chain_begin(self, gif_name, token):
        if token != getattr(self, "_rand_token", 0) or self.conversation_active or self.gif_active:
            return
        path = GIFS_DIR / gif_name
        if not path.exists():
            debug(f"GIF for this message not found: {path}")
            return
        debug(f"This message is followed by {gif_name}")
        self.gif_chain = dict(path=path, stage="text", remaining=GIF_UPLOAD_AFTER_MS, token=token)
        self.gif_chain_timer.start()

    def _gif_chain_cancel(self):
        self.gif_chain = None
        self.gif_chain_timer.stop()
        self.random_widget.upload_label.hide()
        self.random_widget.upload_timer.stop()

    def _gif_chain_tick(self):
        c = self.gif_chain
        if c is None:
            self.gif_chain_timer.stop()
            return
        if c["token"] != getattr(self, "_rand_token", 0) or self.conversation_active or self.gif_active:
            self._gif_chain_cancel()
            return
        if not self.monitor_ready():            # monitor is up: wait until it is open
            return
        c["remaining"] -= self.gif_chain_timer.interval()
        if c["remaining"] > 0:
            return
        if c["stage"] == "text":
            self.random_widget.show_upload_text(GIF_UPLOAD_TEXT)
            c["stage"] = "gif"
            c["remaining"] = GIF_START_AFTER_MS
        else:
            path = c["path"]
            self.gif_chain = None
            self.gif_chain_timer.stop()
            self.start_gif_event([path])

    def _display_random_now(self, name, text, img, faction, replacing=False):
        if self.conversation_active:
            return
        self.remember(text)
        instant = self._instant() or (replacing and not TYPEWRITER_ON_REPLACE)
        self._rand_token = getattr(self, "_rand_token", 0) + 1
        token = self._rand_token

        gif_name = self.gif_by_key.get(message_key(text))
        on_typed = (lambda: self._gif_chain_begin(gif_name, token)) if gif_name else None

        old = self.random_widget
        if replacing and old.has_content:
            # swap to the other window; the old message bounces up and away
            new = next(rw for rw in self.random_pool if rw is not old)
            new._abort_away()
            self.random_widget = new
            if not self._instant():
                old.bounce_away(self.random_bounce_px, RANDOM_BOUNCE_MS)
                make_sound().play()          # the ping plays the moment the message arrives
                # the new message only appears once the old one is totally gone
                def show_later():
                    if token != self._rand_token or self.conversation_active:
                        return
                    self.random_widget.reset_for_show(self.random_home)
                    self.random_widget.show_message(name, text, img, faction,
                                                    play_sound=False, on_typed=on_typed,
                                                    instant=self._instant() or not RANDOM_TYPEWRITER)
                QtCore.QTimer.singleShot(RANDOM_BOUNCE_MS + RANDOM_NEW_DELAY_MS, show_later)
                return
            old.discard()

        if not self.random_widget.has_content:
            self.random_widget.reset_for_show(self.random_home)
        self.random_widget.show_message(name, text, img, faction,
                                        play_sound=True, instant=instant, on_typed=on_typed)

    # ========================================================
    # CONVERSATIONS
    # ========================================================

    def start_conversation(self, conversation_index):
        if not (0 <= conversation_index < len(CONVERSATIONS)):
            return
        conversation = CONVERSATIONS[conversation_index]
        if not conversation:
            return

        debug(f"Starting conversation {conversation_index}")
        self._rand_token = getattr(self, "_rand_token", 0) + 1     # cancel a random message still waiting to appear
        self.conversation_active = True
        self.update_timer.stop()
        self.current_conversation = conversation
        self.current_conversation_index = 0
        self._conv_token += 1
        self._conv_waiting = False
        self._conv_pending = None
        self._conv_pushed_for = None

        for rw in self.random_pool:
            if rw is not self.random_widget:
                rw._abort_away()
        # clear the random message first so nothing overlaps
        self.random_widget.clear_out(on_done=self._enter_convo_mode,
                                     instant=self._instant() or not TYPEWRITER_ON_REPLACE)

    def _conversation_next(self):
        if not self.conversation_active:
            return

        convo = self.current_conversation
        index = self.current_conversation_index
        if convo is None or index >= len(convo):
            self._conversation_finish()
            return

        name, faction, text = convo[index]
        debug(f"Conversation message {index + 1}/{len(convo)}: {name}")

        img = get_character_image(name, faction)

        def show_in(slot, replacing=False, after_dots=False):
            self.remember(text)
            if after_dots:                     # the reply replaces the typing dots
                instant = self._instant() or not TYPEWRITER_AFTER_DOTS
            else:
                instant = self._instant() or (replacing and not TYPEWRITER_ON_REPLACE)
            play = True                        # always ping (muted only in the first minutes)
            slot.show_message(name, text, img, faction,
                              on_typed=self._conversation_typed,
                              play_sound=play, instant=instant)

        self.current_conversation_index += 1

        if index == 0:
            show_in(self.convo_top)            # first message: top slot
        elif index == 1:
            dots = self.convo_bottom.typing
            show_in(self.convo_bottom, after_dots=dots)      # reply: below it
        elif self._conv_pushed_for == index:
            # the old message already bounced up when the dots appeared
            self._conv_pushed_for = None
            show_in(self.convo_bottom, after_dots=self.convo_bottom.typing,
                    replacing=not self.convo_bottom.typing)
        else:
            self._push_up_then(show_in)        # new message bounces the old one up

    def _push_up_then(self, show_new):
        """Remove the message on top, bounce the lower one up into the top slot,
        then place the new message in the (now free) bottom slot."""
        old_top, old_bottom = self.convo_top, self.convo_bottom

        def start_bounce():
            # the lower message becomes the top one
            self.convo_top, self.convo_bottom = old_bottom, old_top
            # the freed (empty, hidden) window goes back to the bottom position
            old_top.set_base_pos(self.convo_bottom_pos)

            anim = QtCore.QPropertyAnimation(old_bottom, b"basePos", self)
            anim.setStartValue(old_bottom.get_base_pos())
            anim.setEndValue(self.convo_top_pos)
            anim.setDuration(BOUNCE_MS)
            anim.setEasingCurve(QtCore.QEasingCurve.OutBounce)
            anim.start()
            self._bounce_anim = anim

            QtCore.QTimer.singleShot(NEW_MESSAGE_START_DELAY_MS,
                                     lambda: show_new(self.convo_bottom, True))

        if old_top.has_content:
            old_top.clear_out(on_done=start_bounce,
                              instant=self._instant() or not TYPEWRITER_ON_REPLACE)
        else:
            start_bounce()

    def monitor_ready(self):
        """True when the monitor is fully down (the user can actually see the screen)."""
        return self.display_down and self.display.pos() == self.target_pos()

    def _conv_schedule(self, callback, delay_ms, dots=False):
        """Run the next conversation step after delay_ms - but only while the monitor is down.
        If the monitor is up, the conversation pauses until it is shown again."""
        self._conv_token += 1
        self._conv_pending = callback
        self._conv_delay = delay_ms
        self._conv_dots = dots
        if self.monitor_ready():
            self._conv_waiting = False
            self._conv_begin_wait(self._conv_token)
        else:
            self._conv_waiting = True
            debug("Conversation paused - waiting for the monitor")

    def _conv_begin_wait(self, token):
        """Start the countdown for the pending step (typing dots first, then the reply)."""
        if self._conv_dots and DOTS_START_DELAY_MS < self._conv_delay:
            QtCore.QTimer.singleShot(DOTS_START_DELAY_MS, lambda: self._conv_dots_start(token))
        QtCore.QTimer.singleShot(self._conv_delay, lambda: self._conv_fire(token))

    def _conv_dots_start(self, token):
        if token != self._conv_token or not self.conversation_active or not self.monitor_ready():
            return
        convo = self.current_conversation
        i = self.current_conversation_index          # index of the reply that is about to come
        if convo is None or i < 1 or i >= len(convo):
            return

        name, faction, _text = convo[i]
        img = get_character_image(name, faction)

        def show_dots(slot, _replacing=False):
            slot.show_typing(name, faction, img)

        if i == 1 or self._conv_pushed_for == i:
            show_dots(self.convo_bottom)                # bottom slot is free
        else:
            self._conv_pushed_for = i                   # make room: old message bounces up first
            self._push_up_then(show_dots)

    def _conv_fire(self, token):
        if token != self._conv_token or not self.conversation_active:
            return
        if not self.monitor_ready():            # monitor was put away during the delay
            self._conv_waiting = True
            debug("Conversation paused - waiting for the monitor")
            return
        cb, self._conv_pending = self._conv_pending, None
        if cb:
            cb()

    def _conv_resume(self):
        if not self._conv_waiting or not self.conversation_active:
            return
        self._conv_waiting = False
        debug("Monitor is down - conversation continues")
        self._conv_begin_wait(self._conv_token)

    def _conversation_typed(self):
        if not self.conversation_active:
            return
        convo = self.current_conversation
        if convo is not None and self.current_conversation_index >= len(convo):
            self._conv_schedule(self._conversation_finish, CONVERSATION_END_HOLD_MS)
        else:
            self._conv_schedule(self._conversation_next, CONVERSATION_REPLY_DELAY_MS, dots=True)

    def _conversation_finish(self):
        pending = [w for w in (self.convo_top, self.convo_bottom) if w.has_content]
        if not pending:
            self.end_conversation()
            return

        remaining = [len(pending)]

        def one_done():
            remaining[0] -= 1
            if remaining[0] == 0:
                self.end_conversation()

        for w in pending:
            w.clear_out(on_done=one_done, instant=self._instant())

    def end_conversation(self):
        debug("Conversation finished")
        self._conv_token += 1
        self._conv_waiting = False
        self._conv_pending = None
        self._conv_pushed_for = None
        self.conversation_active = False
        self.current_conversation = None
        self.current_conversation_index = 0
        self.set_monitor_mode("random")     # monitor goes back up to the one-message height
        QtCore.QTimer.singleShot(POST_CONVERSATION_DELAY_MS, self._show_post_conversation_random)

    def _show_post_conversation_random(self):
        if not NORMAL_MODE and (ONLY_CONVERSATIONS or ONLY_GIFS):
            self.update_message()           # test mode: straight on to the next conversation / GIF
            return
        # normal messages only, so this can't immediately start another conversation
        pool = list(_messages)
        if not pool:
            self.schedule_next()
            return

        line = self.pick_line(pool)
        faction, name, text = extract_parts(line)
        img = get_character_image(name, faction, text)
        self._show_random_message(name, text, img, faction)
        self.schedule_next()


# ============================================================
# MAIN
# ============================================================

def replace_old_instance():
    """Only one overlay at a time. If an older copy of this script is still running (for example the
    invisible one Steam started), close it so the new copy takes over."""
    me = os.getpid()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        old = int(PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        old = None

    if old and old != me:
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {old}", "/NH"],
                                 capture_output=True, text=True, timeout=8,
                                 creationflags=flags).stdout.lower()
            if "python" in out:                       # only ever close a python process
                subprocess.run(["taskkill", "/PID", str(old), "/F"],
                               capture_output=True, timeout=8, creationflags=flags)
                debug(f"Closed the older overlay (process {old})")
        except Exception:
            pass

    try:
        PID_FILE.write_text(str(me), encoding="utf-8")
    except Exception:
        pass

    def cleanup():
        try:
            if PID_FILE.read_text(encoding="utf-8").strip() == str(me):
                PID_FILE.unlink()
        except Exception:
            pass

    atexit.register(cleanup)


def main():
    try:
        LOG_FILE.write_text("", encoding="utf-8")       # fresh log for each run
    except Exception:
        pass
    for _note in _SETTINGS_NOTES:
        debug(_note)
    replace_old_instance()
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    ctrl = OverlayApp()

    debug(f"Ready. Press {HOTKEY_DOWN_NAME} to bring the monitor down, {HOTKEY_UP_NAME} to put it away "
          f"(you should see '{HOTKEY_DOWN_NAME} pressed' / '{HOTKEY_UP_NAME} pressed' here)")

    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        input("\nCrashed. Press Enter to close...")
