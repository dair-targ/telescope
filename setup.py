from setuptools import setup, find_packages

setup(
    name='Telescope',
    version='1',
    packages=find_packages(),
    url='',
    license='',
    author='Vladimir Berkutov',
    author_email='vladimir.berkutov@gmail.com',
    description='',

    install_requires=[
        'pyserial==3.0.1',
        'pytest==2.9.1',
    ]
)
