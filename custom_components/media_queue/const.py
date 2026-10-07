"""Constants for the media queue integration."""

DOMAIN = "media_queue"

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
# 2 (0.2.0): shuffle and repeat per queue. A minor bump: 0.1.0 still reads it.
STORAGE_MINOR_VERSION = 2
SAVE_DELAY = 5

# Most items one queue holds (and one add may put in).
QUEUE_LIMIT = 1000
# Playback-only changes (a new current item) are written this much later.
PLAYBACK_SAVE_DELAY = 60
