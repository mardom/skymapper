import os
import numpy as np
from .. import register_survey

# metaclass for registration.
# see https://effectivepython.com/2015/02/02/register-class-existence-with-metaclasses/
class Meta(type):
    def __new__(meta, name, bases, class_dict):
        cls = type.__new__(meta, name, bases, class_dict)
        register_survey(cls)
        return cls

class BaseSurvey(object):
    @staticmethod
    def load():
        pass

class Survey(BaseSurvey, metaclass=Meta):
    pass

class DES(Survey):
    def load():
        """Returns RA, Dec of the survey footprint."""
        this_dir, this_filename = os.path.split(__file__)
        datafile = os.path.join(this_dir, "des-round17-poly.txt")
        data = np.loadtxt(datafile)
        return data[:,0], data[:,1]

#register_survey(DES)
