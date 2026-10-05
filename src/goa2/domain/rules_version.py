# A game keeps the rules version it was created under for its whole life.
# Rewinds and replays rebuild a game by re-running its recorded decisions, so a
# rule change that alters which decisions the engine asks for must be gated on
# this version; otherwise games started before the change can no longer rebuild.
# Saves and replay logs written before versioning existed are version 0.

REPERFORM_OFFERS_REPLACEMENT = 1  # Fast Travel / Clear may replace a re-performed primary
ATTACK_IMMUNITY_COVERS_WHOLE_ACTION = 2  # Attack immunity covers every effect of the attack
HURRY_UP_INITIATIVE_OVERRIDE = 3  # Hurry Up! overrides Initiative only while the card is unresolved
TARGET_DEFEAT_LOG = 4  # "if the target is (not) defeated" reads the defeat log, not block_succeeded
EMPTY_MEANS_NOT_OBSTACLE = 5  # a space that counts as an obstacle for the performer is not empty
TOKENS_CANNOT_CROSS_MINES = 6  # mines are passable only for units, not a moved token like Pyro

CURRENT_RULES_VERSION = TOKENS_CANNOT_CROSS_MINES
