from aiogram.fsm.state import State, StatesGroup

class YouTubeConsentStates(StatesGroup):
    waiting_for_consent = State()
