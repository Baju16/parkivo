class FakeEurekaClient:
    """Zamiennik klienta Eureka: testy nie łączą się z prawdziwym rejestrem."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []
        self.starts = 0
        self.stops = 0

    async def start(self):
        self.starts += 1

    async def stop(self):
        self.stops += 1

    async def do_service(self, service_name, path, return_type=None, timeout=None):
        self.calls.append((service_name, path, return_type, timeout))
        if self.error:
            raise self.error
        return self.response
