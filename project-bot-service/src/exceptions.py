class BotApiException(Exception):
    def __init__(self, description: str, code: str):
        self.description = description
        self.code = code
        super().__init__(description)
