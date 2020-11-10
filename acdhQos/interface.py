import abc


class IRecord():
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def update(self, data): pass

    @abc.abstractmethod
    def link(self, linkTo: 'IRecord'): pass

class IBackend():
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def createRecord(self) -> IRecord: pass

    @abc.abstractmethod
    def findRecord(self, data) -> IRecord: pass

    @abc.abstractmethod
    def begin(self): pass

    @abc.abstractmethod
    def end(self, log): pass

class ICluster():
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def harvest(self): pass

