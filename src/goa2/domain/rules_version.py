# A game keeps the rules version it was created under for its whole life.
# Rewinds and replays rebuild a game by re-running its recorded decisions, so a
# rule change that alters which decisions the engine asks for must be gated on
# this version; otherwise games started before the change can no longer rebuild.
# Saves and replay logs written before versioning existed are version 0.

REPERFORM_OFFERS_REPLACEMENT = 1  # Fast Travel / Clear may replace a re-performed primary
ATTACK_IMMUNITY_COVERS_WHOLE_ACTION = 2  # Attack immunity covers every effect of the attack

CURRENT_RULES_VERSION = ATTACK_IMMUNITY_COVERS_WHOLE_ACTION
