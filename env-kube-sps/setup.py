
from setuptools import setup, find_packages  # type: ignore

setup(
    name='env-kube-sps',
    version='1.0.1',
    packages=['env_kube_sps'],
    install_requires=[
        "boto3",
        "kubernetes<20",
        "Click<8.0.0"
    ],
    entry_points='''
        [console_scripts]
        env-kube-sps=env_kube_sps:run
    ''',
)


