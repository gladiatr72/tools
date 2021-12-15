
from setuptools import setup, find_packages  # type: ignore

setup(
    name='mkeksauth',
    version='1.0.5',
    py_modules=['src.mkeksauth'],
    install_requires=[
        "boto3==1.13.6",
        "click==6.7",
        "colorama==0.4.3",
#        "kubernetes==11.0.0",
        "pyaml==19.12.0",
    ],
    entry_points='''
        [console_scripts]
        mkeksauth=src.mkeksauth:cli
    ''',
)


