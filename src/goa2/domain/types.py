from typing import NewType

class HeroID(str):
    pass

class CardID(str):
    pass

UnitID = NewType('UnitID', str)
BoardEntityID = NewType('BoardEntityID', str)
