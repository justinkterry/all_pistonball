from stable_baselines.common.policies import CnnPolicy
from stable_baselines import PPO2
from stable_baselines.common.callbacks import EvalCallback
from stable_baselines.common.evaluation import evaluate_policy
from pettingzoo.butterfly import pistonball_v3
import supersuit as ss
import random
import string
import logging
from ray import tune
from ray.tune import track
from ray.tune.suggest.ax import AxSearch

logger = logging.getLogger(tune.__name__)
logger.setLevel(
    level=logging.CRITICAL
)  # Reduce the number of Ray warnings that are not relevant here.

from ax.service.ax_client import AxClient
from ax.utils.tutorials.cnn_utils import train

ax = AxClient(enforce_sequential_optimization=False)
ax.create_experiment(
    name="mnist_experiment",
    parameters=[
        {"name": "gamma", "type": "range", "bounds": [.9, .99], "log_scale": True,  "value_type": 'float'},
        {"name": "n_steps", "type": "range", "bounds": [10, 125], "log_scale": False,  "value_type": 'int'},
        {"name": "ent_coef", "type": "range", "bounds": [0, .25], "log_scale": True,  "value_type": 'float'},
        {"name": "learning_rate", "type": "range", "bounds": [5e-6, .003], "log_scale": True,  "value_type": 'float'},
        {"name": "vf_coef", "type": "range", "bounds": [.1, 1], "log_scale": False,  "value_type": 'float'},
        {"name": "max_grad_norm", "type": "range", "bounds": [0, 1], "log_scale": False,  "value_type": 'float'},
        {"name": "lam", "type": "range", "bounds": [.9, 1], "log_scale": False,  "value_type": 'float'},
        {"name": "nminibatches", "type": "range", "bounds": [4, 4096], "log_scale": False,  "value_type": 'int'},
        {"name": "noptepochs", "type": "range", "bounds": [3, 50], "log_scale": False,  "value_type": 'float'},
        {"name": "cliprange_vf", "type": "range", "bounds": [0, 1], "log_scale": False,  "value_type": 'float'},
        {"name": "n_envs", "type": "range", "bounds": [1, 8], "log_scale": False,  "value_type": 'int'},
    ],
    objective_name="mean_reward",
    minimize=False,
)


def make_env(n_envs):
    env = pistonball_v3.parallel_env(n_pistons=20, local_ratio=0, time_penalty=-0.1, continuous=True, random_drop=True, random_rotate=True, ball_mass=0.75, ball_friction=0.3, ball_elasticity=1.5, max_cycles=125)
    env = ss.color_reduction_v0(env, mode='B')
    env = ss.dtype_v0(env, 'float32')
    env = ss.resize_v0(env, x_size=84, y_size=84)
    env = ss.normalize_obs_v0(env, env_min=0, env_max=1)
    env = ss.frame_stack_v1(env, 3)
    env = ss.pettingzoo_env_to_vec_env_v0(env)
    env = ss.concat_vec_envs_v0(env, n_envs, num_cpus=4, base_class='stable_baselines')
    return env


def train(parameterization):
    letters = string.ascii_lowercase
    folder = ''.join(random.choice(letters) for i in range(10))+'/'
    env = make_env(parameterization['n_envs'])
    del parameterization['n_envs']
    eval_callback = EvalCallback(env, best_model_save_path='~/logs/'+folder, log_path='~/logs/'+folder, eval_freq=20000, deterministic=False, render=False)
    model = PPO2(CnnPolicy, env, parameterization)
    model.learn(total_timesteps=2000000, callback=eval_callback)
    model = PPO2.load('~/logs/'+folder+'best_model')
    mean_reward, std_reward = evaluate_policy(model, model.get_env(), n_eval_episodes=10)
    tune.report(negative_mean_reward=mean_reward)


analysis = tune.run(
    train,
    num_samples=4,
    search_alg=AxSearch(ax_client=ax, max_concurrent=2, mode="max"),
    verbose=2,
    resources_per_trial={"gpu": 1, "cpu": 5},
)


ax.save_to_json_file()


"""
Minirun (2 machines, 2 GPUs each, 2 iterations):
Make sure nothing crashes
Make sure ax saving works
Make sure resource allocations are respected
Make sure logging gives me everything I want
Watch ray dashboard
Make sure the reported optimal hyperparameters are the real ones
See if verbose needs to be changes

Future problems:
SB rendering code

Future upgrades:
ent coeff schedule
Orthogonal policy initialization
Check VF sharing is on
LSTMs/GRUs/etc
Adam annealing
KL penalty?
Remove unnecessary preprocessing
Policy compression/lazy frame stacking?
PPG
Policy architecture in search

"""
