from abc import ABC, abstractmethod
from goa2.domain.state import GameState

class Command(ABC):
    """
    Abstract Base Class for all Game Actions.
    Follows the Command Pattern.
    """
    
    @abstractmethod
    def execute(self, state: GameState) -> GameState:
        """
        Executes the command on the given state.
        Can modify state in-place or return a new state (design choice: Mutation likely for performance).
        Must return the resulting state.
        """
        pass
