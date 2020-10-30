import abc


class IRecord():
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def update(self, *argv): pass

    @abc.abstractmethod
    def link(self, linkTo: 'IRecord'): pass

class IBackend():
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def createRecord() -> IRecord: pass

    @abc.abstractmethod
    def findRecord(self, *argv) -> IRecord: pass

class ICluster():
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def harvest(self, backend: IBackend): pass

