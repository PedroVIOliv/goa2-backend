from typing import NewType

BoardEntityID = NewType("BoardEntityID", str)
UnitID = BoardEntityID
HeroID = BoardEntityID

CardID = NewType("CardID", str)
ModifierID = NewType("ModifierID", str)
