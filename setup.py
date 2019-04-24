import io
import os
import re
import sys

from setuptools import setup

needs_pytest = 'pytest' in set(sys.argv)


def get_version():
    regex = r"__version__\s=\s\'(?P<version>[\d\.ab]+?)\'"

    path = 'aiocassandra/session.py'

    return re.search(regex, read(path)).group('version')


def read(*parts):
    filename = os.path.join(os.path.abspath(os.path.dirname(__file__)), *parts)

    with io.open(filename, encoding='utf-8', mode='rt') as fp:
        return fp.read()


setup(
    name='aiocassandra',
    version=get_version(),
    author='Victor Kovtun',
    author_email='hellysmile@gmail.com',
    url='https://github.com/aio-libs/aiocassandra',
    description='Simple threaded cassandra wrapper for asyncio',
    long_description=read('README.rst'),
    install_requires=['cassandra-driver', 'async-generator'],
    setup_requires=['pytest-runner'] if needs_pytest else [],
    tests_require=['pytest', 'pytest-asyncio', 'pytest-cov'],
    python_requires='>=3.4.0',
    packages=['aiocassandra'],
    zip_safe=False,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Framework :: AsyncIO',
    ],
    keywords=['cassandra', 'asyncio'],
)
