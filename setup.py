from setuptools import (setup, find_packages)

from drs_filer import __version__

with open('README.md', 'r') as fh:
    long_description = fh.read()

setup(
    name='drs-filer',
    version=__version__,
    author='ELIXIR Cloud & AAI',
    author_email='sarthakgupta072@gmail.com',
    description='Lightweight, flexible Flask/Gunicorn-based \
                    GA4GH DRS implementation',
    long_description=long_description,
    long_description_content_type="text/markdown",
    license='Apache License 2.0',
    url='https://github.com/elixir-cloud-aai/drs-filer.git',
    packages=find_packages(),
    keywords=(
        'ga4gh drs elixir rest restful api app server openapi '
        'swagger mongodb python flask'
    ),
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Science/Research',
        'Topic :: Scientific/Engineering :: Bio-Informatics',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    install_requires=[],
)
