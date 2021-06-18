import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="discord-analyzer",
    version="1.0.2",
    author="Rodrigo Palmeirim",
    author_email="rodrigohpalmeirim@hotmail.com",
    url="https://github.com/rodrigohpalmeirim/discord-analyzer",
    description="CLI tool for scanning Discord servers and visualizing statistics",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="python CLI Discord server scan analize statistics metrics table chart shell terminal",
    packages=setuptools.find_packages(),
    classifiers=[
        "Environment :: Console",
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Natural Language :: English",
    ],
    python_requires=">=3.6",
    py_modules=["discord_analyzer"],
    package_dir={'':'discord_analyzer'},
    install_requires=["discord", "emoji", "tabulate", "pytz", "tzlocal"],
    entry_points={
        "console_scripts": [
            "discord-analyzer=discord_analyzer:main",
        ]
    },
)
