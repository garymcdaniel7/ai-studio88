class AIStudioSelectors:
    NAV_BAR = "nav"
    MAIN_TITLE = "h1"

    @classmethod
    def get_selector(cls, element_name):
        selectors = {
            "navigation bar": cls.NAV_BAR,
            "main title": cls.MAIN_TITLE
        }
        return selectors.get(element_name)