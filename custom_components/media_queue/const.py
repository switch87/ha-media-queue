"""Constants for the media queue integration."""

DOMAIN = "media_queue"

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
SAVE_DELAY = 5

# Most items one queue holds (and one add may put in).
QUEUE_LIMIT = 1000
# Playback-only changes (a new current item) are written this much later.
PLAYBACK_SAVE_DELAY = 60
