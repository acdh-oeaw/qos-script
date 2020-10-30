from acdhQos.interface import *

class Redmine(IBackend):

    def createRecord() -> IRecord:
        pass

    def findRecord(self, *argv) -> IRecord:
        pass


class RedmineRecord(IRecord):
    def __init__(self):
        pass

    def update(self, data):
        # - take care of redmine id duplicates
        # - take care of checking inContainerApps
