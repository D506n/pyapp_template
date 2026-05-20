from magutils.env import environ
from magutils.env.mixins import APIMixin


@environ()
class Env(APIMixin):
    pass