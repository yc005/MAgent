""" random """

import numpy as np
from .base import TFBaseModel


class Random(TFBaseModel):
    def __init__(self, env, handle, name, eval_names=None):
        """init a model

        Parameters
        ----------
        env: Environment
            environment
        handle: Handle (ctypes.c_int32)
            handle of this group, can be got by env.get_handles
        name: str
            name of this model
        """
        TFBaseModel.__init__(self, env, handle, name, "random")
        # ======================== set config  ========================
        self.env = env
        self.handle = handle
        self.name = name
        self.n_action = env.get_action_space(handle)[0]

    def infer_action(self, raw_obs, ids, *args, **kwargs):  # Is done related to not using ids?
        """infer action for a batch of agents

        Parameters
        ----------
        raw_obs: tuple(numpy array, numpy array)
            raw observation of agents tuple(views, features)
        ids: numpy array
            ids of agents

        Returns
        -------
        acts: numpy array of int32
            actions for agents
        """
        view, feature = raw_obs[0], raw_obs[1]
        n = len(view)

        actions = np.random.randint(self.n_action, size=n, dtype=np.int32)
        return actions

    def train(self, sample_buffer, print_every=1000):
        pass

