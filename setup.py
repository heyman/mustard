from setuptools import setup, find_packages
from io import open

setup(
    name='mustard',
    version='0.1.0',
    description='DIY Docker PAAS',
    long_description=open('README.rst', encoding='utf-8').read(),
    author='Jonatan Heyman',
    author_email='jonatan@heyman.info',
    url='https://github.com/heyman/mustard',
    download_url='https://pypi.python.org/pypi/mustard',
    license='MIT',
    packages=find_packages(exclude=('tests', 'example')),
    install_requires=[
        'click',
        'fabric',
    ],
    entry_points={
        'console_scripts': [
            'mustard = mustard.cli:main',
        ]
    },
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Topic :: System :: Networking',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
